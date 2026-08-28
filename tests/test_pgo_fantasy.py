import copy
import csv
import gzip
import hashlib
import io
import json
import math
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import pgo_fantasy
import pgo_sources


class FantasySourceLockTests(unittest.TestCase):
    AS_OF = "2026-08-27T12:00:00-04:00"

    def setUp(self):
        manifest = self._manifest()
        self._pinned_schedule = patch.object(
            pgo_sources,
            "EXPECTED_SOURCE_SHA256",
            manifest["sources"][0]["sha256"],
        )
        self._pinned_schedule.start()

    def tearDown(self):
        self._pinned_schedule.stop()

    @classmethod
    def _manifest(cls):
        return {
            "sources": [
                {
                    "name": spec.name,
                    "season": spec.season,
                    "url": spec.url,
                    "sha256": hashlib.sha256(
                        f"{spec.name}:{spec.season}".encode("utf-8")
                    ).hexdigest(),
                    "bytes": 1,
                    "frozen_at": cls.AS_OF,
                }
                for spec in pgo_fantasy.fantasy_source_specs()
            ]
        }

    def test_builds_exact_deterministic_fantasy_lock(self):
        lock = pgo_fantasy.build_fantasy_source_lock(self._manifest())
        text = pgo_fantasy.serialize_fantasy_source_json(lock)

        self.assertEqual(lock["schema_version"], 1)
        self.assertEqual(lock["scope"], {
            "seasons": [2020, 2021, 2022, 2023, 2024, 2025],
            "game_type": "REG",
            "roster_status": "ACT",
        })
        self.assertEqual(len(lock["sources"]), 13)
        self.assertEqual(text, pgo_fantasy.serialize_fantasy_source_json(
            pgo_fantasy.build_fantasy_source_lock({
                "sources": list(reversed(self._manifest()["sources"]))
            })
        ))
        self.assertNotIn("\r", text)
        self.assertTrue(text.endswith("\n"))
        for entry in lock["sources"]:
            self.assertEqual(set(entry), {
                "name", "season", "url", "sha256", "bytes", "frozen_at",
                "cache_path", "required_columns", "allowed_scope",
            })
            self.assertTrue(entry["cache_path"].startswith(".cache/pgo_fantasy/"))

    def test_rejects_naive_or_inconsistent_capture_time_and_manifest_drift(self):
        cases = []
        naive = self._manifest()
        naive["sources"][0]["frozen_at"] = "2026-08-27T12:00:00"
        cases.append(naive)
        inconsistent = self._manifest()
        inconsistent["sources"][0]["frozen_at"] = "2026-08-27T13:00:00-04:00"
        cases.append(inconsistent)
        missing = self._manifest()
        missing["sources"].pop()
        cases.append(missing)
        changed_url = self._manifest()
        changed_url["sources"][0]["url"] = "https://example.invalid/source.csv"
        cases.append(changed_url)

        for manifest in cases:
            with self.subTest(manifest=manifest):
                with self.assertRaises(ValueError):
                    pgo_fantasy.build_fantasy_source_lock(manifest)

    def test_fantasy_research_json_has_lf_checkout_attribute(self):
        result = subprocess.run(
            [
                "git", "check-attr", "eol", "--",
                "research/pgo_fantasy/sources.lock.json",
                "research/pgo_fantasy/source_qualification.json",
            ],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.splitlines(), [
            "research/pgo_fantasy/sources.lock.json: eol: lf",
            "research/pgo_fantasy/source_qualification.json: eol: lf",
        ])


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


class FantasyQualificationFixture:
    _row = staticmethod(FantasyPopulationTests._row)

    def _write_sources(self, directory, schedule, rosters, stats):
        return FantasyPopulationTests()._write_sources(
            directory, schedule, rosters, stats
        )

    def _qualification_rows(self):
        schedule = []
        rosters = {season: [] for season in pgo_fantasy.MODEL_SEASONS}
        stats = {season: [] for season in pgo_fantasy.MODEL_SEASONS}
        for season in pgo_fantasy.MODEL_SEASONS:
            game_id = f"{season}_01_BUF_LAR"
            schedule.append(self._row(
                pgo_fantasy.SCHEDULE_COLUMNS,
                game_id=game_id, season=str(season), week="1", game_type="REG",
                gameday=f"{season}-09-08", gametime="20:20", away_team="BUF",
                home_team="LAR", away_score="21", home_score="17",
            ))
            for team in pgo_fantasy.CURRENT_TEAMS:
                rosters[season].append(self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season=str(season), week="99", game_type="REG", team=team,
                    position="K", status="ACT", full_name=f"Coverage {team}",
                    gsis_id=f"K-{season}-{team}",
                ))
            for team, opponent, player in (("BUF", "LAR", "BUF-QB"), ("LAR", "BUF", "LAR-QB")):
                rosters[season].append(self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season=str(season), week="1", game_type="REG", team=team,
                    position="QB", status="ACT", full_name=player,
                    gsis_id=f"{player}-{season}",
                ))
                stats[season].append(self._row(
                    pgo_fantasy.PLAYER_COLUMNS,
                    player_id=f"{player}-{season}", position="QB",
                    season=str(season), week="1", season_type="REG",
                    game_id=game_id, team=team, opponent_team=opponent,
                    passing_yards="200",
                ))
        return schedule, rosters, stats

    def _qualification_paths(self, directory, mutate=None):
        Path(directory).mkdir(parents=True, exist_ok=True)
        schedule, rosters, stats = self._qualification_rows()
        if mutate is not None:
            mutate(schedule, rosters, stats)
        return self._write_sources(directory, schedule, rosters, stats)

    @staticmethod
    def _fixture_schedule_digest(paths):
        schedule = paths[("schedule_results", None)].read_bytes()
        return patch.object(
            pgo_sources,
            "EXPECTED_SOURCE_SHA256",
            hashlib.sha256(schedule).hexdigest(),
        )

    @staticmethod
    def _source_lock_text(paths):
        manifest = {"sources": []}
        for spec in pgo_fantasy.fantasy_source_specs():
            data = Path(paths[(spec.name, spec.season)]).read_bytes()
            manifest["sources"].append({
                "name": spec.name,
                "season": spec.season,
                "url": spec.url,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "frozen_at": FantasySourceLockTests.AS_OF,
            })
        return pgo_fantasy.serialize_fantasy_source_json(
            pgo_fantasy.build_fantasy_source_lock(manifest)
        )


