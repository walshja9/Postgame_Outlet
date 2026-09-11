"""Descriptive full-inventory usage admission; no fetching, fitting or state writes."""
import argparse
import copy
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re

from pgo_season import load_current, require, utc
from pgo_season_rollover import load_archive, verify_finals
from research.pgo_injury_usage_20260911 import audit
from research.pgo_replacement_depth_20260910 import capture

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def link(snapshot, roster, snaps, finals, target_captured_at):
    """Caller verifies sources; adapt a detached inventory to the established join."""
    projected = copy.deepcopy(snapshot)
    require(len({game['game_id'] for game in projected['games']}) == len(projected['games']), 'Duplicate pregame game')
    teams = {team['team']: team for team in projected['teams']}
    require(len(teams) == len(projected['teams']), 'Duplicate inventory team')
    known = set(); ready = set()
    if projected.get('inventory_version') == 1:
        for name, team in teams.items():
            if team.get('inventory_version') != 1 or not isinstance(team.get('defenders'), list):
                continue
            for player in team['defenders']:
                pid = player.get('gsis_id')
                require(isinstance(pid, str) and re.fullmatch(r'00-\d{7}', pid) and pid not in known,
                        'Duplicate or invalid inventory player identity')
                require(type(player.get('confirmed_unavailable')) is bool, 'Invalid inventory availability flag')
                known.add(pid)
            require(team['unavailable_players'] == [p for p in team['defenders'] if p['confirmed_unavailable']],
                    'Inventory differs from the preserved unavailable subset')
            team['unavailable_players'] = team['defenders']
            ready.add(name)
    unavailable = [dict(game_id=game['game_id'], reason='MISSING_PREGAME_INVENTORY')
                   for game in projected['games'] if not {game['home'], game['away']} <= ready]
    projected['games'] = [game for game in projected['games'] if {game['home'], game['away']} <= ready]
    projected['teams'] = [teams[name] for name in teams if name in ready]
    for result in finals:
        require(utc(result['kickoff']) < utc(result['finalized_at']), 'Final observation must follow kickoff')
        require(all(type(result[key]) is int and result[key] >= 0 for key in ('home_score', 'away_score'))
                and result['actual_margin'] == result['home_score']-result['away_score'], 'Invalid final scores')
    result = audit.link(projected, roster, snaps, finals, target_captured_at)
    rows = result['rows']
    result.update(inventory_version=1, cohort='Complete preserved defender inventory; listed backups are not proven replacements',
                  unavailable_inventory_games=unavailable, observed_zero=sum(r['defensive_snaps'] == 0 for r in rows),
                  observed_positive=sum(r['defensive_snaps'] is not None and r['defensive_snaps'] > 0 for r in rows),
                  pending=sum('NO_VERIFIED_FINAL' in r['exclusions'] for r in rows),
                  missing_target=sum('NO_MATCHED_TARGET_ROW' in r['exclusions'] and 'NO_VERIFIED_FINAL' not in r['exclusions'] for r in rows),
                  prospective_status='UNAVAILABLE', forecast_adjustment=None)
    return result


def load_inventory(root, pointer):
    """Verify archive bytes and reproduce new inventories; never reconstruct old ones."""
    state, manifest = load_archive(root, pointer)
    require(state['schema_version'] == 1 and state['season'] == 2026, 'Unexpected pregame season state')
    snapshot = copy.deepcopy(state.get('replacement_depth') or {})
    if snapshot.get('inventory_version') != 1:
        return dict(snapshot, teams=snapshot.get('teams', []), games=snapshot.get('games', []),
                    sources=snapshot.get('sources', []), generated_at=snapshot.get('generated_at', state['checked_at']),
                    completed_at=manifest['created_at']), []
    require(snapshot['status'] == 'DESCRIPTIVE / NOT IN MODEL' and snapshot['forecast_adjustment'] is None,
            'Pregame inventory is not a valid descriptive capture')
    require(utc(snapshot['generated_at']) <= utc(state['checked_at']) <= utc(manifest['created_at']),
            'Pregame durable clock differs')
    replay = capture.capture(state, root, snapshot['generated_at'])
    require(all(snapshot.get(key) == replay.get(key) for key in
                ('inventory_version', 'teams', 'games', 'sources', 'generated_at', 'source_as_of')),
            'Inventory does not reproduce from its captured sources')
    roster_refs = [ref for ref in snapshot['sources'] if ref.get('url') == capture.ROSTER_URL]
    require(len(roster_refs) == 1, 'Missing or ambiguous pregame roster')
    roster = list(capture._csv(capture.read_source(root, roster_refs[0], snapshot['generated_at'])))
    snapshot['completed_at'] = manifest['created_at']
    return snapshot, roster


