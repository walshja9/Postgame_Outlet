import hashlib
import csv
import json
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pgo_prospective
import pgo_model
import pgo_sources


AS_OF = "2026-08-20T12:00:00-04:00"


def _sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ProspectiveLockTests(unittest.TestCase):
    def setUp(self):
        self.schedule = {
            "sha256": _sha256("synthetic-2026-schedule-v1"),
            "rows": [
                {
                    "game_id": "2026_01_NYJ_BUF",
                    "season": 2026,
                    "week": 1,
                    "game_type": "REG",
                    "kickoff": "2026-09-13T13:00:00-04:00",
                    "home_team": "BUF",
                    "away_team": "NYJ",
                    "home_rest": 7,
                    "away_rest": 7,
                    "location": "Home",
                    "home_score": "",
                    "away_score": "",
                },
                {
                    "game_id": "2026_01_MIA_NE",
                    "season": 2026,
                    "week": 1,
                    "game_type": "REG",
                    "kickoff": "2026-09-13T16:25:00-04:00",
                    "home_team": "NE",
                    "away_team": "MIA",
                    "home_rest": 7,
                    "away_rest": 7,
                    "location": "Home",
                    "home_score": "",
                    "away_score": "",
                },
            ],
        }
        self.model_state = {
            "source_lock_sha256": _sha256("frozen-pgo-sources"),
            "source_hashes": {"schedule_results": _sha256("historical-games")},
            "challenger": {"feature_names": ["home_field"], "coefficients": [1.0]},
            "pgo_v0": {"parameters": {"learning_rate": 0.15}},
            "predictions": {
                "2026_01_NYJ_BUF": {
                    "pgo_v0_prediction": 4.0,
                    "challenger_prediction": 2.0,
                    "challenger_full_strength_prediction": 2.5,
                    "subgroup_flags": {"weeks_1_4": True},
                },
                "2026_01_MIA_NE": {
                    "pgo_v0_prediction": -8.0,
                    "challenger_prediction": -3.0,
                    "challenger_full_strength_prediction": -2.5,
                    "subgroup_flags": {"weeks_1_4": True},
                },
            },
        }

    def test_lock_is_deterministic_and_pregame_only(self):
        first = pgo_prospective.lock_games(self.schedule, self.model_state, AS_OF)
        second = pgo_prospective.lock_games(self.schedule, self.model_state, AS_OF)

        self.assertEqual(
            pgo_prospective.serialize_lock(first), pgo_prospective.serialize_lock(second)
        )
        self.assertEqual(first["status"], "LOCKED")
        self.assertEqual(first["schedule_snapshot_sha256"], self.schedule["sha256"])
        self.assertEqual(first["source_lock_sha256"], self.model_state["source_lock_sha256"])
        self.assertEqual(len(first["games"]), 2)
        self.assertTrue(
            {
                "game_id", "season", "week", "kickoff", "home", "away",
                "game_type", "location", "home_rest", "away_rest",
                "pgo_v0_prediction", "challenger_prediction",
                "challenger_full_strength_prediction", "subgroup_flags",
            }.issubset(first["games"][0])
        )
        self.assertEqual(first["games"][0]["game_type"], "REG")
        self.assertEqual(first["games"][0]["location"], "Home")
        self.assertEqual(first["games"][0]["home_rest"], 7)
        self.assertEqual(first["games"][0]["away_rest"], 7)
        self.assertNotIn("actual_margin", first["games"][0])

    def test_lock_skips_completed_2026_rows_before_boundary(self):
        schedule = deepcopy(self.schedule)
        schedule["rows"].append({
            "game_id": "2026_00_BUF_NYJ", "season": 2026, "week": 0,
            "game_type": "REG", "kickoff": "2026-08-19T13:00:00-04:00",
            "home_team": "BUF", "away_team": "NYJ", "home_rest": 7,
            "away_rest": 7, "location": "Home", "home_score": "24",
            "away_score": "17",
        })
        lock = pgo_prospective.lock_games(schedule, self.model_state, AS_OF)
        self.assertEqual([row["game_id"] for row in lock["games"]], [
            "2026_01_NYJ_BUF", "2026_01_MIA_NE",
        ])

    def test_lock_rejects_invalid_pregame_rows(self):
        cases = []
        duplicate = deepcopy(self.schedule)
        duplicate["rows"].append(deepcopy(duplicate["rows"][0]))
        cases.append((duplicate, self.model_state, "Duplicate game ID:"))

        final_score = deepcopy(self.schedule)
        final_score["rows"][0]["home_score"] = "24"
        cases.append((final_score, self.model_state, "Final score present:"))

        missing_kickoff = deepcopy(self.schedule)
        missing_kickoff["rows"][0]["kickoff"] = ""
        cases.append((missing_kickoff, self.model_state, "Missing kickoff:"))

        boundary_kickoff = deepcopy(self.schedule)
        boundary_kickoff["rows"][0]["kickoff"] = AS_OF
        cases.append((boundary_kickoff, self.model_state, "Kickoff is not after lock boundary:"))

        non_finite = deepcopy(self.model_state)
        non_finite["predictions"]["2026_01_NYJ_BUF"]["challenger_prediction"] = math.nan
        cases.append((self.schedule, non_finite, "Non-finite prediction:"))

        post_kickoff_revision = deepcopy(self.model_state)
        post_kickoff_revision["source_revisions"] = [
            {
                "source": "injury_reports",
                "game_id": "2026_01_NYJ_BUF",
                "available_at": "2026-09-13T13:01:00-04:00",
                "sha256": _sha256("late-injury-revision"),
            }
        ]
        cases.append((self.schedule, post_kickoff_revision, "Post-kickoff source revision:"))

        missing_venue = deepcopy(self.schedule)
        missing_venue["rows"][0]["location"] = ""
        cases.append((missing_venue, self.model_state, "Missing venue:"))

        malformed_flags = deepcopy(self.model_state)
        malformed_flags["predictions"]["2026_01_NYJ_BUF"]["subgroup_flags"] = {
            "weeks_1_4": "false"
        }
        cases.append((self.schedule, malformed_flags, "Invalid subgroup flags:"))

        for schedule, state, prefix in cases:
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, f"^{prefix}"):
                pgo_prospective.lock_games(schedule, state, AS_OF)


