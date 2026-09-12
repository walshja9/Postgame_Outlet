"""Optional descriptive offensive usage collection; no fitting or forecast edits."""
from collections import Counter, defaultdict
import copy
import csv
from datetime import timedelta
import io
import json
from pathlib import Path
import re

import pgo_injury_usage_monitor as shared
import pgo_offensive_inventory as inventory
from pgo_season import canonical, require, sha, utc
from pgo_season_rollover import load_archive, verify_finals
from pgo_sources import normalize_team

PROTOCOL = Path(__file__).resolve().parent/'research/pgo_offensive_usage_20260912/charter.md'
COUNTS = ('cohort_rows', 'eligible_final_rows', 'joined', 'observed_zero', 'observed_positive', 'missing_target', 'pending')


def _read_report(root, ref):
    require(isinstance(ref, dict) and isinstance(ref.get('path'), str) and
            re.fullmatch(r'offensive-usage/reports/[0-9a-f]{64}\.json', ref['path']), 'Invalid offensive report reference')
    raw = shared._path(root, ref['path']).read_bytes()
    require(sha(raw) == ref['sha256'] and len(raw) == ref['bytes'], 'Offensive report bytes differ')
    value = json.loads(raw)
    require(isinstance(value, dict), 'Invalid offensive report')
    return value


def _select(root, finals, selected, excluded):
    missing = finals.keys()-selected.keys()-excluded
    candidates = {}
    if not missing: return
    for directory in ('runs', 'runs-v2'):
        for path in (root/directory).glob('*/manifest.json'):
            raw = shared._path(root, path.relative_to(root).as_posix()).read_bytes()
            manifest = json.loads(raw); durable = utc(manifest['created_at'])
            relevant = {key for key in missing if durable < utc(finals[key]['kickoff'])-timedelta(minutes=60)}
            if not relevant: continue
            pointer = dict(path=path.parent.relative_to(root).as_posix(), manifest_sha256=sha(raw))
            state, _ = load_archive(root, pointer)
            if 'offensive_inventory' not in state: continue
            # Presence fixes the candidate before validating even its version or shape.
            games = {game['game_id'] for week in state['weeks'] for game in week['games']}
            for key in games & relevant:
                rank = (durable, pointer['path'])
                if key not in candidates or rank > candidates[key][0]: candidates[key] = (rank, pointer)
    selected.update({key: value[1] for key, value in candidates.items()})


