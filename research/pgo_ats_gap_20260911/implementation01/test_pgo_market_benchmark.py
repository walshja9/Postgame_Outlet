import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import pgo_ats
from tests import test_pgo_ats


class MarketBenchmarkTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_market_benchmark'),
                             'The saved-line benchmark is not implemented')
        import pgo_market_benchmark
        return pgo_market_benchmark

    def fixture(self, margin=4.25, line=-3.5, actual=6):
        helper = test_pgo_ats.ATSTests()
        state, payload = helper.fixture(margin=margin, line=line)
        with tempfile.TemporaryDirectory() as tmp:
            helper.archive(Path(tmp), state, payload)
            state['ats'] = pgo_ats.refresh(state, None, Path(tmp), state['checked_at'])
        if actual is not None:
            state['results'] = [helper.final(state['weeks'][0]['games'][0], actual)]
            state['checked_at'] = '2026-09-13T22:00:00Z'
        return state

    def test_common_game_signed_margin_error_and_nonmutation(self):
        api = self.api()
        for margin, line, actual, pgo_error, book_error in [(4.25, -3.5, 6, 1.75, 2.5), (-1.25, 3.5, -6, 4.75, 2.5)]:
            with self.subTest(line=line):
                state = self.fixture(margin, line, actual); before = copy.deepcopy(state)
                out = api.summarize(state); benchmark = out['benchmark']
                self.assertEqual(benchmark['n'], 1)
                self.assertEqual(benchmark['pgo_margin_mae'], pgo_error)
                self.assertEqual(benchmark['sportsbook_margin_mae'], book_error)
                self.assertEqual(benchmark['difference'], pgo_error-book_error)
                self.assertEqual(benchmark['pgo_record']['wins'], 1)
                self.assertEqual(benchmark['sportsbook_record']['wins'], 1)
                self.assertEqual(state, before)
                self.assertEqual(out['prospective_status'], 'UNAVAILABLE')

    def test_pick_em_no_pick_actual_tie_and_push_are_separate(self):
        api = self.api()
        zero = api.summarize(self.fixture(0, 0, 0))
        self.assertEqual(zero['benchmark']['n'], 1)
        self.assertEqual(zero['benchmark']['pgo_record'], dict(wins=0, losses=0, ties=0, no_pick=1))
        self.assertEqual(zero['benchmark']['sportsbook_record'], dict(wins=0, losses=0, ties=0, no_pick=1))
        self.assertEqual(zero['ats']['no_edge'], 1)
        tie = api.summarize(self.fixture(4, -3, 0))
        self.assertEqual(tie['benchmark']['pgo_record']['ties'], 1)
        self.assertEqual(tie['benchmark']['sportsbook_record']['ties'], 1)
        self.assertEqual(tie['ats']['losses'], 1)
        push = api.summarize(self.fixture(4, -3, 3))
        self.assertEqual(push['ats']['pushes'], 1)
        self.assertEqual(push['benchmark']['pgo_record']['wins'], 1)

    def test_exact_fixed_bands_and_pending_rows(self):
        api = self.api()
        for margin, expected in [(3.5, 'zero'), (3.75, 'under_1'), (4.5, '1_to_under_3'),
                                  (6.499, '1_to_under_3'), (6.5, '3_or_more'), (0.5, '3_or_more')]:
            with self.subTest(margin=margin):
                out = api.summarize(self.fixture(margin, -3.5, None))
                band = next(row for row in out['ats_bands'] if row['key'] == expected)
                self.assertEqual(band['n'], 1)
                self.assertEqual(band['no_edge' if expected == 'zero' else 'pending'], 1)
                self.assertEqual(out['benchmark']['reasons'], {'pending': 1})
                self.assertIsNone(out['benchmark']['pgo_margin_mae'])

    def test_missing_late_inconsistent_and_changed_main_are_excluded(self):
        api = self.api()
        changes = [
            ('missing_quote', lambda s: s['ats'].update(games=[])),
            ('invalid_quote', lambda s: s['ats']['games'][0].update(issued_at=s['ats']['games'][0]['lock_at'])),
            ('invalid_quote', lambda s: s['ats']['games'][0].update(home_edge=99)),
            ('invalid_quote', lambda s: s['ats']['games'][0].update(home_handicap=float('nan'))),
            ('main_forecast_changed', lambda s: s['weeks'][0]['games'][0].update(source_edition='new-edition')),
            ('invalid_quote', lambda s: s['ats']['games'][0].update(issued_at='2026-09-13T23:00:00Z')),
            ('event_identity', lambda s: s['ats']['games'][0].update(event_id='999')),
            ('forecast_identity', lambda s: s['ats']['games'][0].update(home='LAR')),
            ('invalid_forecast', lambda s: s['weeks'][0]['games'][0].update(pick=None)),
            ('invalid_forecast', lambda s: s['weeks'][0]['games'][0].update(issued_at='2026-09-13T16:00:00Z')),
            ('invalid_final', lambda s: s['results'][0].update(home_team='LAR')),
            ('invalid_final', lambda s: s['results'][0].update(week=2)),
            ('invalid_final', lambda s: s['results'][0].update(finalized_at='2026-09-14T00:00:00Z')),
        ]
        for reason, change in changes:
            with self.subTest(reason=reason):
                state = self.fixture(); change(state); out = api.summarize(state)
                self.assertEqual(out['benchmark']['reasons'], {reason: 1})
                self.assertEqual(out['benchmark']['n'], 0)
                self.assertEqual(out['ats']['unavailable'], 1)

    def test_grade_is_recomputed_and_structural_duplicates_are_rejected(self):
        api = self.api(); state = self.fixture(actual=1)
        state['ats']['games'][0]['grade'] = {'ats': 'W'}
        self.assertEqual(api.summarize(state)['ats']['losses'], 1)
        for collection in ('schedule', 'results'):
            bad = copy.deepcopy(state); bad[collection].append(copy.deepcopy(bad[collection][0]))
            with self.subTest(collection=collection), self.assertRaises(ValueError): api.summarize(bad)
        bad = copy.deepcopy(state); bad['ats']['games'].append(copy.deepcopy(bad['ats']['games'][0]))
        with self.assertRaises(ValueError): api.summarize(bad)
        bad = copy.deepcopy(state); bad['ats']['unavailable'] = copy.deepcopy(bad['ats']['games'])
        with self.assertRaises(ValueError): api.summarize(bad)
        bad = copy.deepcopy(state); bad['results'][0]['game_id'] = 'other'
        with self.assertRaises(ValueError): api.summarize(bad)

    def test_source_age_and_quote_observation_clock_are_required(self):
        api = self.api()
        for captured in ('2026-09-10T18:59:59Z', '2026-09-10T20:00:01Z'):
            with self.subTest(captured=captured):
                state = self.fixture(); row = state['ats']['games'][0]
                row['quote_captured_at'] = row['source']['captured_at'] = captured
                self.assertEqual(api.summarize(state)['benchmark']['reasons'], {'invalid_quote': 1})
        state = self.fixture(); state['ats']['checked_at'] = '2026-09-10T19:59:59Z'
        self.assertEqual(api.summarize(state)['benchmark']['reasons'], {'invalid_quote': 1})


if __name__ == '__main__':
    unittest.main()
