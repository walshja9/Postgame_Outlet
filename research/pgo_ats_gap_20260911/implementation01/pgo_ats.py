"""Saved DraftKings spreads and separate PGO projection checks; no probability model.

Only archived ESPN responses are read. A capture is our observation time, not a
book publication time, and ESPN's `close` field does not prove a closing line.
Call with a source-verified season state; the season writer owns final provenance.
"""
import copy
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

import pgo_sources
from pgo_season import IDENTITY, archive_href, identity, parse_scoreboard, require, utc

PROVIDER = {'id': '100', 'name': 'DraftKings'}
MAX_CAPTURE_AGE = timedelta(minutes=60)
MUTABLE = {'status', 'stale_reason', 'stale_since', 'grade', 'result'}
BASIS = (*IDENTITY, 'lock_at', 'source_edition', 'pgo_issued_at', 'inputs_as_of',
         'pgo_margin', 'model_home_handicap', 'su_pick', 'model_line_eligible')


def _number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'Missing or nonfinite numeric value')
    return float(value)


def _index(rows):
    result = {g['game_id']: g for g in rows}
    require(len(result) == len(rows), 'Duplicate ATS game')
    return result


def _team(value):
    return pgo_sources.normalize_team({'WSH': 'WAS'}.get(value, value))


def _side(margin, game):
    return game['home'] if margin > 0 else game['away'] if margin < 0 else None


def _basis(game, checked):
    row = {key: game[key] for key in IDENTITY}
    cutoff = utc(game['kickoff']) - timedelta(minutes=60)
    require(utc(game['lock_at']) == cutoff, 'ATS lock is not T-60')
    margin = game.get('margin')
    if margin is not None:
        margin = _number(margin)
    issued = game.get('issued_at'); inputs = game.get('inputs_as_of')
    timely = bool(issued and inputs and game.get('source_edition') and margin is not None
                  and not game.get('blocked_reason')
                  and utc(inputs) <= utc(issued) <= checked and utc(issued) < cutoff)
    pick = _side(margin, game) if margin is not None else None
    require(not game.get('pick') or game['pick'] == pick, 'PGO chosen team and saved margin disagree')
    row.update(lock_at=game['lock_at'], source_edition=game.get('source_edition'),
               pgo_issued_at=issued, inputs_as_of=inputs, pgo_margin=margin,
               model_home_handicap=-margin if margin is not None else None,
               su_pick=pick, model_line_eligible=timely)
    return row


def _read(ref, root, checked):
    key = ref['path']; digest = ref['sha256']
    require(re.fullmatch(r'(?:sources|source-archive)/[0-9a-f]{64}\.json', key) is not None
            and Path(key).stem == digest, 'Invalid ATS captured source path')
    require(utc(ref['captured_at']) <= checked, 'ATS source captured in the future')
    path = Path(root) / key
    require(not Path(root).is_symlink() and not path.parent.is_symlink() and not path.is_symlink(), 'ATS source is a symlink')
    raw = path.read_bytes()
    require(type(ref['bytes']) is int and len(raw) == ref['bytes']
            and hashlib.sha256(raw).hexdigest() == digest, 'ATS source hash or length differs')
    url = urlsplit(ref['url']); query = parse_qs(url.query)
    require(url.scheme == 'https' and url.netloc == 'site.api.espn.com'
            and url.path == '/apis/site/v2/sports/football/nfl/scoreboard' and not url.fragment
            and query.get('dates') == ['2026'] and query.get('seasontype') == ['2']
            and len(query.get('week', [])) == 1, 'Invalid ATS scoreboard URL')
    payload = json.loads(raw)
    require(str(payload['week']['number']) == query['week'][0], 'ATS source URL week differs')
    return payload


def _line(value):
    if isinstance(value, str):
        require(re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value.strip()) is not None, 'Invalid sportsbook line')
        value = float(value)
    value = _number(value)
    require(abs(value) <= 100 and value * 2 == round(value * 2), 'Sportsbook line must use half-point increments')
    return value