class ProspectiveGradeTests(unittest.TestCase):
    def setUp(self):
        lock_tests = ProspectiveLockTests()
        lock_tests.setUp()
        self.lock = pgo_prospective.lock_games(
            lock_tests.schedule, lock_tests.model_state, AS_OF
        )
        self.results = [
            {
                "game_id": "2026_01_NYJ_BUF",
                "home_team": "BUF",
                "away_team": "NYJ",
                "kickoff": "2026-09-13T13:00:00-04:00",
                "game_type": "REG",
                "home_score": "24",
                "away_score": "21",
                "finalized_at": "2026-09-13T17:00:00-04:00",
            },
            {
                "game_id": "2026_01_MIA_NE",
                "home_team": "NE",
                "away_team": "MIA",
                "kickoff": "2026-09-13T16:25:00-04:00",
                "game_type": "REG",
                "home_score": "17",
                "away_score": "21",
                "finalized_at": "2026-09-13T20:00:00-04:00",
            },
        ]

    def test_grade_reports_locked_metrics_and_status(self):
        receipt = pgo_prospective.grade_locked_games(self.lock, self.results)

        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["publication_status"], "VALIDATED")
        self.assertEqual(receipt["counts"]["locked_games"], 2)
        self.assertAlmostEqual(receipt["metrics"]["challenger_mae"], 1.0)
        self.assertAlmostEqual(receipt["metrics"]["pgo_v0_mae"], 2.5)
        self.assertEqual(receipt["bootstrap"]["samples"], 10_000)
        self.assertEqual(receipt["bootstrap"]["seed"], 20260721)
        self.assertEqual([row["actual_margin"] for row in receipt["rows"]], [3.0, -4.0])

    def test_grade_holds_when_statistical_gates_fail(self):
        results = [
            {**self.results[0], "home_score": "14", "away_score": "10"},
            {**self.results[1], "home_score": "17", "away_score": "25"},
        ]
        receipt = pgo_prospective.grade_locked_games(self.lock, results)
        self.assertEqual(receipt["status"], "HOLD")
        self.assertEqual(receipt["publication_status"], "EXPERIMENTAL")
        self.assertIn("challenger_mae_lower", receipt["failed_checks"])
        self.assertIn("aggregate_improvement_ci_positive", receipt["failed_checks"])

    def test_grade_serialization_is_deterministic(self):
        receipt = pgo_prospective.grade_locked_games(self.lock, self.results)
        first = pgo_prospective.serialize_grade(receipt, receipt["rows"])
        second = pgo_prospective.serialize_grade(receipt, receipt["rows"])
        self.assertEqual(first, second)

    def test_grade_rejects_tampered_or_incomplete_results(self):
        cases = []
        cases.append((self.results[:1], "Missing locked result:"))
        extra = self.results + [{**self.results[0], "game_id": "unexpected"}]
        cases.append((extra, "Unexpected result:"))
        duplicate = self.results + [deepcopy(self.results[0])]
        cases.append((duplicate, "Duplicate result:"))
        changed_team = [{**self.results[0], "home_team": "NYJ"}, self.results[1]]
        cases.append((changed_team, "locked home team:"))
        changed_kickoff = [{**self.results[0], "kickoff": "2026-09-13T13:01:00-04:00"}, self.results[1]]
        cases.append((changed_kickoff, "locked kickoff:"))
        changed_game_type = [{**self.results[0], "game_type": "POST"}, self.results[1]]
        cases.append((changed_game_type, "locked game type:"))
        missing_kickoff = [{key: value for key, value in self.results[0].items() if key != "kickoff"}, self.results[1]]
        cases.append((missing_kickoff, "Missing result kickoff:"))
        missing_game_type = [{key: value for key, value in self.results[0].items() if key != "game_type"}, self.results[1]]
        cases.append((missing_game_type, "Missing result game type:"))
        non_final = [{**self.results[0], "finalized_at": ""}, self.results[1]]
        cases.append((non_final, "Result not finalized:"))

        for results, prefix in cases:
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, f"^{prefix}"):
                pgo_prospective.grade_locked_games(self.lock, results)

    def test_cli_writes_blocked_receipt_on_integrity_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock_path = pgo_prospective.write_lock(root / "lock", self.lock)
            results_path = root / "results.csv"
            results_path.write_text(
                "game_id,home_team,away_team,home_score,away_score,finalized_at\n"
                "2026_01_NYJ_BUF,BUF,NYJ,24,21,2026-09-13T17:00:00-04:00\n",
                encoding="utf-8",
            )
            output_dir = root / "grade"
            args = SimpleNamespace(
                lock_file=lock_path, results_path=results_path, output_dir=output_dir,
            )
            self.assertEqual(pgo_prospective._cli_grade(args), 1)
            receipt = json.loads((output_dir / "prospective_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertEqual(receipt["publication_status"], "BLOCKED")

    def test_grade_rejects_tampered_lock_prediction_and_hash(self):
        changed_prediction = deepcopy(self.lock)
        changed_prediction["games"][0]["challenger_prediction"] = 99.0
        with self.assertRaisesRegex(ValueError, "^Locked prediction integrity:"):
            pgo_prospective.grade_locked_games(changed_prediction, self.results)

        changed_hash = deepcopy(self.lock)
        changed_hash["artifact_sha256"] = _sha256("tampered-lock-artifact")
        with self.assertRaisesRegex(ValueError, "^Lock artifact hash mismatch:"):
            pgo_prospective.grade_locked_games(changed_hash, self.results)


class ProspectiveArtifactSafetyTests(unittest.TestCase):
    protected_paths = (
        Path("research/pgo_v1/backtest.json"),
        Path("research/pgo_v1/ratings_2026_preseason.csv"),
        Path("research/pgo_v1/validation_predictions.csv"),
        Path("research/pgo_v1/source_audit.json"),
        Path("docs/index.html"),
    )

    def test_serialization_does_not_modify_protected_artifacts(self):
        grade_tests = ProspectiveGradeTests()
        grade_tests.setUp()
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.protected_paths
        }

        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            lock_path = pgo_prospective.write_lock(output_dir, grade_tests.lock)
            receipt = pgo_prospective.grade_locked_games(grade_tests.lock, grade_tests.results)
            grade_path = pgo_prospective.write_grade(output_dir, receipt, receipt["rows"])
            self.assertTrue(lock_path.is_file())
            self.assertTrue(grade_path.is_file())

        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.protected_paths
        }
        self.assertEqual(before, after)


