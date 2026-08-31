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


class PriorObservedFixture:
    COUNTS = {"QB": 30, "RB": 42, "WR": 30, "TE": 20}

    @staticmethod
    def _row(columns, **values):
        return {column: values.get(column, "") for column in columns}

    @staticmethod
    def _csv_bytes(columns, rows):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output, fieldnames=columns, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode("utf-8")

    def _source_rows(self, weeks=(1, 2, 3), counts=None):
        counts = self.COUNTS if counts is None else counts
        schedule = []
        stats = {season: [] for season in pgo_fantasy.MODEL_SEASONS}
        for season in pgo_fantasy.MODEL_SEASONS:
            for week in weeks:
                game_id = f"{season}_{week:02d}_BUF_LAR"
                schedule.append(self._row(
                    pgo_fantasy.SCHEDULE_COLUMNS,
                    game_id=game_id, season=str(season), week=str(week),
                    game_type="REG", gameday=f"{season}-09-{week:02d}",
                    gametime="13:00", away_team="BUF", home_team="LAR",
                    away_score="20", home_score="10",
                ))
                for position, count in counts.items():
                    for index in range(count):
                        stats[season].append(self._row(
                            pgo_fantasy.PLAYER_COLUMNS,
                            player_id=f"{position}-{index:02d}",
                            position=position, season=str(season),
                            week=str(week), season_type="REG",
                            game_id=game_id, team="BUF",
                            opponent_team="LAR",
                            receiving_yards=str(10 + index),
                        ))
        return schedule, stats

    def _write_sources(self, directory, schedule, stats):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        schedule_path = root / "schedule.csv"
        schedule_path.write_bytes(self._csv_bytes(
            pgo_fantasy.SCHEDULE_COLUMNS, schedule
        ))
        paths = {("schedule_results", None): schedule_path}
        for season in pgo_fantasy.MODEL_SEASONS:
            path = root / f"stats-{season}.csv.gz"
            path.write_bytes(gzip.compress(
                self._csv_bytes(pgo_fantasy.PLAYER_COLUMNS, stats[season]),
                mtime=0,
            ))
            paths[("player_weekly_stats", season)] = path
        return paths

    @staticmethod
    def _schedule_patch(paths):
        digest = hashlib.sha256(
            Path(paths[("schedule_results", None)]).read_bytes()
        ).hexdigest()
        return patch.object(pgo_sources, "EXPECTED_SOURCE_SHA256", digest)


class PriorObservedSourceContractTests(
    PriorObservedFixture, unittest.TestCase
):
    def test_inventory_is_schedule_plus_six_stats(self):
        specs = pgo_fantasy.prior_observed_source_specs()
        self.assertEqual(len(specs), 7)
        self.assertEqual(
            {(spec.name, spec.season) for spec in specs},
            {("schedule_results", None)} | {
                ("player_weekly_stats", season)
                for season in pgo_fantasy.MODEL_SEASONS
            },
        )

    def test_loader_reads_each_source_once_and_ignores_mapping_order(self):
        schedule, stats = self._source_rows(weeks=(1,))
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, stats)
            original = Path.read_bytes
            reads = []

            def counted(path):
                reads.append(Path(path))
                return original(path)

            with mock.patch.object(Path, "read_bytes", counted):
                first = pgo_fantasy._load_source_rows(
                    paths,
                    source_specs=pgo_fantasy.prior_observed_source_specs(),
                )
            second = pgo_fantasy._load_source_rows(
                dict(reversed(list(paths.items()))),
                source_specs=pgo_fantasy.prior_observed_source_specs(),
            )

        self.assertEqual(len(reads), 7)
        self.assertTrue(all(
            reads.count(Path(path)) == 1 for path in paths.values()
        ))
        self.assertEqual(first, second)