def _quote(event, game):
    comp = event['competitions'][0]
    status = comp.get('status', event.get('status', {})).get('type', {})
    require(status.get('completed') is False and status.get('state') == 'pre'
            and status.get('name') == 'STATUS_SCHEDULED', 'Sportsbook event is not scheduled')
    require(not comp.get('date') or utc(comp['date']) == utc(game['kickoff']), 'Sportsbook competition kickoff differs')
    books = [b for b in comp.get('odds', []) if str(b.get('provider', {}).get('id')) == PROVIDER['id']]
    require(len(books) == 1, 'DraftKings spread is missing or ambiguous')
    book = books[0]
    require(book['provider'].get('name', '').casefold() in ('draftkings','draft kings'), 'Sportsbook provider name differs')
    home = _line(book['spread']); away = _line(book['pointSpread']['away']['close']['line'])
    require(_line(book['pointSpread']['home']['close']['line']) == home and away == -home,
            'Conflicting home and away sportsbook lines')
    details = str(book['details']).strip()
    if home == 0 and details.upper() in {'EVEN', 'PK', 'PICK', "PICK'EM"}:
        pass
    else:
        match = re.fullmatch(r'([A-Z]{2,3})\s+([+-]?\d+(?:\.\d+)?)', details)
        require(match is not None, 'Unsupported sportsbook details')
        team, value = _team(match[1]), _line(match[2])
        require(team in (game['home'], game['away']) and value == (home if team == game['home'] else away),
                'Sportsbook details disagree with signed home line')
    sides = {x['homeAway']: x for x in comp['competitors']}
    for side, line in (('home', home), ('away', away)):
        team = sides[side]['team']; witness = book[side + 'TeamOdds']
        require(str(witness['team']['id']) == str(team['id']) and _team(witness['team']['abbreviation']) == game[side],
                'Sportsbook team identity differs')
        for flag, expected in (('favorite', line < 0), ('underdog', line > 0)):
            require(flag not in witness or witness[flag] is expected, 'Sportsbook favorite flag conflicts')
    return home


def _sources(state, root, checked):
    """Select the latest captured scoreboard per week; never fall back after failure."""
    latest = {}; quotes = {}; errors = {}; fatal = []
    for ref in state.get('source_captures', []):
        if '/football/nfl/scoreboard?' not in ref.get('url', ''):
            continue
        try:
            week = int(parse_qs(urlsplit(ref['url']).query)['week'][0])
            old = latest.get(week)
            if old and utc(old['captured_at']) == utc(ref['captured_at']):
                require(old['sha256'] == ref['sha256'], 'Conflicting simultaneous scoreboard captures')
            if old is None or utc(ref['captured_at']) > utc(old['captured_at']):
                latest[week] = ref
        except (ValueError, KeyError, TypeError) as exc:
            fatal.append(str(exc))
    for week, ref in latest.items():
        try:
            payload = _read(ref, root, checked)
            parsed = parse_scoreboard(payload, state['schedule'], ref['captured_at'])
            require(checked - utc(ref['captured_at']) <= MAX_CAPTURE_AGE, 'Latest quote capture is older than 60 minutes')
            by_id = {str(e['id']): e for e in payload['events']}
            schedule = _index(state['schedule'])
            for key, metadata in parsed['events'].items():
                try:
                    line = _quote(by_id[metadata['event_id']], schedule[key])
                    quotes[key] = (line, copy.deepcopy(ref), metadata['event_id'])
                except (ValueError, KeyError, TypeError) as exc:
                    errors[key] = str(exc)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            reason = str(exc)
            errors.update({g['game_id']: reason for g in state['schedule'] if g['week'] == week})
            if reason != 'Latest quote capture is older than 60 minutes':
                fatal.append(reason)
    return quotes, errors, fatal


def _final(result, game, checked):
    require(all(result[k] == game[k] for k in ('game_id', 'season', 'week', 'game_type'))
            and result['home_team'] == game['home'] and result['away_team'] == game['away']
            and utc(result['kickoff']) == utc(game['kickoff']), 'ATS final identity differs')
    require(utc(game['kickoff']) < utc(result['finalized_at']) <= checked, 'ATS final timestamp differs')
    require(all(type(result[k]) is int and result[k] >= 0 for k in ('home_score', 'away_score')),
            'ATS final scores must be nonnegative integers')
    require(result['actual_margin'] == result['home_score'] - result['away_score'], 'ATS final margin differs')
    require(str(result['event_id']) == str(game.get('event_id') or game.get('espn_id')), 'ATS final event ID differs')
    return result


def _outcome(value):
    return 'W' if value > 0 else 'L' if value < 0 else 'PUSH'


def _grade(row, result):
    if row.get('result') is not None:
        require(result is not None and all(row['result'].get(k) == result.get(k) for k in
                ('game_id', 'home_score', 'away_score', 'actual_margin', 'event_id', 'finalized_at')),
                'Accepted ATS final changed or disappeared')
    grades = {}
    if not row['model_line_eligible']:
        grades['model_line'] = 'UNAVAILABLE'
    elif row['su_pick'] is None:
        grades['model_line'] = 'NOPICK'
    elif result is None:
        grades['model_line'] = 'PENDING'
    else:
        sign = 1 if row['su_pick'] == row['home'] else -1
        grades['model_line'] = _outcome(sign * (result['actual_margin'] - row['pgo_margin']))
    if 'home_handicap' in row:
        for kind, pick in (('straight_up_ats', row['su_pick']), ('ats', row['ats_pick'])):
            grades[kind] = ('NOPICK' if pick is None else 'PENDING' if result is None else
                            _outcome((1 if pick == row['home'] else -1) * (result['actual_margin'] + row['home_handicap'])))
    row.update(grade=grades, result=copy.deepcopy(result))


