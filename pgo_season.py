"""Automatic, append-only PGO final grading and regular-season editions."""
import argparse
import copy
import csv
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import gzip
import hashlib
import importlib
import io
import json
import math
import os
from pathlib import Path
import re
import urllib.request

import pgo_sources
from release_ratings import atomic_write_text

ROOT = Path(__file__).resolve().parent
DEFAULT_ROOT = ROOT / 'docs/evidence/season-2026'
SEASON = 2026
URLS = {
    'schedule': 'https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv.gz',
    'team': 'https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_2026.csv.gz',
    'player': 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.csv.gz',
    'roster': 'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2026.csv.gz',
    'depth': 'https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv.gz',
}
SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={season}&seasontype=2&week={week}'
IDENTITY = ('game_id', 'season', 'week', 'game_type', 'home', 'away', 'kickoff')


def utc(value):
    date = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return date.astimezone(timezone.utc)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_bytes())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identity(left, right):
    return all(utc(left[k]) == utc(right[k]) if k == 'kickoff' else left[k] == right[k] for k in IDENTITY)


def parse_scoreboard(payload, schedule, captured_at):
    """Only explicit completed FINAL statuses are results; observed time is conservative."""
    season, week = payload['season']['year'], payload['week']['number']
    require(type(season) is int and season == SEASON and payload['season']['type'] == 2, 'Scoreboard season/type differs')
    require(type(week) is int and 1 <= week <= 18, 'Scoreboard week differs')
    expected = {(g['away'], g['home']): g for g in schedule if g['season'] == season and g['week'] == week}
    require(expected, 'Scoreboard has no expected games')
    seen, event_ids, events, results = set(), set(), {}, []
    for event in payload['events']:
        require(event['season']['year'] == season and event['season']['type'] == 2 and event['week']['number'] == week, 'Event season/week/type differs')
        require(len(event['competitions']) == 1, 'Ambiguous competition')
        comp = event['competitions'][0]
        require(str(event['id']) not in event_ids and str(comp.get('id')) == str(event['id']), 'Duplicate or mismatched provider event ID')
        event_ids.add(str(event['id']))
        sides = {x['homeAway']: x for x in comp['competitors']}
        require(len(comp['competitors']) == 2 and set(sides) == {'home', 'away'}, 'Invalid competitors')
        pair = tuple(pgo_sources.normalize_team({'WSH':'WAS'}.get(sides[k]['team']['abbreviation'], sides[k]['team']['abbreviation'])) for k in ('away', 'home'))
        require(pair in expected and pair not in seen, 'Unexpected or duplicate game identity')
        seen.add(pair); g = expected[pair]
        require(not g.get('espn_id') or str(g['espn_id']) == str(event['id']), 'Schedule provider event ID differs')
        require(utc(event['date']) == utc(g['kickoff']), 'Schedule kickoff differs; review rescheduling')
        status = comp.get('status', event.get('status', {})).get('type', {})
        if 'status' in event and 'status' in comp:
            require(all(event['status'].get('type',{}).get(k)==status.get(k) for k in ('completed','state','name')), 'Conflicting event and competition status')
        events[g['game_id']] = {'event_id': str(event['id']), 'status': status.get('name', 'UNKNOWN')}
        if status.get('completed') is not True or status.get('state') != 'post':
            continue
        require(status.get('name') in {'STATUS_FINAL', 'STATUS_FINAL_OVERTIME'}, 'Unsupported completed status')
        require(utc(captured_at) > utc(g['kickoff']), 'Final observed before kickoff')
        scores = {}
        for side in ('home', 'away'):
            raw = str(sides[side]['score'])
            require(re.fullmatch(r'\d+', raw) is not None, 'Final scores must be nonnegative integers')
            scores[side + '_score'] = int(raw)
        results.append(dict(game_id=g['game_id'], season=season, week=week, game_type='REG',
                            kickoff=g['kickoff'], home_team=g['home'], away_team=g['away'], **scores,
                            actual_margin=scores['home_score']-scores['away_score'], finalized_at=captured_at,
                            final_time_basis='First captured explicit provider FINAL status', event_id=str(event['id'])))
    require(seen == set(expected), 'Scoreboard game inventory is incomplete')
    return {'results': results, 'events': events}


def merge_results(existing, incoming):
    output = {r['game_id']: copy.deepcopy(r) for r in existing}
    require(len(output) == len(existing), 'Duplicate saved result')
    seen = set()
    for result in incoming:
        key = result['game_id']; require(key not in seen, 'Duplicate incoming result'); seen.add(key)
        if key in output:
            fields = ('season', 'week', 'game_type', 'home_team', 'away_team', 'home_score', 'away_score', 'actual_margin', 'event_id')
            require(all(output[key][k] == result[k] for k in fields) and utc(output[key]['kickoff']) == utc(result['kickoff']), 'Accepted final changed; review required')
        else:
            output[key] = copy.deepcopy(result)
    return sorted(output.values(), key=lambda r: (r['kickoff'], r['game_id']))


