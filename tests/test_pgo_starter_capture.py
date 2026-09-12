"""Offline capture, review and activation of an official starter announcement."""
import base64
import copy
from http.client import HTTPException, IncompleteRead
import importlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from pgo_season import DEFAULT_ROOT, canonical, read_json, sha


ANNOUNCEMENT = '08e9cb25040d8852f92854213db350cfef036763f4beaa2c3967bc4287367976'
URL = 'https://www.atlantafalcons.com/news/tua-tagovailoa-cooper-rush-michael-penix-jr-state-of-qb-atlanta'


class Clock:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class PartialResponse:
    status = 200
    headers = {'Content-Type':'text/html', 'Content-Length':'999'}

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def geturl(self): return URL
    def read(self): raise IncompleteRead(b'partial response', 999)


class FailedResponse(PartialResponse):
    def read(self): raise HTTPException('protocol failed during body read')


class StarterCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = DEFAULT_ROOT / 'source-archive' / f'{ANNOUNCEMENT}.json'
        cls.saved_envelope = read_json(path)
        cls.real_html = base64.b64decode(cls.saved_envelope['body_base64'], validate=True)
        if sha(path.read_bytes()) != ANNOUNCEMENT:
            raise AssertionError('Pinned Falcons announcement changed')

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_starter_capture'),
                             'The starter capture command must exist')
        self.api = importlib.import_module('pgo_starter_capture')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'season'
        self.config = Path(self.tmp.name) / 'data' / 'pgo_starter_announcements.json'
        self.game = dict(game_id='2026_01_ATL_PIT', season=2026, week=1, game_type='REG',
                         home='PIT', away='ATL', kickoff='2026-09-13T17:00:00+00:00',
                         lock_at='2026-09-13T16:00:00+00:00')
        self.player = dict(team='ATL', gsis_id='00-0033662', full_name='Cooper Rush',
                           status='ACT', position='QB', season='2026')
        self.roster_ref = dict(url='https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2026.csv.gz',
                               path='source-archive/'+'1'*64+'.csv.gz', sha256='1'*64,
                               bytes=1, captured_at='2026-09-12T18:54:50+00:00')
        self.context = (copy.deepcopy(self.game), [copy.deepcopy(self.player)],
                        copy.deepcopy(self.roster_ref), '2026-09-12T18:55:09+00:00')
        self.statement = self.saved_envelope['decision']['statement']
        self.context_patch = patch.object(self.api, '_context', side_effect=lambda root, game_id: copy.deepcopy(self.context))
        self.context_patch.start(); self.addCleanup(self.context_patch.stop)

    def response(self, status=200, final_url=URL, body=None):
        return dict(status=status, final_url=final_url, headers={'Content-Type':'text/html', 'X-Test':'exact'},
                    body=self.real_html if body is None else body)

    def capture(self, *, url=URL, response=None, times=('2026-09-12T19:00:00+00:00',
                                                        '2026-09-12T19:00:01+00:00')):
        fetch = Mock(return_value=response or self.response())
        path = self.api.capture(url, self.game['game_id'], 'ATL', self.player['gsis_id'], self.statement,
                                root=self.root, fetch=fetch, clock=Clock(*times))
        return path, fetch

    def review(self, draft, when='2026-09-12T19:01:00+00:00'):
        return self.api.review(draft, root=self.root, config=self.config, clock=Clock(when))

    def test_real_falcons_html_captures_reviews_and_activates_without_forecast_mutation(self):
        draft, fetch = self.capture()
        captured = read_json(draft)
        self.assertTrue(captured['successful'])
        self.assertEqual(base64.b64decode(captured['body_base64']), self.real_html)
        self.assertEqual((captured['started_at'], captured['captured_at']),
                         ('2026-09-12T19:00:00+00:00', '2026-09-12T19:00:01+00:00'))
        self.assertEqual(captured['headers'], {'Content-Type':'text/html', 'X-Test':'exact'})
        fetch.assert_called_once_with(URL)
        self.assertFalse(self.config.exists(), 'Capture must not activate a starter')

        reviewed = self.review(draft)
        receipt = read_json(reviewed); source = receipt['source']
        envelope = read_json(self.root / source['path'])
        self.assertEqual(envelope['raw_sha256'], sha(self.real_html))
        self.assertEqual(envelope['reviewed_at'], '2026-09-12T19:01:00+00:00')
        self.assertEqual(envelope['decision']['full_name'], 'Cooper Rush')
        self.assertFalse(self.config.exists(), 'Review must not activate a starter')

        rule = self.api.activate(reviewed, root=self.root, config=self.config,
                                 clock=Clock('2026-09-12T19:02:00+00:00', '2026-09-12T19:02:01+00:00'))
        self.assertEqual(rule, dict(game_id=self.game['game_id'], source=source))
        self.assertEqual(read_json(self.config), dict(schema_version=1, announcements=[rule]))

    def test_preflight_url_refusal_never_calls_the_request_seam(self):
        draft, fetch = self.capture(url='https://example.com/news/not-official')
        receipt = read_json(draft)
        fetch.assert_not_called()
        self.assertFalse(receipt['successful'])
        self.assertIsNone(receipt['status'])
        self.assertIn('official HTTPS URL', receipt['error'])
        with self.assertRaises(ValueError):
            self.review(draft)

    def test_redirect_and_http_error_receipts_retain_exact_observations(self):
        cases = [
            (self.response(status=302, final_url='https://www.atlantafalcons.com/news/other', body=b'redirect'),
             '2026-09-12T19:03:00+00:00'),
            (self.response(status=503, body=b'unavailable'), '2026-09-12T19:04:00+00:00'),
        ]
        for response, start in cases:
            end = start.replace(':00+00:00', ':01+00:00')
            with self.subTest(status=response['status']):
                draft, _ = self.capture(response=response, times=(start, end))
                saved = read_json(draft)
                self.assertFalse(saved['successful'])
                self.assertEqual(saved['status'], response['status'])
                self.assertEqual(saved['final_url'], response['final_url'])
                self.assertEqual(base64.b64decode(saved['body_base64']), response['body'])
                self.assertEqual(saved['captured_at'], end)
                with self.assertRaises(ValueError): self.review(draft)

    def test_partial_http_read_retains_failed_receipt(self):
        opener = Mock(); opener.open.return_value = PartialResponse()
        with patch.object(self.api, 'build_opener', return_value=opener):
            draft = self.api.capture(URL, self.game['game_id'], 'ATL', self.player['gsis_id'], self.statement,
                                     root=self.root, fetch=self.api._request,
                                     clock=Clock('2026-09-12T19:06:00+00:00', '2026-09-12T19:06:01+00:00'))
        saved = read_json(draft)
        self.assertFalse(saved['successful'])
        self.assertEqual(saved['status'], 200)
        self.assertEqual(base64.b64decode(saved['body_base64']), b'partial response')
        self.assertIn('incomplete', saved['error'].lower())

    def test_backward_clock_retains_failed_receipt(self):
        drifted, _ = self.capture(times=('2026-09-12T19:07:01+00:00', '2026-09-12T19:07:00+00:00'))
        receipt = read_json(drifted)
        self.assertFalse(receipt['successful'])
        self.assertIn('backwards', receipt['error'].lower())

    def test_http_protocol_failures_retain_receipts_and_available_metadata(self):
        path = self.api.capture(URL, self.game['game_id'], 'ATL', self.player['gsis_id'], self.statement,
                                root=self.root, fetch=Mock(side_effect=HTTPException('bad status line')),
                                clock=Clock('2026-09-12T19:08:00+00:00', '2026-09-12T19:08:01+00:00'))
        saved = read_json(path)
        self.assertFalse(saved['successful'])
        self.assertIsNone(saved['status'])
        self.assertIn('bad status line', saved['error'])

        opener = Mock(); opener.open.return_value = FailedResponse()
        with patch.object(self.api, 'build_opener', return_value=opener):
            path = self.api.capture(URL, self.game['game_id'], 'ATL', self.player['gsis_id'], self.statement,
                                    root=self.root, fetch=self.api._request,
                                    clock=Clock('2026-09-12T19:09:00+00:00', '2026-09-12T19:09:01+00:00'))
        saved = read_json(path)
        self.assertFalse(saved['successful'])
        self.assertEqual(saved['status'], 200)
        self.assertEqual(saved['headers']['Content-Length'], '999')
        self.assertEqual(base64.b64decode(saved['body_base64']), b'')
        self.assertIn('protocol failed', saved['error'])

    def test_tampered_capture_and_unsafe_receipt_paths_are_rejected(self):
        draft, _ = self.capture()
        draft.write_bytes(draft.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.review(draft)
        with self.assertRaisesRegex(ValueError, 'path'):
            self.review(Path(self.tmp.name) / 'outside.json')

    def test_review_rejects_wrong_current_game_and_future_capture(self):
        draft, _ = self.capture()
        wrong = copy.deepcopy(self.context)
        wrong[0]['week'] = 2
        self.context = wrong
        with self.assertRaises(ValueError): self.review(draft)
        self.context = (copy.deepcopy(self.game), [copy.deepcopy(self.player)],
                        copy.deepcopy(self.roster_ref), '2026-09-12T19:02:00+00:00')
        with self.assertRaisesRegex(ValueError, 'future'):
            self.review(draft, '2026-09-12T19:01:00+00:00')

    def test_activation_detects_config_drift_and_same_team_conflict(self):
        draft, _ = self.capture()
        reviewed = self.review(draft)
        self.config.parent.mkdir(parents=True)
        self.config.write_bytes(canonical(dict(schema_version=1, announcements=[])))
        with self.assertRaisesRegex(ValueError, 'drift'):
            self.api.activate(reviewed, root=self.root, config=self.config,
                              clock=Clock('2026-09-12T19:02:00+00:00', '2026-09-12T19:02:01+00:00'))

        self.config.unlink()
        old_review = self.review(draft, '2026-09-12T19:02:30+00:00')
        old_source = read_json(old_review)['source']
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_bytes(canonical(dict(schema_version=1, announcements=[
            dict(game_id=self.game['game_id'], source=old_source)])))
        new_review = self.review(draft, '2026-09-12T19:03:00+00:00')
        with self.assertRaisesRegex(ValueError, 'already has'):
            self.api.activate(new_review, root=self.root, config=self.config,
                              clock=Clock('2026-09-12T19:04:00+00:00', '2026-09-12T19:04:01+00:00'))

    def test_activation_revalidates_roster_evidence_clock_and_cutoff(self):
        draft, _ = self.capture()
        reviewed = self.review(draft)
        self.context[1][0]['status'] = 'RES'
        with self.assertRaisesRegex(ValueError, 'current ACT quarterback'):
            self.api.activate(reviewed, root=self.root, config=self.config,
                              clock=Clock('2026-09-12T19:02:00+00:00', '2026-09-12T19:02:01+00:00'))
        self.context[1][0]['status'] = 'ACT'
        with self.assertRaises(ValueError):
            self.api.activate(reviewed, root=self.root, config=self.config,
                              clock=Clock('2026-09-12T19:00:30+00:00', '2026-09-12T19:00:31+00:00'))
        with self.assertRaisesRegex(ValueError, 'T-60'):
            self.api.activate(reviewed, root=self.root, config=self.config,
                              clock=Clock(self.game['lock_at'], self.game['lock_at']))

    def test_review_and_activation_reject_a_roster_older_than_24_hours(self):
        draft, _ = self.capture()
        self.context[2]['captured_at'] = '2026-09-11T18:00:00+00:00'
        with self.assertRaisesRegex(ValueError, 'roster.*stale'):
            self.review(draft)

        self.context[2]['captured_at'] = '2026-09-12T18:54:50+00:00'
        reviewed = self.review(draft)
        self.context[2]['captured_at'] = '2026-09-11T18:00:00+00:00'
        with self.assertRaisesRegex(ValueError, 'roster.*stale'):
            self.api.activate(reviewed, root=self.root, config=self.config,
                              clock=Clock('2026-09-12T19:02:00+00:00', '2026-09-12T19:02:01+00:00'))

    def test_activation_rechecks_cutoff_immediately_before_atomic_write(self):
        draft, _ = self.capture()
        reviewed = self.review(draft)
        with self.assertRaisesRegex(ValueError, 'T-60'):
            self.api.activate(reviewed, root=self.root, config=self.config,
                              clock=Clock('2026-09-12T19:02:00+00:00', self.game['lock_at']))
        self.assertFalse(self.config.exists())

    def test_activation_detects_config_change_while_staging(self):
        draft, _ = self.capture()
        reviewed = self.review(draft)
        concurrent = canonical(dict(schema_version=1, announcements=[
            dict(game_id='2026_02_ATL_PIT', source={'unrelated':True})]))
        real_fsync = os.fsync

        def drift(descriptor):
            self.config.parent.mkdir(parents=True, exist_ok=True)
            self.config.write_bytes(concurrent)
            return real_fsync(descriptor)

        with patch.object(os, 'fsync', side_effect=drift):
            with self.assertRaisesRegex(ValueError, 'drift'):
                self.api.activate(reviewed, root=self.root, config=self.config,
                                  clock=Clock('2026-09-12T19:02:00+00:00',
                                              '2026-09-12T19:02:01+00:00'))
        self.assertEqual(self.config.read_bytes(), concurrent)

    def test_activation_fsyncs_before_its_final_clock_and_replace(self):
        draft, _ = self.capture()
        reviewed = self.review(draft)
        events = []
        real_fsync, real_replace = os.fsync, os.replace

        def fsync(descriptor):
            events.append('fsync')
            return real_fsync(descriptor)

        clock = Mock(side_effect=lambda: (events.append('clock') or
                     ('2026-09-12T19:02:00+00:00' if events.count('clock') == 1
                      else '2026-09-12T19:02:01+00:00')))

        def replace(source, target):
            events.append('replace')
            return real_replace(source, target)

        with patch.object(os, 'fsync', side_effect=fsync), patch.object(os, 'replace', side_effect=replace):
            self.api.activate(reviewed, root=self.root, config=self.config, clock=clock)
        self.assertEqual(events[-3:], ['fsync', 'clock', 'replace'])

    def test_activation_refuses_an_existing_cooperative_lock(self):
        draft, _ = self.capture()
        reviewed = self.review(draft)
        self.config.parent.mkdir(parents=True)
        lock = self.config.parent / f'.{self.config.name}.activation.lock'
        lock.write_bytes(b'busy')
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.api.activate(reviewed, root=self.root, config=self.config,
                              clock=Clock('2026-09-12T19:02:00+00:00',
                                          '2026-09-12T19:02:01+00:00'))
        self.assertEqual(lock.read_bytes(), b'busy')


if __name__ == '__main__':
    unittest.main()
