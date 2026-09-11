"""Pinned historical outcome-range diagnostic; never emits public numerical bounds."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = {
    'margin': ('research/pgo_postseason_candidate/run-20260909-attempt01/matched-predictions.csv', '3df4dbf26743a3686b6253bb4eb578457d0e2629dde1f0218f215c462feea0cf'),
    'total': ('research/pgo_totals_candidate_20260910/attempt01/predictions.csv', 'f96c85bf348a7df7c88dc6288bc2d470c4270134505d5bb95ce84c2fc534fce8'),
}
EXPECTED = dict(zip(range(2018, 2026), [256, 256, 256, 272, 271, 272, 272, 272]))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError('timezone required')
    return stamp


def timing_reasons(row, later_issued_at=None):
    """Strict actual-time admission; never substitute historical event order."""
    names = ('issued_at', 'inputs_available_at', 'final_verified_at', 'kickoff')
    missing = [f'missing_{key}' for key in names if not row.get(key)]
    if missing:
        return missing
    try:
        issued, available, final, kickoff = (timestamp(row[key]) for key in names)
        later = timestamp(later_issued_at) if later_issued_at else None
    except (TypeError, ValueError):
        return ['invalid_timestamp']
    reasons = []
    if available > issued:
        reasons.append('input_after_issuance')
    if issued > kickoff - timedelta(minutes=60):
        reasons.append('issuance_after_cutoff')
    if final <= kickoff:
        reasons.append('final_not_after_kickoff')
    if later is not None and final >= later:
        reasons.append('final_not_available_before_later_issuance')
    return reasons


def radius(residuals):
    if len(residuals) < 500:
        return None
    if any(not math.isfinite(value) or value < 0 for value in residuals):
        raise ValueError('invalid residual')
    return sorted(residuals)[math.ceil((len(residuals) + 1) * 0.8) - 1]


def load_rows():
    sources = {}
    for kind, (name, digest) in SOURCES.items():
        path = ROOT / name
        if sha(path) != digest:
            raise ValueError(f'changed pinned input: {name}')
        manifest = json.loads((path.parent / 'manifest.json').read_text(encoding='utf-8-sig'))
        if manifest['files'][path.name]['sha256'] != digest:
            raise ValueError('parent manifest differs')
        with path.open(newline='', encoding='utf-8-sig') as handle:
            records = list(csv.DictReader(handle))
        indexed = {row['game_id']: row for row in records}
        if len(indexed) != len(records):
            raise ValueError('duplicate game ID')
        if Counter(int(row['season']) for row in records) != EXPECTED:
            raise ValueError('cohort mismatch')
        sources[kind] = indexed
    if sources['margin'].keys() != sources['total'].keys():
        raise ValueError('unmatched IDs')
    rows = []
    for game_id, margin in sources['margin'].items():
        total = sources['total'][game_id]
        kickoff = timestamp(margin['kickoff'])
        if any(margin[a] != total[b] for a, b in [('season', 'season'), ('week', 'week'), ('home_team', 'home'), ('away_team', 'away')]):
            raise ValueError('identity mismatch')
        if kickoff.date().isoformat() != total['gameday']:
            raise ValueError('date mismatch')
        for field in ('prior_history_through', 'current_history_through'):
            if total[field] and datetime.fromisoformat(total[field]).date() >= kickoff.date():
                raise ValueError('total history not before game day')
        row = dict(game_id=game_id, season=int(margin['season']), week=int(margin['week']), kickoff=margin['kickoff'])
        if not 1 <= row['week'] <= 18:
            raise ValueError('invalid regular-season week')
        for kind, source, prediction in [('margin', margin, 'candidate'), ('total', total, 'pfpa_prior')]:
            row[f'{kind}_prediction'] = float(source[prediction])
            row[f'{kind}_actual'] = float(source[f'actual_{kind}'])
            if any(not math.isfinite(row[f'{kind}_{key}']) for key in ('prediction', 'actual')):
                raise ValueError('nonfinite score')
        if row['total_actual'] < abs(row['margin_actual']):
            raise ValueError('inconsistent final scores')
        rows.append(row)
    return sorted(rows, key=lambda row: (timestamp(row['kickoff']), row['game_id']))


def evaluate(rows):
    if len({row['game_id'] for row in rows}) != len(rows):
        raise ValueError('duplicate game ID')
    predictions, folds = [], []
    for season in sorted({row['season'] for row in rows}):
        calibration = [row for row in rows if row['season'] < season]
        target = [row for row in rows if row['season'] == season]
        if len({row['season'] for row in calibration}) < 2 or len(calibration) < 500:
            folds.append(dict(season=season, calibration_n=len(calibration), target_n=len(target), status='calibration_only'))
            continue
        if max(timestamp(row['kickoff']) for row in calibration) >= min(timestamp(row['kickoff']) for row in target):
            raise ValueError('cross-season time overlap')
        radii = {kind: radius([abs(row[f'{kind}_actual'] - row[f'{kind}_prediction']) for row in calibration]) for kind in ('margin', 'total')}
        folds.append(dict(season=season, calibration_n=len(calibration), target_n=len(target), calibration_seasons=sorted({row['season'] for row in calibration}), calibration_last_kickoff=max(row['kickoff'] for row in calibration), test_first_kickoff=min(row['kickoff'] for row in target), radii=radii, status='diagnostic_only'))
        for row in target:
            result = dict(row)
            for kind, value in radii.items():
                result[f'{kind}_lower'] = row[f'{kind}_prediction'] - value
                result[f'{kind}_upper'] = row[f'{kind}_prediction'] + value
                result[f'{kind}_covered'] = result[f'{kind}_lower'] <= row[f'{kind}_actual'] <= result[f'{kind}_upper']
            predictions.append(result)
    metrics = []
    for season in [None] + sorted({row['season'] for row in predictions}):
        for label, predicate in [('all', lambda row: True), ('week1', lambda row: row['week'] == 1), ('weeks1_4', lambda row: row['week'] <= 4), ('weeks5_18', lambda row: row['week'] >= 5)]:
            cohort = [row for row in predictions if (season is None or row['season'] == season) and predicate(row)]
            for kind in ('margin', 'total'):
                n = len(cohort)
                metrics.append(dict(season=season or 'pooled', slice=label, target=kind, n=n, covered=sum(row[f'{kind}_covered'] for row in cohort), coverage=sum(row[f'{kind}_covered'] for row in cohort) / n if n else None, mean_width=sum(row[f'{kind}_upper'] - row[f'{kind}_lower'] for row in cohort) / n if n else None))
    return predictions, folds, metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    tracked = [HERE / 'charter.md', Path(__file__)]
    tracked += [ROOT / name for name, _ in SOURCES.values()]
    tracked += [(ROOT / name).parent / 'manifest.json' for name, _ in SOURCES.values()]
    before = {str(path.relative_to(ROOT)): sha(path) for path in tracked}
    def save(name, value):
        (args.output / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    save('run-start.json', dict(started_at=datetime.now().astimezone().isoformat(), hashes=before))
    try:
        rows = load_rows()
        predictions, folds, metrics = evaluate(rows)
        reasons = Counter(reason for row in rows for reason in timing_reasons(row))
        result = dict(public_status='UNAVAILABLE', scientific_status='EXPERIMENTAL / HOLD', leakage_verdict='REVIEW REQUIRED', input_n=len(rows), calibration_only_n=len(rows)-len(predictions), evaluated_n=len(predictions), prospective_admissible_n=sum(not timing_reasons(row) for row in rows), timing_exclusions=dict(reasons), folds=folds, metrics=metrics)
        save('metrics.json', result)
        with (args.output / 'ranges.csv').open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(predictions[0]))
            writer.writeheader()
            writer.writerows(predictions)
        after = {str(path.relative_to(ROOT)): sha(path) for path in tracked}
        if before != after:
            raise ValueError('source/code/charter changed during run')
        save('run-receipt.json', dict(status='completed_diagnostic_only', hashes_before=before, hashes_after=after))
        save('manifest.json', {'files': {path.name: {'sha256': sha(path), 'bytes': path.stat().st_size} for path in sorted(args.output.iterdir()) if path.is_file()}})
        print(json.dumps({key: value for key, value in result.items() if key not in ('folds', 'metrics')}, indent=2))
    except Exception as exc:
        save('failure.json', dict(error=type(exc).__name__, detail=str(exc)))
        raise


if __name__ == '__main__':
    main()