class FantasySourceQualificationTests(
    FantasyQualificationFixture, unittest.TestCase
):
    def test_clean_sources_pass_without_stat_driven_population_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory)
            with self._fixture_schedule_digest(paths):
                lock_text = self._source_lock_text(paths)
                receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
                pgo_fantasy.validate_fantasy_source_qualification(lock_text, receipt)

        self.assertEqual(receipt["qualification_status"], "PASS")
        self.assertEqual(receipt["artifact_availability"], "LOCAL_CACHE_ONLY")
        self.assertEqual(receipt["source_count"], 13)
        self.assertEqual(len(receipt["sources"]), 13)
        self.assertTrue(all(receipt["checks"].values()))
        self.assertEqual(receipt["discrepancies"]["total"], 0)
        self.assertTrue(all(
            count == 0
            for count in receipt["discrepancies"]["counts"].values()
        ))
        self.assertEqual(receipt["coverage"]["2022"]["eligible"], 2)

    def test_reports_all_discrepancy_classes_deterministically(self):
        def mutate(schedule, rosters, stats):
            season = 2022
            game_id = f"{season}_01_BUF_LAR"
            schedule.append(self._row(
                pgo_fantasy.SCHEDULE_COLUMNS,
                game_id="2022_02_ARI_ATL", season="2022", week="2",
                game_type="REG", gameday="2022-09-18", gametime="13:00",
                away_team="ARI", home_team="ATL", away_score="10", home_score="17",
            ))
            rosters[season] = [
                row for row in rosters[season]
                if not (row["team"] == "ARI" and row["position"] == "K")
            ]
            rosters[season].extend([
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="INA", full_name="Non ACT", gsis_id="NON-ACT"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="ACT", full_name="Position Conflict", gsis_id="POS-CONFLICT"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="ACT", full_name="Duplicate", gsis_id="DUP-ROSTER"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="LAR", position="WR", status="ACT", full_name="Duplicate", gsis_id="DUP-ROSTER"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="", full_name="Missing Status", gsis_id="MISSING-STATUS"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="ACT", full_name="Missing ID", gsis_id=""),
            ])
            stats[season].extend([
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="NO-ROSTER", position="WR", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="LAR", receiving_yards="40"),
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="NON-ACT", position="WR", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="LAR", receiving_yards="40"),
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="POS-CONFLICT", position="RB", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="LAR", rushing_yards="40"),
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="BAD-SCHEDULE", position="WR", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="BUF", receiving_yards="40"),
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="", position="WR", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="LAR", receiving_yards="40"),
            ])
            rosters[season].append(self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022", week="1", game_type="REG", team="BUF",
                position="WR", status="ACT", full_name="Bad Schedule",
                gsis_id="BAD-SCHEDULE",
            ))
            stats[season].append(copy.deepcopy(stats[season][-2]))

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, mutate)
            with self._fixture_schedule_digest(paths):
                lock_text = self._source_lock_text(paths)
                first = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
                second = pgo_fantasy.qualify_fantasy_sources(
                    dict(reversed(list(paths.items()))), lock_text
                )
                with self.assertRaisesRegex(ValueError, "PASS"):
                    pgo_fantasy.validate_fantasy_source_qualification(
                        lock_text, first
                    )

        self.assertEqual(first, second)
        self.assertEqual(first["qualification_status"], "BLOCKED")
        reasons = {row["reason"] for row in first["discrepancies"]["rows"]}
        self.assertTrue({
            "incomplete_team_coverage", "missing_roster_identity",
            "incomplete_team_week_coverage", "missing_roster_status",
            "duplicate_roster_identity", "conflicting_team",
            "missing_stat_identity", "duplicate_stat_identity", "missing_roster",
            "non_act_roster", "schedule_identity", "position_contradiction",
        }.issubset(reasons))
        expected_counts = {
            reason: (
                2 if reason in {
                    "incomplete_team_week_coverage",
                    "incomplete_stat_team_week_coverage",
                } else 1
            )
            for reason in pgo_fantasy.FANTASY_DISCREPANCY_CLASSES
        }
        self.assertEqual(first["discrepancies"]["counts"], expected_counts)
        self.assertEqual(first["discrepancies"]["by_season"], {
            str(season): (
                expected_counts if season == 2022
                else {reason: 0 for reason in expected_counts}
            )
            for season in pgo_fantasy.MODEL_SEASONS
        })
        self.assertEqual(first["discrepancies"]["rows"], [
            {"reason": "conflicting_team", "season": 2022, "week": 1,
             "gsis_id": "DUP-ROSTER", "game_id": "", "team": "BUF,LAR"},
            {"reason": "duplicate_roster_identity", "season": 2022, "week": 1,
             "gsis_id": "DUP-ROSTER", "game_id": "", "team": "BUF,LAR"},
            {"reason": "duplicate_stat_identity", "season": 2022, "week": 1,
             "gsis_id": "BAD-SCHEDULE", "game_id": "2022_01_BUF_LAR", "team": "BUF"},
            {"reason": "incomplete_stat_team_week_coverage", "season": 2022, "week": 2,
             "gsis_id": "", "game_id": "", "team": "ARI"},
            {"reason": "incomplete_stat_team_week_coverage", "season": 2022, "week": 2,
             "gsis_id": "", "game_id": "", "team": "ATL"},
            {"reason": "incomplete_team_coverage", "season": 2022, "week": 0,
             "gsis_id": "", "game_id": "", "team": "ARI"},
            {"reason": "incomplete_team_week_coverage", "season": 2022, "week": 2,
             "gsis_id": "", "game_id": "", "team": "ARI"},
            {"reason": "incomplete_team_week_coverage", "season": 2022, "week": 2,
             "gsis_id": "", "game_id": "", "team": "ATL"},
            {"reason": "missing_roster", "season": 2022, "week": 1,
             "gsis_id": "NO-ROSTER", "game_id": "2022_01_BUF_LAR", "team": "BUF"},
            {"reason": "missing_roster_identity", "season": 2022, "week": 1,
             "gsis_id": "", "game_id": "", "team": "BUF"},
            {"reason": "missing_roster_status", "season": 2022, "week": 1,
             "gsis_id": "MISSING-STATUS", "game_id": "", "team": "BUF"},
            {"reason": "missing_stat_identity", "season": 2022, "week": 1,
             "gsis_id": "", "game_id": "2022_01_BUF_LAR", "team": "BUF"},
            {"reason": "non_act_roster", "season": 2022, "week": 1,
             "gsis_id": "NON-ACT", "game_id": "2022_01_BUF_LAR", "team": "BUF"},
            {"reason": "position_contradiction", "season": 2022, "week": 1,
             "gsis_id": "POS-CONFLICT", "game_id": "2022_01_BUF_LAR", "team": "BUF"},
            {"reason": "schedule_identity", "season": 2022, "week": 1,
             "gsis_id": "BAD-SCHEDULE", "game_id": "2022_01_BUF_LAR", "team": "BUF"},
        ])
        self.assertEqual(first["coverage"], {
            str(season): {
                "eligible": 6 if season == 2022 else 2,
                "matched_stats": 2,
                "zero_filled": 4 if season == 2022 else 0,
                "bye_skipped": 0,
            }
            for season in pgo_fantasy.MODEL_SEASONS
        })
    def test_qualification_uses_one_loaded_byte_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory)
            target = Path(paths[("weekly_rosters", 2022)])
            original = target.read_bytes()
            reads = []
            original_read_bytes = Path.read_bytes

            def mutate_after_read(path):
                data = original_read_bytes(path)
                if Path(path) == target:
                    reads.append(data)
                    if len(reads) == 1:
                        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
                        rows.append(self._row(
                            pgo_fantasy.ROSTER_COLUMNS,
                            season="2022", week="1", game_type="REG", team="BUF",
                            position="QB", status="ACT", full_name="Mutated",
                            gsis_id="MUTATED-QB",
                        ))
                        output = io.StringIO(newline="")
                        writer = csv.DictWriter(
                            output, fieldnames=pgo_fantasy.ROSTER_COLUMNS,
                            lineterminator="\n",
                        )
                        writer.writeheader()
                        writer.writerows(rows)
                        target.write_text(output.getvalue(), encoding="utf-8", newline="")
                return data

            with self._fixture_schedule_digest(paths):
                lock_text = self._source_lock_text(paths)
                with mock.patch.object(Path, "read_bytes", mutate_after_read):
                    receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
            changed = target.read_bytes()

        self.assertEqual(reads, [original])
        self.assertNotEqual(changed, original)
        self.assertEqual(receipt["coverage"]["2022"]["eligible"], 2)
        source = next(
            source for source in receipt["sources"]
            if (source["name"], source["season"]) == ("weekly_rosters", 2022)
        )
        self.assertEqual(source["sha256"], hashlib.sha256(original).hexdigest())

    def test_unmapped_stat_for_eligible_roster_is_position_contradiction(self):
        def mutate(schedule, rosters, stats):
            stats[2022][0]["position"] = "K"

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, mutate)
            with self._fixture_schedule_digest(paths):
                receipt = pgo_fantasy.qualify_fantasy_sources(
                    paths, self._source_lock_text(paths)
                )

        self.assertEqual(receipt["qualification_status"], "BLOCKED")
        self.assertEqual(receipt["discrepancies"]["counts"]["position_contradiction"], 1)
        self.assertEqual(receipt["discrepancies"]["rows"], [{
            "reason": "position_contradiction", "season": 2022, "week": 1,
            "gsis_id": "BUF-QB-2022", "game_id": "2022_01_BUF_LAR", "team": "BUF",
        }])
        self.assertEqual(receipt["coverage"]["2022"], {
            "eligible": 2, "matched_stats": 1, "zero_filled": 1, "bye_skipped": 0,
        })

    def test_all_post_stats_block_stat_team_week_coverage(self):
        def all_post(schedule, rosters, stats):
            for rows in stats.values():
                for row in rows:
                    row["season_type"] = "POST"

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, all_post)
            with self._fixture_schedule_digest(paths):
                receipt = pgo_fantasy.qualify_fantasy_sources(
                    paths, self._source_lock_text(paths)
                )

        self.assertEqual(receipt["qualification_status"], "BLOCKED")
        self.assertFalse(receipt["checks"]["stat_team_week_coverage"])
        self.assertEqual(
            receipt["discrepancies"]["counts"]["incomplete_stat_team_week_coverage"],
            12,
        )
        self.assertEqual(receipt["discrepancies"]["by_season"], {
            str(season): {
                **{
                    reason: 0
                    for reason in pgo_fantasy.FANTASY_DISCREPANCY_CLASSES
                },
                "incomplete_stat_team_week_coverage": 2,
            }
            for season in pgo_fantasy.MODEL_SEASONS
        })

    def test_missing_regular_stat_team_week_blocks_without_population_growth(self):
        def missing_buf(schedule, rosters, stats):
            stats[2022] = [row for row in stats[2022] if row["team"] != "BUF"]

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, missing_buf)
            with self._fixture_schedule_digest(paths):
                receipt = pgo_fantasy.qualify_fantasy_sources(
                    paths, self._source_lock_text(paths)
                )

        self.assertEqual(receipt["qualification_status"], "BLOCKED")
        self.assertEqual(receipt["discrepancies"]["rows"], [{
            "reason": "incomplete_stat_team_week_coverage",
            "season": 2022,
            "week": 1,
            "gsis_id": "",
            "game_id": "",
            "team": "BUF",
        }])
        self.assertEqual(receipt["coverage"]["2022"], {
            "eligible": 2, "matched_stats": 1, "zero_filled": 1, "bye_skipped": 0,
        })

    def test_qualification_rejects_noncanonical_and_duplicate_lock_text(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory)
            with self._fixture_schedule_digest(paths):
                lock_text = self._source_lock_text(paths)
                duplicate = lock_text.replace(
                    '  "schema_version": 1,\n',
                    '  "schema_version": 1,\n  "schema_version": 1,\n',
                    1,
                )
                for text, message in (
                    (lock_text + " ", "canonical"),
                    (duplicate, "duplicate JSON key"),
                    (None, "invalid JSON"),
                ):
                    with self.subTest(message=message), self.assertRaisesRegex(
                        ValueError, message
                    ):
                        pgo_fantasy.qualify_fantasy_sources(paths, text)

    def test_shared_lock_boundary_requires_pinned_schedule_digest(self):
        manifest = FantasySourceLockTests._manifest()
        digest = manifest["sources"][0]["sha256"]
        with patch.object(pgo_sources, "EXPECTED_SOURCE_SHA256", digest):
            lock = pgo_fantasy.build_fantasy_source_lock(manifest)
            schedule = next(
                entry for entry in lock["sources"]
                if entry["name"] == "schedule_results"
            )
            schedule["sha256"] = "0" * 64
            schedule["cache_path"] = pgo_fantasy._cache_name(
                schedule["url"], schedule["sha256"]
            )
            with self.assertRaisesRegex(ValueError, "pinned SHA-256"):
                pgo_fantasy.validate_fantasy_source_lock(lock)

    def test_receipt_is_bound_to_exact_lock_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory)
            with self._fixture_schedule_digest(paths):
                lock_text = self._source_lock_text(paths)
                receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
                changed_lock = lock_text.replace(
                    FantasySourceLockTests.AS_OF, "2026-08-27T12:00:01-04:00"
                )
                with self.assertRaisesRegex(ValueError, "hash"):
                    pgo_fantasy.validate_fantasy_source_qualification(
                        changed_lock, receipt
                    )


