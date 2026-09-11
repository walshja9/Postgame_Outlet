"""Descriptive common-game market comparison over a source-verified season state.

The caller (normally pgo_season.load_current) verifies archived source bytes.
This module checks identity, saved arithmetic and timing, never changes picks,
and recomputes outcomes instead of trusting displayed grades. No result is
labelled prospective: this protocol has no verified prior public witness.
"""
from collections import Counter
import copy
import math

import pgo_ats
from pgo_season import identity, require, utc
from pgo_season_accuracy import _index


BANDS = (('zero', 'No difference (no edge)'), ('under_1', 'Under 1 point'),
         ('1_to_under_3', '1 to under 3 points'), ('3_or_more', '3 or more points'))
REASONS = {
    'pending': 'No verified final result yet',
    'missing_quote': 'No saved sportsbook comparison',
    'invalid_quote': 'Saved quote arithmetic or timing did not qualify',
    'forecast_identity': 'Forecast, quote and schedule identities differ',
    'event_identity': 'Saved provider event identities differ',
    'main_forecast_changed': 'Saved comparison does not match the current weekly forecast',
    'invalid_forecast': 'Main forecast arithmetic or timing did not qualify',
    'invalid_final': 'Final result identity, scores or timing did not qualify',
}


def _evaluate(game, schedule, row, result, checked, ats_checked, event):
    """One eligibility path for both the paired benchmark and ATS bands."""
    if row is None:
        return None, 'missing_quote'
    try:
        if not identity(game, schedule) or not identity(row, schedule):
            return None, 'forecast_identity'
    except (KeyError, TypeError, ValueError):
        return None, 'forecast_identity'
    event_id = str(schedule.get('espn_id') or '')
    if (not event_id or str(row.get('event_id') or '') != event_id
            or game.get('espn_id') and str(game['espn_id']) != event_id
            or event and str(event.get('event_id') or '') != event_id):
        return None, 'event_identity'
    try:
        pgo_ats._validate(row)
        require(utc(row['issued_at']) <= ats_checked <= checked, 'Future ATS observation')
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, 'invalid_quote'
    try:
        basis = pgo_ats._basis(game, checked)
        require(basis['model_line_eligible'], 'Main forecast is not eligible')
        require('pick' not in game or game['pick'] == basis['su_pick'], 'Main saved pick differs')
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, 'invalid_forecast'
    if any(row.get(key) != basis.get(key) for key in pgo_ats.BASIS):
        return None, 'main_forecast_changed'
    graded = copy.deepcopy(row)
    try:
        if result is not None:
            pgo_ats._final(result, row, checked)
        pgo_ats._grade(graded, result)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, 'invalid_final'
    gap = abs(row['home_edge'])
    band = 'zero' if gap == 0 else 'under_1' if gap < 1 else '1_to_under_3' if gap < 3 else '3_or_more'
    out = dict(game_id=game['game_id'], week=game['week'], kickoff=game['kickoff'],
               pgo_margin=row['pgo_margin'], sportsbook_margin=-row['home_handicap'],
               absolute_gap=gap, band=band, ats_grade=graded['grade']['ats'],
               source_edition=row['source_edition'], quote_captured_at=row['quote_captured_at'],
               pgo_issued_at=row['pgo_issued_at'], comparison_issued_at=row['issued_at'])
    if result is None:
        return out, 'pending'
    actual = result['home_score'] - result['away_score']
    out.update(actual_margin=actual, pgo_margin_error=abs(row['pgo_margin']-actual),
               sportsbook_margin_error=abs(-row['home_handicap']-actual))
    for key, margin in (('pgo_record', row['pgo_margin']), ('sportsbook_record', -row['home_handicap'])):
        out[key] = ('no_pick' if margin == 0 else 'ties' if actual == 0 else
                    'wins' if (margin > 0) == (actual > 0) else 'losses')
    return out, None


