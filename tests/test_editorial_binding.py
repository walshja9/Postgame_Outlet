import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_site
import results


class QuarterbackWriteupTests(unittest.TestCase):
    def test_team_section_binds_to_selected_quarterback(self):
        with tempfile.TemporaryDirectory() as temp:
            writeups = Path(temp)
            (writeups / "CHI.md").write_text(
                "## Quarterback\n\nCaleb Williams (+3.0) led the Week 1 offense.\n\n"
                "## Risk\n\nOther text.", encoding="utf-8"
            )
            with patch.object(generate_site, "WRITEUPS", temp), patch.object(
                generate_site, "QB_WRITEUPS", str(writeups / "qb")
            ):
                self.assertEqual(generate_site.load_qb_writeup("Case Keenum", "CHI", -4.5), "")
                self.assertIn("Caleb Williams", generate_site.load_qb_writeup("Caleb Williams", "CHI", 3.0))

    def test_same_player_with_stale_opening_value_uses_note_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "CHI.md").write_text(
                "## Quarterback\n\nCase Keenum (−3.0) was the old grade.", encoding="utf-8"
            )
            with patch.object(generate_site, "WRITEUPS", temp), patch.object(
                generate_site, "QB_WRITEUPS", str(Path(temp, "qb"))
            ):
                self.assertEqual(generate_site.load_qb_writeup("Case Keenum", "CHI", -4.5), "")
                detail = generate_site.build_qb_detail(
                    {"name": "Case Keenum", "team": "Chicago Bears", "val": -4.5,
                     "notes": "Current selection note"}, "starter", 1
                )
                self.assertIn("Current selection note", detail)
                self.assertNotIn("old grade", detail)

    def test_surname_only_lead_does_not_bind_another_player(self):
        with tempfile.TemporaryDirectory() as temp:
            writeups = Path(temp, "writeups")
            overrides = Path(temp, "qb_writeups")
            writeups.mkdir()
            overrides.mkdir()
            (writeups / "BUF.md").write_text(
                "## Quarterback\n\nAllen (+6.5) powers Buffalo.", encoding="utf-8"
            )
            (overrides / "case-keenum.md").write_text("Keenum-specific analysis.", encoding="utf-8")
            with patch.object(generate_site, "WRITEUPS", str(writeups)), patch.object(
                generate_site, "QB_WRITEUPS", str(overrides)
            ):
                self.assertEqual(generate_site.load_qb_writeup("Josh Allen", "BUF", 6.5), "")
                self.assertEqual(generate_site.load_qb_writeup("Kyle Allen", "BUF", 6.5), "")
                self.assertIn("Keenum-specific", generate_site.load_qb_writeup("Case Keenum", "BUF", -4.5))

    def test_every_current_qb_section_matches_selected_name_and_value(self):
        with Path(generate_site.DATA, "ratings.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 32)
        for row in rows:
            team = generate_site.TEAM[row["team"]][0]
            with self.subTest(team=team):
                self.assertTrue(generate_site.load_qb_writeup(
                    row["qb_name"], team, float(row["qb_value"])
                ))


class RetrospectiveResultsTests(unittest.TestCase):
    def test_cli_and_json_disclose_current_rating_regrade(self):
        payload = {"events": [{
            "id": "game-1", "date": "2026-09-14T17:00Z",
            "competitions": [{
                "status": {"type": {"completed": True, "name": "STATUS_FINAL"}},
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Home"}, "score": "17"},
                    {"homeAway": "away", "team": {"displayName": "Away"}, "score": "10"},
                ],
                "odds": [{"spread": -3.0}],
            }],
        }]}
        with patch.object(results, "fetch_json", return_value=payload):
            games = results.build_week(2, 2026, {"Home": 2.0, "Away": 0.0}, {}, 1.5, with_box=False)
        self.assertEqual(games[0]["my_spread"], -3.5)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            results.print_week(games, 2)
        self.assertIn("RETROSPECTIVE", output.getvalue())
        self.assertIn("current ratings", output.getvalue().lower())
        self.assertIn("Retrospective McCabe Method ATS", output.getvalue())

        with patch.object(results, "load_config", return_value={"season": "2026"}), \
             patch.object(results, "load_ratings", return_value={"Home": 2.0, "Away": 0.0}), \
             patch.object(results, "load_hfa", return_value=({}, 1.5)), \
             patch.object(results, "build_week", return_value=games), \
             patch.object(results.sys, "argv", ["results.py", "2", "--json"]), \
             contextlib.redirect_stdout(output := io.StringIO()):
            results.main()
        self.assertEqual(json.loads(output.getvalue())["grading_basis"], "retrospective_current_ratings")


if __name__ == "__main__":
    unittest.main()
