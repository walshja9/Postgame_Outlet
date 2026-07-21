import csv
import gzip
import hashlib
import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pgo_challenger
import pgo_model
import pgo_sources


def _write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _synthetic_paths(directory, *, mutate_game=None, aliases=True, offseason_change=True):
    canonical = {"OAK": "LV", "SD": "LAC", "STL": "LAR", "LA": "LAR"}

    def team(value):
        return value if aliases else canonical.get(value, value)

    games = [
        ("g1", 2013, 1, "2013-09-01", "OAK", "SD", 17, 24, "LV Coach", "LAC Coach"),
        ("g2", 2013, 2, "2013-09-08", "SD", "STL", 20, 21, "LAC Coach", "LAR Coach"),
        (
            "g3", 2014, 1, "2014-09-01", "LA", "OAK", 14, 27,
            "LAR Coach", "New LV Coach" if offseason_change else "LV Coach",
        ),
        (
            "g4", 2014, 2, "2014-09-08", "OAK", "SD", 23, 20,
            "New LV Coach" if offseason_change else "LV Coach", "LAC Coach",
        ),
    ]
    schedule = []
    for game_id, season, week, day, away, home, away_score, home_score, away_coach, home_coach in games:
        if game_id == mutate_game:
            home_score += 40
        schedule.append({
            "game_id": game_id,
            "season": season,
            "week": week,
            "game_type": "REG",
            "gameday": day,
            "gametime": "13:00",
            "away_team": team(away),
            "home_team": team(home),
            "away_score": away_score,
            "home_score": home_score,
            "location": "Home",
            "away_rest": 7 if week > 1 else 210,
            "home_rest": 7 if week > 1 else 210,
            "away_coach": away_coach,
            "home_coach": home_coach,
        })
    schedule_path = directory / "schedule.csv"
    _write_csv(schedule_path, pgo_sources.SCHEDULE_COLUMNS, schedule)
    paths = {("schedule_results", None): schedule_path}

    game_teams = {
        "g1": (("OAK", "SD", 12.0), ("SD", "OAK", 20.0)),
        "g2": (("SD", "STL", 5.0), ("STL", "SD", 1.0)),
        "g3": (("LA", "OAK", 2.0), ("OAK", "LA", 8.0)),
        "g4": (("OAK", "SD", 4.0), ("SD", "OAK", 2.0)),
    }
    roster_qbs = {
        (2013, 1, "OAK"): "lv-old",
        (2013, 1, "SD"): "lac-qb",
        (2013, 2, "SD"): "lac-qb",
        (2013, 2, "STL"): "lar-qb",
        (2014, 1, "LA"): "lar-qb",
        (2014, 1, "OAK"): "lac-qb" if offseason_change else "lv-old",
        (2014, 2, "OAK"): "lac-qb" if offseason_change else "lv-old",
        (2014, 2, "SD"): "lac-new",
    }
    stats_by_season = {2013: [], 2014: []}
    players_by_season = {2013: [], 2014: []}
    rosters_by_season = {2013: [], 2014: []}
    snaps_by_season = {2013: [], 2014: []}
    for game_id, season, week, *_ in games:
        for raw_team, opponent, passing_epa in game_teams[game_id]:
            qb = roster_qbs[(season, week, raw_team)]
            changed = game_id == mutate_game
            stats_by_season[season].append({
                "season": season,
                "week": week,
                "team": team(raw_team),
                "game_id": game_id,
                "opponent_team": team(opponent),
                "attempts": 20,
                "carries": 20,
                "passing_epa": passing_epa + (100.0 if changed else 0.0),
                "rushing_epa": 3.0 + (50.0 if changed else 0.0),
                "sacks_suffered": 2,
                "passing_interceptions": 1,
                "fumbles_lost_total": 0,
                "passing_20": 3 + (10 if changed else 0),
                "rushing_20": 1,
            })
            players_by_season[season].append({
                "player_id": f"gsis-{qb}",
                "position": "QB",
                "season": season,
                "week": week,
                "team": team(raw_team),
                "attempts": 20,
                "passing_epa": passing_epa + (100.0 if changed else 0.0),
                "passing_cpoe": 2.0,
                "sacks_suffered": 2,
                "passing_interceptions": 1,
                "sack_fumbles_lost": 0,
                "carries": 3,
                "rushing_epa": 1.5,
            })
            rosters_by_season[season].append({
                "season": season,
                "week": week,
                "team": team(raw_team),
                "position": "QB",
                "gsis_id": f"gsis-{qb}",
                "pfr_id": f"pfr-{qb}",
                "years_exp": 3,
                "draft_number": 20,
            })
            snaps_by_season[season].append({
                "season": season,
                "week": week,
                "team": team(raw_team),
                "pfr_player_id": f"pfr-{qb}",
                "position": "QB",
                "offense_snaps": 99 if changed else 50,
                "defense_snaps": 0,
            })

    for season in (2013, 2014):
        for name, columns, rows in (
            ("team_weekly_stats", pgo_sources.TEAM_COLUMNS, stats_by_season[season]),
            ("player_weekly_stats", pgo_sources.PLAYER_COLUMNS, players_by_season[season]),
            ("weekly_rosters", pgo_sources.ROSTER_COLUMNS, rosters_by_season[season]),
            ("injury_reports", pgo_sources.INJURY_COLUMNS, []),
            ("snap_counts", pgo_sources.SNAP_COLUMNS, snaps_by_season[season]),
        ):
            path = directory / f"{name}-{season}.csv"
            _write_csv(path, columns, rows)
            paths[(name, season)] = path
    return paths


def _add_current_roster(paths, directory, *, team="SD", player="future-qb"):
    path = directory / "current-roster-2026.csv"
    _write_csv(path, pgo_sources.ROSTER_COLUMNS, [{
        "season": 2026,
        "week": 0,
        "team": team,
        "position": "QB",
        "gsis_id": f"gsis-{player}",
        "pfr_id": f"pfr-{player}",
        "years_exp": 9,
        "draft_number": 1,
    }])
    paths[("current_roster", 2026)] = path