class FantasySourceCommandTests(FantasyQualificationFixture, unittest.TestCase):
    AS_OF = FantasySourceLockTests.AS_OF

    def _payloads(self, root, mutate=None):
        paths = self._qualification_paths(root / "fixtures", mutate)
        payloads = {}
        for spec in pgo_fantasy.fantasy_source_specs():
            data = paths[(spec.name, spec.season)].read_bytes()
            if spec.url.lower().endswith(".csv.gz"):
                data = gzip.compress(data, mtime=0)
            payloads[spec.url] = data
        return payloads

    def _run_in_root(self, root, argv, payloads=None, freeze=None):
        original = pgo_sources.freeze_sources

        def fetch_fixture(specs, cache_dir, lock_path, frozen_at):
            return original(
                specs, cache_dir, lock_path, frozen_at,
                fetch=payloads.__getitem__,
            )

        previous = Path.cwd()
        os.chdir(root)
        try:
            if payloads is None:
                return pgo_fantasy.main(argv)
            schedule = next(
                spec for spec in pgo_fantasy.fantasy_source_specs()
                if spec.name == "schedule_results"
            )
            digest = hashlib.sha256(payloads[schedule.url]).hexdigest()
            with (
                patch.object(pgo_sources, "EXPECTED_SOURCE_SHA256", digest),
                patch.object(
                    pgo_sources,
                    "freeze_sources",
                    side_effect=fetch_fixture if freeze is None else freeze,
                ),
            ):
                return pgo_fantasy.main(argv)
        finally:
            os.chdir(previous)

    def test_freeze_writes_local_pass_but_not_research(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            code = self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            )
            receipt = json.loads((
                root / "output/pgo-fantasy-source-qualification.json"
            ).read_text(encoding="utf-8"))
            lock_text = (
                root / "output/pgo-fantasy-source-candidate.lock.json"
            ).read_text(encoding="utf-8")

            self.assertEqual(code, 0)
            self.assertEqual(receipt["qualification_status"], "PASS")
            schedule = next(
                spec for spec in pgo_fantasy.fantasy_source_specs()
                if spec.name == "schedule_results"
            )
            with patch.object(
                pgo_sources,
                "EXPECTED_SOURCE_SHA256",
                hashlib.sha256(payloads[schedule.url]).hexdigest(),
            ):
                pgo_fantasy.validate_fantasy_source_qualification(lock_text, receipt)
            self.assertFalse((root / "research/pgo_fantasy").exists())

    def test_blocked_freeze_writes_diagnostic_but_not_research(self):
        def unmatched(schedule, rosters, stats):
            stats[2022].append({
                **stats[2022][0],
                "player_id": "NO-ROSTER",
                "position": "WR",
            })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root, unmatched)
            code = self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            )
            receipt = json.loads((
                root / "output/pgo-fantasy-source-qualification.json"
            ).read_text(encoding="utf-8"))

            self.assertEqual(code, 1)
            self.assertEqual(receipt["qualification_status"], "BLOCKED")
            self.assertGreater(receipt["discrepancies"]["total"], 0)
            self.assertFalse((root / "research/pgo_fantasy").exists())

    def test_accept_requalifies_offline_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            self.assertEqual(self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            ), 0)
            with patch.object(pgo_sources, "freeze_sources") as freeze:
                self.assertEqual(self._run_in_root(
                    root, ["--accept-qualified"], payloads
                ), 0)
                freeze.assert_not_called()
            accepted = root / "research/pgo_fantasy"
            self.assertEqual(
                sorted(path.name for path in accepted.iterdir()),
                ["source_qualification.json", "sources.lock.json"],
            )
            before = {
                path.name: path.read_bytes() for path in accepted.iterdir()
            }
            error = io.StringIO()
            with redirect_stderr(error):
                second = self._run_in_root(
                    root, ["--accept-qualified"], payloads
                )
            self.assertEqual(second, 2)
            self.assertEqual(before, {
                path.name: path.read_bytes() for path in accepted.iterdir()
            })

    def test_accept_rejects_noncanonical_or_duplicate_candidate_lock(self):
        for change in (
            lambda text: text + " ",
            lambda text: text.replace(
                '  "schema_version": 1,\n',
                '  "schema_version": 1,\n  "schema_version": 1,\n',
                1,
            ),
        ):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                payloads = self._payloads(root)
                self.assertEqual(self._run_in_root(
                    root,
                    ["--freeze-sources", "--frozen-at", self.AS_OF],
                    payloads,
                ), 0)
                lock_path = root / "output/pgo-fantasy-source-candidate.lock.json"
                receipt_path = root / "output/pgo-fantasy-source-qualification.json"
                lock_text = change(lock_path.read_text(encoding="utf-8"))
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                receipt["source_lock_sha256"] = hashlib.sha256(
                    lock_text.encode("utf-8")
                ).hexdigest()
                lock_path.write_text(lock_text, encoding="utf-8", newline="")
                receipt_path.write_text(
                    pgo_fantasy.serialize_fantasy_source_json(receipt),
                    encoding="utf-8",
                    newline="",
                )
                with redirect_stderr(io.StringIO()):
                    code = self._run_in_root(
                        root, ["--accept-qualified"], payloads
                    )
                self.assertEqual(code, 2)
                self.assertFalse((root / "research/pgo_fantasy").exists())

    def test_preflight_rejects_bad_time_or_existing_candidate_before_fetch(self):
        for argv, existing in (
            (["--freeze-sources", "--frozen-at", "not-a-time"], False),
            (["--freeze-sources", "--frozen-at", self.AS_OF], True),
        ):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if existing:
                    path = root / "output/pgo-fantasy-source-candidate.lock.json"
                    path.parent.mkdir(parents=True)
                    path.write_text("existing\n", encoding="utf-8")
                previous = Path.cwd()
                os.chdir(root)
                try:
                    with patch.object(pgo_sources, "freeze_sources") as freeze:
                        code = pgo_fantasy.main(argv)
                    self.assertEqual(code, 2)
                    freeze.assert_not_called()
                finally:
                    os.chdir(previous)

    def test_operational_freeze_failure_writes_blocked_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                with patch.object(
                    pgo_sources, "freeze_sources", side_effect=OSError("offline")
                ):
                    code = pgo_fantasy.main([
                        "--freeze-sources", "--frozen-at", self.AS_OF,
                    ])
            finally:
                os.chdir(previous)
            receipt = json.loads((
                root / "output/pgo-fantasy-source-qualification.json"
            ).read_text(encoding="utf-8"))
            self.assertEqual(code, 2)
            self.assertEqual(receipt["qualification_status"], "BLOCKED")
            self.assertEqual(receipt["error"], "OSError: offline")
            self.assertFalse((root / "research/pgo_fantasy").exists())

    def test_freeze_write_failure_removes_candidate_before_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            original = pgo_fantasy._exclusive_write_text
            calls = 0

            def fail_second(path, text):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("receipt write failed")
                return original(path, text)

            with patch.object(
                pgo_fantasy, "_exclusive_write_text", side_effect=fail_second
            ):
                code = self._run_in_root(
                    root,
                    ["--freeze-sources", "--frozen-at", self.AS_OF],
                    payloads,
                )
            receipt = json.loads((
                root / "output/pgo-fantasy-source-qualification.json"
            ).read_text(encoding="utf-8"))
            self.assertEqual(code, 2)
            self.assertFalse((
                root / "output/pgo-fantasy-source-candidate.lock.json"
            ).exists())
            self.assertEqual(receipt["error"], "OSError: receipt write failed")

    def test_candidate_claim_blocks_concurrent_freeze_before_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            original = pgo_sources.freeze_sources
            claim = root / pgo_fantasy.FANTASY_CANDIDATE_CLAIM
            calls = 0

            def first_freeze(specs, cache_dir, lock_path, frozen_at):
                nonlocal calls
                calls += 1
                self.assertTrue(claim.exists())

                def second_freeze(specs, cache_dir, lock_path, frozen_at):
                    return original(
                        specs, cache_dir, lock_path, frozen_at,
                        fetch=payloads.__getitem__,
                    )

                with patch.object(
                    pgo_sources, "freeze_sources", side_effect=second_freeze
                ), redirect_stderr(io.StringIO()):
                    second = pgo_fantasy.main([
                        "--freeze-sources", "--frozen-at", self.AS_OF,
                    ])
                self.assertEqual(second, 2)
                return original(
                    specs, cache_dir, lock_path, frozen_at,
                    fetch=payloads.__getitem__,
                )

            code = self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
                first_freeze,
            )
            self.assertEqual(code, 0)
            self.assertEqual(calls, 1)
            self.assertFalse(claim.exists())

    def test_concurrent_candidate_is_never_overwritten_or_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            original = pgo_sources.freeze_sources
            claim = root / pgo_fantasy.FANTASY_CANDIDATE_CLAIM
            candidate = root / "output/pgo-fantasy-source-candidate.lock.json"

            def interfere(specs, cache_dir, lock_path, frozen_at):
                self.assertTrue(claim.exists())
                candidate.write_text("interloper\n", encoding="utf-8")
                return original(
                    specs, cache_dir, lock_path, frozen_at,
                    fetch=payloads.__getitem__,
                )

            with redirect_stderr(io.StringIO()):
                code = self._run_in_root(
                    root,
                    ["--freeze-sources", "--frozen-at", self.AS_OF],
                    payloads,
                    interfere,
                )
            self.assertEqual(code, 2)
            self.assertEqual(candidate.read_text(encoding="utf-8"), "interloper\n")
            self.assertFalse((
                root / "output/pgo-fantasy-source-qualification.json"
            ).exists())
            self.assertFalse(claim.exists())

    def test_freeze_rollback_keeps_interfering_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            original = pgo_fantasy._exclusive_write_text
            candidate = root / "output/pgo-fantasy-source-candidate.lock.json"
            receipt = root / "output/pgo-fantasy-source-qualification.json"
            claim = root / pgo_fantasy.FANTASY_CANDIDATE_CLAIM

            def interfere(path, text):
                if Path(path) == pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT:
                    receipt.write_text("interloper\n", encoding="utf-8")
                return original(path, text)

            with patch.object(
                pgo_fantasy, "_exclusive_write_text", side_effect=interfere
            ), redirect_stderr(io.StringIO()):
                code = self._run_in_root(
                    root,
                    ["--freeze-sources", "--frozen-at", self.AS_OF],
                    payloads,
                )
            self.assertEqual(code, 2)
            self.assertFalse(candidate.exists())
            self.assertEqual(receipt.read_text(encoding="utf-8"), "interloper\n")
            self.assertFalse(claim.exists())

    def test_cleanup_restores_a_foreign_swap_before_detach(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "output/pgo-fantasy-source-candidate.lock.json"
            target.parent.mkdir()
            owned = pgo_fantasy._exclusive_write_text(target, "owned\n")
            foreign = root / "foreign.lock"
            foreign.write_text("interloper\n", encoding="utf-8")
            original_replace = os.replace
            swapped = False

            def swap_before_detach(source, destination):
                nonlocal swapped
                if Path(source) == target and not swapped:
                    swapped = True
                    original_replace(foreign, target)
                return original_replace(source, destination)

            with patch.object(
                pgo_fantasy.os, "replace", side_effect=swap_before_detach
            ):
                pgo_fantasy._unlink_owned(target, *owned)

            self.assertTrue(swapped)
            self.assertEqual(target.read_text(encoding="utf-8"), "interloper\n")
            self.assertEqual(list(root.glob("output/*.rollback")), [])

    def test_accept_write_failure_leaves_no_partial_research_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            self.assertEqual(self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            ), 0)
            original = pgo_fantasy.atomic_write_text
            calls = 0

            def fail_second(path, text):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("second write failed")
                return original(path, text)

            previous = Path.cwd()
            os.chdir(root)
            try:
                with patch.object(
                    pgo_fantasy, "atomic_write_text", side_effect=fail_second
                ):
                    code = self._run_in_root(
                        root, ["--accept-qualified"], payloads
                    )
            finally:
                os.chdir(previous)
            self.assertEqual(code, 2)
            self.assertFalse((root / "research/pgo_fantasy").exists())
            self.assertEqual(list((root / "research").iterdir()), [])