def _metrics(payload):
    metrics = {}
    for kind in ('straight_up_ats', 'ats', 'model_line'):
        counts = dict(wins=0, losses=0, pushes=0, pending=0, unavailable=0)
        no_pick = 'no_edge' if kind == 'ats' else 'no_pick'; counts[no_pick] = 0
        for row in payload['games'] + payload['unavailable']:
            grade = row.get('grade', {}).get(kind, 'UNAVAILABLE')
            counts[{'W': 'wins', 'L': 'losses', 'PUSH': 'pushes', 'PENDING': 'pending',
                    'UNAVAILABLE': 'unavailable', 'NOPICK': no_pick}[grade]] += 1
        metrics[kind] = counts
    return metrics


def _core(row):
    return {k: v for k, v in row.items() if k not in MUTABLE}


def _validate(row):
    cutoff = utc(row['kickoff']) - timedelta(minutes=60)
    margin = _number(row['pgo_margin']); line = _line(row['home_handicap'])
    require(row['model_line_eligible'] is True and row['model_home_handicap'] == -margin
            and row['away_handicap'] == -line and row['home_edge'] == margin + line
            and row['su_pick'] == _side(margin, row) and row['ats_pick'] == _side(margin + line, row)
            and row['no_edge'] is (margin + line == 0), 'ATS saved arithmetic differs')
    require(row['provider'] == PROVIDER and row['source']['captured_at'] == row['quote_captured_at'], 'ATS saved source differs')
    require(utc(row['inputs_as_of']) <= utc(row['pgo_issued_at']) <= utc(row['issued_at']) < cutoff
            and utc(row['quote_captured_at']) <= utc(row['issued_at'])
            and utc(row['issued_at']) - utc(row['quote_captured_at']) <= MAX_CAPTURE_AGE
            and utc(row['lock_at']) == cutoff and row['issued_at'] == row['updated_at'], 'ATS issuance clocks differ')


