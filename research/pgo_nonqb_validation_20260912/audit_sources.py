"""Pinned injury-source admission audit; no downloads, feature walks or fitting."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import pgo_challenger as ch
from research.pgo_opening_night_20260909.identity import source_package

PINS = {
    'charter.md': '0e8ec999e1eda5a0788232525306b0e95fbf188441222b149cc6d8659f36c163',
    'prior_receipt': 'c4431b8e391c4db30e0f63fcc4957bde2bafd25426a53dc3be86c3fa305352c9',
    'corrected_receipt': '8557f26bbe53992dec795ec6db696d6415ac7aee79ff3828dd6cee4a01b42dc7',
    'identity_manifest': '17f1dec348ad4992dbe32c6e5d54461ef8bd858e7e9d1775e37951385c492f2a',
    'diagnostic_manifest': 'f2ca127483327cfcb82ab20c5aabe88dbf0793f76a1303b43660133caf729abf',
    'original_STOP': 'c3f721962886ba77fd1ff8d45637508d2050fd294c0f3185dff77f3561a66a29',
}
TIMING = ('valid_timestamp', 'missing_date_modified', 'invalid_date_modified', 'at_or_after_T60', 'unmatched_game')
POPULATIONS = ('non_qb', 'qb', 'special_teams', 'unknown_position')


def require(value, message):
    if not value: raise ValueError(message)


def stamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'Modification time lacks timezone')
    return result.astimezone(timezone.utc)


def population(row):
    position = row.get('position', '').strip().upper()
    if position == 'QB': return 'qb'
    if position in {'K', 'P', 'LS'}: return 'special_teams'
    return 'non_qb' if ch.ROLE_POSITION_GROUPS.get(position) in {'skill', 'line', 'defense'} else 'unknown_position'


def period(row):
    return int(row['season']), int(row['week']), ch.normalize_team(row['team'])


def timing(row, games):
    kickoff = games.get(period(row))
    if kickoff is None: return 'unmatched_game'
    value = row.get('date_modified', '').strip()
    if not value: return 'missing_date_modified'
    try: modified = stamp(value)
    except (ValueError, TypeError, OverflowError): return 'invalid_date_modified'
    return 'at_or_after_T60' if modified >= kickoff-timedelta(minutes=60) else 'valid_timestamp'


def key_audit(rows):
    keys = defaultdict(list); versions = defaultdict(set); exact = Counter()
    for row in rows:
        key = (*period(row), row.get('gsis_id', '').strip())
        value = row.get('date_modified', '').strip()
        try: value = stamp(value).isoformat() if value else None
        except (ValueError, TypeError, OverflowError): pass
        signature = json.dumps({k:v for k,v in row.items() if k != 'date_modified'}, sort_keys=True)
        keys[key].append(value); versions[key, value].add(signature)
        exact[json.dumps(row, sort_keys=True)] += 1
    conflicts = [dict(season=key[0], week=key[1], team=key[2], gsis_id=key[3], date_modified=value)
                 for (key, value), signatures in versions.items() if len(signatures) > 1]
    return dict(duplicate_exact_rows=sum(count-1 for count in exact.values()),
                multiple_revision_keys=sum(len(values)>1 for values in keys.values()),
                conflicting_same_timestamp_keys=len(conflicts), conflicts=conflicts,
                missing_gsis_rows=sum(not row.get('gsis_id', '').strip() for row in rows))


def season_summary(season, rows, games):
    expected = {key for key in games if key[0] == season}; result = {}
    for group in POPULATIONS:
        selected = [row for row in rows if population(row) == group]
        counts = Counter(timing(row, games) for row in selected)
        seen = {period(row) for row in selected if period(row) in expected}
        timed = {period(row) for row in selected if timing(row, games) == 'valid_timestamp'}
        result[group] = dict(rows=len(selected), timing={key:counts[key] for key in TIMING},
            report_status_counts=dict(sorted(Counter(row.get('report_status', '').strip() or 'MISSING' for row in selected).items())),
            team_games_with_any_row=len(seen), team_games_with_timed_row=len(timed),
            team_games_without_any_row=len(expected-seen), team_games_without_timed_row=len(expected-timed),
            keys=key_audit(selected))
    return dict(season=season, regular_injury_rows=len(rows), non_qb_all_positions=sum(population(r)!='qb' for r in rows),
                expected_team_games=len(expected), populations=result,
                full_report_coverage='UNKNOWN: individual rows do not certify a complete team injury report')


def run(output):
    output = Path(output).resolve()
    require(output.parent == HERE and not output.exists(), 'Use a new exclusive report directory in this study')
    started = datetime.now(timezone.utc).isoformat(); inputs = {}

    def read(path, expected=None):
        path = Path(path).resolve(); raw = path.read_bytes()
        pin = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        if isinstance(expected, str): require(pin['sha256']==expected, 'Input hash differs: '+str(path))
        elif expected is not None: require(all(pin[key]==expected[key] for key in pin), 'Input bytes/hash differ: '+str(path))
        inputs[str(path)] = pin
        return raw

    code = read(Path(__file__)); charter = read(HERE/'charter.md', PINS['charter.md'])
    for path in (Path(ch.__file__), Path(source_package.__file__), Path(ch.open_csv.__code__.co_filename)):
        read(path)
    old_stop = json.loads(read(ROOT/'research/pgo_snap_identity_repair_20260909/source-conflict-inventory.json', PINS['original_STOP']))
    identity_path = ROOT/'research/pgo_opening_night_20260909/identity/package-complete-20260909/source-manifest.json'
    identity = json.loads(read(identity_path, PINS['identity_manifest']))
    qualified_paths = source_package.load_sources(identity_path, PINS['identity_manifest'])
    require(len(qualified_paths)==26, 'Qualified identity package is incomplete')
    for entry in [identity['qualification'], *identity['evidence'], *identity['sources']]:
        read(entry['path'], entry)
    qualification = json.loads(read(identity['qualification']['path'], identity['qualification']))
    prior = json.loads(read(ROOT/'research/pgo_current_strength/run-20260908/run-receipt.json', PINS['prior_receipt']))
    corrected = json.loads(read(ROOT/'research/pgo_week1_corrected/run-20260908/run-receipt.json', PINS['corrected_receipt']))
    sources = prior['source_inventory_before_after']; selected_sources = {}
    for name in ['schedule_results', *(f'injury_reports:{season}' for season in range(2013,2026))]:
        entry = sources[name]
        require(corrected['source_inventory'][name]=={k:entry[k] for k in ('bytes','sha256')}, 'Historical source selections differ')
        read(entry['path'], entry); selected_sources[name] = entry
    schedule = ch._load_games({('schedule_results', None): Path(sources['schedule_results']['path'])})
    require(len(schedule)==3407, 'Historical game cohort differs')
    games = {}
    for game in schedule:
        for side in ('home','away'):
            key = (game['season'],game['week'],game[side]); require(key not in games, 'Duplicate scheduled team/game')
            games[key] = game['kickoff_dt']
    seasons = []
    for season in range(2013,2026):
        rows = list(ch.open_csv(Path(sources[f'injury_reports:{season}']['path'])))
        require(all(int(row['season'])==season for row in rows), 'Injury source contains another season')
        regular = [row for row in rows if row['game_type']=='REG']
        summary = season_summary(season, regular, games)
        summary['other_game_type_rows'] = len(rows)-len(regular); seasons.append(summary)
    diagnostic = ROOT/'research/pgo_nonqb_availability_20260909/diagnostic-20260909'
    manifest = json.loads(read(diagnostic/'manifest.json', PINS['diagnostic_manifest']))
    for name, pin in manifest['files'].items():
        require(Path(name).name==name, 'Unsafe diagnostic member'); read(diagnostic/name, pin)
    metrics = json.loads((diagnostic/'metrics-receipt.json').read_bytes())
    predictions = list(csv.DictReader(io.StringIO((diagnostic/'predictions.csv').read_text(encoding='utf-8'))))
    require(len(predictions)==len({row['game_id'] for row in predictions})==2127, 'Saved diagnostic game count differs')
    for label, rows in [('overall',predictions), ('weeks_1_4',[r for r in predictions if int(r['week'])<=4]),
                        ('weeks_5_18',[r for r in predictions if int(r['week'])>=5])]:
        for arm in ('with_availability','zero_observed_availability'):
            errors = [float(row[arm])-float(row['actual_margin']) for row in rows]
            actual = dict(count=len(rows),mae=math.fsum(abs(e) for e in errors)/len(rows),rmse=math.sqrt(math.fsum(e*e for e in errors)/len(rows)))
            expected = metrics['slices'][label]['metrics'][arm]
            require(all(abs(actual[k]-expected[k])<1e-10 for k in actual), 'Saved diagnostic metrics differ')
    result = dict(status='BLOCKED FOR FITTING / SOURCE ADMISSION INCOMPLETE', historical_source_vintage='REVIEW REQUIRED',
        forecast_adjustment=None, model_fits=0, feature_walks=0, source_downloads=0, seasons=seasons,
        totals=dict(regular_injury_rows=sum(s['regular_injury_rows'] for s in seasons),
                    non_qb_all_positions=sum(s['non_qb_all_positions'] for s in seasons),
                    expected_team_games=len(games)),
        identity_qualification=dict(original_package_status=old_stop.get('status'), corrected_package_status=qualification['status'],
            scope=identity['scope'], corrected_roster_rows=qualification['corrected_roster_rows'],
            compared_REG_snap_rows=qualification['compared_REG_snap_rows'], remaining_conflicts=len(qualification['resolver_conflicts']),
            unresolved_REG_snap_rows=qualification['all_seasons']['new_unmatched_rows'],
            ambiguous_CIN_rows=qualification['CIN_ambiguous_rows_preserved'], historical_timing_qualified=False),
        prior_diagnostic=dict(games=2127,status=metrics['status'],aggregate_metrics_independently_recomputed=True,
            overall=metrics['slices']['overall'],seasons_with_positive_mae_gain=metrics['seasons_with_positive_mae_gain'],
            limits=metrics['limits']),
        source_selection=selected_sources,
        definitions=dict(non_qb='Offense/defense positions excluding QB, K, P and LS; unknown positions counted separately.',
            non_qb_all_positions='All rows except QB, including separately excluded special teams and unknown positions.',
            valid_timestamp='Nonmissing aware date_modified strictly before scheduled T-60; not proof of historical source publication.',
            timing_precedence='Unmatched scheduled game; missing clock; invalid clock; at or after T-60; valid timestamp.',
            coverage='A timed row establishes only that record. Missing team reports and completeness remain unknown.',
            key_conflict='Same season/week/team/GSIS and normalized modification clock with differing non-clock fields.'),
        limitations=['2025 injury rows have no modification timestamps and cannot be admitted by the strict timing rule.',
            'The earlier diagnostic includes QB losses and heuristic status probabilities; it does not isolate non-QB effects.',
            'Qualified identity corrections do not establish historical publication vintage or complete report coverage.',
            'A prior-usage-only diagnostic does not require historical depth; replacement-quality claims do.',
            'No newly isolated numerical candidate is fitted or accepted at this admission stage.'])
    for path, pin in list(inputs.items()): read(path, pin)
    receipt = dict(started_at=started, completed_at=datetime.now(timezone.utc).isoformat(), inputs=inputs,
        command='python -B research/pgo_nonqb_validation_20260912/audit_sources.py --output research/pgo_nonqb_validation_20260912/report01',
        source_and_code_hashes_unchanged=True, model_fits=0, feature_walks=0, source_downloads=0)
    artifacts = {'source-admission.json':(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n').encode(),
        'receipt.json':(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode(),
        'audit_sources.used.py.txt':code, 'charter.used.md':charter}
    output.mkdir(exist_ok=False)
    for name, raw in artifacts.items():
        with (output/name).open('xb') as handle: handle.write(raw)
    with (output/'manifest.json').open('xb') as handle:
        handle.write((json.dumps(dict(files={name:dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)) for name,raw in artifacts.items()}),indent=2,sort_keys=True)+'\n').encode())
    return dict(status=result['status'],output=str(output),totals=result['totals'],identity=result['identity_qualification'])


def self_check():
    require(not sys.flags.optimize, 'Run self-check without -O; assertions must remain enabled')
    kickoff = datetime(2026, 9, 13, 17, tzinfo=timezone.utc)
    games = {(2026, 1, 'NE'): kickoff}
    row = dict(season='2026', week='1', team='NE', gsis_id='00-0000001', position='LB', report_status='Out',
               date_modified='2026-09-13T16:00:00Z')
    assert population(row) == 'non_qb'
    assert population(dict(row, position='QB')) == 'qb'
    assert population(dict(row, position='K')) == 'special_teams'
    assert timing(dict(row, date_modified='2026-09-13T15:59:59Z'), games) == 'valid_timestamp'
    assert timing(row, games) == 'at_or_after_T60'
    assert timing(dict(row, date_modified='2026-09-13T16:00:01Z'), games) == 'at_or_after_T60'
    assert timing(dict(row, date_modified=''), games) == 'missing_date_modified'
    assert timing(dict(row, date_modified='2026-09-13T16:00:00'), games) == 'invalid_date_modified'
    assert timing(dict(row, team='SEA'), games) == 'unmatched_game'
    keys = key_audit([row, dict(row), dict(row, report_status='Questionable'),
                      dict(row, date_modified='2026-09-12T16:00:00Z')])
    assert keys['duplicate_exact_rows'] == 1
    assert keys['conflicting_same_timestamp_keys'] == 1
    assert keys['multiple_revision_keys'] == 1
    print('PASS: timing, missingness, population and duplicate/conflict self-checks')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        self_check()
    else:
        if args.output is None: parser.error('--output is required unless --self-check is used')
        print(json.dumps(run(args.output), indent=2))
