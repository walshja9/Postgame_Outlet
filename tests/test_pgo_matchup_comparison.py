import csv
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pgo_matchup_comparison
import spreads


class MatchupComparisonTests(unittest.TestCase):
    AS_OF = "2026-09-01T12:00:00Z"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.ratings_path = self.directory / "ratings_2026_preseason.csv"
        self.receipt_path = self.directory / "backtest.json"
        self.rows = [
            {
                "team": abbr,
                "headline_rating": str(index / 10),
                "as_of": self.AS_OF,
                "validation_status": "EXPERIMENTAL",
            }
            for index, abbr in enumerate(spreads.ABBR.values(), start=1)
        ]
        self._write_ratings()
        self._write_receipt()
        self.mccabe_ratings = {
            "Buffalo Bills": 6.0,
            "Miami Dolphins": 4.0,
            "Kansas City Chiefs": 5.0,
            "Denver Broncos": 3.0,
        }
        self.payload = {
            "events": [
                {
                    "date": "2026-09-10T00:20:00Z",
                    "competitions": [{
                        "competitors": [
                            {"homeAway": "away", "team": {"displayName": "Miami Dolphins"}},
                            {"homeAway": "home", "team": {"displayName": "Buffalo Bills"}},
                        ],
                        "odds": [{"spread": -3.0, "details": "BUF -3"}],
                    }],
                },
                {
                    "date": "2026-09-13T17:00:00Z",
                    "competitions": [{
                        "competitors": [
                            {"homeAway": "away", "team": {"displayName": "Denver Broncos"}},
                            {"homeAway": "home", "team": {"displayName": "Kansas City Chiefs"}},
                        ],
                    }],
                },
            ],
        }

    def tearDown(self):
        self.temp.cleanup()

    def _write_ratings(self, rows=None, fieldnames=None):
        rows = self.rows if rows is None else rows
        fieldnames = fieldnames or [
            "team", "headline_rating", "as_of", "validation_status",
        ]
        with self.ratings_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows({name: row.get(name) for name in fieldnames} for row in rows)

    def _write_receipt(self, path=None, **overrides):
        receipt = {
            "status": "PASS",
            "as_of": self.AS_OF,
            "checks": {"audit_complete": True},
            "failed_checks": [],
            "status_reason": "Experimental shadow model.",
        }
        receipt.update(overrides)
        (path or self.receipt_path).write_text(json.dumps(receipt), encoding="utf-8")

    def _ratings(self):
        ratings, _ = pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)
        return ratings

    def test_loads_all_abbreviations_as_full_team_names_with_hold_metadata(self):
        ratings, metadata = pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)

        self.assertEqual(set(ratings), set(spreads.ABBR))
        self.assertEqual(ratings["Buffalo Bills"], 0.1)
        self.assertEqual(metadata["as_of"], self.AS_OF)
        self.assertEqual(metadata["validation_status"], "EXPERIMENTAL")
        self.assertEqual(metadata["display_status"], "HOLD")
        self.assertEqual(metadata["status_reason"], "Experimental shadow model.")

    def test_loader_rejects_invalid_artifacts(self):
        cases = [
            ("missing columns", self.rows, ["team", "headline_rating"], "missing"),
            ("duplicate team", [*self.rows, self.rows[0]], None, "duplicate"),
            ("unknown abbreviation", [{**self.rows[0], "team": "XXX"}, *self.rows[1:]], None, "unknown"),
            ("non-finite rating", [{**self.rows[0], "headline_rating": "nan"}, *self.rows[1:]], None, "finite"),
            ("inconsistent as_of", [{**self.rows[0], "as_of": "2026-09-02T12:00:00Z"}, *self.rows[1:]], None, "as_of"),
        ]
        for name, rows, fields, error in cases:
            with self.subTest(name=name):
                self._write_ratings(rows, fields)
                with self.assertRaisesRegex(ValueError, error):
                    pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)
                self._write_ratings()

    def test_loader_requires_a_valid_matching_receipt(self):
        self.receipt_path.unlink()
        with self.assertRaisesRegex(ValueError, "receipt"):
            pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)

        self._write_receipt(as_of="2026-09-02T12:00:00Z")
        with self.assertRaisesRegex(ValueError, "as_of"):
            pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)

        self._write_receipt(status="BLOCKED")
        with self.assertRaisesRegex(ValueError, "status"):
            pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)

        self._write_receipt(checks=None)
        with self.assertRaisesRegex(ValueError, "checks"):
            pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)

    def test_loader_uses_an_explicit_receipt_path(self):
        explicit_receipt = self.directory / "explicit-backtest.json"
        self._write_receipt(explicit_receipt)
        self.receipt_path.unlink()

        _, metadata = pgo_matchup_comparison.load_pgo_ratings(
            self.ratings_path, receipt_path=explicit_receipt,
        )

        self.assertEqual(Path(metadata["receipt_path"]), explicit_receipt)

    def test_failed_receipt_checks_remain_hold(self):
        self._write_receipt(
            status="HOLD",
            checks={"audit_complete": False},
            failed_checks=["audit_complete"],
        )

        _, metadata = pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)

        self.assertEqual(metadata["display_status"], "HOLD")
        self.assertEqual(metadata["failed_checks"], ["audit_complete"])

    def test_validated_csv_with_failed_receipt_checks_remains_hold(self):
        self._write_ratings([
            {**row, "validation_status": "VALIDATED"} for row in self.rows
        ])
        self._write_receipt(
            status="HOLD",
            checks={"audit_complete": False},
            failed_checks=["audit_complete"],
        )

        _, metadata = pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)

        self.assertEqual(metadata["display_status"], "HOLD")

    def test_loader_accepts_real_shaped_receipt_without_optional_status(self):
        real_receipt = json.loads(
            (Path(pgo_matchup_comparison.__file__).resolve().parent
             / "research" / "pgo_v1" / "backtest.json").read_text(encoding="utf-8")
        )
        real_receipt.pop("status")
        self.receipt_path.write_text(json.dumps(real_receipt), encoding="utf-8")
        self._write_ratings([
            {**row, "as_of": real_receipt["as_of"]} for row in self.rows
        ])

        _, metadata = pgo_matchup_comparison.load_pgo_ratings(self.ratings_path)

        self.assertEqual(metadata["display_status"], "HOLD")

    def test_builds_two_independent_half_point_lines_and_edges(self):
        pgo_ratings = self._ratings()
        pgo_ratings.update({"Buffalo Bills": 3.0, "Miami Dolphins": 2.0})
        mccabe_ratings = {**self.mccabe_ratings, "Buffalo Bills": 6.1}

        rows = pgo_matchup_comparison.build_matchup_rows(
            self.payload, mccabe_ratings, pgo_ratings,
            {"Buffalo Bills": 1.0}, 2.0,
        )

        bills = rows[0]
        self.assertEqual(len(rows), 2)
        self.assertTrue(bills["prime"])
        self.assertEqual(bills["mccabe_hfa"], 1.5)
        self.assertEqual(bills["mccabe_line"], -3.5)
        self.assertEqual(bills["pgo_line"], -2.5)
        self.assertNotEqual(bills["mccabe_line"], bills["pgo_line"])
        self.assertEqual(bills["mccabe_edge"], 0.5)
        self.assertEqual(bills["pgo_edge"], -0.5)

    def test_unpriced_event_has_no_market_or_edges(self):
        rows = pgo_matchup_comparison.build_matchup_rows(
            self.payload, self.mccabe_ratings, self._ratings(), {}, 1.5,
        )

        unpriced = rows[1]
        self.assertIsNone(unpriced["market"])
        self.assertIsNone(unpriced["mccabe_edge"])
        self.assertIsNone(unpriced["pgo_edge"])

    def test_build_rows_rejects_invalid_or_unmatched_events(self):
        cases = []
        duplicate = {"events": [self.payload["events"][0], self.payload["events"][0]]}
        cases.append(("duplicate event", duplicate, self.mccabe_ratings, self._ratings(), "duplicate"))
        unknown = json.loads(json.dumps(self.payload))
        unknown["events"][0]["competitions"][0]["competitors"][0]["team"]["displayName"] = "Unknown Team"
        cases.append(("unknown team", unknown, self.mccabe_ratings, self._ratings(), "unknown"))
        malformed = json.loads(json.dumps(self.payload))
        malformed["events"][0]["competitions"][0]["odds"][0]["spread"] = "BUF -3"
        cases.append(("malformed market", malformed, self.mccabe_ratings, self._ratings(), "market"))
        missing_join = self._ratings()
        missing_join.pop("Miami Dolphins")
        cases.append(("unmatched PGO model join", self.payload, self.mccabe_ratings, missing_join, "unmatched"))
        missing_mccabe = dict(self.mccabe_ratings)
        missing_mccabe.pop("Miami Dolphins")
        cases.append(("unmatched McCabe model join", self.payload, missing_mccabe, self._ratings(), "unmatched"))

        for name, payload, mccabe_ratings, pgo_ratings, error in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, error):
                    pgo_matchup_comparison.build_matchup_rows(
                        payload, mccabe_ratings, pgo_ratings, {}, 1.5,
                    )

    def test_renders_private_preview_with_hold_context_and_unavailable_cells(self):
        metadata = {
            "artifact_path": self.ratings_path,
            "receipt_path": self.receipt_path,
            "as_of": self.AS_OF,
            "validation_status": "EXPERIMENTAL",
            "display_status": "HOLD",
            "status_reason": "Experimental shadow model.",
            "failed_checks": ["aggregate_improvement"],
        }
        rows = [{
            "date": "2026-09-13T17:00:00Z", "prime": False,
            "home": "Kansas City Chiefs", "away": "Denver Broncos",
            "market": None, "details": None, "mccabe_line": -3.5,
            "pgo_line": -2.5, "mccabe_edge": 0.5, "pgo_edge": -0.5,
        }]

        html = pgo_matchup_comparison.render_preview(
            rows, metadata, year=2026, week=1,
            captured_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
            source_url=spreads.ENDPOINT,
        )

        self.assertIn("Private", html)
        self.assertIn("McCabe", html)
        self.assertIn("PGO", html)
        self.assertIn("HOLD", html)
        self.assertIn(self.AS_OF, html)
        self.assertIn("Experimental shadow model.", html)
        self.assertIn("Unavailable", html)
        self.assertIn("<td>+0.5</td>", html)
        self.assertIn("<td>-0.5</td>", html)
        self.assertIn("Denver Broncos", html)
        self.assertNotIn("docs/index.html", html)
        self.assertNotIn("data/ratings.csv", html)

    def test_preview_escapes_year_and_week_in_header(self):
        html = pgo_matchup_comparison.render_preview(
            [], {
                "artifact_path": self.ratings_path,
                "as_of": self.AS_OF,
                "validation_status": "EXPERIMENTAL",
                "display_status": "HOLD",
            }, year='<year>', week='<week>',
            captured_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
            source_url=spreads.ENDPOINT,
        )

        self.assertIn("&lt;year&gt; NFL Week &lt;week&gt;", html)
        self.assertNotIn("<year>", html)
        self.assertNotIn("<week>", html)

    def test_preview_paths_stay_private(self):
        path = pgo_matchup_comparison.default_preview_path(
            datetime(2026, 9, 1, 12, tzinfo=UTC),
        )
        self.assertEqual(
            Path(path).resolve(),
            (Path(pgo_matchup_comparison.__file__).resolve().parent / "output"
             / "pgo-matchup-preview" / "2026-09-01" / "index.html").resolve(),
        )
        with self.assertRaisesRegex(ValueError, "output"):
            pgo_matchup_comparison.write_preview("<p>private</p>", self.directory / "index.html")

    def test_cli_writes_one_private_preview_from_one_fetch(self):
        output = self.directory / "output" / "preview.html"
        public_index = Path(pgo_matchup_comparison.__file__).resolve().parent / "docs" / "index.html"
        before = public_index.read_text(encoding="utf-8")
        with (
            patch.object(pgo_matchup_comparison, "OUTPUT_ROOT", self.directory / "output"),
            patch.object(pgo_matchup_comparison.spreads, "fetch_week", return_value=self.payload) as fetch,
            patch.object(pgo_matchup_comparison.spreads, "load_ratings", return_value=self.mccabe_ratings),
            patch.object(pgo_matchup_comparison.spreads, "load_hfa", return_value=({}, 1.5)),
        ):
            result = pgo_matchup_comparison.main([
                "1", "2026", "--pgo-ratings", str(self.ratings_path),
                "--pgo-receipt", str(self.receipt_path), "--output", str(output),
            ])

        self.assertEqual(result, 0)
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(output.is_file())
        self.assertIn("Private", output.read_text(encoding="utf-8"))
        self.assertEqual(public_index.read_text(encoding="utf-8"), before)

    def test_cli_rejects_an_output_outside_private_root_before_writing(self):
        output = self.directory / "public.html"
        with (
            patch.object(pgo_matchup_comparison, "OUTPUT_ROOT", self.directory / "output"),
            patch.object(pgo_matchup_comparison.spreads, "fetch_week", return_value=self.payload),
            patch.object(pgo_matchup_comparison.spreads, "load_ratings", return_value=self.mccabe_ratings),
            patch.object(pgo_matchup_comparison.spreads, "load_hfa", return_value=({}, 1.5)),
        ):
            result = pgo_matchup_comparison.main([
                "--pgo-ratings", str(self.ratings_path), "--pgo-receipt", str(self.receipt_path),
                "--output", str(output),
            ])

        self.assertEqual(result, 1)
        self.assertFalse(output.exists())

    def test_cli_returns_nonzero_when_fetch_fails(self):
        with patch.object(pgo_matchup_comparison.spreads, "fetch_week", side_effect=RuntimeError("offline")):
            result = pgo_matchup_comparison.main([])

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