class PriorObservedCohortTests(PriorObservedFixture, unittest.TestCase):
    def _build(self, directory, schedule, stats):
        paths = self._write_sources(directory, schedule, stats)
        with self._schedule_patch(paths):
            return pgo_fantasy.build_prior_observed_games(paths)

    def test_prior_state_zero_fill_and_fullback_mapping(self):
        schedule, stats = self._source_rows(
            counts={"QB": 1, "FB": 1, "WR": 1, "TE": 1}
        )
        stats[2022] = [
            row for row in stats[2022]
            if not (row["week"] == "2" and row["player_id"] == "QB-00")
        ]
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._build(directory, schedule, stats)

        self.assertTrue(any(row["week"] == 1 for row in rows))
        self.assertTrue(all(
            not row["evaluation_eligible"]
            for row in rows if row["week"] == 1
        ))
        keyed = {
            (row["season"], row["week"], row["gsis_id"]): row
            for row in rows
        }
        self.assertEqual(keyed[(2022, 2, "QB-00")]["fantasy_points"], 0.0)
        self.assertEqual(keyed[(2022, 2, "FB-00")]["position"], "RB")
        week = next(
            row for row in audit["coverage"]
            if (row["season"], row["week"]) == (2022, 2)
        )
        self.assertEqual(
            (week["eligible"], week["matched_stats"], week["zero_filled"]),
            (4, 3, 1),
        )
        self.assertEqual(week["state_only"], 0)

    def test_first_appearance_enters_next_week(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        for week in (2, 3):
            source = next(
                row for row in stats[2022] if row["week"] == str(week)
            )
            stats[2022].append({**source, "player_id": "NEW-QB"})
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._build(directory, schedule, stats)

        self.assertEqual(
            [(row["season"], row["week"]) for row in rows
             if row["gsis_id"] == "NEW-QB"
             and row["evaluation_eligible"]],
            [(2022, 3)],
        )
        self.assertIn(
            (2022, 2, False),
            {(row["season"], row["week"], row["evaluation_eligible"])
             for row in rows if row["gsis_id"] == "NEW-QB"},
        )
        self.assertIn(
            ("cold_start", 2022, 2, "NEW-QB"),
            {(row["reason"], row["season"], row["week"], row["gsis_id"])
             for row in audit["diagnostics"]},
        )

    def test_future_rows_do_not_change_week_two(self):
        schedule, stats = self._source_rows(counts={"QB": 2})
        with tempfile.TemporaryDirectory() as first_directory:
            first, _ = self._build(first_directory, schedule, stats)
        changed = copy.deepcopy(stats)
        changed[2022] = [
            row for row in changed[2022] if row["week"] != "3"
        ]
        with tempfile.TemporaryDirectory() as second_directory:
            second, _ = self._build(second_directory, schedule, changed)

        select = lambda rows: [
            row for row in rows
            if (row["season"], row["week"]) == (2022, 2)
        ]
        self.assertEqual(select(first), select(second))

    def test_roster_bytes_and_path_mapping_order_have_no_influence(self):
        schedule, stats = self._source_rows(counts={"QB": 2})
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, stats)
            unrelated_roster = Path(directory) / "weekly-roster.csv"
            unrelated_roster.write_bytes(b"status,gsis_id\nACT,OLD\n")
            with self._schedule_patch(paths):
                first = pgo_fantasy.build_prior_observed_games(paths)
            unrelated_roster.write_bytes(b"status,gsis_id\nACT,CHANGED\n")
            reversed_paths = dict(reversed(list(paths.items())))
            with self._schedule_patch(reversed_paths):
                second = pgo_fantasy.build_prior_observed_games(reversed_paths)
        self.assertEqual(first, second)

    def test_most_recent_prior_position_controls_next_week(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        week_two = next(row for row in stats[2022]
                        if row["week"] == "2" and row["player_id"] == "QB-00")
        week_two["position"] = "TE"
        with tempfile.TemporaryDirectory() as directory:
            rows, _ = self._build(directory, schedule, stats)
        keyed = {(row["season"], row["week"], row["gsis_id"]): row
                 for row in rows}
        self.assertEqual(keyed[(2022, 2, "QB-00")]["position"], "QB")
        self.assertEqual(keyed[(2022, 3, "QB-00")]["position"], "TE")

    def test_unsupported_position_is_diagnostic_only(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        source = next(row for row in stats[2022] if row["week"] == "2")
        stats[2022].append({
            **source, "player_id": "K-00", "position": "K"
        })
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._build(directory, schedule, stats)

        self.assertNotIn("K-00", {row["gsis_id"] for row in rows})
        self.assertIn(
            ("unsupported_position", "K-00"),
            {(row["reason"], row["gsis_id"])
             for row in audit["diagnostics"]},
        )

    def test_invalid_relevant_stats_fail_closed(self):
        mutations = (
            lambda row: row.update(player_id=""),
            lambda row: row.update(team="ATL"),
            lambda row: row.update(receiving_yards="NaN"),
        )
        for mutate in mutations:
            schedule, stats = self._source_rows(counts={"QB": 1})
            mutate(next(row for row in stats[2022] if row["week"] == "2"))
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    self._build(directory, schedule, stats)

    def test_duplicate_player_week_fails_closed(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        target = next(row for row in stats[2022] if row["week"] == "2")
        stats[2022].append(copy.deepcopy(target))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Duplicate prior-observed"):
                self._build(directory, schedule, stats)

    def test_mixed_position_duplicate_player_week_fails_closed(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        target = next(row for row in stats[2022] if row["week"] == "2")
        stats[2022].append({**target, "position": "K"})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Duplicate prior-observed"):
                self._build(directory, schedule, stats)

    def test_unpinned_schedule_fails_closed(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, stats)
            with patch.object(
                pgo_sources, "EXPECTED_SOURCE_SHA256", "0" * 64
            ):
                with self.assertRaisesRegex(ValueError, "pinned SHA-256"):
                    pgo_fantasy.build_prior_observed_games(paths)

    def test_team_transition_keeps_prior_game_context(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        schedule.append(self._row(
            pgo_fantasy.SCHEDULE_COLUMNS,
            game_id="2022_02_ATL_CAR", season="2022", week="2",
            game_type="REG", gameday="2022-09-02", gametime="13:00",
            away_team="ATL", home_team="CAR",
            away_score="20", home_score="10",
        ))
        moved = next(row for row in stats[2022]
                     if row["week"] == "2" and row["player_id"] == "QB-00")
        moved.update(
            game_id="2022_02_ATL_CAR", team="ATL", opponent_team="CAR"
        )
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._build(directory, schedule, stats)
        prediction = next(row for row in rows
                          if (row["season"], row["week"], row["gsis_id"])
                          == (2022, 2, "QB-00"))
        self.assertEqual(
            (prediction["game_id"], prediction["team"], prediction["opponent"]),
            ("2022_02_BUF_LAR", "BUF", "LAR"),
        )
        self.assertGreater(prediction["fantasy_points"], 0.0)
        self.assertIn(
            ("team_transition", "QB-00", "BUF", "ATL"),
            {(row["reason"], row["gsis_id"], row["last_known_team"], row["team"])
             for row in audit["diagnostics"]},
        )

    def test_bye_transition_and_recency_expiry_are_unpredicted(self):
        schedule, stats = self._source_rows(
            weeks=tuple(range(1, 11)), counts={"QB": 1}
        )
        schedule.extend((
            self._row(
                pgo_fantasy.SCHEDULE_COLUMNS,
                game_id="2022_01_NYJ_MIA", season="2022", week="1",
                game_type="REG", gameday="2022-09-01", gametime="13:00",
                away_team="NYJ", home_team="MIA",
                away_score="20", home_score="10",
            ),
            self._row(
                pgo_fantasy.SCHEDULE_COLUMNS,
                game_id="2022_02_ATL_CAR", season="2022", week="2",
                game_type="REG", gameday="2022-09-02", gametime="13:00",
                away_team="ATL", home_team="CAR",
                away_score="20", home_score="10",
            ),
        ))
        week_one = next(row for row in stats[2022] if row["week"] == "1")
        week_two = next(row for row in stats[2022] if row["week"] == "2")
        week_ten = next(row for row in stats[2022] if row["week"] == "10")
        stats[2022].extend((
            {**week_one, "player_id": "BYE-QB", "game_id": "2022_01_NYJ_MIA",
             "team": "NYJ", "opponent_team": "MIA"},
            {**week_two, "player_id": "BYE-QB", "game_id": "2022_02_ATL_CAR",
             "team": "ATL", "opponent_team": "CAR"},
            {**week_one, "player_id": "EXPIRED-QB"},
            {**week_ten, "player_id": "EXPIRED-QB"},
        ))
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._build(directory, schedule, stats)
        keys = {(row["season"], row["week"], row["gsis_id"]) for row in rows}
        self.assertIn((2022, 2, "BYE-QB"), keys)
        self.assertIn((2022, 10, "EXPIRED-QB"), keys)
        self.assertFalse(next(row["evaluation_eligible"] for row in rows
                              if (row["season"], row["week"], row["gsis_id"])
                              == (2022, 2, "BYE-QB")))
        self.assertFalse(next(row["evaluation_eligible"] for row in rows
                              if (row["season"], row["week"], row["gsis_id"])
                              == (2022, 10, "EXPIRED-QB")))
        reasons = {(row["reason"], row["gsis_id"], row["week"])
                   for row in audit["diagnostics"]}
        self.assertIn(("bye_transition", "BYE-QB", 2), reasons)
        self.assertIn(("recency_expired", "EXPIRED-QB", 10), reasons)


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
        ), self._row(
            pgo_fantasy.PLAYER_COLUMNS,
            player_id="00-LAR-QB",
            position="QB",
            season="2022",
            week="1",
            season_type="REG",
            game_id="2022_01_BUF_LAR",
            team="LAR",
            opponent_team="BUF",
            passing_yards="200",
        )]
        rosters[2022].append(self._row(
            pgo_fantasy.ROSTER_COLUMNS,
            season="2022",
            week="1",
            game_type="REG",
            team="LAR",
            position="QB",
            status="ACT",
            full_name="Active Rams Quarterback",
            gsis_id="00-LAR-QB",
        ))
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
            roster_rows = list(rosters[season])
            represented = {row["team"] for row in roster_rows}
            roster_rows.extend(self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season=str(season), week="99", game_type="REG", team=team,
                position="K", status="ACT", full_name=f"Unused Kicker {season}",
                gsis_id=f"00-K-{season}-{team}",
            ) for team in sorted(set(pgo_fantasy.CURRENT_TEAMS) - represented))
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
            self.assertEqual(set(by_id), {"00-QB", "00-LAR-QB", "00-FB"})
            self.assertEqual(by_id["00-QB"]["fantasy_points"], 10.0)
            self.assertEqual(by_id["00-QB"]["opponent"], "LAR")
            self.assertEqual(by_id["00-FB"]["position"], "RB")
            self.assertEqual(by_id["00-FB"]["fantasy_points"], 0.0)
            self.assertEqual(
                audit["coverage"]["2022"],
                {
                    "eligible": 3,
                    "matched_stats": 2,
                    "zero_filled": 1,
                    "bye_skipped": 1,
                    "excluded_stats": 0,
                },
            )
            self.assertEqual(audit["position_authority"], "NFLVERSE_WEEKLY_ROSTER")
            self.assertEqual(audit["position_mapping"], {"FB": "RB"})
            self.assertEqual(audit["blocking_discrepancies"]["total"], 0)
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
                "duplicate_roster_identity",
                lambda rows: rows.append(copy.deepcopy(rows[0])),
            ),
            "missing status": (
                "missing_roster_status",
                lambda rows: rows[0].update(status=""),
            ),
            "missing id": (
                "missing_roster_identity",
                lambda rows: rows[0].update(gsis_id=""),
            ),
            "conflicting team": (
                "duplicate_roster_identity",
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
            "unmatched": ("missing_roster", add_unmatched),
            "duplicate": (
                "duplicate_stat_identity",
                lambda rows: rows.append(copy.deepcopy(rows[0])),
            ),
            "wrong team": (
                "schedule_identity",
                lambda rows: rows[0].update(team="LAR", opponent_team="BUF"),
            ),
            "wrong week": (
                "missing_roster",
                lambda rows: rows[0].update(week="2"),
            ),
        }
        for label, (message, mutate) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                schedule, rosters, stats = self._base_rows()
                mutate(stats[2022])
                paths = self._write_sources(directory, schedule, rosters, stats)
                with self.assertRaisesRegex(ValueError, message):
                    pgo_fantasy.build_player_games(paths)

    def test_stat_position_is_diagnostic_and_never_changes_model_rows(self):
        schedule, rosters, stats = self._base_rows()
        with tempfile.TemporaryDirectory() as directory:
            baseline_directory = Path(directory) / "baseline"
            changed_directory = Path(directory) / "changed"
            baseline_directory.mkdir()
            changed_directory.mkdir()
            baseline_paths = self._write_sources(
                baseline_directory, schedule, rosters, stats
            )
            baseline_rows, _ = pgo_fantasy.build_player_games(baseline_paths)

            changed_stats = copy.deepcopy(stats)
            changed_stats[2022][0]["position"] = "TE"
            changed_paths = self._write_sources(
                changed_directory, schedule, rosters, changed_stats
            )
            changed_rows, audit = pgo_fantasy.build_player_games(changed_paths)

        self.assertEqual(
            pgo_fantasy.serialize_fantasy_source_json({"rows": changed_rows}),
            pgo_fantasy.serialize_fantasy_source_json({"rows": baseline_rows}),
        )
        quarterback = next(row for row in changed_rows if row["gsis_id"] == "00-QB")
        self.assertEqual(quarterback["position"], "QB")
        self.assertEqual(quarterback["fantasy_points"], 10.0)
        self.assertEqual(
            audit["diagnostics"]["counts"]["stat_position_disagreement"], 1
        )
        self.assertEqual(
            audit["diagnostics"]["fantasy_point_totals"]
            ["stat_position_disagreement"], 10.0,
        )

    def test_act_unmodeled_roster_stat_is_excluded_and_audited(self):
        schedule, rosters, stats = self._base_rows()
        rosters[2022].append(self._row(
            pgo_fantasy.ROSTER_COLUMNS,
            season="2022", week="1", game_type="REG", team="BUF",
            position="LB", status="ACT", full_name="Two Way Player",
            gsis_id="00-LB",
        ))
        stats[2022].append(self._row(
            pgo_fantasy.PLAYER_COLUMNS,
            player_id="00-LB", position="WR", season="2022", week="1",
            season_type="REG", game_id="2022_01_BUF_LAR", team="BUF",
            opponent_team="LAR", receiving_yards="50",
        ))

        with tempfile.TemporaryDirectory() as directory:
            rows, audit = pgo_fantasy.build_player_games(
                self._write_sources(directory, schedule, rosters, stats)
            )

        self.assertEqual({row["gsis_id"] for row in rows}, {"00-QB", "00-LAR-QB", "00-FB"})
        self.assertEqual(audit["coverage"]["2022"]["excluded_stats"], 1)
        self.assertEqual(
            audit["diagnostics"]["counts"]["act_unmodeled_roster_stat"], 1
        )
        self.assertEqual(
            audit["diagnostics"]["fantasy_point_totals"]
            ["act_unmodeled_roster_stat"], 5.0,
        )

    def test_noneligible_missing_identity_is_diagnostic_but_eligible_is_blocking(self):
        schedule, rosters, stats = self._base_rows()
        rosters[2022].append(self._row(
            pgo_fantasy.ROSTER_COLUMNS,
            season="2022", week="1", game_type="REG", team="BUF",
            position="LB", status="RES", full_name="Reserve Defender",
            gsis_id="",
        ))
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, rosters, stats)
            _, audit = pgo_fantasy.build_player_games(paths)
        self.assertEqual(
            audit["diagnostics"]["counts"]
            ["noneligible_roster_missing_identity"], 1,
        )

        rosters[2022][-1].update(position="QB", status="ACT")
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, rosters, stats)
            with self.assertRaisesRegex(ValueError, "missing_roster_identity"):
                pgo_fantasy.build_player_games(paths)

    def test_taysom_like_roster_qb_stat_te_emits_qb_target(self):
        schedule, rosters, stats = self._base_rows()
        stats[2022][0].update(
            position="TE", passing_yards="", rushing_yards="20",
            receptions="2", receiving_yards="30",
        )
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = pgo_fantasy.build_player_games(
                self._write_sources(directory, schedule, rosters, stats)
            )
        quarterback = next(row for row in rows if row["gsis_id"] == "00-QB")
        self.assertEqual(quarterback["position"], "QB")
        self.assertEqual(quarterback["fantasy_points"], 6.0)
        self.assertEqual(
            audit["diagnostics"]["counts"]["stat_position_disagreement"], 1
        )


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
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["position_authority"], "NFLVERSE_WEEKLY_ROSTER")
        self.assertEqual(receipt["position_mapping"], {"FB": "RB"})
        self.assertEqual(receipt["blocking_discrepancies"]["total"], 0)
        self.assertEqual(receipt["diagnostics"]["total"], 0)
        self.assertTrue(all(
            count == 0
            for count in receipt["blocking_discrepancies"]["counts"].values()
        ))
        self.assertEqual(receipt["coverage"]["2022"], {
            "eligible": 2,
            "matched_stats": 2,
            "zero_filled": 0,
            "bye_skipped": 0,
            "excluded_stats": 0,
        })

    def test_schema_one_qualification_receipt_cannot_pass_v2_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory)
            with self._fixture_schedule_digest(paths):
                lock_text = self._source_lock_text(paths)
                receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
                receipt["schema_version"] = 1
                with self.assertRaisesRegex(ValueError, "not PASS"):
                    pgo_fantasy.validate_fantasy_source_qualification(
                        lock_text, receipt
                    )

    def test_stat_position_disagreement_is_nonblocking_and_deterministic(self):
        def mutate(schedule, rosters, stats):
            stats[2022][0]["position"] = "TE"

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, mutate)
            with self._fixture_schedule_digest(paths):
                lock_text = self._source_lock_text(paths)
                first = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
                second = pgo_fantasy.qualify_fantasy_sources(
                    dict(reversed(list(paths.items()))), lock_text
                )
                pgo_fantasy.validate_fantasy_source_qualification(
                    lock_text, first
                )

        self.assertEqual(first, second)
        self.assertEqual(first["qualification_status"], "PASS")
        self.assertEqual(first["blocking_discrepancies"]["total"], 0)
        self.assertEqual(
            first["diagnostics"]["counts"]["stat_position_disagreement"], 1
        )

    def test_act_unmodeled_scoring_stat_is_excluded_not_population(self):
        def mutate(schedule, rosters, stats):
            rosters[2022].append(self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022", week="1", game_type="REG", team="BUF",
                position="DB", status="ACT", full_name="Hybrid Defender",
                gsis_id="HYBRID-DB",
            ))
            stats[2022].append(self._row(
                pgo_fantasy.PLAYER_COLUMNS,
                player_id="HYBRID-DB", position="WR", season="2022", week="1",
                season_type="REG", game_id="2022_01_BUF_LAR", team="BUF",
                opponent_team="LAR", receptions="1", receiving_yards="10",
            ))

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, mutate)
            with self._fixture_schedule_digest(paths):
                lock_text = self._source_lock_text(paths)
                receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
                pgo_fantasy.validate_fantasy_source_qualification(
                    lock_text, receipt
                )

        self.assertEqual(receipt["qualification_status"], "PASS")
        self.assertEqual(receipt["coverage"]["2022"]["eligible"], 2)
        self.assertEqual(receipt["coverage"]["2022"]["excluded_stats"], 1)
        self.assertEqual(
            receipt["diagnostics"]["counts"]["act_unmodeled_roster_stat"], 1
        )
        self.assertEqual(
            receipt["diagnostics"]["fantasy_point_totals"]
            ["act_unmodeled_roster_stat"],
            1.5,
        )

    def test_noneligible_missing_ids_keep_every_source_row(self):
        def mutate(schedule, rosters, stats):
            for name in ("First", "Second"):
                rosters[2022].append(self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="BUF",
                    position="LB", status="RES", full_name=name, gsis_id="",
                ))

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, mutate)
            with self._fixture_schedule_digest(paths):
                lock_text = self._source_lock_text(paths)
                receipt = pgo_fantasy.qualify_fantasy_sources(
                    paths, lock_text
                )
                pgo_fantasy.validate_fantasy_source_qualification(
                    lock_text, receipt
                )

        rows = [
            row for row in receipt["diagnostics"]["rows"]
            if row["reason"] == "noneligible_roster_missing_identity"
        ]
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["source_row_number"], rows[1]["source_row_number"])
        self.assertEqual(
            receipt["diagnostics"]["counts"]
            ["noneligible_roster_missing_identity"], 2,
        )

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
            next(
                row for row in rosters[season]
                if row["team"] == "ARI" and row["position"] == "K"
            )["game_type"] = "POST"
            rosters[season].extend([
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="INA", full_name="Non ACT", gsis_id="NON-ACT"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="ACT", full_name="Position Conflict", gsis_id="POS-CONFLICT"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="ACT", full_name="Duplicate", gsis_id="DUP-ROSTER"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="LAR", position="WR", status="ACT", full_name="Duplicate", gsis_id="DUP-ROSTER"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="", full_name="Missing Status", gsis_id="MISSING-STATUS"),
                self._row(pgo_fantasy.ROSTER_COLUMNS, season="2022", week="1", game_type="REG", team="BUF", position="WR", status="ACT", full_name="Missing ID", gsis_id=""),
                self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="BUF",
                    position="QB", status="ACT", full_name="Invalid Target",
                    gsis_id="INVALID-TARGET",
                ),
                self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="BUF",
                    position="DB", status="ACT", full_name="Hybrid Defender",
                    gsis_id="HYBRID-DB",
                ),
                self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="BUF",
                    position="LB", status="RES",
                    full_name="Missing Noneligible ID", gsis_id="",
                ),
            ])
            stats[season].extend([
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="NO-ROSTER", position="WR", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="LAR", receiving_yards="40"),
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="NON-ACT", position="WR", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="LAR", receiving_yards="40"),
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="POS-CONFLICT", position="RB", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="LAR", rushing_yards="40"),
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="BAD-SCHEDULE", position="WR", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="BUF", receiving_yards="40"),
                self._row(pgo_fantasy.PLAYER_COLUMNS, player_id="", position="WR", season="2022", week="1", season_type="REG", game_id=game_id, team="BUF", opponent_team="LAR", receiving_yards="40"),
                self._row(
                    pgo_fantasy.PLAYER_COLUMNS,
                    player_id="INVALID-TARGET", position="QB", season="2022",
                    week="1", season_type="REG", game_id=game_id, team="BUF",
                    opponent_team="LAR", passing_yards="NaN",
                ),
                self._row(
                    pgo_fantasy.PLAYER_COLUMNS,
                    player_id="HYBRID-DB", position="WR", season="2022",
                    week="1", season_type="REG", game_id=game_id, team="BUF",
                    opponent_team="LAR", receptions="1", receiving_yards="10",
                ),
            ])
            rosters[season].append(self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022", week="1", game_type="REG", team="BUF",
                position="WR", status="ACT", full_name="Bad Schedule",
                gsis_id="BAD-SCHEDULE",
            ))
            stats[season].append(copy.deepcopy(next(
                row for row in stats[season]
                if row["player_id"] == "BAD-SCHEDULE"
            )))

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
        self.assertEqual(
            {row["reason"] for row in first["blocking_discrepancies"]["rows"]},
            set(pgo_fantasy.FANTASY_BLOCKING_CLASSES),
        )
        self.assertEqual(
            {row["reason"] for row in first["diagnostics"]["rows"]},
            set(pgo_fantasy.FANTASY_DIAGNOSTIC_CLASSES),
        )
        for name, classes in (
            ("blocking_discrepancies", pgo_fantasy.FANTASY_BLOCKING_CLASSES),
            ("diagnostics", pgo_fantasy.FANTASY_DIAGNOSTIC_CLASSES),
        ):
            summary = first[name]
            self.assertEqual(summary["rows"], sorted(
                summary["rows"], key=pgo_fantasy._finding_key
            ))
            self.assertEqual(summary["counts"], {
                reason: sum(
                    row["reason"] == reason for row in summary["rows"]
                )
                for reason in classes
            })
            self.assertEqual(summary["by_season"], {
                str(season): {
                    reason: sum(
                        row["season"] == season and row["reason"] == reason
                        for row in summary["rows"]
                    )
                    for reason in classes
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

    def test_unmapped_stat_position_is_nonblocking_diagnostic(self):
        def mutate(schedule, rosters, stats):
            stats[2022][0]["position"] = "K"

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, mutate)
            with self._fixture_schedule_digest(paths):
                receipt = pgo_fantasy.qualify_fantasy_sources(
                    paths, self._source_lock_text(paths)
                )

        self.assertEqual(receipt["qualification_status"], "PASS")
        self.assertEqual(receipt["blocking_discrepancies"]["total"], 0)
        self.assertEqual(receipt["diagnostics"]["counts"]["stat_position_disagreement"], 1)
        self.assertEqual(receipt["coverage"]["2022"], {
            "eligible": 2, "matched_stats": 2, "zero_filled": 0, "bye_skipped": 0,
            "excluded_stats": 0,
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
            receipt["blocking_discrepancies"]["counts"]["incomplete_stat_team_week_coverage"],
            12,
        )
        self.assertEqual(receipt["blocking_discrepancies"]["by_season"], {
            str(season): {
                **{
                    reason: 0
                    for reason in pgo_fantasy.FANTASY_BLOCKING_CLASSES
                },
                "incomplete_stat_team_week_coverage": 2,
            }
            for season in pgo_fantasy.MODEL_SEASONS
        })

    def test_unmodeled_nonroster_stats_do_not_satisfy_team_week_coverage(self):
        def unmodeled_nonroster(schedule, rosters, stats):
            for season, rows in stats.items():
                for row in rows:
                    row["player_id"] = f"K-NON-ROSTER-{season}-{row['team']}"
                    row["position"] = "K"

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, unmodeled_nonroster)
            with self._fixture_schedule_digest(paths):
                receipt = pgo_fantasy.qualify_fantasy_sources(
                    paths, self._source_lock_text(paths)
                )

        self.assertEqual(receipt["qualification_status"], "BLOCKED")
        self.assertFalse(receipt["checks"]["stat_team_week_coverage"])
        self.assertEqual(
            receipt["blocking_discrepancies"]["counts"]["incomplete_stat_team_week_coverage"],
            12,
        )
        self.assertEqual(receipt["coverage"], {
            str(season): {
                "eligible": 2,
                "matched_stats": 0,
                "zero_filled": 2,
                "bye_skipped": 0,
                "excluded_stats": 0,
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
        self.assertEqual(receipt["blocking_discrepancies"]["rows"], [{
            "reason": "incomplete_stat_team_week_coverage",
            "season": 2022,
            "week": 1,
            "gsis_id": "",
            "game_id": "",
            "team": "BUF",
            "source": "player_weekly_stats:2022",
            "source_row_number": 0,
        }])
        self.assertEqual(receipt["coverage"]["2022"], {
            "eligible": 2, "matched_stats": 1, "zero_filled": 1, "bye_skipped": 0,
            "excluded_stats": 0,
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
                root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
            ).read_text(encoding="utf-8"))
            lock_text = (
                root / pgo_fantasy.FANTASY_CANDIDATE_LOCK
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
                root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
            ).read_text(encoding="utf-8"))

            self.assertEqual(code, 1)
            self.assertEqual(receipt["qualification_status"], "BLOCKED")
            self.assertGreater(receipt["blocking_discrepancies"]["total"], 0)
            self.assertFalse((root / "research/pgo_fantasy").exists())

    def test_v2_freeze_never_reads_or_writes_august_27_candidate_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_lock = root / "output/pgo-fantasy-source-candidate.lock.json"
            old_receipt = root / "output/pgo-fantasy-source-qualification.json"
            old_lock.parent.mkdir(parents=True)
            old_lock.write_bytes(b"immutable old lock\n")
            old_receipt.write_bytes(b"immutable old receipt\n")
            payloads = self._payloads(root)

            code = self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            )

            self.assertEqual(code, 0)
            self.assertEqual(old_lock.read_bytes(), b"immutable old lock\n")
            self.assertEqual(old_receipt.read_bytes(), b"immutable old receipt\n")
            self.assertTrue((root / pgo_fantasy.FANTASY_CANDIDATE_LOCK).exists())
            self.assertTrue((
                root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
            ).exists())

    def test_accept_rejects_schema_one_receipt_without_fetch_or_research(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            self.assertEqual(self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            ), 0)
            receipt_path = root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
            receipt = json.loads(receipt_path.read_bytes().decode("utf-8"))
            receipt["schema_version"] = 1
            receipt_path.write_bytes(
                pgo_fantasy.serialize_fantasy_source_json(receipt).encode("utf-8")
            )

            schedule = next(
                spec for spec in pgo_fantasy.fantasy_source_specs()
                if spec.name == "schedule_results"
            )
            digest = hashlib.sha256(payloads[schedule.url]).hexdigest()
            previous = Path.cwd()
            os.chdir(root)
            try:
                with patch.object(
                    pgo_sources, "EXPECTED_SOURCE_SHA256", digest
                ), patch.object(
                    pgo_sources, "freeze_sources"
                ) as freeze, redirect_stderr(io.StringIO()):
                    code = pgo_fantasy.main(["--accept-qualified"])
            finally:
                os.chdir(previous)

            self.assertEqual(code, 2)
            freeze.assert_not_called()
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
                lock_path = root / pgo_fantasy.FANTASY_CANDIDATE_LOCK
                receipt_path = root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
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

    def test_accept_rejects_crlf_candidate_lock_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            self.assertEqual(self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            ), 0)
            lock_path = root / pgo_fantasy.FANTASY_CANDIDATE_LOCK
            lock_path.write_bytes(lock_path.read_bytes().replace(b"\n", b"\r\n"))
            with redirect_stderr(io.StringIO()):
                code = self._run_in_root(root, ["--accept-qualified"], payloads)

            self.assertEqual(code, 2)
            self.assertFalse((root / "research/pgo_fantasy").exists())

    def test_accept_rejects_crlf_candidate_receipt_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            self.assertEqual(self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            ), 0)
            receipt_path = root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
            receipt_path.write_bytes(
                receipt_path.read_bytes().replace(b"\n", b"\r\n")
            )
            with redirect_stderr(io.StringIO()):
                code = self._run_in_root(root, ["--accept-qualified"], payloads)

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
                    path = root / pgo_fantasy.FANTASY_CANDIDATE_LOCK
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
                root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
            ).read_text(encoding="utf-8"))
            self.assertEqual(code, 2)
            self.assertEqual(receipt["schema_version"], 2)
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
                root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
            ).read_text(encoding="utf-8"))
            self.assertEqual(code, 2)
            self.assertFalse((
                root / pgo_fantasy.FANTASY_CANDIDATE_LOCK
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
            candidate = root / pgo_fantasy.FANTASY_CANDIDATE_LOCK

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
                root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
            ).exists())
            self.assertFalse(claim.exists())

    def test_freeze_rollback_keeps_interfering_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            original = pgo_fantasy._exclusive_write_text
            candidate = root / pgo_fantasy.FANTASY_CANDIDATE_LOCK
            receipt = root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
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
            target = root / pgo_fantasy.FANTASY_CANDIDATE_LOCK
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
            "schema_version": 2,
            "scope": {
                "seasons": list(pgo_fantasy.MODEL_SEASONS),
                "game_type": "REG",
                "roster_status": "ACT",
            },
            "position_authority": pgo_fantasy.FANTASY_POSITION_AUTHORITY,
            "position_mapping": dict(pgo_fantasy.FANTASY_POSITION_MAPPING),
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
                    "excluded_stats": 0,
                }
                for season in pgo_fantasy.MODEL_SEASONS
            },
            "blocking_discrepancies": pgo_fantasy._summarize_findings(
                [], pgo_fantasy.FANTASY_BLOCKING_CLASSES
            ),
            "diagnostics": pgo_fantasy._summarize_findings(
                [],
                pgo_fantasy.FANTASY_DIAGNOSTIC_CLASSES,
                pgo_fantasy.FANTASY_POINT_DIAGNOSTICS,
            ),
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
                {"schema_version": 2, "checks": {"source_contract": True}},
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
