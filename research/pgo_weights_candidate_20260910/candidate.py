"""Fixed overlapping-input ablations and prior-OOF probability diagnostics."""
import argparse
import copy
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASELINE = ROOT/'research/pgo_postseason_candidate/run-20260909-attempt01'
BASELINE_SHA = 'a58aeff835471182a555e4b926beafd0db01c7c5e3fe19827ddf56bd03f2514a'
CHARTER_SHA = 'ef1ef4e69db2edb48463b6a0c490ac1e32962bdc28fd27f9ef933f39021d86d5'
IDENTITY = 'pgo-weights-probabilities-2026-09-10'
DROPS = {
    'without_qb_passing': ('qb_ball_security', 'qb_cpoe', 'qb_current_minus_full', 'qb_epa_per_dropback', 'qb_sack_avoidance'),
    'without_team_passing': ('passing_epa_per_play_for', 'sack_avoidance_rate'),
}
ARMS = ('postseason', *DROPS)
CURVES = ('scalar', 'intercept')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')


def write_json(path, value):
    with Path(path).open('xb') as handle:
        handle.write(json_bytes(value))


def utc(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(value.tzinfo is not None, 'Timestamp lacks timezone')
    return value.astimezone(timezone.utc)


def verified(directory, digest):
    directory = Path(directory)
    require(sha(directory/'manifest.json') == digest, 'Manifest hash differs')
    manifest = json.loads((directory/'manifest.json').read_bytes())
    for name, meta in manifest['files'].items():
        require(Path(name).name == name and name not in ('.', '..'), 'Unsafe manifest member')
        path = directory/name
        require(path.is_file() and not path.is_symlink() and sha(path) == meta['sha256'] and path.stat().st_size == meta['bytes'],
                'Manifest member differs: '+name)
    return manifest


def drop_features(originals, arm):
    require(arm in DROPS, 'Unplanned feature arm')
    rows = copy.deepcopy(originals)
    for row, old in zip(rows, originals):
        require(set(DROPS[arm]) <= row['features'].keys(), 'Required ablation field missing')
        for key in DROPS[arm]: del row['features'][key]
        restored = copy.deepcopy(row)
        restored['features'].update({key:old['features'][key] for key in DROPS[arm]})
        require(restored == old, 'Surviving original field changed')
    return rows


def calibration_split(rows, season):
    require(len({r['game_id'] for r in rows}) == len(rows), 'Duplicate calibration game')
    train = [r for r in rows if r['season'] < season]
    test = [r for r in rows if r['season'] == season]
    require(len({r['season'] for r in train}) >= 2 and test, 'Insufficient calibration warmup or test rows')
    require(max(utc(r['kickoff']) for r in train) < min(utc(r['kickoff']) for r in test), 'Calibration time leakage')
    return train, test


def sigmoid(value):
    return 1/(1+math.exp(-value)) if value >= 0 else math.exp(value)/(1+math.exp(value))


def fit_calibration(rows, column, intercept):
    require(rows and type(intercept) is bool, 'Calibration needs rows and a fixed curve')
    require(all(type(r[column]) in (int, float) and math.isfinite(r[column]) and
                type(r['actual_margin']) in (int, float) and math.isfinite(r['actual_margin']) for r in rows),
            'Invalid calibration prediction or target')
    pairs = [(r[column], int(r['actual_margin'] > 0)) for r in rows if r['actual_margin'] != 0]
    require(pairs, 'No non-tie calibration games')
    # Conditional coordinate solves are monotone derivatives of the fixed convex
    # objective. Slope is projected onto [0, infinity); intercept is unconstrained.
    def root(derivative, constrained=False):
        if constrained and derivative(0) >= 0: return 0.
        low, high = (0., 1.) if constrained else (-1., 1.)
        while derivative(low) > 0: low *= 2
        while derivative(high) < 0: high *= 2
        for _ in range(100):
            middle = (low+high)/2
            if derivative(middle) < 0: low = middle
            else: high = middle
        return (low+high)/2
    a, b = 0., 0.
    for iteration in range(1000):
        a = root(lambda value:value+math.fsum(x*(sigmoid(b+value*x)-y) for x,y in pairs), True)
        if intercept:
            b = root(lambda value:value+math.fsum(sigmoid(value+a*x)-y for x,y in pairs))
        ga = a+math.fsum(x*(sigmoid(b+a*x)-y) for x,y in pairs)
        gb = b+math.fsum(sigmoid(b+a*x)-y for x,y in pairs) if intercept else 0.
        residual = max(abs(gb), abs(ga) if a > 0 else max(0., -ga))
        if residual < 1e-8: break
    require(residual < 1e-8, 'Calibration solver failed its gradient check')
    ties = sum(r['actual_margin'] == 0 for r in rows)
    return dict(curve='intercept' if intercept else 'scalar', slope=a, intercept=b,
                tie_probability=(ties+1)/(len(rows)+2), training_games=len(rows), training_ties=ties,
                l2=1., gradient_residual=residual, iterations=iteration+1)


def probabilities(margin, fitted):
    a,b,t = (fitted[key] for key in ('slope','intercept','tie_probability'))
    require(all(type(v) in (int,float) and math.isfinite(v) for v in (margin,a,b,t)) and a >= 0 and 0 < t < 1,
            'Invalid frozen calibration')
    home = sigmoid(b+a*margin)
    return [(1-t)*home, (1-t)*(1-home), t]


def losses(row, key):
    p = row[key]
    require(len(p) == 3 and all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 1 for v in p)
            and abs(math.fsum(p)-1) <= 1e-12, 'Invalid three-class probability')
    actual = row['actual_margin']; target = 0 if actual > 0 else 1 if actual < 0 else 2
    return -math.log(max(1e-15,p[target])), math.fsum((v-int(i == target))**2 for i,v in enumerate(p))


