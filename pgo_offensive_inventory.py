"""Future-only offensive non-QB inventory from verified archives; no model values."""
from collections import defaultdict
import copy
from datetime import timedelta
from pathlib import Path
import re

from pgo_season import require, sha, utc
from pgo_season_availability import load_availability
from pgo_season_rollover import load_archive
from pgo_sources import CURRENT_TEAMS, normalize_team
from research.pgo_replacement_depth_20260910 import capture as source

POSITIONS = frozenset('RB FB WR TE C G OG LG RG T OT LT RT OL'.split())
STATUSES = frozenset('ACT RES DEV EXE INA'.split())
STATUS = 'DESCRIPTIVE / NOT IN MODEL'


def build_teams(roster, depth, observations, checked_at, depth_captured_at):
    clock, cutoff = utc(checked_at), utc(depth_captured_at)
    indexed = defaultdict(list); known = set(); unresolved = defaultdict(list)
    for row in roster:
        team = normalize_team(row.get('team', ''))
        if row.get('position', '').upper() not in POSITIONS or row.get('status') not in STATUSES:
            continue
        require(team in CURRENT_TEAMS and str(row.get('season')) == '2026' and row.get('full_name'),
                'Invalid current offensive roster team, season or name')
        pid = row.get('gsis_id', '')
        if not re.fullmatch(r'00-\d{7}', pid):
            unresolved[team].append(dict(name=row['full_name'], position=row['position'], roster_status=row['status'],
                                         reason='MISSING_STABLE_IDENTITY'))
            continue
        require(pid not in known, 'Duplicate current offensive roster identity')
        known.add(pid); indexed[team].append(row)
    require(set(indexed) | set(unresolved) == set(CURRENT_TEAMS), 'Incomplete offensive roster team coverage')
    latest = {}; selected = defaultdict(list)
    for row in depth:
        team = normalize_team(row.get('team', ''))
        if row.get('pos_abb', '').upper() not in POSITIONS or row.get('pos_grp', '').casefold() == 'special teams':
            continue
        require(team in CURRENT_TEAMS, 'Invalid offensive depth team')
        stamp = utc(row['dt'])
        if stamp > cutoff: continue
        if team not in latest or stamp > latest[team]: latest[team] = stamp; selected[team] = []
        if stamp == latest[team]: selected[team].append(row)
    require(set(latest) == set(CURRENT_TEAMS), 'Incomplete offensive depth team coverage')
    teams = []
    for team in sorted(CURRENT_TEAMS):
        saved = observations.get(team, {})
        fresh = saved.get('checked_at') and clock-utc(saved['checked_at']) <= timedelta(hours=24)
        official = defaultdict(list); unresolved_official = []
        roster_ids = {row['gsis_id'] for row in indexed[team]}
        for item in saved.get('observations', []):
            require(utc(item['captured_at']) <= clock and
                    (not item.get('published_at') or utc(item['published_at']) <= utc(item['captured_at'])),
                    'Invalid offensive availability source clock')
            if not fresh or clock-utc(item['captured_at']) > timedelta(hours=24): continue
            if item.get('gsis_id') in roster_ids and item.get('identity_status') == 'RESOLVED':
                official[item['gsis_id']].append(item)
            elif item.get('position', '').upper() in POSITIONS:
                unresolved_official.append(item.get('name', 'Unknown player'))
        stamp = latest[team]; depth_fresh = clock-stamp <= timedelta(hours=24)
        depth_by_id = defaultdict(list); unresolved_depth = []; slots = set()
        for row in selected[team]:
            identity = (row.get('gsis_id'), row.get('pos_abb'), row.get('pos_slot'))
            require(identity not in slots, 'Duplicate offensive depth identity/slot'); slots.add(identity)
            if row.get('gsis_id') not in roster_ids:
                unresolved_depth.append(dict(gsis_id=row.get('gsis_id') or None, name=row.get('player_name'),
                                             reason='NO_CURRENT_TEAM_ROSTER_IDENTITY'))
            elif depth_fresh: depth_by_id[row['gsis_id']].append(row)
        players = []
        for row in indexed[team]:
            pid = row['gsis_id']; aliases = source.evidence.aliases(row); entries = depth_by_id[pid]
            matched = all(source.evidence.ch._normalize_player_name(r.get('player_name', '')) in aliases for r in entries)
            roles = []
            if matched:
                for entry in entries:
                    require(re.fullmatch(r'[1-9]\d*', entry.get('pos_rank', '')) is not None, 'Invalid offensive provider depth rank')
                    roles.append(dict(position=entry['pos_abb'], rank=int(entry['pos_rank']),
                                      slot=entry.get('pos_slot') or None, group=entry.get('pos_grp')))
            admitted = []
            for item in official[pid]:
                if source.evidence.ch._normalize_player_name(item.get('name', '')) in aliases: admitted.append(copy.deepcopy(item))
                else: unresolved_official.append(item.get('name', 'Unknown player'))
            statuses = sorted({item['status'] for item in admitted})
            players.append(dict(gsis_id=pid, name=row['full_name'], position=row['position'], roster_status=row['status'],
                                roster_context={key: row.get(key) or None for key in ('season', 'week', 'game_type')},
                                depth_status='STALE' if not depth_fresh else 'NAME_MISMATCH' if not matched else 'LISTED' if roles else 'UNLISTED',
                                depth_rows=roles, availability_statuses=statuses or ['UNKNOWN'], observations=admitted,
                                confirmed_unavailable=bool(set(statuses) & {'OUT', 'INACTIVE'}),
                                uncertain=bool(set(statuses) & {'QUESTIONABLE', 'DOUBTFUL'})))
        teams.append(dict(team=team, inventory_version=1, players=players, unresolved_roster=unresolved[team],
                          depth_snapshot_at=stamp.isoformat(), depth_status='DATED_PROVIDER_LIST' if depth_fresh else 'STALE',
                          unresolved_depth=unresolved_depth, unresolved_official_names=sorted(set(unresolved_official)),
                          report_status=saved.get('report_status', 'UNKNOWN') if fresh else 'UNKNOWN',
                          final_inactives_status=saved.get('final_inactives_status', 'UNKNOWN') if fresh else 'UNKNOWN',
                          availability_checked_at=saved.get('checked_at'),
                          availability_status='CURRENT' if fresh else 'STALE' if saved else 'UNKNOWN'))
    return teams