class ProspectiveFitTests(unittest.TestCase):
    def test_turnover_cutoff_is_scoped_to_future_block(self):
        historical = [pgo_prospective.pgo_challenger.FeatureRow(
            "old", 2025, 18, "2025-12-28T13:00:00-05:00", 0.0, {}, {}
        )]
        historical_metadata = {
            "old": {
                "home_team": "HOU", "away_team": "IND",
                "home_returning_snap_share": 0.9,
                "away_returning_snap_share": 0.9,
            }
        }
        future = [
            pgo_prospective.pgo_challenger.FeatureRow(
                "f1", 2026, 1, "2026-09-13T13:00:00-04:00", 0.0, {}, {}
            ),
            pgo_prospective.pgo_challenger.FeatureRow(
                "f2", 2026, 2, "2026-09-20T13:00:00-04:00", 0.0, {}, {}
            ),
        ]
        future_metadata = {
            "f1": {
                "home_team": "BUF", "away_team": "NYJ",
                "home_returning_snap_share": 0.2,
                "away_returning_snap_share": 0.3,
            },
            "f2": {
                "home_team": "MIA", "away_team": "NE",
                "home_returning_snap_share": 0.4,
                "away_returning_snap_share": 0.5,
            },
        }
        flags = pgo_prospective._prospective_turnover_flags(
            historical, historical_metadata, future, future_metadata
        )
        self.assertEqual(flags, {"f1": True, "f2": False})

    def test_v0_ratings_apply_2026_offseason_retention(self):
        with tempfile.TemporaryDirectory() as temp:
            schedule = Path(temp, "schedule.csv")
            with schedule.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=pgo_sources.SCHEDULE_COLUMNS)
                writer.writeheader()
                writer.writerow({
                    "game_id": "g2025", "season": 2025, "week": 18,
                    "game_type": "REG", "gameday": "2025-12-28",
                    "gametime": "13:00", "away_team": "NYJ", "home_team": "BUF",
                    "away_score": 10, "home_score": 20, "location": "Home",
                    "away_rest": 7, "home_rest": 7, "away_coach": "a",
                    "home_coach": "h",
                })
            parameters = pgo_model.Parameters(0.3, 0.9, 3.0, 20.0)
            with (
                patch.object(pgo_model, "select_parameters", return_value=parameters),
                patch.object(pgo_model, "walk_forward", return_value=([], {"BUF": 10.0, "NYJ": -2.0})),
            ):
                _, ratings = pgo_prospective._fit_v0_state({("schedule_results", None): schedule})
        self.assertAlmostEqual(ratings["BUF"], 9.0)
        self.assertAlmostEqual(ratings["NYJ"], -1.8)

    def test_fit_uses_both_full_views_coach_flag_and_turnover_helper(self):
        parameters = pgo_prospective.pgo_challenger.ChallengerParameters(2, 1.0, 1.0)
        historical_row = pgo_prospective.pgo_challenger.FeatureRow(
            "old", 2025, 18, "2025-12-28T13:00:00-05:00", 0.0, {"value": 0.0}, {}
        )
        context = {
            "evaluation_metadata": {},
            "coaches": {"BUF": "old coach", "NYJ": "same coach"},
            "prior_starter": {"BUF": "old starter", "NYJ": "same starter"},
        }
        inputs = {}
        schedule = [{
            "game_id": "future", "season": 2026, "week": 1,
            "game_type": "REG", "kickoff": "2026-09-13T13:00:00-04:00",
            "home_team": "BUF", "away_team": "NYJ", "location": "Home",
            "home_rest": 7, "away_rest": 7, "home_coach": "new coach",
            "away_coach": "same coach",
        }, {
            "game_id": "completed", "season": 2026, "week": 0,
            "game_type": "REG", "kickoff": "2026-08-19T13:00:00-04:00",
            "home_team": "BUF", "away_team": "NYJ", "location": "Home",
            "home_rest": 7, "away_rest": 7, "home_coach": "old coach",
            "away_coach": "same coach", "home_score": "24", "away_score": "17",
        }]
        states = {
            "BUF": ({"value": 10.0}, {"value": 1.0, "qb_current_minus_full": 0.0}),
            "NYJ": ({"value": 20.0}, {"value": 2.0, "qb_current_minus_full": 0.0}),
        }
        metadata = {
            "BUF": {"returning_snap_share": 0.8, "starter": "new starter"},
            "NYJ": {"returning_snap_share": 0.8, "starter": "same starter"},
        }

        class Preprocessor:
            feature_names = ("value",)
            missing_features = ()
            medians = np.array([0.0])
            scales = np.array([1.0])

            def transform(self, rows):
                return np.array([[row.features["value"]] for row in rows], dtype=float)

        def feature_difference(home, away, game):
            return {"value": home["value"] + away["value"]}

        with (
            patch.object(pgo_prospective.pgo_challenger, "select_parameters", return_value=parameters),
            patch.object(pgo_prospective.pgo_challenger, "_walk", side_effect=[
                ([historical_row], context, inputs), ([], context, inputs)
            ]),
            patch.object(pgo_prospective.pgo_challenger, "fit_preprocessor", return_value=Preprocessor()),
            patch.object(pgo_prospective.pgo_challenger, "fit_huber_ridge", return_value=np.array([0.0, 1.0])),
            patch.object(pgo_prospective.pgo_challenger, "predict", side_effect=lambda x, _: x[:, 0]),
            patch.object(pgo_prospective.pgo_challenger, "_matchup_features", side_effect=feature_difference),
            patch.object(pgo_prospective, "_snapshot_states_with_schedule", return_value=(states, metadata)),
            patch.object(pgo_prospective, "_fit_v0_state", return_value=(pgo_model.Parameters(0.3, 0.9, 3.0, 20.0), {"BUF": 1.0, "NYJ": -1.0})),
            patch.object(pgo_prospective, "_prospective_turnover_flags", return_value={"future": True}) as turnover,
        ):
            state = pgo_prospective.fit_model_state({}, AS_OF, schedule)

        prediction = state["predictions"]["future"]
        self.assertEqual(prediction["challenger_prediction"], 3.0)
        self.assertEqual(prediction["challenger_full_strength_prediction"], 30.0)
        self.assertTrue(prediction["subgroup_flags"]["changed_or_backup_qb"])
        self.assertTrue(prediction["subgroup_flags"]["head_coach_change"])
        self.assertTrue(prediction["subgroup_flags"]["high_roster_turnover"])
        turnover.assert_called_once()
        self.assertEqual(len(turnover.call_args.args[2]), 1)

    def test_cli_validates_manifest_before_model_fit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            schedule_path = root / "schedule.csv"
            with schedule_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=pgo_sources.SCHEDULE_COLUMNS)
                writer.writeheader()
                writer.writerow({
                    "game_id": "future", "season": 2026, "week": 1,
                    "game_type": "REG", "gameday": "2026-09-13",
                    "gametime": "13:00", "away_team": "NYJ", "home_team": "BUF",
                    "away_score": "", "home_score": "", "location": "Home",
                    "away_rest": 7, "home_rest": 7, "away_coach": "a",
                    "home_coach": "h",
                })
            lock_path = root / "sources.lock.json"
            lock_path.write_text('{"sources": []}\n', encoding="utf-8")
            args = SimpleNamespace(
                schedule_snapshot=schedule_path, lock_path=lock_path,
                cache_dir=root / "cache", as_of=AS_OF, output_dir=root / "out",
            )
            with (
                patch.object(pgo_sources, "load_locked_sources", return_value={}),
                patch.object(pgo_prospective.pgo_challenger, "_source_preflight", side_effect=ValueError("frozen_at boundary")),
                patch.object(pgo_prospective, "fit_model_state") as fit,
                self.assertRaisesRegex(ValueError, "frozen_at boundary"),
            ):
                pgo_prospective._cli_lock(args)
            fit.assert_not_called()