def completed_week(schedule, results):
    ids = {r['game_id'] for r in results}; completed = 0
    for week in range(1, 19):
        games = {g['game_id'] for g in schedule if g['week'] == week}
        if not games or not games <= ids:
            break
        completed = week
    return completed


def forecast_status(game, checked_at):
    if game.get('margin') is None or game.get('blocked_reason'):
        return 'BLOCKED'
    return 'LOCKED' if utc(checked_at) >= utc(game['kickoff']) - timedelta(minutes=60) else 'DRAFT'


def record(games, results):
    finals = {r['game_id']: r for r in results}
    require(len(finals) == len(results), 'Duplicate grades result')
    counts = dict(wins=0, losses=0, ties=0, no_pick=0, pending=0)
    for g in games:
        r = finals.get(g['game_id'])
        if r is None:
            counts['pending'] += 1
            continue
        require(r['home_team'] == g['home'] and r['away_team'] == g['away'] and utc(r['kickoff']) == utc(g['kickoff']), 'Grade identity differs')
        m = g.get('margin')
        if m is None or m == 0 or g.get('blocked_reason'):
            counts['no_pick'] += 1
        elif r['actual_margin'] == 0:
            counts['ties'] += 1
        else:
            counts['wins' if (m > 0) == (r['actual_margin'] > 0) else 'losses'] += 1
    return counts


def allocate_confidence(games, calibration):
    from pgo_confidence_picks import _probabilities
    rows = copy.deepcopy(games)
    eligible = [g for g in rows if g.get('margin') not in (None,0) and not g.get('blocked_reason')]
    for g in eligible:
        probabilities = _probabilities(g['margin'], calibration['slope'], calibration['tie_probability'])
        side = 'home' if probabilities['home'] >= probabilities['away'] else 'away'
        g['pick'] = g[side]
        g['confidence'] = dict(win_probability=probabilities[side], probabilities=probabilities, added_after_lock=False, earned_points=None)
    for points, g in enumerate(sorted(eligible, key=lambda g: (g['confidence']['win_probability'], g['game_id'])), 1):
        g['confidence'].update(points=points, expected_points=points*g['confidence']['win_probability'])
    return rows


def revise_game(old, new, checked_at):
    require(identity(old, new), 'Revision game identity differs')
    require(utc(checked_at) < utc(old['kickoff'])-timedelta(minutes=60), 'Prediction is locked')
    require(utc(new['issued_at']) <= utc(checked_at), 'Revision is from the future')
    require(utc(new['issued_at']) >= utc(old['issued_at']), 'Revision moves backwards')
    return copy.deepcopy(new)


def archive_href(relative):
    if relative.split('/')[0] in {'runs-v2', 'availability-v2', 'source-archive'}:
        return 'https://raw.githubusercontent.com/walshja9/Postgame_Outlet/main/docs/evidence/season-2026/' + relative
    return 'evidence/season-2026/' + relative


