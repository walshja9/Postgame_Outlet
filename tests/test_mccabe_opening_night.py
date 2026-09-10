import csv
import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_site
import pgo_comparison
import snapshot


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "research/pgo_opening_night_20260909/mccabe-dashboard-reference.html"
EXPECTED_REFERENCE_SHA256 = "0703d91894c1bc3c57dc7f19989e4ac231edc18162c41ca56425dbc699182da4"


class McCabeOpeningNightTests(unittest.TestCase):
    def test_current_starters_do_not_reappear_as_backups(self):
        starters, backups = generate_site.load_qbs()
        self.assertEqual(len(starters), 32)
        self.assertEqual(len(backups), 18)
        self.assertFalse({row["name"] for row in starters} & {row["name"] for row in backups})
        tua = next(row for row in starters if row["name"] == "Tua Tagovailoa")
        self.assertEqual((tua["age"], tua["exp"]), ("28", "6"))

    def test_comparison_uses_the_active_config_edition_snapshot(self):
        rows = [{"team": "Alpha", "rating": 1.0}]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, "snapshots.json")
            snapshot.save_snaps({
                "Week 1 2026 - McCabe Sep 9": {
                    "published_at": "2026-09-09T15:00:00-04:00",
                    "rows": rows,
                    "corrections": [],
                }
            }, path)
            with patch.object(
                generate_site,
                "load_config",
                return_value={"edition": "Week 1 2026 - McCabe Sep 9"},
            ):
                metadata = pgo_comparison.load_mccabe_snapshot(path, rows)
        self.assertEqual(metadata["mccabe_edition"], "Week 1 2026 - McCabe Sep 9")

    def test_supplied_grades_and_writeups_are_preserved_exactly(self):
        source = REFERENCE.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), EXPECTED_REFERENCE_SHA256)
        document = source.decode("utf-8")
        row_pattern = re.compile(
            r'<tr class="row"[^>]*>\s*<td class="rk">(?P<rank>\d+)</td>\s*'
            r'<td class="tm">.*?<span class="nm">(?P<team>.*?)</span>'
            r'<span class="qbn">(?P<qb_name>.*?)</span></td>\s*'
            r'<td class="n">(?P<qb>.*?)</td><td class="n">(?P<off>.*?)</td>'
            r'<td class="n">(?P<defense>.*?)</td>\s*'
            r'<td class="rate">(?P<rating>.*?)</td>.*?</tr>\s*'
            r'<tr class="drawer"[^>]*><td colspan="8"><div class="wu">'
            r'(?P<writeup>.*?)</div></td></tr>',
            re.S,
        )
        supplied = list(row_pattern.finditer(document))
        self.assertEqual(len(supplied), 32)

        with (ROOT / "data/ratings.csv").open(encoding="utf-8", newline="") as handle:
            current = {row["team"]: row for row in csv.DictReader(handle)}
        self.assertEqual(set(current), {match["team"] for match in supplied})
        for match in supplied:
            team = match["team"]
            row = current[team]
            with self.subTest(team=team):
                self.assertEqual(row["qb_name"], match["qb_name"])
                for field, source_field in (
                    ("qb_value", "qb"), ("off_value", "off"), ("def_value", "defense")
                ):
                    self.assertEqual(f'{float(row[field]):+.1f}', match[source_field])
                total = sum(float(row[field]) for field in ("qb_value", "off_value", "def_value"))
                self.assertEqual(f"{total:+.1f}", match["rating"])

    def test_generated_board_has_accessible_signed_scale_and_mobile_column_control(self):
        rows = generate_site.load_teams(generate_site.load_prior())
        document = generate_site.build_html(
            rows,
            {"season": "2026", "edition": "Opening Night 2026", "author": "Sean McCabe"},
        )
        self.assertEqual(document.count('class="rating-bar"'), 32)
        self.assertIn('role="img" aria-label="Total rating +7.6 on a -8 to +8 scale"', document)
        self.assertIn('<span aria-hidden="true">-8</span><span>Rating scale</span><span aria-hidden="true">+8</span>', document)
        self.assertIn('id="ratings-columns" type="checkbox"', document)
        self.assertIn("panelRatings.classList.toggle('show-details', event.target.checked)", document)
        self.assertIn('class="mobile-qb">Matthew Stafford</span>', document)
        self.assertIn('aria-haspopup="dialog"', document)
        self.assertIn("McCabe&#x27;s editorial ratings", document)
        self.assertNotIn("Preseason &middot; roster-based", document)

        self.assertIn('class="rating-fill pos" style="left:50%;width:47.5%"', generate_site.rating_bar(7.6))
        self.assertIn('class="rating-fill neg" style="right:50%;width:25.0%"', generate_site.rating_bar(-4.0))
        self.assertIn('class="rating-fill zero" style="left:50%;width:0.0%"', generate_site.rating_bar(0.0))

    def test_injury_status_and_markdown_links_are_explicit_and_safe(self):
        block = generate_site.build_injury_status({
            "injury_checked_at": "2026-09-09T14:49:44+00:00",
            "injury_status": "Four teams have formal reports; 28 teams remain unknown. Final inactives are pending.",
            "injury_source_url": "https://www.nfl.com/injuries/",
        })
        self.assertIn("Official injury report coverage checked as of", block)
        self.assertIn("September 9, 2026 at 10:49 AM ET", block)
        self.assertIn("<summary>Injuries checked September 9, 2026 at 10:49 AM ET &middot; final inactives pending</summary>", block)
        self.assertIn("Four teams have formal reports; 28 teams remain unknown", block)
        self.assertIn('href="https://www.nfl.com/injuries/"', block)
        self.assertIn(
            '<a href="https://www.nfl.com/news/example">official update</a>',
            generate_site.md_to_html("[official update](https://www.nfl.com/news/example)"),
        )
        self.assertNotIn("<a ", generate_site.md_to_html("[unsafe](javascript:alert(1))"))
        with self.assertRaisesRegex(ValueError, "timezone"):
            generate_site.build_injury_status({
                "injury_checked_at": "2026-09-09T14:49:44",
                "injury_status": "Partial coverage.",
                "injury_source_url": "https://www.nfl.com/injuries/",
            })


if __name__ == "__main__":
    unittest.main()
