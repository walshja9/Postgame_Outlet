"""Source-backed current forecasts kept outside immutable weekly issue records."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import re

import pgo_season as season
from pgo_season import identity, require, utc


POLICY = ('Current projection using the existing frozen PGO model and completed-week statistics. '
          'It is separately timestamped and never eligible for the locked record, ATS or confidence grading.')


def _games(state, checked_at):
    from pgo_expected_starters import CURRENT_CONFIG
    if not CURRENT_CONFIG.exists():
        return []
    require(not CURRENT_CONFIG.is_symlink(), 'Current starter configuration is a symlink')
    config = json.loads(CURRENT_CONFIG.read_bytes())
    require(type(config.get('schema_version')) is int and config['schema_version'] == 1
            and isinstance(config.get('announcements'), list), 'Invalid current starter configuration')
    keys = {row['game_id'] for row in config['announcements']}
    finals = {row['game_id'] for row in state.get('results', [])}
    completed = state['rankings']['completed_week']
    checked = utc(checked_at)
    return [game for week in state['weeks'] for game in week['games']
            if game['game_id'] in keys and game['game_id'] not in finals
            and game['week'] == completed+1
            and utc(game['lock_at']) <= checked <= utc(game['kickoff'])+timedelta(hours=6)]


def refresh(state, root):
    """Build only explicitly verified current starters; leave every issued week alone."""
    from pgo_expected_starters import apply_current
    from pgo_season_availability import capture_availability, UNAVAILABLE
    checked = season.now()
    refs = []
    try:
        games = _games(state, checked)
        state['current_projection_check'] = dict(status='IDLE', checked_at=checked, blocked_reason=None)
        if not games:
            return refs
        raw, roster_ref = season.fetch_source(season.URLS['roster'], root)
        roster = season.csv_rows(raw); refs.append(roster_ref)
        raw, depth_ref = season.fetch_source(season.URLS['depth'], root)
        depth = season.csv_rows(raw); refs.append(depth_ref)
        current_week = [game for game in state['schedule']
                        if game['week'] == state['rankings']['completed_week']+1
                        and game['game_id'] not in {row['game_id'] for row in state.get('results', [])}]
        selected, annotations = apply_current({}, roster, current_week, root, season.now(), depth=depth)
        verified = [game for game in games if annotations.get(game['game_id'])]
        require(len(verified) == len(games), 'Current starter authority is missing for an applicable game')
        refs += [row['source'] for rows in annotations.values() for row in rows]
        expected = {team:row['gsis_id'] for team, row in selected.items()}
        directory = Path(root)/'availability-v2'/utc(season.now()).strftime('%Y%m%dT%H%M%S%fZ')
        availability = capture_availability(verified, roster, expected, directory, purpose='context')
        retained = []
        for original in verified:
            key = original['game_id']; before = state.get('current_projections', {}).get(key)
            if not before:
                continue
            for team in (original['home'], original['away']):
                old = before.get('availability', {}).get('teams', {}).get(team, {})
                new = availability['games'][key]['teams'][team]
                changed_with_authority = old.get('expected_qb_gsis_id') != selected[team]['gsis_id'] and any(
                    row['team'] == team and row['gsis_id'] == selected[team]['gsis_id'] for row in annotations.get(key, []))
                if old.get('expected_qb_status') in UNAVAILABLE and not changed_with_authority and new['expected_qb_status'] not in UNAVAILABLE:
                    retained.append(key); break
        verified = [game for game in verified if game['game_id'] not in retained]
        hold = 'Latest reports do not resolve previously confirmed unavailable quarterbacks: ' + ', '.join(retained) if retained else None
        if not verified:
            state['current_projection_check'] = dict(status='BLOCKED', checked_at=season.now(), blocked_reason=hold,
                source_archive=directory.relative_to(root).as_posix())
            refs.append(dict(label='Latest current availability attempt; earlier unavailable evidence retained',
                href=season.archive_href(directory.relative_to(root).as_posix()+'/availability.json')))
            return refs
        rankings, week, model_refs = season.build_next(state, state['schedule'], state['results'], root,
            completed=state['rankings']['completed_week'], selected=selected, roster_sources=refs,
            captured_sources=refs, starter_announcements=annotations, current_projection=True)
        refs = model_refs
        built = {game['game_id']:game for game in week['games']}
        overlays = {}
        for original in verified:
            key = original['game_id']
            require(key in built, 'Current projection game was not built')
            game = copy.deepcopy(built[key])
            observation = copy.deepcopy(availability['games'][key])
            observation['source_archive'] = directory.relative_to(root).as_posix()
            confidence = game.get('confidence') or {}
            game.update(projection_kind='CURRENT', forecast_status='CURRENT',
                eligible_for_locked_record=False, after_lock=utc(game['issued_at']) >= utc(game['lock_at']),
                after_kickoff=utc(game['issued_at']) >= utc(game['kickoff']),
                confidence=None, grade='NOT_ELIGIBLE', result=None, availability=observation,
                rankings=copy.deepcopy(rankings), source_captures=copy.deepcopy(model_refs), policy=POLICY,
                model_inputs=dict(schedule=[copy.deepcopy(row) for row in state['schedule'] if row['week'] <= game['week']],
                    completed_results=[copy.deepcopy(row) for row in state['results'] if row['week'] <= rankings['completed_week']],
                    starter_announcements=copy.deepcopy(annotations), calibration=copy.deepcopy(state['calibration'])),
                probabilities=copy.deepcopy(confidence.get('probabilities')),
                win_probability=confidence.get('win_probability'))
            if observation.get('blocked_reason'):
                game.update(blocked_reason=observation['blocked_reason'], pick=None,
                            margin=None, total=None, home_points=None, away_points=None,
                            probabilities=None, win_probability=None)
            overlays[key] = game
        candidate = dict(state, checked_at=season.now(),
                         current_projections=dict(state.get('current_projections', {}), **overlays))
        validate(candidate, root)
        state['current_projections'] = candidate['current_projections']
        blocked = [game['blocked_reason'] for game in overlays.values() if game.get('blocked_reason')] + ([hold] if hold else [])
        state['current_projection_check'] = dict(status='BLOCKED' if blocked else 'READY',
            checked_at=season.now(), blocked_reason='; '.join(blocked) if blocked else None)
        refs.append(dict(label='Current projection official availability',
            href=season.archive_href(directory.relative_to(root).as_posix()+'/availability.json')))
    except (ValueError, KeyError, TypeError, AttributeError, OSError, OverflowError) as error:
        state['current_projection_check'] = dict(status='BLOCKED', checked_at=season.now(), blocked_reason=str(error))
    return refs


def validate(state, root, durable=None):
    """Replay overlay evidence and real clocks without treating it as a locked pick."""
    current = state.get('current_projections', {})
    require(isinstance(current, dict), 'Invalid current projections')
    if not current:
        return
    if durable is not None:
        require(utc(state['checked_at']) <= utc(durable), 'Current projection state follows durable write')
    from pgo_expected_starters import verify_current
    from pgo_season_availability import load_availability
    from pgo_season_rollover import source_bytes
    primary = {game['game_id']:game for week in state['weeks'] for game in week['games']}
    saved_availability = {}
    try:
        for key, game in current.items():
            require(key == game['game_id'] and key in primary and identity(primary[key], game),
                    'Current projection game identity differs')
            issued, inputs, cutoff = utc(game['issued_at']), utc(game['inputs_as_of']), utc(game['kickoff'])-timedelta(minutes=60)
            require(cutoff <= inputs <= issued <= utc(state['checked_at']) and utc(game['lock_at']) == cutoff,
                    'Current projection issue or input clock differs')
            durable_fields = {'durable_at', 'durable_after_lock', 'durable_after_kickoff'}
            present = durable_fields & set(game)
            require(not present or present == durable_fields, 'Incomplete current projection durable metadata')
            if durable is not None:
                require(present == durable_fields, 'Saved current projection lacks durable metadata')
            if present:
                saved = utc(game['durable_at'])
                require(issued <= saved and (durable is None or saved <= utc(durable))
                        and type(game['durable_after_lock']) is bool and game['durable_after_lock'] == (saved >= cutoff)
                        and type(game['durable_after_kickoff']) is bool and game['durable_after_kickoff'] == (saved >= utc(game['kickoff'])),
                        'Current projection durable clock or timing differs')
            require(game['projection_kind'] == 'CURRENT' and game['eligible_for_locked_record'] is False
                    and type(game['after_lock']) is bool and game['after_lock'] == (issued >= cutoff)
                    and type(game['after_kickoff']) is bool and game['after_kickoff'] == (issued >= utc(game['kickoff'])),
                    'Current projection eligibility or timing differs')
            require(game.get('confidence') is None and game['grade'] == 'NOT_ELIGIBLE'
                    and game.get('result') is None, 'Current projection cannot carry locked-record grades')
            rankings = game['rankings']
            require(rankings['generated_at'] == game['issued_at'] and rankings['inputs_as_of'] == game['inputs_as_of']
                    and rankings['edition'] == game['source_edition'] and rankings['completed_week'] == game['week']-1,
                    'Current projection model edition differs')
            require(game.get('starter_announcements'), 'Current projection lacks verified current starter authority')
            verify_current(game, game['starter_announcements'], root)
            for ref in [*game['source_captures'], *rankings.get('source_captures', [])]:
                require(utc(ref['captured_at']) <= inputs, 'Current projection source follows its inputs')
                source_bytes(root, ref, inputs.isoformat())
            observation = game['availability']; path = observation['source_archive']
            require(re.fullmatch(r'availability-v2/\d{8}T\d{12}Z', path) is not None,
                    'Invalid current projection availability archive path')
            if path not in saved_availability:
                saved_availability[path] = load_availability(Path(root)/path)
            capture = saved_availability[path]
            require(capture.get('purpose') == 'context' and capture['games'].get(key)
                    == {field:value for field,value in observation.items() if field != 'source_archive'}
                    and utc(observation['checked_at']) <= inputs,
                    'Current projection availability differs from archived evidence')
            _replay(state, game, root)
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError('Invalid current projection schema') from error



def _replay(state, game, root):
    """Reproduce both QB identities and all numbers from the saved model inputs."""
    from pgo_expected_starters import _announcement, select_player
    from pgo_forecast_corrected import _same
    from pgo_season_model import GAME_IDENTITY, build_week, load_seed
    from pgo_season_rollover import source_bytes
    from pgo_sources import CURRENT_TEAMS
    inputs = game['model_inputs']; completed = game['rankings']['completed_week']
    _same(game['source_captures'], game['rankings']['source_captures'], 'Current model source inventory')
    _same(inputs['calibration'], state['calibration'], 'Frozen current calibration')
    captures = {}
    for kind in (('team', 'player') if completed else ()) + ('roster', 'depth'):
        refs = [ref for ref in game['source_captures'] if ref.get('url') == season.URLS[kind]]
        require(len(refs) == 1, 'Current model source is missing or ambiguous: ' + kind)
        captures[kind] = season.csv_rows(source_bytes(root, refs[0], game['inputs_as_of']))
    schedule = {row['game_id']:row for row in inputs['schedule']}
    require(len(schedule) == len(inputs['schedule']), 'Duplicate current model schedule game')
    known_schedule = {row['game_id']:row for row in state['schedule'] if row['week'] <= game['week']}
    require(set(schedule) == set(known_schedule), 'Current model schedule inventory differs')
    for key, row in schedule.items():
        _same({field:row[field] for field in GAME_IDENTITY},
              {field:known_schedule[key][field] for field in GAME_IDENTITY}, 'Current model schedule identity')
    results = inputs['completed_results']; saved_results = {row['game_id']:row for row in state['results']}
    require(len({row['game_id'] for row in results}) == len(results), 'Duplicate current model result')
    require({row['game_id'] for row in results} == {key for key,row in saved_results.items() if row['week'] <= completed},
            'Current model completed-result inventory differs')
    completed_games = []
    for result in results:
        require(result['week'] <= completed and utc(result['finalized_at']) <= utc(game['inputs_as_of']),
                'Current model result is later than its completed-week inputs')
        _same(result, saved_results[result['game_id']], 'Current model accepted final')
        source = schedule[result['game_id']]
        require(result['home_team'] == source['home'] and result['away_team'] == source['away']
                and utc(result['kickoff']) == utc(source['kickoff']), 'Current model final identity differs')
        completed_games.append(dict(source, home_score=result['home_score'], away_score=result['away_score'],
                                    finalized_at=result['finalized_at']))
    annotations = inputs['starter_announcements']
    require(isinstance(annotations, dict) and annotations.get(game['game_id']) == game['starter_announcements'],
            'Current model starter inventory differs')
    selected = {}
    for key, rows in annotations.items():
        require(key in schedule and schedule[key]['week'] == game['week'] and isinstance(rows, list),
                'Current model starter game differs')
        for row in rows:
            require(row['source'] in game['source_captures'], 'Current model starter source is absent')
            decision = _announcement(schedule[key], row['source'], root, game['inputs_as_of'], purpose='current_projection')
            team = decision['team']
            require(team not in selected and all(row[field] == decision[field] for field in ('team','gsis_id','full_name')),
                    'Current model starter identity differs')
            selected[team] = select_player(captures['roster'], decision, schedule[key])
    remaining = set(CURRENT_TEAMS)-set(selected)
    if remaining:
        selected.update(season.select_roster(captures['roster'], captures['depth'], game['inputs_as_of'], teams=remaining))
    require(len({row['gsis_id'] for row in selected.values()}) == len(CURRENT_TEAMS),
            'Current model QB identities are duplicated')
    expected = {team:selected[team]['full_name'] for team in (game['home'],game['away'])}
    _same(game['expected_qbs'], expected, 'Current model expected quarterbacks')
    for team in expected:
        require(game['availability']['teams'][team]['expected_qb_gsis_id'] == selected[team]['gsis_id'],
                'Current availability quarterback differs from archived roster and depth')
    snapshot = season.initial_snapshot()
    output = build_week(load_seed(), snapshot['fit'], completed_games, captures.get('team', []),
        captures.get('player', []), selected, [schedule[game['game_id']]], season=season.SEASON,
        completed_week=completed, generated_at=game['issued_at'], inputs_as_of=game['inputs_as_of'],
        scoring_rates=snapshot['scoring_rates'], league_mean_total=snapshot['league_mean_total'], current_projection=True)
    expected_teams = output['teams']
    _same([{key:row[key] for key in expected_teams[0]} for row in game['rankings']['teams']],
          expected_teams, 'Current model rankings')
    history = max((row['kickoff'] for row in completed_games), default=snapshot['history']['through'])
    require(game['rankings']['history_through'] == history, 'Current model history cutoff differs')
    forecast = output['games'][0]
    _same(game['explanation'], forecast['explanation'], 'Current model explanation')
    require(game.get('blocked_reason') == game['availability'].get('blocked_reason'),
            'Current QB block differs from verified availability')
    if game.get('blocked_reason'):
        require(all(game.get(field) is None for field in ('margin','total','home_points','away_points','pick','probabilities','win_probability')),
                'Unavailable current quarterback cannot issue a score or pick')
    else:
        for field in ('margin','total','home_points','away_points'):
            _same(game[field], forecast[field], 'Current model ' + field)
        predicted = season.allocate_confidence([forecast], inputs['calibration'])[0]
        confidence = predicted.get('confidence') or {}
        _same(game.get('pick'), predicted.get('pick'), 'Current model winner')
        _same(game.get('probabilities'), confidence.get('probabilities'), 'Current model probabilities')
        _same(game.get('win_probability'), confidence.get('win_probability'), 'Current model win probability')



def stamp_durable(state, previous, durable):
    """Bind a new current record to observed fsync time before admitting its manifest."""
    fields = {'durable_at', 'durable_after_lock', 'durable_after_kickoff'}
    rewritten = False; saved = utc(durable)
    for key, game in state.get('current_projections', {}).items():
        before = (previous or {}).get('current_projections', {}).get(key)
        core = {field:value for field,value in game.items() if field not in fields}
        if before is not None and core == {field:value for field,value in before.items() if field not in fields}:
            require(all(game.get(field) == before.get(field) for field in fields),
                    'An existing current projection durable timestamp changed')
            continue
        require(utc(game['issued_at']) <= saved, 'Current projection issue follows durable write')
        flags = dict(durable_after_lock=saved >= utc(game['lock_at']),
                     durable_after_kickoff=saved >= utc(game['kickoff']))
        # Stamp once; rewrite again only if a final fsync crossed a timing boundary.
        if 'durable_at' not in game or any(game.get(field) != value for field,value in flags.items()):
            game.update(durable_at=durable, **flags); rewritten = True
    return rewritten