def _pregame_bytes(row):
    return json.dumps(
        {
            "game_id": row.game_id,
            "season": row.season,
            "week": row.week,
            "kickoff": row.kickoff,
            "features": row.features,
            "subgroup_flags": row.subgroup_flags,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _model_row(game_id, season, signal, margin):
    return pgo_challenger.FeatureRow(
        game_id,
        season,
        1,
        f"{season}-09-01T13:00-04:00",
        margin,
        {"signal": signal},
        {},
    )


class SourceTests(unittest.TestCase):
    def test_source_inventory_uses_the_frozen_2013_and_url_contracts(self):
        specs = pgo_sources.source_specs()
        grouped = {}
        for spec in specs:
            grouped.setdefault(spec.name, []).append(spec)

        self.assertEqual(
            sorted(grouped),
            [
                "current_roster",
                "injury_reports",
                "player_weekly_stats",
                "schedule_results",
                "snap_counts",
                "team_weekly_stats",
                "weekly_rosters",
            ],
        )
        for name in (
            "injury_reports",
            "player_weekly_stats",
            "snap_counts",
            "team_weekly_stats",
            "weekly_rosters",
        ):
            self.assertEqual([spec.season for spec in grouped[name]], list(range(2013, 2026)))

        self.assertEqual(
            [spec.url for spec in grouped["team_weekly_stats"]],
            [
                f"https://github.com/nflverse/nflverse-data/releases/download/"
                f"stats_team/stats_team_week_{season}.csv.gz"
                for season in range(2013, 2026)
            ],
        )
        self.assertEqual(
            [spec.url for spec in grouped["player_weekly_stats"]],
            [
                f"https://github.com/nflverse/nflverse-data/releases/download/"
                f"stats_player/stats_player_week_{season}.csv.gz"
                for season in range(2013, 2026)
            ],
        )
        self.assertEqual(
            [spec.url for spec in grouped["weekly_rosters"]],
            [
                f"https://github.com/nflverse/nflverse-data/releases/download/"
                f"weekly_rosters/roster_weekly_{season}.csv"
                for season in range(2013, 2026)
            ],
        )
        self.assertEqual(
            [spec.url for spec in grouped["injury_reports"]],
            [
                f"https://github.com/nflverse/nflverse-data/releases/download/"
                f"injuries/injuries_{season}.csv"
                for season in range(2013, 2026)
            ],
        )
        self.assertEqual(
            [spec.url for spec in grouped["snap_counts"]],
            [
                f"https://github.com/nflverse/nflverse-data/releases/download/"
                f"snap_counts/snap_counts_{season}.csv"
                for season in range(2013, 2026)
            ],
        )
        self.assertEqual(
            [(spec.season, spec.url) for spec in grouped["current_roster"]],
            [
                (
                    2026,
                    "https://github.com/nflverse/nflverse-data/releases/"
                    "download/rosters/roster_2026.csv.gz",
                )
            ],
        )
        self.assertEqual(len(grouped["schedule_results"]), 1)
        self.assertEqual(
            (grouped["schedule_results"][0].season, grouped["schedule_results"][0].url),
            (
                None,
                "https://raw.githubusercontent.com/nflverse/nfldata/"
                "29102e4f32febb597750c71a27f22fb2898e3cfc/data/games.csv",
            ),
        )
        required_columns = {
            "schedule_results": (
                "game_id", "season", "week", "game_type", "gameday", "gametime",
                "away_team", "home_team", "away_score", "home_score", "location",
                "away_rest", "home_rest", "away_coach", "home_coach",
            ),
            "team_weekly_stats": (
                "season", "week", "team", "game_id", "opponent_team", "attempts",
                "carries", "passing_epa", "rushing_epa", "sacks_suffered",
                "passing_interceptions", "fumbles_lost_total", "passing_20", "rushing_20",
            ),
            "player_weekly_stats": (
                "player_id", "position", "season", "week", "team", "attempts",
                "passing_epa", "passing_cpoe", "sacks_suffered",
                "passing_interceptions", "sack_fumbles_lost", "carries", "rushing_epa",
            ),
            "weekly_rosters": (
                "season", "week", "team", "position", "gsis_id", "pfr_id",
                "years_exp", "draft_number",
            ),
            "injury_reports": (
                "season", "week", "team", "gsis_id", "position", "report_status",
                "practice_status",
            ),
            "snap_counts": (
                "season", "week", "team", "pfr_player_id", "position",
                "offense_snaps", "defense_snaps",
            ),
            "current_roster": (
                "season", "week", "team", "position", "gsis_id", "pfr_id",
                "years_exp", "draft_number",
            ),
        }
        for name, named_specs in grouped.items():
            self.assertTrue(all(spec.required_columns == required_columns[name] for spec in named_specs))

    def test_freeze_records_sorted_urls_sizes_and_hashes(self):
        specs = (
            pgo_sources.SourceSpec(
                "zeta", 2020, "https://example.test/zeta.csv.gz", ("value",)
            ),
            pgo_sources.SourceSpec(
                "alpha", None, "https://example.test/alpha.csv.gz", ("value",)
            ),
        )
        payloads = {
            specs[0].url: gzip.compress(b"value\nzeta\n", mtime=0),
            specs[1].url: gzip.compress(b"value\nalpha\n", mtime=0),
        }

        with tempfile.TemporaryDirectory() as temp:
            cache_dir = Path(temp, "cache")
            lock_path = Path(temp, "sources.lock.json")
            first = pgo_sources.freeze_sources(
                specs,
                cache_dir,
                lock_path,
                "2026-07-21T12:00:00-04:00",
                fetch=payloads.__getitem__,
            )
            first_bytes = lock_path.read_bytes()
            second = pgo_sources.freeze_sources(
                tuple(reversed(specs)),
                cache_dir,
                lock_path,
                "2026-07-21T12:00:00-04:00",
                fetch=payloads.__getitem__,
            )
            second_bytes = lock_path.read_bytes()

            expected = {
                "sources": [
                    {
                        "name": spec.name,
                        "season": spec.season,
                        "url": spec.url,
                        "sha256": hashlib.sha256(payloads[spec.url]).hexdigest(),
                        "bytes": len(payloads[spec.url]),
                        "frozen_at": "2026-07-21T12:00:00-04:00",
                    }
                    for spec in reversed(specs)
                ]
            }
            cached = sorted(path.name for path in cache_dir.iterdir())

        self.assertEqual(first, expected)
        self.assertEqual(second, expected)
        self.assertEqual(first_bytes, json.dumps(expected, indent=2, sort_keys=True).encode() + b"\n")
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(
            cached,
            sorted(f"{entry['sha256']}.csv.gz" for entry in expected["sources"]),
        )

    def test_locked_loader_rejects_changed_bytes(self):
        spec = pgo_sources.SourceSpec(
            "team_weekly_stats",
            2013,
            "https://example.test/team.csv.gz",
            ("team",),
        )
        payload = gzip.compress(b"team\nLV\n", mtime=0)

        with tempfile.TemporaryDirectory() as temp:
            cache_dir = Path(temp, "cache")
            lock_path = Path(temp, "sources.lock.json")
            manifest = pgo_sources.freeze_sources(
                (spec,), cache_dir, lock_path, "frozen", fetch=lambda _: payload
            )
            cached = Path(cache_dir, f"{manifest['sources'][0]['sha256']}.csv.gz")
            changed = bytearray(cached.read_bytes())
            changed[-1] ^= 1
            cached.write_bytes(changed)

            with self.assertRaisesRegex(ValueError, "team_weekly_stats.*2013"):
                pgo_sources.load_locked_sources(lock_path, cache_dir)

    def test_schema_change_fails_before_modeling(self):
        modeled = []

        with tempfile.TemporaryDirectory() as temp:
            paths = self._write_inventory(Path(temp), omit=("team_weekly_stats", 2013))
            with self.assertRaisesRegex(ValueError, "team_weekly_stats.*2013.*rushing_20"):
                audit = pgo_sources.validate_source_audit(paths)
                modeled.append(audit)

        self.assertEqual(modeled, [])

    def test_header_only_source_fails_before_modeling(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = self._write_inventory(
                Path(temp), empty=("injury_reports", 2013)
            )
            with self.assertRaisesRegex(
                ValueError, "injury_reports.*2013.*zero data rows"
            ):
                pgo_sources.validate_source_audit(paths)

    def test_team_aliases_normalize_before_identity_checks(self):
        identities = {"LV": "Raiders", "LAC": "Chargers"}

        joined = [identities[pgo_sources.normalize_team(team)] for team in ("OAK", "SD")]

        self.assertEqual(joined, ["Raiders", "Chargers"])
        with self.assertRaisesRegex(ValueError, "Unknown team abbreviation: XYZ"):
            pgo_sources.normalize_team("XYZ")

    @staticmethod
    def _write_inventory(directory, omit=None, empty=None):
        paths = {}
        for index, spec in enumerate(pgo_sources.source_specs()):
            columns = list(spec.required_columns)
            if (spec.name, spec.season) == omit:
                columns.remove("rushing_20")
            path = directory / f"{index}.csv"
            row = {column: "1" for column in columns}
            for column in ("team", "home_team"):
                if column in row:
                    row[column] = "LV"
            for column in ("opponent_team", "away_team"):
                if column in row:
                    row[column] = "LAC"
            with open(path, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                if (spec.name, spec.season) != empty:
                    writer.writerow(row)
            paths[(spec.name, spec.season)] = path
        return paths


class FeatureTests(unittest.TestCase):
    def test_full_locked_paths_cannot_leak_current_roster_into_history(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            paths = _synthetic_paths(directory)
            historical = pgo_challenger.build_snapshot_states(
                paths, "2013-09-08T14:00:00-04:00", 4
            )
            _add_current_roster(paths, directory)

            with_current_source = pgo_challenger.build_snapshot_states(
                paths, "2013-09-08T14:00:00-04:00", 4
            )

        self.assertEqual(historical, with_current_source)

    def test_january_as_of_rejects_later_week_eighteen_period(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            paths = _synthetic_paths(directory)
            before = pgo_challenger.build_snapshot_states(
                paths, "2024-01-01T00:00:00-05:00", 4
            )
            schedule_path = paths[("schedule_results", None)]
            with open(schedule_path, encoding="utf-8", newline="") as handle:
                schedule = list(csv.DictReader(handle))
            schedule.append({
                "game_id": "future-week-18", "season": 2023, "week": 18,
                "game_type": "REG", "gameday": "2024-01-07", "gametime": "13:00",
                "away_team": "OAK", "home_team": "SD", "away_score": 10,
                "home_score": 20, "location": "Home", "away_rest": 7,
                "home_rest": 7, "away_coach": "LV Coach", "home_coach": "LAC Coach",
            })
            _write_csv(schedule_path, pgo_sources.SCHEDULE_COLUMNS, schedule)
            roster_path = directory / "weekly-rosters-2023.csv"
            _write_csv(roster_path, pgo_sources.ROSTER_COLUMNS, [{
                "season": 2023, "week": 18, "team": "SD", "position": "QB",
                "gsis_id": "gsis-future-week-18", "pfr_id": "pfr-future-week-18",
                "years_exp": 9, "draft_number": 1,
            }])
            paths[("weekly_rosters", 2023)] = roster_path
            injury_path = directory / "injuries-2023.csv"
            _write_csv(injury_path, pgo_sources.INJURY_COLUMNS, [{
                "season": 2023, "week": 18, "team": "SD",
                "gsis_id": "gsis-future-week-18", "position": "QB",
                "report_status": "Out", "practice_status": "",
            }])
            paths[("injury_reports", 2023)] = injury_path

            with_future_period = pgo_challenger.build_snapshot_states(
                paths, "2024-01-01T00:00:00-05:00", 4
            )

        self.assertEqual(before, with_future_period)

    def test_current_roster_is_admissible_for_2026_offseason_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            paths = _synthetic_paths(directory)
            _add_current_roster(paths, directory)

            states = pgo_challenger.build_snapshot_states(
                paths, "2026-07-21T12:00:00-04:00", 4
            )

        self.assertAlmostEqual(
            states["LAC"][0]["qb_experience_prior"], math.log1p(9)
        )

    def test_missing_rate_still_ages_exponential_state(self):
        state = pgo_challenger._RatioState(10.0, 10.0)

        aged = state.update(None, 0.0, 0.5)
        updated = aged.update(0.0, 10.0, 0.5)

        self.assertEqual(aged, pgo_challenger._RatioState(5.0, 5.0))
        self.assertAlmostEqual(updated.value, 0.2)

    def test_equivalent_as_of_offsets_build_identical_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = _synthetic_paths(Path(temp))

            eastern = pgo_challenger.build_snapshot_states(
                paths, "2013-09-08T13:30:00-04:00", 4
            )
            mountain = pgo_challenger.build_snapshot_states(
                paths, "2013-09-08T11:30:00-06:00", 4
            )

        self.assertEqual(eastern, mountain)

    def test_injury_revision_after_kickoff_rejected_across_offsets(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = _synthetic_paths(Path(temp))
            injury_path = paths[("injury_reports", 2013)]
            _write_csv(
                injury_path,
                (*pgo_sources.INJURY_COLUMNS, "date_modified"),
                [{
                    "season": 2013, "week": 1, "team": "SD",
                    "gsis_id": "gsis-lac-qb", "position": "QB",
                    "report_status": "Questionable", "practice_status": "",
                    "date_modified": "2013-09-01T11:30:00-06:00",
                }],
            )

            with self.assertRaisesRegex(ValueError, "Injury revision after kickoff"):
                pgo_challenger.build_feature_rows(paths, 4)

    def test_snapshot_as_of_week_two_ignores_later_roster_and_injury(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = _synthetic_paths(Path(temp))
            roster_path = paths[("weekly_rosters", 2013)]
            with open(roster_path, encoding="utf-8", newline="") as handle:
                rosters = list(csv.DictReader(handle))
            rosters.append({
                "season": 2013,
                "week": 3,
                "team": "SD",
                "position": "QB",
                "gsis_id": "gsis-lac-qb",
                "pfr_id": "pfr-lac-qb",
                "years_exp": 3,
                "draft_number": 20,
            })
            _write_csv(roster_path, pgo_sources.ROSTER_COLUMNS, rosters)
            injury_path = paths[("injury_reports", 2013)]
            _write_csv(injury_path, pgo_sources.INJURY_COLUMNS, [{
                "season": 2013,
                "week": 3,
                "team": "SD",
                "gsis_id": "gsis-lac-qb",
                "position": "QB",
                "report_status": "Out",
                "practice_status": "Did Not Participate",
            }])

            states = pgo_challenger.build_snapshot_states(
                paths, "2013-09-08T14:00:00-04:00", 4
            )

        full, current = states["LAC"]
        self.assertEqual(full, current)

    def test_current_game_stats_cannot_change_its_own_features(self):
        with tempfile.TemporaryDirectory() as before_temp, tempfile.TemporaryDirectory() as after_temp:
            before = pgo_challenger.build_feature_rows(
                _synthetic_paths(Path(before_temp)), 4
            )
            after = pgo_challenger.build_feature_rows(
                _synthetic_paths(Path(after_temp), mutate_game="g1"), 4
            )

        self.assertEqual(_pregame_bytes(before[0]), _pregame_bytes(after[0]))
        self.assertNotEqual(before[0].actual_margin, after[0].actual_margin)

    def test_changed_qb_flag_uses_prior_completed_game_starter(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = _synthetic_paths(Path(temp))
            roster_path = paths[("weekly_rosters", 2013)]
            with open(roster_path, encoding="utf-8", newline="") as handle:
                rosters = list(csv.DictReader(handle))
            rosters.extend({
                "season": 2013,
                "week": week,
                "team": "SD",
                "position": "QB",
                "gsis_id": "gsis-a-modeled",
                "pfr_id": "pfr-a-modeled",
                "years_exp": 3,
                "draft_number": 1,
            } for week in (1, 2))
            _write_csv(roster_path, pgo_sources.ROSTER_COLUMNS, rosters)
            player_path = paths[("player_weekly_stats", 2013)]
            with open(player_path, encoding="utf-8", newline="") as handle:
                players = list(csv.DictReader(handle))
            players.append({
                "player_id": "gsis-a-modeled",
                "position": "QB",
                "season": 2013,
                "week": 1,
                "team": "SD",
                "attempts": 1,
                "passing_epa": -10,
                "passing_cpoe": -20,
                "sacks_suffered": 0,
                "passing_interceptions": 0,
                "sack_fumbles_lost": 0,
                "carries": 0,
                "rushing_epa": 0,
            })
            _write_csv(player_path, pgo_sources.PLAYER_COLUMNS, players)

            rows = pgo_challenger.build_feature_rows(paths, 4)

        self.assertFalse(rows[1].subgroup_flags["changed_or_backup_qb"])

    def test_current_game_stats_change_only_later_features(self):
        with tempfile.TemporaryDirectory() as before_temp, tempfile.TemporaryDirectory() as after_temp:
            before = pgo_challenger.build_feature_rows(
                _synthetic_paths(Path(before_temp)), 4
            )
            after = pgo_challenger.build_feature_rows(
                _synthetic_paths(Path(after_temp), mutate_game="g1"), 4
            )

        self.assertEqual(_pregame_bytes(before[0]), _pregame_bytes(after[0]))
        self.assertNotEqual(_pregame_bytes(before[1]), _pregame_bytes(after[1]))

    def test_relocated_teams_and_player_ids_join(self):
        with tempfile.TemporaryDirectory() as alias_temp, tempfile.TemporaryDirectory() as current_temp:
            aliased = pgo_challenger.build_feature_rows(
                _synthetic_paths(Path(alias_temp), aliases=True), 4
            )
            current = pgo_challenger.build_feature_rows(
                _synthetic_paths(Path(current_temp), aliases=False), 4
            )

        self.assertEqual(aliased, current)
        self.assertLess(aliased[1].features["qb_epa_per_dropback"], 0.0)
        self.assertGreater(aliased[2].features["incoming_prior_snap_share"], 0.0)

    def test_offseason_roster_and_head_coach_changes_are_pregame(self):
        with (
            tempfile.TemporaryDirectory() as changed_temp,
            tempfile.TemporaryDirectory() as stable_temp,
            tempfile.TemporaryDirectory() as result_temp,
        ):
            changed = pgo_challenger.build_feature_rows(
                _synthetic_paths(Path(changed_temp), offseason_change=True), 4
            )
            stable = pgo_challenger.build_feature_rows(
                _synthetic_paths(Path(stable_temp), offseason_change=False), 4
            )
            changed_result = pgo_challenger.build_feature_rows(
                _synthetic_paths(
                    Path(result_temp), offseason_change=True, mutate_game="g3"
                ),
                4,
            )

        self.assertNotEqual(
            changed[2].features["returning_offense_snap_share"],
            stable[2].features["returning_offense_snap_share"],
        )
        self.assertNotEqual(
            changed[2].features["head_coach_continuity"],
            stable[2].features["head_coach_continuity"],
        )
        self.assertEqual(_pregame_bytes(changed[2]), _pregame_bytes(changed_result[2]))

    def test_snap_window_advances_when_rostered_player_has_no_snap_row(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = _synthetic_paths(Path(temp))
            schedule_path = paths[("schedule_results", None)]
            with open(schedule_path, encoding="utf-8", newline="") as handle:
                schedule = list(csv.DictReader(handle))
            dates = ("2013-09-15", "2013-09-22", "2013-09-29", "2013-10-06")
            for week, day in zip(range(3, 7), dates):
                schedule.append({
                    "game_id": f"zero-{week}", "season": 2013, "week": week,
                    "game_type": "REG", "gameday": day, "gametime": "13:00",
                    "away_team": "SD", "home_team": "OAK", "away_score": 10,
                    "home_score": 20, "location": "Home", "away_rest": 7,
                    "home_rest": 7, "away_coach": "LAC Coach",
                    "home_coach": "LV Coach",
                })
            _write_csv(schedule_path, pgo_sources.SCHEDULE_COLUMNS, schedule)

            team_path = paths[("team_weekly_stats", 2013)]
            with open(team_path, encoding="utf-8", newline="") as handle:
                team_rows = list(csv.DictReader(handle))
            roster_path = paths[("weekly_rosters", 2013)]
            with open(roster_path, encoding="utf-8", newline="") as handle:
                rosters = list(csv.DictReader(handle))
            snap_path = paths[("snap_counts", 2013)]
            with open(snap_path, encoding="utf-8", newline="") as handle:
                snaps = list(csv.DictReader(handle))
            rosters.append({
                "season": 2013, "week": 1, "team": "OAK", "position": "WR",
                "gsis_id": "gsis-stale", "pfr_id": "pfr-stale",
                "years_exp": 2, "draft_number": 50,
            })
            snaps.append({
                "season": 2013, "week": 1, "team": "OAK",
                "pfr_player_id": "pfr-stale", "position": "WR",
                "offense_snaps": 50, "defense_snaps": 0,
            })
            for week in range(3, 7):
                for team, opponent in (("OAK", "SD"), ("SD", "OAK")):
                    team_rows.append({
                        "season": 2013, "week": week, "team": team,
                        "game_id": f"zero-{week}", "opponent_team": opponent,
                        "attempts": 20, "carries": 20, "passing_epa": 1,
                        "rushing_epa": 1, "sacks_suffered": 1,
                        "passing_interceptions": 0, "fumbles_lost_total": 0,
                        "passing_20": 1, "rushing_20": 1,
                    })
                    qb = "lv-old" if team == "OAK" else "lac-qb"
                    rosters.append({
                        "season": 2013, "week": week, "team": team,
                        "position": "QB", "gsis_id": f"gsis-{qb}",
                        "pfr_id": f"pfr-{qb}", "years_exp": 3,
                        "draft_number": 20,
                    })
                    snaps.append({
                        "season": 2013, "week": week, "team": team,
                        "pfr_player_id": f"pfr-{qb}", "position": "QB",
                        "offense_snaps": 50, "defense_snaps": 0,
                    })
                rosters.append({
                    "season": 2013, "week": week, "team": "OAK",
                    "position": "WR", "gsis_id": "gsis-stale",
                    "pfr_id": "pfr-stale", "years_exp": 2,
                    "draft_number": 50,
                })
            _write_csv(team_path, pgo_sources.TEAM_COLUMNS, team_rows)
            _write_csv(roster_path, pgo_sources.ROSTER_COLUMNS, rosters)
            _write_csv(snap_path, pgo_sources.SNAP_COLUMNS, snaps)
            injury_path = paths[("injury_reports", 2013)]
            _write_csv(injury_path, pgo_sources.INJURY_COLUMNS, [{
                "season": 2013, "week": 6, "team": "OAK",
                "gsis_id": "gsis-stale", "position": "WR",
                "report_status": "Out", "practice_status": "",
            }])

            states = pgo_challenger.build_snapshot_states(
                paths, "2013-10-06T14:00:00-04:00", 4
            )

        self.assertEqual(states["LV"][1]["offense_availability"], 0.0)


class ModelTests(unittest.TestCase):
    def test_imputation_and_scaling_use_training_rows_only(self):
        training = [
            pgo_challenger.FeatureRow(
                "one", 2013, 1, "2013-09-01T13:00-04:00", 0.0,
                {"signal": 1.0, "constant": 5.0}, {},
            ),
            pgo_challenger.FeatureRow(
                "two", 2014, 1, "2014-09-01T13:00-04:00", 0.0,
                {"signal": None, "constant": 5.0}, {},
            ),
            pgo_challenger.FeatureRow(
                "three", 2015, 1, "2015-09-01T13:00-04:00", 0.0,
                {"signal": 3.0, "constant": 5.0}, {},
            ),
        ]
        before = training + [
            pgo_challenger.FeatureRow(
                "future", 2020, 1, "2020-09-01T13:00-04:00", 0.0,
                {"signal": 10.0, "constant": 5.0}, {},
            )
        ]
        after = training + [
            pgo_challenger.FeatureRow(
                "future", 2020, 1, "2020-09-01T13:00-04:00", 0.0,
                {"signal": 1_000_000.0, "constant": -1_000_000.0}, {},
            )
        ]

        first = pgo_challenger.fit_preprocessor(
            [row for row in before if row.season < 2020],
            ("signal", "constant"),
        )
        second = pgo_challenger.fit_preprocessor(
            [row for row in after if row.season < 2020],
            ("signal", "constant"),
        )

        np.testing.assert_array_equal(first.medians, second.medians)
        np.testing.assert_array_equal(first.scales, second.scales)
        np.testing.assert_allclose(first.medians, [2.0, 5.0])
        np.testing.assert_allclose(first.scales, [np.sqrt(2.0 / 3.0), 1.0])
        self.assertEqual(first.missing_features, ("signal",))
        transformed = first.transform(training)
        self.assertEqual(transformed.shape, (3, 3))
        np.testing.assert_array_equal(transformed[:, -1], [0.0, 1.0, 0.0])

    def test_future_rows_cannot_change_selected_parameters(self):
        history = [
            _model_row(f"{season}-{index}", season, signal, 2.0 + 3.0 * signal)
            for season in range(2013, 2018)
            for index, signal in enumerate((-2.0, -1.0, 0.0, 1.0, 2.0))
        ]
        before = history + [_model_row("future", 2018, 50.0, 152.0)]
        after = history + [_model_row("future", 2018, 50.0, -1_000_000.0)]

        with patch.object(pgo_challenger, "build_feature_rows", return_value=before):
            first = pgo_challenger.select_parameters({}, (2016, 2017))
        with patch.object(pgo_challenger, "build_feature_rows", return_value=after):
            second = pgo_challenger.select_parameters({}, (2016, 2017))

        self.assertEqual(first, second)

    def test_unnamed_future_schema_cannot_change_selection(self):
        history = [
            _model_row(f"{season}-{index}", season, signal, 2.0 + 3.0 * signal)
            for season in range(2013, 2018)
            for index, signal in enumerate((-1.0, 0.0, 1.0))
        ]
        future = replace(
            _model_row("future", 2018, 0.0, 0.0),
            features={"signal": 0.0, "future_only": 1.0},
        )

        with patch.object(pgo_challenger, "build_feature_rows", return_value=history):
            expected = pgo_challenger.select_parameters({}, (2016, 2017))
        with patch.object(
            pgo_challenger, "build_feature_rows", return_value=history + [future]
        ):
            actual = pgo_challenger.select_parameters({}, (2016, 2017))

        self.assertEqual(actual, expected)
        named_mismatch = [
            replace(history[0], features={"signal": -1.0, "extra": 1.0}),
            *history[1:],
        ]
        with (
            patch.object(
                pgo_challenger,
                "build_feature_rows",
                return_value=named_mismatch,
            ),
            self.assertRaisesRegex(ValueError, "Feature row shapes do not align"),
        ):
            pgo_challenger.select_parameters({}, (2016, 2017))

    def test_ridge_does_not_penalize_intercept(self):
        x = np.arange(-4.0, 5.0).reshape(-1, 1)
        y = 2.0 + 3.0 * x[:, 0]

        coefficients = pgo_challenger.fit_huber_ridge(
            x, y, alpha=1_000_000.0, delta=1.0
        )

        self.assertAlmostEqual(coefficients[0], 2.0)

    def test_huber_fit_downweights_one_large_outlier(self):
        x = np.arange(11.0).reshape(-1, 1)
        y = 2.0 + 3.0 * x[:, 0]
        y[-1] = 200.0
        ordinary_slope = np.linalg.lstsq(
            np.column_stack((np.ones(len(x)), x)), y, rcond=None
        )[0][1]

        robust_slope = pgo_challenger.fit_huber_ridge(
            x, y, alpha=1e-9, delta=1.0
        )[1]

        self.assertLess(abs(robust_slope - 3.0), abs(ordinary_slope - 3.0))

    def test_invalid_model_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            pgo_challenger.fit_preprocessor([], ("signal",))
        with self.assertRaises(ValueError):
            pgo_challenger.fit_huber_ridge(
                np.ones((2, 1)), np.ones(3), alpha=1.0, delta=1.0
            )
        with self.assertRaises(ValueError):
            pgo_challenger.fit_huber_ridge(
                np.ones((2, 1)), np.ones(2), alpha=0.0, delta=1.0
            )
        with self.assertRaises(ValueError):
            pgo_challenger.predict(np.ones((2, 1)), np.ones(3))
        rows = [
            _model_row(str(season), season, float(season - 2013), 1.0)
            for season in range(2013, 2016)
        ] + [_model_row("validation", 2016, 3.0, float("nan"))]
        with (
            patch.object(pgo_challenger, "build_feature_rows", return_value=rows),
            self.assertRaisesRegex(ValueError, "finite"),
        ):
            pgo_challenger.select_parameters({}, (2016,))

    def test_nonfinite_prediction_errors_are_rejected(self):
        rows = [
            _model_row(str(season), season, signal, -1e307)
            for season, signal in zip(range(2013, 2016), (-1.0, 0.0, 1.0))
        ] + [_model_row("validation", 2016, 0.0, np.finfo(float).max)]

        with (
            patch.object(pgo_challenger, "build_feature_rows", return_value=rows),
            self.assertRaisesRegex(ValueError, "Prediction errors must be finite"),
        ):
            pgo_challenger.select_parameters({}, (2016,))


class EvaluationTests(unittest.TestCase):
    @staticmethod
    def _fold_rows():
        rows, metadata = [], {}
        for season in range(2013, 2026):
            game_id = f"game-{season}"
            signal = float(season - 2013)
            features = {"signal": signal}
            rows.append(pgo_challenger.FeatureRow(
                game_id, season, 1, f"{season}-09-01T13:00:00-04:00",
                3.0 + signal, features,
                {
                    "changed_or_backup_qb": False,
                    "head_coach_change": False,
                    "weeks_1_4": True,
                    "weeks_5_18": False,
                },
            ))
            metadata[game_id] = {
                "home_full_features": {
                    "signal": signal + (10.0 if season == 2018 else 0.0)
                },
                "away_full_features": dict(features),
                "home_team": "LV",
                "away_team": "LAC",
                "home_returning_snap_share": 0.4,
                "away_returning_snap_share": 0.6,
            }
        return rows, metadata

    @staticmethod
    def _schedule_path(directory, rows):
        path = directory / "schedule.csv"
        _write_csv(path, pgo_sources.SCHEDULE_COLUMNS, [
            {
                "game_id": row.game_id,
                "season": row.season,
                "week": row.week,
                "game_type": "REG",
                "gameday": f"{row.season}-09-01",
                "gametime": "13:00",
                "away_team": "LAC",
                "home_team": "LV",
                "away_score": 20,
                "home_score": 20 + row.actual_margin,
                "location": "Home",
                "away_rest": 7,
                "home_rest": 7,
                "away_coach": "Away Coach",
                "home_coach": "Home Coach",
            }
            for row in rows
        ])
        return path

    @staticmethod
    def _passing_evaluation():
        subgroups = {
            name: {"status": "INSUFFICIENT_EVIDENCE", "count": 99}
            for name in pgo_challenger.SUBGROUPS
        }
        subgroups["changed_or_backup_qb"] = {
            "status": "SUFFICIENT_EVIDENCE",
            "count": 100,
            "pgo_v0_mae": 10.0,
            "challenger_mae": 9.0,
            "improvement": 1.0,
            "lower": -0.10,
            "upper": 0.20,
        }
        return {
            "paired_game_ids": True,
            "pgo_v0": {"count": 100, "mae": 9.25},
            "challenger": {"count": 100, "mae": 9.0},
            "improvement": {
                "mean": 0.25,
                "lower": 0.10,
                "upper": 0.40,
                "samples": 10_000,
                "seed": 20260721,
            },
            "subgroups": subgroups,
        }

    @staticmethod
    def _turnover_paths(directory, mutate_postgame_snaps=False):
        paths = _synthetic_paths(directory)
        roster_path = paths[("weekly_rosters", 2013)]
        snap_path = paths[("snap_counts", 2013)]
        with open(roster_path, encoding="utf-8", newline="") as handle:
            rosters = list(csv.DictReader(handle))
        with open(snap_path, encoding="utf-8", newline="") as handle:
            snaps = list(csv.DictReader(handle))
        for team, player in (("OAK", "lv-wr"), ("SD", "incoming-wr")):
            rosters.append({
                "season": 2013, "week": 1, "team": team, "position": "WR",
                "gsis_id": f"gsis-{player}", "pfr_id": f"pfr-{player}",
                "years_exp": 2, "draft_number": 100,
            })
            snaps.append({
                "season": 2013, "week": 1, "team": team,
                "pfr_player_id": f"pfr-{player}", "position": "WR",
                "offense_snaps": 50, "defense_snaps": 0,
            })
        _write_csv(roster_path, pgo_sources.ROSTER_COLUMNS, rosters)
        _write_csv(snap_path, pgo_sources.SNAP_COLUMNS, snaps)

        roster_path = paths[("weekly_rosters", 2014)]
        snap_path = paths[("snap_counts", 2014)]
        with open(roster_path, encoding="utf-8", newline="") as handle:
            rosters = list(csv.DictReader(handle))
        with open(snap_path, encoding="utf-8", newline="") as handle:
            snaps = list(csv.DictReader(handle))
        for week, player in ((1, "lv-wr"), (2, "lv-wr"), (2, "incoming-wr")):
            rosters.append({
                "season": 2014, "week": week, "team": "OAK", "position": "WR",
                "gsis_id": f"gsis-{player}", "pfr_id": f"pfr-{player}",
                "years_exp": 3, "draft_number": 100,
            })
        snaps.append({
            "season": 2014, "week": 1, "team": "OAK",
            "pfr_player_id": "pfr-lv-wr", "position": "WR",
            "offense_snaps": 50, "defense_snaps": 0,
        })
        if mutate_postgame_snaps:
            next(
                row for row in snaps
                if row["week"] == "1" and row["team"] == "OAK"
                and row["pfr_player_id"] == "pfr-lac-qb"
            )["offense_snaps"] = 99
        _write_csv(roster_path, pgo_sources.ROSTER_COLUMNS, rosters)
        _write_csv(snap_path, pgo_sources.SNAP_COLUMNS, snaps)
        return paths

    def test_outer_fold_never_trains_on_same_or_later_season(self):
        rows, metadata = self._fold_rows()
        selected_for, trained_on = [], []
        original_fit = pgo_challenger.fit_preprocessor

        def select(_paths, seasons):
            selected_for.append(tuple(seasons))
            return pgo_challenger.ChallengerParameters(4, 1.0, 1.0)

        def capture_fit(training, names):
            trained_on.append(tuple(row.season for row in training))
            return original_fit(training, names)

        with tempfile.TemporaryDirectory() as temp:
            paths = {
                ("schedule_results", None): self._schedule_path(Path(temp), rows)
            }
            with (
                patch.object(pgo_challenger, "select_parameters", side_effect=select),
                patch.object(
                    pgo_challenger,
                    "_walk",
                    return_value=(rows, {"evaluation_metadata": metadata}, {}),
                ),
                patch.object(
                    pgo_challenger, "fit_preprocessor", side_effect=capture_fit
                ),
            ):
                predictions, _ = pgo_challenger.rolling_predictions(paths)

        self.assertEqual(
            selected_for,
            [tuple(range(2016, season)) for season in range(2018, 2026)],
        )
        self.assertEqual(len(trained_on), 8)
        for outer_season, training_seasons in zip(range(2018, 2026), trained_on):
            self.assertTrue(training_seasons)
            self.assertLess(max(training_seasons), outer_season)
        self.assertEqual(
            [row["season"] for row in predictions], list(range(2018, 2026))
        )
        self.assertTrue(predictions[0]["major_availability_loss"])
        self.assertTrue(all(row["high_roster_turnover"] for row in predictions))

    def test_challenger_and_v0_require_identical_game_ids(self):
        rows, metadata = self._fold_rows()
        incumbent = [
            pgo_model.Prediction(
                row.game_id, row.season, row.actual_margin, row.actual_margin
            )
            for row in rows
            if 2018 <= row.season <= 2024
        ]
        with (
            patch.object(
                pgo_challenger,
                "select_parameters",
                return_value=pgo_challenger.ChallengerParameters(4, 1.0, 1.0),
            ),
            patch.object(
                pgo_challenger,
                "_walk",
                return_value=(rows, {"evaluation_metadata": metadata}, {}),
            ),
            patch.object(
                pgo_challenger, "_incumbent_predictions", return_value=incumbent
            ),
            self.assertRaisesRegex(ValueError, "game-2025"),
        ):
            pgo_challenger.rolling_predictions({})

    def test_metric_summary_reports_required_secondary_metrics(self):
        rows = [
            {
                "game_id": "a", "season": 2018, "week": 1,
                "actual_margin": 10.0, "challenger_prediction": 8.0,
            },
            {
                "game_id": "b", "season": 2018, "week": 2,
                "actual_margin": -5.0, "challenger_prediction": -10.0,
            },
            {
                "game_id": "c", "season": 2019, "week": 1,
                "actual_margin": 0.0, "challenger_prediction": 20.0,
            },
        ]

        summary = pgo_challenger.metric_summary(rows, "challenger_prediction")

        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["mae"], 9.0)
        self.assertEqual(summary["median_absolute_error"], 5.0)
        self.assertAlmostEqual(summary["rmse"], math.sqrt(143.0))
        self.assertAlmostEqual(summary["miss_rate_above_14"], 1.0 / 3.0)
        self.assertEqual(summary["miss_rate_above_21"], 0.0)
        self.assertAlmostEqual(summary["mean_signed_error_home"], -13.0 / 3.0)
        self.assertAlmostEqual(summary["mean_signed_error_away"], 13.0 / 3.0)
        self.assertEqual(
            [season["season"] for season in summary["seasons"]], [2018, 2019]
        )
        self.assertEqual(
            [band["band"] for band in summary["calibration_bands"]],
            ["<-7", "-7:-3", "-3:3", "3:7", ">7"],
        )

    def test_paired_block_bootstrap_is_seeded_and_week_blocked(self):
        rows = [
            {
                "game_id": "a", "season": 2018, "week": 1,
                "actual_margin": 0.0, "pgo_v0_prediction": 1.0,
                "challenger_prediction": 0.0,
            },
            {
                "game_id": "b", "season": 2018, "week": 1,
                "actual_margin": 0.0, "pgo_v0_prediction": 3.0,
                "challenger_prediction": 0.0,
            },
            {
                "game_id": "c", "season": 2018, "week": 2,
                "actual_margin": 0.0, "pgo_v0_prediction": 10.0,
                "challenger_prediction": 0.0,
            },
        ]
        samples, seed = 20, 7
        draws = np.random.default_rng(seed).integers(0, 2, size=(samples, 2))
        blocks = (np.array([1.0, 3.0]), np.array([10.0]))
        expected = np.array([
            np.concatenate([blocks[index] for index in draw]).mean()
            for draw in draws
        ])

        first = pgo_challenger.paired_block_bootstrap(rows, samples, seed)
        second = pgo_challenger.paired_block_bootstrap(rows, samples, seed)

        self.assertEqual(first, second)
        self.assertEqual(first["samples"], samples)
        self.assertEqual(first["seed"], seed)
        self.assertAlmostEqual(first["mean"], 14.0 / 3.0)
        self.assertAlmostEqual(first["lower"], np.percentile(expected, 2.5))
        self.assertAlmostEqual(first["upper"], np.percentile(expected, 97.5))

    def test_subgroups_freeze_before_scoring_and_require_100_games(self):
        def row(index):
            return {
                "game_id": str(index), "season": 2018, "week": index + 1,
                "actual_margin": 0.0, "pgo_v0_prediction": 2.0,
                "challenger_prediction": 1.0,
                "changed_or_backup_qb": True,
                "major_availability_loss": False,
                "head_coach_change": False,
                "high_roster_turnover": False,
                "weeks_1_4": False,
                "weeks_5_18": False,
            }

        rows = [row(index) for index in range(99)]
        insufficient = pgo_challenger.subgroup_results(rows)
        self.assertEqual(
            insufficient["changed_or_backup_qb"]["status"],
            "INSUFFICIENT_EVIDENCE",
        )

        rows.append(row(99))
        sufficient = pgo_challenger.subgroup_results(rows)
        mutated = [dict(value, challenger_prediction=1000.0) for value in rows]
        rescored = pgo_challenger.subgroup_results(mutated)

        self.assertEqual(sufficient["changed_or_backup_qb"]["count"], 100)
        self.assertEqual(
            sufficient["changed_or_backup_qb"]["status"], "SUFFICIENT_EVIDENCE"
        )
        self.assertEqual(
            rescored["changed_or_backup_qb"]["count"],
            sufficient["changed_or_backup_qb"]["count"],
        )

    def test_turnover_freezes_each_team_at_its_earliest_pregame_share(self):
        with (
            tempfile.TemporaryDirectory() as before_temp,
            tempfile.TemporaryDirectory() as after_temp,
        ):
            before_rows, before_context, _ = pgo_challenger._walk(
                self._turnover_paths(Path(before_temp)), 4
            )
            after_rows, after_context, _ = pgo_challenger._walk(
                self._turnover_paths(Path(after_temp), True), 4
            )

        before_rows = [row for row in before_rows if row.season == 2014]
        after_rows = [row for row in after_rows if row.season == 2014]
        before_metadata = before_context["evaluation_metadata"]
        after_metadata = after_context["evaluation_metadata"]
        self.assertEqual(
            before_metadata["g3"]["home_returning_snap_share"],
            after_metadata["g3"]["home_returning_snap_share"],
        )
        self.assertNotEqual(
            before_metadata["g4"]["away_returning_snap_share"],
            after_metadata["g4"]["away_returning_snap_share"],
        )

        before_flags, before_quartile = pgo_challenger._frozen_turnover_flags(
            before_rows, before_metadata
        )
        after_flags, after_quartile = pgo_challenger._frozen_turnover_flags(
            after_rows, after_metadata
        )

        self.assertEqual(before_quartile, after_quartile)
        self.assertEqual(before_flags, after_flags)
        self.assertTrue(before_flags["g3"])
        self.assertTrue(before_flags["g4"])

    def test_gate_requires_complete_audit_categories(self):
        evaluation = self._passing_evaluation()
        full_audit = {
            "source": True,
            "identity": True,
            "leakage": True,
            "reproducibility": True,
        }
        missing_reproducibility = dict(full_audit)
        missing_reproducibility.pop("reproducibility")

        self.assertFalse(
            pgo_challenger.gate_checks(
                {"source": True}, evaluation, 32, True
            )["audit_checks_pass"]
        )
        self.assertFalse(
            pgo_challenger.gate_checks(
                missing_reproducibility, evaluation, 32, True
            )["audit_checks_pass"]
        )

    def test_gate_rejects_inconsistent_subgroup_evidence(self):
        audit = {
            "source": True,
            "identity": True,
            "leakage": True,
            "reproducibility": True,
        }
        valid = self._passing_evaluation()
        sufficient = valid["subgroups"]["changed_or_backup_qb"]
        invalid = [
            {"status": "INSUFFICIENT_EVIDENCE", "count": 100},
            dict(sufficient, count=99),
            dict(sufficient, improvement=2.0),
            dict(sufficient, lower=0.30, upper=0.20),
        ]
        for name in (
            "pgo_v0_mae", "challenger_mae", "improvement", "lower", "upper"
        ):
            missing = dict(sufficient)
            missing.pop(name)
            invalid.append(missing)
            invalid.append(dict(sufficient, **{name: float("nan")}))

        for evidence in invalid:
            with self.subTest(evidence=evidence):
                evaluation = dict(valid)
                evaluation["subgroups"] = dict(valid["subgroups"])
                evaluation["subgroups"]["changed_or_backup_qb"] = evidence
                self.assertFalse(
                    pgo_challenger.gate_checks(
                        audit, evaluation, 32, True
                    )["no_sufficient_subgroup_regression"]
                )

    def test_gate_rejects_invalid_aggregate_counts_and_maes(self):
        audit = {
            "source": True,
            "identity": True,
            "leakage": True,
            "reproducibility": True,
        }
        valid = self._passing_evaluation()
        invalid = []
        for side in ("pgo_v0", "challenger"):
            missing = dict(valid[side])
            missing.pop("count")
            invalid.append((f"missing {side} count", side, missing))
        invalid.extend((
            ("unequal counts", "pgo_v0", {"count": 99, "mae": 9.25}),
            ("zero count", "pgo_v0", {"count": 0, "mae": 9.25}),
            ("negative count", "pgo_v0", {"count": -1, "mae": 9.25}),
        ))
        for side in ("pgo_v0", "challenger"):
            for value in (-1.0, float("nan"), float("inf")):
                invalid.append((
                    f"invalid {side} mae {value}",
                    side,
                    {"count": 100, "mae": value},
                ))

        for label, side, evidence in invalid:
            with self.subTest(label=label):
                evaluation = dict(valid)
                evaluation[side] = evidence
                self.assertFalse(
                    pgo_challenger.gate_checks(
                        audit, evaluation, 32, True
                    )["challenger_mae_lower"]
                )

    def test_gate_rejects_invalid_aggregate_bootstrap_evidence(self):
        audit = {
            "source": True,
            "identity": True,
            "leakage": True,
            "reproducibility": True,
        }
        valid = self._passing_evaluation()
        interval = valid["improvement"]
        invalid = []
        for name in ("mean", "lower", "upper", "samples", "seed"):
            missing = dict(interval)
            missing.pop(name)
            invalid.append((f"missing {name}", missing))
        for name in ("mean", "lower", "upper"):
            for value in (float("nan"), float("inf")):
                invalid.append((
                    f"nonfinite {name} {value}",
                    dict(interval, **{name: value}),
                ))
        invalid.extend((
            ("lower above mean", dict(interval, lower=0.30, mean=0.20)),
            ("mean above upper", dict(interval, mean=0.50, upper=0.40)),
            ("wrong samples", dict(interval, samples=9_999)),
            ("wrong seed", dict(interval, seed=1)),
        ))

        for label, evidence in invalid:
            with self.subTest(label=label):
                evaluation = dict(valid)
                evaluation["improvement"] = evidence
                self.assertFalse(
                    pgo_challenger.gate_checks(
                        audit, evaluation, 32, True
                    )["aggregate_improvement_ci_positive"]
                )

    def test_gate_uses_improvement_ci_direction_correctly(self):
        audit = {
            "source": True,
            "identity": True,
            "leakage": True,
            "reproducibility": True,
        }
        evaluation = self._passing_evaluation()

        positive = pgo_challenger.gate_checks(audit, evaluation, 32, True)
        self.assertTrue(all(positive.values()))

        incomplete = dict(evaluation)
        incomplete["subgroups"] = dict(evaluation["subgroups"])
        incomplete["subgroups"].pop("high_roster_turnover")
        self.assertFalse(
            pgo_challenger.gate_checks(audit, incomplete, 32, True)[
                "no_sufficient_subgroup_regression"
            ]
        )

        negative = dict(evaluation)
        negative["improvement"] = {
            "mean": -0.25, "lower": -0.40, "upper": -0.10,
            "samples": 10_000, "seed": 20260721,
        }
        self.assertFalse(
            pgo_challenger.gate_checks(audit, negative, 32, True)[
                "aggregate_improvement_ci_positive"
            ]
        )

        subgroup_loss = dict(evaluation)
        subgroup_loss["subgroups"] = dict(evaluation["subgroups"])
        subgroup_loss["subgroups"]["changed_or_backup_qb"] = {
            "status": "SUFFICIENT_EVIDENCE",
            "count": 100,
            "pgo_v0_mae": 10.0,
            "challenger_mae": 9.0,
            "improvement": 1.0,
            "lower": -0.40,
            "upper": -0.10,
        }
        self.assertFalse(
            pgo_challenger.gate_checks(audit, subgroup_loss, 32, True)[
                "no_sufficient_subgroup_regression"
            ]
        )


class LineupTests(unittest.TestCase):
    @staticmethod
    def _snapshot(starter_probability=1.0, replacement_value=0.4):
        return {
            "LV": {
                "starter": {
                    "position": "QB",
                    "qb_value": 1.0,
                    "offense_snap_share": 0.8,
                    "defense_snap_share": 0.0,
                    "probability": starter_probability,
                },
                "strong-backup": {
                    "position": "QB",
                    "qb_value": replacement_value,
                    "offense_snap_share": 0.1,
                    "defense_snap_share": 0.0,
                    "probability": 1.0,
                },
                "weak-backup": {
                    "position": "QB",
                    "qb_value": -0.2,
                    "offense_snap_share": 0.0,
                    "defense_snap_share": 0.0,
                    "probability": 1.0,
                },
            }
        }

    def test_active_player_has_zero_availability_adjustment(self):
        full, current = pgo_challenger.lineup_views(
            "OAK", self._snapshot(), {"pgo_v0": 2.0}
        )

        self.assertEqual(full, current)
        self.assertEqual(current["qb_current_minus_full"], 0.0)
        self.assertEqual(current["offense_availability"], 0.0)

    def test_doubtful_backup_consumes_only_its_probability_mass(self):
        snapshot = {
            "LV": {
                "starter": {
                    "position": "QB", "qb_value": 1.0, "probability": 0.0,
                    "offense_snap_share": 0.8, "defense_snap_share": 0.0,
                },
                "doubtful-backup": {
                    "position": "QB", "qb_value": 0.8, "probability": 0.25,
                    "offense_snap_share": 0.1, "defense_snap_share": 0.0,
                },
                "healthy-backup": {
                    "position": "QB", "qb_value": 0.2, "probability": 1.0,
                    "offense_snap_share": 0.1, "defense_snap_share": 0.0,
                },
            }
        }

        _, current = pgo_challenger.lineup_views("LV", snapshot, {})

        self.assertAlmostEqual(current["qb_epa_per_dropback"], 0.35)
        self.assertAlmostEqual(current["qb_current_minus_full"], -0.65)

    def test_missing_replacement_probability_mass_stays_missing(self):
        snapshot = {
            "LV": {
                "starter": {
                    "position": "QB", "qb_value": 1.0, "probability": 0.0,
                    "offense_snap_share": 1.0, "defense_snap_share": 0.0,
                }
            }
        }

        _, current = pgo_challenger.lineup_views("LV", snapshot, {})

        self.assertIsNone(current["qb_epa_per_dropback"])
        self.assertIsNone(current["qb_current_minus_full"])

    def test_out_qb_uses_replacement_quality(self):
        full, current = pgo_challenger.lineup_views(
            "LV", self._snapshot(starter_probability=0.0), {}
        )
        _, weaker = pgo_challenger.lineup_views(
            "LV",
            self._snapshot(starter_probability=0.0, replacement_value=0.1),
            {},
        )

        self.assertEqual(full["qb_epa_per_dropback"], 1.0)
        self.assertEqual(current["qb_epa_per_dropback"], 0.4)
        self.assertEqual(current["qb_current_minus_full"], -0.6)
        self.assertGreater(
            current["qb_current_minus_full"],
            weaker["qb_current_minus_full"],
        )

    def test_questionable_and_limited_players_are_probability_weighted(self):
        self.assertEqual(pgo_challenger.availability_probability("Out", ""), 0.0)
        self.assertEqual(pgo_challenger.availability_probability("Doubtful", ""), 0.25)
        self.assertEqual(pgo_challenger.availability_probability("Questionable", ""), 0.70)
        self.assertEqual(
            pgo_challenger.availability_probability("", "Did Not Participate"),
            0.70,
        )
        self.assertEqual(
            pgo_challenger.availability_probability("", "Limited Participation"),
            0.90,
        )
        self.assertEqual(
            pgo_challenger.availability_probability("", "Full Participation"),
            1.0,
        )
        with self.assertRaisesRegex(ValueError, "Unknown injury report status"):
            pgo_challenger.availability_probability("Probable", "")

        snapshot = {
            "LV": {
                "questionable": {
                    "position": "WR",
                    "offense_snap_share": 0.5,
                    "defense_snap_share": 0.0,
                    "probability": 0.70,
                },
                "limited": {
                    "position": "LB",
                    "offense_snap_share": 0.0,
                    "defense_snap_share": 0.4,
                    "probability": 0.90,
                },
            }
        }
        _, current = pgo_challenger.lineup_views("LV", snapshot, {})

        self.assertAlmostEqual(current["offense_availability"], -0.15)
        self.assertAlmostEqual(current["defense_availability"], -0.04)

    def test_full_plus_adjustment_equals_current_before_and_after_centering(self):
        full, current = pgo_challenger.lineup_views(
            "LV", self._snapshot(starter_probability=0.25), {"pgo_v0": 2.0}
        )
        coefficients = {
            name: index / 10
            for index, (name, value) in enumerate(full.items(), 1)
            if value is not None and current[name] is not None
        }
        full_rating = sum(coefficients[name] * full[name] for name in coefficients)
        current_rating = sum(
            coefficients[name] * current[name] for name in coefficients
        )
        adjustment = sum(
            coefficients[name] * (current[name] - full[name])
            for name in coefficients
        )

        self.assertTrue(math.isclose(full_rating + adjustment, current_rating, abs_tol=1e-9))
        center = 1.234
        self.assertTrue(
            math.isclose(
                (full_rating - center) + adjustment,
                current_rating - center,
                abs_tol=1e-9,
            )
        )
