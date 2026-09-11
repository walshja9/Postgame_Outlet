"""Pure accuracy summaries over original saved forecasts and verified final results.

The caller owns source/hash verification (normally pgo_season.load_current).
summarize never fetches, revises forecasts, fits probabilities, or trusts displayed
grades. Optional accuracy_models contain name, edition, issued_at and saved games.
Every denominator is metric-specific; excluded means rows in that model's saved
schedule which did not qualify, including games without verified final results.
"""
from collections import Counter
import copy
from datetime import datetime, timedelta, timezone
import math


METRICS = ('record', 'margin_mae', 'total_mae', 'probabilities', 'confidence', 'reliability')
SIDES = ('home', 'away', 'tie')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _utc(value):
    try:
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError('Invalid accuracy timestamp') from exc
    _require(value.tzinfo is not None, 'Accuracy timestamp must have a timezone')
    return value.astimezone(timezone.utc)


def _number(value, label):
    _require(type(value) in (int, float) and math.isfinite(value), f'Invalid {label}')
    return value


def _index(rows, label):
    out = {}
    for row in rows:
        key = row.get('game_id')
        _require(isinstance(key, str) and key and key not in out, f'Duplicate or missing {label} game ID')
        out[key] = row
    return out


def _evaluate(game, result, issued_at, checked_at):
    kickoff = _utc(game['kickoff']); cutoff = kickoff-timedelta(minutes=60)
    if game.get('lock_at') is not None:
        _require(_utc(game['lock_at']) == cutoff, 'Saved lock differs from T-60')
    issued = game.get('issued_at', issued_at)
    issued = _utc(issued) if issued is not None else None
    if issued is not None:
        _require(issued <= checked_at, 'Forecast timestamp follows summary check')
    margin, total = game.get('margin'), game.get('total')
    if margin is not None:
        _number(margin, 'forecast margin')
    if total is not None:
        _require(_number(total, 'forecast total') >= 0, 'Negative forecast total')
    selected = game['home'] if margin is not None and margin > 0 else game['away'] if margin is not None and margin < 0 else None
    if 'pick' in game:
        expected = None if game.get('blocked_reason') else selected
        _require(game['pick'] == expected, 'Saved pick differs from forecast margin')
    confidence = game.get('confidence') or {}
    flag = confidence.get('added_after_lock')
    _require(flag is None or type(flag) is bool, 'Invalid confidence timing flag')
    probability = confidence.get('probabilities')
    full = isinstance(probability, dict) and all(key in probability for key in SIDES)
    if isinstance(probability, dict):
        for key in SIDES:
            if key in probability:
                _require(0 <= _number(probability[key], 'probability') <= 1, 'Probability out of range')
    if full:
        _require(abs(math.fsum(probability[key] for key in SIDES)-1) <= 1e-12,
                 'Full probabilities do not sum to one')
    win_probability = confidence.get('win_probability')
    if win_probability is not None:
        _require(0 <= _number(win_probability, 'selected win probability') <= 1, 'Selected probability out of range')
        if full and selected is not None:
            side = 'home' if selected == game['home'] else 'away'
            _require(abs(win_probability-probability[side]) <= 1e-12, 'Selected probability differs from full probabilities')
    points = confidence.get('points')
    if points is not None:
        _require(type(points) is int and points > 0, 'Confidence points must be a positive integer')
    if confidence.get('expected_points') is not None:
        expected = _number(confidence['expected_points'], 'expected confidence points')
        if points is not None and win_probability is not None:
            _require(abs(expected-points*win_probability) <= 1e-10, 'Expected confidence points differ')
    actual = side = None
    if result is not None:
        _require(result.get('home_team') == game['home'] and result.get('away_team') == game['away']
                 and _utc(result.get('kickoff')) == kickoff, 'Result game identity differs')
        _require(all(result.get(key) == game.get(key) for key in ('season', 'week', 'game_type')),
                 'Result season/week/type differs')
        _require(all(type(result.get(key)) is int and result[key] >= 0 for key in ('home_score', 'away_score')),
                 'Final scores must be nonnegative integers')
        _require(kickoff < _utc(result.get('finalized_at')) <= checked_at, 'Result final timestamp is invalid')
        actual = result['home_score']-result['away_score']
        if 'actual_margin' in result:
            _require(type(result['actual_margin']) in (int, float) and result['actual_margin'] == actual,
                     'Result margin differs from scores')
        side = 'home' if actual > 0 else 'away' if actual < 0 else 'tie'
    reason = ('no_verified_final' if result is None else
              'blocked_forecast' if game.get('blocked_reason') else
              'unknown_forecast_time' if issued is None else
              'late_forecast' if issued >= cutoff else None)
    values, reasons = {}, {}
    for metric in METRICS:
        why = reason
        if not why and metric in ('record', 'margin_mae') and margin is None:
            why = 'missing_margin'
        if not why and metric in ('record', 'confidence', 'reliability') and selected is None:
            why = 'no_pick'
        if not why and metric == 'total_mae' and total is None:
            why = 'missing_total'
        if not why and metric in ('probabilities', 'reliability'):
            why = ('late_confidence' if flag is True else 'unknown_confidence_time' if flag is None else
                   'incomplete_probabilities' if not full else None)
        if not why and metric == 'confidence' and (points is None or win_probability is None):
            why = 'missing_confidence'
        if why:
            reasons[metric] = why
            continue
        correct = side != 'tie' and selected == game[side]
        if metric == 'record':
            values[metric] = 'ties' if side == 'tie' else 'wins' if correct else 'losses'
        elif metric == 'margin_mae':
            values[metric] = abs(margin-actual)
        elif metric == 'total_mae':
            values[metric] = abs(total-result['home_score']-result['away_score'])
        elif metric == 'probabilities':
            # Same three-class sum Brier and 1e-15 log floor as pgo_confidence_picks.grade.
            values[metric] = (math.fsum((probability[key]-int(key == side))**2 for key in SIDES),
                              -math.log(max(1e-15, probability[side])))
        elif metric == 'confidence':
            values[metric] = (points if correct else 0, points*win_probability, points, flag is True, flag is None)
        else:
            values[metric] = (probability['home' if selected == game['home'] else 'away'], int(correct))
    return values, reasons


