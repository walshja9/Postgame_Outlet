"""Arithmetic-only checks; synthetic records do not qualify source evidence."""
from copy import deepcopy
import importlib
import importlib.util
import unittest


MODULE = 'research.pgo_nonqb_absence_burden_20260913.features'
LOCK = '2026-09-13T16:00:00Z'
PLAYER = '00-0030001'


def observation(week=1, share=.8, **changes):
    row = dict(gsis_id=PLAYER, game_id=f'2025_{week:02d}_NE_SEA', season=2025,
               game_type='REG', unit='offense', kickoff=f'2025-10-{week:02d}T17:00:00Z',
               final_observed_at=f'2025-10-{week:02d}T21:00:00Z',
               source_captured_at='2026-09-12T16:00:00Z', share=share)
    return dict(row, **changes)


def player(**changes):
    return dict(dict(gsis_id=PLAYER, position='WR', status='OUT',
                     injury_documented=True, prior_usage=.8), **changes)


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'Feature implementation is missing')
        self.f = importlib.import_module(MODULE)

    def prior(self, rows, **changes):
        return self.f.prior_share(rows, **dict(dict(player_id=PLAYER, unit='offense',
                                                  season=2026, lock_at=LOCK), **changes))

    def burden(self, rows, **changes):
        return self.f.unit_burden(rows, **dict(dict(unit='offense', report_complete=True), **changes))

    def test_last_four_include_zero_follow_identity_and_leave_input_unchanged(self):
        rows = [observation(i, share, team='NE' if i < 4 else 'SEA')
                for i, share in enumerate([1., .8, 0., 0., .4], 1)]
        rows.reverse()
        original = deepcopy(rows)
        result = self.prior(rows)
        self.assertEqual(result, dict(share=.2, count=4, game_ids=[
            f'2025_{i:02d}_NE_SEA' for i in (2, 3, 4, 5)], status='KNOWN'))
        self.assertEqual(rows, original)

    def test_missing_history_is_unknown_and_unrelated_observations_do_not_enter(self):
        rows = [observation(gsis_id='00-0030002'), observation(unit='defense'),
                observation(game_type='POST'), observation(season=2024),
                observation(kickoff=LOCK)]
        self.assertEqual(self.prior(rows), dict(share=None, count=0, game_ids=[], status='UNKNOWN'))
        self.assertEqual(self.prior([observation(share=0)])['share'], 0.)

    def test_selected_bad_values_and_clocks_block_without_older_fallback(self):
        older = [observation(i) for i in range(1, 5)]
        changes = [dict(share=v) for v in (None, True, float('nan'), float('inf'), -.1, 1.1, '0.8')]
        changes += [dict(source_captured_at=LOCK), dict(source_captured_at='2026-09-14T00:00:00Z'),
                    dict(final_observed_at='2025-10-05T17:00:00Z'),
                    dict(final_observed_at='2026-09-12T17:00:00Z'),
                    dict(kickoff='not-a-clock'), dict(source_captured_at='2026-09-12T16:00:00')]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prior(older + [observation(5, **change)])
        # An invalid value outside the fixed selected four is not an observation fallback.
        self.assertEqual(self.prior([observation(share=None)] +
                                   [observation(i) for i in range(2, 6)])['count'], 4)

    def test_duplicate_history_rejected_and_clock_ties_order_by_game_id(self):
        with self.assertRaises(ValueError):
            self.prior([observation(), observation()])
        rows = [observation(game_id=f'2025_01_NE_{team}') for team in ('SEA', 'ATL')]
        self.assertEqual(self.prior(rows)['game_ids'], ['2025_01_NE_ATL', '2025_01_NE_SEA'])

    def test_invalid_newest_game_type_cannot_fall_back_to_older_history(self):
        older = [observation(i) for i in range(1, 5)]
        for game_type in (None, '', 'Reg', 'REG ', 'WC', True, []):
            with self.subTest(game_type=game_type), self.assertRaises(ValueError):
                self.prior(older + [observation(5, game_type=game_type)])
        latest = observation(5)
        del latest['game_type']
        with self.assertRaises(ValueError):
            self.prior(older + [latest])
        for game_type in ('PRE', 'POST'):
            with self.subTest(game_type=game_type):
                self.assertEqual(self.prior(older + [observation(5, game_type=game_type)]),
                                 self.prior(older))

    def test_burden_can_exceed_one_and_explicit_no_absences_is_zero(self):
        result = self.burden([player(), player(gsis_id='00-0030002', position='LT')])
        self.assertEqual(result, dict(total=1.6, known_subtotal=1.6, qualifying_count=2,
                                      missing=[], status='KNOWN'))
        self.assertEqual(self.burden([])['total'], 0.)

    def test_missing_reports_identity_usage_or_injury_membership_keep_subtotal(self):
        cases = [(player(gsis_id=None), 'IDENTITY_UNKNOWN'),
                 (player(gsis_id='wrong'), 'IDENTITY_UNKNOWN'),
                 (player(gsis_id='00-0030002', prior_usage=None), 'PRIOR_USAGE_UNKNOWN'),
                 (player(gsis_id='00-0030002', injury_documented=None), 'INJURY_REASON_UNKNOWN')]
        for extra, reason in cases:
            with self.subTest(reason=reason):
                result = self.burden([player(), extra])
                self.assertIsNone(result['total'])
                self.assertEqual(result['known_subtotal'], .8)
                self.assertIn(reason, [r['reason'] for r in result['missing']])
        result = self.burden([player()], report_complete=False)
        self.assertIsNone(result['total'])
        self.assertEqual(result['known_subtotal'], .8)
        self.assertEqual(result['status'], 'UNKNOWN')

    def test_excludes_noninjury_uncertain_roster_context_qbs_and_specialists(self):
        rows = [player(gsis_id=f'00-{i:07d}', status=status) for i, status in enumerate(
            ('RES', 'INA', 'DEV', 'ACT', 'QUESTIONABLE', 'DOUBTFUL', 'DNP'), 1)]
        rows += [player(gsis_id=f'00-{i:07d}', position=position)
                 for i, position in enumerate(('QB', 'K', 'P', 'LS', 'LB'), 20)]
        rows.append(player(gsis_id='00-0039999', status='INACTIVE', injury_documented=False))
        self.assertEqual(self.burden(rows)['total'], 0.)
        self.assertEqual(self.burden([player(position='EDGE')], unit='defense')['total'], .8)
        self.assertEqual(self.burden([player(status='INACTIVE')])['total'], .8)
        for unit in ('offense', 'defense'):
            self.assertIsNone(self.burden([player(position=None)], unit=unit)['total'])

    def test_duplicate_eligible_identity_and_invalid_fractions_fail(self):
        with self.assertRaises(ValueError):
            self.burden([player(), player(status='RES')])
        for value in (True, float('nan'), float('inf'), -.1, 1.1, '0.8'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.burden([player(prior_usage=value)])
        with self.assertRaises(ValueError):
            self.burden([player(injury_documented='yes')])
        with self.assertRaises(ValueError):
            self.burden([], report_complete='yes')

    def test_missing_or_unrecognized_status_cannot_become_known_zero(self):
        for status in (None, '', 'Out', ' OUT', 'OUT ', 'healthy', True, []):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.burden([player(status=status)])
        row = player()
        del row['status']
        with self.assertRaises(ValueError):
            self.burden([row])
        for status in ('AVAILABLE', 'UNREPORTED', 'UNKNOWN'):
            with self.subTest(status=status):
                self.assertEqual(self.burden([player(status=status)])['total'], 0.)

    def test_margin_inputs_have_home_margin_sign_and_unknown_propagates(self):
        home, away = dict(offense=1.6, defense=.2), dict(offense=.4, defense=.8)
        result = self.f.margin_inputs(home, away)
        self.assertAlmostEqual(result['x_off'], -1.2)
        self.assertAlmostEqual(result['x_def'], .6)
        self.assertIsNone(self.f.margin_inputs(dict(home, offense=None), away))
        self.assertIsNone(self.f.margin_inputs({}, away))
        for value in (True, float('nan'), -.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.f.margin_inputs(dict(home, offense=value), away)


if __name__ == '__main__':
    unittest.main()