def save_state(state, root=DEFAULT_ROOT):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    require(not root.is_symlink(), 'Season root is a symlink')
    stamp = utc(state['checked_at']).strftime('%Y%m%dT%H%M%S%fZ')
    directory = root/'runs-v2'/stamp
    directory.mkdir(parents=True, exist_ok=False)
    payload = gzip.compress(canonical(state), mtime=0)
    with (directory/'state.json.gz').open('xb') as handle:
        handle.write(payload); handle.flush(); os.fsync(handle.fileno())
    durable = now()
    prior = None
    if (root/'current.json').exists():
        prior = load_current(root)
        prior_games = {g['game_id']:g for w in prior['weeks'] for g in w['games']}
        for week in state['weeks']:
            for game in week['games']:
                before = prior_games.get(game['game_id'])
                fields = ('margin','total','home_points','away_points','issued_at','source_edition','inputs_as_of','explanation','expected_qbs','availability','blocked_reason')
                changed = before is not None and any(before.get(k)!=game.get(k) for k in fields)
                new_pick = before is None and game.get('margin') is not None
                if changed or new_pick:
                    require(utc(durable)<utc(game['kickoff'])-timedelta(minutes=60), 'Forecast changed across durable-write lock deadline')
    if 'penalty_shadow' in state:
        from pgo_penalty_monitor import check_durable_shadow
        check_durable_shadow(state, prior, durable)
    if 'totals_shadow' in state or 'totals_shadow' in (prior or {}):
        from pgo_totals_monitor import check_durable_shadow
        check_durable_shadow(state, prior, durable)
    if 'weights_shadow' in state or 'weights_shadow' in (prior or {}):
        from pgo_weights_monitor import check_durable_shadow
        check_durable_shadow(state, prior, durable)
    if 'replacement_depth' in state:
        check_replacement_depth(state, prior, durable)
    manifest = dict(schema_version=1, created_at=durable, files={'state.json.gz': {'sha256':sha(payload),'bytes':len(payload)}},
                    code_sha256=sha(Path(__file__).read_bytes()))
    previous = root/'current.json'
    if previous.exists(): manifest['previous'] = read_json(previous)
    raw = canonical(manifest)
    with (directory/'manifest.json').open('xb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    relative=directory.relative_to(root).as_posix()
    pointer = dict(path=relative, manifest_sha256=sha(raw), checked_at=state['checked_at'],
                   state_url=archive_href(relative+'/state.json.gz'), manifest_url=archive_href(relative+'/manifest.json'))
    atomic_write_text(root/'current.json', canonical(pointer).decode())
    return directory


def load_current(root=DEFAULT_ROOT):
    root = Path(root)
    if not (root/'current.json').exists(): return None
    require(not root.is_symlink() and not (root/'current.json').is_symlink(), 'Invalid season pointer')
    pointer = read_json(root/'current.json')
    require(re.fullmatch(r'runs(?:-v2)?/\d{8}T\d{12}Z', pointer['path']) is not None, 'Invalid season archive path')
    directory = root/pointer['path']
    require(not directory.is_symlink(), 'Invalid season archive directory')
    raw = (directory/'manifest.json').read_bytes()
    require(sha(raw) == pointer['manifest_sha256'], 'Season manifest hash differs')
    manifest = json.loads(raw)
    require(set(manifest['files']) in ({'state.json'}, {'state.json.gz'}), 'Invalid season state inventory')
    filename=next(iter(manifest['files']))
    payload = (directory/filename).read_bytes(); meta = manifest['files'][filename]
    require(not (directory/filename).is_symlink() and sha(payload) == meta['sha256'] and len(payload) == meta['bytes'], 'Season state hash differs')
    state = json.loads(gzip.decompress(payload) if filename.endswith('.gz') else payload)
    require(state['schema_version'] == 1 and state['season'] == SEASON, 'Season schema differs')
    references = [*state.get('source_captures', []), *(r['source'] for r in state.get('results',[]) if 'source' in r)]
    references += state.get('rankings',{}).get('source_captures',[])
    references += [ref for refs in state.get('edition_sources',{}).values() for ref in refs]
    verified = {}
    for ref in references:
        key = ref['path']
        require(re.fullmatch(r'(?:sources|source-archive)/[0-9a-f]{64}\.(?:json|csv\.gz)',key) is not None, 'Invalid captured source path')
        require(utc(ref['captured_at']) <= utc(state['checked_at']), 'Source captured after state')
        if key not in verified:
            source_path = root/key
            require(not source_path.is_symlink(), 'Captured source is a symlink')
            source_raw = source_path.read_bytes()
            verified[key]=(sha(source_raw),len(source_raw))
        require(verified[key]==(ref['sha256'],ref['bytes']), 'Captured source hash or length differs')
    availability = {g.get('availability',{}).get('source_archive') for w in state['weeks'] for g in w['games']}
    for path in availability - {None}:
        require(re.fullmatch(r'availability(?:-v2)?/\d{8}T\d{12}Z',path) is not None, 'Invalid availability archive path')
        from pgo_season_availability import load_availability
        load_availability(root/path)
    return state


def parse_schedule(raw, season=SEASON):
    from pgo_prospective import _normalize_row
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(raw).decode('utf-8-sig'))))
    games = []
    for row in rows:
        if row.get('season') != str(season) or row.get('game_type') != 'REG': continue
        normalized = _normalize_row(row)
        game = {k: normalized[k] for k in ('game_id', 'season', 'week', 'game_type', 'kickoff', 'location', 'home_rest', 'away_rest')}
        game.update(home=normalized['home_team'], away=normalized['away_team'], espn_id=row.get('espn',''))
        require(re.fullmatch(r'\d+', game['espn_id']) is not None, 'Missing schedule provider event ID')
        game['lock_at'] = (utc(game['kickoff'])-timedelta(minutes=60)).isoformat()
        game['provider_scores'] = {k: row.get(k) for k in ('home_score', 'away_score')}
        games.append(game)
    require(len(games) == 272 and len({g['game_id'] for g in games}) == 272, 'Expected complete 272-game regular-season schedule')
    require({g['week'] for g in games} == set(range(1, 19)), 'Schedule weeks incomplete')
    return sorted(games, key=lambda g: (g['kickoff'], g['game_id']))


