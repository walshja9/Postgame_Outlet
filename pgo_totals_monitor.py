"""Immutable prospective comparisons of four fixed, unfitted scoring-total rules.

The season updater owns provider/hash verification. This module checks the saved
final identities and observation clocks, retains their witnesses, and never fetches.
"""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from pgo_sources import CURRENT_TEAMS

ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / 'docs/evidence/forecast-lab-2026/september-09-postseason/scoring-rates.json'
SEED_SHA256 = '24ca1d9a41a6e4f0c37b1e1b6328726220806108c8d6d41900cb9cace1fe7d00'
SEED_HREF = 'evidence/forecast-lab-2026/september-09-postseason/scoring-rates.json'
HISTORICAL_DIR = ROOT / 'research/pgo_totals_candidate_20260910/attempt01'
HISTORICAL_MANIFEST_SHA256 = '790fd10b4d3d8afa431c41737b5f8361387844c44d354b175459eba1cf9c0183'
METHODS = ('league_prior', 'pfpa_prior', 'shrink_4', 'shrink_8')
EASTERN = ZoneInfo('America/New_York')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _utc(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    _require(result.tzinfo is not None, 'Totals clock needs a timezone')
    return result.astimezone(timezone.utc)


def _number(value):
    _require(type(value) in (int, float) and math.isfinite(value), 'Totals value must be finite')
    return value


def _verified(path, digest, size=None):
    _require(path.is_file() and not path.is_symlink(), 'Totals source is missing or a symlink')
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == digest and (size is None or len(raw) == size),
             'Totals source hash or size differs: ' + path.name)
    return raw


def load_seed():
    seed = json.loads(_verified(SEED_PATH, SEED_SHA256))
    _require(set(seed['rates']) == set(CURRENT_TEAMS), 'Totals seed team inventory differs')
    return seed


def load_historical():
    _require(not HISTORICAL_DIR.is_symlink(), 'Totals historical directory is a symlink')
    manifest = json.loads(_verified(HISTORICAL_DIR / 'manifest.json', HISTORICAL_MANIFEST_SHA256))
    names = {'metrics.json', 'predictions.csv', 'public-summary.json', 'run-receipt.json', 'run-start.json'}
    _require(set(manifest['files']) == names, 'Totals historical inventory differs')
    files = {name: _verified(HISTORICAL_DIR / name, info['sha256'], info['bytes'])
             for name, info in manifest['files'].items()}
    summary = json.loads(files['public-summary.json'])
    return {key: summary[key] for key in ('games', 'metrics', 'further_study_screen', 'paired', 'limitations')}


def _index(rows):
    result = {}
    for row in rows:
        key = row.get('game_id')
        _require(isinstance(key, str) and key and key not in result, 'Duplicate or missing totals game ID')
        result[key] = row
    return result


def _identity(game, final=False):
    home, away = (game['home_team'], game['away_team']) if final else (game['home'], game['away'])
    _require(game['season'] == 2026 and game['game_type'] == 'REG'
             and type(game['week']) is int and 1 <= game['week'] <= 18
             and home in CURRENT_TEAMS and away in CURRENT_TEAMS and home != away,
             'Totals game identity differs')
    return game['season'], game['week'], game['game_type'], home, away, _utc(game['kickoff'])


def _finals(rows, checked):
    finals = _index(rows); seen = set()
    for result in finals.values():
        identity = _identity(result, True)
        _require(all(type(result.get(key)) is int and result[key] >= 0 for key in ('home_score', 'away_score')),
                 'Totals final scores must be nonnegative integers')
        if 'actual_margin' in result:
            _require(_number(result['actual_margin']) == result['home_score'] - result['away_score'],
                     'Totals final margin differs')
        _require(identity[-1] < _utc(result['finalized_at']) <= checked, 'Totals final observation is from the future or before kickoff')
        if result.get('source') is not None:
            captured = _utc(result['source']['captured_at'])
            _require(identity[-1] < captured <= checked, 'Totals source observation is from the future or before kickoff')
        for team in identity[3:5]:
            key = (result['week'], team)
            _require(key not in seen, 'Duplicate totals team/week identity')
            seen.add(key)
    return finals


def _metrics(games, finals):
    paired = []
    for game in games:
        _require(set(game['totals']) == set(METHODS) and all(_number(v) >= 0 for v in game['totals'].values()),
                 'Totals method inventory or prediction differs')
        result = finals.get(game['game_id'])
        if result is not None:
            _require(_identity(game) == _identity(result, True), 'Totals grading identity differs')
            paired.append((game, result['home_score'] + result['away_score']))
    metrics = dict(paired_games=len(paired), paired_weeks=len({g['week'] for g, _ in paired}),
                   game_ids=sorted(g['game_id'] for g, _ in paired), bias_definition='predicted_total_minus_actual_total')
    for method in METHODS:
        errors = [g['totals'][method] - actual for g, actual in paired]
        metrics[method] = dict(games=len(errors), mae=math.fsum(abs(v) for v in errors)/len(errors) if errors else None,
                              rmse=math.hypot(*errors)/math.sqrt(len(errors)) if errors else None,
                              bias=math.fsum(errors)/len(errors) if errors else None)
    return metrics


