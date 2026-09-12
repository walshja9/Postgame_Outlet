"""Read-only, offline receipt for an observed regular-season edition transition."""
import argparse
from collections import defaultdict
import copy
from datetime import timedelta
import gzip
import json
import math
from pathlib import Path
import re

import pgo_season as season
from pgo_season import canonical, require, sha, utc


def load_archive(root, pointer):
    require(re.fullmatch(r'runs(?:-v2)?/\d{8}T\d{12}Z', pointer['path']) is not None, 'Invalid archive path')
    root = Path(root).resolve()
    directory = root / pointer['path']
    require(directory.resolve().is_relative_to(root) and not directory.is_symlink(), 'Invalid archive directory')
    manifest_path = directory / 'manifest.json'
    require(not manifest_path.is_symlink(), 'Invalid manifest symlink')
    raw = manifest_path.read_bytes()
    require(sha(raw) == pointer['manifest_sha256'], 'Archive manifest hash differs')
    manifest = json.loads(raw)
    require(set(manifest['files']) in ({'state.json'}, {'state.json.gz'}), 'Invalid archive inventory')
    name = next(iter(manifest['files']))
    require(not (directory / name).is_symlink(), 'Invalid state symlink')
    payload = (directory / name).read_bytes()
    meta = manifest['files'][name]
    require(sha(payload) == meta['sha256'] and len(payload) == meta['bytes'], 'Archive state hash differs')
    state = json.loads(gzip.decompress(payload) if name.endswith('.gz') else payload)
    season.check_starter_announcements(state, root)
    return state, manifest


def index(rows):
    result = {row['game_id']: row for row in rows}
    require(len(result) == len(rows), 'Duplicate game identity')
    return result


def check_preserved(before, after, durable=None):
    # Issuance alone is insufficient: production rejects writes that finish at T-60.
    clock = utc(durable or after['checked_at'])
    require(clock >= utc(after['checked_at']), 'Durable archive clock precedes state check')
    old = index([g for w in before['weeks'] for g in w['games']])
    new = index([g for w in after['weeks'] for g in w['games']])
    require(set(old) <= set(new), 'Previously issued game removed')
    count = 0
    for key, game in old.items():
        if clock < utc(game['kickoff']) - timedelta(minutes=60):
            continue
        def locked(row):
            row = copy.deepcopy(row)
            for field in ('forecast_status', 'grade', 'result'):
                row.pop(field, None)
            if row.get('confidence'):
                row['confidence'].pop('earned_points', None)
            return row
        require(locked(game) == locked(new[key]), 'Locked forecast or confidence changed: ' + key)
        if game.get('result') is not None:
            require(all(game.get(k) == new[key].get(k) for k in ('result', 'grade', 'confidence')), 'Accepted game grade changed')
        count += 1
    results = index(after.get('results', []))
    for key, row in index(before.get('results', [])).items():
        require(results.get(key) == row, 'Accepted final changed or removed')
    if before.get('ats'):
        from pgo_ats import _core
        after_ats = index((after.get('ats') or {}).get('games', []))
        for key, row in index(before['ats'].get('games', [])).items():
            require(key in after_ats, 'Saved sportsbook line removed')
            if clock >= utc(row['kickoff']) - timedelta(minutes=60):
                require(_core(row) == _core(after_ats[key]), 'Locked sportsbook line or choice changed')
            if row.get('result') is not None:
                require(all(row.get(k) == after_ats[key].get(k) for k in ('result', 'grade')), 'Accepted ATS grade changed')
    return count


def source_bytes(root, ref, deadline):
    require(re.fullmatch(r'(?:sources|source-archive)/[0-9a-f]{64}\.(?:json|csv\.gz)', ref['path']) is not None, 'Invalid source path')
    path = Path(root) / ref['path']
    require(not path.is_symlink() and path.resolve().is_relative_to(Path(root).resolve()), 'Invalid source symlink')
    raw = path.read_bytes()
    require(sha(raw) == ref['sha256'] and len(raw) == ref['bytes'], 'Source hash differs')
    require(utc(ref['captured_at']) <= utc(deadline), 'Source captured after edition')
    return raw


