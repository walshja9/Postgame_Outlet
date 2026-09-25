"""First-capture McCabe game lines inside the append-only season archive.

No network, grading, backfill, or numerical adjustment. Replay uses saved input
bytes, not today's editorial files. The season writer supplies the durable clock.
"""
import copy
import csv
from datetime import timedelta
import io
import json
import math
from pathlib import Path
import re

import spreads
from pgo_season import IDENTITY, canonical, identity, require, sha, utc

DATA = Path(__file__).resolve().parent / 'data'
FILES = ('ratings.csv', 'config.csv', 'hfa.csv', 'snapshots.json')
METHOD = 'McCabe spreads.py v1: rounded component totals; team/default HFA even at neutral venues; +0.5 for UTC hour 23-04; Python half-point rounding'
TEAMS = {code: name for name, code in spreads.ABBR.items()}


class LateCapture(ValueError):
    """Only this failure permits dropping newly collected optional records."""


def _number(value):
    require(not isinstance(value, bool) and value not in (None, ''), 'Missing McCabe numeric input')
    number = float(value)
    require(math.isfinite(number), 'Nonfinite McCabe input')
    return number


def _csv(source):
    return list(csv.DictReader(io.StringIO(source['text'].lstrip('\ufeff'))))


def _inputs(files, checked):
    require(set(files) == set(FILES), 'McCabe input inventory differs')
    for source in files.values():
        raw = source['text'].encode('utf-8')
        require(type(source['bytes']) is int and len(raw) == source['bytes']
                and sha(raw) == source['sha256'], 'McCabe input bytes/hash differ')
    config_rows = _csv(files['config.csv'])
    config = {r['key']: r['value'] for r in config_rows}
    require(len(config) == len(config_rows), 'Duplicate McCabe configuration key')
    edition = config['edition']
    match = re.fullmatch(r'Week ([1-9]|1[0-8]) (\d{4})(?: .+)?', edition)
    require(match is not None, 'McCabe edition must identify its regular-season week and year')
    week, year = int(match[1]), int(match[2])
    require(str(year) == config['season'], 'McCabe edition season differs')
    teams = {}
    for row in _csv(files['ratings.csv']):
        team = row['team']
        require(team in spreads.ABBR and spreads.ABBR[team] not in teams, 'Unknown or duplicate McCabe team')
        require(row['needs_review'].strip().upper() == 'N', 'McCabe ratings require editorial review')
        require(isinstance(row['qb_name'], str) and row['qb_name'].strip(), 'Missing McCabe quarterback')
        require(row['conf'] and row['division'], 'Missing McCabe team metadata')
        qb, off, defense = (_number(row[k]) for k in ('qb_value', 'off_value', 'def_value'))
        teams[spreads.ABBR[team]] = dict(team=team, conf=row['conf'], div=row['division'],
            qb_name=row['qb_name'], qb=qb, off=off, **{'def': defense}, rating=round(qb + off + defense, 1))
    require(set(teams) == set(TEAMS), 'McCabe capture requires exactly 32 teams')
    entry = json.loads(files['snapshots.json']['text'])[edition]
    published = entry['published_at']
    require(utc(published) <= checked, 'McCabe snapshot publication is in the future')
    frozen = entry['rows']
    require(len(frozen) == 32 and len({r['team'] for r in frozen}) == 32, 'McCabe snapshot inventory differs')
    expected = {row['team']: row for row in teams.values()}
    for row in frozen:
        require(row['team'] in expected, 'Unknown McCabe snapshot team')
        for key, value in expected[row['team']].items():
            actual = _number(row[key]) if key in ('qb', 'off', 'def', 'rating') else row[key]
            require(actual == value, 'McCabe snapshot quarterback/components differ from reviewed ratings')
    hfa_rows = _csv(files['hfa.csv'])
    hfa = {r['team']: _number(r['home_field']) for r in hfa_rows}
    require(len(hfa) == len(hfa_rows) and 'DEFAULT' in hfa and set(hfa) <= set(spreads.ABBR) | {'DEFAULT'},
            'Missing, duplicate or unknown McCabe HFA input')
    return dict(edition=edition, week=week, season=year, published_at=published, teams=teams, hfa=hfa)