def _mean(values):
    return math.fsum(values)/len(values) if values else None


def _aggregate(metric, values):
    if metric in ('margin_mae', 'total_mae'):
        return dict(value=_mean(values))
    if metric == 'record':
        return {key: values.count(key) for key in ('wins', 'losses', 'ties')}
    if metric == 'probabilities':
        return dict(brier=_mean([v[0] for v in values]), log_loss=_mean([v[1] for v in values]))
    if metric == 'confidence':
        return dict(earned_points=sum(v[0] for v in values) if values else None,
                    expected_points=math.fsum(v[1] for v in values) if values else None,
                    available_points=sum(v[2] for v in values) if values else None,
                    late_count=sum(v[3] for v in values), unknown_timing_count=sum(v[4] for v in values))
    return {}


def _series(model, results, checked_at):
    games = _index(model['games'], 'forecast')
    evaluated = {key: _evaluate(game, results.get(key), model.get('issued_at'), checked_at)
                 for key, game in games.items()}
    summary = dict(name=model['name'], edition=model['edition'], games_total=len(games),
                   finalized_games=len(games.keys() & results.keys()))
    for metric in METRICS:
        keys = sorted(key for key, (values, _) in evaluated.items() if metric in values)
        reasons = Counter(why[metric] for _, why in evaluated.values() if metric in why)
        summary[metric] = dict(n=len(keys), excluded=len(games)-len(keys),
            reasons=dict(sorted(reasons.items())), game_ids=keys,
            **_aggregate(metric, [evaluated[key][0][metric] for key in keys]))
    bins = [[] for _ in range(10)]
    for key in summary['reliability']['game_ids']:
        value = evaluated[key][0]['reliability']; bins[min(9, int(value[0]*10))].append(value)
    summary['reliability_bins'] = [dict(lower=i/10, upper=(i+1)/10, count=len(values),
        mean_probability=_mean([v[0] for v in values]), observed_win_rate=_mean([v[1] for v in values]))
        for i, values in enumerate(bins)]
    return summary, evaluated


def _comparison(primary, model, left, right):
    comparison = dict(primary_edition=primary['edition'], model_edition=model['edition'], model_name=model['name'])
    union = left.keys() | right.keys()
    for metric in METRICS:
        keys = sorted(key for key in left.keys() & right.keys() if metric in left[key][0] and metric in right[key][0])
        a = _aggregate(metric, [left[key][0][metric] for key in keys])
        b = _aggregate(metric, [right[key][0][metric] for key in keys])
        item = dict(n=len(keys), excluded=len(union)-len(keys), game_ids=keys)
        if metric in ('margin_mae', 'total_mae'):
            item.update(primary=a['value'], model=b['value'],
                        difference=a['value']-b['value'] if keys else None)
        elif metric == 'probabilities':
            item.update({key: dict(primary=a[key], model=b[key], difference=a[key]-b[key] if keys else None)
                         for key in ('brier', 'log_loss')})
        else:
            item.update(primary=a, model=b)
        comparison[metric] = item
    return comparison


def summarize(state):
    """Return JSON-safe metrics without changing state or using its displayed grades.

    Probability accuracy requires all three originally saved probabilities and an
    explicit added_after_lock=False attestation. Confidence pool totals are a
    separate accounting measure and disclose late/unknown-timing counts. Empty
    metrics are None. Comparison differences are primary minus historical model;
    negative error/loss differences favor the primary on those exact common games.
    """
    checked = _utc(state['checked_at'])
    results = _index(state.get('results', []), 'result')
    primary = dict(name='PGO weekly model', edition='pgo-weekly-2026',
                   games=[game for week in state.get('weeks', []) for game in week['games']])
    models = [primary, *state.get('accuracy_models', [])]
    _require(len({model['edition'] for model in models}) == len(models), 'Duplicate accuracy model edition')
    summaries, evaluated = [], []
    for model in models:
        summary, rows = _series(model, results, checked); summaries.append(summary); evaluated.append(rows)
    return dict(schema_version=1, checked_at=state['checked_at'], primary=summaries[0], models=summaries,
                comparisons=[_comparison(summaries[0], summaries[i], evaluated[0], evaluated[i]) for i in range(1, len(models))],
                guidance=['Small samples do not establish accuracy or calibration; each metric shows its eligible games.',
                          'Reliability uses ten fixed selected-team probability bins; tied games count as no selected-team win.',
                          'Brier is the sum across home, away and tie outcomes (0 to 2); log loss uses a 1e-15 floor.',
                          'Confidence points are fixed pool accounting, not a probability accuracy score; late entries are disclosed.',
                          'Model comparisons use identical eligible game IDs for each metric. Lower error and loss are better.'])


def load_models():
    """Read the same verified immutable snapshots as the existing model record view.

    This optional I/O helper preserves saved issuance metadata and does not attach
    subsequently fitted probabilities to old predictions. Call summarize with a
    shallow state copy containing accuracy_models=load_models().
    """
    from pgo_season import legacy_models
    return copy.deepcopy(legacy_models())