def refresh(state, previous, root, checked_at):
    """Return an ATS payload without mutating state, source files or prior versions."""
    old = (previous or {}).get('ats') or {}
    out = dict(status='READY', checked_at=checked_at, blocked_reason=None, provider=copy.deepcopy(PROVIDER),
               max_capture_age_minutes=60, quote_time_basis='Our ESPN response capture; provider publication time unavailable',
               games=copy.deepcopy(old.get('games', [])), unavailable=copy.deepcopy(old.get('unavailable', [])))
    try:
        checked = utc(checked_at)
        require(state['season'] == 2026, 'ATS season differs')
        require(not old.get('checked_at') or utc(old['checked_at']) <= checked, 'ATS refresh clock moved backwards')
        games = _index([g for w in state['weeks'] for g in w['games']]); schedule = _index(state['schedule'])
        before = _index(out['games']); missing = _index(out['unavailable']); finals = _index(state['results'])
        require(not set(before) & set(missing) and (set(before) | set(missing)) <= set(games), 'An archived ATS game disappeared')
        quotes, errors, fatal = _sources(state, root, checked)
        if fatal or state.get('status') != 'READY':
            out.update(status='BLOCKED', blocked_reason='; '.join(fatal) or 'Main season state is not READY')
        rows = []; unavailable = []; verified = set()
        for key, game in games.items():
            require(key in schedule and identity(game, schedule[key]), 'ATS forecast and schedule identity differ')
            basis = _basis(game, checked); previous_row = before.get(key) or missing.get(key)
            cutoff = utc(basis['lock_at'])
            if previous_row:
                require(identity(previous_row, basis), 'Archived ATS identity changed')
                if checked >= cutoff and key not in before:
                    require(all(previous_row.get(k) == basis.get(k) for k in BASIS), 'Locked PGO projection changed')
            if key in before:
                _validate(before[key])
                ref = before[key]['source']
                if ref['sha256'] not in verified:
                    _read(ref, root, checked); verified.add(ref['sha256'])
            reason = errors.get(key, 'No verified current DraftKings spread in the saved capture')
            row = copy.deepcopy(before.get(key))
            if row and any(row.get(k) != basis.get(k) for k in BASIS):
                reason = 'Main PGO forecast changed or was withheld; retaining the prior saved comparison. ' + reason
                row.update(stale_reason=reason, stale_since=row.get('stale_since') or checked_at)
            if checked >= cutoff:
                reason = 'No sportsbook comparison was issued before T-60'
                if row: row['status'] = 'LOCKED'
            elif out['status'] != 'READY' or not basis['model_line_eligible']:
                reason = out['blocked_reason'] or 'Original timely PGO prediction is unavailable'
                if row: row.update(status='STALE', stale_reason=reason, stale_since=row.get('stale_since') or checked_at)
            elif key in quotes and key not in finals:
                line, ref, event_id = quotes[key]
                if row and (utc(ref['captured_at']) < utc(row['quote_captured_at'])
                            or utc(basis['pgo_issued_at']) < utc(row['pgo_issued_at'])):
                    reason = 'Quote or PGO version moved backwards'
                    row.update(status='STALE', stale_reason=reason, stale_since=row.get('stale_since') or checked_at)
                else:
                    source = dict(ref, href=archive_href(ref['path']))
                    candidate = dict(basis, source=source, event_id=event_id, quote_captured_at=ref['captured_at'],
                                     provider=copy.deepcopy(PROVIDER), home_handicap=line, away_handicap=-line,
                                     home_edge=basis['pgo_margin'] + line, ats_pick=_side(basis['pgo_margin'] + line, basis),
                                     no_edge=basis['pgo_margin'] + line == 0, issued_at=checked_at, updated_at=checked_at,
                                     status='CURRENT', stale_reason=None, stale_since=None)
                    if row and all(row.get(k) == v for k, v in _core(candidate).items() if k not in {'issued_at', 'updated_at'}):
                        row.update(status='CURRENT', stale_reason=None, stale_since=None)
                    else:
                        row = candidate
                    _validate(row)
            elif row:
                row.update(status='STALE', stale_reason=reason, stale_since=row.get('stale_since') or checked_at)
            if row is None:
                row = dict(basis, reason=reason, event_id=str(schedule[key].get('espn_id') or state.get('events', {}).get(key, {}).get('event_id', '')))
                if previous_row: row['result'] = copy.deepcopy(previous_row.get('result'))
                unavailable.append(row)
            else:
                rows.append(row)
            result = finals.get(key)
            if result is not None: _final(result, row, checked)
            _grade(row, result)
        out.update(games=rows, unavailable=unavailable)
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
        out.update(status='BLOCKED', blocked_reason=str(exc))
    out['metrics'] = _metrics(out)
    return out


def check_durable(state, previous, durable):
    """New/revised book comparisons must actually finish saving before T-60."""
    current = state.get('ats') or {}; old = (previous or {}).get('ats') or {}
    before = _index(old.get('games', [])); after = _index(current.get('games', []))
    before_missing = _index(old.get('unavailable', [])); missing = _index(current.get('unavailable', []))
    require(set(before) <= set(after) and set(before_missing) <= (set(after) | set(missing)), 'An archived ATS row was removed')
    require(not set(after) & set(missing), 'Duplicate quoted and unavailable ATS game')
    games = _index([g for w in state.get('weeks', []) for g in w['games']]); clock = utc(durable)
    for key, row in {**missing, **after}.items():
        require(key in games and identity(row, games[key]), 'Durable ATS game identity differs')
        basis = _basis(games[key], clock)
        retained = key in before and _core(row) == _core(before[key])
        if not retained:
            require(all(row.get(k) == basis.get(k) for k in BASIS), 'Durable ATS PGO forecast differs')
        elif any(row.get(k) != basis.get(k) for k in BASIS):
            require(row['status'] in {'STALE', 'LOCKED'} and row.get('stale_reason'), 'Changed main forecast needs a retained-comparison warning')
        old_row = before.get(key) or before_missing.get(key)
        cutoff = utc(row['kickoff']) - timedelta(minutes=60)
        if old_row and clock >= cutoff:
            require(all(row.get(k) == old_row.get(k) for k in BASIS), 'Locked PGO comparison changed')
        if key in after:
            _validate(row)
            changed = key not in before or _core(row) != _core(before[key])
            if changed:
                require(state.get('status') == 'READY' and utc(row['issued_at']) <= clock < cutoff,
                        'ATS durable-write lock crossed or main state is blocked')
                if key in before:
                    require(utc(row['quote_captured_at']) >= utc(before[key]['quote_captured_at'])
                            and utc(row['issued_at']) >= utc(before[key]['issued_at'])
                            and utc(row['pgo_issued_at']) >= utc(before[key]['pgo_issued_at']), 'ATS version moved backwards')
        if old_row and old_row.get('result') is not None:
            require(row.get('result') == old_row['result'], 'Accepted ATS final changed')