def _game(game):
    require(type(game['season']) is int and type(game['week']) is int
            and 1 <= game['week'] <= 18 and game['game_type'] == 'REG', 'Invalid McCabe game season/week')
    require(game['home'] in TEAMS and game['away'] in TEAMS and game['home'] != game['away'],
            'Invalid McCabe game teams')
    match = re.fullmatch(r'(\d{4})_(\d{2})_([A-Z]{2,3})_([A-Z]{2,3})', game['game_id'])
    normalize = lambda team: 'LAR' if team == 'LA' else team
    require(match is not None and (int(match[1]), int(match[2]), normalize(match[3]), normalize(match[4]))
            == (game['season'], game['week'], game['away'], game['home']), 'McCabe game identity differs')
    cutoff = utc(game['kickoff']) - timedelta(minutes=60)
    require(utc(game['lock_at']) == cutoff, 'McCabe cutoff must be T-60')
    require(game['location'] in ('Home', 'Neutral'), 'Unknown McCabe venue convention')
    return cutoff


def _index(rows):
    indexed = {r['game_id']: r for r in rows}
    require(len(indexed) == len(rows), 'Duplicate McCabe game')
    return indexed


def _forecast(game, inputs, input_id, issued, market):
    cutoff = _game(game)
    require(game['season'] == inputs['season'] and game['week'] == inputs['week'], 'McCabe edition/game week differs')
    require(utc(inputs['published_at']) <= utc(issued) < cutoff, 'McCabe forecast was not issued before cutoff')
    home, away = inputs['teams'][game['home']], inputs['teams'][game['away']]
    base = inputs['hfa'].get(home['team'], inputs['hfa']['DEFAULT'])
    prime = spreads.is_primetime(utc(game['kickoff']).isoformat())
    hfa = base + (0.5 if prime else 0)
    margin = home['rating'] - away['rating'] + hfa
    return dict({k: game[k] for k in IDENTITY}, location=game['location'], lock_at=game['lock_at'],
                issued_at=issued, edition=inputs['edition'], published_at=inputs['published_at'],
                input_id=input_id, method=METHOD, teams={'home': home, 'away': away},
                base_hfa=base, primetime=prime, hfa=hfa, margin=margin,
                spread=spreads.round_half(-margin), market=copy.deepcopy(market))


def _market(row, root):
    market = row['market']
    require(market.get('provider_published_at') is None, 'McCabe market provider publication time is unavailable')
    if market['status'] == 'UNAVAILABLE':
        require(set(market) == {'status', 'reason', 'provider_published_at'} and market['reason'], 'Invalid unavailable McCabe market')
        return
    from pgo_ats import MAX_CAPTURE_AGE, PROVIDER, _quote, _read
    require(market['status'] == 'AVAILABLE' and market['provider'] == PROVIDER, 'Invalid McCabe market provider')
    issued = utc(row['issued_at']); observed = utc(market['captured_at'])
    require(market['captured_at'] == market['source']['captured_at']
            and observed <= issued and issued - observed <= MAX_CAPTURE_AGE, 'McCabe market observation clock differs')
    payload = _read(market['source'], root, issued)
    from pgo_season import parse_scoreboard
    event, = [e for e in payload['events'] if str(e['id']) == market['event_id']]
    events = parse_scoreboard(dict(payload, events=[event]), [row], market['captured_at'])['events']
    require(events[row['game_id']]['event_id'] == market['event_id'], 'McCabe market event identity differs')
    require(_quote(event, row) == _number(market['home_handicap']), 'McCabe market line replay differs')


def validate(state, root):
    """Validate saved evidence independently of today's local editorial files."""
    payload = state.get('mccabe_forecasts') or {}
    if not payload:
        return
    require(payload['status'] in ('READY', 'WAITING', 'BLOCKED'), 'Invalid McCabe collection status')
    checked = utc(state['checked_at'])
    require(utc(payload['checked_at']) <= checked, 'McCabe check follows season state')
    games = _index(payload.get('games', [])); files = payload.get('inputs', {})
    parsed = {}
    for key, source in files.items():
        require(sha(canonical(source)) == key, 'McCabe input bundle hash differs')
        parsed[key] = _inputs(source, checked)
    require(set(files) == {g['input_id'] for g in games.values()}, 'McCabe input bundle references differ')
    for row in games.values():
        require(row['season'] == state['season'] and utc(row['issued_at']) <= checked, 'McCabe forecast clock/season differs')
        replay = _forecast(row, parsed[row['input_id']], row['input_id'], row['issued_at'], row['market'])
        require(row == replay, 'McCabe forecast arithmetic/input replay differs')
        _market(row, root)


