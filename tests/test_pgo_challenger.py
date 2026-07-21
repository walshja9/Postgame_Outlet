import csv
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pgo_sources


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