def fetch_source(url, root=DEFAULT_ROOT):
    """Archive actual response bytes once; each reference retains its observation time."""
    require(url.startswith(('https://github.com/nflverse/nflverse-data/', 'https://site.api.espn.com/')), 'Unexpected automation source')
    from espn_api import _STRATEGIES
    error = None
    for headers in _STRATEGIES:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as response:
                raw = response.read()
                require(response.status == 200, 'Source response was not successful')
                break
        except (OSError, ValueError) as exc:
            error = exc
    else:
        raise ValueError(f'Source unavailable: {url}: {error}')
    captured = now(); digest = sha(raw)
    suffix = '.csv.gz' if url.endswith('.gz') else '.json'
    relative = 'source-archive/' + digest + suffix
    path = Path(root)/relative; path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): require(path.read_bytes() == raw and not path.is_symlink(), 'Source hash collision or symlink')
    else:
        with path.open('xb') as handle: handle.write(raw)
    return raw, {'url':url, 'captured_at':captured, 'sha256':digest, 'bytes':len(raw), 'path':relative}


def csv_rows(raw):
    return list(csv.DictReader(io.StringIO(gzip.decompress(raw).decode('utf-8-sig'))))


def fetch_inputs(state, root):
    raw, source = fetch_source(URLS['schedule'], root)
    schedule = parse_schedule(raw); sources = [source]
    by_id = {g['game_id']:g for g in schedule}
    for week in state['weeks']:
        for g in week['games']:
            require(g['game_id'] in by_id and identity(g, by_id[g['game_id']]), 'Issued schedule changed; manual rescheduling review required')
    results = list(state['results']); events = {}
    # Finished weeks are checked again for score corrections; pending future weeks are not polled.
    last = max(state['current_week'], completed_week(schedule, results)+1)
    for week in range(1, min(last, 18)+1):
        raw, source = fetch_source(SCOREBOARD.format(season=SEASON, week=week), root)
        accepted = parse_scoreboard(json.loads(raw), schedule, source['captured_at'])
        incoming = [dict(r, source=source) for r in accepted['results']]
        require({r['game_id'] for r in results if r['week']==week} <= {r['game_id'] for r in incoming}, 'Previously accepted final is no longer final; review required')
        results = merge_results(results, incoming)
        events.update(accepted['events']); sources.append(source)
    return schedule, results, sources, events


@lru_cache(maxsize=1)
def initial_snapshot():
    import pgo_forecast_postseason
    return pgo_forecast_postseason.load_snapshot(pgo_forecast_postseason.DEFAULT_DIR)


@lru_cache(maxsize=1)
def legacy_models():
    import pgo_forecast_corrected as corrected
    import pgo_forecast_snapshot as september
    models = []
    for name, module, directory in [('PGO postseason - original Week 1', None, None),
                                     ('PGO corrected - September 8', corrected, corrected.DEFAULT_OUTPUT),
                                     ('PGO - September 7 preseason', september, ROOT/'docs/evidence/forecast-lab-2026/september-07')]:
        snapshot = initial_snapshot() if module is None else module.load_snapshot(directory)
        models.append(dict(name=name, edition=snapshot['edition'], issued_at=snapshot['generated_at'], games=snapshot['games']))
    initial = models[-1]['games']
    models.append(dict(name='PGO v0 - saved preseason baseline', edition='pgo-v0-preseason', issued_at=models[-1]['issued_at'],
                       games=[dict(g, margin=g['pgo_v0_margin'], total=None, home_points=None, away_points=None) for g in initial]))
    return models


