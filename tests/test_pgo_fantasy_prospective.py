import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pgo_fantasy
import pgo_fantasy_prospective as prospective


class ProspectiveFantasyFixture:
    CAPTURED = "2026-09-09T18:50:00-04:00"
    KICKOFF = "2026-09-09T20:20:00-04:00"
    LOCKED_AT = "2026-09-09T19:20:00-04:00"

    @staticmethod
    def scoring(**values):
        return {
            field: values.get(field, 0.0)
            for field in pgo_fantasy.SCORING_FIELDS
        }

    def envelope(self, rows, teams=("BUF", "LAR"), captured=None):
        return {
            "schema_version": 1,
            "source": "synthetic-official-source",
            "source_as_of": captured or self.CAPTURED,
            "captured_at": captured or self.CAPTURED,
            "teams_processed": list(teams),
            "rows": rows,
        }

    def config(self):
        return {
            "schema_version": 1,
            "model_version": "pgo_fantasy_2026_baseline_v1",
            "frozen_at": "2026-09-01T12:00:00-04:00",
            "trained_through": 2025,
            "scoring": "PGO_HALF_PPR_V1",
            "history_games": 8,
            "half_life_games": 4,
            "pseudo_games": 4,
            "position_mean_evidence_sha256": "d" * 64,
            "position_means": {
                "QB": 15.0, "RB": 8.0, "WR": 7.0, "TE": 5.0,
            },
        }

    def source_values(self, *, availability=True, history_rows=None):
        game_id = "2026_01_BUF_LAR"
        schedule = self.envelope([{
            "season": 2026, "week": 1, "game_id": game_id,
            "game_type": "REG", "kickoff": self.KICKOFF,
            "away_team": "BUF", "home_team": "LAR",
        }])
        roster = self.envelope([
            {"gsis_id": "veteran", "player_name": "Veteran",
             "team": "BUF", "position": "WR", "status": "ACT"},
            {"gsis_id": "rookie", "player_name": "Rookie",
             "team": "LAR", "position": "WR", "status": "ACT"},
            {"gsis_id": "inactive", "player_name": "Inactive",
             "team": "BUF", "position": "RB", "status": "ACT"},
        ])
        inactive = self.envelope([
            {"gsis_id": "inactive", "team": "BUF", "status": "INACTIVE"},
        ])
        default_history = [{
            "season": 2025, "week": 18, "game_id": "2025_18_BUF_NYJ",
            "game_type": "REG", "finalized_at": "2026-01-04T19:00:00-05:00",
            "gsis_id": "veteran", "team": "BUF", "position": "WR",
            **self.scoring(receiving_yards=100.0),
        }]
        values = {
            "schedule": schedule,
            "roster": roster,
            "history": self.envelope(
                default_history if history_rows is None else history_rows
            ),
        }
        if availability:
            values["availability"] = inactive
        return values, game_id

    def loaded_sources(self, directory, *, availability=True, history_rows=None):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        values, game_id = self.source_values(
            availability=availability, history_rows=history_rows
        )
        loaded = {}
        for kind, value in values.items():
            path = self.write_json(root / f"{kind}.json", value)
            loaded[kind] = prospective.load_snapshot(path, kind)
        config_path = self.write_json(
            root / "config.json", self.config(), canonical=True
        )
        return loaded, prospective.load_model_config(config_path), game_id

    def command_fixture(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        values, game_id = self.source_values()
        paths = {"root": root, "game_id": game_id}
        for kind, value in values.items():
            paths[kind] = self.write_json(root / f"{kind}.json", value)
        paths["config"] = self.write_json(
            root / "config.json", self.config(), canonical=True
        )
        return paths

    @staticmethod
    def write_json(path, value, *, canonical=False):
        text = (
            prospective.canonical_json(value) + "\n"
            if canonical
            else json.dumps(value, ensure_ascii=False) + "\n"
        )
        Path(path).write_text(text, encoding="utf-8", newline="")
        return Path(path)


class ProspectiveSourceBoundaryTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def test_snapshot_reads_one_byte_sequence_and_receipts_exact_bytes(self):
        rows = [{
            "season": 2026, "week": 1, "game_id": "2026_01_BUF_LAR",
            "game_type": "REG", "kickoff": self.KICKOFF,
            "away_team": "BUF", "home_team": "LAR",
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(
                Path(directory) / "schedule.json", self.envelope(rows)
            )
            expected = path.read_bytes()
            original = Path.read_bytes
            reads = []

            def counted(target):
                reads.append(Path(target))
                return original(target)

            with patch.object(Path, "read_bytes", counted):
                loaded = prospective.load_snapshot(path, "schedule")

        self.assertEqual(reads, [path])
        self.assertEqual(loaded["snapshot"]["rows"], rows)
        self.assertEqual(loaded["receipt"]["bytes"], len(expected))
        self.assertEqual(loaded["bytes"], expected)
        self.assertEqual(
            loaded["receipt"]["sha256"], hashlib.sha256(expected).hexdigest()
        )

    def test_loaded_views_cannot_drift_from_their_frozen_bytes(self):
        rows = [{
            "season": 2026, "week": 1, "game_id": "2026_01_BUF_LAR",
            "game_type": "REG", "kickoff": self.KICKOFF,
            "away_team": "BUF", "home_team": "LAR",
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(
                Path(directory) / "schedule.json", self.envelope(rows)
            )
            loaded = prospective.load_snapshot(path, "schedule")
            loaded["snapshot"]["rows"][0]["kickoff"] = (
                "2026-09-10T20:20:00-04:00"
            )
            with self.assertRaisesRegex(ValueError, "frozen bytes"):
                prospective.verify_loaded_snapshot(loaded, "schedule")

            config_path = self.write_json(
                Path(directory) / "config.json", self.config(), canonical=True
            )
            model = prospective.load_model_config(config_path)
            model["config"]["history_games"] = 7
            with self.assertRaisesRegex(ValueError, "frozen bytes"):
                prospective.verify_model_config(model)

    def test_loaded_views_reject_type_changes_equal_under_python(self):
        rows = [{
            "season": 2026, "week": 1, "game_id": "2026_01_BUF_LAR",
            "game_type": "REG", "kickoff": self.KICKOFF,
            "away_team": "BUF", "home_team": "LAR",
        }]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loaded = prospective.load_snapshot(
                self.write_json(root / "schedule.json", self.envelope(rows)),
                "schedule",
            )
            loaded["snapshot"]["schema_version"] = True
            with self.assertRaisesRegex(ValueError, "frozen bytes"):
                prospective.verify_loaded_snapshot(loaded, "schedule")

            model = prospective.load_model_config(self.write_json(
                root / "config.json", self.config(), canonical=True
            ))
            model["config"]["schema_version"] = True
            with self.assertRaisesRegex(ValueError, "frozen bytes"):
                prospective.verify_model_config(model)

    def test_snapshot_rejects_duplicate_json_nonfinite_and_naive_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text(
                '{"schema_version":1,"schema_version":1}\n',
                encoding="utf-8", newline="",
            )
            nonfinite = root / "nonfinite.json"
            nonfinite.write_text(
                '{"schema_version":1,"value":NaN}\n',
                encoding="utf-8", newline="",
            )
            naive = self.envelope([], captured="2026-09-09T18:50:00")
            naive_path = self.write_json(root / "naive.json", naive)
            for path in (duplicate, nonfinite, naive_path):
                with self.subTest(path=path.name):
                    with self.assertRaises(ValueError):
                        prospective.load_snapshot(path, "schedule")

    def test_snapshot_rejects_overflowed_json_numbers(self):
        rows = [{
            "season": 2026, "week": 1, "game_id": "2026_01_BUF_LAR",
            "game_type": "REG", "kickoff": self.KICKOFF,
            "away_team": "BUF", "home_team": "LAR",
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overflow.json"
            path.write_text(
                prospective.canonical_json(self.envelope(rows)).replace(
                    '"week":1', '"week":1e999'
                ) + "\n",
                encoding="utf-8", newline="",
            )
            with self.assertRaises(ValueError):
                prospective.load_snapshot(path, "schedule")

    def test_model_config_requires_exact_canonical_frozen_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = self.write_json(
                root / "config.json", self.config(), canonical=True
            )
            loaded = prospective.load_model_config(canonical)
            self.assertEqual(loaded["config"], self.config())
            self.assertEqual(
                loaded["sha256"], hashlib.sha256(canonical.read_bytes()).hexdigest()
            )
            changed = self.config()
            changed["history_games"] = 7
            changed_path = self.write_json(
                root / "changed.json", changed, canonical=True
            )
            with self.assertRaisesRegex(ValueError, "model config"):
                prospective.load_model_config(changed_path)
