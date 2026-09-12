import copy
import csv
import gzip
import hashlib
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from research.pgo_replacement_depth_20260910 import capture
from tests.test_pgo_replacement_depth import roster, slot

CHECK = '2026-09-11T12:00:00+00:00'


class InjuryUsageMonitorTests(unittest.TestCase):
    def setUp(self):
        import pgo_injury_usage_monitor as api
        self.api = api
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.history = patch.object(capture, '_history', return_value=({}, None)); self.history.start(); self.addCleanup(self.history.stop)
        self.final_check = patch.object(api, 'verify_finals'); self.final_check.start(); self.addCleanup(self.final_check.stop)
        self.game = dict(game_id='2026_01_SF_LA', season=2026, week=1, game_type='REG', home='LAR', away='SF',
                         kickoff='2026-09-11T00:35:00+00:00', lock_at='2026-09-10T23:35:00+00:00')
        self.final = dict(self.game, home_team='LAR', away_team='SF', home_score=20, away_score=21,
                          actual_margin=-1, finalized_at='2026-09-11T03:30:00+00:00')
        self.state = dict(schema_version=1, season=2026, checked_at=CHECK, results=[self.final],
                          schedule=[self.game], weeks=[dict(games=[self.game])])
        self.rows = [dict(game_id=self.game['game_id'], season='2026', week='1', game_type='REG', team='SF',
                         opponent='LA', pfr_player_id='PlayTe00', defense_snaps='0')]
        self.first = self.archive('2026-09-10T20:00:00+00:00', '2026-09-10T20:00:01+00:00')

    def archive(self, generated, durable, version=1, malformed=False, game=None, games=None):
        game = game or self.game
        rr = [dict(roster('00-0000001', 'Player One'), team='SF', pfr_id='PlayTe00', game_type='REG'),
              dict(roster('00-0000002', 'Backup Two'), team='SF', pfr_id='BackTe00', game_type='REG'),
              dict(roster('00-0000003', 'Inactive Three', 'INA'), team='SF', pfr_id='InacTh00', game_type='REG')]
        dd = [dict(slot(r['gsis_id'], r['full_name'], i+1), team='SF') for i, r in enumerate(rr)]
        refs = []
        for url, rows in ((capture.ROSTER_URL, rr), (capture.DEPTH_URL, dd)):
            stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
            raw = gzip.compress(stream.getvalue().encode(), mtime=0); digest = hashlib.sha256(raw).hexdigest()
            path = self.root/'source-archive'/f'{digest}.csv.gz'; path.parent.mkdir(exist_ok=True); path.write_bytes(raw)
            refs.append(dict(url=url, path=path.relative_to(self.root).as_posix(), captured_at='2026-09-10T20:00:00+00:00', sha256=digest, bytes=len(raw)))
        state = dict(schema_version=1, season=2026, checked_at=generated, source_captures=refs, weeks=[dict(games=games or [game])])
        state['replacement_depth'] = capture.capture(state, self.root, generated, inventory_version=version or 1)
        if version is None: state['replacement_depth'].pop('inventory_version')
        if malformed: state['replacement_depth']['teams'][0]['defenders'] = [dict(gsis_id='bad')]
        from pgo_season import utc
        directory = self.root/'runs-v2'/utc(generated).strftime('%Y%m%dT%H%M%S%fZ'); directory.mkdir(parents=True)
        raw = json.dumps(state).encode(); (directory/'state.json').write_bytes(raw)
        manifest = json.dumps(dict(created_at=durable, files={'state.json':dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))})).encode()
        (directory/'manifest.json').write_bytes(manifest)
        pointer = dict(path=directory.relative_to(self.root).as_posix(), manifest_sha256=hashlib.sha256(manifest).hexdigest())
        (self.root/'current.json').write_text(json.dumps(pointer))
        return pointer

    def response(self, rows=None):
        stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=list(self.rows[0])); writer.writeheader(); writer.writerows(self.rows if rows is None else rows)
        response = MagicMock(); response.__enter__.return_value = response
        response.status = 200; response.headers = {}; response.read.return_value = stream.getvalue().encode()
        return response

    def refresh(self, old=None, checked=CHECK, response=None):
        before = copy.deepcopy(self.state)
        with patch.object(self.api, 'urlopen', return_value=response or self.response()) as fetch, patch.object(self.api, 'now', return_value=checked):
            result = self.api.refresh_shadow(self.state, {'injury_usage': old} if old else {}, self.root, checked)
        self.assertEqual(self.state, before)
        return result, fetch

    def test_latest_durable_prelock_version_and_distinct_missing_rows(self):
        selected = self.archive('2026-09-10T21:00:00+00:00', '2026-09-10T21:00:01+00:00', version=2)
        self.archive('2026-09-10T23:34:00+00:00', self.game['lock_at'], version=2)
        result, fetch = self.refresh()
        self.assertEqual(result['status'], 'READY'); fetch.assert_called_once()
        self.assertEqual(result['selected_games'][self.game['game_id']], selected)
        self.assertEqual(result['metrics']['cohort_rows'], 3)
        self.assertEqual(result['metrics']['joined'], 1)
        self.assertEqual(result['metrics']['observed_zero'], 1)
        self.assertEqual(result['metrics']['missing_target'], 2)
        self.assertIsNone(result['forecast_adjustment']); self.assertEqual(result['predictive_status'], 'UNAVAILABLE')
        self.assertNotIn('rows', result)

    def test_selected_pointer_stays_fixed_and_source_is_throttled(self):
        first, _ = self.refresh()
        self.archive('2026-09-10T22:00:00+00:00', '2026-09-10T22:00:01+00:00', version=2)
        again, fetch = self.refresh(first, checked='2026-09-11T13:00:00+00:00')
        fetch.assert_not_called(); self.assertEqual(again['selected_games'], first['selected_games'])
        self.assertEqual(again['metrics']['cohort_rows'], 2)
        self.assertEqual(again['report'], first['report'])
        later, fetch = self.refresh(again, checked='2026-09-12T13:00:00+00:00')
        fetch.assert_called_once(); self.assertEqual(later['selected_games'], first['selected_games'])

    def test_malformed_latest_capture_blocks_without_older_fallback(self):
        bad = self.archive('2026-09-10T22:00:00+00:00', '2026-09-10T22:00:01+00:00', malformed=True)
        result, fetch = self.refresh()
        self.assertEqual(result['status'], 'BLOCKED'); fetch.assert_not_called()
        self.assertEqual(result['selected_games'][self.game['game_id']], bad)

    def test_missing_inventory_and_pending_games_do_not_fetch(self):
        for path in (self.root/self.first['path']).iterdir(): path.unlink()
        (self.root/self.first['path']).rmdir()
        self.archive('2026-09-10T21:00:00+00:00', '2026-09-10T21:00:01+00:00', version=None)
        result, fetch = self.refresh(); fetch.assert_not_called()
        self.assertEqual(result['status'], 'WAITING')
        self.assertEqual(result['excluded_games'][0]['reason'], 'MISSING_PREGAME_INVENTORY')
        self.state['results'] = []
        result, fetch = self.refresh(); fetch.assert_not_called(); self.assertEqual(result['pending_games'], 1)

    def test_missing_original_cohort_stays_excluded_without_rescanning_or_backfill(self):
        self.state['results'][0]['game_id'] = '2026_01_NE_SEA'
        first, fetch = self.refresh(); fetch.assert_not_called()
        game = dict(self.game, game_id='2026_01_NE_SEA')
        self.archive('2026-09-10T21:00:00+00:00', '2026-09-10T21:00:01+00:00', game=game)
        with patch.object(self.api, 'load_archive', wraps=self.api.load_archive) as archive:
            result, fetch = self.refresh(first)
        fetch.assert_not_called(); self.assertEqual(result['status'], 'WAITING')
        self.assertEqual(result['excluded_games'], first['excluded_games'])
        self.assertEqual(result['selected_games'], {})
        self.assertEqual(archive.call_count, 1)

    def test_source_failure_preserves_excluded_cohort_through_recovery(self):
        missing = dict(self.final, game_id='2026_01_NE_SEA')
        self.state['results'].append(missing)
        first, _ = self.refresh()
        path = self.root/first['source']['path']; raw = path.read_bytes(); path.write_bytes(raw+b' ')
        failed, fetch = self.refresh(first)
        fetch.assert_not_called(); self.assertEqual(failed['status'], 'BLOCKED')
        self.assertEqual(failed['excluded_games'], first['excluded_games'])
        path.write_bytes(raw)
        self.archive('2026-09-10T21:00:00+00:00', '2026-09-10T21:00:01+00:00', game=dict(self.game, game_id=missing['game_id']))
        recovered, fetch = self.refresh(failed)
        fetch.assert_not_called(); self.assertEqual(recovered['status'], 'READY')
        self.assertEqual(recovered['selected_games'], first['selected_games'])
        self.assertEqual(recovered['excluded_games'], first['excluded_games'])
        self.assertEqual(recovered['metrics']['cohort_rows'], 2)

    def test_new_eligible_final_bypasses_daily_throttle_without_duplicate_samples(self):
        first, _ = self.refresh()
        game = dict(self.game, game_id='2026_02_SF_LA', week=2, kickoff='2026-09-11T14:00:00+00:00', lock_at='2026-09-11T13:00:00+00:00')
        self.archive('2026-09-11T12:00:00+00:00', '2026-09-11T12:00:01+00:00', game=game)
        self.state['results'].append(dict(self.final, game_id=game['game_id'], week=2, kickoff=game['kickoff'], finalized_at='2026-09-11T17:00:00+00:00'))
        self.state['schedule'].append(game)
        result, fetch = self.refresh(first, checked='2026-09-11T18:00:00+00:00')
        fetch.assert_called_once(); self.assertEqual(result['metrics']['games'], 2)
        self.assertEqual(result['metrics']['cohort_rows'], 4)

    def test_one_archive_shared_by_two_final_games_does_not_repeat_rows(self):
        game = dict(self.game, game_id='2026_02_SF_LA', week=2, kickoff='2026-09-11T14:00:00+00:00', lock_at='2026-09-11T13:00:00+00:00')
        selected = self.archive('2026-09-10T22:00:00+00:00', '2026-09-10T22:00:01+00:00', games=[self.game, game])
        self.state['results'].append(dict(self.final, game_id=game['game_id'], week=2, kickoff=game['kickoff'], finalized_at='2026-09-11T17:00:00+00:00'))
        result, _ = self.refresh(checked='2026-09-11T18:00:00+00:00')
        self.assertEqual(result['metrics']['games'], 2); self.assertEqual(result['metrics']['cohort_rows'], 4)
        self.assertEqual(result['selected_games'], {self.game['game_id']:selected, game['game_id']:selected})

    def test_non200_and_network_failures_are_preserved_and_throttled(self):
        for error in (HTTPError('https://example.invalid', 404, 'missing', {}, io.BytesIO(b'not yet')),
                      URLError('private error detail')):
            with self.subTest(error=type(error).__name__), patch.object(self.api, 'urlopen', side_effect=error) as fetch, patch.object(self.api, 'now', return_value=CHECK):
                result = self.api.refresh_shadow(self.state, {}, self.root, CHECK)
            fetch.assert_called_once(); self.assertEqual(result['status'], 'BLOCKED')
            self.assertNotIn('private error detail', json.dumps(result))
            self.assertTrue((self.root/result['last_attempt']['path']).is_file())
            again, fetch = self.refresh(result, checked='2026-09-11T13:00:00+00:00')
            fetch.assert_not_called(); self.assertEqual(again['status'], 'BLOCKED')

    def test_failed_http_body_read_retains_actual_http_status(self):
        error = HTTPError('https://example.invalid', 503, 'temporary', {}, io.BytesIO(b''))
        error.read = MagicMock(side_effect=OSError('private read error'))
        with patch.object(self.api, 'urlopen', side_effect=error), patch.object(self.api, 'now', return_value=CHECK):
            result = self.api.refresh_shadow(self.state, {}, self.root, CHECK)
        self.assertEqual(result['status'], 'BLOCKED')
        receipt = json.loads((self.root/result['last_attempt']['path']).read_bytes())
        self.assertEqual(receipt['http_status'], 503)
        self.assertEqual(receipt['failure'], 'REQUEST_FAILED')

    def test_incomplete_http_body_is_preserved_and_next_tick_is_throttled(self):
        response = self.response(); response.read.side_effect = IncompleteRead(b'partial', 100)
        result, fetch = self.refresh(response=response)
        fetch.assert_called_once(); self.assertEqual(result['status'], 'BLOCKED')
        receipt = json.loads((self.root/result['last_attempt']['path']).read_bytes())
        self.assertEqual(receipt['http_status'], 200); self.assertEqual(receipt['failure'], 'REQUEST_FAILED')
        self.assertEqual((self.root/result['last_attempt']['path']).with_name('response.bin').read_bytes(), b'partial')
        again, fetch = self.refresh(result, checked='2026-09-11T13:00:00+00:00')
        fetch.assert_not_called(); self.assertEqual(again['status'], 'BLOCKED')

    def test_failed_refresh_retains_valid_old_source_and_report(self):
        first, _ = self.refresh()
        with patch.object(self.api, 'urlopen', side_effect=URLError('private')), patch.object(self.api, 'now', return_value='2026-09-12T13:00:00+00:00'):
            failed = self.api.refresh_shadow(self.state, {'injury_usage':first}, self.root, '2026-09-12T13:00:00+00:00')
        self.assertEqual(failed['status'], 'BLOCKED'); self.assertEqual(failed['source'], first['source']); self.assertEqual(failed['report'], first['report'])

    def test_saved_target_report_and_selected_pointer_tamper_block(self):
        first, _ = self.refresh()
        for path in (self.root/first['source']['path'], (self.root/first['source']['path']).with_name('response.bin'),
                     self.root/first['report']['path'], self.root/self.first['path']/'state.json'):
            raw = path.read_bytes(); path.write_bytes(raw+b' ')
            try:
                result, fetch = self.refresh(first, checked='2026-09-11T13:00:00+00:00')
                self.assertEqual(result['status'], 'BLOCKED'); fetch.assert_not_called()
            finally: path.write_bytes(raw)

    def test_malformed_saved_report_is_blocked_without_uncaught_shape_error(self):
        first, _ = self.refresh(); raw = b'[]'; digest = hashlib.sha256(raw).hexdigest()
        relative = f'injury-usage/reports/{digest}.json'; (self.root/relative).write_bytes(raw)
        first['report'] = dict(path=relative, sha256=digest, bytes=len(raw))
        result, fetch = self.refresh(first)
        self.assertEqual(result['status'], 'BLOCKED'); fetch.assert_not_called()

    def test_invalid_final_and_duplicate_zero_target_cannot_admit(self):
        with patch.object(self.api, 'verify_finals', side_effect=ValueError('bad final')):
            result, fetch = self.refresh()
        self.assertEqual(result['status'], 'BLOCKED'); fetch.assert_not_called()
        rows = [self.rows[0], dict(self.rows[0], defense_snaps='NaN'), dict(self.rows[0], pfr_player_id='unknown')]
        result, _ = self.refresh(response=self.response(rows))
        self.assertEqual(result['metrics']['joined'], 0)
        self.assertEqual(result['metrics']['observed_zero'], 0)
        self.assertEqual(result['metrics']['unresolved_target_identities'], 1)
        self.assertEqual(result['metrics']['invalid_target_rows'], 2)


if __name__ == '__main__':
    unittest.main()