def load_target(source):
    receipt = json.loads((source / 'receipt.json').read_bytes())
    raw = (source / 'response.bin').read_bytes()
    require(receipt['url'] == audit.URL and receipt['sha256'] == capture._sha(raw) and receipt['bytes'] == len(raw),
            'Target source bytes or URL differ')
    require(utc(receipt['started_at']) <= utc(receipt['captured_at']) <= datetime.now(timezone.utc), 'Invalid target capture clock')
    require(not receipt.get('published_at') or utc(receipt['published_at']) <= utc(receipt['captured_at']), 'Target publication follows capture')
    require(type(receipt['http_status']) is int and 100 <= receipt['http_status'] <= 599, 'Invalid target HTTP status')
    rows = []
    if receipt['http_status'] == 200:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        require({'game_id', 'season', 'week', 'game_type', 'team', 'opponent', 'pfr_player_id', 'defense_snaps'} <= set(reader.fieldnames or []),
                'Target CSV schema differs')
        rows = list(reader)
    return rows, receipt


def run(pregame_pointer, source, output, root=ROOT / 'docs/evidence/season-2026'):
    root, source, output = Path(root), Path(source), Path(output)
    require(output.resolve().parent == HERE and not output.exists(), 'Use a new exclusive output directory in this study')
    selected = Path(pregame_pointer).read_bytes()
    snapshot, roster = load_inventory(root, json.loads(selected))
    snaps, target = load_target(source)
    current_pointer = (root / 'current.json').read_bytes()
    state = load_current(root)
    require(state is not None, 'No verified final state')
    verify_finals(state, root, max((r['week'] for r in state['results']), default=0))
    result = link(snapshot, roster, snaps, state['results'], target['captured_at'])
    result.update(target_source=target, final_state_checked_at=state['checked_at'],
                  historical_admission='BLOCKED FOR FITTING',
                  limitations=['No fitting, numerical injury adjustment or predictive admission.',
                               'Missing inventory is never reconstructed from later rosters.',
                               'Defensive snaps do not prove which assignment a backup filled.',
                               'Targets observed before their verified final remain unavailable.'])
    require((root / 'current.json').read_bytes() == current_pointer, 'Final-state pointer changed during report')
    tracked = [Path(__file__), HERE / 'charter.md', Path(capture.__file__), Path(audit.__file__),
               ROOT / 'tests/test_pgo_defender_inventory.py', source / 'receipt.json', source / 'response.bin']
    receipt = dict(completed_at=datetime.now(timezone.utc).isoformat(),
                   inputs={path.relative_to(ROOT).as_posix(): dict(sha256=capture._sha(path.read_bytes()), bytes=path.stat().st_size) for path in tracked},
                   source_state_unchanged=True)
    artifacts = {'admission.json': capture._json(result), 'pregame-pointer.json': selected,
                 'final-state-pointer.json': current_pointer, 'receipt.json': capture._json(receipt)}
    output.mkdir()
    for name, raw in artifacts.items():
        (output / name).write_bytes(raw)
    (output / 'manifest.json').write_bytes(capture._json(dict(files={name: dict(sha256=capture._sha(raw), bytes=len(raw)) for name, raw in artifacts.items()})))
    return {key: value for key, value in result.items() if key not in ('rows', 'excluded_target_rows', 'target_source')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pregame-pointer', type=Path, required=True, help='Exact pointer to the originally saved pregame season archive')
    parser.add_argument('--source', type=Path, required=True, help='Preserved snap source folder with response.bin and receipt.json')
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(**vars(parser.parse_args())), indent=2))
