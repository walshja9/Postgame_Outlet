"""Automatic descriptive defender usage; never fit or change a forecast."""
from collections import Counter
import copy
from datetime import timedelta
from http.client import HTTPException, IncompleteRead
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pgo_season import canonical, now, require, sha, utc
from pgo_season_rollover import load_archive, verify_finals
from research.pgo_defender_inventory_20260911 import inventory

PROTOCOL = Path(__file__).resolve().parent/'research/pgo_nonqb_validation_20260912/charter.md'
COUNTS = ('cohort_rows', 'eligible_final_rows', 'joined', 'observed_zero', 'observed_positive', 'missing_target', 'pending')


def _path(root, relative):
    path = root/relative
    require(path.resolve().is_relative_to(root.resolve()) and not root.is_symlink()
            and all(not member.is_symlink() for member in (path, *path.parents) if member != root.parent),
            'Unsafe usage artifact path')
    return path


def _read(root, ref):
    require(isinstance(ref, dict) and isinstance(ref.get('path'), str)
            and re.fullmatch(r'injury-usage/(?:targets/[0-9a-f]{64}/receipt|reports/[0-9a-f]{64})\.json', ref['path']),
            'Invalid usage artifact reference')
    raw = _path(root, ref['path']).read_bytes()
    require(sha(raw) == ref['sha256'] and len(raw) == ref['bytes'], 'Usage artifact bytes differ')
    value = json.loads(raw)
    require(isinstance(value, dict), 'Invalid usage artifact object')
    return value


def _write(root, relative, raw):
    path = _path(root, relative); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw, 'Usage artifact collision')
    else:
        with path.open('xb') as handle: handle.write(raw)
    return dict(path=relative, sha256=sha(raw), bytes=len(raw))


def _attempt(root, ref):
    receipt = _read(root, ref)
    require(receipt['url'] == inventory.audit.URL and utc(receipt['started_at']) <= utc(receipt['captured_at']) <= utc(now()),
            'Invalid usage source clock or URL')
    require(receipt['captured_at'] == ref['captured_at'], 'Usage source reference clock differs')
    raw = _path(root, str(Path(ref['path']).with_name('response.bin'))).read_bytes()
    require(sha(raw) == receipt['sha256'] and len(raw) == receipt['bytes'], 'Usage source bytes differ')
    require(receipt.get('http_status') is None or (type(receipt['http_status']) is int and 100 <= receipt['http_status'] <= 599),
            'Invalid usage HTTP status')
    return receipt


def _download(root):
    started = now(); status = None; headers = {}; raw = b''; failure = None
    try:
        try:
            response = urlopen(Request(inventory.audit.URL, headers={'User-Agent': 'PGO-Usage/1.0'}), timeout=20)
        except HTTPError as error:
            response = error
        with response:
            status = response.status; headers = dict(response.headers); raw = response.read()
    except (URLError, OSError, TimeoutError, HTTPException) as error:
        if isinstance(error, IncompleteRead): raw = error.partial
        failure = 'REQUEST_FAILED'
    receipt = dict(url=inventory.audit.URL, started_at=started, captured_at=now(), http_status=status,
                   headers=headers, bytes=len(raw), sha256=sha(raw), published_at=None, failure=failure)
    payload = canonical(receipt); folder = 'injury-usage/targets/' + sha(payload)
    _write(root, folder+'/response.bin', raw)
    ref = _write(root, folder+'/receipt.json', payload)
    return dict(ref, captured_at=receipt['captured_at'])