def bootstrap():
    from pgo_confidence_full_slate import load_verified, DEFAULT_OUTPUT
    from pgo_model_updates import FULL_CONFIDENCE_MANIFEST_SHA256
    snapshot = initial_snapshot()
    pool = load_verified(DEFAULT_OUTPUT, FULL_CONFIDENCE_MANIFEST_SHA256, snapshot)
    confidence = {g['game_id']:g for g in pool['games']}
    games = []
    for raw in snapshot['games']:
        g = copy.deepcopy(raw); c = confidence[g['game_id']]
        g.update(issued_at=snapshot['generated_at'], source_edition=snapshot['edition'], inputs_as_of=snapshot['inputs_as_of'],
                 expected_qbs={t:next(r['qb_name'] for r in snapshot['teams'] if r['team']==t) for t in (g['home'],g['away'])}, lock_at=(utc(g['kickoff'])-timedelta(minutes=60)).isoformat(),
                 pick=c['selected_team'], blocked_reason=None,
                 confidence=dict(points=c['confidence_points'],win_probability=c['win_probability'],expected_points=c['expected_points'],
                                 probabilities=c['probabilities'],earned_points=None,added_after_lock=c['added_after_lock']),
                 availability=dict(checked_at=snapshot['inputs_as_of'], summary='Saved opening-week report; non-QB injuries are not numerical adjustments.', blocked_reason=None))
        games.append(g)
    teams = copy.deepcopy(snapshot['teams'])
    from pgo_forecast_corrected import score
    from pgo_challenger import _matchup_features
    by_team={t['team']:t for t in teams}
    for g in games:
        vector=_matchup_features(by_team[g['home']]['features'],by_team[g['away']]['features'],dict(g,neutral=g['location']=='Neutral'))
        neutral=score(dict(vector,home_field=0.,rest_difference=0.),snapshot['fit'])
        venue=score(dict(vector,rest_difference=0.),snapshot['fit'])-neutral
        require(math.isclose(neutral,by_team[g['home']]['rating']-by_team[g['away']]['rating'],abs_tol=1e-8), 'Opening ratings and neutral margin differ')
        g['explanation']=dict(neutral_margin=neutral,home_adjustment=venue,rest_adjustment=g['margin']-neutral-venue,
                              home_rating=by_team[g['home']]['rating'],away_rating=by_team[g['away']]['rating'],
                              rating_inputs_as_of=snapshot['inputs_as_of'],total_method='Saved 2025 regular-season and playoff scoring history')
    return dict(schema_version=1, season=SEASON, current_week=1, checked_at=now(), status='READY', blocked_reason=None,
                rankings=dict(edition=snapshot['edition'],generated_at=snapshot['generated_at'],inputs_as_of=snapshot['inputs_as_of'],
                              history_through=snapshot['history']['through'],teams=teams,completed_week=0),
                weeks=[dict(week=1,source_edition=snapshot['edition'],generated_at=snapshot['generated_at'],inputs_as_of=snapshot['inputs_as_of'],games=games)],
                calibration={'slope':pool['calibration']['slopes']['postseason'],'tie_probability':pool['calibration']['tie_probability']},
                results=[],sources=[],limitations=['EXPERIMENTAL / HOLD. Weekly updates do not establish predictive accuracy.',
                  'Non-QB availability is shown separately; no fitted injury or replacement-quality penalty is applied.',
                  'Expected scores use the existing scoring-history heuristic. Probabilities reuse the frozen historical calibration.'],
                archives=[])


def select_roster(roster, depth, captured_at):
    active = {}
    for row in roster:
        if str(row.get('season')) != str(SEASON) or row.get('status') != 'ACT' or row.get('position') != 'QB': continue
        team = pgo_sources.normalize_team(row['team']); key=(team,row['gsis_id'])
        require(key not in active, 'Duplicate current roster QB')
        active[key] = dict(row,team=team)
    eligible = [r for r in depth if r.get('pos_abb') == 'QB' and str(r.get('pos_rank')) == '1' and utc(r['dt']) <= utc(captured_at)]
    require(eligible, 'No dated QB depth data')
    latest = max(utc(r['dt']) for r in eligible)
    require(utc(captured_at)-latest <= timedelta(days=7), 'QB depth snapshot is older than seven days')
    selected = {}
    for r in eligible:
        if utc(r['dt']) != latest: continue
        team = pgo_sources.normalize_team(r['team']);key=(team,r['gsis_id'])
        require(team not in selected and key in active, 'Expected QB is ambiguous or not on the active roster')
        selected[team] = active[key]
    require(set(selected) == set(pgo_sources.CURRENT_TEAMS) and len({r['gsis_id'] for r in selected.values()}) == 32, 'Expected QBs must cover all 32 teams uniquely')
    return selected


