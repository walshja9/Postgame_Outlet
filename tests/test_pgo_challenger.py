import csv
import gzip
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

import pgo_challenger
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
