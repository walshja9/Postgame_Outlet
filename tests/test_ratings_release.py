import csv
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