class FantasyBaselineTests(unittest.TestCase):
    @staticmethod
    def _row(season, week, position, index):
        return {
            "season": season,
            "week": week,
            "game_id": f"{season}_{week:02d}_BUF_LAR",
            "gsis_id": f"{position}-{index:02d}",
            "player_name": f"{position} Player {index}",
            "team": "BUF",
            "opponent": "LAR",
            "position": position,
            "fantasy_points": float(
                index + week + {"QB": 12, "RB": 8, "WR": 6, "TE": 4}[position]
            ),
        }

    def _model_rows(self):
        counts = {"QB": 30, "RB": 42, "WR": 30, "TE": 20}
        rows = []
        for season in pgo_fantasy.MODEL_SEASONS:
            weeks = (1, 2, 3) if season == 2022 else (1,)
            for week in weeks:
                rows.extend(
                    self._row(season, week, position, index)
                    for position, count in counts.items()
                    for index in range(count)
                )
        return rows

    @classmethod
    def _audit(cls):
        counts = {season: 0 for season in pgo_fantasy.MODEL_SEASONS}
        for row in cls()._model_rows():
            counts[row["season"]] += 1
        return {
            "schema_version": 1,
            "scope": {
                "seasons": list(pgo_fantasy.MODEL_SEASONS),
                "game_type": "REG",
                "roster_status": "ACT",
            },
            "sources": [
                {
                    "name": spec.name,
                    "season": spec.season,
                    "bytes": 1,
                    "sha256": hashlib.sha256(
                        f"{spec.name}:{spec.season}".encode("utf-8")
                    ).hexdigest(),
                    "rows": 1,
                }
                for spec in pgo_fantasy.fantasy_source_specs()
            ],
            "coverage": {
                str(season): {
                    "eligible": counts[season],
                    "matched_stats": counts[season],
                    "zero_filled": 0,
                    "bye_skipped": 0,
                }
                for season in pgo_fantasy.MODEL_SEASONS
            },
            "checks": {
                "source_contract": True,
                "schedule_identity": True,
                "roster_identity": True,
                "stat_identity": True,
                "finite_targets": True,
            },
        }

    def test_strong_baseline_uses_eight_games_half_life_four_and_four_pseudo_games(self):
        history = [float(value) for value in range(1, 11)]
        recent_newest_first = list(reversed(history[-8:]))
        weights = [2 ** (-index / 4) for index in range(8)]
        expected = (
            sum(
                value * weight
                for value, weight in zip(recent_newest_first, weights)
            )
            + 4 * 12.0
        ) / (sum(weights) + 4)

        self.assertAlmostEqual(pgo_fantasy.strong_baseline(history, 12.0), expected)
        self.assertEqual(pgo_fantasy.strong_baseline([], 12.0), 12.0)
        with self.assertRaisesRegex(ValueError, "finite"):
            pgo_fantasy.strong_baseline([1.0], math.nan)

    def test_primary_pool_uses_locked_quotas_and_gsis_tie_break(self):
        counts = {"QB": 30, "RB": 30, "WR": 30, "TE": 20}
        rows = [
            {
                **self._row(2022, 1, position, index),
                "strong_prediction": 10.0,
            }
            for position, count in counts.items()
            for index in range(count)
        ]

        selected = pgo_fantasy.select_primary_pool(rows)

        self.assertEqual(len(selected), 96)
        self.assertIn(("2022_01_BUF_LAR", "QB-23"), selected)
        self.assertNotIn(("2022_01_BUF_LAR", "QB-24"), selected)
        self.assertEqual(
            sum(gsis_id.startswith("QB-") for _, gsis_id in selected),
            24,
        )
        with self.assertRaisesRegex(ValueError, "Insufficient primary-pool QB"):
            pgo_fantasy.select_primary_pool(
                [
                    row
                    for row in rows
                    if not (
                        row["position"] == "QB"
                        and int(row["gsis_id"].removeprefix("QB-")) >= 23
                    )
                ]
            )

    def test_same_week_outcomes_do_not_change_same_week_predictions(self):
        rows = self._model_rows()
        _, original = pgo_fantasy.backtest_baselines(rows, self._audit())
        mutated_rows = copy.deepcopy(rows)
        changed = next(
            row
            for row in mutated_rows
            if row["season"] == 2022
            and row["week"] == 2
            and row["gsis_id"] == "RB-00"
        )
        changed["fantasy_points"] += 1000.0

        _, mutated = pgo_fantasy.backtest_baselines(mutated_rows, self._audit())

        def keyed(predictions):
            return {
                (
                    row["season"],
                    row["week"],
                    row["game_id"],
                    row["gsis_id"],
                ): row
                for row in predictions
            }

        before = keyed(original)
        after = keyed(mutated)
        for key in before:
            if key[0] == 2022 and key[1] <= 2:
                self.assertEqual(
                    (
                        before[key]["null_prediction"],
                        before[key]["strong_prediction"],
                        before[key]["primary_pool"],
                    ),
                    (
                        after[key]["null_prediction"],
                        after[key]["strong_prediction"],
                        after[key]["primary_pool"],
                    ),
                )
        week_3_key = (2022, 3, "2022_03_BUF_LAR", "RB-00")
        self.assertNotEqual(
            before[week_3_key]["strong_prediction"],
            after[week_3_key]["strong_prediction"],
        )
        self.assertEqual(
            before[week_3_key]["null_prediction"],
            after[week_3_key]["null_prediction"],
        )

    def test_backtest_is_deterministic_under_input_permutation(self):
        rows = self._model_rows()

        first = pgo_fantasy.backtest_baselines(rows, self._audit())
        second = pgo_fantasy.backtest_baselines(list(reversed(rows)), self._audit())

        self.assertEqual(first, second)

    def test_backtest_rejects_duplicate_player_week_identity(self):
        rows = self._model_rows()
        duplicate = copy.deepcopy(next(
            row
            for row in rows
            if row["season"] == 2022
            and row["week"] == 1
            and row["gsis_id"] == "QB-00"
        ))
        duplicate["game_id"] = "2022_01_OTHER_GAME"
        rows.append(duplicate)

        with self.assertRaisesRegex(ValueError, "Duplicate baseline player-week"):
            pgo_fantasy.backtest_baselines(rows, self._audit())

    def test_backtest_rejects_incomplete_or_mismatched_source_audit(self):
        rows = self._model_rows()
        with self.assertRaisesRegex(ValueError, "Source audit"):
            pgo_fantasy.backtest_baselines(
                rows,
                {"schema_version": 1, "checks": {"source_contract": True}},
            )

        mismatched = self._audit()
        mismatched["coverage"]["2022"]["eligible"] += 1
        with self.assertRaisesRegex(ValueError, "Source audit"):
            pgo_fantasy.backtest_baselines(rows, mismatched)


