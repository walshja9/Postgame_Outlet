"""Build and verify the separately identified September active-roster experiment.

No fetching, model fitting, historical rewriting, or automatic promotion.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile

import numpy as np
import pgo_challenger as challenger
import pgo_model
import pgo_prospective as prospective
import pgo_sources

ROOT = Path(__file__).resolve().parent
EDITION = 'pgo-active-roster-2026-09-07'
RECOVERED_FIT_SHA256 = '1b960834b33cdda08bf69b792fa24ee2bb57ff738b1153aa1c1d833914af2036'
PORTABLE_FIT_SHA256 = 'f24429f99f078d57b135881bf1c371bc158539d3ff945e4434dd3e02533136d4'
LEGACY_SHA256 = 'd6ebf73188c41046f945a54653bdb89eadc2dc18d917276a47c0166b9ada98e9'
ORIGINAL_RATINGS_SHA256 = '6f983ddbb8e79263d70043429639ee5aa4c092edb847c41248a089b7a1e5a335'
GAME_COLUMNS = ('game_id', 'season', 'week', 'kickoff', 'home', 'away', 'location',
                'margin', 'total', 'home_points', 'away_points', 'pgo_v0_margin',
                'legacy_margin', 'old_selector_margin')
TEAM_COLUMNS = ('rank', 'team', 'rating', 'qb_name', 'qb_gsis_id',
                'old_selector_qb_name', 'old_selector_rating', 'qb_policy_effect')


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(data):
    return (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def _csv(rows, columns):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def _verified(path, digest, size=None):
    raw = Path(path).read_bytes()
    if _hash(raw) != digest or (size is not None and len(raw) != size):
        raise ValueError(f'Input hash/size mismatch: {Path(path).name}')
    return raw


def expected_scores(total, margin):
    total, margin = float(total), float(margin)
    if not all(map(math.isfinite, (total, margin))) or total < abs(margin):
        raise ValueError('Total and margin must imply finite nonnegative scores')
    return (total + margin) / 2, (total - margin) / 2


def starter_states(states, metadata, starters):
    """Change only the candidate's QB policy; keep historical EPA values intact."""
    if set(states) != set(starters) or set(states) != set(metadata):
        raise ValueError('Starter/team coverage mismatch')
    output = deepcopy(states)
    for team, selected in starters.items():
        players = [p for p in metadata[team]['roster'].values()
                   if p['position'] == 'QB' and p['gsis_id'] == selected['gsis_id']]
        if selected['status'] != 'ACT' or len(players) != 1:
            raise ValueError(f'Expected QB1 is not a unique active roster QB: {team}')
        for view in output[team]:
            view.update({name: challenger._qb_feature(players[0], name)
                         for name in challenger.QB_FEATURES})
            view['qb_current_minus_full'] = 0.0
    return output


def _preprocessor(fit):
    p = fit['preprocessor']
    return challenger.Preprocessor(tuple(p['feature_names']), np.asarray(p['medians']),
                                  np.asarray(p['scales']), tuple(p['missing_features']))


def _score(features, fit):
    row = challenger.FeatureRow('', 2026, 0, '', 0.0, features, {})
    return float(challenger.predict(_preprocessor(fit).transform([row]), fit['coefficients'])[0])


def _neutral(features):
    return {**features, 'home_field': 0.0, 'rest_difference': 0.0}


def _margin(home, away, game, fit):
    matchup = {**game, 'neutral': game['location'] == 'Neutral'}
    return _score(challenger._matchup_features(home, away, matchup), fit)


def _scoring_rates(paths):
    points, allowed, counts, totals, seen = Counter(), Counter(), Counter(), [], set()
    for row in pgo_sources.open_csv(paths[('schedule_results', None)]):
        if row['season'] != '2025' or row['game_type'] != 'REG':
            continue
        if not row['home_score'] or not row['away_score']:
            raise ValueError('Incomplete 2025 scoring history')
        home, away = (pgo_sources.normalize_team(row[key]) for key in ('home_team', 'away_team'))
        if row['game_id'] in seen or home == away:
            raise ValueError('Duplicate or invalid scoring-history game')
        seen.add(row['game_id'])
        hs, aws = float(row['home_score']), float(row['away_score'])
        if min(hs, aws) < 0 or not all(map(math.isfinite, (hs, aws))):
            raise ValueError('Invalid scoring history')
        points[home] += hs; points[away] += aws
        allowed[home] += aws; allowed[away] += hs
        counts.update((home, away)); totals.append(hs + aws)
    if set(counts) != set(pgo_model.CURRENT_TEAMS) or set(counts.values()) != {17} or len(totals) != 272:
        raise ValueError('Scoring baseline requires the complete 2025 regular season')
    rates = {team: {'pf': points[team] / counts[team], 'pa': allowed[team] / counts[team],
                    'games': counts[team]} for team in sorted(counts)}
    return rates, sum(totals) / len(totals)