def _issue(game, finals, seed, checked_at):
    history = sorted((r for r in finals.values()
                      if {game['home'], game['away']} & {r['home_team'], r['away_team']}
                      and _utc(r['kickoff']).astimezone(EASTERN).date() < _utc(game['kickoff']).astimezone(EASTERN).date()),
                     key=lambda r: (_utc(r['kickoff']), r['game_id']))
    totals = dict(league_prior=_number(seed['league_mean_total']))
    for weight, method in ((0, 'pfpa_prior'), (4, 'shrink_4'), (8, 'shrink_8')):
        values = []
        for team in (game['home'], game['away']):
            prior = seed['rates'][team]
            played = [r for r in history if team in (r['home_team'], r['away_team'])]
            for field in ('pf', 'pa'):
                old = _number(prior[field]); _require(old >= 0, 'Negative totals prior rate')
                points = sum(r['home_score' if (r['home_team'] == team) == (field == 'pf') else 'away_score'] for r in played)
                values.append((weight*old + points)/(weight + len(played)) if weight else old)
        totals[method] = math.fsum(values)/2
    _require(all(_number(v) >= 0 for v in totals.values()), 'Invalid totals prediction')
    row = {k: game[k] for k in ('game_id', 'season', 'week', 'game_type', 'home', 'away', 'kickoff')}
    row.update(lock_at=(_utc(game['kickoff'])-timedelta(minutes=60)).isoformat(), issued_at=checked_at,
               totals=totals, seed_sha256=SEED_SHA256, seed_source_href=SEED_HREF,
               history_game_ids=[r['game_id'] for r in history], history_witnesses=copy.deepcopy(history))
    return row


def refresh_shadow(state, previous, checked_at):
    old = (previous or {}).get('totals_shadow') or {}
    payload = dict(status='READY', blocked_reason=None, generated_at=checked_at,
                   games=copy.deepcopy(old.get('games', [])), metrics=copy.deepcopy(old.get('metrics', _metrics([], {}))),
                   excluded=copy.deepcopy(old.get('excluded', [])), historical=copy.deepcopy(old.get('historical', {})),
                   historical_manifest_sha256=old.get('historical_manifest_sha256', HISTORICAL_MANIFEST_SHA256))
    try:
        checked = _utc(checked_at)
        _require(state['season'] == 2026, 'Totals monitor is fixed to the 2026 season')
        finals = _finals(state['results'], checked)
        for key, before in _index((previous or {}).get('results', [])).items():
            _require(key in finals and _identity(before, True) == _identity(finals[key], True)
                     and all(before[k] == finals[key][k] for k in ('home_score', 'away_score', 'finalized_at')),
                     'Accepted totals final changed or disappeared')
        issued = _index(payload['games'])
        payload['metrics'] = _metrics(payload['games'], finals)
        _require(all(g['seed_sha256'] == SEED_SHA256 for g in payload['games']), 'Totals seed changed after issuance')
        _require(payload['historical_manifest_sha256'] == HISTORICAL_MANIFEST_SHA256,
                 'Totals historical package changed after issuance')
        payload['historical'] = load_historical()
        seed = load_seed()
        _require(state['status'] == 'READY', 'Main season state is not READY: ' + str(state.get('blocked_reason')))
        games = _index([g for w in state['weeks'] for g in w['games']])
        excluded = {r['game_id']: r for r in payload['excluded']}; additions = []; seen = set()
        for key, game in games.items():
            _identity(game)
            for team in (game['home'], game['away']):
                _require((game['week'], team) not in seen, 'Duplicate totals forecast team/week identity')
                seen.add((game['week'], team))
            if key in issued:
                _require(_identity(game) == _identity(issued[key]), 'Issued totals game identity changed')
                continue
            cutoff = _utc(game['kickoff'])-timedelta(minutes=60)
            _require(_utc(game['lock_at']) == cutoff, 'Totals lock differs from T-60')
            if checked >= cutoff or key in finals or game.get('forecast_status') in ('LOCKED', 'FINAL'):
                excluded[key] = dict(game_id=key, reason='Not issued before the real T-60 lock')
            elif game.get('blocked_reason') or game.get('forecast_status') == 'BLOCKED' or game.get('margin') is None:
                excluded[key] = dict(game_id=key, reason='Primary forecast is unavailable')
            else:
                _number(game['margin'])
                additions.append(_issue(game, finals, seed, checked_at)); excluded.pop(key, None)
        payload['games'].extend(additions)
        payload['excluded'] = list(excluded.values())
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
        payload.update(status='BLOCKED', blocked_reason=str(error))
    return payload


def check_durable_shadow(state, previous, durable_at):
    old = (previous or {}).get('totals_shadow', {}).get('games', [])
    current = state.get('totals_shadow', {}).get('games', [])
    before, after = _index(old), _index(current)
    _require(set(before) <= set(after), 'An immutable totals row was removed')
    for key, game in after.items():
        if key in before:
            _require(game == before[key], 'An immutable totals row changed')
            continue
        _identity(game)
        cutoff = _utc(game['kickoff'])-timedelta(minutes=60); issued = _utc(game['issued_at'])
        _require(issued <= _utc(durable_at) < cutoff and _utc(game['lock_at']) == cutoff,
                 'Totals durable-write lock crossed')
        _require(game['seed_sha256'] == SEED_SHA256, 'Totals seed pin differs')
        witnesses = _finals(game['history_witnesses'], issued)
        _require(game['history_game_ids'] == list(witnesses), 'Totals history witnesses differ')
        for result in witnesses.values():
            _require({game['home'], game['away']} & {result['home_team'], result['away_team']}
                     and _utc(result['kickoff']).astimezone(EASTERN).date() < _utc(game['kickoff']).astimezone(EASTERN).date(),
                     'Totals history is not from a prior game day')
        _metrics([game], {})
