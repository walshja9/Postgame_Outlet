import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from pgo_workflow_status import report_health


class WorkflowStatusTests(unittest.TestCase):
    def report(self, status='READY', reason=None, penalty_status='READY', penalty_reason=None, **components):
        state = dict(status=status, blocked_reason=reason, checked_at='2026-09-10T16:22:00Z',
                     penalty_shadow=dict(status=penalty_status, blocked_reason=penalty_reason),
                     totals_shadow=dict(status='READY', blocked_reason=None),
                     weights_shadow=dict(status='READY', blocked_reason=None),
                     ats=dict(status='READY', blocked_reason=None),
                     replacement_depth=dict(status='DESCRIPTIVE / NOT IN MODEL', blocked_reason=None,
                                            historical_admission='BLOCKED FOR FITTING'))
        state.update(components)
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / 'summary.md'
            with contextlib.redirect_stdout(output):
                payload = report_health(state, summary)
            saved = summary.read_text(encoding='utf-8')
        self.assertIn(json.dumps(payload, indent=2), saved)
        return payload, output.getvalue()

    def test_final_inactive_watch_warns_without_blocking_main_health(self):
        games = [dict(game_id=str(i), home='SEA', away='NE', missing_teams=['SEA'], status=status,
                      checked_at='2026-09-10T16:20:00Z', after_lock=False)
                 for i,status in enumerate(('MISSING','STALE','AWAITING','VERIFIED'))]
        watch = dict(status='ATTENTION', checked_at='2026-09-10T16:22:00Z', games=games)
        with patch('pgo_season.availability_watch', return_value=watch, create=True):
            payload, output = self.report()
        self.assertEqual(payload['condition'], 'READY')
        self.assertEqual(payload.get('availability_watch'), watch)
        self.assertEqual(output.count('::warning::'), 2)
        self.assertIn('final inactives MISSING: NE @ SEA', output)
        self.assertIn('final inactives STALE: NE @ SEA', output)
        self.assertIn('SEA', output)
        watch['blocked_reason'] = 'Official source unavailable\n::error::not a new command'
        with patch('pgo_season.availability_watch', return_value=watch, create=True):
            _, output = self.report()
        self.assertIn('::warning::PGO final inactive watch: Official source unavailable%0A', output)
        self.assertNotIn('\n::error::', output)

    def test_ready_state_records_the_actual_check_without_warning(self):
        payload, output = self.report()
        self.assertEqual(payload['condition'], 'READY')
        self.assertEqual(payload['checked_at'], '2026-09-10T16:22:00Z')
        self.assertNotIn('::warning::', output)

    def test_weekly_wait_source_error_and_availability_error_are_distinct(self):
        for reason, condition in [('Waiting to publish the next week: Missing team statistics', 'WAITING_FOR_NEXT_WEEK'),
                                  ('Automatic update needs review: Invalid final', 'SOURCE_REVIEW'),
                                  ('Availability refresh needs review: Source unavailable', 'AVAILABILITY_REVIEW')]:
            with self.subTest(reason=reason):
                payload, output = self.report('BLOCKED', reason)
                self.assertEqual(payload['status'], 'BLOCKED')
                self.assertEqual(payload['condition'], condition)
                self.assertEqual(payload['blocked_reason'], reason)
                self.assertIn('::warning::', output)

    def test_independent_penalty_block_is_visible_and_warning_text_is_escaped(self):
        reason = 'Bad % source\n::error::forged\rline'
        payload, output = self.report(penalty_status='BLOCKED', penalty_reason=reason)
        self.assertEqual(payload['status'], 'READY')
        self.assertEqual(payload['penalty_status'], 'BLOCKED')
        self.assertEqual(payload['penalty_blocked_reason'], reason)
        self.assertIn('Bad %25 source%0A::error::forged%0Dline', output)
        self.assertNotIn('\n::error::', output)

    def test_new_component_failures_do_not_change_main_health(self):
        for key, prefix in [('totals_shadow','totals'), ('weights_shadow','weights'),
                            ('replacement_depth','replacement_depth'), ('ats','ats')]:
            with self.subTest(component=key):
                payload, output = self.report(**{key:dict(status='BLOCKED', blocked_reason='Source missing')})
                self.assertEqual(payload['status'],'READY')
                self.assertEqual(payload['condition'],'READY')
                self.assertEqual(payload[prefix+'_status'],'BLOCKED')
                self.assertEqual(payload[prefix+'_blocked_reason'],'Source missing')
                self.assertEqual(output.count('::warning::'),1)

    def test_descriptive_replacement_capture_is_not_a_runtime_failure(self):
        payload, output = self.report()
        self.assertEqual(payload['replacement_depth_status'],'DESCRIPTIVE / NOT IN MODEL')
        self.assertEqual(payload['replacement_depth_historical_admission'],'BLOCKED FOR FITTING')
        self.assertNotIn('::warning::',output)


if __name__ == '__main__':
    unittest.main()
