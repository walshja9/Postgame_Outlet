"""Fixed prior/current-season total formulas. Importing performs no reads or fits."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
import io
from itertools import groupby
import json
import math
from pathlib import Path

from pgo_sources import CURRENT_TEAMS, normalize_team

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent
BASELINE = ROOT / 'research/pgo_postseason_candidate/run-20260909-attempt01'
BASELINE_SHA256 = 'a58aeff835471182a555e4b926beafd0db01c7c5e3fe19827ddf56bd03f2514a'
CHARTER_SHA256 = 'a28a582f09261da4fcaf609d23de9ce994b60a35e95602de3d10de24a0cd5af5'
SCORING = ROOT / 'docs/evidence/forecast-lab-2026/september-09-postseason/scoring-rates.json'
SCORING_SHA256 = '24ca1d9a41a6e4f0c37b1e1b6328726220806108c8d6d41900cb9cace1fe7d00'
IDENTITY = 'pgo-totals-candidate-2026-09-10'
MODELS = ('league_prior', 'pfpa_prior', 'shrink_4', 'shrink_8')
HISTORY_TYPES = frozenset(('REG', 'WC', 'DIV', 'CON', 'SB'))


def _require(value, message):
    if not value:
        raise ValueError(message)


def _integer(value, name):
    try:
        number = float(value)
    except (ValueError, TypeError) as error:
        raise ValueError('Missing or invalid ' + name) from error
    _require(not isinstance(value, bool) and math.isfinite(number) and number >= 0 and number.is_integer(),
             'Invalid ' + name)
    return int(number)


def _games(raw):
    games, seen, periods = [], set(), set()
    for row in raw:
        _require(row['game_type'] in HISTORY_TYPES, 'Unexpected history game type')
        home, away = (normalize_team(row[k]) for k in ('home_team', 'away_team'))
        day = date.fromisoformat(row['gameday']).isoformat()
        identity = row['game_id']
        season, week = _integer(row['season'], 'season'), _integer(row['week'], 'week')
        _require(identity and identity not in seen and home != away and home in CURRENT_TEAMS and away in CURRENT_TEAMS
                 and week > 0, 'Invalid or duplicate game identity')
        seen.add(identity)
        for team in (home, away):
            _require((day, team) not in periods, 'Duplicate team game-day identity')
            periods.add((day, team))
        games.append(dict(game_id=identity, season=season, week=week, gameday=day,
                          game_type=row['game_type'], home=home, away=away,
                          home_score=_integer(row['home_score'], 'home score'),
                          away_score=_integer(row['away_score'], 'away score')))
    return sorted(games, key=lambda g: (g['gameday'], g['game_id']))


def _rates(games):
    values = defaultdict(lambda: dict(pf=0., pa=0., games=0, postseason_games=0))
    _require(games, 'Missing prior-season scoring history')
    for game in games:
        for side, other in (('home', 'away'), ('away', 'home')):
            row = values[game[side]]
            row['pf'] += game[side + '_score']; row['pa'] += game[other + '_score']
            row['games'] += 1; row['postseason_games'] += game['game_type'] != 'REG'
    rates = {team: dict(row, pf=row['pf']/row['games'], pa=row['pa']/row['games']) for team, row in sorted(values.items())}
    league = math.fsum(g['home_score'] + g['away_score'] for g in games) / len(games)
    return rates, league


def predict(raw, seasons=range(2018, 2026)):
    """Read rates before each Eastern game-day batch; never update from that day."""
    games = _games(raw)
    by_season = defaultdict(list)
    for game in games:
        by_season[game['season']].append(game)
    predictions = []
    for season in seasons:
        prior_games, current_games = by_season[season - 1], by_season[season]
        prior, league = _rates(prior_games)
        prior_through = max(g['gameday'] for g in prior_games)
        _require(current_games and prior_through < current_games[0]['gameday'], 'Invalid prior-season chronology')
        current = defaultdict(lambda: dict(pf=0., pa=0., games=0))
        through = None
        for day, group in groupby(current_games, key=lambda g: g['gameday']):
            group = list(group)
            for game in group:
                if game['game_type'] != 'REG':
                    continue
                row = {k: game[k] for k in ('game_id', 'season', 'week', 'gameday', 'home', 'away')}
                row.update(actual_total=game['home_score'] + game['away_score'],
                           prior_history_through=prior_through, current_history_through=through,
                           league_prior=league)
                rates = {}
                for side in ('home', 'away'):
                    team = game[side]
                    _require(team in prior, 'Missing required prior team scoring history')
                    old, now = prior[team], current[team]
                    row[side + '_prior_games'] = old['games']
                    row[side + '_current_games'] = now['games']
                    for field in ('pf', 'pa'):
                        row[side + '_prior_' + field] = old[field]
                        row[side + '_current_' + field] = now[field]
                        rates[side, field, 0] = old[field]
                        for weight in (4, 8):
                            rates[side, field, weight] = (weight * old[field] + now[field]) / (weight + now['games'])
                for weight, name in ((0, 'pfpa_prior'), (4, 'shrink_4'), (8, 'shrink_8')):
                    row[name] = math.fsum(rates[side, field, weight] for side in ('home', 'away') for field in ('pf', 'pa')) / 2
                predictions.append(row)
            for game in group:
                for side, other in (('home', 'away'), ('away', 'home')):
                    current[game[side]]['pf'] += game[side + '_score']
                    current[game[side]]['pa'] += game[other + '_score']
                    current[game[side]]['games'] += 1
            through = day
    return sorted(predictions, key=lambda r: (r['gameday'], r['game_id']))


def _metrics(rows, name):
    errors = [r[name] - r['actual_total'] for r in rows]
    _require(errors, 'Empty metric cohort')
    return dict(games=len(errors), mae=math.fsum(map(abs, errors))/len(errors),
                rmse=math.sqrt(math.fsum(e*e for e in errors)/len(errors)),
                bias=math.fsum(errors)/len(errors))


def _interval(rows, candidate, baseline, cluster, samples):
    import numpy as np
    groups = defaultdict(list)
    for row in rows:
        key = row['season'] if cluster == 'season' else (row['season'], row['week'])
        groups[key].append(abs(row[baseline]-row['actual_total']) - abs(row[candidate]-row['actual_total']))
    values = [groups[key] for key in sorted(groups)]
    sums = np.array([math.fsum(v) for v in values]); counts = np.array([len(v) for v in values])
    rng = np.random.default_rng(20260910)
    draws = rng.multinomial(len(values), [1/len(values)]*len(values), size=samples)
    means = (draws @ sums) / (draws @ counts)
    return dict(cluster=cluster, clusters=len(values), samples=samples, seed=20260910,
                improvement=math.fsum(sums)/int(sum(counts)),
                lower=float(np.quantile(means, .025)), upper=float(np.quantile(means, .975)),
                lower_97_5=float(np.quantile(means, .0125)), upper_97_5=float(np.quantile(means, .9875)))


def evaluate(rows, samples=10000):
    views = dict(overall=rows, week_1=[r for r in rows if r['week'] == 1],
                 weeks_1_4=[r for r in rows if r['week'] <= 4], weeks_5_18=[r for r in rows if r['week'] >= 5])
    seasons = sorted({r['season'] for r in rows})
    views.update({str(s): [r for r in rows if r['season'] == s] for s in seasons})
    metrics = {label: {name: _metrics(part, name) for name in MODELS} for label, part in views.items() if part}
    paired, screens = {}, {}
    for candidate in ('shrink_4', 'shrink_8'):
        paired[candidate], checks, wins = {}, {}, {}
        for baseline in ('pfpa_prior', 'league_prior'):
            comparison = {cluster: _interval(rows, candidate, baseline, cluster, samples) for cluster in ('season', 'season_week')}
            paired[candidate]['vs_' + baseline] = comparison
            wins[baseline] = sum(metrics[str(s)][candidate]['mae'] < metrics[str(s)][baseline]['mae'] for s in seasons)
            checks[baseline] = dict(improvement_at_least_0_10=comparison['season']['improvement'] >= .10,
                                   at_least_five_seasons=wins[baseline] >= 5,
                                   positive_adjusted_interval=comparison['season']['lower_97_5'] > 0)
        passed = all(value for check in checks.values() for value in check.values())
        screens[candidate] = dict(status='PASS' if passed else 'FAIL', season_wins=wins, checks=checks)
    return dict(status='EXPERIMENTAL / HOLD', metrics=metrics, paired=paired, further_study_screen=screens)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def _pins():
    manifest_raw = (BASELINE/'manifest.json').read_bytes()
    _require(_sha(manifest_raw) == BASELINE_SHA256, 'Postseason manifest differs')
    for name, meta in json.loads(manifest_raw)['files'].items():
        _require(Path(name).name == name, 'Unsafe baseline member')
        raw = (BASELINE/name).read_bytes()
        _require(len(raw) == meta['bytes'] and _sha(raw) == meta['sha256'], 'Baseline member differs: ' + name)
    _require(_sha((DIRECTORY/'charter.md').read_bytes()) == CHARTER_SHA256, 'Totals charter differs')
    _require(_sha(SCORING.read_bytes()) == SCORING_SHA256, 'Current scoring-rate input differs')
    source = json.loads((BASELINE/'run-start.json').read_bytes())['sources']['schedule_results:None']
    path = Path(source['path'])
    _require(path.is_file() and path.stat().st_size == source['bytes'] and _sha(path.read_bytes()) == source['sha256'], 'Schedule bytes differ')
    files = [Path(__file__), DIRECTORY/'charter.md', ROOT/'tests/test_pgo_totals_candidate.py', ROOT/'pgo_sources.py']
    return dict(baseline_manifest_sha256=BASELINE_SHA256, scoring_sha256=SCORING_SHA256,
                source=source, code={str(p.relative_to(ROOT)): _sha(p.read_bytes()) for p in files})


def _protected():
    prefixes = ['docs/evidence/forecast-lab-2026', 'docs/evidence/nonqb-availability-2026',
                'docs/evidence/defensive-depth-2026', 'docs/evidence/penalty-model-2026',
                'research/pgo_nonqb_availability_20260909', 'research/pgo_defensive_depth_candidate',
                'research/pgo_postseason_candidate', 'research/pgo_penalty_candidate']
    return {str(p.relative_to(ROOT)): _sha(p.read_bytes()) for prefix in prefixes for p in (ROOT/prefix).rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def run(output):
    output = Path(output).resolve()
    _require(output.parent == DIRECTORY and not output.exists(), 'Use a new exclusive totals attempt directory')
    pins, protected = _pins(), _protected()
    start = dict(identity=IDENTITY, started_at=datetime.now(timezone.utc).isoformat(),
                 status='STARTED_INCOMPLETE', pins=pins, protected_before=protected)
    output.mkdir()
    (output/'run-start.json').write_bytes(_json(start))
    try:
        with Path(pins['source']['path']).open(newline='', encoding='utf-8-sig') as stream:
            raw = list(csv.DictReader(stream))
        selected = [r for r in raw if r['game_type'] in HISTORY_TYPES and 2013 <= int(r['season']) <= 2025]
        incomplete = [r['game_id'] for r in selected if not r['home_score'] or not r['away_score']]
        games = [r for r in selected if r['home_score'] and r['away_score']]
        _require(len(games) == 3562, 'Historical completed game inventory differs')
        rows = predict(games)
        with (BASELINE/'matched-predictions.csv').open(newline='') as stream:
            matched = {r['game_id']: r for r in csv.DictReader(stream)}
        _require(len(rows) == len(matched) == 2127 and {r['game_id'] for r in rows} == set(matched), 'Evaluation cohort differs')
        normalized = {g['game_id']: g for g in _games(games)}
        for row in rows:
            old = matched[row['game_id']]; game = normalized[row['game_id']]
            _require(row['season'] == int(old['season']) and row['week'] == int(old['week'])
                     and row['home'] == normalize_team(old['home_team']) and row['away'] == normalize_team(old['away_team'])
                     and row['gameday'] == old['kickoff'][:10]
                     and game['home_score'] - game['away_score'] == float(old['actual_margin']), 'Evaluation identity differs')
        _require([sum(r['season'] == s for r in rows) for s in range(2018, 2026)] == [256,256,256,272,271,272,272,272], 'Season counts differ')
        rates, league = _rates([g for g in normalized.values() if g['season'] == 2025])
        saved = json.loads(SCORING.read_bytes())
        _require(rates == saved['rates'] and league == saved['league_mean_total'], 'Original 2025 REG+POST scoring rule fails replay')
        # Falsification uses the same formulas, not a refit or a new candidate arm.
        pivot = '2024-10-06'
        perturbed = [dict(g, home_score='99', away_score='0') if g['gameday'] >= pivot else dict(g) for g in games]
        alternate = predict(perturbed)
        _require([(r['game_id'], [r[n] for n in MODELS]) for r in rows if r['gameday'] <= pivot] ==
                 [(r['game_id'], [r[n] for n in MODELS]) for r in alternate if r['gameday'] <= pivot], 'Future/current-day perturbation changed earlier predictions')
        result = evaluate(rows)
        result.update(identity=IDENTITY, generated_at=datetime.now(timezone.utc).isoformat(),
                      historical_source_vintage='REVIEW REQUIRED', fits=0,
                      coverage=dict(history_games=len(games), team_games=2*len(games), evaluated_games=len(rows),
                                    game_types=dict(Counter(g['game_type'] for g in games)), incomplete_game_ids=incomplete),
                      checks=dict(cohort_identity='PASS', current_2025_scoring_rule_replay='PASS', future_same_day_exclusion='PASS'))
        summary = dict(identity=IDENTITY, status='EXPERIMENTAL / HOLD', target='NFL game total points',
                       games=len(rows), metrics=result['metrics']['overall'],
                       further_study_screen=result['further_study_screen'], paired=result['paired'],
                       limitations=['Reused 2018-2025 seasons are diagnostic, not a fresh holdout.',
                                    'Historical publication timing remains REVIEW REQUIRED.',
                                    'No live totals, margins, probabilities or rankings changed.'],
                       prospective_recipe=dict(pseudo_games=[4,8], decision='Durably saved before T-60',
                                               history='Verified prior-day finals only', formal_review='After 2026 REG; at least 150 common pairs across 12 weeks',
                                               promotion='None; separate approval and evidence required'))
        _require(_pins() == pins and _protected() == protected, 'Source/code/prior evidence changed during attempt')
        receipt = dict(start, status='EXPERIMENTAL / HOLD', completed_at=datetime.now(timezone.utc).isoformat(),
                       protected_before_after='PASS', protected_file_count=len(protected), pins_before_after='PASS')
        stream = io.StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
        artifacts = {'predictions.csv': stream.getvalue().encode(), 'metrics.json': _json(result),
                     'public-summary.json': _json(summary), 'run-receipt.json': _json(receipt)}
        for name, value in artifacts.items():
            (output/name).write_bytes(value)
        members = {p.name: dict(sha256=_sha(p.read_bytes()), bytes=p.stat().st_size) for p in sorted(output.iterdir())}
        (output/'manifest.json').write_bytes(_json(dict(identity=IDENTITY, status='EXPERIMENTAL / HOLD', files=members)))
        return summary
    except Exception as error:
        (output/'failure.json').write_bytes(_json(dict(status='FAILED_PRESERVED', error=str(error), failed_at=datetime.now(timezone.utc).isoformat())))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
