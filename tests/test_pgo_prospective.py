import hashlib
import csv
import json
import math
import os
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

    def test_cli_canonicalizes_blocked_receipt_for_untrusted_lock_json(self):
        cases = {
            "array": "[]",
            "schema-two-nan": (
                '{"schema_version":2,"candidate":{"kind":"'
                + pgo_prospective.BLEND_KIND
                + '"},"source_hashes":{"bad":NaN}}'
            ),
            "schema-one-nan": (
                '{"schema_version":1,"source_hashes":{"bad":NaN}}'
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            results_path = root / "results.csv"
            results_path.write_text("game_id\n", encoding="utf-8")
            for name, payload in cases.items():
                with self.subTest(name=name):
                    lock_path = root / f"{name}.json"
                    lock_path.write_text(payload, encoding="utf-8")
                    output_dir = root / name

                    result = pgo_prospective.main([
                        "grade", "--lock-file", str(lock_path),
                        "--results-path", str(results_path),
                        "--output-dir", str(output_dir),
                    ])

                    receipt_text = (
                        output_dir / "prospective_receipt.json"
                    ).read_text(encoding="utf-8")
                    receipt = json.loads(receipt_text)
                    self.assertEqual(result, 1)
                    self.assertEqual(receipt["status"], "BLOCKED")
                    self.assertEqual(receipt["schema_version"], 1)
                    self.assertEqual(receipt["source_hashes"], {})
                    self.assertNotIn("NaN", receipt_text)
                    self.assertEqual(
                        receipt_text, pgo_prospective._canonical(receipt) + "\n"
                    )

    def test_grade_rejects_tampered_lock_prediction_and_hash(self):
        changed_prediction = deepcopy(self.lock)
        changed_prediction["games"][0]["challenger_prediction"] = 99.0
        with self.assertRaisesRegex(ValueError, "^Locked prediction integrity:"):
            pgo_prospective.grade_locked_games(changed_prediction, self.results)

        changed_hash = deepcopy(self.lock)
        changed_hash["artifact_sha256"] = _sha256("tampered-lock-artifact")
        with self.assertRaisesRegex(ValueError, "^Lock artifact hash mismatch:"):
            pgo_prospective.grade_locked_games(changed_hash, self.results)


class ProspectiveBlendGradeTests(unittest.TestCase):
    development_path = Path("research/pgo_stability_blend/development.json")

    def setUp(self):
        lock_tests = ProspectiveLockTests()
        lock_tests.setUp()
        base = pgo_prospective.lock_games(
            lock_tests.schedule, lock_tests.model_state, AS_OF
        )
        development_bytes = self.development_path.read_bytes()
        self.lock = pgo_prospective.derive_stability_blend(
            base, json.loads(development_bytes), hashlib.sha256(development_bytes).hexdigest(),
            "2026-08-21T12:00:00-04:00",
        )
        self.lock_bytes = pgo_prospective.serialize_lock(self.lock).encode("utf-8")
        self.attestation = pgo_prospective.build_prospective_attestation(
            base,
            pgo_prospective.serialize_lock(base).encode("utf-8"),
            pgo_prospective._prediction_csv(base).encode("utf-8"),
            self.lock,
            self.lock_bytes,
            pgo_prospective._prediction_csv(self.lock).encode("utf-8"),
            development_bytes,
        )
        self.results = [
            {
                "game_id": "2026_01_NYJ_BUF", "home_team": "BUF", "away_team": "NYJ",
                "kickoff": "2026-09-13T13:00:00-04:00", "game_type": "REG",
                "home_score": "24", "away_score": "21",
                "finalized_at": "2026-09-13T17:00:00-04:00",
            },
            {
                "game_id": "2026_01_MIA_NE", "home_team": "NE", "away_team": "MIA",
                "kickoff": "2026-09-13T16:25:00-04:00", "game_type": "REG",
                "home_score": "17", "away_score": "21",
                "finalized_at": "2026-09-13T20:00:00-04:00",
            },
        ]

    def _write_inputs(self, root, results):
        lock_path = pgo_prospective.write_lock(root / "lock", self.lock)
        attestation_path = root / "attestation.json"
        attestation_path.write_text(
            pgo_prospective._canonical(self.attestation) + "\n", encoding="utf-8"
        )
        results_path = root / "results.csv"
        columns = tuple(sorted({key for row in results for key in row}))
        with results_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(results)
        return lock_path, results_path, attestation_path

    def test_candidate_grade_reports_metrics_and_status(self):
        receipt = pgo_prospective.grade_locked_games(
            self.lock,
            self.results,
            attestation=self.attestation,
            lock_bytes=self.lock_bytes,
        )

        self.assertAlmostEqual(receipt["metrics"]["pgo_v0_mae"], 2.5)
        self.assertAlmostEqual(receipt["metrics"]["challenger_mae"], 1.0)
        self.assertAlmostEqual(receipt["metrics"]["candidate_mae"], 1.625)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["publication_status"], "VALIDATED")
        self.assertEqual(receipt["bootstrap"]["samples"], 10_000)
        self.assertEqual(receipt["bootstrap"]["seed"], 20260721)
        self.assertEqual(receipt["candidate_vs_challenger_interval"], {
            "mean": -0.625, "lower": -0.625, "upper": -0.625,
            "samples": 10_000, "seed": 20260721,
        })
        self.assertEqual(receipt["subgroup_results"]["weeks_1_4"], {
            "status": "INSUFFICIENT_EVIDENCE", "count": 2,
        })
        self.assertTrue(receipt["checks"]["no_sufficient_subgroup_regression"])

    def test_candidate_holds_for_sufficient_subgroup_regression(self):
        subgroups = {
            name: {"status": "INSUFFICIENT_EVIDENCE", "count": 0}
            for name in pgo_prospective.pgo_challenger.SUBGROUPS
        }
        subgroups["weeks_1_4"] = {
            "status": "SUFFICIENT_EVIDENCE",
            "count": 100,
            "pgo_v0_mae": 2.0,
            "challenger_mae": 3.0,
            "improvement": -1.0,
            "lower": -1.5,
            "upper": -0.5,
        }

        with patch.object(
            pgo_prospective.pgo_challenger,
            "subgroup_results",
            return_value=subgroups,
        ):
            receipt = pgo_prospective.grade_locked_games(
                self.lock,
                self.results,
                attestation=self.attestation,
                lock_bytes=self.lock_bytes,
            )

        self.assertFalse(receipt["checks"]["no_sufficient_subgroup_regression"])
        self.assertEqual(receipt["status"], "HOLD")

    def test_candidate_grade_requires_external_attestation_and_exact_lock_bytes(self):
        for attestation, lock_bytes in ((None, None), (self.attestation, b"{}")):
            with self.subTest(lock_bytes=lock_bytes), self.assertRaisesRegex(
                ValueError, "[Aa]ttestation"
            ):
                pgo_prospective.grade_locked_games(
                    self.lock,
                    self.results,
                    attestation=attestation,
                    lock_bytes=lock_bytes,
                )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock_path, results_path, _ = self._write_inputs(root, self.results)
            output_dir = root / "grade"
            self.assertEqual(pgo_prospective.main([
                "grade", "--lock-file", str(lock_path), "--results-path",
                str(results_path), "--output-dir", str(output_dir),
            ]), 1)
            receipt = json.loads((output_dir / "prospective_receipt.json").read_text())
            self.assertEqual(receipt["status"], "BLOCKED")

    def test_candidate_grade_rejects_coordinated_development_rehash(self):
        changed = deepcopy(self.lock)
        changed["candidate"]["development_receipt_sha256"] = _sha256("other development")
        changed["artifact_sha256"] = pgo_prospective._artifact_hash(changed)
        pgo_prospective._verify_lock(changed)

        with self.assertRaisesRegex(ValueError, "attestation"):
            pgo_prospective.grade_locked_games(
                changed,
                self.results,
                attestation=self.attestation,
                lock_bytes=pgo_prospective.serialize_lock(changed).encode("utf-8"),
            )

    def test_candidate_grade_rejects_coordinated_base_candidate_rehash(self):
        changed = deepcopy(self.lock)
        game = changed["games"][0]
        game["pgo_v0_prediction"] += 1.0
        game["challenger_prediction"] += 1.0
        game["candidate_prediction"] = pgo_prospective._blend_prediction(
            game["pgo_v0_prediction"], game["challenger_prediction"]
        )
        base = pgo_prospective._base_lock_from_derived(changed)
        base["prediction_integrity_sha256"] = pgo_prospective._prediction_integrity_hash(
            base["games"]
        )
        base["artifact_sha256"] = pgo_prospective._artifact_hash(base)
        changed["base_prediction_integrity_sha256"] = base["prediction_integrity_sha256"]
        changed["base_lock_artifact_sha256"] = base["artifact_sha256"]
        changed["prediction_integrity_sha256"] = pgo_prospective._prediction_integrity_hash(
            changed["games"], include_candidate=True
        )
        changed["artifact_sha256"] = pgo_prospective._artifact_hash(changed)
        pgo_prospective._verify_lock(changed)

        with self.assertRaisesRegex(ValueError, "attestation"):
            pgo_prospective.grade_locked_games(
                changed,
                self.results,
                attestation=self.attestation,
                lock_bytes=pgo_prospective.serialize_lock(changed).encode("utf-8"),
            )

    def test_candidate_holds_when_v0_is_perfect(self):
        results = [
            {**self.results[0], "home_score": "24", "away_score": "20"},
            {**self.results[1], "home_score": "17", "away_score": "25"},
        ]
        receipt = pgo_prospective.grade_locked_games(
            self.lock,
            results,
            attestation=self.attestation,
            lock_bytes=self.lock_bytes,
        )

        self.assertEqual(receipt["status"], "HOLD")
        self.assertIn("candidate_mae_lower", receipt["failed_checks"])

    def test_candidate_cli_blocks_missing_cancelled_and_changed_kickoff_results(self):
        cases = (
            self.results[:1],
            [{**self.results[0], "status": "CANCELLED"}, self.results[1]],
            [{**self.results[0], "kickoff": "2026-09-13T13:01:00-04:00"}, self.results[1]],
        )
        for results in cases:
            with self.subTest(results=results):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    lock_path, results_path, attestation_path = self._write_inputs(root, results)
                    output_dir = root / "grade"
                    self.assertEqual(pgo_prospective.main([
                        "grade", "--lock-file", str(lock_path), "--results-path",
                        str(results_path), "--attestation-file", str(attestation_path),
                        "--output-dir", str(output_dir),
                    ]), 1)
                    receipt = json.loads((output_dir / "prospective_receipt.json").read_text())
                    self.assertEqual(receipt["status"], "BLOCKED")
                    self.assertIn("candidate_mae_lower", receipt["checks"])

    def test_candidate_grade_rejects_prediction_hash_and_formula_tampering(self):
        prediction = deepcopy(self.lock)
        prediction["games"][0]["candidate_prediction"] = 99.0
        prediction["prediction_integrity_sha256"] = pgo_prospective._prediction_integrity_hash(
            prediction["games"], include_candidate=True
        )
        prediction["artifact_sha256"] = pgo_prospective._artifact_hash(prediction)
        changed_hash = deepcopy(self.lock)
        changed_hash["artifact_sha256"] = _sha256("tampered-lock-artifact")
        formula = deepcopy(self.lock)
        formula["candidate"]["formula"] = "other"
        formula["artifact_sha256"] = pgo_prospective._artifact_hash(formula)
        for lock in (prediction, changed_hash, formula):
            with self.subTest(lock=lock["artifact_sha256"]), self.assertRaises(ValueError):
                pgo_prospective.grade_locked_games(
                    lock,
                    self.results,
                    attestation=self.attestation,
                    lock_bytes=pgo_prospective.serialize_lock(lock).encode("utf-8"),
                )

    def test_candidate_grade_rejects_invalid_result_rows(self):
        with self.assertRaisesRegex(ValueError, "^Invalid result row:"):
            pgo_prospective.grade_locked_games(
                self.lock,
                [None],
                attestation=self.attestation,
                lock_bytes=self.lock_bytes,
            )

    def test_candidate_grade_serialization_is_deterministic(self):
        receipt = pgo_prospective.grade_locked_games(
            self.lock,
            self.results,
            attestation=self.attestation,
            lock_bytes=self.lock_bytes,
        )

        first = pgo_prospective.serialize_grade(receipt, receipt["rows"])
        self.assertEqual(first, pgo_prospective.serialize_grade(receipt, receipt["rows"]))
        self.assertEqual(first[1].splitlines()[0].split(",")[-3:], [
            "candidate_absolute_error", "candidate_improvement_vs_pgo_v0",
            "candidate_improvement_vs_challenger",
        ])

    def test_main_grade_returns_pass_hold_and_blocked(self):
        cases = (
            (self.results, 0),
            ([
                {**self.results[0], "home_score": "24", "away_score": "20"},
                {**self.results[1], "home_score": "17", "away_score": "25"},
            ], 1),
            (self.results[:1], 1),
        )
        for results, expected in cases:
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    lock_path, results_path, attestation_path = self._write_inputs(root, results)
                    self.assertEqual(pgo_prospective.main([
                        "grade", "--lock-file", str(lock_path), "--results-path",
                        str(results_path), "--attestation-file", str(attestation_path),
                        "--output-dir", str(root / "grade"),
                    ]), expected)


class ProspectiveBlendLockTests(unittest.TestCase):
    development_path = Path("research/pgo_stability_blend/development.json")

    def setUp(self):
        lock_tests = ProspectiveLockTests()
        lock_tests.setUp()
        self.base_lock = pgo_prospective.lock_games(
            lock_tests.schedule, lock_tests.model_state, AS_OF
        )
        self.original_base_lock = deepcopy(self.base_lock)
        self.development_receipt_bytes = self.development_path.read_bytes()
        self.development_receipt = json.loads(self.development_receipt_bytes)
        self.development_file_sha256 = hashlib.sha256(
            self.development_receipt_bytes
        ).hexdigest()
        self.as_of = "2026-08-21T12:00:00-04:00"

    def _derived(self):
        return pgo_prospective.derive_stability_blend(
            self.base_lock, self.development_receipt,
            self.development_file_sha256, self.as_of,
        )

    def _rehash(self, lock):
        lock["prediction_integrity_sha256"] = pgo_prospective._prediction_integrity_hash(
            lock["games"], include_candidate=True
        )
        lock["artifact_sha256"] = pgo_prospective._artifact_hash(lock)

    def _cli_args(self, root, name):
        base_lock = root / "base.json"
        base_predictions = root / "base.csv"
        receipt = root / "development.json"
        base_lock.write_bytes(
            pgo_prospective.serialize_lock(self.base_lock).encode("utf-8")
        )
        base_predictions.write_text(
            pgo_prospective._prediction_csv(self.base_lock),
            encoding="utf-8",
            newline="",
        )
        receipt.write_bytes(self.development_receipt_bytes)
        return SimpleNamespace(
            base_lock=base_lock,
            base_predictions=base_predictions,
            development_receipt=receipt,
            as_of=self.as_of,
            output_dir=root / f"derived-{name}",
            attestation_output=root / f"attestation-{name}.json",
        )

    def test_derives_reconstructable_candidate_lock_without_mutating_base(self):
        derived = self._derived()
        self.assertEqual(derived["schema_version"], 2)
        self.assertEqual(
            [game["candidate_prediction"] for game in derived["games"]],
            [3.5, -6.75],
        )
        self.assertEqual(
            pgo_prospective._base_lock_from_derived(derived), self.base_lock
        )
        self.assertEqual(self.base_lock, self.original_base_lock)
        self.assertEqual(
            pgo_prospective._prediction_csv(derived).splitlines()[0].split(",")[-1],
            "candidate_prediction",
        )

    def test_lock_validation_fails_closed_for_schema_and_candidate_tampering(self):
        top_level = deepcopy(self.base_lock)
        top_level["candidate"] = {}
        game_level = deepcopy(self.base_lock)
        game_level["games"][0]["candidate_prediction"] = 3.5
        wrong_schema = deepcopy(self.base_lock)
        wrong_schema["schema_version"] = 3
        wrong_kind = self._derived()
        wrong_kind["candidate"]["kind"] = "other"
        self._rehash(wrong_kind)
        for lock in (top_level, game_level, wrong_schema, wrong_kind):
            with self.subTest(lock=lock.get("schema_version")), self.assertRaises(ValueError):
                pgo_prospective._verify_lock(lock)

    def test_derivation_rejects_changed_base_and_development_contracts(self):
        changed_prediction = deepcopy(self.base_lock)
        changed_prediction["games"][0]["pgo_v0_prediction"] = 99.0
        changed_artifact = deepcopy(self.base_lock)
        changed_artifact["artifact_sha256"] = _sha256("changed-artifact")
        changed_prediction_hash = deepcopy(self.base_lock)
        changed_prediction_hash["prediction_integrity_sha256"] = _sha256("changed-prediction")
        bad_artifact = deepcopy(self.development_receipt)
        bad_artifact["artifact_sha256"] = _sha256("changed-development-artifact")
        bad_source = deepcopy(self.development_receipt)
        bad_source["source_sha256"] = _sha256("changed-development-source")
        bad_kind = deepcopy(self.development_receipt)
        bad_kind["candidate"]["kind"] = "other"
        bad_weight = deepcopy(self.development_receipt)
        bad_weight["candidate"]["pgo_v1_weight"] = 0.5
        cases = (
            (changed_prediction, self.development_receipt),
            (changed_artifact, self.development_receipt),
            (changed_prediction_hash, self.development_receipt),
            (self.base_lock, bad_artifact),
            (self.base_lock, bad_source),
            (self.base_lock, bad_kind),
            (self.base_lock, bad_weight),
        )
        for base, receipt in cases:
            with self.subTest(base=base is self.base_lock), self.assertRaises(ValueError):
                pgo_prospective.derive_stability_blend(
                    base, receipt, self.development_file_sha256, self.as_of
                )

    def test_derived_validation_rejects_rehashed_candidate_tampering(self):
        late = self._derived()
        late["candidate"]["as_of"] = late["games"][0]["kickoff"]
        self._rehash(late)
        changed_prediction = self._derived()
        changed_prediction["games"][0]["candidate_prediction"] = 99.0
        self._rehash(changed_prediction)
        changed_weight = self._derived()
        changed_weight["candidate"]["pgo_v1_weight"] = 0.5
        self._rehash(changed_weight)
        for lock in (late, changed_prediction, changed_weight):
            with self.subTest(lock=lock["candidate"]["as_of"]), self.assertRaises(ValueError):
                pgo_prospective._verify_lock(lock)

    def test_attestation_is_deterministic_and_self_verifying(self):
        derived = self._derived()
        base_lock_bytes = pgo_prospective.serialize_lock(self.base_lock).encode("utf-8")
        base_prediction_bytes = pgo_prospective._prediction_csv(self.base_lock).encode("utf-8")
        derived_lock_bytes = pgo_prospective.serialize_lock(derived).encode("utf-8")
        derived_prediction_bytes = pgo_prospective._prediction_csv(derived).encode("utf-8")
        attestation = pgo_prospective.build_prospective_attestation(
            self.base_lock, base_lock_bytes, base_prediction_bytes, derived,
            derived_lock_bytes, derived_prediction_bytes, self.development_receipt_bytes,
        )
        self.assertEqual(
            pgo_prospective._verify_prospective_attestation(attestation), attestation
        )
        changed = deepcopy(attestation)
        changed["candidate"]["as_of"] = changed["earliest_kickoff"]
        changed["artifact_sha256"] = pgo_prospective._artifact_hash(changed)
        with self.assertRaises(ValueError):
            pgo_prospective._verify_prospective_attestation(changed)

        chronological_base = deepcopy(self.base_lock)
        chronological_base["games"][1]["kickoff"] = "2026-09-13T16:25:00+05:00"
        chronological_base["artifact_sha256"] = pgo_prospective._artifact_hash(
            chronological_base
        )
        chronological_derived = pgo_prospective.derive_stability_blend(
            chronological_base, self.development_receipt,
            self.development_file_sha256, self.as_of,
        )
        chronological_attestation = pgo_prospective.build_prospective_attestation(
            chronological_base,
            pgo_prospective.serialize_lock(chronological_base).encode("utf-8"),
            pgo_prospective._prediction_csv(chronological_base).encode("utf-8"),
            chronological_derived,
            pgo_prospective.serialize_lock(chronological_derived).encode("utf-8"),
            pgo_prospective._prediction_csv(chronological_derived).encode("utf-8"),
            self.development_receipt_bytes,
        )
        self.assertEqual(
            chronological_attestation["earliest_kickoff"],
            chronological_base["games"][1]["kickoff"],
        )

    def test_cli_refuses_existing_targets_and_mismatched_base_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_lock = root / "base.json"
            base_predictions = root / "base.csv"
            receipt = root / "development.json"
            base_lock.write_bytes(pgo_prospective.serialize_lock(self.base_lock).encode("utf-8"))
            base_predictions.write_text(pgo_prospective._prediction_csv(self.base_lock), encoding="utf-8", newline="")
            receipt.write_bytes(self.development_receipt_bytes)
            args = SimpleNamespace(
                base_lock=base_lock, base_predictions=base_predictions,
                development_receipt=receipt, as_of=self.as_of,
                output_dir=root / "derived", attestation_output=root / "attestation.json",
            )
            self.assertEqual(pgo_prospective._cli_derive_blend(args), 0)
            self.assertTrue((args.output_dir / "prospective_lock.json").is_file())
            self.assertTrue((args.output_dir / "prospective_predictions.csv").is_file())
            self.assertTrue(args.attestation_output.is_file())
            self.assertEqual(pgo_prospective._cli_derive_blend(args), 1)

            existing_attestation = SimpleNamespace(**{
                **args.__dict__, "output_dir": root / "other",
            })
            self.assertEqual(pgo_prospective._cli_derive_blend(existing_attestation), 1)
            base_predictions.write_text("wrong\n", encoding="utf-8", newline="")
            mismatch = SimpleNamespace(**{
                **args.__dict__, "output_dir": root / "mismatch",
                "attestation_output": root / "mismatch-attestation.json",
            })
            self.assertEqual(pgo_prospective._cli_derive_blend(mismatch), 1)
            self.assertFalse(mismatch.output_dir.exists())

    def test_cli_refuses_attestation_aliases_without_writing_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_lock = root / "base.json"
            base_predictions = root / "base.csv"
            receipt = root / "development.json"
            base_lock.write_bytes(pgo_prospective.serialize_lock(self.base_lock).encode("utf-8"))
            base_predictions.write_text(
                pgo_prospective._prediction_csv(self.base_lock),
                encoding="utf-8",
                newline="",
            )
            receipt.write_bytes(self.development_receipt_bytes)

            for name in ("prospective_lock.json", "prospective_predictions.csv"):
                with self.subTest(name=name):
                    output_dir = root / name.removesuffix(".json").removesuffix(".csv")
                    args = SimpleNamespace(
                        base_lock=base_lock,
                        base_predictions=base_predictions,
                        development_receipt=receipt,
                        as_of=self.as_of,
                        output_dir=output_dir,
                        attestation_output=output_dir / name,
                    )
                    self.assertEqual(pgo_prospective._cli_derive_blend(args), 1)
                    self.assertFalse(output_dir.exists())

    def test_cli_refuses_output_directory_below_attestation_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_lock = root / "base.json"
            base_predictions = root / "base.csv"
            receipt = root / "development.json"
            base_lock.write_bytes(pgo_prospective.serialize_lock(self.base_lock).encode("utf-8"))
            base_predictions.write_text(
                pgo_prospective._prediction_csv(self.base_lock),
                encoding="utf-8",
                newline="",
            )
            receipt.write_bytes(self.development_receipt_bytes)
            attestation = root / "attestation.json"
            args = SimpleNamespace(
                base_lock=base_lock,
                base_predictions=base_predictions,
                development_receipt=receipt,
                as_of=self.as_of,
                output_dir=attestation / "derived",
                attestation_output=attestation,
            )

            try:
                result = pgo_prospective._cli_derive_blend(args)
            except OSError:
                result = None
            self.assertEqual((result, attestation.exists()), (1, False))

    def test_cli_rolls_back_all_outputs_when_any_write_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_lock = root / "base.json"
            base_predictions = root / "base.csv"
            receipt = root / "development.json"
            base_lock.write_bytes(pgo_prospective.serialize_lock(self.base_lock).encode("utf-8"))
            base_predictions.write_text(
                pgo_prospective._prediction_csv(self.base_lock),
                encoding="utf-8",
                newline="",
            )
            receipt.write_bytes(self.development_receipt_bytes)
            write = pgo_prospective.atomic_write_text

            for failing_write in (1, 2, 3):
                with self.subTest(failing_write=failing_write):
                    output_dir = root / f"derived-{failing_write}"
                    attestation = root / f"attestation-{failing_write}.json"
                    args = SimpleNamespace(
                        base_lock=base_lock,
                        base_predictions=base_predictions,
                        development_receipt=receipt,
                        as_of=self.as_of,
                        output_dir=output_dir,
                        attestation_output=attestation,
                    )
                    calls = 0

                    def fail_write(path, content):
                        nonlocal calls
                        calls += 1
                        if calls == failing_write:
                            raise OSError("controlled output failure")
                        write(path, content)

                    with patch.object(pgo_prospective, "atomic_write_text", fail_write):
                        try:
                            result = pgo_prospective._cli_derive_blend(args)
                        except OSError:
                            result = None
                    self.assertEqual(
                        (result, output_dir.exists(), attestation.exists()),
                        (1, False, False),
                    )

    def test_cli_preserves_raced_targets_and_removes_owned_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_lock = root / "base.json"
            base_predictions = root / "base.csv"
            receipt = root / "development.json"
            base_lock.write_bytes(pgo_prospective.serialize_lock(self.base_lock).encode("utf-8"))
            base_predictions.write_text(
                pgo_prospective._prediction_csv(self.base_lock),
                encoding="utf-8",
                newline="",
            )
            receipt.write_bytes(self.development_receipt_bytes)
            link = os.link

            for raced_link in (1, 2, 3):
                with self.subTest(raced_link=raced_link):
                    output_dir = root / f"derived-{raced_link}"
                    attestation = root / f"attestation-{raced_link}.json"
                    targets = (
                        output_dir / "prospective_lock.json",
                        output_dir / "prospective_predictions.csv",
                        attestation,
                    )
                    args = SimpleNamespace(
                        base_lock=base_lock,
                        base_predictions=base_predictions,
                        development_receipt=receipt,
                        as_of=self.as_of,
                        output_dir=output_dir,
                        attestation_output=attestation,
                    )
                    calls = 0

                    def race_link(source, target):
                        nonlocal calls
                        calls += 1
                        if calls == raced_link:
                            Path(target).write_text("racer", encoding="utf-8")
                        link(source, target)

                    with patch.object(os, "link", race_link):
                        result = pgo_prospective._cli_derive_blend(args)
                    self.assertEqual(result, 1)
                    for index, target in enumerate(targets, start=1):
                        if index == raced_link:
                            self.assertEqual(target.read_text(encoding="utf-8"), "racer")
                        else:
                            self.assertFalse(target.exists())
                    if raced_link == 3:
                        self.assertFalse(output_dir.exists())

    def test_cli_cleans_partial_outputs_before_handling_interruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            link = os.link

            for error_type in (KeyboardInterrupt, RuntimeError):
                with self.subTest(error_type=error_type.__name__):
                    args = self._cli_args(root, error_type.__name__)
                    targets = (
                        args.output_dir / "prospective_lock.json",
                        args.output_dir / "prospective_predictions.csv",
                        args.attestation_output,
                    )
                    calls = 0

                    def interrupt_link(source, target):
                        nonlocal calls
                        calls += 1
                        if calls == 2:
                            raise error_type("controlled interruption")
                        link(source, target)

                    caught = None
                    result = None
                    try:
                        with patch.object(os, "link", interrupt_link):
                            result = pgo_prospective._cli_derive_blend(args)
                    except BaseException as error:
                        caught = error

                    if error_type is KeyboardInterrupt:
                        self.assertIsInstance(caught, KeyboardInterrupt)
                    else:
                        self.assertIsNone(caught)
                        self.assertEqual(result, 1)
                    self.assertFalse(any(target.exists() for target in targets))

    def test_cli_cleanup_failure_does_not_mask_or_expose_partial_final(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self._cli_args(root, "cleanup-failure")
            targets = (
                args.output_dir / "prospective_lock.json",
                args.output_dir / "prospective_predictions.csv",
                args.attestation_output,
            )
            link = os.link
            unlink = Path.unlink
            link_calls = 0
            cleanup_failed = False

            def fail_second_link(source, target):
                nonlocal link_calls
                link_calls += 1
                if link_calls == 2:
                    raise OSError("controlled promotion failure")
                link(source, target)

            def fail_first_cleanup(path, *positional, **keywords):
                nonlocal cleanup_failed
                if not cleanup_failed:
                    cleanup_failed = True
                    raise PermissionError("controlled cleanup failure")
                return unlink(path, *positional, **keywords)

            caught = None
            result = None
            try:
                with (
                    patch.object(os, "link", fail_second_link),
                    patch.object(Path, "unlink", fail_first_cleanup),
                ):
                    result = pgo_prospective._cli_derive_blend(args)
            except BaseException as error:
                caught = error

            self.assertTrue(cleanup_failed)
            self.assertIsNone(caught)
            self.assertEqual(result, 1)
            self.assertFalse(any(target.exists() for target in targets))

    def test_cli_detaches_before_identity_check_during_adversarial_swap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self._cli_args(root, "adversarial-swap")
            first = args.output_dir / "prospective_lock.json"
            second = args.output_dir / "prospective_predictions.csv"
            link = os.link
            samestat = os.path.samestat
            link_calls = 0
            swapped = False

            def race_second_link(source, target):
                nonlocal link_calls
                link_calls += 1
                if link_calls == 2:
                    Path(target).write_text("external-b", encoding="utf-8")
                link(source, target)

            def swap_first_before_comparison(left, right):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    replacement = root / "external-a.swap"
                    replacement.write_text("external-a", encoding="utf-8")
                    os.replace(replacement, first)
                return samestat(left, right)

            with (
                patch.object(os, "link", race_second_link),
                patch.object(os.path, "samestat", swap_first_before_comparison),
            ):
                result = pgo_prospective._cli_derive_blend(args)

            self.assertEqual(result, 1)
            self.assertTrue(swapped)
            self.assertEqual(first.read_text(encoding="utf-8"), "external-a")
            self.assertEqual(second.read_text(encoding="utf-8"), "external-b")
            self.assertFalse(args.attestation_output.exists())

    def test_attestation_rejects_substituted_evidence_inputs(self):
        derived = self._derived()
        base_lock_bytes = pgo_prospective.serialize_lock(self.base_lock).encode("utf-8")
        base_prediction_bytes = pgo_prospective._prediction_csv(self.base_lock).encode("utf-8")
        derived_lock_bytes = pgo_prospective.serialize_lock(derived).encode("utf-8")
        derived_prediction_bytes = pgo_prospective._prediction_csv(derived).encode("utf-8")

        cases = [
            (self.base_lock, base_lock_bytes, b"unrelated development receipt"),
            (self.base_lock, base_lock_bytes + b" ", self.development_receipt_bytes),
        ]
        different_base = deepcopy(self.base_lock)
        different_base["source_lock_sha256"] = _sha256("different base")
        different_base["artifact_sha256"] = pgo_prospective._artifact_hash(different_base)
        cases.append((
            different_base,
            pgo_prospective.serialize_lock(different_base).encode("utf-8"),
            self.development_receipt_bytes,
        ))
        for base, lock_bytes, receipt_bytes in cases:
            with self.subTest(base=base is self.base_lock), self.assertRaises(ValueError):
                pgo_prospective.build_prospective_attestation(
                    base, lock_bytes, base_prediction_bytes, derived,
                    derived_lock_bytes, derived_prediction_bytes, receipt_bytes,
                )


class ProspectiveSchemaOneRegressionTests(unittest.TestCase):
    def test_schema_one_serialized_bytes_are_frozen(self):
        lock_tests = ProspectiveLockTests()
        lock_tests.setUp()
        lock = pgo_prospective.lock_games(lock_tests.schedule, lock_tests.model_state, AS_OF)
        self.assertEqual(
            _sha256(pgo_prospective.serialize_lock(lock)),
            "38a32705b5ff09efcc60a1e12526acbfdf6960525aadac9c80847513f70b7ad0",
        )
        self.assertEqual(
            _sha256(pgo_prospective._prediction_csv(lock)),
            "97ac0f7f24786ef04bc67a493283b1e3f61422c45007b024d6f1facab4cf9c1d",
        )

        grade_tests = ProspectiveGradeTests()
        grade_tests.setUp()
        receipt = pgo_prospective.grade_locked_games(grade_tests.lock, grade_tests.results)
        receipt_text, rows_text = pgo_prospective.serialize_grade(receipt, receipt["rows"])
        self.assertEqual(_sha256(receipt_text), "10dfebd8f68d8327a533d373f79f1677a1b966f7dc7c995afe7b34c0fcaeeb26")
        self.assertEqual(_sha256(rows_text), "155ec3456adcd45dc9e05c1ddf4d92a45c3e07da1e5f93a950bc43417c6a5c41")


class ProspectiveBlendDevelopmentTests(unittest.TestCase):
    source_path = Path("research/pgo_v1/validation_predictions.csv")

    def setUp(self):
        self.source = pgo_prospective.load_development_predictions(self.source_path)
        self.receipt = pgo_prospective.develop_stability_blend(self.source)

    def test_tracked_source_and_approved_fixed_blend_are_reproduced(self):
        self.assertEqual(
            self.source["sha256"],
            "b697b6f8f5eee9ae1efe607272458964a681f99f440a94f86d8edce2ad5a19b7",
        )
        self.assertEqual(len(self.source["rows"]), 2_127)
        self.assertEqual({row["season"] for row in self.source["rows"]}, set(range(2018, 2026)))
        self.assertEqual(self.receipt["status"], "DEVELOPMENT_ONLY")
        self.assertEqual(self.receipt["candidate"]["kind"], "fixed_convex_stability_blend")
        self.assertEqual(self.receipt["selection"]["selected_pgo_v1_weight"], 0.25)
        self.assertEqual(self.receipt["selection"]["first_regressing_weight"], 0.30)
        self.assertEqual(len(self.receipt["grid_results"]), 21)
        self.assertAlmostEqual(self.receipt["metrics"]["candidate_mae"], 10.227241, places=6)
        self.assertAlmostEqual(self.receipt["metrics"]["pgo_v0_mae"], 10.266150, places=6)
        self.assertAlmostEqual(self.receipt["aggregate_interval"]["lower"], 0.017797, places=6)
        self.assertAlmostEqual(self.receipt["aggregate_interval"]["upper"], 0.060136, places=6)
        self.assertTrue(all(row["improvement"] > 0.0 for row in self.receipt["season_results"]))

    def test_receipt_serialization_and_cli_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = pgo_prospective.write_development_receipt(root / "first.json", self.receipt)
            second = pgo_prospective.write_development_receipt(root / "second.json", self.receipt)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            output = root / "cli.json"
            self.assertEqual(
                pgo_prospective._cli_develop_blend(
                    SimpleNamespace(predictions=self.source_path, output=output)
                ),
                0,
            )
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), self.receipt)

    def test_loader_rejects_invalid_csv_contracts(self):
        raw = self.source_path.read_text(encoding="utf-8")
        header, first, *rest = raw.splitlines()
        cases = {
            "header": "changed," + header.split(",", 1)[1] + "\n" + first + "\n",
            "duplicate": "\n".join((header, first, first)) + "\n",
            "boolean": "\n".join((header, first.replace(",true,", ",True,", 1))) + "\n",
            "nonfinite": "\n".join((header, first.replace(",6.000000,", ",nan,"))) + "\n",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, text in cases.items():
                path = root / f"{name}.csv"
                path.write_text(text, encoding="utf-8", newline="")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    pgo_prospective.load_development_predictions(path)

    def test_development_contract_rejects_source_and_receipt_tampering(self):
        missing = {"rows": self.source["rows"][:-1], "sha256": self.source["sha256"]}
        wrong_season = deepcopy(self.source)
        wrong_season["rows"][0]["season"] = 2017
        changed_hash = {**self.source, "sha256": _sha256("changed-source")}
        for source in (missing, wrong_season, changed_hash):
            with self.subTest(source=source["sha256"]), self.assertRaises(ValueError):
                pgo_prospective.develop_stability_blend(source)

        stale_hash = deepcopy(self.receipt)
        stale_hash["metrics"]["candidate_mae"] = 0.0
        with self.assertRaises(ValueError):
            pgo_prospective._verify_development_receipt(stale_hash)
        rehashed = deepcopy(stale_hash)
        rehashed["artifact_sha256"] = pgo_prospective._artifact_hash(rehashed)
        with self.assertRaises(ValueError):
            pgo_prospective._verify_development_receipt(rehashed)
        no_regression = deepcopy(self.receipt)
        for grid_row in no_regression["grid_results"]:
            for season_row in grid_row["season_results"]:
                season_row["improvement"] = 1.0
        no_regression["artifact_sha256"] = pgo_prospective._artifact_hash(no_regression)
        with self.assertRaises(ValueError):
            pgo_prospective._verify_development_receipt(no_regression)
    def test_rehashed_aggregate_interval_tampering_is_rejected(self):
        changed_interval = deepcopy(self.receipt)
        changed_interval["aggregate_interval"]["lower"] = 0.0
        changed_interval["artifact_sha256"] = pgo_prospective._artifact_hash(changed_interval)
        with self.assertRaises(ValueError):
            pgo_prospective._verify_development_receipt(changed_interval)

    def test_rehashed_non_selected_grid_tampering_is_rejected(self):
        changed_non_selected_grid = deepcopy(self.receipt)
        changed_non_selected_grid["grid_results"][0]["metrics"]["candidate_mae"] = 0.0
        changed_non_selected_grid["artifact_sha256"] = pgo_prospective._artifact_hash(
            changed_non_selected_grid
        )
        with self.assertRaises(ValueError):
            pgo_prospective._verify_development_receipt(changed_non_selected_grid)


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
