"""Current projections are independent of the immutable weekly forecasting record."""
import copy
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pgo_expected_starters as starters
import pgo_season as season
import pgo_season_availability as availability
from pgo_season_rollover import load_archive
from tests.test_pgo_starter_revision import ANNOUNCEMENT, DEPTH, GAME, ROSTER, RUSH


class CurrentProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opening = season.bootstrap()
        cls.inputs = {}
        for kind, digest in (('roster', ROSTER), ('depth', DEPTH)):
            path = f'source-archive/{digest}.csv.gz'
            raw = (season.DEFAULT_ROOT/path).read_bytes()
            if season.sha(raw) != digest:
                raise AssertionError('Pinned current-projection fixture changed')
            cls.inputs[kind] = raw, dict(url=season.URLS[kind], path=path,
                sha256=digest, bytes=len(raw))
        envelope = season.read_json(season.DEFAULT_ROOT/f'source-archive/{ANNOUNCEMENT}.json')
        envelope['purpose'] = 'current_projection'
        cls.announcement = season.canonical(envelope)
        digest = season.sha(cls.announcement)
        cls.source = dict(url=envelope['url'], path=f'source-archive/{digest}.json',
            sha256=digest, bytes=len(cls.announcement), captured_at=envelope['captured_at'])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = '2026-09-13T17:05:00Z'
        self.state = copy.deepcopy(self.opening)
        self.state.update(checked_at=self.clock, schedule=copy.deepcopy(self.opening['weeks'][0]['games']),
                          source_captures=[])
        for game in self.state['weeks'][0]['games']:
            game.get('availability', {}).pop('source_archive', None)
        self.original = copy.deepcopy(self.state)
        for raw, ref in self.inputs.values():
            path = self.root/ref['path']; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        (self.root/self.source['path']).write_bytes(self.announcement)
        self.config = self.root/'current-config.json'
        self.config.write_bytes(season.canonical(dict(schema_version=1,
            announcements=[dict(game_id=GAME, source=self.source)])))
        self.addCleanup(patch.stopall)
        patch.object(season, 'now', side_effect=lambda: self.clock).start()
        patch.object(availability, '_clock', side_effect=lambda now=None: season.utc(now or self.clock)).start()
        patch.object(season, 'fetch_source', side_effect=self.fetch_source).start()
        # Return each source's own URL while retaining a deliberately unavailable official report.
        patch.object(availability, '_fetch', side_effect=lambda url:
            dict(body=b'<html></html>', status=200, final_url=url)).start()
        patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network call')).start()
        patch.object(availability, 'urlopen', side_effect=AssertionError('Unexpected availability call')).start()

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_current_projection'),
                             'Separate current-projection module is missing')
        return importlib.import_module('pgo_current_projection')

    def fetch_source(self, url, root):
        self.assertEqual(Path(root), self.root)
        kind = next((kind for kind in self.inputs if season.URLS[kind] == url), None)
        self.assertIsNotNone(kind, 'Opening-week replay must not fetch incomplete-week statistics')
        raw, ref = self.inputs[kind]
        return raw, dict(ref, captured_at=self.clock)

    def refresh(self):
        api = self.module()
        self.assertTrue(hasattr(starters, 'CURRENT_CONFIG'), 'Separate current-starter configuration is missing')
        with patch.object(starters, 'CURRENT_CONFIG', self.config):
            refs = api.refresh(self.state, self.root)
        self.state['checked_at'] = self.clock
        self.state['source_captures'] = [ref for ref in refs if 'path' in ref]
        return api

    def test_real_model_can_build_postlock_current_games_without_revising_weekly_records(self):
        self.assertIn('current_projection', inspect.signature(season.build_next).parameters,
                      'build_next cannot yet generate a separate post-lock projection')
        selected = season.select_roster(season.csv_rows(self.inputs['roster'][0]),
            season.csv_rows(self.inputs['depth'][0]), self.clock)
        _, normal, _ = season.build_next(self.state, self.state['schedule'], [], self.root,
                                         completed=0, selected=selected)
        self.assertIsNone(next(g for g in normal['games'] if g['game_id']==GAME)['margin'])
        selected['ATL'] = next(row for row in season.csv_rows(self.inputs['roster'][0])
                               if row['gsis_id']==RUSH)
        ranking, current, _ = season.build_next(self.state, self.state['schedule'], [], self.root,
            completed=0, selected=selected, current_projection=True)
        game = next(g for g in current['games'] if g['game_id']==GAME)
        self.assertIsInstance(game['margin'], float)
        self.assertEqual(game['expected_qbs']['ATL'], 'Cooper Rush')
        self.assertEqual(ranking['completed_week'], 0)
        self.assertEqual(self.state, self.original)
        final = dict(game_id=GAME, week=1, home_score=21, away_score=20,
                     finalized_at=self.clock)
        _, current, _ = season.build_next(self.state, self.state['schedule'], [final], self.root,
            completed=0, selected=selected, current_projection=True)
        self.assertNotIn(GAME, {g['game_id'] for g in current['games']})

    def test_postkickoff_current_projection_replays_actual_clock_and_preserves_archives(self):
        original_dir = season.save_state(self.state, self.root)
        original_pointer = season.read_json(self.root/'current.json')
        original_bytes = {path:path.read_bytes() for path in original_dir.iterdir()}
        self.clock = '2026-09-13T17:06:00Z'
        api = self.refresh()
        self.assertEqual(self.state['current_projection_check']['status'], 'READY',
                         self.state['current_projection_check'])
        game = self.state['current_projections'][GAME]
        self.assertEqual(self.state['weeks'], self.original['weeks'])
        self.assertEqual(self.state['rankings'], self.original['rankings'])
        self.assertEqual(game['expected_qbs']['ATL'], 'Cooper Rush')
        self.assertIsInstance(game['margin'], float)
        self.assertEqual(game['issued_at'], self.clock)
        self.assertEqual(game['inputs_as_of'], self.clock)
        self.assertTrue(game['after_lock'])
        self.assertTrue(game['after_kickoff'])
        self.assertIs(game['eligible_for_locked_record'], False)
        self.assertIsNone(game['confidence'])
        self.assertEqual(game['grade'], 'NOT_ELIGIBLE')
        self.assertEqual(game['rankings']['completed_week'], 0)
        self.assertEqual(game['availability']['teams']['ATL']['expected_qb_gsis_id'], RUSH)
        season.save_state(self.state, self.root)
        self.assertEqual(season.load_current(self.root), self.state)
        self.assertEqual(load_archive(self.root, season.read_json(self.root/'current.json'))[0], self.state)
        self.assertEqual(load_archive(self.root, original_pointer)[0], self.original)
        for path, raw in original_bytes.items():
            self.assertEqual(path.read_bytes(), raw)
        for field, bad in [('eligible_for_locked_record', True), ('after_kickoff', False),
                           ('issued_at', '2026-09-13T17:07:00Z')]:
            malformed = copy.deepcopy(self.state); malformed['current_projections'][GAME][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                api.validate(malformed, self.root)
        source = self.root/self.source['path']; source.write_bytes(source.read_bytes()+b' ')
        for loader in (lambda: season.load_current(self.root),
                       lambda: load_archive(self.root, season.read_json(self.root/'current.json'))):
            with self.assertRaises(ValueError): loader()

    def test_current_projection_rejects_tampered_opponent_qb_rankings_and_numbers(self):
        api = self.refresh()
        cases = []
        wrong_qb = copy.deepcopy(self.state)
        wrong_qb['current_projections'][GAME]['expected_qbs']['PIT'] = 'Invented Starter'
        cases.append(('opponent QB', wrong_qb))
        wrong_rank = copy.deepcopy(self.state)
        next(row for row in wrong_rank['current_projections'][GAME]['rankings']['teams']
             if row['team']=='PIT')['qb_gsis_id'] = '00-9999999'
        cases.append(('ranking QB', wrong_rank))
        wrong_score = copy.deepcopy(self.state)
        game = wrong_score['current_projections'][GAME]
        game['home_points'] += 1
        game['margin'] += 1
        game['total'] += 1
        game['explanation']['rest_adjustment'] += 1
        cases.append(('coherent invented score', wrong_score))
        wrong_probability = copy.deepcopy(self.state)
        wrong_probability['current_projections'][GAME]['win_probability'] = .999
        cases.append(('invented probability', wrong_probability))
        for label, malformed in cases:
            with self.subTest(label=label), self.assertRaises(ValueError):
                api.validate(malformed, self.root)

    def test_current_projection_fsync_crossing_kickoff_stamps_actual_durable_clock(self):
        api = self.module()
        self.assertTrue(hasattr(api, 'stamp_durable'), 'Current projection lacks actual durable-write metadata')
        self.clock = '2026-09-13T16:59:00Z'
        self.refresh()
        game = self.state['current_projections'][GAME]
        self.assertFalse(game['after_kickoff'])
        clocks = iter(['2026-09-13T16:59:59Z', '2026-09-13T17:00:01Z', '2026-09-13T17:00:02Z'])
        with patch.object(season, 'now', side_effect=lambda: next(clocks)):
            directory = season.save_state(self.state, self.root)
        game = self.state['current_projections'][GAME]
        self.assertEqual(game['issued_at'], '2026-09-13T16:59:00Z')
        self.assertEqual(game['inputs_as_of'], '2026-09-13T16:59:00Z')
        self.assertEqual(game['durable_at'], '2026-09-13T17:00:01Z')
        self.assertTrue(game['durable_after_lock'])
        self.assertTrue(game['durable_after_kickoff'])
        self.assertIs(game['eligible_for_locked_record'], False)
        self.assertEqual(season.load_current(self.root), self.state)
        self.assertEqual(season.read_json(directory/'manifest.json')['created_at'], '2026-09-13T17:00:02Z')
        malformed = copy.deepcopy(self.state); malformed['current_projections'][GAME]['durable_after_kickoff'] = False
        with self.assertRaises(ValueError): api.validate(malformed, self.root)

    def test_new_current_record_overwrites_supplied_stale_durable_metadata(self):
        self.refresh()
        game = self.state['current_projections'][GAME]
        game.update(durable_at='2026-09-13T17:05:01Z', durable_after_lock=True, durable_after_kickoff=True)
        self.clock = '2026-09-13T17:06:00Z'; self.state['checked_at'] = self.clock
        clocks = iter([self.clock, '2026-09-13T17:06:01Z'])
        with patch.object(season, 'now', side_effect=lambda: next(clocks)):
            directory = season.save_state(self.state, self.root)
        self.assertEqual(game['durable_at'], self.clock, 'A new record must use this save actual fsync')
        self.assertTrue(game['durable_after_lock'])
        self.assertTrue(game['durable_after_kickoff'])
        self.assertEqual(season.read_json(directory/'manifest.json')['created_at'], '2026-09-13T17:06:01Z')
        self.assertEqual(season.load_current(self.root), self.state)

    def test_changed_current_record_overwrites_retained_old_durable_metadata(self):
        self.refresh()
        original_directory = season.save_state(self.state, self.root)
        protected = {path:path.read_bytes() for path in original_directory.iterdir()}
        game = self.state['current_projections'][GAME]
        old_durable = game['durable_at']
        # A second archived official receipt is valid model evidence and changes
        # the core while preserving exactly one roster/depth/stats source each.
        receipt = copy.deepcopy(game['starter_announcements'][0]['source'])
        game['source_captures'].append(copy.deepcopy(receipt))
        game['rankings']['source_captures'].append(copy.deepcopy(receipt))
        self.clock = '2026-09-13T17:06:00Z'; self.state['checked_at'] = self.clock
        clocks = iter([self.clock, '2026-09-13T17:06:01Z'])
        with patch.object(season, 'now', side_effect=lambda: next(clocks)):
            directory = season.save_state(self.state, self.root)
        self.assertNotEqual(game['durable_at'], old_durable)
        self.assertEqual(game['durable_at'], self.clock, 'Changed coherent core requires this save actual fsync')
        self.assertEqual(season.read_json(directory/'manifest.json')['created_at'], '2026-09-13T17:06:01Z')
        self.assertEqual(season.load_current(self.root), self.state)
        for path, raw in protected.items():
            self.assertEqual(path.read_bytes(), raw, 'Previously admitted archive must stay immutable')

    def test_unchanged_current_record_preserves_exact_durable_metadata(self):
        self.refresh()
        original_directory = season.save_state(self.state, self.root)
        protected = {path:path.read_bytes() for path in original_directory.iterdir()}
        before = copy.deepcopy(self.state['current_projections'][GAME])
        self.clock = '2026-09-13T17:06:00Z'; self.state['checked_at'] = self.clock
        # One clock read proves an unchanged record needs no timestamp rewrite.
        clocks = iter([self.clock])
        with patch.object(season, 'now', side_effect=lambda: next(clocks)):
            season.save_state(self.state, self.root)
        self.assertEqual(self.state['current_projections'][GAME], before)
        self.assertEqual(season.load_current(self.root), self.state)
        for path, raw in protected.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_current_projection_requires_clock_before_durable_archive(self):
        api = self.module()
        self.assertIn('durable', inspect.signature(api.validate).parameters,
                      'Current projection lacks a durable-write clock check')
        self.refresh()
        with self.assertRaises(ValueError):
            api.validate(self.state, self.root, durable='2026-09-13T17:04:00Z')

    def test_prelock_current_config_does_not_bypass_ordinary_revision_workflow(self):
        self.clock = '2026-09-13T15:45:00Z'
        self.refresh()
        self.assertEqual(self.state.get('current_projections', {}), {})
        self.assertEqual(self.state['weeks'], self.original['weeks'])

    def test_verified_replacement_itself_out_has_no_current_score_or_pick(self):
        report = ('<title>NFL Injury Report - Week 1 of the 2026 Season</title>'
                  '<h2 class="d3-o-section-sub-title"><span>Falcons</span></h2><table>'
                  '<tr><th>Player</th><th>Position</th><th>Injuries</th><th>Practice Status</th><th>Game Status</th></tr>'
                  '<tr><td>Cooper Rush</td><td>QB</td><td>Knee</td>'
                  '<td>Did Not Participate</td><td>Out</td></tr></table>')
        with patch.object(availability, '_fetch', side_effect=lambda url:
                dict(body=report.encode() if url==availability.REPORT_URL else b'<html></html>',
                     status=200, final_url=url)):
            self.refresh()
        game = self.state['current_projections'][GAME]
        self.assertIn('Cooper Rush is OUT', game['blocked_reason'])
        for field in ('margin', 'total', 'home_points', 'away_points', 'pick', 'win_probability'):
            self.assertIsNone(game.get(field), field)
        self.assertEqual(self.state['weeks'], self.original['weeks'])
        first = copy.deepcopy(game)
        self.clock = '2026-09-13T17:06:00Z'
        self.refresh()
        second = self.state['current_projections'][GAME]
        self.assertEqual(second, first, 'Missing reports must retain the earlier confirmed unavailable projection')
        self.assertEqual(self.state['current_projection_check']['status'], 'BLOCKED')

    def test_missing_current_authority_never_substitutes_default_qb_or_mutates_original(self):
        self.config.write_bytes(season.canonical(dict(schema_version=1, announcements=[])))
        self.refresh()
        self.assertEqual(self.state.get('current_projections', {}), {})
        self.assertEqual(self.state['weeks'], self.original['weeks'])
        self.assertEqual(self.state['rankings'], self.original['rankings'])

    def test_unverified_current_source_blocks_only_current_projection_and_retains_original(self):
        source = self.root/self.source['path']; source.write_bytes(source.read_bytes()+b' ')
        self.refresh()
        self.assertEqual(self.state.get('current_projections', {}), {})
        self.assertEqual(self.state['current_projection_check']['status'], 'BLOCKED')
        self.assertEqual(self.state['weeks'], self.original['weeks'])


if __name__ == '__main__':
    unittest.main()
