import hashlib
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import pgo_prospective


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
        non_final = [{**self.results[0], "finalized_at": ""}, self.results[1]]
        cases.append((non_final, "Result not finalized:"))

        for results, prefix in cases:
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, f"^{prefix}"):
                pgo_prospective.grade_locked_games(self.lock, results)

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