def probability_metrics(rows, key, margin_key):
    require(rows and len({r['game_id'] for r in rows}) == len(rows), 'Missing or duplicate probability rows')
    pairs = [losses(r,key) for r in rows]; bins = [[] for _ in range(10)]; disagreements = 0; no_pick = 0
    for row in rows:
        p = row[key]
        if p[0] == p[1]: no_pick += 1; continue
        selected = 0 if p[0] > p[1] else 1
        actual = row['actual_margin']; target = 0 if actual > 0 else 1 if actual < 0 else 2
        bins[min(9,int(p[selected]*10))].append((p[selected],int(selected == target)))
        margin = row.get(margin_key) if margin_key else None
        if margin is not None and margin != 0:
            disagreements += selected != (0 if margin > 0 else 1)
    return dict(count=len(rows), log_loss=math.fsum(v[0] for v in pairs)/len(rows),
                brier=math.fsum(v[1] for v in pairs)/len(rows), ties=sum(r['actual_margin'] == 0 for r in rows),
                favorite_disagreements=disagreements, no_probability_favorite=no_pick,
                reliability_bins=[dict(lower=i/10,upper=(i+1)/10,count=len(values),
                    mean_probability=math.fsum(p for p,_ in values)/len(values) if values else None,
                    observed_win_rate=sum(y for _,y in values)/len(values) if values else None) for i,values in enumerate(bins)])


def paired_interval(rows, candidate, control, samples=10000, seed=20260910):
    blocks = defaultdict(list)
    for r in rows: blocks[r['season']].append(r[control]-r[candidate])
    require(blocks and all(math.isfinite(v) for values in blocks.values() for v in values), 'Invalid paired losses')
    sums = np.array([math.fsum(blocks[s]) for s in sorted(blocks)])
    counts = np.array([len(blocks[s]) for s in sorted(blocks)])
    draw = np.random.default_rng(seed).integers(0,len(blocks),size=(samples,len(blocks)))
    distribution = sums[draw].sum(axis=1)/counts[draw].sum(axis=1)
    return dict(mean=float(sums.sum()/counts.sum()),lower=float(np.percentile(distribution,2.5)),
                upper=float(np.percentile(distribution,97.5)),blocks=len(blocks),samples=samples,seed=seed)