def build_next(state, schedule, results, root, *, completed=None, selected=None, roster_sources=()):
    from pgo_season_model import load_seed, build_week
    completed = completed_week(schedule, results) if completed is None else completed
    require(0 <= completed <= 18, 'Unsupported completed week')
    captured, sources = {'team': [], 'player': []}, list(roster_sources)
    kinds = (['team','player'] if completed else []) + ([] if selected is not None else ['roster','depth'])
    for kind in kinds:
        raw, source = fetch_source(URLS[kind], root)
        captured[kind] = csv_rows(raw); sources.append(source)
    generated = now()
    selected = selected or select_roster(captured['roster'], captured['depth'], generated)
    by_id={g['game_id']:g for g in schedule}
    completed_games=[]
    for r in results:
        if r['week'] > completed: continue
        g=by_id[r['game_id']]
        provider=g.get('provider_scores',{})
        require(all(str(provider.get(k,'')) in {str(r[k]), str(float(r[k]))} for k in ('home_score','away_score')), 'Statistics schedule does not yet agree with verified final scores')
        completed_games.append(dict(g,home_score=r['home_score'],away_score=r['away_score'],finalized_at=r['finalized_at']))
    snapshot = initial_snapshot()
    output = build_week(load_seed(),snapshot['fit'],completed_games,captured['team'],captured['player'],selected,
                        [g for g in schedule if g['week']==completed+1 and utc(g['kickoff'])-timedelta(minutes=60)>utc(generated)],season=SEASON,completed_week=completed,
                        generated_at=generated,inputs_as_of=generated,scoring_rates=snapshot['scoring_rates'],league_mean_total=snapshot['league_mean_total'])
    edition=f'pgo-postseason-{SEASON}-'+('after-week18' if completed==18 else f'week{completed+1}')+'-'+utc(generated).strftime('%Y%m%dT%H%M%SZ')
    old = {r['team']:r['rank'] for r in state['rankings']['teams']}
    for team in output['teams']: team['prior_rank']=old[team['team']]
    games=[]
    for g in output['games']:
        g=copy.deepcopy(g);g.update(issued_at=generated,source_edition=edition,inputs_as_of=generated,expected_qbs={t:selected[t]['full_name'] for t in (g['home'],g['away'])},lock_at=(utc(g['kickoff'])-timedelta(minutes=60)).isoformat(),blocked_reason=None)
        if utc(generated)>=utc(g['lock_at']):
            for field in ('margin','total','home_points','away_points'): g[field]=None
            g.update(pick=None,confidence=None,blocked_reason='No forecast was issued before this game locked.')
        games.append(g)
    issued={g['game_id'] for g in games}
    for source_game in schedule:
        if source_game['week']==completed+1 and source_game['game_id'] not in issued:
            games.append(dict(source_game,margin=None,total=None,home_points=None,away_points=None,pick=None,confidence=None,issued_at=generated,source_edition=edition,inputs_as_of=generated,blocked_reason='No forecast was issued before this game locked.'))
    games=allocate_confidence(games,state['calibration'])
    rankings=dict(edition=edition,generated_at=generated,inputs_as_of=generated,history_through=max((r['kickoff'] for r in completed_games),default=snapshot['history']['through']),
                  teams=output['teams'],completed_week=completed,source_captures=sources)
    week=dict(week=completed+1,source_edition=edition,generated_at=generated,inputs_as_of=generated,games=games)
    week['source_captures']=sources
    return rankings,week,sources


def refresh_availability(state, root):
    from pgo_season_availability import capture_availability
    checked=now()
    games=[g for w in state['weeks'] for g in w['games'] if timedelta(minutes=60)<utc(g['kickoff'])-utc(checked)<=timedelta(hours=24)]
    if not games:return []
    raw, roster_source=fetch_source(URLS['roster'],root);roster=csv_rows(raw)
    raw, depth_source=fetch_source(URLS['depth'],root);depth=csv_rows(raw)
    selected=select_roster(roster,depth,now())
    expected={t:r['gsis_id'] for t,r in selected.items()}
    before={t['team']:t['qb_gsis_id'] for t in state['rankings']['teams']}
    changed={team for team in expected if before[team]!=expected[team]}
    path=Path(root)/'availability-v2'/utc(checked).strftime('%Y%m%dT%H%M%S%fZ')
    captured=capture_availability(games,roster,expected,path)
    refs=[roster_source,depth_source]
    if any(changed & {g['home'],g['away']} for g in games):
        rankings,revision,sources=build_next(state,state['schedule'],state['results'],root,
            completed=state['rankings']['completed_week'],selected=selected,roster_sources=refs)
        new_games={g['game_id']:g for g in revision['games']}
        for week in state['weeks']:
            for index, old in enumerate(week['games']):
                new=new_games.get(old['game_id'])
                if new is None or utc(now())>=utc(old['kickoff'])-timedelta(minutes=60):continue
                assigned=old.get('confidence') or old.get('withheld_confidence')
                if new.get('confidence') and assigned:
                    new['confidence']['points']=assigned['points']
                    new['confidence']['expected_points']=assigned['points']*new['confidence']['win_probability']
                new['expected_qbs']={t:selected[t]['full_name'] for t in (new['home'],new['away'])}
                new['availability']=old.get('availability',{})
                if old.get('blocked_by_availability') and not changed & {old['home'],old['away']}:
                    for key in ('blocked_reason','blocked_by_availability','withheld_confidence'):
                        if key in old:new[key]=copy.deepcopy(old[key])
                    new['confidence']=None;new['pick']=None
                week['games'][index]=revise_game(old,new,now())
            if week['week']==revision['week']:
                week.update(source_edition=revision['source_edition'],generated_at=revision['generated_at'],inputs_as_of=revision['inputs_as_of'])
        state['rankings']=rankings;state.setdefault('edition_sources',{})[rankings['edition']]=sources;refs=sources
        games=[g for w in state['weeks'] for g in w['games'] if g['game_id'] in captured['games']]
    for g in games:
        observation=captured['games'][g['game_id']]
        if utc(now())>=utc(g['kickoff'])-timedelta(minutes=60):continue
        g['availability']=observation
        if observation.get('blocked_reason'):
            g['blocked_reason']=observation['blocked_reason'];g['blocked_by_availability']=True;g['pick']=None
            if g.get('confidence'):
                g['withheld_confidence']=g['confidence'];g['confidence']=None
        # Unknown or omitted reports do not undo a previously confirmed OUT designation.
        g['availability']['source_archive']=path.relative_to(root).as_posix()
    refs.append({'label':'Saved availability observations','href':archive_href(path.relative_to(root).as_posix()+'/availability.json')})
    return refs


