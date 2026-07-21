import csv
import io
import tempfile
import unittest
from pathlib import Path

import pgo_model


FIELDS = [
    "game_id", "season", "game_type", "gameday", "away_team",
    "away_score", "home_team", "home_score", "location", "spread_line",
]


def games_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def row(game_id, season, away, away_score, home, home_score, **overrides):
    value = {
        "game_id": game_id,
        "season": season,
        "game_type": "REG",
        "gameday": f"{season}-09-01",
        "away_team": away,
        "away_score": away_score,
        "home_team": home,
        "home_score": home_score,
        "location": "Home",
        "spread_line": "-99.5",
    }
    value.update(overrides)
    return value


class ParsingTests(unittest.TestCase):
    def test_uses_only_completed_regular_season_team_results(self):
        text = games_csv([
            row("one", 2025, "OAK", 10, "SD", 20),
            row("two", 2025, "A", 10, "B", 20, game_type="POST"),
            row("three", 2025, "A", "", "B", ""),
        ])

        games = pgo_model.parse_games(text)

        self.assertEqual(len(games), 1)
        self.assertEqual((games[0].away, games[0].home), ("LV", "LAC"))
        self.assertEqual(games[0].margin, 10.0)

    def test_market_line_does_not_change_parsed_game(self):
        first = row("one", 2025, "A", 10, "B", 20, spread_line="-2.5")
        second = {**first, "spread_line": "+12.5"}
        self.assertEqual(
            pgo_model.parse_games(games_csv([first])),
            pgo_model.parse_games(games_csv([second])),
        )


class WalkForwardTests(unittest.TestCase):
    def test_prediction_is_recorded_before_result_update(self):
        games = [
            pgo_model.Game("one", 2020, "2020-09-01", "B", "A", 12.0, False),
            pgo_model.Game("two", 2020, "2020-09-08", "B", "A", 0.0, False),
        ]
        params = pgo_model.Parameters(0.2, 0.5, 2.0, 20.0)

        predictions, _ = pgo_model.walk_forward(games, params)

        self.assertEqual(predictions[0].predicted, 2.0)
        self.assertEqual(predictions[1].predicted, 4.0)

    def test_new_season_regresses_existing_ratings(self):
        games = [
            pgo_model.Game("one", 2020, "2020-09-01", "B", "A", 12.0, False),
            pgo_model.Game("two", 2021, "2021-09-01", "B", "A", 0.0, False),
        ]
        params = pgo_model.Parameters(0.2, 0.5, 2.0, 20.0)

        predictions, _ = pgo_model.walk_forward(games, params)

        self.assertEqual(predictions[1].predicted, 3.0)
