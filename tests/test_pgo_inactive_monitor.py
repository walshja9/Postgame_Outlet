"""Final lists remain visible without rewriting the prediction they arrived after."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pgo_season as api
from tests import test_pgo_season_boundaries as fixtures


class InactiveMonitorTests(unittest.TestCase):
    def fixture(self):
        game = fixtures.SeasonBoundaryTests().game()
        return fixtures.SeasonBoundaryTests().state([game]), game

    def observation(self, game, checked='2026-09-13T16:30:00Z', complete=True):
        return dict(game_id=game['game_id'], home=game['home'], away=game['away'],
                    kickoff=game['kickoff'], lock_at=game['lock_at'], checked_at=checked,
                    summary='Official inactive lists', blocked_reason=None,
                    teams={t: dict(final_inactives_status='VERIFIED_LIST' if complete else 'UNKNOWN')
                           for t in (game['home'], game['away'])})

    def test_late_capture_is_separate_and_failed_attempt_retains_its_real_clock(self):
        state, game = self.fixture(); before = copy.deepcopy(state['weeks'])
        observation = self.observation(game)
        selected = {t: dict(gsis_id=t+'-old', full_name=t+' old') for t in ('SEA','NE')}
        with tempfile.TemporaryDirectory() as tmp, patch.object(api, 'now', return_value='2026-09-13T16:30:00Z'), \
             patch.object(api, 'fetch_source', return_value=(b'', {})), patch.object(api, 'csv_rows', return_value=[]), \
             patch.object(api, 'select_roster', return_value=selected), \
             patch('pgo_season_availability.capture_availability', return_value={'games': {game['game_id']: observation}}) as capture:
            api.refresh_availability(state, Path(tmp))
            self.assertEqual(capture.call_args.kwargs['purpose'], 'context')
            self.assertEqual(state['weeks'], before)
            self.assertEqual(state['availability_context'][game['game_id']]['checked_at'], observation['checked_at'])
            saved = copy.deepcopy(state['availability_context'])
            capture.side_effect = OSError('Official source unavailable')
            api.refresh_availability(state, Path(tmp))
            self.assertEqual(state['availability_context'], saved)
            self.assertEqual(state['availability_context_check']['status'], 'BLOCKED')
            self.assertEqual(state['weeks'], before)
            # HTTP errors are normally returned as an incomplete package, not raised.
            capture.side_effect = None
            capture.return_value = {'games': {game['game_id']: self.observation(game, complete=False)}}
            api.refresh_availability(state, Path(tmp))
            self.assertEqual(state['availability_context'], saved)
            self.assertEqual(state['availability_context_check']['status'], 'BLOCKED')
            self.assertIn('SEA', state['availability_context_check']['blocked_reason'])
            state.pop('availability_context')
            state['weeks'][0]['games'][0]['availability'] = self.observation(game, checked='2026-09-13T15:59:00Z')
            before = copy.deepcopy(state['weeks'])
            api.refresh_availability(state, Path(tmp))
            self.assertNotIn(game['game_id'], state.get('availability_context', {}))
            self.assertEqual(state['weeks'], before)

    def test_watch_reports_missing_stale_and_late_verified_without_relabeling_forecast(self):
        state, game = self.fixture()
        state['checked_at'] = '2026-09-13T15:00:00Z'
        self.assertEqual(api.availability_watch(state)['games'][0]['status'], 'AWAITING')
        state['checked_at'] = '2026-09-13T15:50:00Z'
        self.assertEqual(api.availability_watch(state)['games'][0]['status'], 'MISSING')
        state['availability_context'] = {game['game_id']: self.observation(game)}
        state['checked_at'] = '2026-09-13T16:31:00Z'
        self.assertEqual(api.availability_watch(state)['status'], 'READY')
        state['checked_at'] = '2026-09-13T16:45:00Z'
        self.assertEqual(api.availability_watch(state)['games'][0]['status'], 'STALE')
        state['checked_at'] = '2026-09-13T17:05:00Z'
        self.assertEqual(api.availability_watch(state)['games'][0]['status'], 'VERIFIED')
        self.assertEqual(state['weeks'][0]['games'][0], game)

    def test_context_must_match_archived_evidence_and_save_clock(self):
        state, game = self.fixture(); state['checked_at'] = '2026-09-13T16:31:00Z'
        observation = self.observation(game)
        archive = 'availability-v2/20260913T163000000000Z'
        state['availability_context'] = {game['game_id']: dict(observation, source_archive=archive)}
        payload = {'purpose': 'context', 'games': {game['game_id']: observation}}
        with patch('pgo_season_availability.load_availability', return_value=payload):
            api.check_availability_context(state, Path('fixture'), '2026-09-13T16:31:01Z')
            state['availability_context'][game['game_id']]['summary'] = 'Changed without source'
            with self.assertRaisesRegex(ValueError, 'context.*evidence'):
                api.check_availability_context(state, Path('fixture'), '2026-09-13T16:31:01Z')
            state['availability_context'][game['game_id']]['summary'] = observation['summary']
            with self.assertRaisesRegex(ValueError, 'context.*clock'):
                api.check_availability_context(state, Path('fixture'), '2026-09-13T16:29:00Z')


if __name__ == '__main__':
    unittest.main()