def _select(root, finals, selected, excluded):
    """Choose on identity and durable clocks before validating the chosen payload."""
    missing = {key: final for key, final in finals.items() if key not in selected and key not in excluded}
    candidates = {}
    if missing:
        for directory in ('runs', 'runs-v2'):
            for path in (root/directory).glob('*/manifest.json'):
                raw = _path(root, path.relative_to(root).as_posix()).read_bytes()
                manifest = json.loads(raw); durable = utc(manifest['created_at'])
                relevant = {key: row for key, row in missing.items() if durable < utc(row['kickoff'])-timedelta(minutes=60)}
                if not relevant: continue
                pointer = dict(path=path.parent.relative_to(root).as_posix(), manifest_sha256=sha(raw))
                state, _ = load_archive(root, pointer)
                snapshot = state.get('replacement_depth') or {}
                if 'inventory_version' not in snapshot: continue
                games = {game['game_id'] for game in snapshot.get('games', [])}
                for key in games & relevant.keys():
                    rank = (durable, pointer['path'])
                    if key not in candidates or rank > candidates[key][0]: candidates[key] = (rank, pointer)
    selected.update({key: value[1] for key, value in candidates.items()})


def refresh_shadow(state, previous, root, checked_at):
    """Optional season-writer operation; only immutable descriptive artifacts are written."""
    root = Path(root)
    old = copy.deepcopy((previous or {}).get('injury_usage') or {})
    result = dict(old, status='WAITING', blocked_reason=None, checked_at=checked_at,
                  forecast_adjustment=None, predictive_status='UNAVAILABLE', coverage_scope='Defenders only',
                  selected_games=copy.deepcopy(old.get('selected_games', {})), games=old.get('games', []),
                  metrics=old.get('metrics', dict(games=0, **dict.fromkeys(COUNTS, 0))),
                  excluded_games=copy.deepcopy(old.get('excluded_games', [])))
    try:
        pointer_raw = (root/'current.json').read_bytes()
        load_archive(root, json.loads(pointer_raw))
        finals = {row['game_id']: row for row in state['results']}
        require(len(finals) == len(state['results']), 'Duplicate usage final game')
        verify_finals(state, root, max((row['week'] for row in finals.values()), default=0))
        issued = {game['game_id'] for week in state.get('weeks', []) for game in week['games']}
        result['pending_games'] = len(issued - finals.keys())
        require(set(result['selected_games']) <= finals.keys(), 'Selected usage final disappeared')
        for ref in (old.get('source'), old.get('last_attempt')):
            if ref: _attempt(root, ref)
        old_report = _read(root, old['report']) if old.get('report') else None
        exclusions = old.get('excluded_games', [])
        excluded = {row['game_id'] for row in exclusions}
        require(len(excluded) == len(exclusions) and excluded <= finals.keys() and not excluded & result['selected_games'].keys()
                and all(row['reason'] == 'MISSING_PREGAME_INVENTORY' for row in exclusions), 'Invalid saved cohort exclusions')
        _select(root, finals, result['selected_games'], excluded)
        result['excluded_games'] = [dict(game_id=key, reason='MISSING_PREGAME_INVENTORY')
                                    for key in sorted(finals.keys() - result['selected_games'].keys())]
        loaded = {}; cohorts = {}
        for key, pointer in sorted(result['selected_games'].items()):
            cache_key = canonical(pointer)
            if cache_key not in loaded: loaded[cache_key] = inventory.load_inventory(root, pointer)
            snapshot, roster = loaded[cache_key]
            require(snapshot.get('inventory_version') in (1, 2), 'Missing selected inventory version')
            games = [game for game in snapshot['games'] if game['game_id'] == key]
            require(len(games) == 1 and utc(snapshot['completed_at']) < utc(finals[key]['kickoff'])-timedelta(minutes=60),
                    'Selected inventory is missing or late')
            require(all(games[0][name] == finals[key][field] for name, field in
                        (('home', 'home_team'), ('away', 'away_team'), ('kickoff', 'kickoff'))), 'Selected game identity differs')
            cohorts[key] = (dict(snapshot, games=games), roster)
        if not cohorts:
            require((root/'current.json').read_bytes() == pointer_raw, 'Season pointer changed')
            return result
        attempt = _attempt(root, old['last_attempt']) if old.get('last_attempt') else None
        due = attempt is None or utc(checked_at)-utc(attempt['captured_at']) >= timedelta(hours=24) or any(
            utc(finals[key]['finalized_at']) > utc(attempt['captured_at']) for key in cohorts)
        if due:
            result['last_attempt'] = _download(root)
            attempt = _attempt(root, result['last_attempt'])
            require(attempt['http_status'] == 200 and attempt.get('failure') is None, 'Usage target request unavailable')
            snaps, receipt = inventory.load_target(_path(root, result['last_attempt']['path']).parent)
            result['source'] = result['last_attempt']
        else:
            require(attempt['http_status'] == 200 and attempt.get('failure') is None and old.get('source') == old.get('last_attempt'),
                    'Usage target request unavailable')
            snaps, receipt = inventory.load_target(_path(root, old['source']['path']).parent)
        verified_finals = [finals[key] for key in sorted(cohorts)]
        if old_report and all(old_report.get(key) == value for key, value in
                              (('selected_games', result['selected_games']), ('source', result['source']), ('verified_finals', verified_finals))):
            result.update(games=old_report['games'], metrics=old_report['metrics'])
        else:
            reports = []; rows = []; unique = set(); invalid_targets = {}
            for key, (snapshot, roster) in cohorts.items():
                report = inventory.link(snapshot, roster, snaps, [finals[key]], receipt['captured_at'])
                require(not report['unavailable_inventory_games'], 'Selected team inventory is missing')
                for row in report['rows']:
                    identity = (row['game_id'], row['team'], row['gsis_id'])
                    require(identity not in unique, 'Duplicate usage observation'); unique.add(identity)
                rows += report['rows']
                for excluded in report['excluded_target_rows']:
                    if excluded['source'].get('game_id') == key: invalid_targets[excluded['source_row']] = excluded
                reports.append(dict(game_id=key, inventory_version=snapshot['inventory_version'],
                                    **{name: report[name] for name in COUNTS}, exclusions=report['exclusions']))
            metrics = dict(games=len(reports), **{key: sum(game[key] for game in reports) for key in COUNTS})
            metrics['coverage'] = metrics['joined']/metrics['eligible_final_rows'] if metrics['eligible_final_rows'] else None
            metrics['exclusions'] = dict(Counter(reason for row in rows for reason in row['exclusions']))
            metrics['invalid_target_rows'] = len(invalid_targets)
            metrics['unresolved_target_identities'] = sum('UNRESOLVED_STABLE_IDENTITY' in row['exclusions'] for row in invalid_targets.values())
            pinned = [PROTOCOL, Path(__file__), Path(inventory.__file__), Path(inventory.audit.__file__),
                      Path(inventory.capture.__file__), inventory.HERE/'charter.md']
            if any(snapshot['inventory_version'] == 2 for snapshot, _ in cohorts.values()):
                pinned.append(inventory.HERE/'inventory-v2-addendum.md')
            payload = canonical(dict(selected_games=result['selected_games'], source=result['source'], verified_finals=verified_finals,
                                     games=reports, metrics=metrics, rows=rows, excluded_target_rows=list(invalid_targets.values()),
                                     inputs={path.relative_to(PROTOCOL.parents[2]).as_posix(): sha(path.read_bytes())
                                             for path in pinned},
                                     forecast_adjustment=None, predictive_status='UNAVAILABLE'))
            result.update(games=reports, metrics=metrics, report=_write(root, 'injury-usage/reports/'+sha(payload)+'.json', payload))
        require((root/'current.json').read_bytes() == pointer_raw, 'Season pointer changed')
        result['status'] = 'READY'
    except (ValueError, KeyError, TypeError, OSError, ImportError, OverflowError):
        result.update(status='BLOCKED', blocked_reason='Defender usage observation needs review; saved evidence is retained.')
    return result