def link(snapshot, roster, snaps, final, target_captured_at):
    """Strict offense_snaps join; duplicate counting precedes value filtering."""
    require(len(snapshot['games']) == 1, 'Offensive usage requires one selected game')
    game = snapshot['games'][0]; lock = utc(game['lock_at'])
    require(lock == utc(game['kickoff'])-timedelta(minutes=60), 'Invalid offensive T-60')
    require(all(final[key] == game[field] for key, field in
                (('game_id', 'game_id'), ('season', 'season'), ('week', 'week'), ('game_type', 'game_type'),
                 ('home_team', 'home'), ('away_team', 'away'), ('kickoff', 'kickoff'))), 'Offensive final game differs')
    require(utc(final['kickoff']) < utc(final['finalized_at']) and
            all(type(final[key]) is int and final[key] >= 0 for key in ('home_score', 'away_score')) and
            final['actual_margin'] == final['home_score']-final['away_score'], 'Invalid offensive final observation')
    common = []
    if max(utc(snapshot['generated_at']), utc(snapshot['completed_at'])) >= lock: common.append('LATE_PREGAME_CAPTURE')
    if any(utc(ref[field]) >= lock for ref in snapshot['sources'] for field in ('captured_at', 'published_at') if ref.get(field)):
        common.append('LATE_FEATURE_SOURCE')
    if utc(target_captured_at) <= utc(final['finalized_at']): common.append('TARGET_BEFORE_FINAL_OBSERVATION')
    identities = defaultdict(set); names = defaultdict(set)
    for row in roster:
        if str(row.get('season')) == '2026' and row.get('pfr_id') and re.fullmatch(r'00-\d{7}', row.get('gsis_id', '')):
            identities[normalize_team(row.get('team', '')), row['pfr_id']].add(row['gsis_id'])
            names[normalize_team(row.get('team', '')), row['gsis_id']].update(inventory.source.evidence.aliases(row))
    counts = Counter(); targets = {}; invalid = []
    for number, row in enumerate(snaps, 2):
        if row.get('game_id') != game['game_id']: continue
        reasons = []; team = normalize_team(row.get('team', ''))
        if team not in (game['home'], game['away']) or normalize_team(row.get('opponent', '')) != (
                game['away'] if team == game['home'] else game['home']): reasons.append('EVENT_TEAM_OPPONENT_MISMATCH')
        if row.get('season') != str(game['season']) or row.get('week') != str(game['week']) or row.get('game_type') != 'REG':
            reasons.append('WRONG_SEASON_WEEK_OR_TYPE')
        ids = identities.get((team, row.get('pfr_player_id')), set())
        if len(ids) != 1: reasons.append('UNRESOLVED_STABLE_IDENTITY')
        identity = (team, next(iter(ids))) if len(ids) == 1 else None
        if not reasons: counts[identity] += 1
        if identity and row.get('player') and inventory.source.evidence.ch._normalize_player_name(row['player']) not in names[identity]:
            reasons.append('TARGET_PLAYER_NAME_MISMATCH')
        value = row.get('offense_snaps', '')
        if not isinstance(value, str) or not re.fullmatch(r'\d+', value): reasons.append('INVALID_OFFENSIVE_SNAP_COUNT')
        if reasons: invalid.append(dict(source_row=number, source=row, exclusions=reasons))
        else: targets[identity] = (int(value), number, row['pfr_player_id'])
    rows = []; known = set(); teams = set()
    for team in snapshot['teams']:
        require(team['team'] not in teams, 'Duplicate offensive inventory team'); teams.add(team['team'])
        if team['team'] not in (game['home'], game['away']): continue
        require(type(team.get('inventory_version')) is int and team['inventory_version'] == 1, 'Invalid offensive team version')
        for player in team['players']:
            pid = player['gsis_id']
            require(re.fullmatch(r'00-\d{7}', pid) and pid not in known, 'Duplicate offensive player identity'); known.add(pid)
            reasons = list(common)
            if not team.get('depth_snapshot_at'): reasons.append('UNKNOWN_DEPTH_CLOCK')
            elif utc(team['depth_snapshot_at']) >= lock: reasons.append('LATE_DEPTH_CLOCK')
            if any(utc(item[field]) >= lock for item in player['observations'] for field in ('captured_at', 'published_at') if item.get(field)):
                reasons.append('LATE_AVAILABILITY_SOURCE')
            identity = (team['team'], pid); match = targets.get(identity)
            if not match: reasons.append('NO_MATCHED_TARGET_ROW')
            if counts[identity] > 1: reasons.append('DUPLICATE_TARGET_IDENTITY')
            rows.append(dict(copy.deepcopy(player), game_id=game['game_id'], team=team['team'],
                             opponent=game['away'] if team['team'] == game['home'] else game['home'],
                             pregame_generated_at=snapshot['generated_at'], pregame_completed_at=snapshot['completed_at'],
                             depth_snapshot_at=team.get('depth_snapshot_at'), final_observed_at=final['finalized_at'],
                             target_captured_at=target_captured_at, offensive_snaps=match[0] if match and not reasons else None,
                             target_source_row=match[1] if match and counts[identity] == 1 else None,
                             target_pfr_id=match[2] if match and counts[identity] == 1 else None, exclusions=reasons))
    require({game['home'], game['away']} <= teams, 'Missing selected offensive team inventory')
    temporal = {'LATE_PREGAME_CAPTURE', 'LATE_FEATURE_SOURCE', 'TARGET_BEFORE_FINAL_OBSERVATION',
                'UNKNOWN_DEPTH_CLOCK', 'LATE_DEPTH_CLOCK', 'LATE_AVAILABILITY_SOURCE'}
    return dict(rows=rows, excluded_target_rows=invalid, cohort_rows=len(rows),
                eligible_final_rows=sum(not temporal.intersection(row['exclusions']) for row in rows),
                joined=sum(not row['exclusions'] for row in rows),
                observed_zero=sum(row['offensive_snaps'] == 0 for row in rows),
                observed_positive=sum(row['offensive_snaps'] is not None and row['offensive_snaps'] > 0 for row in rows),
                missing_target=sum('NO_MATCHED_TARGET_ROW' in row['exclusions'] for row in rows),
                pending=sum('TARGET_BEFORE_FINAL_OBSERVATION' in row['exclusions'] for row in rows))


