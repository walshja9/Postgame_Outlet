import copy
import csv
import hashlib
import math
import tempfile
import unittest
from pathlib import Path

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


class FantasyPopulationTests(unittest.TestCase):
    @staticmethod
    def _row(columns, **values):
        return {column: values.get(column, "") for column in columns}

    def _base_rows(self):
        schedule = [self._row(
            pgo_fantasy.SCHEDULE_COLUMNS,
            game_id="2022_01_BUF_LAR",
            season="2022",
            week="1",
            game_type="REG",
            gameday="2022-09-08",
            gametime="20:20",
            away_team="BUF",
            home_team="LAR",
            away_score="31",
            home_score="10",
        )]
        rosters = {season: [] for season in pgo_fantasy.MODEL_SEASONS}
        stats = {season: [] for season in pgo_fantasy.MODEL_SEASONS}
        rosters[2022] = [
            self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022",
                week="1",
                game_type="REG",
                team="BUF",
                position="QB",
                status="ACT",
                full_name="Active Quarterback",
                gsis_id="00-QB",
            ),
            self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022",
                week="1",
                game_type="REG",
                team="LAR",
                position="FB",
                status="ACT",
                full_name="Active Fullback",
                gsis_id="00-FB",
            ),
            self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022",
                week="1",
                game_type="REG",
                team="BUF",
                position="WR",
                status="INA",
                full_name="Inactive Receiver",
                gsis_id="00-INA",
            ),
            self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022",
                week="1",
                game_type="REG",
                team="NE",
                position="TE",
                status="ACT",
                full_name="Bye Tight End",
                gsis_id="00-BYE",
            ),
            self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022",
                week="1",
                game_type="REG",
                team="BUF",
                position="K",
                status="ACT",
                full_name="Ignored Kicker",
                gsis_id="00-K",
            ),
        ]
        stats[2022] = [self._row(
            pgo_fantasy.PLAYER_COLUMNS,
            player_id="00-QB",
            position="QB",
            season="2022",
            week="1",
            season_type="REG",
            game_id="2022_01_BUF_LAR",
            team="BUF",
            opponent_team="LAR",
            passing_yards="250",
        )]
        return schedule, rosters, stats

    def _write_sources(self, directory, schedule, rosters, stats):
        root = Path(directory)
        paths = {}

        def write(name, season, columns, rows):
            path = root / f"{name}_{season if season is not None else 'all'}.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            paths[(name, season)] = path

        write("schedule_results", None, pgo_fantasy.SCHEDULE_COLUMNS, schedule)
        for season in pgo_fantasy.MODEL_SEASONS:
            roster_rows = rosters[season] or [self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season=str(season),
                week="99",
                game_type="REG",
                team="BUF",
                position="K",
                status="ACT",
                full_name=f"Unused Kicker {season}",
                gsis_id=f"00-K-{season}",
            )]
            stat_rows = stats[season] or [self._row(
                pgo_fantasy.PLAYER_COLUMNS,
                player_id=f"00-K-{season}",
                position="K",
                season=str(season),
                week="99",
                season_type="REG",
                game_id=f"unused-{season}",
                team="BUF",
                opponent_team="MIA",
            )]
            write(
                "weekly_rosters",
                season,
                pgo_fantasy.ROSTER_COLUMNS,
                roster_rows,
            )
            write(
                "player_weekly_stats",
                season,
                pgo_fantasy.PLAYER_COLUMNS,
                stat_rows,
            )
        return paths

    def test_builds_act_population_maps_fullbacks_and_zero_fills_after_audit(self):
        schedule, rosters, stats = self._base_rows()
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, rosters, stats)

            rows, audit = pgo_fantasy.build_player_games(paths)

            by_id = {row["gsis_id"]: row for row in rows}
            self.assertEqual(set(by_id), {"00-QB", "00-FB"})
            self.assertEqual(by_id["00-QB"]["fantasy_points"], 10.0)
            self.assertEqual(by_id["00-QB"]["opponent"], "LAR")
            self.assertEqual(by_id["00-FB"]["position"], "RB")
            self.assertEqual(by_id["00-FB"]["fantasy_points"], 0.0)
            self.assertEqual(
                audit["coverage"]["2022"],
                {
                    "eligible": 2,
                    "matched_stats": 1,
                    "zero_filled": 1,
                    "bye_skipped": 1,
                },
            )
            self.assertTrue(all(value is True for value in audit["checks"].values()))
            self.assertEqual(len(audit["sources"]), 13)
            for receipt in audit["sources"]:
                path = paths[(receipt["name"], receipt["season"])]
                data = path.read_bytes()
                self.assertEqual(receipt["bytes"], len(data))
                self.assertEqual(receipt["sha256"], hashlib.sha256(data).hexdigest())

    def test_rejects_missing_extra_empty_or_malformed_sources(self):
        schedule, rosters, stats = self._base_rows()
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, rosters, stats)
            missing = dict(paths)
            del missing[("weekly_rosters", 2020)]
            with self.assertRaisesRegex(ValueError, "Missing source"):
                pgo_fantasy.build_player_games(missing)

            extra = dict(paths)
            extra[("injury_reports", 2022)] = next(iter(paths.values()))
            with self.assertRaisesRegex(ValueError, "Unexpected source"):
                pgo_fantasy.build_player_games(extra)

            empty = dict(paths)
            empty_path = Path(directory) / "empty.csv"
            with empty_path.open("w", newline="", encoding="utf-8") as handle:
                csv.DictWriter(
                    handle, fieldnames=pgo_fantasy.ROSTER_COLUMNS
                ).writeheader()
            empty[("weekly_rosters", 2020)] = empty_path
            with self.assertRaisesRegex(ValueError, "zero data rows"):
                pgo_fantasy.build_player_games(empty)

            malformed = dict(paths)
            malformed_path = Path(directory) / "malformed.csv"
            columns = tuple(
                column for column in pgo_fantasy.ROSTER_COLUMNS if column != "status"
            )
            with malformed_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerow({column: "x" for column in columns})
            malformed[("weekly_rosters", 2020)] = malformed_path
            with self.assertRaisesRegex(ValueError, "missing required columns: status"):
                pgo_fantasy.build_player_games(malformed)

    def test_rejects_roster_identity_failures(self):
        mutations = {
            "duplicate": (
                "Duplicate eligible roster identity",
                lambda rows: rows.append(copy.deepcopy(rows[0])),
            ),
            "missing status": (
                "Missing roster status",
                lambda rows: rows[0].update(status=""),
            ),
            "missing id": (
                "Missing roster GSIS ID",
                lambda rows: rows[0].update(gsis_id=""),
            ),
            "conflicting team": (
                "Duplicate eligible roster identity",
                lambda rows: rows.append({**rows[0], "team": "LAR"}),
            ),
        }
        for label, (message, mutate) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                schedule, rosters, stats = self._base_rows()
                mutate(rosters[2022])
                paths = self._write_sources(directory, schedule, rosters, stats)
                with self.assertRaisesRegex(ValueError, message):
                    pgo_fantasy.build_player_games(paths)

    def test_rejects_unmatched_duplicate_or_contradictory_stats(self):
        def add_unmatched(stats):
            stats.append({
                **stats[0],
                "player_id": "00-WR",
                "position": "WR",
                "receiving_yards": "50",
                "passing_yards": "",
            })

        mutations = {
            "unmatched": ("outside ACT roster population", add_unmatched),
            "duplicate": (
                "Duplicate eligible stat identity",
                lambda rows: rows.append(copy.deepcopy(rows[0])),
            ),
            "wrong team": (
                "Stat team/opponent mismatch",
                lambda rows: rows[0].update(team="LAR", opponent_team="BUF"),
            ),
            "wrong week": (
                "Stat schedule identity mismatch",
                lambda rows: rows[0].update(week="2"),
            ),
            "wrong position": (
                "Position mismatch",
                lambda rows: rows[0].update(position="RB"),
            ),
            "ineligible position mismatch": (
                "Position mismatch",
                lambda rows: rows[0].update(position="K"),
            ),
        }
        for label, (message, mutate) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                schedule, rosters, stats = self._base_rows()
                mutate(stats[2022])
                paths = self._write_sources(directory, schedule, rosters, stats)
                with self.assertRaisesRegex(ValueError, message):
                    pgo_fantasy.build_player_games(paths)


if __name__ == "__main__":
    unittest.main()
