import copy
import unittest
from research.pgo_score_ranges_20260911.experiment import evaluate, radius, timing_reasons


class ScoreRangesTests(unittest.TestCase):
    def rows(self):
        return [dict(game_id=f'{season}_{i}', season=season, week=1 if i < 40 else 5,
                     kickoff=f'{season}-09-01T12:00:00-04:00', margin_prediction=0,
                     margin_actual=i % 23, total_prediction=40, total_actual=40+i % 31)
                for season in range(2018, 2022) for i in range(256)]

    def test_finite_sample_order_and_minimum(self):
        self.assertIsNone(radius([1] * 499))
        self.assertEqual(radius(list(range(500))), 400)
        with self.assertRaises(ValueError):
            radius([float('nan')] * 500)

    def test_future_and_current_season_outcomes_do_not_change_bounds(self):
        rows = self.rows()
        original, folds, _ = evaluate(rows)
        changed = copy.deepcopy(rows)
        for row in changed:
            if row['season'] >= 2020:
                row['margin_actual'] += 10000
                row['total_actual'] += 10000
        altered, _, _ = evaluate(changed)
        old_bounds = [(r['margin_lower'], r['total_upper']) for r in original if r['season'] == 2020]
        new_bounds = [(r['margin_lower'], r['total_upper']) for r in altered if r['season'] == 2020]
        self.assertEqual(old_bounds, new_bounds)
        self.assertEqual(folds[2]['calibration_n'], 512)
        self.assertNotEqual(original[-1]['total_upper'], altered[-1]['total_upper'])

    def test_duplicates_and_time_overlap_rejected(self):
        rows = self.rows()
        with self.assertRaises(ValueError):
            evaluate(rows + [rows[0]])
        rows[0]['kickoff'] = '2022-09-01T12:00:00-04:00'
        with self.assertRaises(ValueError):
            evaluate(rows)

    def test_timestamp_missing_and_cutoff_boundaries(self):
        self.assertEqual(len(timing_reasons({})), 4)
        row = dict(issued_at='2026-09-10T19:00:00-04:00', inputs_available_at='2026-09-10T18:59:00-04:00', kickoff='2026-09-10T20:00:00-04:00', final_verified_at='2026-09-10T23:59:00-04:00')
        self.assertEqual(timing_reasons(row, '2026-09-11T00:00:00-04:00'), [])
        self.assertIn('final_not_available_before_later_issuance', timing_reasons(row, row['final_verified_at']))
        row['issued_at'] = '2026-09-10T19:00:01-04:00'
        self.assertIn('issuance_after_cutoff', timing_reasons(row))
        row['inputs_available_at'] = '2026-09-10T19:00:02-04:00'
        self.assertIn('input_after_issuance', timing_reasons(row))
        row['issued_at'] = '2026-09-10T19:00:00'
        self.assertEqual(timing_reasons(row), ['invalid_timestamp'])

    def test_inclusive_coverage_and_early_cohort_counts(self):
        rows = self.rows()
        for row in rows:
            row['margin_actual'] = 10
        predictions, _, metrics = evaluate(rows)
        self.assertTrue(all(row['margin_covered'] for row in predictions))
        early = next(m for m in metrics if m['season'] == 'pooled' and m['slice'] == 'weeks1_4' and m['target'] == 'margin')
        self.assertEqual(early['n'], 80)
        self.assertEqual(early['coverage'], 1)
        self.assertEqual(early['mean_width'], 20)


if __name__ == '__main__':
    unittest.main()