def refresh_shadow(state, previous, root, checked_at):
    root = Path(root); old = copy.deepcopy((previous or {}).get('offensive_usage') or {})
    result = dict(old, status='WAITING', blocked_reason=None, checked_at=checked_at,
                  forecast_adjustment=None, predictive_status='UNAVAILABLE', coverage_scope='Offensive non-QB players',
                  selected_games=copy.deepcopy(old.get('selected_games', {})), games=old.get('games', []),
                  metrics=old.get('metrics', dict(games=0, **dict.fromkeys(COUNTS, 0))),
                  excluded_games=copy.deepcopy(old.get('excluded_games', [])))
    try:
        pointer_raw = (root/'current.json').read_bytes(); load_archive(root, json.loads(pointer_raw))
        finals = {row['game_id']: row for row in state['results']}
        require(len(finals) == len(state['results']), 'Duplicate offensive final')
        verify_finals(state, root, max((row['week'] for row in finals.values()), default=0))
        issued = {game['game_id'] for week in state.get('weeks', []) for game in week['games']}
        result['pending_games'] = len(issued-finals.keys())
        require(result['selected_games'].keys() <= finals.keys(), 'Selected offensive final disappeared')
        for ref in (old.get('source'), old.get('last_attempt')):
            if ref: shared._attempt(root, ref)
        if old.get('report'): _read_report(root, old['report'])
        exclusions = old.get('excluded_games', []); excluded = {row['game_id'] for row in exclusions}
        require(len(excluded) == len(exclusions) and excluded <= finals.keys() and
                not excluded & result['selected_games'].keys() and
                all(row['reason'] == 'MISSING_PREGAME_INVENTORY' for row in exclusions), 'Invalid saved offensive exclusions')
        _select(root, finals, result['selected_games'], excluded)
        result['excluded_games'] = [dict(game_id=key, reason='MISSING_PREGAME_INVENTORY')
                                    for key in sorted(finals.keys()-result['selected_games'].keys())]
        loaded = {}; cohorts = {}
        for key, pointer in sorted(result['selected_games'].items()):
            cache_key = canonical(pointer)
            if cache_key not in loaded: loaded[cache_key] = inventory.load_inventory(root, pointer)
            snapshot, roster = loaded[cache_key]
            games = [game for game in snapshot['games'] if game['game_id'] == key]
            require(len(games) == 1 and utc(snapshot['completed_at']) < utc(finals[key]['kickoff'])-timedelta(minutes=60),
                    'Selected offensive inventory is missing or late')
            cohorts[key] = (dict(snapshot, games=games), roster)
        if cohorts:
            # Both monitors consume the same raw snap feed; retain its original custody path.
            refs = [ref for ref in (old.get('last_attempt'), (state.get('injury_usage') or {}).get('last_attempt')) if ref]
            attempts = [(shared._attempt(root, ref), ref) for ref in refs]
            attempt, ref = max(attempts, key=lambda pair: utc(pair[0]['captured_at'])) if attempts else (None, None)
            due = attempt is None or utc(checked_at)-utc(attempt['captured_at']) >= timedelta(hours=24) or any(
                utc(finals[key]['finalized_at']) >= utc(attempt['captured_at']) for key in cohorts)
            if due: ref = shared._download(root); attempt = shared._attempt(root, ref)
            result['last_attempt'] = copy.deepcopy(ref)
            require(attempt['http_status'] == 200 and attempt.get('failure') is None, 'Offensive usage target unavailable')
            require(not attempt.get('published_at') or utc(attempt['published_at']) <= utc(attempt['captured_at']), 'Invalid offensive target publication clock')
            raw = shared._path(root, str(Path(ref['path']).with_name('response.bin'))).read_bytes()
            reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
            require({'game_id', 'season', 'week', 'game_type', 'team', 'opponent', 'pfr_player_id', 'offense_snaps'} <= set(reader.fieldnames or []),
                    'Offensive target CSV schema differs')
            require(len(reader.fieldnames) == len(set(reader.fieldnames)), 'Duplicate offensive target CSV column')
            snaps = list(reader)
            require(all(None not in row and all(value is not None for value in row.values()) for row in snaps),
                    'Malformed offensive target CSV row width')
            result['source'] = copy.deepcopy(ref)
            reports = []; rows = []; invalid = []
            for key, (snapshot, roster) in cohorts.items():
                report = link(snapshot, roster, snaps, finals[key], attempt['captured_at'])
                reports.append(dict(game_id=key, **{name: report[name] for name in COUNTS}))
                rows += report['rows']; invalid += report['excluded_target_rows']
            metrics = dict(games=len(reports), **{key: sum(report[key] for report in reports) for key in COUNTS})
            metrics.update(coverage=metrics['joined']/metrics['eligible_final_rows'] if metrics['eligible_final_rows'] else None,
                           exclusions=dict(Counter(reason for row in rows for reason in row['exclusions'])),
                           invalid_target_rows=len(invalid),
                           unresolved_target_identities=sum('UNRESOLVED_STABLE_IDENTITY' in row['exclusions'] for row in invalid))
            pinned = [PROTOCOL, Path(__file__), Path(inventory.__file__), Path(shared.__file__), Path(inventory.source.__file__)]
            payload = canonical(dict(selected_games=result['selected_games'], source=result['source'],
                                     verified_finals=[finals[key] for key in sorted(cohorts)], games=reports, metrics=metrics,
                                     rows=rows, excluded_target_rows=invalid,
                                     inputs={path.relative_to(PROTOCOL.parents[2]).as_posix(): sha(path.read_bytes()) for path in pinned},
                                     forecast_adjustment=None, predictive_status='UNAVAILABLE'))
            result.update(games=reports, metrics=metrics,
                          report=shared._write(root, 'offensive-usage/reports/'+sha(payload)+'.json', payload), status='READY')
        require((root/'current.json').read_bytes() == pointer_raw, 'Season pointer changed')
    except (ValueError, KeyError, TypeError, OSError, ImportError, OverflowError, AttributeError):
        result.update(status='BLOCKED', blocked_reason='Offensive usage observation needs review; saved evidence is retained.')
    return result
