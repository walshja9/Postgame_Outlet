import copy
import importlib.util
import json
import math
import unittest


class SeasonAccuracyTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_season_accuracy'),
                             'Pure saved-forecast accuracy summary is missing')
        import pgo_season_accuracy
        return pgo_season_accuracy

    def game(self, key, margin=3, total=45, probability=None, late=False):
        game = dict(game_id=key, season=2026, week=1, game_type='REG',
                    home='SEA', away='NE', kickoff='2026-09-10T00:20:00Z',
                    lock_at='2026-09-09T23:20:00Z', issued_at='2026-09-09T22:00:00Z',
                    margin=margin, total=total, blocked_reason=None)
        if probability is not None:
            selected = 'home' if margin > 0 else 'away'
            game['confidence'] = dict(points=2, probabilities=probability,
                win_probability=probability[selected], expected_points=2*probability[selected],
                added_after_lock=late, earned_points=999)  # Recompute from finals.
        return game

    def final(self, game, home=24, away=21):
        return dict(game_id=game['game_id'], season=2026, week=1, game_type='REG',
                    home_team=game['home'], away_team=game['away'], kickoff=game['kickoff'],
                    home_score=home, away_score=away, actual_margin=home-away,
                    finalized_at='2026-09-10T04:00:00Z')

    def state(self, games, finals):
        return dict(checked_at='2026-09-10T05:00:00Z', season=2026,
                    weeks=[dict(week=1, games=games)], results=finals)

    def test_hand_computed_win_loss_tie_and_late_probability(self):
        api = self.api()
        games = [self.game('win', probability=dict(home=.6, away=.3, tie=.1)),
                 self.game('loss', margin=-2, total=40, probability=dict(home=.2, away=.7, tie=.1)),
                 self.game('tie', margin=1, total=44, probability=dict(home=.5, away=.4, tie=.1)),
                 self.game('late', margin=4, total=42, probability=dict(home=.8, away=.1, tie=.1), late=True)]
        finals = [self.final(games[0]), self.final(games[1], 21, 17),
                  self.final(games[2], 20, 20), self.final(games[3], 23, 20)]
        state = self.state(games, finals); before = copy.deepcopy(state)
        summary = api.summarize(state); result = summary['primary']
        self.assertEqual(state, before)
        json.dumps(summary, allow_nan=False)
        self.assertEqual([result['record'][x] for x in ('wins', 'losses', 'ties', 'n')], [2, 1, 1, 4])
        self.assertAlmostEqual(result['margin_mae']['value'], (0+6+1+1)/4)
        self.assertAlmostEqual(result['total_mae']['value'], (0+2+4+1)/4)
        self.assertEqual(result['probabilities']['n'], 3)
        self.assertEqual(result['probabilities']['reasons'], {'late_confidence': 1})
        self.assertAlmostEqual(result['probabilities']['brier'], (.26+1.14+1.22)/3)
        self.assertAlmostEqual(result['probabilities']['log_loss'], -math.log(.6*.2*.1)/3)
        self.assertEqual(result['confidence']['earned_points'], 4)
        self.assertAlmostEqual(result['confidence']['expected_points'], 5.2)
        self.assertEqual(result['confidence']['available_points'], 8)
        self.assertEqual(result['confidence']['late_count'], 1)
        self.assertEqual(result['reliability']['n'], 3)
        bins = result['reliability_bins']
        self.assertEqual(len(bins), 10)
        self.assertEqual([bins[i]['count'] for i in (5, 6, 7, 8)], [1, 1, 1, 0])
        self.assertEqual(bins[5]['observed_win_rate'], 0)
        self.assertEqual(bins[6]['observed_win_rate'], 1)

    def test_missing_late_blocked_and_zero_have_metric_specific_counts(self):
        api = self.api()
        games = [self.game('pending'), self.game('missing', None, None),
                 self.game('late'), self.game('blocked'), self.game('zero', 0, 45),
                 self.game('unknown-time'), self.game('incomplete-prob', probability=dict(home=.6, away=.3, tie=.1))]
        games[2]['issued_at'] = games[2]['lock_at']
        games[3]['blocked_reason'] = 'Expected QB unavailable'
        del games[5]['issued_at']
        del games[6]['confidence']['probabilities']['tie']
        finals = [self.final(g) for g in games[1:]]
        summary = api.summarize(self.state(games, finals))['primary']
        self.assertEqual(summary['record']['n'], 1)
        self.assertEqual(summary['record']['reasons'], dict(no_verified_final=1, missing_margin=1,
            late_forecast=1, blocked_forecast=1, no_pick=1, unknown_forecast_time=1))
        self.assertEqual(summary['margin_mae']['n'], 2)
        self.assertEqual(summary['total_mae']['n'], 2)
        self.assertEqual(summary['probabilities']['n'], 0)
        self.assertIn('incomplete_probabilities', summary['probabilities']['reasons'])
        self.assertIsNone(summary['probabilities']['brier'])
        self.assertEqual(summary['confidence']['n'], 1)  # Saved scalar probability still prices this fixed pool.

    def test_common_game_comparisons_do_not_compare_unequal_schedules(self):
        api = self.api()
        a, b, c = self.game('a', 3), self.game('b', 20), self.game('c', 2)
        state = self.state([a, b], [self.final(g) for g in (a, b, c)])
        old_a, old_c = self.game('a', 1), self.game('c', 2)
        del old_a['issued_at']; del old_c['issued_at']
        state['accuracy_models'] = [dict(name='Prior', edition='prior',
            issued_at='2026-09-09T21:00:00Z', games=[old_a, old_c])]
        out = api.summarize(state)
        self.assertEqual(len(out['models']), 2)
        self.assertAlmostEqual(out['primary']['margin_mae']['value'], 8.5)
        metric = out['comparisons'][0]['margin_mae']
        self.assertEqual(metric['game_ids'], ['a'])
        self.assertEqual(metric['n'], 1)
        self.assertEqual(metric['primary'], 0)
        self.assertEqual(metric['model'], 2)
        self.assertEqual(metric['difference'], -2)
        self.assertEqual(metric['excluded'], 2)
        self.assertIsNone(out['comparisons'][0]['probabilities']['brier']['difference'])

    def test_rejects_identity_score_duplicate_and_probability_corruption(self):
        api = self.api(); game = self.game('a', probability=dict(home=.6, away=.3, tie=.1))
        base = self.state([game], [self.final(game)])
        mutations = [lambda s: s['results'][0].update(home_team='BUF'),
                     lambda s: s['results'][0].update(home_score=None),
                     lambda s: s['results'][0].update(away_score=True),
                     lambda s: s['results'][0].update(actual_margin=10),
                     lambda s: s['results'][0].update(finalized_at='2026-09-09T23:00:00Z'),
                     lambda s: s['results'].append(copy.deepcopy(s['results'][0])),
                     lambda s: s['weeks'][0]['games'].append(copy.deepcopy(game)),
                     lambda s: s['weeks'][0]['games'][0].update(margin=float('nan')),
                     lambda s: s['weeks'][0]['games'][0].update(pick='BUF'),
                     lambda s: s['weeks'][0]['games'][0]['confidence']['probabilities'].update(home=.8),
                     lambda s: s['weeks'][0]['games'][0]['confidence'].update(win_probability=.8),
                     lambda s: s['weeks'][0]['games'][0].update(lock_at='2026-09-10T00:00:00Z')]
        for mutate in mutations:
            state = copy.deepcopy(base); mutate(state)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                api.summarize(state)

    def test_empty_metrics_are_unknown_and_unknown_confidence_time_is_not_timely(self):
        api = self.api()
        out = api.summarize(self.state([], []))['primary']
        self.assertIsNone(out['margin_mae']['value'])
        self.assertIsNone(out['confidence']['expected_points'])
        game = self.game('a', probability=dict(home=1., away=0., tie=0.))
        del game['confidence']['added_after_lock']
        result = api.summarize(self.state([game], [self.final(game)]))['primary']
        self.assertEqual(result['probabilities']['reasons'], {'unknown_confidence_time': 1})
        game['confidence']['added_after_lock'] = False
        result = api.summarize(self.state([game], [self.final(game, 20, 20)]))['primary']
        self.assertEqual(result['probabilities']['brier'], 2)
        self.assertAlmostEqual(result['probabilities']['log_loss'], -math.log(1e-15))
        self.assertEqual(result['reliability_bins'][9]['count'], 1)

    def test_legacy_loader_keeps_issuance_but_does_not_invent_v0_total(self):
        api = self.api()
        from unittest.mock import patch
        import pgo_forecast_corrected as corrected
        import pgo_season as season
        import pgo_forecast_snapshot as preseason
        game = dict(self.game('a'), pgo_v0_margin=-2, home_points=24, away_points=21)
        snapshot = dict(generated_at=game['issued_at'], games=[game])
        season.legacy_models.cache_clear()
        try:
            with patch.object(corrected, 'load_snapshot', return_value=dict(snapshot,edition='corrected')), \
                 patch.object(season, 'initial_snapshot', return_value=dict(snapshot,edition='postseason')), \
                 patch.object(preseason, 'load_snapshot', return_value=dict(snapshot,edition='preseason')):
                models = api.load_models()
        finally:
            season.legacy_models.cache_clear()
        v0 = models[-1]
        self.assertEqual(v0['issued_at'], game['issued_at'])
        self.assertIsNone(v0['games'][0].get('total'))
        self.assertIsNone(v0['games'][0].get('home_points'))
        out = api.summarize(dict(self.state([game], [self.final(game)]), accuracy_models=models))
        self.assertEqual(out['comparisons'][-1]['total_mae']['n'], 0)
        self.assertIsNone(out['comparisons'][-1]['total_mae']['difference'])
        self.assertEqual(game['total'], 45)


if __name__ == '__main__':
    unittest.main()
