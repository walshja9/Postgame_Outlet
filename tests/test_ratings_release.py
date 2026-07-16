import copy
import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import generate_site
import snapshot
import spreads
from release_ratings import load_release_rows


FIELDS = [
    "team", "conf", "division", "qb_name", "qb_value", "off_value",
    "def_value", "needs_review", "notes", "age", "exp",
]


def write_ratings(path, review_values=("N", "N")):
    rows = [
        {
            "team": "Alpha", "conf": "AFC", "division": "East",
            "qb_name": "A QB", "qb_value": "1", "off_value": "0.5",
            "def_value": "-0.5", "needs_review": review_values[0],
            "notes": "Alpha note", "age": "30", "exp": "5",
        },
        {
            "team": "Beta", "conf": "NFC", "division": "West",
            "qb_name": "B QB", "qb_value": "0", "off_value": "0",
            "def_value": "0", "needs_review": review_values[1],
            "notes": "Beta note", "age": "28", "exp": "3",
        },
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class ReleaseGateTests(unittest.TestCase):
    def test_lists_every_flagged_team(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, "ratings.csv")
            write_ratings(path, ("Y", "y"))

            with self.assertRaisesRegex(
                ValueError,
                r"Release blocked: needs_review=Y for Alpha, Beta",
            ):
                load_release_rows(path)

    def test_returns_cleared_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, "ratings.csv")
            write_ratings(path)

            self.assertEqual(
                [row["team"] for row in load_release_rows(path)],
                ["Alpha", "Beta"],
            )

    def test_all_public_artifact_loaders_share_the_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            write_ratings(data / "ratings.csv", ("Y", "N"))

            with patch.object(generate_site, "DATA", str(data)):
                with self.assertRaisesRegex(ValueError, "Alpha"):
                    generate_site.load_teams({})
            with patch.object(snapshot, "DATA", str(data)):
                with self.assertRaisesRegex(ValueError, "Alpha"):
                    snapshot.snapshot_current()
            with patch.object(spreads, "DATA", str(data)):
                with self.assertRaisesRegex(ValueError, "Alpha"):
                    spreads.load_ratings()


class SnapshotTests(unittest.TestCase):
    def test_legacy_snapshot_list_is_preserved(self):
        rows = [{"team": "Alpha", "rating": 1.0}]
        entry = snapshot.normalize_snapshot_entry(rows)
        self.assertEqual(entry["rows"], rows)
        self.assertEqual(entry["published_at"], "")
        self.assertEqual(entry["corrections"], [])

    def test_correction_note_does_not_change_frozen_rows(self):
        snaps = {
            "Week 1": {
                "published_at": "2026-09-10T12:00:00-04:00",
                "rows": [{"team": "Alpha", "rating": 1.0}],
                "corrections": [],
            }
        }
        before = copy.deepcopy(snaps["Week 1"]["rows"])
        snapshot.add_correction(
            snaps,
            "Week 1",
            "Corrected the displayed opponent name; rating unchanged.",
            at="2026-09-11T09:30:00-04:00",
        )
        self.assertEqual(snaps["Week 1"]["rows"], before)
        self.assertEqual(
            snaps["Week 1"]["corrections"],
            [{
                "at": "2026-09-11T09:30:00-04:00",
                "note": "Corrected the displayed opponent name; rating unchanged.",
            }],
        )

    def test_duplicate_snapshot_label_is_rejected(self):
        snaps = {"Week 1": {"published_at": "", "rows": [], "corrections": []}}
        with self.assertRaisesRegex(ValueError, "already exists"):
            snapshot.add_snapshot(snaps, "Week 1", [], at="2026-09-10T12:00:00-04:00")

    def test_correction_note_cannot_be_empty(self):
        snaps = {"Week 1": {"published_at": "", "rows": [], "corrections": []}}
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            snapshot.add_correction(snaps, "Week 1", "   ")


class MovementTests(unittest.TestCase):
    def test_movement_compares_current_rank_to_latest_snapshot(self):
        current = [
            {"team": "Beta", "rating": 2.0},
            {"team": "Alpha", "rating": 1.0},
            {"team": "Gamma", "rating": 0.0},
        ]
        previous = [
            {"team": "Alpha", "rating": 2.0},
            {"team": "Beta", "rating": 1.0},
            {"team": "Gamma", "rating": 0.0},
        ]
        self.assertEqual(
            generate_site.movement_by_team(current, previous),
            {"Beta": 1, "Alpha": -1, "Gamma": 0},
        )

    def test_new_team_has_no_comparable_movement(self):
        self.assertEqual(
            generate_site.movement_by_team(
                [{"team": "Alpha", "rating": 1.0}],
                [],
            ),
            {"Alpha": None},
        )