def pins():
    require(sha(HERE/'charter.md') == CHARTER_SHA, 'Locked weights charter differs')
    verified(BASELINE, BASELINE_SHA)
    code = ['research/pgo_weights_candidate_20260910/candidate.py','tests/test_pgo_weights_candidate.py',
            'research/pgo_weights_candidate_20260910/charter.md','research/pgo_penalty_candidate/candidate.py',
            'research/pgo_week1_corrected/train.py','research/pgo_input_audit/audit_model.py',
            'pgo_challenger.py','pgo_current_strength.py','pgo_opponent_evaluation.py',
            'pgo_strength_evaluation.py','pgo_forecast_snapshot.py','pgo_sources.py','pgo_model.py','pgo_prospective.py']
    return dict(code={p:sha(ROOT/p) for p in code}, baseline_manifest_sha256=BASELINE_SHA,
                charter_sha256=CHARTER_SHA, numpy_version=np.__version__)


def start(output, kind, **bindings):
    output = Path(output).resolve()
    require(output.parent == HERE and not output.exists(), 'Use a new exclusive weights run directory')
    receipt = dict(identity=IDENTITY,kind=kind,started_at=datetime.now(timezone.utc).isoformat(),pins=pins(),**bindings)
    receipt['protected'] = {p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'docs/evidence').rglob('*')
                            if p.is_file() and p.relative_to(ROOT).as_posix() != 'docs/evidence/season-2026/current.json'}
    output.mkdir()
    write_json(output/'run-start.json',receipt)
    return output, receipt


def finish(output, receipt, **results):
    require(receipt['pins'] == pins(), 'Fit code or source pins changed')
    require(all(sha(ROOT/name) == digest for name,digest in receipt['protected'].items()), 'Issued artifact changed')
    receipt = dict(receipt, finished_at=datetime.now(timezone.utc).isoformat(),status='COMPLETE / EXPERIMENTAL / HOLD',
                   historical_source_vintage='REVIEW REQUIRED',protected_before_after='PASS',**results)
    write_json(output/'run-receipt.json',receipt)
    files = {p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(output.iterdir()) if p.is_file()}
    write_json(output/'manifest.json',dict(identity=IDENTITY,files=files,**{k:receipt[k] for k in ('pins','status')}))
    return dict(path=output.relative_to(ROOT).as_posix(),manifest_sha256=sha(output/'manifest.json'),**results)


def prepare(output):
    from research.pgo_penalty_candidate.candidate import load_baseline
    output, receipt = start(output,'PREPARATION_NO_FITS')
    baseline = load_baseline()
    originals = baseline['originals']
    require(sha(BASELINE/'historical-features.json') == '5b0aa4ac3d06ff37314c71984003651434f0df1cb2f17c6a74e7b26c44f20365', 'Frozen design hash differs')
    with (output/'historical-features.json').open('xb') as handle: handle.write((BASELINE/'historical-features.json').read_bytes())
    coverage = {}
    for arm in DROPS:
        rows = drop_features(originals,arm)
        coverage[arm] = dict(rows=len(rows),dropped=list(DROPS[arm]),remaining_features=sorted(rows[0]['features']),
                            surviving_values_and_missingness='EXACT')
    write_json(output/'coverage.json',coverage)
    write_json(output/'baseline-replay.json',baseline['replay'])
    return finish(output,receipt,model_fits=0,calibration_fits=0,training_games=3407,evaluation_games=2127)


def _views(rows, key, margin_key):
    groups = dict(overall=rows,week1=[r for r in rows if r['week']==1],weeks1_4=[r for r in rows if r['week']<=4])
    result = {name:probability_metrics(values,key,margin_key) for name,values in groups.items()}
    result['seasons'] = {str(s):probability_metrics([r for r in rows if r['season']==s],key,margin_key)
                         for s in sorted({r['season'] for r in rows})}
    return result


