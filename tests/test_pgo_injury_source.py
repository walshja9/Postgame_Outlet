import copy
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pgo_challenger
import pgo_injury_source
import pgo_model


AS_OF = "2026-08-25T12:00:00-04:00"
LAR_SOURCE = "https://www.therams.com/team/injury-report/"
GB_SOURCE = "https://www.packers.com/news/preseason-availability"


class InjurySourceImporterTests(unittest.TestCase):
    def _snapshot(self):
        team_sources = []
        for team in pgo_model.CURRENT_TEAMS:
            source = {
                "team": team,
                "source_url": f"https://www.nfl.com/teams/{team.lower()}/",
                "source_kind": "no_formal_report",
                "source_published_at": "",
                "target_game": "2026 PRE3",
                "coverage_note": "Official team source checked; no formal report posted",
            }
            if team == "LAR":
                source.update({
                    "source_url": LAR_SOURCE,
                    "source_kind": "formal_injury_report",
                    "source_published_at": "2026-08-24T18:00:00-07:00",
                    "coverage_note": "Official club injury report checked",
                })
            elif team == "GB":
                source.update({
                    "source_url": GB_SOURCE,
                    "source_kind": "preseason_availability_list",
                    "source_published_at": "2026-08-24T14:00:00-05:00",
                    "coverage_note": "Official club preseason availability list checked",
                })
            team_sources.append(source)
        return {
            "source": "Official NFL club preseason availability sources",
            "source_as_of": AS_OF,
            "team_sources": team_sources,
            "players": [{
                "team": "LAR",
                "gsis_id": "00-0039075",
                "player": "Puka Nacua",
                "position": "WR",
                "source_url": LAR_SOURCE,
                "injury": "knee",
                "practice_status": "Limited Participation",
                "game_status": "Questionable",
                "availability_text": "",
            }, {
                "team": "GB",
                "gsis_id": "00-0036265",
                "player": "Jordan Love",
                "position": "QB",
                "source_url": GB_SOURCE,
                "injury": "",
                "practice_status": "",
                "game_status": "",
                "availability_text": "Will not suit up in the preseason game",
            }],
        }

    def _write_snapshot(self, directory, snapshot):
        path = Path(directory) / "injury_snapshot.json"
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        return path

    def test_import_filters_editorial_rows_and_reconciles_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = self._write_snapshot(directory, self._snapshot())
            overlay_path = Path(directory) / "availability.csv"
            coverage_path = Path(directory) / "coverage.json"

            result = pgo_injury_source.import_snapshot(
                source_path, overlay_path, coverage_path
            )

            self.assertEqual(result["source_player_count"], 2)
            self.assertEqual(result["overlay_row_count"], 1)
            self.assertEqual(result["excluded_player_count"], 1)
            self.assertEqual(result["teams_with_overlay_players"], ["LAR"])
            self.assertEqual(result["teams_processed"], list(pgo_model.CURRENT_TEAMS))
            with overlay_path.open(encoding="utf-8", newline="") as handle:
                overlay = list(csv.DictReader(handle))
            self.assertEqual(overlay[0]["availability_probability"], "0.70")
            self.assertEqual(
                overlay[0]["source_note"],
                f"Official injury report: knee; practice=Limited Participation; "
                f"game=Questionable; source={LAR_SOURCE}",
            )
            self.assertEqual(tuple(overlay[0]), pgo_challenger.AVAILABILITY_COLUMNS)

            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            self.assertEqual(
                coverage["raw_source_sha256"],
                hashlib.sha256(source_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(len(coverage["team_sources"]), 32)
            self.assertEqual(coverage["team_source_player_counts"]["GB"], 1)
            self.assertEqual(coverage["team_row_counts"]["GB"], 0)
            self.assertEqual(coverage["team_row_counts"]["LAR"], 1)
            self.assertEqual(coverage["team_excluded_counts"]["GB"], 1)
            self.assertEqual(coverage["source_player_count"], 2)
            self.assertEqual(coverage["player_row_count"], 1)
            self.assertEqual(coverage["excluded_player_count"], 1)
            self.assertEqual(coverage["overlay_player_keys"], [{
                "team": "LAR", "gsis_id": "00-0039075",
            }])
            self.assertEqual(coverage["exclusions"][0]["team"], "GB")
            self.assertEqual(
                coverage["exclusions"][0]["reason"],
                "preseason_availability_list is editorial-only",
            )

    def test_import_rejects_invalid_source_semantics(self):
        snapshot = self._snapshot()
        cases = []

        duplicate_team = copy.deepcopy(snapshot)
        duplicate_team["team_sources"].append(
            copy.deepcopy(duplicate_team["team_sources"][0])
        )
        cases.append((
            "duplicate team", duplicate_team, "Duplicate injury source team",
        ))

        wrong_source = copy.deepcopy(snapshot)
        wrong_source["players"][0]["source_url"] = GB_SOURCE
        cases.append(("wrong source", wrong_source, "does not match team source"))

        unknown_kind = copy.deepcopy(snapshot)
        unknown_kind["team_sources"][0]["source_kind"] = "rumor"
        cases.append(("unknown kind", unknown_kind, "Unknown injury source kind"))

        no_report_player = copy.deepcopy(snapshot)
        lar_source = next(
            row for row in no_report_player["team_sources"] if row["team"] == "LAR"
        )
        lar_source["source_kind"] = "no_formal_report"
        cases.append(("no report player", no_report_player, "cannot list players"))

        future_source = copy.deepcopy(snapshot)
        future_source["team_sources"][0]["source_published_at"] = (
            "2026-08-26T12:00:00-04:00"
        )
        cases.append(("future source", future_source, "later than snapshot"))

        naive_capture = copy.deepcopy(snapshot)
        naive_capture["source_as_of"] = "2026-08-25T12:00:00"
        cases.append(("naive capture", naive_capture, "timezone"))

        with tempfile.TemporaryDirectory() as directory:
            for label, invalid, message in cases:
                with self.subTest(label=label):
                    source_path = self._write_snapshot(directory, invalid)
                    with self.assertRaisesRegex(ValueError, message):
                        pgo_injury_source.load_snapshot(source_path)

    def test_generated_overlay_passes_reconciled_coverage_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = self._write_snapshot(directory, self._snapshot())
            overlay_path = Path(directory) / "availability.csv"
            coverage_path = Path(directory) / "coverage.json"
            pgo_injury_source.import_snapshot(
                source_path, overlay_path, coverage_path
            )

            overlay, receipt = pgo_challenger.load_availability_overlay(
                overlay_path, AS_OF, coverage_path=coverage_path
            )

        self.assertEqual(
            overlay[("LAR", "00-0039075")]["availability_probability"], 0.70
        )
        self.assertTrue(receipt["coverage"]["passed"])
        self.assertEqual(
            receipt["coverage"]["teams_processed"],
            sorted(pgo_model.CURRENT_TEAMS),
        )


if __name__ == "__main__":
    unittest.main()