def decorate(state, results):
    state['results']=results;finals={r['game_id']:r for r in results}
    all_games=[g for w in state['weeks'] for g in w['games']]
    state['model_records']=[dict(name='PGO weekly model',edition='pgo-weekly-2026',**record(all_games,results))]
    state['model_records'] += [dict(name=m['name'],edition=m['edition'],**record(m['games'],results)) for m in legacy_models()]
    for week in state['weeks']:
        finished=0
        for g in week['games']:
            result=finals.get(g['game_id'])
            g['forecast_status']=forecast_status(g,state['checked_at'])
            g['pick']=None if g.get('margin') is None or g.get('blocked_reason') or g['margin']==0 else g['home'] if g['margin']>0 else g['away']
            g['grade']='PENDING';g['result']=None
            if result:
                finished+=1;g['result']={k:result[k] for k in ('home_score','away_score')}
                grade=record([g],[result])
                g['grade']=next(label for key,label in [('wins','W'),('losses','L'),('ties','T'),('no_pick','NO_PICK')] if grade[key])
                if g['forecast_status']!='BLOCKED':g['forecast_status']='FINAL'
                if g.get('confidence'):g['confidence']['earned_points']=g['confidence']['points'] if g['grade']=='W' else 0
        week['status']='COMPLETE' if finished==len(week['games']) else 'IN_PROGRESS' if finished or any(utc(g['kickoff'])<=utc(state['checked_at']) for g in week['games']) else 'UPCOMING'
    state['freshness']='Checked every 15 minutes when the scheduled runner is available. Final-result grades update first; weekly rankings wait for complete game statistics.'


def check_replacement_depth(state, previous, durable):
    """A new descriptive observation must be durably saved before its game locks."""
    current=state.get('replacement_depth',{})
    before=(previous or {}).get('replacement_depth',{})
    # Retaining the same dated observation on a failed refresh is permitted after
    # lock. Status/check messages cannot turn a changed observation into an old one.
    messages={'status','blocked_reason','checked_at'}
    if before and {k:v for k,v in current.items() if k not in messages}=={k:v for k,v in before.items() if k not in messages}:
        return
    generated=utc(current['generated_at']); durable=utc(durable)
    require(generated<=utc(state['checked_at'])<=durable, 'Replacement capture clock follows its saved state')
    if current.get('completed_at') is not None:
        require(generated<=utc(current['completed_at'])<=durable, 'Replacement completion clock differs')
    source_time=utc(current['source_as_of']) if current.get('source_as_of') is not None else generated
    require(source_time<=generated, 'Replacement source is from the future')
    for ref in current.get('sources',[]):
        if ref.get('captured_at') is not None:
            require(utc(ref['captured_at'])<=source_time, 'Replacement source capture follows its source clock')
    primary={g['game_id']:g for w in state['weeks'] for g in w['games']}
    finals={r['game_id'] for r in state['results']}
    games=current.get('games',[]); seen=set()
    for game in games:
        key=game['game_id']
        require(key not in seen and key in primary and key not in finals, 'Replacement game is duplicate, missing or already final')
        seen.add(key); source=primary[key]
        require(all(game[k]==source[k] for k in ('home','away'))
                and utc(game['kickoff'])==utc(source['kickoff']), 'Replacement game identity differs')
        cutoff=utc(game['kickoff'])-timedelta(minutes=60)
        require(utc(game['lock_at'])==utc(source['lock_at'])==cutoff, 'Replacement game cutoff differs')
        require(utc(game['captured_at'])==generated, 'Replacement game capture clock differs')
        require(generated<=durable<cutoff, 'Replacement durable-write deadline crossed')