def fit(output, prepared, digest):
    from research.pgo_penalty_candidate.candidate import load_baseline
    from research.pgo_week1_corrected import train as corrected
    audit = corrected.audit; prepared = Path(prepared).resolve()
    require(prepared.parent == HERE, 'Preparation must be local weights research')
    verified(prepared,digest)
    prior = json.loads((prepared/'run-receipt.json').read_bytes())
    require(prior['kind']=='PREPARATION_NO_FITS' and prior['pins']==pins(), 'Prepared code/source pins differ')
    output, receipt = start(output,'FIXED_DIAGNOSTIC_FITS',prepared_manifest_sha256=digest)
    baseline = load_baseline(); originals = baseline['originals']
    require((prepared/'historical-features.json').read_bytes() == (BASELINE/'historical-features.json').read_bytes(), 'Prepared design changed')
    matched = {key:dict(game_id=key,season=int(r['season']),week=int(r['week']),kickoff=r['kickoff'],
        home_team=r['home_team'],away_team=r['away_team'],neutral_site=r['neutral_site']=='True',
        actual_margin=float(r['actual_margin']),postseason=float(r['candidate'])) for key,r in baseline['matched'].items()}
    final_fits = {'postseason':json.loads((BASELINE/'final-fit.json').read_bytes())}
    folds = []; maximum = 0.; model_count = 0
    for arm in DROPS:
        rows = [audit.ch.FeatureRow(**r) for r in drop_features(originals,arm)]
        for season,training,testing in [*audit.base.expanding_folds(rows),(None,rows,[])]:
            if testing: require(max(utc(r.kickoff) for r in training) < min(utc(r.kickoff) for r in testing), 'Margin fold time leakage')
            pp, coefficients, mirrored = corrected.fit_combined(training); model_count += 1
            fitted = audit._fit_receipt(pp,coefficients,training,testing,4,name='active4_symmetric',fit_training=mirrored)
            fitted.update(arm=arm,evaluation_season=season,dropped_features=list(DROPS[arm]))
            probes = testing or training
            values = audit.base._predict_rows(probes,pp,coefficients)
            replayed = corrected.replay(probes,json.loads(json_bytes(fitted)))
            error = max(abs(a-b) for a,b in zip(values,replayed)); maximum = max(maximum,error)
            require(all(math.isfinite(v) for v in values+replayed) and error <= 1e-10, 'Serialized ablation replay differs')
            write_json(output/f'fit-{arm}-{season or "final"}.json',fitted)
            if season is None: final_fits[arm] = fitted
            else:
                folds.append(fitted)
                for row,value in zip(testing,values): matched[row.game_id][arm] = value
    rows = sorted(matched.values(),key=lambda r:(r['season'],r['week'],r['kickoff'],r['game_id']))
    require(len(rows)==2127 and all(all(arm in r for arm in ARMS) for r in rows), 'Incomplete common margin cohort')
    margin_metrics = {arm:audit.metric_views(rows,arm) for arm in ARMS}
    margin_intervals = {arm:audit.base.season_block_bootstrap(rows,arm,'postseason',samples=10000,seed=20260910) for arm in DROPS}
    margin_screens = {}
    for arm in DROPS:
        control = margin_metrics['postseason']; candidate = margin_metrics[arm]
        wins = sum(a['mae'] < b['mae'] for a,b in zip(candidate['seasons'],control['seasons']))
        checks = dict(mae_improvement_at_least_005=control['overall']['mae']-candidate['overall']['mae'] >= .05,
                      five_season_wins=wins>=5,positive_lower_bound=margin_intervals[arm]['lower']>0)
        margin_screens[arm] = dict(result='PASS' if all(checks.values()) else 'FAIL',checks=checks,season_wins=wins,promotion='HOLD')
    with (output/'matched-predictions.csv').open('xb') as handle: handle.write(audit.base._csv_bytes(rows))
    write_json(output/'final-fits.json',final_fits)
    write_json(output/'margin-metrics.json',dict(metrics=margin_metrics,paired_intervals=margin_intervals,screens=margin_screens))
    probability_rows = []; calibrations = []; final_calibrations = {}; calibration_count = 0
    keys = [f'{arm}_{curve}' for arm in ARMS for curve in CURVES]
    for season in [*range(2020,2026),None]:
        training,testing = calibration_split(rows,season) if season else (rows,[])
        counts = [sum((0 if r['actual_margin']>0 else 1 if r['actual_margin']<0 else 2)==i for r in training) for i in range(3)]
        constant = [(n+1)/(len(training)+3) for n in counts]
        fit_record = dict(evaluation_season=season,training_game_ids=[r['game_id'] for r in training],
                          validation_game_ids=[r['game_id'] for r in testing],constant=constant,curves={})
        for arm in ARMS:
            for curve in CURVES:
                key=f'{arm}_{curve}'; fitted=fit_calibration(training,arm,curve=='intercept'); calibration_count += 1
                fit_record['curves'][key]=fitted
        write_json(output/f'calibration-{season or "final"}.json',fit_record)
        calibrations.append(fit_record)
        if season is None: final_calibrations=fit_record; continue
        for old in testing:
            row = dict(old,constant=constant)
            for arm in ARMS:
                for curve in CURVES:
                    key=f'{arm}_{curve}'; fitted=fit_record['curves'][key]
                    row[key]=probabilities(old[arm],fitted)
                    require(row[key] == probabilities(old[arm],json.loads(json_bytes(fitted))), 'Calibration JSON replay differs')
            probability_rows.append(row)
    require(model_count==18 and calibration_count==42 and len(probability_rows)==1615, 'Fit or evaluation inventory differs')
    probability_metrics_all = {key:_views(probability_rows,key,key.rsplit('_',1)[0]) for key in keys}
    probability_metrics_all['constant'] = _views(probability_rows,'constant',None)
    comparisons = {}; probability_screens = {}
    for key in keys:
        if key=='postseason_scalar': continue
        pairs = [('postseason_scalar','vs_postseason_scalar')]
        if key.endswith('_intercept'): pairs.append((key.replace('_intercept','_scalar'),'vs_own_scalar'))
        for control,label in pairs:
            values = [dict(season=r['season'],candidate=losses(r,key)[0],control=losses(r,control)[0]) for r in probability_rows]
            interval=paired_interval(values,'candidate','control'); comparisons[f'{key}_{label}']=interval
            if label!='vs_postseason_scalar': continue
            cm,bm=probability_metrics_all[key],probability_metrics_all[control]
            wins=sum(cm['seasons'][str(s)]['log_loss']<bm['seasons'][str(s)]['log_loss'] for s in range(2020,2026))
            checks=dict(logloss_improvement_at_least_0005=bm['overall']['log_loss']-cm['overall']['log_loss']>=.005,
                        four_season_wins=wins>=4,positive_lower_bound=interval['lower']>0)
            probability_screens[key]=dict(result='PASS' if all(checks.values()) else 'FAIL',checks=checks,season_wins=wins,promotion='HOLD')
    write_json(output/'probability-predictions.json',probability_rows)
    write_json(output/'final-calibrations.json',final_calibrations)
    write_json(output/'probability-metrics.json',dict(metrics=probability_metrics_all,paired_intervals=comparisons,screens=probability_screens))
    verified(prepared,digest)
    return finish(output,receipt,model_fits=model_count,calibration_fits=calibration_count,evaluation_games=2127,
                  probability_evaluation_games=1615,maximum_serialized_replay_error=maximum,
                  baseline_replay=baseline['replay'],margin_screens=margin_screens,probability_screens=probability_screens)


def main():
    parser=argparse.ArgumentParser(description=__doc__); commands=parser.add_subparsers(dest='operation',required=True)
    pre=commands.add_parser('prepare'); pre.add_argument('--output',type=Path,required=True)
    run=commands.add_parser('fit'); run.add_argument('--output',type=Path,required=True)
    run.add_argument('--prepared',type=Path,required=True); run.add_argument('--manifest-sha256',required=True)
    args=parser.parse_args()
    result=prepare(args.output) if args.operation=='prepare' else fit(args.output,args.prepared,args.manifest_sha256)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
