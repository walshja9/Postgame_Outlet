import hashlib
import json
import math
import tempfile
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
