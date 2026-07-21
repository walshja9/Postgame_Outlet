import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

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


class GateTests(unittest.TestCase):
    def test_parameter_search_ignores_holdout_results(self):
        before = [
            pgo_model.Game("train", 2017, "2017-09-01", "B", "A", 10.0, False),
        ]
        good_holdout = pgo_model.Game(
            "holdout", 2018, "2018-09-01", "B", "A", 50.0, False,
        )
        bad_holdout = pgo_model.Game(
            "holdout", 2018, "2018-09-01", "B", "A", -50.0, False,
        )
        self.assertEqual(
            pgo_model.select_parameters(before + [good_holdout]),
            pgo_model.select_parameters(before + [bad_holdout]),
        )

    def test_gate_requires_aggregate_and_every_season_to_win(self):
        aggregate = {"games": 2127, "model_mae": 10.0, "baseline_mae": 11.0}
        seasons = [
            {"season": 2018, "model_mae": 10.0, "baseline_mae": 11.0},
            {"season": 2019, "model_mae": 11.1, "baseline_mae": 11.0},
        ]
        checks = pgo_model.gate_checks(aggregate, seasons, 32)
        self.assertTrue(checks["aggregate_beats_baseline"])
        self.assertFalse(checks["every_season_beats_baseline"])
        self.assertFalse(all(checks.values()))

    def test_incomplete_sample_is_held_without_public_inputs(self):
        games = [
            pgo_model.Game(
                f"game-{season}", season, f"{season}-09-01",
                "B", "A", float((season % 7) + 1), False,
            )
            for season in range(1999, 2026)
        ]

        report, ratings = pgo_model.build_analysis(games)

        self.assertEqual(report["status"], "HOLD")
        self.assertFalse(report["checks"]["at_least_2000_holdout_games"])
        self.assertFalse(report["checks"]["all_32_current_teams"])
        self.assertIn("market spreads and odds", report["scope"]["excluded"])
        self.assertEqual(ratings, [])

    def test_hold_writes_report_but_not_ratings(self):
        report = {"status": "HOLD"}
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "ratings_2026_preseason.csv").write_text(
                "stale PASS output\n",
                encoding="utf-8",
            )
            written = pgo_model.write_outputs(Path(temp), report, [])
            self.assertFalse(written)
            self.assertTrue(Path(temp, "backtest.json").exists())
            self.assertFalse(Path(temp, "ratings_2026_preseason.csv").exists())

    def test_pass_writes_ranked_shadow_ratings(self):
        report = {"status": "PASS"}
        ratings = [
            {"team": "A", "rating": 1.25},
            {"team": "B", "rating": -1.25},
        ]
        with tempfile.TemporaryDirectory() as temp:
            written = pgo_model.write_outputs(Path(temp), report, ratings)
            with open(
                Path(temp, "ratings_2026_preseason.csv"),
                newline="",
                encoding="utf-8",
            ) as handle:
                rows = list(csv.DictReader(handle))

        self.assertTrue(written)
        self.assertEqual(
            rows,
            [
                {"rank": "1", "team": "A", "rating": "1.25"},
                {"rank": "2", "team": "B", "rating": "-1.25"},
            ],
        )


class CliTests(unittest.TestCase):
    def test_local_source_hold_records_hash_without_ratings(self):
        text = games_csv([
            row(
                f"game-{season}", season, "A", 10, "B", 20,
                gameday=f"{season}-09-01",
            )
            for season in range(1999, 2026)
        ])
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp, "games.csv")
            output = Path(temp, "research")
            source.write_text(text, encoding="utf-8")
            expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()

            with redirect_stdout(io.StringIO()):
                code = pgo_model.main([
                    "--source", str(source),
                    "--output-dir", str(output),
                ])
            report = json.loads(Path(output, "backtest.json").read_text())
            ratings_exist = Path(
                output, "ratings_2026_preseason.csv",
            ).exists()

        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(
            report["source"]["sha256"],
            expected_hash,
        )
        self.assertFalse(ratings_exist)

    def test_pinned_source_hash_mismatch_fails_before_analysis(self):
        with patch("pgo_model.read_source", return_value=(b"changed", "source")):
            with self.assertRaisesRegex(ValueError, "hash does not match"):
                pgo_model.main([])
