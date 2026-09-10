import copy
import unittest

from research.pgo_totals_candidate_20260910 import candidate as totals


def game(identity, day, season, week, home='NE', away='SEA', hs=20, aws=10, kind='REG'):
    return dict(game_id=identity, gameday=day, gametime='13:00', season=str(season),
                week=str(week), game_type=kind, home_team=home, away_team=away,
                home_score=str(hs), away_score=str(aws))


class TotalsCandidateTests(unittest.TestCase):
    def fixture(self):
        return [game('old', '2024-09-01', 2024, 1),
                game('playoff', '2025-01-01', 2024, 20, hs=40, aws=20, kind='DIV'),
                game('first', '2025-09-01', 2025, 1, hs=50, aws=30),
                game('second', '2025-09-08', 2025, 2, hs=10, aws=0)]

    def test_manual_prior_postseason_and_fixed_shrinkage(self):
        rows = totals.predict(self.fixture(), seasons=(2025,))
        first, second = rows
        self.assertEqual(first['pfpa_prior'], 45.)
        self.assertEqual(first['league_prior'], 45.)
        self.assertEqual(first['shrink_4'], 45.)
        self.assertEqual(first['home_current_games'], 0)
        self.assertAlmostEqual(second['shrink_4'], (4 * 45 + 80) / 5)
        self.assertAlmostEqual(second['shrink_8'], (8 * 45 + 80) / 9)
        self.assertEqual(second['current_history_through'], '2025-09-01')
        self.assertEqual(second['home_prior_games'], 2)

    def test_same_day_future_and_input_order_do_not_leak_or_mutate(self):
        games = self.fixture()
        games += [game('other-old', '2024-09-02', 2024, 1, 'BUF', 'NYJ'),
                  game('same-day', '2025-09-01', 2025, 1, 'BUF', 'NYJ')]
        before = copy.deepcopy(games)
        rows = totals.predict(games, seasons=(2025,))
        changed = copy.deepcopy(games)
        for row in changed:
            if row['gameday'] >= '2025-09-01':
                row['home_score'] = '99'
                row['away_score'] = '0'
        alternate = totals.predict(changed, seasons=(2025,))
        names = totals.MODELS
        self.assertEqual([(r['game_id'], [r[n] for n in names]) for r in rows if r['gameday'] == '2025-09-01'],
                         [(r['game_id'], [r[n] for n in names]) for r in alternate if r['gameday'] == '2025-09-01'])
        self.assertEqual(rows, totals.predict(list(reversed(games)), seasons=(2025,)))
        self.assertEqual(games, before)

    def test_zero_scores_missing_history_and_invalid_identity(self):
        rows = self.fixture()
        rows[0]['home_score'] = rows[0]['away_score'] = '0'
        self.assertEqual(totals.predict(rows, seasons=(2025,))[0]['pfpa_prior'], 30.)
        with self.assertRaisesRegex(ValueError, 'prior'):
            totals.predict(rows[2:], seasons=(2025,))
        for mutate in (lambda x: x.append(dict(x[0])),
                       lambda x: x[0].update(home_team='SEA'),
                       lambda x: x[0].update(home_score='nan'),
                       lambda x: x[0].update(home_score='-1'),
                       lambda x: x[0].update(home_score='1.5'),
                       lambda x: x[0].update(gameday='invalid')):
            value = copy.deepcopy(rows); mutate(value)
            with self.assertRaises(ValueError): totals.predict(value, seasons=(2025,))
        missing = copy.deepcopy(rows); missing[2]['home_score'] = ''
        with self.assertRaisesRegex(ValueError, 'score'):
            totals.predict(missing, seasons=(2025,))

    def test_home_away_symmetry_and_new_season_reset(self):
        games = self.fixture()
        games.append(game('next', '2026-09-01', 2026, 1))
        mirrored = [dict(r, home_team=r['away_team'], away_team=r['home_team'],
                         home_score=r['away_score'], away_score=r['home_score']) for r in games]
        rows = totals.predict(games, seasons=(2025, 2026))
        other = totals.predict(mirrored, seasons=(2025, 2026))
        self.assertEqual([[r[n] for n in totals.MODELS] for r in rows], [[r[n] for n in totals.MODELS] for r in other])
        self.assertEqual(rows[-1]['home_current_games'], 0)
        self.assertEqual(rows[-1]['shrink_4'], 45.)

    def test_cluster_metrics_are_paired_and_deterministic(self):
        rows = [dict(season=2020+i//2, week=i%2+1, actual_total=40.,
                     league_prior=44., pfpa_prior=43., shrink_4=42., shrink_8=41.) for i in range(4)]
        result = totals.evaluate(rows, samples=100)
        self.assertEqual(result['metrics']['overall']['shrink_4']['mae'], 2.)
        self.assertEqual(result['metrics']['overall']['shrink_4']['bias'], 2.)
        interval = result['paired']['shrink_4']['vs_pfpa_prior']['season']
        self.assertEqual(interval['lower'], 1.)
        self.assertEqual(interval['upper'], 1.)
        self.assertEqual(result, totals.evaluate(rows, samples=100))


if __name__ == '__main__':
    unittest.main()