class SnapshotHtmlTests(unittest.TestCase):
    def test_snapshot_metadata_is_embedded_and_rendered(self):
        row = {
            "team": "Alpha", "conf": "AFC", "div": "East",
            "qb_name": "A QB", "qb": 1.0, "off": 0.5, "def": -0.5,
            "prior": "", "rating": 1.0, "injury": False,
        }
        meta = {
            "published_at": "2026-09-10T12:00:00-04:00",
            "corrections": [{
                "at": "2026-09-11T09:30:00-04:00",
                "note": "Corrected opponent label; rating unchanged.",
            }],
        }
        snaps = {"Week 1": {**meta, "rows": [row]}}

        with tempfile.TemporaryDirectory() as temp:
            with patch.object(generate_site, "DATA", temp):
                with patch("generate_site.load_snaps", return_value=snaps, create=True):
                    page = generate_site.build_html([row], {"season": "2026"})

        marker = "const VERSION_META = "
        self.assertTrue(marker in page, f"{marker!r} missing")
        payload = page.split(marker, 1)[1].split(";\n", 1)[0]
        self.assertEqual(json.loads(payload)["Week 1"], meta)
        self.assertIn('id="versionMeta"', page)
        self.assertIn("renderVersionMeta(e.target.value);", page)

    def test_snapshot_correction_cannot_break_out_of_script(self):
        note = "Correction </script><script>alert(1)</script>"
        snaps = {
            "Week 1": {
                "published_at": "",
                "rows": [],
                "corrections": [{"at": "2026-09-11T09:30:00-04:00", "note": note}],
            }
        }

        with tempfile.TemporaryDirectory() as temp:
            with patch.object(generate_site, "DATA", temp):
                with patch.object(generate_site, "load_snaps", return_value=snaps):
                    page = generate_site.build_html([], {"season": "2026"})

        payload = page.split("const VERSION_META = ", 1)[1].split(";\n", 1)[0]
        self.assertNotIn("</script>", payload)
        self.assertEqual(
            json.loads(payload)["Week 1"]["corrections"][0]["note"],
            note,
        )


class GeneratedDocumentTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {
                "team": "Alpha", "conf": "AFC", "div": "East",
                "qb_name": "A QB", "qb": 1.0, "off": 0.5, "def": -0.5,
                "prior": 0.0, "rating": 1.0, "notes": "Alpha note",
                "injury": False,
            }
        ]
        self.config = {
            "season": "2026",
            "edition": "2026 Preseason",
            "author": "Sean McCabe",
        }
        generate_site.build_html.qb_data = ([], [])

    def test_metadata_names_author_edition_and_canonical_page(self):
        generated_at = datetime(2026, 7, 15, 22, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "snapshots.json").write_text("{}", encoding="utf-8")
            with patch.object(generate_site, "DATA", temp):
                document = generate_site.build_html(
                    self.rows,
                    self.config,
                    generated_at=generated_at,
                )
        self.assertIn('<meta name="description"', document)
        self.assertIn(
            '<link rel="canonical" href="https://postgameoutlet.com/pages/power-ratings">',
            document,
        )
        self.assertIn("Sean McCabe", document)
        self.assertIn("2026 Preseason", document)
        self.assertIn('<time datetime="2026-07-15T22:00:00+00:00">', document)

    def test_prediction_lab_surface_is_not_public(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "snapshots.json").write_text("{}", encoding="utf-8")
            with patch.object(generate_site, "DATA", temp):
                document = generate_site.build_html(self.rows, self.config)
        self.assertNotIn("Schedule &amp; Spreads", document)
        self.assertNotIn("SPREADS_JSON", document)
        self.assertNotIn("const SPREADS", document)
        self.assertNotIn("From ratings to a betting line", document)
        self.assertNotIn("my_margin(home)", document)
        self.assertNotIn("unofficial ESPN feed", document)
        self.assertNotIn("season-long edge list", document)
        self.assertNotIn("Home field plays a role", document)
        self.assertNotIn("Prime-time home games", document)
        self.assertNotRegex(document, r"edge on your\s+picks")

    def test_default_output_is_private_preview(self):
        args = generate_site.parse_args([])
        self.assertRegex(
            args.output.replace("\\", "/"),
            r"output/ratings-preview/\d{4}-\d{2}-\d{2}/index\.html$",
        )


if __name__ == "__main__":
    unittest.main()