def refresh_experiments(state, previous, root):
    """Run each optional comparison independently over detached verified inputs."""
    operations=(('penalty_shadow','pgo_penalty_monitor','refresh_shadow',True),
                ('totals_shadow','pgo_totals_monitor','refresh_shadow',False),
                ('weights_shadow','pgo_weights_monitor','refresh_shadow',False),
                ('replacement_depth','research.pgo_replacement_depth_20260910.capture','capture',True))
    for key,module_name,method,needs_root in operations:
        old=(previous or {}).get(key,{})
        try:
            operation=getattr(importlib.import_module(module_name),method)
            arguments=[copy.deepcopy(state)]
            if key!='replacement_depth':arguments.append(copy.deepcopy(previous))
            if needs_root:arguments.append(root)
            arguments.append(state['checked_at'])
            result=operation(*arguments)
            require(isinstance(result,dict), 'Experiment returned no saved payload')
            if key=='replacement_depth' and result.get('status')=='BLOCKED' and old:
                result=dict(copy.deepcopy(old),status='BLOCKED',blocked_reason=result.get('blocked_reason'),checked_at=state['checked_at'])
            state[key]=result
        except Exception as error:
            # An optional study must not suppress primary grades or another study.
            state[key]=dict(copy.deepcopy(old),status='BLOCKED',blocked_reason=str(error),checked_at=state['checked_at'])
            if key=='replacement_depth' and not old:
                state[key].update(generated_at=state['checked_at'],games=[],teams=[],sources=[],forecast_adjustment=None)


def refresh(root=DEFAULT_ROOT):
    root=Path(root);previous=load_current(root)
    if previous and previous.get('season_complete'):return previous
    state=copy.deepcopy(previous) if previous else bootstrap()
    state.update(checked_at=now(),status='READY',blocked_reason=None)
    try:
        schedule,results,sources,events=fetch_inputs(state,root)
        state['sources']=sources;state['schedule']=schedule;state['results']=results
        completed=completed_week(schedule,results)
        if completed>state['rankings'].get('completed_week',0):
            try:
                rankings,week,refs=build_next(state,schedule,results,root)
                # Replay does not mutate prior editions; one new next-week edition is installed.
                state['rankings']=rankings;state.setdefault('edition_sources',{})[rankings['edition']]=refs;state['sources']+=refs
                if completed<18:
                    state['current_week']=week['week'];state['weeks'].append(week)
                else:state['season_complete']=True
            except (ValueError,KeyError,OSError) as error:
                state.update(status='BLOCKED',blocked_reason='Waiting to publish the next week: '+str(error))
        try:state['sources']+=refresh_availability(state,root)
        except (ValueError,KeyError,OSError) as error:
            state.update(status='BLOCKED',blocked_reason='Availability refresh needs review: '+str(error))
        state['events']=events
        decorate(state,results)
    except (ValueError,KeyError,OSError) as error:
        state.update(status='BLOCKED',blocked_reason='Automatic update needs review: '+str(error))
        decorate(state,state['results'])
    state['checked_at']=now()
    if previous:
        old={g['game_id']:g for w in previous['weeks'] for g in w['games']}
        for week in state['weeks']:
            for index,g in enumerate(week['games']):
                before=old.get(g['game_id'])
                if before and utc(state['checked_at'])>=utc(g['kickoff'])-timedelta(minutes=60):
                    # Restore the whole issued record, including its explanations and source/QB identity.
                    week['games'][index]=copy.deepcopy(before)
        decorate(state,state['results'])
        pointer=read_json(root/'current.json')
        prior_manifest=read_json(root/pointer['path']/'manifest.json')
        prior_file=next(iter(prior_manifest['files']))
        state['archives']=[*previous.get('archives',[]),dict(checked_at=previous['checked_at'],href=archive_href(pointer['path']+'/'+prior_file))]
    state['source_captures']=[r for r in state['sources'] if 'path' in r]
    state['sources']=[r if 'href' in r else {'label':'Source captured '+r['captured_at'], 'href':archive_href(r['path'])} for r in state['sources']]
    state['sources'].append({'label':'Saved refreshes and verification record','href':'evidence/season-2026/current.json'})
    refresh_experiments(state, previous, root)
    save_state(state,root)
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    args=parser.parse_args()
    state=refresh(args.root) if args.refresh else load_current(args.root)
    print(json.dumps({k:state.get(k) for k in ('status','current_week','checked_at','blocked_reason','model_records')},indent=2))


if __name__=='__main__':main()
