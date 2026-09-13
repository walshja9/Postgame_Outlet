"""Pure absence-burden arithmetic; KNOWN never implies source admission."""
from datetime import datetime, timezone
import math
import re
from statistics import median


POSITIONS = {
    'offense': frozenset(('RB', 'FB', 'WR', 'TE', 'OL', 'C', 'G', 'OG', 'LG', 'RG',
                          'T', 'OT', 'LT', 'RT')),
    'defense': frozenset(('DL', 'DE', 'DT', 'NT', 'EDGE', 'LB', 'ILB', 'OLB', 'MLB',
                          'DB', 'CB', 'S', 'FS', 'SS')),
}
EXCLUDED = frozenset(('QB', 'K', 'P', 'LS'))
STATUSES = frozenset(('OUT', 'INACTIVE', 'RES', 'INA', 'DEV', 'EXE', 'ACT',
                      'QUESTIONABLE', 'DOUBTFUL', 'DNP', 'AVAILABLE', 'UNREPORTED', 'UNKNOWN'))


def _unit(value):
    if not isinstance(value, str) or value not in POSITIONS:
        raise ValueError('Unit must be normalized offense or defense')
    return value


def _identity(value):
    return isinstance(value, str) and re.fullmatch(r'\d{2}-\d{7}', value, flags=re.ASCII) is not None


def _clock(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Clock must be timezone-aware')
    return value.astimezone(timezone.utc)


def _number(value, *, fraction=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Value must be finite nonnegative numerical data, not a boolean')
    if fraction and value > 1:
        raise ValueError('Prior unit fraction must be between zero and one')
    return float(value)


def prior_share(rows, *, player_id, unit, season, lock_at):
    """Select prior games first, then validate their observed values and clocks.

    Relevant player/unit/season records require normalized REG, PRE or POST game
    types before non-REG exclusion; malformed labels cannot cause older fallback.
    """
    unit, cutoff = _unit(unit), _clock(lock_at)
    if not _identity(player_id) or type(season) is not int or season < 1:
        raise ValueError('Canonical GSIS identity and integer season are required')
    eligible, seen = [], set()
    for row in rows:
        if row.get('gsis_id') != player_id:
            continue
        if _unit(row.get('unit')) != unit:
            continue
        if type(row.get('season')) is not int:
            raise ValueError('Historical season must be normalized integer data')
        if row['season'] not in (season - 1, season):
            continue
        game_type = row.get('game_type')
        if not isinstance(game_type, str) or game_type not in ('REG', 'PRE', 'POST'):
            raise ValueError('Historical game type must be normalized REG, PRE or POST')
        if game_type != 'REG':
            continue
        kickoff = _clock(row.get('kickoff'))
        if kickoff >= cutoff:
            continue
        game_id = row.get('game_id')
        if not isinstance(game_id, str) or not game_id or game_id.strip() != game_id:
            raise ValueError('Normalized prior game identity is required')
        if game_id in seen:
            raise ValueError('Duplicate eligible player/game observation')
        seen.add(game_id)
        eligible.append((kickoff, game_id, row))
    selected = sorted(eligible, key=lambda item: item[:2])[-4:]
    shares = []
    for kickoff, _, row in selected:
        final = _clock(row.get('final_observed_at'))
        captured = _clock(row.get('source_captured_at'))
        if not kickoff < final <= captured < cutoff:
            raise ValueError('Selected prior observation does not precede the decision deadline')
        shares.append(_number(row.get('share'), fraction=True))
    return dict(share=median(shares) if shares else None, count=len(shares),
                game_ids=[item[1] for item in selected], status='KNOWN' if shares else 'UNKNOWN')


def unit_burden(players, *, unit, report_complete):
    """Keep unknown membership/usage separate from the calculable subtotal.

    Every row needs an exact normalized STATUSES label. UNREPORTED and UNKNOWN
    explicitly mean no confirmed designation; neither establishes report coverage
    or health. Missing, misspelled and unrecognized labels are invalid inputs.
    """
    unit = _unit(unit)
    if type(report_complete) is not bool:
        raise ValueError('Report completeness must be an explicit boolean')
    missing = [] if report_complete else [dict(gsis_id=None, reason='REPORT_INCOMPLETE')]
    shares, seen, qualifying = [], set(), 0
    for row in players:
        status = row.get('status')
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError('Player status must be an explicit normalized STATUSES label')
        position = row.get('position')
        if position in EXCLUDED:
            continue
        assigned = next((name for name, positions in POSITIONS.items() if position in positions), None)
        if assigned is not None and assigned != unit:
            continue
        player_id = row.get('gsis_id')
        identified = _identity(player_id)
        if identified:
            if player_id in seen:
                raise ValueError('Duplicate eligible player identity')
            seen.add(player_id)
        if status not in ('OUT', 'INACTIVE'):
            continue
        documented = row.get('injury_documented')
        if documented is not None and type(documented) is not bool:
            raise ValueError('Injury documentation must be true, false or unknown')
        if documented is False:
            continue
        reasons = []
        if documented is None:
            reasons.append('INJURY_REASON_UNKNOWN')
        else:
            qualifying += int(assigned is not None)
        if assigned is None:
            reasons.append('UNIT_UNKNOWN')
        if not identified:
            reasons.append('IDENTITY_UNKNOWN')
        if documented is True and assigned is not None:
            share = row.get('prior_usage')
            if share is None:
                reasons.append('PRIOR_USAGE_UNKNOWN')
            else:
                share = _number(share, fraction=True)
                if not reasons:
                    shares.append(share)
        missing.extend(dict(gsis_id=player_id, reason=reason) for reason in reasons)
    subtotal = math.fsum(shares)
    return dict(total=None if missing else subtotal, known_subtotal=subtotal,
                qualifying_count=qualifying, missing=missing, status='UNKNOWN' if missing else 'KNOWN')


def margin_inputs(home, away):
    """Return away-minus-home burdens; absent totals never become zero."""
    totals = [side.get(unit) for unit in ('offense', 'defense') for side in (home, away)]
    values = [None if value is None else _number(value) for value in totals]
    if any(value is None for value in values):
        return None
    return dict(x_off=values[1] - values[0], x_def=values[3] - values[2])