def validate_snapshot(data):
    """Recompute ratings, contributions, margins and scores from frozen inputs."""
    if data['schema_version'] != 1 or data['edition'] != EDITION:
        raise ValueError('Unknown forecast edition')
    if _hash(_json(data['fit'])) != PORTABLE_FIT_SHA256:
        raise ValueError('Snapshot is not using the recovered public fit')
    generated = prospective._parse_datetime(data['generated_at'])
    if any(prospective._parse_datetime(s['captured_at']) > generated for s in data['sources']):
        raise ValueError('Source captured after issuance')
    depth_capture = next(s['captured_at'] for s in data['sources'] if s['name'] == 'depth.csv.gz')
    if prospective._parse_datetime(data['depth_as_of']) > prospective._parse_datetime(depth_capture):
        raise ValueError('QB depth is later than its source capture')
    if any(prospective._parse_datetime(s['verified_at']) > generated for s in data['historical_sources']):
        raise ValueError('Historical inputs verified after issuance')
    prospective._verify_lock(data['lock'])
    if data['fit'] != data['lock']['model_state']['challenger']:
        raise ValueError('Snapshot fit differs from the locked fit')
    source_hashes = {s['name']: s['sha256'] for s in [*data['sources'], *data['historical_sources']]}
    if source_hashes != data['lock']['source_hashes']:
        raise ValueError('Snapshot sources differ from the locked inputs')
    if prospective._parse_datetime(data['lock']['as_of']) != generated:
        raise ValueError('Margin lock and score issuance differ')
    teams = {row['team']: row for row in data['teams']}
    if len(data['teams']) != 32 or set(teams) != set(pgo_model.CURRENT_TEAMS):
        raise ValueError('Exactly 32 unique teams are required')
    if len({row['qb_gsis_id'] for row in teams.values()}) != 32:
        raise ValueError('QB identity is shared across teams')
    center = sum(_score(_neutral(row['features']), data['fit']) for row in teams.values()) / 32
    old_center = sum(_score(_neutral(row['old_selector_features']), data['fit']) for row in teams.values()) / 32
    ordered = sorted(teams)
    pp = _preprocessor(data['fit'])
    matrix = pp.transform([challenger._neutral_feature_row(t, teams[t]['features'], pp) for t in ordered])
    contributions = (matrix - matrix.mean(axis=0)) * np.asarray(data['fit']['coefficients'])[1:]
    names = [*pp.feature_names, *(f'{name}_missing' for name in pp.missing_features)]
    for rank, row in enumerate(sorted(teams.values(), key=lambda r: (-r['rating'], r['team'])), 1):
        if row['rank'] != rank or not row['qb_name'] or not row['qb_gsis_id']:
            raise ValueError('Invalid rank or QB identity')
        rating = _score(_neutral(row['features']), data['fit']) - center
        if not math.isclose(rating, row['rating'], abs_tol=1e-9):
            raise ValueError('Rating does not reproduce from its features')
        expected = dict(zip(names, contributions[ordered.index(row['team'])]))
        if set(row['contributions']) != set(expected) or any(
                not math.isclose(row['contributions'][k], v, abs_tol=1e-9) for k, v in expected.items()):
            raise ValueError('Individual rating contributions do not reproduce')
        if not math.isclose(sum(row['contributions'].values()), rating, abs_tol=1e-9):
            raise ValueError('Rating contributions do not reconcile')
        old = _score(_neutral(row['old_selector_features']), data['fit'])
        if not math.isclose(row['old_selector_rating'], old - old_center, abs_tol=1e-9) or not math.isclose(
                row['qb_policy_effect'], rating + center - old, abs_tol=1e-9):
            raise ValueError('QB-policy sensitivity does not reproduce')
        chosen = data['starters'][row['team']]
        if chosen['gsis_id'] != row['qb_gsis_id'] or chosen['qb_name'] != row['qb_name'] or chosen['status'] != 'ACT':
            raise ValueError('Rating QB differs from the qualified starter')
    legacy = json.loads(_verified(ROOT / 'docs/evidence/forecast-lab-2026/prospective_lock.json', LEGACY_SHA256))
    legacy_games = {g['game_id']: g for g in legacy['games']}
    locked = {row['game_id']: row for row in data['lock']['games']}
    counts, weeks, identities = Counter(), set(), set()
    if len(data['games']) != 272 or len(locked) != 272:
        raise ValueError('Exactly 272 games are required')
    for game in data['games']:
        game_id = game['game_id']
        if game_id in identities or game_id not in locked:
            raise ValueError('Duplicate or unknown game identity')
        identities.add(game_id)
        if game['season'] != 2026 or game['game_type'] != 'REG' or not 1 <= game['week'] <= 18:
            raise ValueError('Invalid forecast season/week')
        if prospective._parse_datetime(game['kickoff']) <= generated:
            raise ValueError('Forecast issued at or after kickoff')
        if game['home'] == game['away'] or game['location'] not in {'Home', 'Neutral'}:
            raise ValueError('Invalid matchup or venue')
        for key in ('season', 'week', 'kickoff', 'home', 'away', 'game_type', 'location', 'home_rest', 'away_rest'):
            if game[key] != locked[game_id][key] or game[key] != legacy_games[game_id][key]:
                raise ValueError('Snapshot and margin lock identity differ')
        for team in (game['home'], game['away']):
            if team not in teams or (team, game['week']) in weeks:
                raise ValueError('Duplicate team/week or invalid team')
            weeks.add((team, game['week'])); counts[team] += 1
        margin = _margin(teams[game['home']]['features'], teams[game['away']]['features'], game, data['fit'])
        rates = data['scoring_rates']
        total = sum(rates[t][k] for t in (game['home'], game['away']) for k in ('pf', 'pa')) / 2
        home_points, away_points = expected_scores(total, margin)
        values = {'margin': margin, 'total': total, 'home_points': home_points, 'away_points': away_points,
                  'pgo_v0_margin': legacy_games[game_id]['pgo_v0_prediction'],
                  'legacy_margin': legacy_games[game_id]['candidate_prediction'],
                  'old_selector_margin': _margin(teams[game['home']]['old_selector_features'],
                                                teams[game['away']]['old_selector_features'], game, data['fit'])}
        if not math.isclose(margin, locked[game_id]['challenger_prediction'], abs_tol=1e-9):
            raise ValueError('Score margin differs from its canonical lock')
        for key, value in values.items():
            if not math.isfinite(float(game[key])) or not math.isclose(game[key], value, abs_tol=1e-9):
                raise ValueError(f'Forecast does not reproduce: {game_id} {key}')
    if set(counts.values()) != {17}:
        raise ValueError('Each team must have 17 forecasts')


