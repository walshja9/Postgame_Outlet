import math
import unittest

import pgo_fantasy


class FantasyContractTests(unittest.TestCase):
    def test_source_inventory_is_baseline_only_and_requires_status_and_scoring(self):
        specs = pgo_fantasy.fantasy_source_specs()

        self.assertEqual(len(specs), 13)
        self.assertEqual(
            {(spec.name, spec.season) for spec in specs},
            {("schedule_results", None)}
            | {
                (name, season)
                for name in ("weekly_rosters", "player_weekly_stats")
                for season in range(2020, 2026)
            },
        )
        roster_columns = {
            column
            for spec in specs
            if spec.name == "weekly_rosters"
            for column in spec.required_columns
        }
        player_columns = {
            column
            for spec in specs
            if spec.name == "player_weekly_stats"
            for column in spec.required_columns
        }
        self.assertIn("status", roster_columns)
        self.assertEqual(
            {
                "passing_yards",
                "passing_tds",
                "passing_interceptions",
                "passing_2pt_conversions",
                "rushing_yards",
                "rushing_tds",
                "rushing_2pt_conversions",
                "receptions",
                "receiving_yards",
                "receiving_tds",
                "receiving_2pt_conversions",
                "special_teams_tds",
                "fumbles_lost_total",
            },
            player_columns & pgo_fantasy.SCORING_FIELDS,
        )
        inventory_text = " ".join(
            (spec.name + " " + " ".join(spec.required_columns)).lower()
            for spec in specs
        )
        for prohibited in (
            "injury",
            "practice",
            "inactive",
            "depth_chart",
            "pff",
            "betting",
        ):
            self.assertNotIn(prohibited, inventory_text)

    def test_half_ppr_scores_every_locked_component(self):
        row = {
            "passing_yards": "250",
            "passing_tds": "2",
            "passing_interceptions": "1",
            "rushing_yards": "25",
            "receiving_yards": "40",
            "rushing_tds": "1",
            "receiving_tds": "1",
            "receptions": "4",
            "fumbles_lost_total": "1",
            "passing_2pt_conversions": "1",
            "rushing_2pt_conversions": "1",
            "receiving_2pt_conversions": "1",
            "special_teams_tds": "1",
        }

        self.assertAlmostEqual(pgo_fantasy.half_ppr(row), 46.5)

    def test_half_ppr_treats_blanks_as_zero_and_rejects_invalid_numbers(self):
        self.assertEqual(pgo_fantasy.half_ppr({}), 0.0)
        self.assertEqual(
            pgo_fantasy.half_ppr({name: "" for name in pgo_fantasy.SCORING_FIELDS}),
            0.0,
        )
        for invalid in ("not-a-number", "NaN", "inf", -math.inf):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    pgo_fantasy.half_ppr({"passing_yards": invalid})


if __name__ == "__main__":
    unittest.main()
