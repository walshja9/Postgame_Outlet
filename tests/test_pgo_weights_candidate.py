import copy
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path


class WeightsCandidateTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('research.pgo_weights_candidate_20260910.candidate'),
                             'Bounded weights/probability runner is missing')
        from research.pgo_weights_candidate_20260910 import candidate
        return candidate

    def rows(self):
        return [dict(game_id=f'{season}_{i}', season=season, week=i+1,
            kickoff=f'{season}-09-{i+1:02}T20:00:00Z', actual_margin=actual,
            postseason=margin) for season in range(2018, 2022)
            for i, (actual, margin) in enumerate([(3, 2), (-7, -3), (0, 1), (8, 4)])]

    def test_fixed_drops_preserve_every_other_original_value_and_missingness(self):
        api = self.api()
        raw = [dict(game_id='a', actual_margin=3, features={name:None for name in
            set().union(*api.DROPS.values()) | {'defense_availability','qb_log_dropbacks'}})]
        before = copy.deepcopy(raw)
        for arm, dropped in api.DROPS.items():
            out = api.drop_features(raw, arm)
            self.assertEqual(set(raw[0]['features'])-set(out[0]['features']), set(dropped))
            self.assertEqual(out[0]['features']['defense_availability'], None)
            check = copy.deepcopy(out[0]); check['features'].update({name:raw[0]['features'][name] for name in dropped})
            self.assertEqual(check, raw[0])
        self.assertEqual(raw, before)
        with self.assertRaises(ValueError): api.drop_features(raw, 'unplanned')
        with self.assertRaises(ValueError): api.drop_features([dict(raw[0], features={})], 'without_qb_passing')

    def test_calibration_uses_only_earlier_oof_seasons(self):
        api = self.api(); rows = self.rows()
        train, test = api.calibration_split(rows, 2020)
        self.assertEqual(len(train), 8); self.assertEqual(len(test), 4)
        first = api.fit_calibration(train, 'postseason', True)
        changed = copy.deepcopy(rows)
        for row in changed:
            if row['season'] >= 2020: row['actual_margin'] = -1000; row['postseason'] = 1000
        second = api.fit_calibration(api.calibration_split(changed, 2020)[0], 'postseason', True)
        self.assertEqual(first, second)
        changed = copy.deepcopy(rows); changed[0]['kickoff'] = '2020-10-01T00:00:00Z'
        with self.assertRaises(ValueError): api.calibration_split(changed, 2020)

    def test_scalar_matches_existing_method_and_intercept_has_small_gradient(self):
        api = self.api(); rows = self.rows()
        from research.pgo_confidence_pool_20260909.check import slope
        scalar = api.fit_calibration(rows, 'postseason', False)
        self.assertAlmostEqual(scalar['slope'], slope(rows, 'postseason'), places=12)
        self.assertEqual(scalar['intercept'], 0)
        self.assertAlmostEqual(scalar['tie_probability'], 5/18)
        shifted = [dict(r, actual_margin=4) if i % 4 == 1 else r for i, r in enumerate(rows)]
        fitted = api.fit_calibration(shifted, 'postseason', True)
        self.assertGreater(fitted['intercept'], 0)
        gradient = [fitted['intercept'], fitted['slope']]
        for row in shifted:
            if row['actual_margin'] == 0: continue
            error = api.sigmoid(fitted['intercept']+fitted['slope']*row['postseason'])-int(row['actual_margin'] > 0)
            gradient[0] += error; gradient[1] += error*row['postseason']
        self.assertLess(abs(gradient[0]), 1e-7)
        self.assertLess(abs(gradient[1]), 1e-7)
        self.assertLess(api.probabilities(-2, fitted)[0], api.probabilities(2, fitted)[0])

    def test_probability_metrics_count_ties_and_reliability(self):
        api = self.api()
        rows = [dict(game_id='a', season=2020, week=1, actual_margin=3, p=[.6,.3,.1], margin=1),
                dict(game_id='b', season=2020, week=2, actual_margin=0, p=[.2,.3,.5], margin=2)]
        result = api.probability_metrics(rows, 'p', 'margin')
        self.assertAlmostEqual(result['brier'], (.26+.38)/2)
        self.assertAlmostEqual(result['log_loss'], -math.log(.6*.5)/2)
        self.assertEqual(result['ties'], 1)
        self.assertEqual(result['favorite_disagreements'], 1)
        self.assertEqual(sum(x['count'] for x in result['reliability_bins']), 2)
        self.assertEqual(result['reliability_bins'][3]['observed_win_rate'], 0)

    def test_invalid_predictions_probabilities_and_duplicate_ids_fail_closed(self):
        api = self.api(); rows = self.rows()
        with self.assertRaises(ValueError): api.calibration_split(rows+[rows[0]], 2020)
        with self.assertRaises(ValueError): api.fit_calibration([dict(rows[0],postseason=float('nan'))], 'postseason', False)
        with self.assertRaises(ValueError): api.probability_metrics([dict(rows[0],p=[.5,.5,.1])], 'p', 'postseason')
        with self.assertRaises(ValueError): api.probabilities(1, dict(slope=-1,intercept=0,tie_probability=.01))
        boundary = api.fit_calibration([dict(rows[0],postseason=1,actual_margin=-2)], 'postseason', True)
        self.assertEqual(boundary['slope'], 0)

    def test_seeded_paired_uncertainty_and_exclusive_json_writes(self):
        api = self.api()
        rows = [dict(season=2020,a=1.,b=2.),dict(season=2021,a=2.,b=4.)]
        first = api.paired_interval(rows,'a','b',samples=100,seed=7)
        self.assertEqual(first,api.paired_interval(rows,'a','b',samples=100,seed=7))
        self.assertEqual(first['mean'],1.5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'; api.write_json(path,first)
            with self.assertRaises(FileExistsError): api.write_json(path,first)


if __name__ == '__main__':
    unittest.main()