def blocked(previous, checked_at, reason):
    out = copy.deepcopy((previous or {}).get('mccabe_forecasts') or {})
    out.update(status='BLOCKED', checked_at=checked_at, blocked_reason=str(reason))
    out.setdefault('games', []); out.setdefault('inputs', {})
    return out


def refresh(state, previous, root, checked_at, *, data_dir=None):
    """Capture eligible current-week games once; all changes are detached."""
    out = blocked(previous, checked_at, '')
    try:
        if previous:
            validate(previous, root)
        checked = utc(checked_at)
        require(checked == utc(state['checked_at']), 'McCabe issue clock differs from season check')
        require(not previous or utc(previous['checked_at']) <= checked, 'McCabe clock moved backwards')
        files = {}
        for name in FILES:
            raw = ((data_dir or DATA) / name).read_bytes()
            files[name] = dict(text=raw.decode('utf-8'), sha256=sha(raw), bytes=len(raw))
        inputs = _inputs(files, checked)
        require(inputs['season'] == state['season'], 'McCabe season differs from schedule')
        schedule = _index(state['schedule'])
        before = _index(out['games'])
        for key, old in before.items():
            require(key in schedule and identity(old, schedule[key]) and old['location'] == schedule[key]['location'],
                    'Saved McCabe schedule identity changed')
        eligible = []
        for game in schedule.values():
            cutoff = _game(game)
            if (game['week'] == inputs['week'] == state['current_week'] and checked < cutoff
                    and game['game_id'] not in before and game['game_id'] not in {r['game_id'] for r in state['results']}):
                eligible.append(game)
        require(state['status'] == 'READY', 'Verified season schedule is unavailable')
        quotes = {}
        if eligible:
            from pgo_ats import _sources
            try:
                quotes, _, _ = _sources(state, root, checked)
            except (ValueError, KeyError, TypeError, OSError):
                pass  # The human line is still eligible without a market comparison.
        added = []
        input_id = sha(canonical(files))
        for game in eligible:
            market = dict(status='UNAVAILABLE', provider_published_at=None,
                          reason='No verified current market quote in the existing archived captures')
            if game['game_id'] in quotes:
                from pgo_ats import PROVIDER
                line, source, event = quotes[game['game_id']]
                market = dict(status='AVAILABLE', provider=copy.deepcopy(PROVIDER), home_handicap=line,
                    source=source, captured_at=source['captured_at'], event_id=event, provider_published_at=None)
            row = _forecast(game, inputs, input_id, checked_at, market)
            _market(row, root)
            added.append(row)
        if added:
            out['inputs'][input_id] = files
            out['games'].extend(added)
        out.update(status='READY' if out['games'] else 'WAITING', blocked_reason=None)
        validate(dict(state, mccabe_forecasts=out), root)
        return out
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
        return blocked(previous, checked_at, error)


def check_durable(state, previous, durable, root):
    """Never mutate/drop an issued record; new records must finish before T-60."""
    validate(state, root)
    before = (previous or {}).get('mccabe_forecasts') or {}
    after = state.get('mccabe_forecasts') or {}
    old = _index(before.get('games', [])); new = _index(after.get('games', []))
    require(set(old) <= set(new) and all(new[k] == v for k, v in old.items()), 'An issued McCabe forecast was removed or changed')
    require(all(after.get('inputs', {}).get(k) == v for k, v in before.get('inputs', {}).items()),
            'An issued McCabe input bundle was removed or changed')
    clock = utc(durable)
    require(utc(state['checked_at']) <= clock, 'McCabe durable clock precedes its season check')
    schedule = _index(state.get('schedule', []))
    for key in set(new) - set(old):
        row = new[key]
        require(state['status'] == 'READY' and key not in {r['game_id'] for r in state['results']},
                'New McCabe capture requires a verified schedule without an accepted final')
        require(row['issued_at'] == state['checked_at'], 'New McCabe issue clock differs from collection')
        require(key in schedule and identity(row, schedule[key]) and row['location'] == schedule[key]['location']
                and row['week'] == state['current_week'], 'New McCabe capture does not match current schedule/week')
        if clock >= _game(row):
            raise LateCapture('McCabe capture crossed the durable T-60 cutoff')