class FantasyReceiptTests(unittest.TestCase):
    @staticmethod
    def _rows():
        return FantasyBaselineTests()._model_rows()

    @staticmethod
    def _audit():
        return FantasyBaselineTests._audit()

    @staticmethod
    def _mae(rows, prediction_name):
        return sum(
            abs(row["fantasy_points"] - row[prediction_name]) for row in rows
        ) / len(rows)

    def test_fold_report_recomputes_from_common_prediction_rows(self):
        audit = self._audit()

        report, predictions = pgo_fantasy.backtest_baselines(self._rows(), audit)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["model"], "pgo_fantasy_baselines_v1")
        self.assertEqual(report["stage"], "BASELINE_ONLY")
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["publication_status"], "EXPERIMENTAL")
        self.assertEqual(report["scoring"], "HALF_PPR")
        self.assertEqual(
            report["population"], "WEEKLY_ROSTER_ACT_QB_RB_FB_WR_TE"
        )
        canonical_audit = json.dumps(
            audit,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(
            report["source_audit_sha256"],
            hashlib.sha256(canonical_audit).hexdigest(),
        )
        self.assertEqual(
            [fold["test_season"] for fold in report["folds"]],
            [2022, 2023, 2024, 2025],
        )
        for fold in report["folds"]:
            season = fold["test_season"]
            self.assertEqual(fold["train_seasons"], list(range(2020, season)))
            season_rows = [row for row in predictions if row["season"] == season]
            primary_rows = [row for row in season_rows if row["primary_pool"]]
            self.assertGreater(len(season_rows), len(primary_rows))
            self.assertEqual(fold["all_eligible"]["count"], len(season_rows))
            self.assertEqual(fold["primary"]["count"], len(primary_rows))
            for label, selected in (
                ("all_eligible", season_rows),
                ("primary", primary_rows),
            ):
                self.assertAlmostEqual(
                    fold[label]["null_mae"],
                    self._mae(selected, "null_prediction"),
                )
                self.assertAlmostEqual(
                    fold[label]["strong_mae"],
                    self._mae(selected, "strong_prediction"),
                )
            self.assertEqual(set(fold["primary_by_position"]), {"QB", "RB", "WR", "TE"})
            for position, metrics in fold["primary_by_position"].items():
                position_rows = [
                    row for row in primary_rows if row["position"] == position
                ]
                self.assertEqual(metrics["count"], len(position_rows))
                self.assertAlmostEqual(
                    metrics["strong_mae"],
                    self._mae(position_rows, "strong_prediction"),
                )

        pooled_primary = [row for row in predictions if row["primary_pool"]]
        self.assertEqual(report["pooled"]["primary"]["count"], len(pooled_primary))
        self.assertAlmostEqual(
            report["pooled"]["primary"]["strong_mae"],
            self._mae(pooled_primary, "strong_prediction"),
        )

        def finite_numbers(value):
            if isinstance(value, dict):
                return all(finite_numbers(item) for item in value.values())
            if isinstance(value, list):
                return all(finite_numbers(item) for item in value)
            return not isinstance(value, float) or math.isfinite(value)

        self.assertTrue(finite_numbers(report))
        self.assertNotIn("candidate", report)

    def test_receipt_serialization_is_deterministic_lf_only_and_finite(self):
        first_report, first_predictions = pgo_fantasy.backtest_baselines(
            self._rows(), self._audit()
        )
        second_report, second_predictions = pgo_fantasy.backtest_baselines(
            list(reversed(self._rows())), self._audit()
        )

        first_json = pgo_fantasy.serialize_baseline_report(first_report)
        second_json = pgo_fantasy.serialize_baseline_report(second_report)
        first_csv = pgo_fantasy.serialize_baseline_predictions(first_predictions)
        second_csv = pgo_fantasy.serialize_baseline_predictions(
            list(reversed(second_predictions))
        )

        self.assertEqual(first_json, second_json)
        self.assertEqual(first_csv, second_csv)
        self.assertTrue(first_json.endswith("\n"))
        self.assertTrue(first_csv.endswith("\n"))
        self.assertNotIn("\r", first_json)
        self.assertNotIn("\r", first_csv)
        self.assertEqual(
            first_csv.splitlines()[0].split(","),
            list(pgo_fantasy.PREDICTION_COLUMNS),
        )

        comma_name = copy.deepcopy(first_predictions)
        comma_name[0]["player_name"] = "Player, Quoted"
        self.assertIn(
            '"Player, Quoted"',
            pgo_fantasy.serialize_baseline_predictions(comma_name),
        )

        bad_report = copy.deepcopy(first_report)
        bad_report["pooled"]["primary"]["strong_mae"] = math.nan
        with self.assertRaises(ValueError):
            pgo_fantasy.serialize_baseline_report(bad_report)
        bad_predictions = copy.deepcopy(first_predictions)
        bad_predictions[0]["strong_prediction"] = math.inf
        with self.assertRaisesRegex(ValueError, "finite"):
            pgo_fantasy.serialize_baseline_predictions(bad_predictions)
        with self.assertRaisesRegex(ValueError, "zero"):
            pgo_fantasy.serialize_baseline_predictions([])
        with self.assertRaisesRegex(ValueError, "Invalid baseline prediction row"):
            pgo_fantasy.serialize_baseline_predictions([{}])

    def test_nonfinite_source_audit_cannot_be_bound(self):
        audit = self._audit()
        audit["bad"] = math.nan

        with self.assertRaises(ValueError):
            pgo_fantasy.backtest_baselines(self._rows(), audit)

if __name__ == "__main__":
    unittest.main()