def verify_finals(state, root, completed):
    schedule = index(state['schedule'])
    finals = index(state['results'])
    parsed = {}
    for key, result in finals.items():
        require(key in schedule, 'Final is absent from schedule')
        require(result['week'] == schedule[key]['week'], 'Final week differs from schedule')
        if result['week'] > completed:
            continue
        ref = result['source']
        if ref['path'] not in parsed:
            raw = source_bytes(root, ref, state['checked_at'])
            parsed[ref['path']] = index(season.parse_scoreboard(json.loads(raw), state['schedule'], ref['captured_at'])['results'])
        verified = parsed[ref['path']].get(key)
        require(verified is not None and all(result.get(k) == v for k, v in verified.items()), 'Saved final differs from explicit provider FINAL')
    expected = {k for k, g in schedule.items() if g['week'] <= completed}
    require({g['week'] for g in schedule.values() if g['week'] <= completed} == set(range(1, completed + 1)), 'Completed-week schedule inventory is missing')
    return expected - set(finals)


def verify_statistics(state, root, completed):
    import pgo_season_model as model
    refs = state['rankings'].get('source_captures', [])
    feeds = {}
    for kind in ('team', 'player'):
        matches = [r for r in refs if r.get('url') == season.URLS[kind]]
        require(len(matches) == 1, 'Missing or ambiguous edition ' + kind + ' statistics capture')
        feeds[kind] = season.csv_rows(source_bytes(root, matches[0], state['rankings']['inputs_as_of']))
    games = [g for g in state['schedule'] if g['week'] <= completed]
    periods = {(g['season'], g['week'], g[side]) for g in games for side in ('home', 'away')}
    teams, players, seen = {}, defaultdict(list), set()
    for original in feeds['team']:
        key = model._period(original)
        if key not in periods:
            continue
        require(key not in teams, 'Duplicate team production')
        row = dict(original)
        for name in (*model.TEAM_COUNTS, 'passing_epa', 'rushing_epa'):
            row[name] = model._number(row.get(name), nullable=name not in model.TEAM_COUNTS)
        teams[key] = row
    for row in feeds['player']:
        key = model._period(row)
        if key not in periods:
            continue
        player = (*key, row.get('player_id'))
        require(row.get('player_id') and isinstance(row.get('position'), str) and player not in seen, 'Missing or duplicate player identity')
        seen.add(player)
        players[key].append(row)
    finals = index(state['results'])
    for game in games:
        result = finals[game['game_id']]
        require(utc(result['finalized_at']) <= utc(state['rankings']['inputs_as_of']), 'Edition precedes verified final')
        require(all(str(game.get('provider_scores', {}).get(k)) in {str(result[k]), str(float(result[k]))} for k in ('home_score', 'away_score')), 'Statistics schedule disagrees with final')
        model._validate_production(game, teams, players)


