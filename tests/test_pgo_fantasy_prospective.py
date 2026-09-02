import hashlib
import json
import math
import tempfile
import subprocess
import unittest
from copy import deepcopy
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

    def test_snapshot_rejects_shape_correct_malformed_row_values(self):
        values, _ = self.source_values()
        schedule = values["schedule"]["rows"][0]
        roster = values["roster"]["rows"][0]
        availability = values["availability"]["rows"][0]
        history = values["history"]["rows"][0]
        cases = (
            ("schedule season boolean", "schedule", {**schedule, "season": True}),
            ("schedule week boolean", "schedule", {**schedule, "week": True}),
            ("schedule game ID blank", "schedule", {**schedule, "game_id": " "}),
            ("schedule game type not text", "schedule", {**schedule, "game_type": 1}),
            ("schedule kickoff naive", "schedule", {
                **schedule, "kickoff": "2026-09-09T20:20:00",
            }),
            ("schedule team outside envelope", "schedule", {
                **schedule, "away_team": "MIA",
            }),
            ("roster player ID blank", "roster", {**roster, "gsis_id": " "}),
            ("roster team outside envelope", "roster", {**roster, "team": "MIA"}),
            ("availability status not text", "availability", {
                **availability, "status": 1,
            }),
            ("availability team outside envelope", "availability", {
                **availability, "team": "MIA",
            }),
            ("history season boolean", "history", {**history, "season": True}),
            ("history week boolean", "history", {**history, "week": True}),
            ("history game ID not text", "history", {**history, "game_id": 1}),
            ("history game type blank", "history", {**history, "game_type": " "}),
            ("history finalized naive", "history", {
                **history, "finalized_at": "2026-01-04T19:00:00",
            }),
            ("history player ID blank", "history", {**history, "gsis_id": " "}),
            ("history position not text", "history", {**history, "position": 1}),
            ("history team outside envelope", "history", {**history, "team": "MIA"}),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (name, kind, row) in enumerate(cases):
                with self.subTest(name=name):
                    payload = dict(values[kind])
                    payload["rows"] = [row]
                    path = self.write_json(root / f"{index}.json", payload)
                    with self.assertRaises(ValueError):
                        prospective.load_snapshot(path, kind)

    def test_history_rejects_invalid_scoring_values(self):
        values, _ = self.source_values()
        history = values["history"]["rows"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, field in enumerate(sorted(pgo_fantasy.SCORING_FIELDS)):
                with self.subTest(field=field):
                    payload = dict(values["history"])
                    payload["rows"] = [{**history, field: "not-a-number"}]
                    path = self.write_json(root / f"{index}.json", payload)
                    with self.assertRaises(ValueError):
                        prospective.load_snapshot(path, "history")

            overflow = Path(root / "overflow.json")
            overflow.write_text(
                prospective.canonical_json(values["history"]).replace(
                    '"receiving_yards":100.0', '"receiving_yards":1e999'
                ) + "\n",
                encoding="utf-8", newline="",
            )
            with self.assertRaises(ValueError):
                prospective.load_snapshot(overflow, "history")

            for index, field in enumerate(sorted(pgo_fantasy.SCORING_FIELDS)):
                with self.subTest(boolean_field=field):
                    payload = dict(values["history"])
                    payload["rows"] = [{**history, field: True}]
                    path = self.write_json(root / f"boolean-{index}.json", payload)
                    with self.assertRaises(ValueError):
                        prospective.load_snapshot(path, "history")

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

    def test_model_config_rejects_an_unfrozen_model_version(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config()
            config["model_version"] = "other_v1"
            path = self.write_json(
                Path(directory) / "config.json", config, canonical=True
            )
            with self.assertRaisesRegex(ValueError, "model config"):
                prospective.load_model_config(path)


class ProspectiveProjectionTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def test_projection_uses_history_cold_start_and_verified_inactive(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            result = prospective.project_game(
                sources, model, game_id, self.LOCKED_AT, lock_mode=True
            )
        rows = {row["gsis_id"]: row for row in result["rows"]}
        self.assertGreater(rows["veteran"]["strong_prediction"], 7.0)
        self.assertEqual(rows["veteran"]["history_count"], 1)
        self.assertEqual(rows["veteran"]["initialization_reason"], "HISTORY")
        self.assertEqual(rows["rookie"]["strong_prediction"], 7.0)
        self.assertEqual(
            rows["rookie"]["initialization_reason"], "TRUE_COLD_START"
        )
        self.assertEqual(rows["inactive"]["strong_prediction"], 0.0)
        self.assertFalse(rows["inactive"]["ranking_eligible"])

    def test_preview_keeps_unverified_players_but_lock_rejects_them(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(
                directory, availability=False
            )
            preview = prospective.project_game(
                sources, model, game_id, self.CAPTURED, lock_mode=False
            )
            self.assertTrue(all(
                row["availability_status"] == "UNVERIFIED"
                for row in preview["rows"]
            ))
            with self.assertRaisesRegex(ValueError, "availability"):
                prospective.project_game(
                    sources, model, game_id, self.LOCKED_AT, lock_mode=True
                )

    def test_future_or_current_game_history_cannot_change_projection(self):
        future = [{
            "season": 2026, "week": 1, "game_id": "2026_01_BUF_LAR",
            "game_type": "REG", "finalized_at": "2026-09-09T23:59:00-04:00",
            "gsis_id": "veteran", "team": "BUF", "position": "WR",
            **self.scoring(receiving_yards=999.0),
        }]
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(
                directory, history_rows=future
            )
            with self.assertRaisesRegex(ValueError, "history"):
                prospective.project_game(
                    sources, model, game_id, self.LOCKED_AT, lock_mode=True
                )

    def test_preview_rejects_any_supplied_source_captured_after_preview_time(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            sources["availability"]["snapshot"]["captured_at"] = (
                "2026-09-09T19:00:00-04:00"
            )
            sources["availability"]["bytes"] = json.dumps(
                sources["availability"]["snapshot"], ensure_ascii=False
            ).encode("utf-8") + b"\n"
            sources["availability"] = prospective.load_snapshot(
                self.write_json(
                    Path(directory) / "late-availability.json",
                    sources["availability"]["snapshot"],
                ),
                "availability",
            )
            with self.assertRaisesRegex(ValueError, "captured after"):
                prospective.project_game(
                    sources, model, game_id, self.CAPTURED, lock_mode=False
                )

    def test_projection_rejects_model_config_frozen_after_prediction_time(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, _, game_id = self.loaded_sources(directory)
            config = self.config()
            config["frozen_at"] = "2026-09-09T19:00:00-04:00"
            model = prospective.load_model_config(self.write_json(
                Path(directory) / "future-config.json", config, canonical=True
            ))
            with self.assertRaisesRegex(ValueError, "frozen after"):
                prospective.project_game(
                    sources, model, game_id, self.CAPTURED, lock_mode=False
                )

    def test_history_is_eight_games_and_current_roster_context_wins(self):
        history = [{
            "season": 2024, "week": 18, "game_id": "old",
            "game_type": "REG", "finalized_at": "2025-01-05T19:00:00-05:00",
            "gsis_id": "veteran", "team": "BUF", "position": "RB",
            **self.scoring(receiving_yards=999.0),
        }]
        history.extend({
            "season": 2025, "week": week, "game_id": f"2025_{week:02d}",
            "game_type": "REG",
            "finalized_at": f"2025-{9 + week // 4:02d}-{1 + week:02d}T19:00:00-04:00",
            "gsis_id": "veteran", "team": "LAR", "position": "RB",
            **self.scoring(receiving_yards=10.0 * week),
        } for week in range(1, 10))
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(
                directory, history_rows=history
            )
            row = next(item for item in prospective.project_game(
                sources, model, game_id, self.LOCKED_AT, lock_mode=True
            )["rows"] if item["gsis_id"] == "veteran")
        self.assertEqual(row["history_count"], 8)
        self.assertEqual(row["team"], "BUF")
        self.assertEqual(row["position"], "WR")
        self.assertEqual(row["opponent"], "LAR")
        self.assertAlmostEqual(
            row["strong_prediction"],
            pgo_fantasy.strong_baseline(list(range(2, 10)), 7.0),
        )

    def test_fb_maps_to_rb_but_unsupported_or_duplicate_roster_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values, game_id = self.source_values()
            values["roster"]["rows"][2]["position"] = "FB"
            loaded = {
                kind: prospective.load_snapshot(
                    self.write_json(root / f"{kind}.json", value), kind
                )
                for kind, value in values.items()
            }
            model = prospective.load_model_config(self.write_json(
                root / "config.json", self.config(), canonical=True
            ))
            rows = prospective.project_game(
                loaded, model, game_id, self.LOCKED_AT, lock_mode=True
            )["rows"]
            self.assertEqual(
                next(row for row in rows if row["gsis_id"] == "inactive")["position"],
                "RB",
            )

            for change in ("unsupported", "duplicate"):
                broken = json.loads(json.dumps(values["roster"]))
                if change == "unsupported":
                    broken["rows"][0]["position"] = "K"
                else:
                    broken["rows"][1]["gsis_id"] = broken["rows"][0]["gsis_id"]
                loaded["roster"] = prospective.load_snapshot(
                    self.write_json(root / f"{change}.json", broken), "roster"
                )
                with self.subTest(change=change):
                    with self.assertRaises(ValueError):
                        prospective.project_game(
                            loaded, model, game_id, self.LOCKED_AT, lock_mode=True
                        )

    def test_ranking_is_deterministic_and_uses_gsis_id_for_ties(self):
        rows = [
            {"game_id": "g", "gsis_id": "b", "position": "WR",
             "strong_prediction": 10.0, "ranking_eligible": True},
            {"game_id": "g", "gsis_id": "a", "position": "WR",
             "strong_prediction": 10.0, "ranking_eligible": True},
            {"game_id": "g", "gsis_id": "q", "position": "QB",
             "strong_prediction": 20.0, "ranking_eligible": True},
        ]
        ranked = prospective.rank_rows(list(reversed(rows)))
        by_id = {row["gsis_id"]: row for row in ranked}
        self.assertEqual(by_id["a"]["position_rank"], 1)
        self.assertEqual(by_id["b"]["position_rank"], 2)
        self.assertEqual(by_id["a"]["flex_rank"], 1)
        self.assertEqual(by_id["q"]["superflex_rank"], 1)

    def test_preview_is_explicitly_ungradeable_and_reports_source_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, _ = self.loaded_sources(
                directory, availability=False
            )
            preview = prospective.build_preview(
                sources, model, 1, self.CAPTURED
            )
        self.assertEqual(preview["evidence_mode"], "PREVIEW")
        self.assertFalse(preview["gradeable"])
        self.assertEqual(
            preview["source_coverage"]["availability"]["missing"],
            ["BUF", "LAR"],
        )

    def test_preview_revalidates_inputs_when_roster_skips_every_game(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, _ = self.loaded_sources(directory)
            sources["roster"] = prospective.load_snapshot(self.write_json(
                root / "missing-roster.json", self.envelope([], teams=("MIA",))
            ), "roster")
            for label in ("source", "model"):
                with self.subTest(label=label):
                    candidate_sources = deepcopy(sources)
                    candidate_model = deepcopy(model)
                    if label == "source":
                        candidate_sources["schedule"]["snapshot"]["rows"][0][
                            "game_id"
                        ] = "tampered"
                    else:
                        candidate_model["config"]["history_games"] = 7
                    with self.assertRaisesRegex(ValueError, "frozen bytes"):
                        prospective.build_preview(
                            candidate_sources, candidate_model, 1, self.CAPTURED
                        )

    def test_preview_checks_chronology_when_roster_skips_every_game(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, _ = self.loaded_sources(directory)
            sources["roster"] = prospective.load_snapshot(self.write_json(
                root / "missing-roster.json", self.envelope([], teams=("MIA",))
            ), "roster")
            for label in ("source", "model"):
                with self.subTest(label=label):
                    candidate_sources = deepcopy(sources)
                    candidate_model = deepcopy(model)
                    if label == "source":
                        late = deepcopy(candidate_sources["availability"]["snapshot"])
                        late["captured_at"] = "2026-09-09T19:00:00-04:00"
                        candidate_sources["availability"] = prospective.load_snapshot(
                            self.write_json(root / "late-availability.json", late),
                            "availability",
                        )
                        error = "captured after"
                    else:
                        config = self.config()
                        config["frozen_at"] = "2026-09-09T19:00:00-04:00"
                        candidate_model = prospective.load_model_config(
                            self.write_json(root / "late-config.json", config, canonical=True)
                        )
                        error = "frozen after"
                    with self.assertRaisesRegex(ValueError, error):
                        prospective.build_preview(
                            candidate_sources, candidate_model, 1, self.CAPTURED
                        )

    def test_late_preview_rejects_history_captured_after_t60(self):
        history = [{
            "season": 2026, "week": 1, "game_id": "2026_01_MIA_NYJ",
            "game_type": "REG", "finalized_at": "2026-09-09T19:25:00-04:00",
            "gsis_id": "veteran", "team": "BUF", "position": "WR",
            **self.scoring(receiving_yards=999.0),
        }]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values, game_id = self.source_values(history_rows=history)
            values["history"]["source_as_of"] = "2026-09-09T19:25:00-04:00"
            values["history"]["captured_at"] = "2026-09-09T19:25:00-04:00"
            sources = {
                kind: prospective.load_snapshot(
                    self.write_json(root / f"{kind}.json", value), kind
                )
                for kind, value in values.items()
            }
            model = prospective.load_model_config(self.write_json(
                root / "config.json", self.config(), canonical=True
            ))
            with self.assertRaisesRegex(ValueError, "captured after"):
                prospective.project_game(
                    sources, model, game_id,
                    "2026-09-09T19:30:00-04:00", lock_mode=False,
                )

    def test_zero_coverage_preview_rejects_post_t60_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, _ = self.loaded_sources(directory)
            sources["roster"] = prospective.load_snapshot(self.write_json(
                root / "missing-roster.json", self.envelope([], teams=("MIA",))
            ), "roster")
            for label in ("source", "model"):
                with self.subTest(label=label):
                    candidate_sources = deepcopy(sources)
                    candidate_model = deepcopy(model)
                    if label == "source":
                        late = deepcopy(candidate_sources["availability"]["snapshot"])
                        late["captured_at"] = "2026-09-09T19:25:00-04:00"
                        candidate_sources["availability"] = prospective.load_snapshot(
                            self.write_json(root / "late-availability.json", late),
                            "availability",
                        )
                        error = "captured after"
                    else:
                        config = self.config()
                        config["frozen_at"] = "2026-09-09T19:25:00-04:00"
                        candidate_model = prospective.load_model_config(
                            self.write_json(root / "late-config.json", config, canonical=True)
                        )
                        error = "frozen after"
                    with self.assertRaisesRegex(ValueError, error):
                        prospective.build_preview(
                            candidate_sources, candidate_model, 1,
                            "2026-09-09T19:30:00-04:00",
                        )


class ProspectiveGameLockTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def test_lock_is_canonical_deterministic_and_bound_to_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            first = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            second = prospective.build_game_lock(
                dict(reversed(list(sources.items()))), model, game_id,
                self.LOCKED_AT, "a" * 40,
            )
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "LOCKED")
        self.assertEqual(
            prospective.serialize_game_lock(first),
            prospective.serialize_game_lock(second),
        )
        changed = json.loads(prospective.serialize_game_lock(first))
        next(
            row for row in changed["predictions"]
            if row["availability_status"] == "ACTIVE"
        )["strong_prediction"] += 1.0
        with self.assertRaisesRegex(ValueError, "integrity"):
            prospective.verify_game_lock(changed)

    def test_after_t_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            with self.assertRaisesRegex(ValueError, "T-60"):
                prospective.build_game_lock(
                    sources, model, game_id,
                    "2026-09-09T19:20:01-04:00", "a" * 40,
                )

    def test_lock_rejects_mutated_source_view_and_incomplete_team_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            sources["schedule"]["snapshot"]["rows"][0]["home_team"] = "SF"
            with self.assertRaisesRegex(ValueError, "frozen bytes"):
                prospective.build_game_lock(
                    sources, model, game_id, self.LOCKED_AT, "a" * 40
                )

            sources, model, game_id = self.loaded_sources(
                Path(directory) / "coverage"
            )
            incomplete = json.loads(json.dumps(
                sources["availability"]["snapshot"]
            ))
            incomplete["teams_processed"] = ["BUF"]
            sources["availability"] = prospective.load_snapshot(
                self.write_json(
                    Path(directory) / "incomplete.json", incomplete
                ),
                "availability",
            )
            with self.assertRaisesRegex(ValueError, "coverage"):
                prospective.build_game_lock(
                    sources, model, game_id, self.LOCKED_AT, "a" * 40
                )

    def test_lock_writer_never_overwrites_existing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, game_id = self.loaded_sources(root / "inputs")
            lock = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            output = root / "lock"
            self.assertTrue(prospective.write_game_lock(output, lock))
            first = (output / "fantasy_lock.json").read_bytes()
            self.assertFalse(prospective.write_game_lock(output, lock))
            self.assertEqual((output / "fantasy_lock.json").read_bytes(), first)

    def test_lock_writer_checks_publication_guard_after_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, game_id = self.loaded_sources(root / "inputs")
            lock = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            output = root / "lock"
            staged = []

            def guard():
                staged.extend(output.glob("*.pending"))
                raise ValueError("Fantasy game lock T-60 window has closed")

            with self.assertRaisesRegex(ValueError, "T-60"):
                prospective.write_game_lock(output, lock, guard)
            self.assertTrue(staged)
            self.assertFalse(output.exists())

    def test_rescheduled_lock_does_not_rewrite_old_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, game_id = self.loaded_sources(root / "inputs")
            old = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            old_dir = root / "old"
            self.assertTrue(prospective.write_game_lock(old_dir, old))
            original = (old_dir / "fantasy_lock.json").read_bytes()
            rescheduled = json.loads(json.dumps(
                sources["schedule"]["snapshot"]
            ))
            rescheduled["rows"][0]["kickoff"] = (
                "2026-09-10T20:20:00-04:00"
            )
            sources["schedule"] = prospective.load_snapshot(
                self.write_json(root / "rescheduled.json", rescheduled),
                "schedule",
            )
            new = prospective.build_game_lock(
                sources, model, game_id,
                "2026-09-10T19:20:00-04:00", "a" * 40,
            )
            self.assertTrue(prospective.write_game_lock(root / "new", new))
            self.assertEqual((old_dir / "fantasy_lock.json").read_bytes(), original)
            self.assertNotEqual(old["artifact_sha256"], new["artifact_sha256"])

    def test_lock_rejects_rehashed_noncanonical_receipt_teams(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            changed = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
        changed["source_receipts"][0]["teams_processed"] = [
            "BUF", "BUF", "LAR"
        ]
        changed["source_receipts_sha256"] = hashlib.sha256(
            prospective.canonical_json(changed["source_receipts"]).encode("utf-8")
        ).hexdigest()
        changed["artifact_sha256"] = prospective._artifact_hash(changed)
        with self.assertRaisesRegex(ValueError, "source receipts"):
            prospective.verify_game_lock(changed)

    def test_load_game_lock_returns_exact_bytes_sha_and_lf_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, game_id = self.loaded_sources(root / "inputs")
            lock = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            data = prospective.serialize_game_lock(lock).encode("utf-8")
            path = root / "fantasy_lock.json"
            path.write_bytes(data)
            loaded = prospective.load_game_lock(path)
        self.assertEqual(loaded["lock"], lock)
        self.assertEqual(loaded["bytes"], data)
        self.assertEqual(loaded["sha256"], hashlib.sha256(data).hexdigest())
        csv_text = prospective.game_prediction_csv(lock)
        self.assertTrue(csv_text.endswith("\n"))
        self.assertNotIn("\r", csv_text)
        self.assertEqual(
            csv_text.splitlines()[0], ",".join(prospective.LOCK_PREDICTION_COLUMNS)
        )

    def test_load_game_lock_rejects_noncanonical_and_duplicate_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, game_id = self.loaded_sources(root / "inputs")
            lock = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            noncanonical = root / "noncanonical.json"
            noncanonical.write_bytes(
                b"\n" + prospective.serialize_game_lock(lock).encode("utf-8")
            )
            duplicate = root / "duplicate.json"
            duplicate.write_bytes(b'{"schema_version":1,"schema_version":1}\n')
            with self.assertRaisesRegex(ValueError, "canonical"):
                prospective.load_game_lock(noncanonical)
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                prospective.load_game_lock(duplicate)


class ProspectiveWeekGradeTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def load_result_value(self, value):
        with tempfile.TemporaryDirectory() as directory:
            return prospective.load_results(self.write_json(
                Path(directory) / "results.json", value
            ))

    def week_evidence(self):
        positions = (("QB", 30), ("RB", 40), ("WR", 40), ("TE", 20))
        roster_rows = [
            {
                "gsis_id": f"{position}-{index:03d}",
                "player_name": f"{position} {index:03d}",
                "team": "BUF" if index % 2 == 0 else "LAR",
                "position": position,
                "status": "ACT",
            }
            for position, count in positions for index in range(count)
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values, game_id = self.source_values(history_rows=[])
            values["roster"] = self.envelope(roster_rows)
            values["availability"] = self.envelope([])
            sources = {
                kind: prospective.load_snapshot(
                    self.write_json(root / f"{kind}.json", value), kind
                )
                for kind, value in values.items()
            }
            model = prospective.load_model_config(self.write_json(
                root / "config.json", self.config(), canonical=True
            ))
            lock = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            lock_bytes = prospective.serialize_game_lock(lock).encode("utf-8")
            loaded_locks = [{
                "lock": lock,
                "bytes": lock_bytes,
                "sha256": hashlib.sha256(lock_bytes).hexdigest(),
            }]
            result_rows = [{
                "game_id": game_id,
                "gsis_id": row["gsis_id"],
                **self.scoring(receiving_yards=10.0),
            } for row in roster_rows if row["gsis_id"] != "WR-000"]
            results_value = {
                "schema_version": 1,
                "source": "synthetic-official-results",
                "source_as_of": "2026-09-10T00:30:00-04:00",
                "captured_at": "2026-09-10T00:30:00-04:00",
                "teams_processed": ["BUF", "LAR"],
                "games": [{
                    "game_id": game_id,
                    "status": "FINAL",
                    "finalized_at": "2026-09-10T00:20:00-04:00",
                }],
                "rows": result_rows,
            }
            results = prospective.load_results(self.write_json(
                root / "results.json", results_value
            ))
        return loaded_locks, results

    def test_week_grade_uses_exact_locks_and_zero_fills_missing_stats(self):
        loaded_locks, results = self.week_evidence()
        grade = prospective.grade_week(loaded_locks, results)
        self.assertEqual(grade["status"], "HOLD")
        self.assertEqual(grade["publication_status"], "EXPERIMENTAL")
        self.assertEqual(grade["metrics"]["primary"]["count"], 96)
        missing = next(row for row in grade["rows"] if row["gsis_id"] == "WR-000")
        self.assertEqual(missing["fantasy_points"], 0.0)
        self.assertTrue(grade["checks"]["complete_game_results"])

    def test_results_load_once_with_exact_bytes_and_reject_bad_json_values(self):
        _, results = self.week_evidence()
        self.assertEqual(
            results["receipt"]["sha256"],
            hashlib.sha256(results["bytes"]).hexdigest(),
        )
        self.assertIs(prospective.verify_loaded_results(results), results)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (
                ("duplicate", b'{"schema_version":1,"schema_version":1}\n'),
                ("nonfinite", b'{"schema_version":NaN}\n'),
            ):
                path = root / f"{name}.json"
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "invalid JSON"):
                    prospective.load_results(path)
        results["receipt"]["rows"] += 1
        with self.assertRaisesRegex(ValueError, "frozen bytes"):
            prospective.verify_loaded_results(results)

    def test_results_reject_invalid_types_nonfinite_scoring_and_finalization_timing(self):
        _, results = self.week_evidence()
        for field, value, error in (
            ("schema_version", True, "schema"),
            ("captured_at", "2026-09-10T00:00:00", "timestamp"),
        ):
            changed = deepcopy(results["snapshot"])
            changed[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, error):
                self.load_result_value(changed)
        changed = deepcopy(results["snapshot"])
        changed["rows"][0]["receiving_yards"] = float("inf")
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            self.load_result_value(changed)
        changed = deepcopy(results["snapshot"])
        changed["games"][0]["finalized_at"] = "2026-09-10T00:31:00-04:00"
        with self.assertRaisesRegex(ValueError, "after result capture"):
            self.load_result_value(changed)

    def test_week_grade_rejects_missing_final_game_extra_or_cross_week_results(self):
        loaded_locks, results = self.week_evidence()
        missing_value = deepcopy(results["snapshot"])
        missing_value["games"] = []
        missing_value["rows"] = []
        with self.assertRaisesRegex(ValueError, "final game"):
            prospective.grade_week(loaded_locks, self.load_result_value(missing_value))
        extra_value = deepcopy(results["snapshot"])
        extra_value["rows"].append({
            "game_id": loaded_locks[0]["lock"]["game_id"],
            "gsis_id": "not-locked",
            **self.scoring(receiving_yards=1.0),
        })
        with self.assertRaisesRegex(ValueError, "result identity"):
            prospective.grade_week(loaded_locks, self.load_result_value(extra_value))
        cross_week = deepcopy(results["snapshot"])
        cross_week["games"].append({
            "game_id": "2026_02_MIA_NYJ", "status": "FINAL",
            "finalized_at": "2026-09-10T00:20:00-04:00",
        })
        cross_week["rows"].append({
            "game_id": "2026_02_MIA_NYJ", "gsis_id": "other",
            **self.scoring(),
        })
        with self.assertRaisesRegex(ValueError, "final game coverage"):
            prospective.grade_week(loaded_locks, self.load_result_value(cross_week))

    def test_week_grade_rejects_rehashed_or_noncanonical_lock_and_epoch_mismatch(self):
        loaded_locks, results = self.week_evidence()
        changed = deepcopy(loaded_locks[0])
        changed["lock"]["predictions"][0]["strong_prediction"] += 5.0
        with self.assertRaisesRegex(ValueError, "integrity"):
            prospective.grade_week([changed], results)
        changed = deepcopy(loaded_locks[0])
        changed["lock"]["week"] = 2
        for row in changed["lock"]["predictions"]:
            row["week"] = 2
        changed["lock"]["prediction_integrity_sha256"] = prospective._prediction_hash(
            changed["lock"]["predictions"]
        )
        changed["lock"]["artifact_sha256"] = prospective._artifact_hash(changed["lock"])
        data = prospective.serialize_game_lock(changed["lock"]).encode("utf-8")
        changed["bytes"] = data
        changed["sha256"] = hashlib.sha256(data).hexdigest()
        with self.assertRaisesRegex(ValueError, "one model epoch"):
            prospective.grade_week([loaded_locks[0], changed], results)

    def test_weekly_ranks_and_primary_pool_do_not_depend_on_results(self):
        loaded_locks, results = self.week_evidence()
        first = prospective.grade_week(loaded_locks, results)
        changed_value = deepcopy(results["snapshot"])
        for index, row in enumerate(changed_value["rows"]):
            row.update(self.scoring(receiving_yards=float(index * 100)))
        second = prospective.grade_week(
            loaded_locks, self.load_result_value(changed_value)
        )

        def selections(grade):
            return {
                (row["game_id"], row["gsis_id"], row["position_rank"],
                 row["flex_rank"], row["superflex_rank"])
                for row in grade["rows"] if row["primary_pool"]
            }

        self.assertEqual(selections(first), selections(second))

    def test_week_grade_rejects_rehashed_metric_or_artifact_tampering(self):
        loaded_locks, results = self.week_evidence()
        grade = prospective.grade_week(loaded_locks, results)
        changed = deepcopy(grade)
        changed["metrics"]["primary"]["strong_mae"] += 1.0
        changed["artifact_sha256"] = prospective._artifact_hash(changed)
        with self.assertRaisesRegex(ValueError, "metrics"):
            prospective.verify_week_grade(changed)
        changed = deepcopy(grade)
        changed["rows"][0]["fantasy_points"] += 1.0
        with self.assertRaisesRegex(ValueError, "row binding"):
            prospective.serialize_week_grade(changed)
        changed = deepcopy(grade)
        changed["artifact_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "integrity"):
            prospective.serialize_week_grade(changed)

    def test_week_grade_writer_never_overwrites_an_existing_artifact(self):
        loaded_locks, results = self.week_evidence()
        grade = prospective.grade_week(loaded_locks, results)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "grade"
            self.assertTrue(prospective.write_week_grade(output, grade))
            first = (output / "fantasy_week_grade.json").read_bytes()
            self.assertFalse(prospective.write_week_grade(output, grade))
            self.assertEqual((output / "fantasy_week_grade.json").read_bytes(), first)

    def test_grade_reconstructs_rows_from_exact_embedded_lock_bytes(self):
        loaded_locks, results = self.week_evidence()
        changed = prospective.grade_week(loaded_locks, results)
        changed["rows"][0]["player_name"] = "rewritten"
        changed["artifact_sha256"] = prospective._artifact_hash(changed)
        with self.assertRaisesRegex(ValueError, "evidence binding"):
            prospective.verify_week_grade(changed)

    def test_grade_reconstructs_actuals_from_exact_embedded_result_bytes(self):
        loaded_locks, results = self.week_evidence()
        changed = prospective.grade_week(loaded_locks, results)
        raw = json.loads(changed["result_bytes"])
        raw["rows"][0]["receiving_yards"] += 100.0
        changed["result_bytes"] = prospective.canonical_json(raw) + "\n"
        changed["artifact_sha256"] = prospective._artifact_hash(changed)
        with self.assertRaisesRegex(ValueError, "result receipt"):
            prospective.verify_week_grade(changed)

    def test_week_grade_rejects_mixed_code_epoch(self):
        loaded_locks, results = self.week_evidence()
        changed = deepcopy(loaded_locks[0])
        changed["lock"]["code_sha"] = "b" * 40
        changed["lock"]["artifact_sha256"] = prospective._artifact_hash(changed["lock"])
        data = prospective.serialize_game_lock(changed["lock"]).encode("utf-8")
        changed["bytes"] = data
        changed["sha256"] = hashlib.sha256(data).hexdigest()
        with self.assertRaisesRegex(ValueError, "one model epoch"):
            prospective.grade_week([loaded_locks[0], changed], results)

    def test_week_grade_rejects_python_equal_boolean_substitutions(self):
        loaded_locks, results = self.week_evidence()
        grade = prospective.grade_week(loaded_locks, results)
        for field, value in (
            (("checks", "primary_pool_96"), 1),
            (("metrics", "primary", "strong_win"), 0),
            (("rows", 0, "position_rank"), True),
        ):
            changed = deepcopy(grade)
            target = changed
            for key in field[:-1]:
                target = target[key]
            target[field[-1]] = value
            changed["artifact_sha256"] = prospective._artifact_hash(changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                prospective.verify_week_grade(changed)


class ProspectiveSeasonGradeTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def week_grade(self, week, strong_delta=1.0, code_sha="a" * 40):
        locks, results = ProspectiveWeekGradeTests("runTest").week_evidence()
        lock = deepcopy(locks[0]["lock"])
        game_id = f"2026_{week:02d}_BUF_LAR"
        lock["week"] = week
        lock["game_id"] = game_id
        lock["code_sha"] = code_sha
        lock["scheduled_week_games"] = [game_id]
        for row in lock["predictions"]:
            row["week"] = week
            row["game_id"] = game_id
            row["null_prediction"] += strong_delta
        lock["prediction_integrity_sha256"] = prospective._prediction_hash(
            lock["predictions"]
        )
        lock["artifact_sha256"] = prospective._artifact_hash(lock)
        lock_bytes = prospective.serialize_game_lock(lock).encode("utf-8")
        loaded = {
            "lock": lock,
            "bytes": lock_bytes,
            "sha256": hashlib.sha256(lock_bytes).hexdigest(),
        }
        snapshot = deepcopy(results["snapshot"])
        for game in snapshot["games"]:
            game["game_id"] = game_id
        for row in snapshot["rows"]:
            row["game_id"] = game_id
        result_bytes = (prospective.canonical_json(snapshot) + "\n").encode("utf-8")
        grade = prospective.grade_week(
            [loaded], prospective._results_from_bytes(result_bytes)
        )
        self.assertEqual(sum(row["primary_pool"] for row in grade["rows"]), 96)
        self.assertEqual(
            len({(row["game_id"], row["gsis_id"]) for row in grade["rows"]
                 if row["primary_pool"]}),
            96,
        )
        return grade

    @staticmethod
    def audit(verdict="CLEAN", audited_at="2026-09-11T00:00:00-04:00"):
        audit = {
            "schema_version": 1,
            "verdict": verdict,
            "audited_at": audited_at,
        }
        audit["artifact_sha256"] = prospective._artifact_hash(audit)
        return audit

    def season_weeks(self, strong_delta=1.0):
        return [self.week_grade(week, strong_delta) for week in range(1, 19)]

    def test_complete_verified_weekly_evidence_passes_the_frozen_gate(self):
        receipt = prospective.grade_season(self.season_weeks(), self.audit())
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["publication_status"], "VALIDATED")
        self.assertEqual(receipt["bootstrap"]["seed"], 20260901)
        self.assertEqual(receipt["bootstrap"]["samples"], 10_000)
        self.assertGreater(receipt["bootstrap"]["lower"], 0.0)
        self.assertEqual(receipt["metrics"]["primary_count"], 18 * 96)
        self.assertEqual(
            prospective.serialize_season_grade(receipt),
            prospective.serialize_season_grade(prospective.verify_season_grade(receipt)),
        )
        self.assertEqual(
            prospective.serialize_season_grade(receipt),
            prospective.serialize_season_grade(
                prospective.grade_season(self.season_weeks(), self.audit())
            ),
        )

    def test_missing_week_holds_but_duplicate_week_blocks(self):
        weeks = self.season_weeks()
        self.assertEqual(
            prospective.grade_season(weeks[:-1], self.audit())["status"], "HOLD"
        )
        weeks[-1] = weeks[-2]
        self.assertEqual(
            prospective.grade_season(weeks, self.audit())["status"], "BLOCKED"
        )

    def test_mixed_code_sha_blocks_the_epoch(self):
        weeks = self.season_weeks()
        weeks[-1] = self.week_grade(18, code_sha="b" * 40)
        receipt = prospective.grade_season(weeks, self.audit())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["checks"]["common_model_epoch"])

    def test_loaders_require_canonical_bytes_and_strict_values(self):
        grade = self.week_grade(1)
        audit = self.audit()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            grade_path = root / "grade.json"
            audit_path = root / "audit.json"
            grade_path.write_text(prospective.serialize_week_grade(grade), newline="")
            audit_path.write_text(prospective.canonical_json(audit) + "\n", newline="")
            self.assertEqual(prospective.load_week_grade(grade_path), grade)
            self.assertEqual(prospective.load_leakage_audit(audit_path), audit)
            grade_path.write_text(prospective.serialize_week_grade(grade) + " ", newline="")
            with self.assertRaisesRegex(ValueError, "canonical"):
                prospective.load_week_grade(grade_path)
            audit_path.write_text(
                prospective.canonical_json(audit) + "\n ", newline=""
            )
            with self.assertRaisesRegex(ValueError, "canonical"):
                prospective.load_leakage_audit(audit_path)
            audit_path.write_text(
                prospective.canonical_json({**audit, "schema_version": True}) + "\n",
                newline="",
            )
            with self.assertRaises(ValueError):
                prospective.load_leakage_audit(audit_path)
        receipt = prospective.grade_season(self.season_weeks(), self.audit())
        for field, value in (
            (("checks", "season_complete"), 1),
            (("metrics", "primary_count"), True),
            (("metrics", "null_mae"), float("nan")),
            (("leakage_audit_audited_at",), "2026-09-10T00:30:00-04:00"),
            (("weeks",), list(range(1, 18))),
        ):
            changed = deepcopy(receipt)
            target = changed
            for key in field[:-1]:
                target = target[key]
            target[field[-1]] = value
            if not isinstance(value, float) or math.isfinite(value):
                changed["artifact_sha256"] = prospective._artifact_hash(changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                prospective.verify_season_grade(changed)

    def test_full_season_statistical_shortfall_is_experimental_hold(self):
        receipt = prospective.grade_season(self.season_weeks(0.0), self.audit())
        self.assertEqual(receipt["status"], "HOLD")
        self.assertEqual(receipt["publication_status"], "EXPERIMENTAL")
        self.assertFalse(receipt["checks"]["relative_improvement_at_least_1pct"])

    def test_audit_must_follow_the_latest_frozen_result_capture(self):
        receipt = prospective.grade_season(
            self.season_weeks(), self.audit(audited_at="2026-09-10T00:29:00-04:00")
        )
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["checks"]["leakage_audit_after_results"])

    def test_equal_result_capture_audit_qualifies_and_forged_pass_fails(self):
        receipt = prospective.grade_season(
            self.season_weeks(), self.audit(audited_at="2026-09-10T00:30:00-04:00")
        )
        self.assertEqual(receipt["status"], "PASS")
        forged = deepcopy(receipt)
        forged.update({
            "week_grade_sha256": [],
            "week_grade_bytes": [],
            "weeks": list(range(1, 19)),
            "metrics": {
                "primary_count": 0, "null_mae": None, "strong_mae": None,
                "relative_improvement": 1.0, "weekly_wins": 18,
            },
            "bootstrap": {
                "mean": 1.0, "lower": 1.0, "upper": 1.0,
                "samples": 10_000, "seed": 20260901,
            },
            "checks": {key: True for key in receipt["checks"]},
            "status": "PASS", "publication_status": "VALIDATED",
        })
        forged["artifact_sha256"] = prospective._artifact_hash(forged)
        with self.assertRaises(ValueError):
            prospective.serialize_season_grade(forged)

    def test_rebuilt_diagnostics_are_deterministic_and_tamper_evident(self):
        receipt = prospective.grade_season(self.season_weeks(), self.audit())
        diagnostics = receipt["diagnostics"]
        self.assertEqual(
            list(diagnostics["by_position"]), ["QB", "RB", "WR", "TE"]
        )
        self.assertEqual(
            [item["week"] for item in diagnostics["weekly_strong_spearman"]],
            list(range(1, 19)),
        )
        misses = diagnostics["largest_strong_misses"]
        self.assertEqual(
            misses,
            sorted(misses, key=lambda row: (
                -row["strong_absolute_error"], row["game_id"], row["gsis_id"]
            )),
        )
        changed = deepcopy(receipt)
        changed["diagnostics"]["availability_counts"]["active"] = True
        changed["artifact_sha256"] = prospective._artifact_hash(changed)
        with self.assertRaises(ValueError):
            prospective.serialize_season_grade(changed)

    def test_coordinated_weekly_artifact_mutation_still_blocks(self):
        weeks = self.season_weeks()
        weeks[-1]["rows"][0]["fantasy_points"] += 1.0
        weeks[-1]["artifact_sha256"] = prospective._artifact_hash(weeks[-1])
        receipt = prospective.grade_season(weeks, self.audit())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["checks"]["artifact_integrity"])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "blocked"
            self.assertTrue(prospective.write_season_grade(output, receipt))
            path = output / "fantasy_season_grade.json"
            first = path.read_bytes()
            self.assertFalse(prospective.write_season_grade(output, receipt))
            self.assertEqual(path.read_bytes(), first)
        changed = deepcopy(receipt)
        changed["rejected_week_grade_bytes"] = [
            prospective.serialize_week_grade(weeks[0])
        ]
        changed["artifact_sha256"] = prospective._artifact_hash(changed)
        with self.assertRaises(ValueError):
            prospective.serialize_season_grade(changed)

    def test_json_safe_malformed_week_is_serializable_blocked_evidence(self):
        receipt = prospective.grade_season([{"unexpected": []}], self.audit())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["checks"]["artifact_integrity"])
        self.assertEqual(len(receipt["rejected_week_grade_bytes"]), 1)
        self.assertEqual(
            prospective.serialize_season_grade(receipt),
            prospective.serialize_season_grade(prospective.verify_season_grade(receipt)),
        )

    def test_season_evidence_items_must_be_text(self):
        receipt = prospective.grade_season(self.season_weeks(), self.audit())
        for field in ("week_grade_bytes", "rejected_week_grade_bytes"):
            changed = deepcopy(receipt)
            changed[field] = [1]
            changed["artifact_sha256"] = prospective._artifact_hash(changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                prospective.serialize_season_grade(changed)

    def test_season_writer_never_overwrites_an_existing_artifact(self):
        receipt = prospective.grade_season(self.season_weeks(), self.audit())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "season"
            self.assertTrue(prospective.write_season_grade(output, receipt))
            path = output / "fantasy_season_grade.json"
            first = path.read_bytes()
            self.assertFalse(prospective.write_season_grade(output, receipt))
            self.assertEqual(path.read_bytes(), first)


class ProspectiveFantasyCommandTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def test_preview_and_lock_use_only_supplied_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            preview = paths["root"] / "preview.json"
            with (
                patch("urllib.request.urlopen") as remote,
                patch.object(
                    prospective, "_now",
                    return_value=prospective.parse_timestamp(
                        self.LOCKED_AT, "test clock"
                    ),
                ),
                patch.object(
                    prospective, "_current_code_sha", return_value="a" * 40
                ),
            ):
                self.assertEqual(prospective.main([
                    "preview", "--schedule", str(paths["schedule"]),
                    "--roster", str(paths["roster"]),
                    "--history", str(paths["history"]),
                    "--config", str(paths["config"]),
                    "--week", "1", "--as-of", self.CAPTURED,
                    "--output", str(preview),
                ]), 0)
                self.assertEqual(prospective.main([
                    "lock", "--schedule", str(paths["schedule"]),
                    "--roster", str(paths["roster"]),
                    "--availability", str(paths["availability"]),
                    "--history", str(paths["history"]),
                    "--config", str(paths["config"]),
                    "--game-id", paths["game_id"],
                    "--output-dir", str(paths["root"] / "lock"),
                    "--diagnostic-output", str(paths["root"] / "lock-blocked.json"),
                ]), 0)
            remote.assert_not_called()
            self.assertTrue(preview.is_file())
            self.assertTrue((paths["root"] / "lock" / "fantasy_lock.json").is_file())

    def test_preview_cannot_replace_a_supplied_frozen_file(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            first = paths["schedule"].read_bytes()
            self.assertEqual(prospective.main([
                "preview", "--schedule", str(paths["schedule"]),
                "--roster", str(paths["roster"]),
                "--history", str(paths["history"]),
                "--config", str(paths["config"]),
                "--week", "1", "--as-of", self.CAPTURED,
                "--output", str(paths["schedule"]),
            ]), 1)
            self.assertEqual(paths["schedule"].read_bytes(), first)

    def test_preview_refuses_to_replace_an_existing_lock_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            sources = {
                kind: prospective.load_snapshot(paths[kind], kind)
                for kind in ("schedule", "roster", "availability", "history")
            }
            model = prospective.load_model_config(paths["config"])
            lock = prospective.build_game_lock(
                sources, model, paths["game_id"], self.LOCKED_AT, "a" * 40
            )
            output = paths["root"] / "fantasy_lock.json"
            output.write_text(prospective.serialize_game_lock(lock), newline="")
            first = output.read_bytes()
            self.assertEqual(prospective.main([
                "preview", "--schedule", str(paths["schedule"]),
                "--roster", str(paths["roster"]),
                "--history", str(paths["history"]),
                "--config", str(paths["config"]),
                "--week", "1", "--as-of", self.CAPTURED,
                "--output", str(output),
            ]), 1)
            self.assertEqual(output.read_bytes(), first)

    def test_preview_race_preserves_a_concurrently_created_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            output = paths["root"] / "preview.json"
            preview_command = [
                "preview", "--schedule", str(paths["schedule"]),
                "--roster", str(paths["roster"]),
                "--history", str(paths["history"]),
                "--config", str(paths["config"]),
                "--week", "1", "--as-of", self.CAPTURED,
                "--output", str(output),
            ]
            self.assertEqual(prospective.main(preview_command), 0)
            artifact = b'{"accepted":"concurrent artifact"}\n'
            detach = prospective.pgo_prospective._detach_output

            def raced(target, state):
                detach(target, state)
                Path(target).write_bytes(artifact)

            with patch.object(
                prospective.pgo_prospective, "_detach_output", side_effect=raced
            ):
                self.assertEqual(prospective.main(preview_command), 1)
            self.assertEqual(output.read_bytes(), artifact)

    def test_preview_missing_target_race_cannot_clobber_an_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            output = paths["root"] / "preview.json"
            artifact = b'{"accepted":"concurrent artifact"}\n'
            exclusive = prospective.pgo_fantasy._exclusive_write_text

            def raced(path, text):
                if Path(path) == output:
                    output.write_bytes(artifact)
                return exclusive(path, text)

            with patch.object(
                prospective.pgo_fantasy, "_exclusive_write_text", side_effect=raced
            ):
                self.assertEqual(prospective.main([
                    "preview", "--schedule", str(paths["schedule"]),
                    "--roster", str(paths["roster"]),
                    "--history", str(paths["history"]),
                    "--config", str(paths["config"]),
                    "--week", "1", "--as-of", self.CAPTURED,
                    "--output", str(output),
                ]), 1)
            self.assertEqual(output.read_bytes(), artifact)

    def test_preview_interrupt_cleans_its_claim_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            output = paths["root"] / "preview.json"
            original = prospective.pgo_fantasy._exclusive_write_text

            def interrupted(path, text):
                if Path(path) == output:
                    raise KeyboardInterrupt()
                return original(path, text)

            with patch.object(
                prospective.pgo_fantasy, "_exclusive_write_text", side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    prospective.main([
                        "preview", "--schedule", str(paths["schedule"]),
                        "--roster", str(paths["roster"]),
                        "--history", str(paths["history"]),
                        "--config", str(paths["config"]),
                        "--week", "1", "--as-of", self.CAPTURED,
                        "--output", str(output),
                    ])
            self.assertFalse(output.exists())
            self.assertFalse((paths["root"] / ".preview.json.preview-claim").exists())

    def test_preview_interrupt_restores_the_replaced_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            output = paths["root"] / "preview.json"
            command = [
                "preview", "--schedule", str(paths["schedule"]),
                "--roster", str(paths["roster"]),
                "--history", str(paths["history"]),
                "--config", str(paths["config"]),
                "--week", "1", "--as-of", self.CAPTURED,
                "--output", str(output),
            ]
            self.assertEqual(prospective.main(command), 0)
            first = output.read_bytes()
            exclusive = prospective.pgo_fantasy._exclusive_write_text

            def interrupted(path, text):
                if Path(path) == output:
                    raise KeyboardInterrupt()
                return exclusive(path, text)

            with patch.object(
                prospective.pgo_fantasy, "_exclusive_write_text", side_effect=interrupted
            ):
                with self.assertRaises(KeyboardInterrupt):
                    prospective.main(command)
            self.assertEqual(output.read_bytes(), first)

    def test_lock_rechecks_time_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            output = paths["root"] / "late-lock"
            diagnostic = paths["root"] / "late-blocked.json"
            events = []

            def code_sha():
                events.append("sha")
                return "a" * 40

            def clock():
                events.append("now")
                return prospective.parse_timestamp(
                    (self.LOCKED_AT if events.count("now") < 3
                     else "2026-09-09T19:21:00-04:00"),
                    "test clock",
                )

            with (
                patch.object(prospective, "_now", side_effect=clock),
                patch.object(prospective, "_current_code_sha", side_effect=code_sha),
            ):
                result = prospective.main([
                    "lock", "--schedule", str(paths["schedule"]),
                    "--roster", str(paths["roster"]),
                    "--availability", str(paths["availability"]),
                    "--history", str(paths["history"]),
                    "--config", str(paths["config"]),
                    "--game-id", paths["game_id"], "--output-dir", str(output),
                    "--diagnostic-output", str(diagnostic),
                ])
            self.assertEqual(result, 1)
            self.assertEqual(events[:2], ["sha", "now"])
            self.assertEqual(events.count("now"), 3)
            self.assertFalse(output.exists())
            self.assertEqual(json.loads(diagnostic.read_text())["status"], "BLOCKED")

    def test_existing_diagnostic_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            diagnostic = paths["root"] / "blocked.json"
            diagnostic.write_text("frozen evidence\n", newline="")
            first = diagnostic.read_bytes()
            with (
                patch.object(
                    prospective, "_now",
                    return_value=prospective.parse_timestamp(
                        "2026-09-09T19:21:00-04:00", "test clock"
                    ),
                ),
                patch.object(
                    prospective, "_current_code_sha", return_value="a" * 40
                ),
            ):
                self.assertEqual(prospective.main([
                    "lock", "--schedule", str(paths["schedule"]),
                    "--roster", str(paths["roster"]),
                    "--availability", str(paths["availability"]),
                    "--history", str(paths["history"]),
                    "--config", str(paths["config"]),
                    "--game-id", paths["game_id"],
                    "--output-dir", str(paths["root"] / "lock"),
                    "--diagnostic-output", str(diagnostic),
                ]), 2)
            self.assertEqual(diagnostic.read_bytes(), first)

    def test_grade_commands_route_hold_and_pass_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(
                    prospective, "load_game_lock",
                    return_value={"lock": {"code_sha": "a" * 40}},
                ),
                patch.object(prospective, "load_results", return_value={}),
                patch.object(prospective, "_current_code_sha", return_value="a" * 40),
                patch.object(
                    prospective, "grade_week", return_value={"status": "HOLD"}
                ),
                patch.object(prospective, "write_week_grade", return_value=True),
            ):
                self.assertEqual(prospective.main([
                    "grade-week", "--lock", str(root / "lock.json"),
                    "--results", str(root / "results.json"),
                    "--output-dir", str(root / "week"),
                    "--diagnostic-output", str(root / "week-blocked.json"),
                ]), 1)
            with (
                patch.object(
                    prospective, "load_week_grade", return_value={"code_sha": "a" * 40}
                ),
                patch.object(prospective, "load_leakage_audit", return_value={}),
                patch.object(prospective, "_current_code_sha", return_value="a" * 40),
                patch.object(
                    prospective, "grade_season", return_value={"status": "PASS"}
                ),
                patch.object(prospective, "write_season_grade", return_value=True),
            ):
                self.assertEqual(prospective.main([
                    "grade-season", "--week-grade", str(root / "week.json"),
                    "--leakage-audit", str(root / "audit.json"),
                    "--output-dir", str(root / "season"),
                    "--diagnostic-output", str(root / "season-blocked.json"),
                ]), 0)

    def test_grade_commands_require_the_frozen_runtime_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diagnostic = root / "blocked.json"
            with (
                patch.object(
                    prospective, "load_game_lock",
                    return_value={"lock": {"code_sha": "a" * 40}},
                ),
                patch.object(prospective, "_current_code_sha", return_value="b" * 40),
                patch.object(prospective, "grade_week") as grade_week,
            ):
                self.assertEqual(prospective.main([
                    "grade-week", "--lock", str(root / "lock.json"),
                    "--results", str(root / "results.json"),
                    "--output-dir", str(root / "week"),
                    "--diagnostic-output", str(diagnostic),
                ]), 1)
            grade_week.assert_not_called()
            self.assertIn("runtime code", json.loads(diagnostic.read_text())["error"])
            diagnostic.unlink()
            with (
                patch.object(
                    prospective, "load_week_grade", return_value={"code_sha": "a" * 40}
                ),
                patch.object(
                    prospective, "_current_code_sha",
                    side_effect=ValueError("Prospective fantasy runtime code is not clean"),
                ),
                patch.object(prospective, "grade_season") as grade_season,
            ):
                self.assertEqual(prospective.main([
                    "grade-season", "--week-grade", str(root / "week.json"),
                    "--leakage-audit", str(root / "audit.json"),
                    "--output-dir", str(root / "season"),
                    "--diagnostic-output", str(diagnostic),
                ]), 1)
            grade_season.assert_not_called()

    def test_code_sha_requires_a_clean_tracked_runtime_and_wraps_git_errors(self):
        head = prospective.subprocess.CompletedProcess(
            (), 0, stdout="a" * 40 + "\n", stderr=""
        )
        clean = prospective.subprocess.CompletedProcess((), 0, stdout="", stderr="")
        tracked = prospective.subprocess.CompletedProcess(
            (), 0, stdout="\n".join(prospective.CODE_PATHS) + "\n", stderr=""
        )
        dirty = prospective.subprocess.CompletedProcess(
            (), 0, stdout=" M pgo_fantasy.py\n", stderr=""
        )
        self.assertEqual(prospective.CODE_PATHS, (
            "pgo_fantasy_prospective.py", "pgo_fantasy.py", "pgo_prospective.py",
            "pgo_challenger.py", "pgo_sources.py", "pgo_model.py",
            "release_ratings.py",
        ))
        with patch.object(
            prospective.subprocess, "run", side_effect=(head, clean, tracked)
        ):
            self.assertEqual(prospective._current_code_sha(), "a" * 40)
        with patch.object(
            prospective.subprocess, "run", side_effect=(head, dirty)
        ):
            with self.assertRaisesRegex(ValueError, "not clean"):
                prospective._current_code_sha()
        for path in ("pgo_model.py", "release_ratings.py"):
            for status in (f" M {path}\n", f"?? {path}\n"):
                changed = prospective.subprocess.CompletedProcess(
                    (), 0, stdout=status, stderr=""
                )
                with self.subTest(path=path, status=status), patch.object(
                    prospective.subprocess, "run", side_effect=(head, changed)
                ):
                    with self.assertRaisesRegex(ValueError, "not clean"):
                        prospective._current_code_sha()
        with patch.object(
            prospective.subprocess, "run",
            side_effect=subprocess.CalledProcessError(1, ("git",)),
        ):
            with self.assertRaisesRegex(ValueError, "identity"):
                prospective._current_code_sha()

    def test_cli_help_lists_only_four_local_operations(self):
        with self.assertRaises(SystemExit) as caught:
            prospective.main(["--help"])
        self.assertEqual(caught.exception.code, 0)
