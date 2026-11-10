import json
import tempfile
import unittest
from pathlib import Path

import pgo_season as season


GAME = {'game_id': '2026_09_LV_SF', 'kickoff': '2026-11-08T21:05:00+00:00'}
FIX = {'2026_09_LV_SF': {'game_id': '2026_09_LV_SF', 'source_kickoff': '2026-11-08T21:05:00+00:00',
                         'kickoff': '2026-11-08T21:25:00+00:00', 'reviewed': 'test'}}


class KickoffCorrectionTests(unittest.TestCase):
    def test_applies_while_source_shows_superseded_time(self):
        self.assertEqual(season.apply_kickoff_correction(GAME, FIX)['kickoff'], '2026-11-08T21:25:00+00:00')

    def test_noop_once_source_publishes_corrected_time(self):
        game = dict(GAME, kickoff='2026-11-08T21:25:00Z')
        self.assertIs(season.apply_kickoff_correction(game, FIX), game)

    def test_other_source_change_requires_review(self):
        with self.assertRaisesRegex(ValueError, 'review rescheduling'):
            season.apply_kickoff_correction(dict(GAME, kickoff='2026-11-09T01:20:00+00:00'), FIX)

    def test_uncorrected_games_untouched(self):
        game = {'game_id': 'other', 'kickoff': '2026-11-08T18:00:00+00:00'}
        self.assertIs(season.apply_kickoff_correction(game, FIX), game)

    def test_loader_validates_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'c.json'
            self.assertEqual(season.load_kickoff_corrections(path), {})
            path.write_text(json.dumps([{'game_id': 'x'}]))
            with self.assertRaises(ValueError):
                season.load_kickoff_corrections(path)
            path.write_text(json.dumps(list(FIX.values()) * 2))
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                season.load_kickoff_corrections(path)

    def test_repository_correction_file_is_valid(self):
        self.assertIn('2026_09_LV_SF', season.load_kickoff_corrections())


if __name__ == '__main__':
    unittest.main()