def summarize(state):
    """Return JSON-safe descriptive metrics without modifying the saved state.

    `benchmark` uses exactly the same finalized game IDs for both MAEs and both
    winner records. Difference = PGO MAE - sportsbook MAE. Pick'em/no-pick is
    separate from a selected side's actual tied game. Empty MAEs are None.
    `ats_bands` includes validated pending rows and no-edge rows; `ats` includes
    unavailable rows. `benchmark.reasons` partitions all excluded forecast rows.
    Structural duplicate/unknown IDs raise ValueError; row exclusions are coded.
    """
    checked = utc(state['checked_at'])
    games = _index([g for week in state.get('weeks', []) for g in week['games']], 'forecast')
    schedule = _index(state.get('schedule', []), 'schedule')
    results = _index(state.get('results', []), 'final')
    ats = state.get('ats') or {}
    quotes = _index(ats.get('games', []), 'quote')
    missing = _index(ats.get('unavailable', []), 'unavailable quote')
    require(games.keys() <= schedule.keys() and results.keys() <= schedule.keys(), 'Unknown scheduled game ID')
    require(not quotes.keys() & missing.keys() and (quotes.keys() | missing.keys()) <= games.keys(),
            'Unknown or duplicate saved comparison game ID')
    event_ids = [str(game['espn_id']) for game in schedule.values() if game.get('espn_id')]
    require(len(event_ids) == len(set(event_ids)), 'Duplicate scheduled provider event ID')
    ats_checked = utc(ats['checked_at']) if ats.get('checked_at') else checked
    require(ats_checked <= checked, 'ATS observation follows state check')
    reasons = Counter(); rows = []; finals = []
    counts = dict(wins=0, losses=0, pushes=0, pending=0, no_edge=0, unavailable=0)
    bands = [dict(key=key, label=label, n=0, game_ids=[], wins=0, losses=0, pushes=0, pending=0, no_edge=0)
             for key, label in BANDS]
    by_band = {band['key']: band for band in bands}
    for key, game in sorted(games.items()):
        row, reason = _evaluate(game, schedule[key], quotes.get(key), results.get(key), checked,
                                ats_checked, state.get('events', {}).get(key))
        if reason:
            reasons[reason] += 1
        if row is None:
            counts['unavailable'] += 1
            rows.append(dict(game_id=key, reason=reason, ats_grade='UNAVAILABLE'))
            continue
        band = by_band[row['band']]
        field = {'W': 'wins', 'L': 'losses', 'PUSH': 'pushes', 'PENDING': 'pending', 'NOPICK': 'no_edge'}[row['ats_grade']]
        counts[field] += 1; band[field] += 1; band['n'] += 1; band['game_ids'].append(key)
        rows.append(dict(row, reason=reason))
        if reason is None:
            finals.append(row)
    n = len(finals)
    pgo_mae = math.fsum(row['pgo_margin_error'] for row in finals)/n if n else None
    book_mae = math.fsum(row['sportsbook_margin_error'] for row in finals)/n if n else None
    benchmark = dict(n=n, game_ids=[row['game_id'] for row in finals], excluded=len(games)-n,
                     reasons=dict(sorted(reasons.items())), pgo_margin_mae=pgo_mae,
                     sportsbook_margin_mae=book_mae, difference=pgo_mae-book_mae if n else None)
    for key in ('pgo_record', 'sportsbook_record'):
        benchmark[key] = {outcome: sum(row[key] == outcome for row in finals)
                          for outcome in ('wins', 'losses', 'ties', 'no_pick')}
    return dict(schema_version=1, checked_at=state['checked_at'], games_total=len(games),
                benchmark=benchmark, ats=counts, ats_bands=bands, rows=rows,
                reason_labels=REASONS.copy(), prospective_status='UNAVAILABLE',
                guidance=['Descriptive saved-line results; small samples do not establish an advantage.',
                          'Both margin errors and winner records use the same eligible final games.',
                          'Signed difference is PGO error minus sportsbook error; lower error is better.',
                          'Zero disagreement means no ATS suggestion. Pushes are separate from wins and losses.',
                          'Fixed gap bands are monitoring categories, not a validated selection threshold.',
                          'No prior public protocol witness is verified; all observations remain descriptive.'])
