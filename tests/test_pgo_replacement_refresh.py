import copy
from contextlib import ExitStack
import csv
import gzip
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pgo_season as season
from research.pgo_replacement_depth_20260910 import capture


OLD = '2026-09-10T20:00:00Z'
NOW = '2026-09-12T04:00:00Z'


class ReplacementRefreshTests(unittest.TestCase):
    def archive(self, root, url, captured_at):
        rows = ([dict(season='2026', team='NE', position='LB', status='ACT', gsis_id='00-0000001',
                      full_name='Test Defender', first_name='Test', last_name='Defender')]
                if url == season.URLS['roster'] else
                [dict(team='NE', pos_grp='Base 3-4 D', pos_abb='LB', pos_rank='1', dt=OLD,
                      gsis_id='00-0000001', player_name='Test Defender')])
        text = io.StringIO(); writer = csv.DictWriter(text, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
        raw = gzip.compress(text.getvalue().encode(), mtime=0); digest = season.sha(raw)
        relative = 'source-archive/' + digest + '.csv.gz'; (root / relative).parent.mkdir(exist_ok=True)
        (root / relative).write_bytes(raw)
        return raw, dict(url=url, captured_at=captured_at, sha256=digest, bytes=len(raw), path=relative)

    def state(self, root):
        old = dict(game_id='2026_01_NE_SEA', season=2026, week=1, game_type='REG', home='SEA', away='NE',
                   kickoff='2026-09-10T00:20:00Z', lock_at='2026-09-09T23:20:00Z', issued_at='2026-09-09T18:00:00Z',
                   inputs_as_of='2026-09-09T17:00:00Z', source_edition='original', margin=3.25, total=45.,
                   home_points=24.125, away_points=20.875, blocked_reason=None,
                   confidence=dict(points=10, win_probability=.6, expected_points=6., added_after_lock=False))
        upcoming = dict(copy.deepcopy(old), game_id='2026_01_SF_LA', home='LAR', away='SF',
                        kickoff='2026-09-13T17:00:00Z', lock_at='2026-09-13T16:00:00Z')
        result = dict(game_id=old['game_id'], season=2026, week=1, game_type='REG', home_team='SEA', away_team='NE',
                      kickoff=old['kickoff'], home_score=13, away_score=10, actual_margin=3,
                      finalized_at='2026-09-10T04:00:00Z', event_id='1')
        refs = [self.archive(root, season.URLS[kind], OLD)[1] for kind in ('roster', 'depth')]
        state = dict(schema_version=1, season=2026, current_week=1, status='READY', checked_at=OLD,
                     rankings=dict(completed_week=0), weeks=[dict(week=1, games=[old, upcoming])],
                     schedule=[copy.deepcopy(old), copy.deepcopy(upcoming)], results=[result],
                     source_captures=refs, sources=copy.deepcopy(refs))
        with patch.object(season, 'legacy_models', return_value=[]), patch.object(capture, '_history', return_value=({}, None)):
            season.decorate(state, state['results'])
            state['replacement_depth'] = capture.capture(state, root, OLD)
        with patch.object(season, 'now', return_value=OLD): season.save_state(state, root)
        return state

    def production(self, root, before, clock, *, fetch=None, availability=None):
        """Keep the real refresh/save/load/capture path; replace only external inputs."""
        import pgo_penalty_monitor, pgo_totals_monitor, pgo_weights_monitor, pgo_ats
        with ExitStack() as stack:
            stack.enter_context(patch.object(season, 'now', side_effect=lambda: clock[0]))
            stack.enter_context(patch.object(season, 'legacy_models', return_value=[]))
            stack.enter_context(patch.object(season, 'fetch_inputs', return_value=(copy.deepcopy(before['schedule']), copy.deepcopy(before['results']), [], {})))
            fetched = stack.enter_context(patch.object(season, 'fetch_source', side_effect=fetch or (lambda url, target: self.archive(target, url, clock[0]))))
            if availability is not None:
                stack.enter_context(patch.object(season, 'refresh_availability', side_effect=availability))
            selected = stack.enter_context(patch.object(season, 'select_roster', side_effect=AssertionError('Source maintenance selected QBs')))
            rebuilt = stack.enter_context(patch.object(season, 'build_next', side_effect=AssertionError('Source maintenance rebuilt rankings')))
            stack.enter_context(patch.object(capture, '_history', return_value=({}, None)))
            for module, method in ((pgo_penalty_monitor, 'refresh_shadow'), (pgo_totals_monitor, 'refresh_shadow'),
                                   (pgo_weights_monitor, 'refresh_shadow'), (pgo_ats, 'refresh')):
                stack.enter_context(patch.object(module, method, return_value=dict(status='READY', games=[])))
            result = season.refresh(root)
            self.assertEqual(season.load_current(root), result)
            self.assertEqual(selected.call_count, 0); self.assertEqual(rebuilt.call_count, 0)
            return result, fetched.call_count

    def test_stale_off_day_sources_refresh_before_state_clock_and_preserve_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); before = self.state(root); original_pointer = (root / 'current.json').read_bytes()
            result, calls = self.production(root, before, [NOW])
            self.assertEqual(calls, 2)
            self.assertEqual(result['status'], 'READY')
            self.assertEqual(result['replacement_source_check']['status'], 'READY')
            self.assertEqual(result['replacement_depth']['status'], 'DESCRIPTIVE / NOT IN MODEL')
            self.assertEqual(result['weeks'], before['weeks'])
            self.assertEqual(result['rankings'], before['rankings'])
            self.assertEqual(result['results'], before['results'])
            self.assertEqual(result['model_records'], before['model_records'])
            refs = result['source_captures']; self.assertEqual(len(refs), 2)
            self.assertEqual({ref['captured_at'] for ref in refs}, {NOW})
            self.assertEqual({ref['sha256'] for ref in refs}, {ref['sha256'] for ref in before['source_captures']})
            self.assertTrue(all('published_at' not in ref for ref in refs))
            ne = next(t for t in result['replacement_depth']['teams'] if t['team'] == 'NE')
            self.assertEqual(season.utc(ne['depth_snapshot_at']), season.utc(OLD))
            self.assertNotEqual((root / 'current.json').read_bytes(), original_pointer)
            later, calls = self.production(root, result, ['2026-09-12T04:15:00Z'])
            self.assertEqual(calls, 0)
            self.assertEqual(later['replacement_depth']['source_as_of'], result['replacement_depth']['source_as_of'])

    def test_partial_failure_retains_successful_receipt_and_original_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); before = self.state(root)
            def fetch(url, target):
                if url == season.URLS['depth']: raise OSError('provider unavailable')
                return self.archive(target, url, NOW)
            result, calls = self.production(root, before, [NOW], fetch=fetch)
            self.assertEqual(calls, 2)
            self.assertEqual(result['status'], 'READY')
            self.assertEqual(result['replacement_source_check']['status'], 'BLOCKED')
            self.assertEqual(result['replacement_depth']['status'], 'BLOCKED')
            self.assertEqual(result['replacement_depth']['generated_at'], before['replacement_depth']['generated_at'])
            self.assertEqual(result['replacement_depth']['teams'], before['replacement_depth']['teams'])
            self.assertEqual(result['weeks'], before['weeks'])
            self.assertEqual(result['model_records'], before['model_records'])
            self.assertEqual([ref['url'] for ref in result['source_captures']], [season.URLS['roster']])

            recovered, calls = self.production(root, result, ['2026-09-12T04:15:00Z'])
            self.assertEqual(calls, 1)
            self.assertEqual(recovered['replacement_source_check']['status'], 'READY')
            self.assertEqual(recovered['replacement_depth']['status'], 'DESCRIPTIVE / NOT IN MODEL')
            self.assertEqual({ref['url'] for ref in recovered['source_captures']}, {season.URLS['roster'], season.URLS['depth']})
            roster = next(ref for ref in recovered['source_captures'] if ref['url'] == season.URLS['roster'])
            self.assertEqual(roster['captured_at'], NOW)
            self.assertEqual(recovered['weeks'], before['weeks'])
            self.assertEqual(recovered['model_records'], before['model_records'])

    def test_conflicting_source_hashes_at_same_time_block_only_replacement_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); before = self.state(root)
            raw, first = self.archive(root, season.URLS['roster'], NOW)
            raw = gzip.compress(gzip.decompress(raw) + b'\n', mtime=0)
            digest = season.sha(raw); relative = 'source-archive/' + digest + '.csv.gz'
            (root / relative).write_bytes(raw)
            conflict = dict(first, sha256=digest, path=relative, bytes=len(raw), captured_at='2026-09-12T04:00:00+00:00')
            before['source_captures'] += [first, conflict]
            before['checked_at'] = '2026-09-12T04:00:00Z'
            with patch.object(season, 'now', return_value=NOW): season.save_state(before, root)
            result, calls = self.production(root, before, ['2026-09-12T04:15:00Z'])
            self.assertEqual(result['status'], 'READY')
            self.assertEqual(result['replacement_source_check']['status'], 'BLOCKED')
            self.assertEqual(result['replacement_source_check']['blocked_reason'], 'Replacement source refresh unavailable: roster.')
            self.assertEqual(result['replacement_depth']['status'], 'BLOCKED')
            self.assertEqual(result['model_records'], before['model_records'])

    def test_slow_source_fetch_crossing_lock_restores_original_pick_and_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); before = self.state(root); clock = ['2026-09-13T15:59:59Z']
            def forecast(state, target):
                state['weeks'][0]['games'][1]['margin'] = 99.
                state['weeks'][0]['games'][1]['confidence']['points'] = 99
                return []
            def fetch(url, target):
                clock[0] = '2026-09-13T16:00:01Z'
                return self.archive(target, url, clock[0])
            result, calls = self.production(root, before, clock, fetch=fetch, availability=forecast)
            game = result['weeks'][0]['games'][1]; original = before['weeks'][0]['games'][1]
            self.assertEqual(calls, 2)
            self.assertEqual(result['checked_at'], clock[0])
            for key in ('margin', 'total', 'home_points', 'away_points', 'confidence', 'issued_at', 'inputs_as_of', 'source_edition'):
                self.assertEqual(game[key], original[key])
            self.assertEqual(game['forecast_status'], 'LOCKED')
            self.assertEqual(result['replacement_depth']['games'], [])

    def test_future_receipt_is_not_admitted_or_allowed_to_block_primary_grades(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); before = self.state(root)
            def fetch(url, target): return self.archive(target, url, '2026-09-12T05:00:00Z')
            result, calls = self.production(root, before, [NOW], fetch=fetch)
            self.assertEqual(result['status'], 'READY')
            self.assertEqual(result['replacement_source_check']['status'], 'BLOCKED')
            self.assertEqual(result['replacement_depth']['status'], 'BLOCKED')
            self.assertEqual(result['source_captures'], [])
            self.assertEqual(result['model_records'], before['model_records'])

    def test_no_future_games_skips_source_fetch(self):
        self.assertTrue(hasattr(season, 'refresh_replacement_sources'), 'Source-only maintenance helper is missing')
        state = dict(weeks=[], results=[], sources=[])
        with patch.object(season, 'now', return_value=NOW), patch.object(season, 'fetch_source') as fetch:
            season.refresh_replacement_sources(state, Path('unused'))
        self.assertEqual(fetch.call_count, 0)
        self.assertEqual(state['replacement_source_check']['status'], 'IDLE')


if __name__ == '__main__':
    unittest.main()