def observe(root=season.DEFAULT_ROOT, completed=1):
    require(type(completed) is int and 1 <= completed <= 17, 'Transition week must be between 1 and 17')
    root = Path(root)
    state = season.load_current(root)
    require(state is not None, 'No saved season state')
    pointer = season.read_json(root / 'current.json')
    current, manifest = load_archive(root, pointer)
    require(current == state, 'Current pointer changed during verification')
    report = dict(schema_version=1, observed_at=season.now(), verifier_sha256=sha(Path(__file__).read_bytes()), state_checked_at=state['checked_at'],
                  completed_week=completed, next_week=completed + 1, current_pointer=pointer,
                  status='WAITING', checks={}, limitations='Offline saved-evidence observation; not an on-time publication or prediction-quality claim.')
    if manifest.get('previous'):
        prior, _ = load_archive(root, manifest['previous'])
        require(utc(prior['checked_at']) < utc(state['checked_at']), 'Archive clock did not advance')
        report['checks']['locked_games_preserved_from_previous'] = check_preserved(prior, state, manifest.get('created_at'))
        report['previous_pointer'] = manifest['previous']
    missing = verify_finals(state, root, completed)
    report['checks']['verified_finals'] = {'missing_game_ids': sorted(missing), 'count': sum(r['week'] <= completed for r in state['results'])}
    report['checks']['rankings_completed_week'] = state['rankings']['completed_week']
    if missing:
        report['reason'] = 'Week is incomplete; real rollover cannot yet be verified.'
        return report
    if state['rankings']['completed_week'] < completed:
        report['reason'] = 'Finals are complete; statistics-ready next edition has not been saved.'
        report['saved_blocked_reason'] = state.get('blocked_reason')
        return report
    # Follow immutable pointers to the first saved edition after the target week.
    seen = {pointer['path']}
    transition, transition_pointer = state, pointer
    while manifest.get('previous'):
        previous_pointer = manifest['previous']
        require(previous_pointer['path'] not in seen, 'Archive pointer cycle')
        seen.add(previous_pointer['path'])
        previous, previous_manifest = load_archive(root, previous_pointer)
        require(utc(previous['checked_at']) < utc(current['checked_at']), 'Archive clock did not advance')
        check_preserved(previous, current, manifest.get('created_at'))
        if previous['rankings']['completed_week'] < completed:
            break
        current, manifest = previous, previous_manifest
        transition, transition_pointer = current, previous_pointer
    else:
        raise ValueError('No hash-verified pre-transition archive')
    require(transition['rankings']['completed_week'] == completed, 'Target weekly edition was skipped')
    require(not verify_finals(transition, root, completed), 'Transition lacks complete verified finals')
    verify_statistics(transition, root, completed)
    rankings = transition['rankings']['teams']
    require(len(rankings) == 32 and {r['team'] for r in rankings} == set(season.pgo_sources.CURRENT_TEAMS)
            and {r['rank'] for r in rankings} == set(range(1, 33))
            and all(math.isfinite(float(r['rating'])) for r in rankings), 'Next rankings require all 32 teams and finite ratings')
    weeks = [w for w in transition['weeks'] if w['week'] == completed + 1]
    require(len(weeks) == 1 and transition['current_week'] == completed + 1, 'Missing or duplicate next edition')
    require(weeks[0]['source_edition'] == transition['rankings']['edition'], 'Slate and rankings editions differ')
    expected = index([g for g in transition['schedule'] if g['week'] == completed + 1])
    actual = index(weeks[0]['games'])
    require(expected and set(actual) == set(expected) and all(season.identity(actual[k], expected[k]) for k in expected), 'Next fixture inventory differs')
    refs = [r for r in transition['source_captures'] if r.get('url') == season.URLS['schedule']]
    require(len(refs) == 1, 'Missing or ambiguous transition schedule source')
    captured_schedule = season.parse_schedule(source_bytes(root, refs[0], transition['checked_at']))
    captured_next = index([g for g in captured_schedule if g['week'] == completed + 1])
    require(set(expected) == set(captured_next) and all(season.identity(expected[k], captured_next[k]) for k in expected), 'Next fixtures differ from captured schedule')
    report.update(status='VERIFIED', reason='Saved week transition verified against archived source bytes.',
                  transition_pointer=transition_pointer, previous_pointer=previous_pointer)
    report['checks'].update(statistics='VERIFIED', rankings=32, next_fixtures=len(actual),
                            archives_checked=len(seen), locked_fields='PRESERVED across checked archive chain')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=season.DEFAULT_ROOT)
    parser.add_argument('--completed-week', type=int, default=1)
    parser.add_argument('--output', type=Path, help='New receipt file; existing receipts are never overwritten')
    args = parser.parse_args()
    try:
        report = observe(args.root, args.completed_week)
    except (ValueError, KeyError, OSError, TypeError) as error:
        report = dict(schema_version=1, observed_at=season.now(), status='INVALID', reason=str(error))
    raw = canonical(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as handle:
            handle.write(raw)
    print(raw.decode(), end='')
    return int(report['status'] == 'INVALID')


if __name__ == '__main__':
    raise SystemExit(main())
