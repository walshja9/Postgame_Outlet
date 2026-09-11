import copy
import json
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import pgo_model_updates as view

ROOT = Path(__file__).resolve().parents[1]


class ModelUpdateTests(unittest.TestCase):
    def snapshot(self):
        data = json.loads((ROOT / 'docs/evidence/forecast-lab-2026/september-08-corrected/snapshot.json').read_bytes())
        data['edition'] = 'pgo-postseason-week1-2026-09-09'
        data['generated_at'] = '2026-09-09T20:00:00+00:00'
        data['history'] = {'game_types': ['REG', 'WC', 'DIV', 'CON', 'SB'],
                           'through': '2026-02-09T00:00:00+00:00',
                           'regular_games': 272, 'postseason_games': 13, 'scoring_season': 2025}
        data['validation'] = {'status': 'FAIL', 'baseline_mae': 10.1, 'candidate_mae': 10.2,
                              'games': 2127, 'season_wins': 3,
                              'interval': {'lower': -0.1, 'upper': 0.04},
                              'limitations': ['Reused seasons <not new evidence>']}
        for team in data['teams']:
            team.update(baseline_rank=team['rank'], baseline_rating=team['rating'])
        for game in data['games']:
            game.update(corrected_margin=game['margin'], corrected_total=game['total'])
        return data

    def test_all_team_candidate_is_visible_separate_and_uses_saved_values(self):
        snapshot = self.snapshot()
        before = copy.deepcopy(snapshot)
        rendered = view.render_updates(snapshot)
        self.assertIn('Postseason history', rendered)
        self.assertIn('EXPERIMENTAL / HOLD', rendered)
        self.assertIn('did not pass', rendered)
        self.assertIn('2127', rendered)
        self.assertIn('10.100', rendered)
        self.assertIn('10.200', rendered)
        self.assertIn('&lt;not new evidence&gt;', rendered)
        self.assertEqual(rendered.count('data-postseason-team='), 32)
        self.assertEqual(rendered.count('data-postseason-game-id='), 16)
        self.assertEqual(rendered.count('class="forecast-reason-row"'), 16)
        self.assertNotIn('data-weekly-game-id=', rendered)
        self.assertNotIn('data-snapshot-game-id=', rendered)
        self.assertIn('NE 23, SEA 24', rendered)
        self.assertIn('NE 23.1, SEA 23.5', rendered)
        self.assertIn('SEA by 0.4 points', rendered)
        self.assertIn('regular season and playoffs', rendered)
        self.assertIn('non-QB player quality', rendered)
        self.assertIn('Before the venue adjustment: NE by 1.2 points', rendered)
        self.assertNotIn('href="#latest-inactive-notes"', rendered)
        self.assertEqual(snapshot, before)

    def test_actual_verified_candidate_keeps_issued_values_and_separate_identity(self):
        import pgo_forecast_lab as lab
        import pgo_forecast_postseason as model
        snapshot = model.load_snapshot(view.DEFAULT_DIR)
        protected = list(view.DEFAULT_DIR.glob('*')) + list((view.DEFAULT_DIR.parent / 'weekly-postseason').glob('*.json'))
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected if path.is_file()}
        rendered = view.render_current_updates()
        ne = next(team for team in snapshot['teams'] if team['team'] == 'NE')
        self.assertIn(f'New England moves from #{ne["baseline_rank"]} to #{ne["rank"]}', rendered)
        self.assertIn('did not pass the historical screen and remains EXPERIMENTAL / HOLD', rendered)
        self.assertIn('SEA by 3.3 points', rendered)
        self.assertEqual(rendered.count('data-postseason-team='), 32)
        self.assertEqual(rendered.count('data-postseason-game-id='), 16)
        self.assertEqual(rendered.count('data-depth-team='), 32)
        self.assertEqual(rendered.count('Before the venue adjustment:'), 16)
        self.assertIn('Game designation: Out', rendered)
        self.assertIn('Game designation: Questionable', rendered)
        self.assertIn('ACT roster defenders', rendered)
        self.assertIn('0 of 16 saved September 9 forecasts', rendered)
        self.assertIn('data-weekly-cutoff=', rendered)
        self.assertIn('function updateWeeklyLocks()', lab.FORECAST_DISPLAY_SCRIPT)
        self.assertIn('function openFragment(hash)', lab.FORECAST_DISPLAY_SCRIPT)
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before})

    def test_main_board_links_original_editions_to_existing_lab_archive(self):
        compact=view.render_current_updates(include_original=False)
        archive=view.render_current_updates()
        self.assertIn('id="pgo-season"',compact)
        self.assertIn('forecast-lab.html#opening-week-editions',compact)
        self.assertIn('forecast-lab.html#latest-inactive-notes',compact)
        self.assertNotIn('data-postseason-game-id=',compact)
        self.assertIn('id="opening-week-editions"',archive)
        self.assertEqual(archive.count('data-postseason-game-id='),16)
        self.assertGreater(len(archive)-len(compact),500000)

    def test_moved_edition_fragments_keep_exact_destinations_without_duplicate_current_ids(self):
        earlier='<div id="postseason-rating-NE" data-game-id="not-a-fragment"><p id="latest-inactive-notes"></p><i id="keep"></i></div>'
        links=view._original_editions_link(earlier,'<div id="keep"></div>')
        for key in ('opening-week-editions','postseason-rating-NE','latest-inactive-notes'):
            self.assertIn(f'id="{key}"',links)
            self.assertIn(f'href="forecast-lab.html#{key}"',links)
        self.assertNotIn('id="keep"',links)
        self.assertNotIn('not-a-fragment',links)

    def test_selected_postseason_board_leads_and_previous_models_roundtrip(self):
        import pgo_current_board as board
        import pgo_forecast_lab as lab
        from tests.test_pgo_current_board import CurrentBoardTests
        from tests.test_pgo_forecast_lab import ForecastLabTests
        fixture = CurrentBoardTests()
        fixture.setUp()
        updates = view.render_updates(self.snapshot())
        with patch.object(view, 'render_current_updates', return_value=updates):
            page = board.add_current_board(fixture.page, fixture.snapshot, fixture.mccabe)
        self.assertIn('<h2>PGO Power Rankings &mdash; Experimental</h2>', page)
        self.assertLess(page.index('data-postseason-team='), page.index('data-current-pgo-team='))
        self.assertIn('<details class="pgo-previous-models" id="previous-models">', page)
        self.assertIn('<summary>Compare previous models</summary>', page)
        self.assertLess(page.index('id="previous-models"'), page.index('data-current-pgo-team='))
        self.assertEqual(page.count('data-postseason-team='), 32)
        self.assertEqual(page.count('data-current-pgo-team='), 32)
        self.assertEqual(page.count(lab.FORECAST_DISPLAY_SCRIPT), 1)
        self.assertEqual(board.strip_current_board(page), fixture.page)
        self.assertIn('Injury reports are shown as context', page)
        self.assertIn('not numerical adjustments', page)
        archive = ForecastLabTests()
        with patch.object(view, 'render_current_updates', return_value=updates):
            lab_page = lab.render_lab(archive.synthetic_lock(), [], [],
                snapshot=archive.synthetic_snapshot(), weekly={'games': [], 'revisions': []})
        self.assertLess(lab_page.index('data-postseason-team='), lab_page.index('Weekly predictions'))
        self.assertIn('<summary>Compare previous models</summary>', lab_page)
        self.assertEqual(lab_page.count('data-postseason-game-id='), 16)
        self.assertIn('September 7 preseason baseline', lab_page)
        self.assertIn('Original frozen forecast record', lab_page)
        with patch.object(view, 'render_current_updates', return_value=''):
            fallback = board.add_current_board(fixture.page, fixture.snapshot, fixture.mccabe)
        self.assertNotIn('id="previous-models"', fallback)
        self.assertIn('data-current-pgo-team=', fallback)
        self.assertEqual(board.strip_current_board(fallback), fixture.page)

    def test_passing_screen_does_not_promote_and_invalid_core_is_rejected(self):
        snapshot = self.snapshot()
        snapshot['validation']['status'] = 'PASS'
        rendered = view.render_updates(snapshot)
        self.assertIn('passed the historical screen', rendered)
        self.assertIn('EXPERIMENTAL / HOLD', rendered)
        for key, value in (('edition', 'old-edition'), ('teams', snapshot['teams'][:-1])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                view.render_updates({**snapshot, key: value})
        broken = copy.deepcopy(snapshot)
        broken['games'][0]['total'] += 1
        with self.assertRaises(ValueError):
            view.render_updates(broken)

    def test_candidate_ledger_uses_shared_results_without_duplicate_rows(self):
        snapshot = self.snapshot()
        snapshot['_manifest_sha256'] = 'current-source'
        game = {**snapshot['games'][0], 'source_edition': snapshot['edition'],
                'source_generated_at': snapshot['generated_at'],
                'source_manifest_sha256': snapshot['_manifest_sha256'],
                'lock_at': '2026-09-09T23:20:00Z'}
        result = {'game_id': game['game_id'], 'home_score': 24, 'away_score': 21, 'actual_margin': 3}
        before = copy.deepcopy((snapshot, game, result))
        rendered = view.render_updates(snapshot, weekly={'games': [game]}, results=[result])
        self.assertEqual(rendered.count('data-postseason-game-id='), 1)
        self.assertIn('1 of 1', rendered)
        self.assertIn('Average miss', rendered)
        self.assertIn('NE 21, SEA 24', rendered)
        self.assertIn('Before the venue adjustment', rendered)
        self.assertIn('September 8 corrected margin', rendered)
        rendered = view.render_updates(snapshot, weekly={'games': [{**game, 'source_manifest_sha256': 'older'}]})
        self.assertNotIn('Before the venue adjustment', rendered)
        self.assertIn('Saved score calculation', rendered)
        self.assertEqual((snapshot, game, result), before)

    def test_current_panel_reads_one_shared_result_feed_and_filters_candidate_games(self):
        import pgo_forecast_lab as lab
        import pgo_forecast_postseason as model
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidate = root / 'forecast-lab-2026/september-09-postseason'
            ledger = candidate.parent / 'weekly-postseason'
            original = candidate.parent / 'weekly'
            candidate.mkdir(parents=True)
            ledger.mkdir()
            (candidate / 'manifest.json').write_bytes(b'verified manifest')
            game = {**snapshot['games'][0], 'source_edition': snapshot['edition'],
                    'source_generated_at': snapshot['generated_at'],
                    'source_manifest_sha256': hashlib.sha256(b'verified manifest').hexdigest(),
                    'lock_at': '2026-09-09T23:20:00Z'}
            other = snapshot['games'][1]
            results = [{'game_id': item['game_id'], 'home_score': 24, 'away_score': 21,
                        'actual_margin': 3} for item in (game, other)]
            with patch.object(view, 'DEFAULT_DIR', candidate), \
                    patch.object(model, 'load_snapshot', return_value=snapshot), \
                    patch.object(lab, 'WEEKLY_DIR', original), \
                    patch.object(lab.pgo_forecast_weekly, 'load_weekly',
                                 side_effect=[{'games': [game]}, {'games': [game, other]}]) as load, \
                    patch.object(lab, 'load_results', return_value=(results, [])) as accepted:
                rendered = view.render_current_updates()
            self.assertEqual([call.args[0] for call in load.call_args_list], [ledger, original])
            accepted.assert_called_once()
            self.assertEqual(accepted.call_args.args[0], original / 'results')
            self.assertEqual(len(accepted.call_args.args[1]['games']), 2)
            self.assertIn('1 of 1 saved September 9 forecasts', rendered)
            self.assertEqual(rendered.count('data-postseason-game-id='), 1)
            self.assertIn('Before the venue adjustment', rendered)

    def test_depth_evidence_is_descriptive_and_missing_history_is_not_zero(self):
        codes = [team['team'] for team in self.snapshot()['teams']]
        depth = {'status': 'DESCRIPTIVE / NOT IN MODEL', 'forecast_adjustment': None,
                 'generated_at': '2026-09-09T21:00:00Z', 'inputs_as_of': '2026-09-09T20:00:00Z',
                 'historical_window': '2025 REG + POST', 'sources': [],
                 'limitations': ['No admitted historical pregame depth'], 'teams': []}
        for code in codes:
            depth['teams'].append({'team': code, 'active_defenders': 1, 'listed_starters': 0,
                'listed_backups': 1, 'backups_with_prior_defensive_snaps': 0,
                'backups_without_prior_defensive_snaps': 1, 'unlisted_defenders': 0,
                'depth_snapshot_at': None, 'coverage_status': 'PARTIAL', 'players': []})
        depth['teams'][0]['players'] = [{'name': '<Rookie>', 'gsis_id': 'rookie-id',
            'position': 'LB', 'roster_status': 'ACT', 'depth_rows': [{'position': 'LB', 'rank': 2}],
            'history_status': 'NO_PRIOR_HISTORY', 'defensive_snaps': None,
            'def_sacks': None, 'def_qb_hits': None, 'def_tackles_for_loss': None,
            'def_pass_defended': None, 'def_interceptions': None,
            'observed_games': 0, 'previous_teams': [], 'depth_status': 'MATCHED'}]
        before = copy.deepcopy(depth)
        rendered = view.render_updates(depth=depth)
        self.assertIn('DESCRIPTIVE / NOT IN MODEL', rendered)
        self.assertIn('does not change any rating or forecast', rendered)
        self.assertIn('&lt;Rookie&gt;', rendered)
        self.assertNotIn('<Rookie>', rendered)
        self.assertIn('Unavailable', rendered)
        self.assertIn('rookie', rendered.lower())
        self.assertEqual(rendered.count('data-depth-team='), 32)
        self.assertEqual(depth, before)
        coverage = {codes[0]: {'captured_at': '2026-09-09T21:16:09Z',
                    'source_url': 'https://example.com/official-injury',
                    'observations': [{'gsis_id': 'rookie-id', 'game_status': 'Out',
                                      'practice_status': 'Did Not Participate'}]}}
        annotated = view._depth_evidence(depth, coverage)
        self.assertIn('Game designation: Out', annotated)
        self.assertIn('Earlier forecast-input report notes captured', annotated)
        self.assertIn('Data coverage:', annotated)
        coverage[codes[0]]['observations'][0]['game_status'] = ''
        annotated = view._depth_evidence(depth, coverage)
        self.assertIn('Practice report: Did Not Participate', annotated)
        self.assertNotIn('Game designation: Out', annotated)
        coverage[codes[0]]['observations'][0]['gsis_id'] = 'different-id'
        self.assertNotIn('Practice report:', view._depth_evidence(depth, coverage))
        with self.assertRaises(ValueError):
            view.render_updates(depth={**depth, 'forecast_adjustment': 0.0})

    def test_defense_test_summary_stays_separate_from_postseason_forecasts(self):
        summary = {**self.snapshot()['validation'], 'manifest_sha256': 'a' * 64,
                   'report_url': 'https://example.com/defense-test'}
        rendered = view.render_defense_test(summary)
        self.assertIn('Defensive-production test', rendered)
        self.assertIn('did not pass', rendered)
        self.assertIn('EXPERIMENTAL / HOLD', rendered)
        self.assertIn('not added to the postseason forecasts', rendered)
        self.assertIn('10.200', rendered)
        self.assertIn('3 of 8 seasons', rendered)
        self.assertIn('a' * 64, rendered)
        self.assertNotIn('data-postseason-team', rendered)
        self.assertNotIn('data-postseason-game-id', rendered)
        with self.assertRaises(ValueError):
            view.render_defense_test({**summary, 'report_url': 'javascript:alert(1)'})

    def test_missing_optional_updates_are_empty(self):
        self.assertEqual(view.render_updates(), '')
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / 'evidence/forecast-lab-2026/september-09-postseason'
            with patch.object(view, 'DEFAULT_DIR', candidate), patch.object(view, 'DEFENSE_TEST_DIR', Path(temp) / 'missing-run'):
                self.assertEqual(view.render_current_updates(), '')
                candidate.mkdir(parents=True)
                (candidate / 'manifest.json').write_bytes(b'not valid JSON')
                with self.assertRaises(ValueError):
                    view.render_current_updates()


if __name__ == '__main__':
    unittest.main()