def capture(state, root, checked_at):
    """Detached observation; eligibility requires a later verified durable archive."""
    root = Path(root); clock = utc(checked_at)
    result = dict(inventory_version=1, status='BLOCKED', blocked_reason=None, generated_at=clock.isoformat(),
                  sources=[], games=[], teams=[], forecast_adjustment=None)
    refs = [*state.get('source_captures', []), *state.get('sources', []),
            *state.get('rankings', {}).get('source_captures', []),
            *state.get('replacement_depth', {}).get('sources', []), *state.get('offensive_inventory', {}).get('sources', [])]
    refs += [ref for values in state.get('edition_sources', {}).values() for ref in values]
    chosen = {}
    for url in (source.ROSTER_URL, source.DEPTH_URL):
        matches = [ref for ref in refs if ref.get('url') == url and ref.get('path')]
        if not matches: return dict(result, blocked_reason='Missing archived offensive roster/depth source.')
        require(all(utc(ref['captured_at']) <= clock for ref in matches), 'Future offensive source reference')
        ref = max(matches, key=lambda row: utc(row['captured_at']))
        if clock-utc(ref['captured_at']) > timedelta(hours=24):
            return dict(result, blocked_reason='Offensive roster/depth source is older than 24 hours.')
        require(not ref.get('published_at') or utc(ref['published_at']) <= utc(ref['captured_at']), 'Invalid offensive source publication clock')
        chosen[url] = copy.deepcopy(ref)
    roster = list(source._csv(source.read_source(root, chosen[source.ROSTER_URL], checked_at)))
    depth = source._csv(source.read_source(root, chosen[source.DEPTH_URL], checked_at))
    games = source.eligible_games(state, checked_at); observations = {}; packages = {}
    for game in games:
        ref = game.get('availability', {}).get('source_archive')
        if not ref: continue
        require(re.fullmatch(r'availability(?:-v2)?/\d{8}T\d{12}Z', ref) is not None, 'Invalid offensive availability path')
        directory = root/ref
        require(directory.resolve().is_relative_to(root.resolve()) and not directory.is_symlink()
                and not directory.parent.is_symlink(), 'Unsafe offensive availability path')
        if ref not in packages: packages[ref] = load_availability(directory)
        saved = packages[ref]['games'].get(game['game_id'])
        require(saved is not None and all(saved[key] == game[key] for key in
                ('game_id', 'season', 'week', 'game_type', 'home', 'away', 'kickoff', 'lock_at')), 'Offensive availability game differs')
        require(utc(saved['checked_at']) <= clock < utc(saved['lock_at']) and
                {key: value for key, value in game['availability'].items() if key != 'source_archive'} == saved,
                'Offensive availability snapshot differs')
        for team, info in saved['teams'].items():
            require(team in (game['home'], game['away']) and team not in observations, 'Ambiguous offensive availability team/game')
            observations[team] = dict(info, checked_at=saved['checked_at'])
    source_refs = list(chosen.values())
    for ref, package in packages.items():
        raw = (root/ref/'manifest.json').read_bytes()
        source_refs.append(dict(path=ref+'/manifest.json', sha256=sha(raw), bytes=len(raw),
                                captured_at=package['checked_at'], kind='verified_official_availability'))
    return dict(result, status=STATUS, sources=source_refs,
                teams=build_teams(roster, depth, observations, checked_at, chosen[source.DEPTH_URL]['captured_at']),
                games=[{key: game[key] for key in ('game_id', 'season', 'week', 'game_type', 'home', 'away', 'kickoff', 'lock_at')} for game in games])


def load_inventory(root, pointer):
    state, manifest = load_archive(root, pointer)
    snapshot = copy.deepcopy(state.get('offensive_inventory') or {})
    require(state['schema_version'] == 1 and state['season'] == 2026 and
            type(snapshot.get('inventory_version')) is int and snapshot['inventory_version'] == 1,
            'Missing or invalid offensive inventory version')
    require(snapshot['status'] == STATUS and snapshot['forecast_adjustment'] is None and
            utc(snapshot['generated_at']) <= utc(state['checked_at']) <= utc(manifest['created_at']), 'Invalid offensive inventory clocks/status')
    require(snapshot == capture(state, root, snapshot['generated_at']), 'Offensive inventory does not reproduce from archived sources')
    refs = [ref for ref in snapshot['sources'] if ref.get('url') == source.ROSTER_URL]
    require(len(refs) == 1, 'Missing unique offensive roster reference')
    roster = list(source._csv(source.read_source(root, refs[0], snapshot['generated_at'])))
    snapshot['completed_at'] = manifest['created_at']
    return snapshot, roster