def load_snapshot(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Snapshot directory cannot be a symlink')
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    if manifest['schema_version'] != 1 or manifest['edition'] != EDITION:
        raise ValueError('Invalid snapshot manifest')
    files = manifest['files']
    required = {'snapshot.json', 'forecasts.csv', 'ratings.csv', 'fit.json', 'source-manifest.json',
                'source-qualification.json', 'july-snapshot-states.json', 'original-july-ratings.csv', 'original-july-backtest.json',
                'scoring-history-2025.csv', 'roster.csv.gz', 'depth.csv.gz', 'schedule.csv.gz',
                *(f'{tag}-{kind}.json' for tag in ('rosters', 'depth_charts', 'schedules') for kind in ('release', 'timestamp'))}
    if not required <= set(files):
        raise ValueError('Snapshot files are incomplete')
    raw_files = {}
    for name, entry in files.items():
        if Path(name).name != name or '/' in name or '\\' in name or ':' in name or (directory / name).is_symlink():
            raise ValueError('Invalid snapshot artifact path')
        raw_files[name] = _verified(directory / name, entry['sha256'], entry['bytes'])
    data = json.loads(raw_files['snapshot.json'])
    validate_snapshot(data)
    if json.loads(raw_files['fit.json']) != data['fit']:
        raise ValueError('Fit artifact differs from the snapshot')
    if raw_files['forecasts.csv'] != _csv(data['games'], GAME_COLUMNS):
        raise ValueError('Forecast CSV differs from the snapshot')
    if raw_files['ratings.csv'] != _csv(data['teams'], TEAM_COLUMNS):
        raise ValueError('Rating CSV differs from the snapshot')
    provenance = json.loads(raw_files['source-manifest.json'])
    if data['lock']['source_lock_sha256'] != _hash(raw_files['source-manifest.json']):
        raise ValueError('Source manifest is not bound to the margin lock')
    if provenance['sources'] != data['sources'] or provenance['historical_sources'] != data['historical_sources']:
        raise ValueError('Portable provenance differs from the snapshot')
    for entry in data['sources']:
        if entry['name'] in raw_files and _hash(raw_files[entry['name']]) != entry['sha256']:
            raise ValueError('Public source bytes differ from the capture')
    qualified = json.loads(raw_files['source-qualification.json'])
    if qualified['status'] != 'PASS' or qualified['failed_checks'] or qualified['capture_manifest_sha256'] != provenance['original_capture_manifest_sha256']:
        raise ValueError('Qualification belongs to another source capture')
    roster = list(pgo_sources.open_csv(directory / 'roster.csv.gz'))
    depth = list(pgo_sources.open_csv(directory / 'depth.csv.gz'))
    latest = max(r['dt'] for r in depth)
    qb1s = [(pgo_sources.normalize_team(r['team']), r['gsis_id']) for r in depth
            if r['dt'] == latest and r['pos_abb'] == 'QB' and r['pos_rank'] == '1']
    if latest != data['depth_as_of'] or len(qb1s) != 32 or set(qb1s) != {
            (r['team'], r['qb_gsis_id']) for r in data['teams']}:
        raise ValueError('Starter assumptions differ from the raw depth chart')
    for row in data['teams']:
        for identity, name in ((row['qb_gsis_id'], row['qb_name']),
                               (row['old_selector_qb_gsis_id'], row['old_selector_qb_name'])):
            matches = [r for r in roster if pgo_sources.normalize_team(r['team']) == row['team']
                       and r['gsis_id'] == identity and r['position'] == 'QB' and r['status'] == 'ACT']
            if len(matches) != 1 or matches[0]['full_name'] != name:
                raise ValueError('QB identity/name differs from the raw active roster')
    rates, league_total = _scoring_rates({('schedule_results', None): directory / 'scoring-history-2025.csv'})
    if rates != data['scoring_rates'] or league_total != data['league_mean_total']:
        raise ValueError('Total-scoring inputs do not reproduce')
    july = json.loads(raw_files['july-snapshot-states.json'])
    july_ratings = challenger.build_ratings(july['states'], np.asarray(data['fit']['coefficients']),
                                           _preprocessor(data['fit']), '2026-07-21T12:00:00-04:00')
    if _hash(raw_files['original-july-ratings.csv']) != ORIGINAL_RATINGS_SHA256:
        raise ValueError('Original July ratings hash differs')
    original = raw_files['original-july-ratings.csv'].decode().replace('\r\n', '\n')
    backtest = json.loads(_verified(directory / 'original-july-backtest.json',
        'ab32daa4cb3de5f6f5004a538edab9f145e8dbd3d7bcfb4b3fd069af7c05d9da'))
    if challenger._rating_csv(july_ratings, backtest).replace('\r\n', '\n') != original:
        raise ValueError('Portable fit does not reproduce every July CSV cell')
    return data


def build_snapshot(recovered_fit, capture_dir, qualification_path, output):
    output, capture_dir = Path(output).resolve(), Path(capture_dir).resolve()
    if output.exists() or output == capture_dir or output in capture_dir.parents:
        raise ValueError('New snapshot output must be an unused separate directory')
    code_hashes = {name: _hash((ROOT / name).read_bytes().replace(b'\r\n', b'\n')) for name in
                   ('pgo_forecast_snapshot.py', 'pgo_challenger.py', 'pgo_prospective.py', 'pgo_sources.py', 'pgo_model.py')}
    fit_raw = _verified(recovered_fit, RECOVERED_FIT_SHA256)
    recovered = json.loads(fit_raw)
    capture_raw = (capture_dir / 'capture.json').read_bytes()
    capture = json.loads(capture_raw)
    qualification = json.loads(Path(qualification_path).read_bytes())
    if qualification['status'] != 'PASS' or qualification['failed_checks'] or qualification['capture_manifest_sha256'] != _hash(capture_raw):
        raise ValueError('Source qualification is not bound to this capture')
    for entry in capture['sources']:
        if Path(entry['file']).name != entry['file']:
            raise ValueError('Invalid captured source path')
        _verified(capture_dir / entry['file'], entry['sha256'], entry['bytes'])
    paths = {}
    for entry in recovered['original_raw_sources']:
        _verified(entry['path'], entry['sha256'], entry['bytes'])
        name, _, season = entry['source'].partition(':')
        paths[(name, int(season) if season else None)] = Path(entry['path'])
    fit = {key: recovered[key] for key in ('identity', 'parameters', 'preprocessor', 'coefficients',
                                         'historical_code_revision', 'historical_code_sha256', 'training',
                                         'published_csv_reproduced')}
    fit['recovered_artifact_sha256'] = _hash(fit_raw)
    schedule_raw = list(pgo_sources.open_csv(capture_dir / 'schedule.csv.gz'))
    schedule = [prospective._normalize_row(row) for row in schedule_raw
                if row['season'] == '2026' and row['game_type'] == 'REG']
    if len(schedule) != 272 or any(row['home_score'] or row['away_score'] for row in schedule):
        raise ValueError('Fresh preseason schedule must contain 272 unplayed games')
    roster_all = list(pgo_sources.open_csv(capture_dir / 'roster.csv.gz'))
    roster = [row for row in roster_all if row['status'] == 'ACT']
    if any(row['season'] != '2026' or row['week'] != '1' for row in roster):
        raise ValueError('Current roster is outside the preseason Week 1 boundary')
    starters = {r['team']: {'gsis_id': r['gsis_id'], 'status': r['roster_status'], 'qb_name': r['player_name']}
                for r in qualification['chosen_qbs'] if r['depth_rank'] == 1}
    if len(starters) != 32 or len(qualification['chosen_qbs']) != 32:
        raise ValueError('Exactly 32 qualified QB1s are required')
    depth = list(pgo_sources.open_csv(capture_dir / 'depth.csv.gz'))
    latest = max(row['dt'] for row in depth)
    raw_starters = [(pgo_sources.normalize_team(r['team']), r['gsis_id']) for r in depth
                    if r['dt'] == latest and r['pos_abb'] == 'QB' and r['pos_rank'] == '1']
    if len(raw_starters) != 32 or set(raw_starters) != {(t, r['gsis_id']) for t, r in starters.items()}:
        raise ValueError('Qualified QB1s disagree with the latest raw depth snapshot')
    # The ACT-only inference roster is temporary; original raw sources stay unchanged.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pgo-roster-', dir=output.parent) as folder:
        temporary = Path(folder).resolve()
        if output.parent not in temporary.parents:
            raise ValueError('Temporary roster path escaped the output workspace')
        roster_path = temporary / 'active-roster.csv'
        roster_path.write_bytes(_csv(roster, tuple(roster[0])))
        paths[('current_roster', 2026)] = roster_path
        _, context, inputs = challenger._walk(paths, fit['parameters']['half_life_games'])
        as_of = datetime.now(timezone.utc).isoformat()
        old_states, metadata = prospective._snapshot_states_with_schedule(
            paths, schedule, as_of, fit['parameters']['half_life_games'], context, inputs)
        states = starter_states(old_states, metadata, starters)
    rates, league_total = _scoring_rates(paths)
    pp = _preprocessor(fit)
    model = np.asarray(fit['coefficients'])
    ratings = challenger.build_ratings(states, model, pp, as_of)
    old_ratings = {r['team']: r for r in challenger.build_ratings(old_states, model, pp, as_of)}
    ordered = sorted(states)
    matrix = pp.transform([challenger._neutral_feature_row(t, states[t][0], pp) for t in ordered])
    centered_contributions = (matrix - matrix.mean(axis=0)) * model[1:]
    feature_names = [*pp.feature_names, *(f'{name}_missing' for name in pp.missing_features)]
    name_map = {(pgo_sources.normalize_team(r['team']), r['gsis_id']): r['full_name'] for r in roster}
    teams = []
    for rating in ratings:
        team = rating['team']
        old_qb = metadata[team]['roster'][metadata[team]['starter']]['gsis_id']
        teams.append(dict(rank=rating['rank'], team=team, rating=rating['full_strength_rating'],
                          qb_name=starters[team]['qb_name'], qb_gsis_id=starters[team]['gsis_id'],
                          old_selector_qb_name=name_map[(team, old_qb)],
                          old_selector_qb_gsis_id=old_qb, old_selector_features=old_states[team][0],
                          old_selector_rating=old_ratings[team]['full_strength_rating'],
                          qb_policy_effect=_score(_neutral(states[team][0]), fit) - _score(_neutral(old_states[team][0]), fit),
                          features=states[team][0],
                          contributions=dict(zip(feature_names, centered_contributions[ordered.index(team)].tolist()))))
    legacy_path = ROOT / 'docs/evidence/forecast-lab-2026/prospective_lock.json'
    legacy = json.loads(_verified(legacy_path, LEGACY_SHA256))
    prospective._verify_lock(legacy)
    legacy_games = {g['game_id']: g for g in legacy['games']}
    v0 = legacy['model_state']['pgo_v0']
    games, predictions = [], {}
    for row in schedule:
        game = {k: row[k] for k in ('game_id', 'season', 'week', 'kickoff', 'game_type', 'location', 'home_rest', 'away_rest')}
        game.update(home=row['home_team'], away=row['away_team'])
        old_game = legacy_games[game['game_id']]
        if any(game[k] != old_game[k] for k in game):
            raise ValueError('Fresh/archived schedule identity differs; comparison needs review')
        margin = _margin(states[game['home']][0], states[game['away']][0], game, fit)
        total = sum(rates[t][k] for t in (game['home'], game['away']) for k in ('pf', 'pa')) / 2
        hp, ap = expected_scores(total, margin)
        v0_margin = v0['ratings'][game['home']] - v0['ratings'][game['away']]
        v0_margin += 0 if game['location'] == 'Neutral' else v0['parameters']['home_field']
        game.update(margin=margin, total=total, home_points=hp, away_points=ap,
                    pgo_v0_margin=v0_margin, legacy_margin=old_game['candidate_prediction'],
                    old_selector_margin=_margin(old_states[game['home']][0], old_states[game['away']][0], game, fit))
        games.append(game)
        predictions[game['game_id']] = dict(pgo_v0_prediction=v0_margin, challenger_prediction=margin,
                                            challenger_full_strength_prediction=margin, subgroup_flags={})
    games.sort(key=lambda g: (g['kickoff'], g['game_id']))
    sources = [dict(name=s['file'], url=s['url'], sha256=s['sha256'], bytes=s['bytes'], captured_at=s['captured_at'])
               for s in capture['sources']]
    historical_manifest = json.loads((ROOT / 'research/pgo_v1/sources.lock.json').read_bytes())
    historical_sources = [dict(name=e['name'] + (f":{e['season']}" if e['season'] else ''),
                               url=e['url'], sha256=e['sha256'], bytes=e['bytes'],
                               reported_frozen_at=e['frozen_at'], verified_at=recovered['recovery_generated_at'])
                          for e in historical_manifest['sources'] if e['name'] != 'current_roster']
    generated = datetime.now(timezone.utc).isoformat()
    source_manifest = dict(schema_version=1, sources=sources, historical_sources=historical_sources,
                           original_capture_manifest_sha256=_hash(capture_raw),
                           portability='Stable-URL derivative of the original capture. Provider raw files and metadata are included. The NFL HTML is retained locally; its digest and the extracted 16-game reconciliation are published, not the full webpage. Historical capture times are reported values, not verified original acquisition times.')
    source_hashes = {s['name']: s['sha256'] for s in [*sources, *historical_sources]}
    state = dict(challenger=fit, pgo_v0=v0, predictions=predictions,
                 source_hashes=source_hashes, source_lock_sha256=_hash(_json(source_manifest)))
    lock = prospective.lock_games({'rows': schedule, 'sha256': source_hashes['schedule.csv.gz']}, state, generated)
    data = dict(schema_version=1, edition=EDITION, generated_at=generated, depth_as_of=latest,
                fit=fit, teams=teams, games=games, lock=lock, sources=sources, historical_sources=historical_sources, scoring_rates=rates, starters=starters,
                league_mean_total=league_total, roster_status_counts=dict(Counter(r['status'] for r in roster_all)),
                legacy_lock_sha256=LEGACY_SHA256, inference_code_sha256=code_hashes,
                inference_code_hash_format='UTF-8 source with LF line endings',
                method=dict(name='Active-roster preseason scenario', status='EXPERIMENTAL — HOLD',
                            roster_policy='Only ACT roster entries; the latest verified active QB1 is selected by depth order. The same roster and QB assumptions apply to every week.',
                            injury_coverage='ACT is administrative status, not proof of health or game-day availability. No comprehensive practice, injury, or game-day inactive adjustment is included.',
                            history='Team and QB performance through the 2025 regular season. The historical fit and selected parameters are fixed. The embedded results-rating offseason convention is preserved.',
                            totals='Total = (home 2025 points for/game + home points allowed/game + away points for/game + away points allowed/game) / 2. Expected scores = (total ± home margin) / 2. Whole scores are presentation rounding.',
                            fit_recovery='The exact July public fit was reconstructed and reproduced every saved field for all 32 teams. This active-roster / expected-starter inference policy is a separate, unvalidated candidate.',
                            evaluation='Primary: margin MAE. Also track margin RMSE, total MAE, per-team score MAE and winner accuracy. No calibrated win probabilities or automatic promotion.',
                            schedule='Week 1 was independently checked against NFL.com. Later kickoffs are provider-listed and may change; Week 18 times are provisional.'))
    validate_snapshot(data)
    outputs = {'snapshot.json': _json(data), 'fit.json': _json(fit),
               'forecasts.csv': _csv(games, GAME_COLUMNS), 'ratings.csv': _csv(teams, TEAM_COLUMNS),
               'source-manifest.json': _json(source_manifest),
               'july-snapshot-states.json': Path(recovered_fit).with_name('july-snapshot-states.json').read_bytes(),
               'original-july-ratings.csv': (ROOT / 'research/pgo_v1/ratings_2026_preseason.csv').read_bytes(),
               'original-july-backtest.json': _verified(ROOT / 'research/pgo_v1/backtest.json',
                    'ab32daa4cb3de5f6f5004a538edab9f145e8dbd3d7bcfb4b3fd069af7c05d9da'),
               'scoring-history-2025.csv': _csv([r for r in pgo_sources.open_csv(paths[('schedule_results', None)])
                                               if r['season'] == '2025' and r['game_type'] == 'REG'],
                                              ('game_id', 'season', 'game_type', 'home_team', 'away_team', 'home_score', 'away_score')),
               'source-qualification.json': _json({k: v for k, v in qualification.items() if k != 'source_directory'})}
    for source in sources:
        if source['name'] != 'nfl-week-1.html':
            outputs[source['name']] = (capture_dir / source['name']).read_bytes()
    outputs['manifest.json'] = _json(dict(schema_version=1, edition=EDITION, generated_at=generated,
        files={name: dict(sha256=_hash(raw), bytes=len(raw)) for name, raw in outputs.items()}))
    # Binary source files use native exclusive creation; the manifest is last.
    # A failed partial capture is preserved and cannot be mistaken for a complete edition.
    output.mkdir()
    for name, raw in outputs.items():
        with (output / name).open('xb') as handle:
            handle.write(raw)
    return load_snapshot(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--recovered-fit', type=Path)
    parser.add_argument('--capture-dir', type=Path)
    parser.add_argument('--qualification', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        data = load_snapshot(args.verify)
    else:
        if not all((args.recovered_fit, args.capture_dir, args.qualification, args.output)):
            parser.error('Build requires --recovered-fit, --capture-dir, --qualification and --output')
        data = build_snapshot(args.recovered_fit, args.capture_dir, args.qualification, args.output)
    print(f"Verified {data['edition']}: {len(data['teams'])} teams, {len(data['games'])} games; {data['generated_at']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
