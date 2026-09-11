import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pgo_season as season
import pgo_season_rollover as rollover


class RolloverTests(unittest.TestCase):
    def test_archive_hash_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / 'runs/20260911T120000000000Z'
            directory.mkdir(parents=True)
            raw = season.canonical({'checked_at': '2026-09-11T12:00:00+00:00'})
            (directory / 'state.json').write_bytes(raw)
            manifest = season.canonical({'files': {'state.json': {'sha256': season.sha(raw), 'bytes': len(raw)}}})
            (directory / 'manifest.json').write_bytes(manifest)
            pointer = {'path': directory.relative_to(root).as_posix(), 'manifest_sha256': season.sha(manifest)}
            self.assertEqual(rollover.load_archive(root, pointer)[0]['checked_at'], '2026-09-11T12:00:00+00:00')
            (directory / 'state.json').write_bytes(raw + b' ')
            with self.assertRaisesRegex(ValueError, 'state hash'):
                rollover.load_archive(root, pointer)
            with self.assertRaisesRegex(ValueError, 'archive path'):
                rollover.load_archive(root, {**pointer, 'path': '../outside'})

    def test_locked_forecast_confidence_and_grade_boundaries(self):
        game = {'game_id': 'a', 'kickoff': '2026-09-10T00:00:00+00:00', 'margin': 3,
                'confidence': {'points': 12, 'earned_points': None}, 'grade': 'PENDING'}
        before = {'checked_at': '2026-09-10T00:00:00+00:00', 'weeks': [{'games': [game]}], 'results': []}
        after = copy.deepcopy(before)
        after['weeks'][0]['games'][0]['confidence']['earned_points'] = 12
        after['weeks'][0]['games'][0]['grade'] = 'W'
        self.assertEqual(rollover.check_preserved(before, after), 1)
        for field, value in [('margin', 4), ('confidence', {'points': 11, 'earned_points': 12})]:
            broken = copy.deepcopy(after)
            broken['weeks'][0]['games'][0][field] = value
            with self.assertRaisesRegex(ValueError, 'Locked forecast'):
                rollover.check_preserved(before, broken)
        after['weeks'][0]['games'] = []
        with self.assertRaisesRegex(ValueError, 'removed'):
            rollover.check_preserved(before, after)

    def test_existing_final_cannot_change(self):
        before = {'checked_at': '2026-09-10T00:00:00+00:00', 'weeks': [], 'results': [{'game_id': 'a', 'home_score': 13}]}
        after = copy.deepcopy(before)
        after['results'][0]['home_score'] = 14
        with self.assertRaisesRegex(ValueError, 'Accepted final'):
            rollover.check_preserved(before, after)

    def test_crossing_lock_requires_unchanged_forecast_confidence_and_book(self):
        game = dict(game_id='a', kickoff='2026-09-10T01:00:00Z', margin=3,
                    issued_at='2026-09-09T23:58:00Z', confidence=dict(points=12, earned_points=None))
        book = dict(game_id='a', kickoff=game['kickoff'], home_handicap=-3,
                    issued_at=game['issued_at'], ats_pick='home')
        before = dict(checked_at='2026-09-09T23:59:00Z', weeks=[dict(games=[game])],
                      results=[], ats=dict(games=[book]))
        for changed in ('forecast', 'confidence', 'book'):
            after = copy.deepcopy(before)
            if changed == 'forecast':
                after['weeks'][0]['games'][0]['margin'] = 4
            elif changed == 'confidence':
                after['weeks'][0]['games'][0]['confidence']['points'] = 11
            else:
                after['ats']['games'][0]['home_handicap'] = -4
            # A changed record saved strictly before the cutoff is eligible.
            after['checked_at'] = '2026-09-09T23:59:30Z'
            rollover.check_preserved(before, after)
            # A pre-lock issued_at cannot excuse a durable write at T-60.
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'Locked'):
                rollover.check_preserved(before, after, '2026-09-10T00:00:00Z')
            after['checked_at'] = '2026-09-10T00:00:01Z'
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'Locked'):
                rollover.check_preserved(before, after)
        unchanged = copy.deepcopy(before)
        unchanged['checked_at'] = '2026-09-10T00:00:01Z'
        self.assertEqual(rollover.check_preserved(before, unchanged), 1)

    def test_final_must_replay_explicit_provider_status(self):
        from tests.test_pgo_season import SeasonTests
        fixture = SeasonTests()
        game, board = fixture.game(), fixture.board()
        captured = '2026-09-10T00:00:00Z'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = season.canonical(board)
            ref = dict(path='sources/' + season.sha(raw) + '.json', sha256=season.sha(raw), bytes=len(raw), captured_at=captured)
            (root / 'sources').mkdir()
            (root / ref['path']).write_bytes(raw)
            result = season.parse_scoreboard(board, [game], captured)['results'][0]
            state = dict(schedule=[game], results=[dict(result, source=ref)], checked_at=captured)
            self.assertEqual(rollover.verify_finals(state, root, 1), set())
            state['results'][0]['home_score'] += 1
            with self.assertRaisesRegex(ValueError, 'explicit provider FINAL'):
                rollover.verify_finals(state, root, 1)
            state['results'] = []
            self.assertEqual(rollover.verify_finals(state, root, 1), {game['game_id']})
            with self.assertRaisesRegex(ValueError, 'after edition'):
                rollover.source_bytes(root, ref, '2026-09-09T00:00:00Z')

    def test_wrong_week_final_cannot_satisfy_completed_inventory(self):
        state = {'schedule': [{'game_id': 'a', 'week': 1}],
                 'results': [{'game_id': 'a', 'week': 2}]}
        with patch.object(rollover, 'source_bytes', side_effect=AssertionError('Wrong identity must fail before source read')):
            with self.assertRaisesRegex(ValueError, 'Final week differs'):
                rollover.verify_finals(state, '.', 1)

    def test_statistics_require_full_matching_production(self):
        from tests.test_pgo_season_model import SeasonModelTests
        SeasonModelTests.setUpClass()
        args = SeasonModelTests().inputs()
        games = [dict(g, provider_scores={k: str(g[k]) for k in ('home_score', 'away_score')}) for g in args['completed_games']]
        state = dict(schedule=games, results=args['completed_games'], rankings=dict(inputs_as_of=args['inputs_as_of'],
                     source_captures=[dict(url=season.URLS[k]) for k in ('team', 'player')]))
        with patch.object(rollover, 'source_bytes', return_value=b'fixture'), patch.object(season, 'csv_rows', side_effect=[args['team_rows'], args['qb_rows']]):
            rollover.verify_statistics(state, '.', 1)
        for teams, players in [(args['team_rows'][:-1], args['qb_rows']), (args['team_rows'], args['qb_rows'][:-1]),
                               (args['team_rows'], args['qb_rows'] + [args['qb_rows'][0]])]:
            with self.subTest(teams=len(teams), players=len(players)), patch.object(rollover, 'source_bytes', return_value=b'fixture'), patch.object(season, 'csv_rows', side_effect=[teams, players]):
                with self.assertRaises(ValueError):
                    rollover.verify_statistics(state, '.', 1)

    def test_transition_states_and_missing_slate(self):
        from tests.test_pgo_season import SeasonTests
        fixture = SeasonTests()
        old_game, new_game = fixture.game(), fixture.game(2)
        before = dict(checked_at='2026-09-10T00:00:00Z', weeks=[dict(week=1, games=[old_game])], results=[], rankings=dict(completed_week=0))
        after = copy.deepcopy(before)
        after.update(checked_at='2026-09-10T01:00:00Z', current_week=2, schedule=[old_game, new_game], source_captures=[dict(url=season.URLS['schedule'])])
        after['rankings'].update(completed_week=1, edition='next', teams=[dict(team=t, rank=i, rating=0.) for i, t in enumerate(season.pgo_sources.CURRENT_TEAMS, 1)])
        after['weeks'].append(dict(week=2, source_edition='next', games=[new_game]))
        pointer = dict(path='runs/20260910T010000000000Z')
        prior_pointer = dict(path='runs/20260910T000000000000Z')
        def load(root, ref):
            return (after, {'previous': prior_pointer}) if ref == pointer else (before, {})
        with patch.object(season, 'load_current', return_value=after), patch.object(season, 'read_json', return_value=pointer), patch.object(rollover, 'load_archive', side_effect=load), patch.object(rollover, 'verify_finals', return_value=set()), patch.object(rollover, 'verify_statistics'), patch.object(rollover, 'source_bytes', return_value=b'fixture'), patch.object(season, 'parse_schedule', return_value=after['schedule']):
            report = rollover.observe('.')
            self.assertEqual(report['status'], 'VERIFIED')
            self.assertEqual(report['checks']['rankings'], 32)
            after['weeks'][1]['games'] = []
            with self.assertRaisesRegex(ValueError, 'fixture inventory'):
                rollover.observe('.')
            after['rankings']['completed_week'] = 0
            self.assertEqual(rollover.observe('.')['status'], 'WAITING')


if __name__ == '__main__':
    unittest.main()
