import hashlib
import csv
import io
import json
import math
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pgo_challenger
import pgo_comparison
from tests.test_pgo_fantasy_prospective import ProspectiveFantasyFixture


class RatingExplanationTests(unittest.TestCase):
    def setUp(self):
        self.page = pgo_comparison.pgo_current_board.strip_current_board(
            pgo_comparison.PUBLIC_OUTPUT.read_text(encoding="utf-8"))
        self.receipt = pgo_comparison.validate_receipt(json.loads(
            pgo_comparison.BACKTEST_PATH.read_text(encoding="utf-8")))
        self.rows = pgo_comparison.load_model_rows(
            pgo_comparison.MODEL_PATH, self.receipt)

    def test_all_saved_groups_are_centered_and_source_backed(self):
        self.assertTrue(callable(getattr(pgo_comparison, "add_rating_explanations", None)))
        result = pgo_comparison.add_rating_explanations(self.page)
        roster_mean = sum(float(row["roster_coaching_points"]) for row in self.rows) / 32
        templates = dict(re.findall(
            r'<template id="pgo-explanation-([A-Z]+)">(.*?)</template>', result, re.S))
        self.assertEqual(set(templates), {row["team"] for row in self.rows})
        centered = []
        for row in self.rows:
            detail = templates[row["team"]]
            values = {key: float(value) for key, value in re.findall(
                r'<dd data-component="([^"]+)" data-value="([^"]+)">', detail)}
            roster = float(row["roster_coaching_points"]) - roster_mean
            self.assertAlmostEqual(values["roster"], roster, places=10)
            self.assertAlmostEqual(values["performance"] + values["roster"],
                                   row["full_strength_rating"], places=10)
            centered.append(values["roster"])
            self.assertIn("2026-07-21T12:00:00-04:00", detail)
            self.assertIn("Experimental model", detail)
            self.assertIn("HOLD", detail)
        self.assertAlmostEqual(sum(centered), 0, places=10)
        for text in ("neutral-field", "league-average", "July 21, 2026", "PGO lineup",
                     "Performance contribution", "Roster/coaching contribution",
                     "starting-QB/depth", "feature-level", "correlated", "fitted to game margins",
                     "QB + non-QB offense + defense", "PGO vs McCabe", "Closest agreements",
                     "Biggest disagreements", "PGO higher", "McCabe higher"):
            self.assertIn(text, result)
        self.assertNotIn("PGO today", pgo_comparison.extract_comparison_panel(result))
        self.assertNotIn("Rating gap", pgo_comparison.extract_comparison_panel(result))
        self.assertIn("openDrawer(template.innerHTML, trigger)", result)
        self.assertEqual(result.count('class="pgo-rating-trigger row-trigger team-trigger"'), 32)

    def test_every_drawer_has_its_dialog_name_and_consistent_displayed_sum(self):
        result = pgo_comparison.add_rating_explanations(self.page)
        dialog_label = re.search(r'id="drawer"[^>]*aria-labelledby="([^"]+)"', result).group(1)
        templates = re.findall(r'<template id="pgo-explanation-([A-Z]+)">(.*?)</template>', result, re.S)
        self.assertEqual(len(templates), 32)
        for team, detail in templates:
            with self.subTest(team=team, check="accessible name"):
                self.assertEqual(len(re.findall(rf'<h2 id="{dialog_label}">[^<]+</h2>', detail)), 1)
            with self.subTest(team=team, check="displayed sum"):
                shown = {key: Decimal(value) for key, value in re.findall(
                    r'<dd data-component="([^"]+)" data-value="[^"]+">([^<]+)</dd>', detail)}
                self.assertEqual(shown["performance"] + shown["roster"], shown["full_strength"])

    def test_long_explanations_are_collapsed_and_metadata_wrapper_is_idempotent(self):
        result = pgo_comparison.add_rating_explanations(self.page)
        self.assertIn('forecast-lab.html#model-sensitivity', result)
        self.assertIn('Calibrated uncertainty: unavailable', result)
        self.assertIn('Source freshness', result)
        panel = pgo_comparison.extract_comparison_panel(result)
        self.assertEqual(panel.count('<details class="pgo-rank-disclosure">'), 1)
        self.assertIn('<summary>Where PGO and McCabe agree and disagree</summary>', panel)
        self.assertEqual(panel.count('<details class="pgo-comparison-metadata">'), 1)
        metadata = re.search(r'<p class="comparison-summary">.*?</p>', self.page, re.S).group(0)
        self.assertIn('<summary>Snapshot dates and backtest</summary>' + metadata + '</details>', panel)
        primer = re.search(r'<p class="pgo-rating-meaning">(.*?)</p>', panel, re.S).group(1)
        self.assertLess(len(primer), 650)
        self.assertNotIn('CSV', primer)
        self.assertEqual(pgo_comparison.add_rating_explanations(result), result)

    def test_archived_team_takeaways_precede_values_and_link_issued_edition(self):
        page = pgo_comparison.add_rating_explanations(self.page)
        for team, performance, roster in [('NE', '+6.417', '+0.583'), ('JAX', '+6.018', '+0.263')]:
            template = page.split(f'<template id="pgo-explanation-{team}">', 1)[1].split('</template>', 1)[0]
            intro = template.split('<dl>', 1)[0]
            self.assertIn('Archived July 21, 2026', intro)
            self.assertIn(performance, intro)
            self.assertIn(roster, intro)
            self.assertIn(f'forecast-lab.html#rating-{team}', template)
            self.assertIn('<details><summary>How these saved contributions are calculated</summary>', template)
        self.assertIn('Unadopted research', page)

    def test_idempotent_preserves_numeric_cells_fantasy_and_refresh(self):
        result = pgo_comparison.add_rating_explanations(self.page)
        self.assertEqual(pgo_comparison.add_rating_explanations(result), result)
        before = pgo_comparison.extract_comparison_panel(self.page)
        after = pgo_comparison.extract_comparison_panel(result)
        old_cells = re.findall(r'<td\b.*?</td>', before)
        if "Rating gap" in before:
            old_cells = [cell for index, cell in enumerate(old_cells) if index % 9 != 8]
        self.assertEqual(old_cells, re.findall(r'<td\b.*?</td>', after))
        self.assertEqual(pgo_comparison._extract_published_fantasy_panel(self.page),
                         pgo_comparison._extract_published_fantasy_panel(result))
        refreshed = pgo_comparison.refresh_mccabe_page(ComparisonTests._base_html(), result)
        self.assertEqual(pgo_comparison.add_rating_explanations(refreshed), refreshed)
        component_values = r'data-component="([^"]+)" data-value="([^"]+)"'
        self.assertEqual(re.findall(component_values, result),
                         re.findall(component_values, refreshed))

    def test_legacy_and_current_refresh_recompute_rank_highlights(self):
        current = pgo_comparison.load_mccabe_rows(pgo_comparison.MCCABE_PATH)
        current[0]["rank"], current[-1]["rank"] = current[-1]["rank"], current[0]["rank"]
        current[0]["rating"] = -20.0
        for page in (self.page, pgo_comparison.add_rating_explanations(self.page)):
            with self.subTest(enriched='PGO EXPLANATIONS START' in page), patch.object(
                    pgo_comparison, "load_mccabe_rows", return_value=current):
                refreshed = pgo_comparison.refresh_mccabe_page(ComparisonTests._base_html(), page)
            result = pgo_comparison.add_rating_explanations(refreshed)
            panel = pgo_comparison.extract_comparison_panel(result)
            self.assertNotIn("Rating gap", panel)
            self.assertEqual(len(re.findall(r'<td data-sort=', panel)), 32 * 8)
            self.assertIn('data-sort="-20.0">-20.0</td>', panel)
            highlights = re.search(r'<div class="pgo-rank-highlights">.*?</div>', panel, re.S).group(0)
            before = re.search(r'<div class="pgo-rank-highlights">.*?</div>',
                               pgo_comparison.add_rating_explanations(self.page), re.S).group(0)
            self.assertNotEqual(highlights, before)
            source = {row["team"]: row for row in self.rows}
            for row in current:
                self.assertIn(f'{row["team"]}: PGO #{source[row["abbr"]]["rank"]}, McCabe #{row["rank"]}',
                              result)
            self.assertEqual(pgo_comparison._extract_published_fantasy_panel(
                                 pgo_comparison.strip_current_injury_notes(self.page)),
                             pgo_comparison._extract_published_fantasy_panel(
                                 pgo_comparison.strip_current_injury_notes(result)))

    def test_rejects_invalid_components_and_source_algebra(self):
        with pgo_comparison.MODEL_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        for field, value in (("performance_points", "nan"),
                             ("roster_coaching_points", "inf"),
                             ("performance_points", "123.0")):
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as temp:
                changed = [dict(row) for row in rows]
                changed[0][field] = value
                path = Path(temp) / "ratings.csv"
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(changed)
                with self.assertRaises(ValueError):
                    pgo_comparison.add_rating_explanations(self.page, model_path=path)

    def test_rejects_mismatched_and_duplicate_public_rows(self):
        panel = pgo_comparison.extract_comparison_panel(self.page)
        row = re.search(r'<tr><th scope="row" data-sort=.*?</tr>', panel, re.S).group(0)
        for changed in (re.sub(r'<td data-sort="[^"]+">', '<td data-sort="999">', row, count=1),
                        row + row):
            with self.subTest(changed=changed[:70]), self.assertRaises(ValueError):
                pgo_comparison.add_rating_explanations(self.page.replace(row, changed, 1))


class ComparisonTests(unittest.TestCase):
    @staticmethod
    def _saved_comparison_rows():
        receipt = json.loads(pgo_comparison.BACKTEST_PATH.read_text(encoding="utf-8"))
        return pgo_comparison.build_comparison_rows(
            pgo_comparison.load_mccabe_rows(pgo_comparison.MCCABE_PATH),
            pgo_comparison.load_model_rows(pgo_comparison.MODEL_PATH, receipt))

    @staticmethod
    def _base_html():
        return (
            '<html><head><meta name="description" content="Sean McCabe’s board">'
            "<style>base</style></head><body>"
            '<div class="updated">By Sean McCabe &middot; Edition</div>'
            '    <button type="button" class="tab active" id="tab-ratings" '
            'role="tab" aria-selected="true" aria-controls="panel-ratings" '
            'tabindex="0" data-panel="ratings">Power Ratings</button>'
            '<button type="button" class="tab" id="tab-qbs" role="tab" '
            'aria-selected="false" aria-controls="panel-qbs" tabindex="-1" '
            'data-panel="qbs" style="display:block">QB Ratings</button>'
            '<button type="button" class="tab" id="tab-method" role="tab" '
            'aria-selected="false" aria-controls="panel-method" tabindex="-1" '
            'data-panel="method">Methodology</button>'
            '  <section class="panel active" id="panel-ratings" '
            'role="tabpanel" aria-labelledby="tab-ratings">McCabe</section>'
            '<section class="panel" id="panel-qbs" role="tabpanel" '
            'aria-labelledby="tab-qbs" hidden>QBs</section>'
            '<section class="panel" id="panel-method" role="tabpanel" '
            'aria-labelledby="tab-method" hidden>Method</section>'
            "</body></html>"
        )

    @staticmethod
    def _panel_inner(document, panel_id):
        match = re.search(
            rf'<section\b[^>]* id="{panel_id}"[^>]*>(.*?)</section>',
            document,
            re.S,
        )
        if match is None:
            raise AssertionError(f"Missing panel: {panel_id}")
        return match.group(1)

    @staticmethod
    def _held_receipt():
        checks = {name: True for name in pgo_challenger.GATE_CHECK_NAMES}
        checks["aggregate_improvement_ci_positive"] = False
        return {
            "status": "HOLD",
            "publication_status": "EXPERIMENTAL",
            "failed_checks": ["aggregate_improvement_ci_positive"],
            "checks": checks,
            "as_of": "2026-07-21T12:00:00-04:00",
            "version": "pgo_v1",
            "mccabe_edition": "Preseason 2026",
            "mccabe_published_at": "2026-07-16T11:22:52-04:00",
            "metrics": {
                "pgo_v0": {"mae": 10.266150},
                "challenger": {"mae": 10.205173},
            },
            "aggregate_interval": {
                "mean": 0.060977,
                "lower": -0.024395,
                "upper": 0.144917,
            },
            "receipt_ref": "test-receipt-ref",
        }

    @staticmethod
    def _fantasy_preview():
        config_sha256 = "a" * 64

        def row(
            gsis_id,
            player_name,
            position,
            team,
            opponent,
            strong_prediction,
            position_rank,
            flex_rank,
            superflex_rank,
            *,
            qb_depth_rank=None,
            ranking_eligible=True,
            history_count=1,
        ):
            return {
                "season": 2026,
                "week": 1,
                "game_id": "2026_01_BUF_LAR",
                "gsis_id": gsis_id,
                "player_name": player_name,
                "team": team,
                "opponent": opponent,
                "position": position,
                "null_prediction": strong_prediction - 1.0,
                "strong_prediction": strong_prediction,
                "history_count": history_count,
                "initialization_reason": (
                    "HISTORY" if history_count else "TRUE_COLD_START"
                ),
                "availability_status": "UNVERIFIED",
                "qb_depth_rank": qb_depth_rank,
                "ranking_eligible": ranking_eligible,
                "config_sha256": config_sha256,
                "position_rank": position_rank,
                "flex_rank": flex_rank,
                "superflex_rank": superflex_rank,
            }

        return {
            "schema_version": 1,
            "artifact_kind": "PGO_FANTASY_WEEKLY_PREVIEW",
            "artifact_sha256": "b" * 64,
            "config_sha256": config_sha256,
            "evidence_mode": "PREVIEW",
            "generated_at": "2026-09-03T13:52:56-04:00",
            "gradeable": False,
            "model_version": "pgo_fantasy_2026_baseline_v2",
            "publication_status": "EXPERIMENTAL",
            "season": 2026,
            "source_coverage": {
                "roster": {"processed": ["BUF", "LAR"], "missing": []},
                "availability": {
                    "processed": [],
                    "missing": ["BUF", "LAR"],
                },
                "depth": {"processed": ["BUF", "LAR"], "missing": []},
            },
            "status": "HOLD",
            "teams_missing": [],
            "teams_processed": ["BUF", "LAR"],
            "week": 1,
            "rows": [
                row(
                    "qb-buf",
                    "Buffalo QB",
                    "QB",
                    "BUF",
                    "LAR",
                    20.0,
                    1,
                    None,
                    1,
                    qb_depth_rank=1,
                ),
                row(
                    "qb-buf-backup",
                    "Buffalo Backup",
                    "QB",
                    "BUF",
                    "LAR",
                    19.0,
                    None,
                    None,
                    None,
                    qb_depth_rank=2,
                    ranking_eligible=False,
                ),
                row(
                    "rb-lar",
                    "Los Angeles RB",
                    "RB",
                    "LAR",
                    "BUF",
                    15.0,
                    1,
                    1,
                    2,
                ),
                row(
                    "wr-buf",
                    "Rookie <script>alert(1)</script>",
                    "WR",
                    "BUF",
                    "LAR",
                    14.0,
                    1,
                    2,
                    3,
                    history_count=0,
                ),
                row(
                    "te-lar",
                    "Los Angeles TE",
                    "TE",
                    "LAR",
                    "BUF",
                    10.0,
                    1,
                    3,
                    4,
                ),
            ],
        }

    def test_mccabe_review_flag_blocks_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ratings.csv"
            path.write_text(
                "team,qb_value,off_value,def_value,needs_review\n"
                "Buffalo Bills,6.5,1.0,-0.5,Y\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "needs_review=Y"):
                pgo_comparison.load_mccabe_rows(path)

    def test_mccabe_source_timestamp_rejects_shallow_checkout(self):
        result = type("Result", (), {"stdout": "true\n"})()
        with patch.object(pgo_comparison.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "full Git history"):
                pgo_comparison.mccabe_source_timestamp(pgo_comparison.MCCABE_PATH)

    def test_mccabe_loader_keeps_selected_quarterbacks(self):
        source = pgo_comparison.load_release_rows(pgo_comparison.MCCABE_PATH)
        for index, row in enumerate(source):
            row['qb_name'] = f'QB <{index}>'
        with patch.object(pgo_comparison, 'load_release_rows', return_value=source):
            rows = pgo_comparison.load_mccabe_rows(pgo_comparison.MCCABE_PATH)
        self.assertEqual({row['team']: row['qb_name'] for row in rows},
                         {row['team']: row['qb_name'] for row in source})

    def test_comparison_calculates_both_model_ranks_and_disagreements(self):
        mccabe = [
            {"team": "Buffalo Bills", "abbr": "BUF", "rank": 1, "rating": 7.0},
            {"team": "Miami Dolphins", "abbr": "MIA", "rank": 2, "rating": -4.5},
        ]
        model = [
            {
                "team": "MIA", "rank": 1,
                "full_strength_rating": 1.0, "availability_adjustment": -2.0,
                "current_lineup_rating": -1.0, "headline_view": "full_strength",
                "headline_rating": 1.0,
            },
            {
                "team": "BUF", "rank": 2,
                "full_strength_rating": 0.5, "availability_adjustment": 2.0,
                "current_lineup_rating": 2.5, "headline_view": "full_strength",
                "headline_rating": 0.5,
            },
        ]

        rows = pgo_comparison.build_comparison_rows(mccabe, model)

        buffalo = next(row for row in rows if row["team"] == "Buffalo Bills")
        self.assertEqual(buffalo["current_lineup_rank"], 1)
        self.assertEqual(buffalo["rank_disagreement"], 1)
        self.assertEqual(buffalo["rating_disagreement"], -6.5)

    def test_blocked_or_mislabeled_receipt_is_rejected(self):
        blocked = {
            "status": "BLOCKED", "publication_status": "BLOCKED",
            "failed_checks": ["audit_checks_pass"],
            "checks": {
                name: name != "audit_checks_pass"
                for name in pgo_challenger.GATE_CHECK_NAMES
            },
        }
        with self.assertRaisesRegex(ValueError, "not eligible"):
            pgo_comparison.validate_receipt(blocked)

    def test_panel_exposes_hold_metrics_and_no_third_ranking(self):
        panel = pgo_comparison.render_comparison_panel(
            [{
                "team": "Buffalo Bills", "mccabe_rank": 1,
                "mccabe_rating": 7.0, "full_strength_rank": 2,
                "full_strength_rating": 0.5, "availability_adjustment": 2.0,
                "current_lineup_rank": 1, "current_lineup_rating": 2.5,
                "rank_disagreement": 1, "rating_disagreement": -6.5,
            }],
            self._held_receipt(),
        )
        self.assertIn("Experimental model \N{EM DASH} HOLD", panel)
        self.assertIn("-0.024 to +0.145", panel)
        self.assertNotIn(">PGO v0<", panel)
        self.assertNotIn(">Market<", panel)
        self.assertIn(
            "https://github.com/walshja9/Postgame_Outlet/blob/test-receipt-ref/research/pgo_v1/backtest.json",
            panel,
        )
        self.assertIn(
            "https://github.com/walshja9/Postgame_Outlet/blob/main/docs/superpowers/specs/2026-07-21-independent-forward-looking-pgo-model-design.md",
            panel,
        )
        self.assertEqual(
            panel.count('target="_blank" rel="noopener noreferrer"'),
            2,
        )

    def test_receipt_link_does_not_fall_back_to_main(self):
        receipt = self._held_receipt()
        receipt.pop("receipt_ref")
        panel = pgo_comparison.render_comparison_panel([], receipt)
        self.assertIn("Backtest receipt available on publish", panel)
        self.assertNotIn("/blob/main/research/pgo_v1/backtest.json", panel)

    def test_publish_requires_receipt_and_ratings_at_same_commit(self):
        with patch.object(
            pgo_comparison,
            "immutable_git_ref",
            side_effect=["a" * 40, "b" * 40],
        ):
            with self.assertRaisesRegex(ValueError, "same Git commit"):
                pgo_comparison.require_immutable_artifacts(
                    pgo_comparison.BACKTEST_PATH,
                    pgo_comparison.MODEL_PATH,
                )

    def test_preview_does_not_require_immutable_receipt(self):
        receipt = self._held_receipt()
        receipt.pop("receipt_ref")
        with (
            patch.object(
                pgo_comparison,
                "load_comparison_rows",
                return_value=(self._saved_comparison_rows(), receipt),
            ) as load,
            patch.object(pgo_comparison, "atomic_write_text"),
        ):
            code = pgo_comparison.main(["--output", "output/preview.html"])

        self.assertEqual(code, 0)
        self.assertFalse(load.call_args.kwargs["require_immutable"])

    def test_fantasy_cli_rejects_public_modes_before_loading(self):
        for public_flag in ("--publish", "--refresh-mccabe"):
            with (
                self.subTest(public_flag=public_flag),
                patch.object(
                    pgo_comparison.fantasy_prospective,
                    "load_week1_preview",
                ) as load,
                patch.object(
                    pgo_comparison.generate_site,
                    "load_config",
                ) as load_config,
                patch.object(pgo_comparison, "atomic_write_text") as write,
            ):
                errors = io.StringIO()
                with redirect_stderr(errors):
                    code = pgo_comparison.main([
                        "--fantasy-preview",
                        "frozen.json",
                        public_flag,
                    ])

                self.assertEqual(code, 1)
                self.assertIn("private-only", errors.getvalue())
                load.assert_not_called()
                load_config.assert_not_called()
                write.assert_not_called()

    def test_fantasy_cli_rejects_input_output_alias_before_loading(self):
        same = Path("output") / "same.json"
        with (
            patch.object(
                pgo_comparison.fantasy_prospective,
                "load_week1_preview",
            ) as load,
            patch.object(
                pgo_comparison.generate_site,
                "load_config",
            ) as load_config,
            patch.object(pgo_comparison, "atomic_write_text") as write,
        ):
            errors = io.StringIO()
            with redirect_stderr(errors):
                code = pgo_comparison.main([
                    "--fantasy-preview",
                    str(same),
                    "--output",
                    str(same),
                ])

        self.assertEqual(code, 1)
        self.assertIn("different files", errors.getvalue())
        load.assert_not_called()
        load_config.assert_not_called()
        write.assert_not_called()

    def test_fantasy_cli_validates_before_reading_site_shell(self):
        with (
            patch.object(
                pgo_comparison.fantasy_prospective,
                "load_week1_preview",
                side_effect=ValueError("invalid frozen preview"),
            ) as load,
            patch.object(Path, "read_text") as read,
            patch.object(
                pgo_comparison.generate_site,
                "load_config",
            ) as load_config,
            patch.object(pgo_comparison, "atomic_write_text") as write,
        ):
            errors = io.StringIO()
            with redirect_stderr(errors):
                code = pgo_comparison.main([
                    "--fantasy-preview",
                    "frozen.json",
                    "--output",
                    "output/fantasy/index.html",
                ])

        self.assertEqual(code, 1)
        self.assertIn("invalid frozen preview", errors.getvalue())
        load.assert_called_once()
        read.assert_not_called()
        load_config.assert_not_called()
        write.assert_not_called()

    def test_fantasy_cli_writes_only_private_output(self):
        fantasy = self._fantasy_preview()
        comparison = pgo_comparison.render_comparison_panel(
            self._saved_comparison_rows(), self._held_receipt()
        )
        existing = pgo_comparison.inject_comparison(
            self._base_html(), comparison
        )

        with tempfile.TemporaryDirectory() as temp:
            public = Path(temp) / "index.html"
            public.write_text(existing, encoding="utf-8")
            with (
                patch.object(
                    pgo_comparison.fantasy_prospective,
                    "load_week1_preview",
                    return_value=fantasy,
                ) as load,
                patch.object(pgo_comparison, "PUBLIC_OUTPUT", public),
                patch.object(
                    pgo_comparison.generate_site,
                    "load_config",
                    return_value={},
                ) as load_config,
                patch.object(
                    pgo_comparison,
                    "load_comparison_rows",
                ) as load_comparison,
                patch.object(pgo_comparison, "atomic_write_text") as write,
            ):
                code = pgo_comparison.main([
                    "--fantasy-preview",
                    "frozen.json",
                    "--output",
                    "output/fantasy/index.html",
                ])

        self.assertEqual(code, 0)
        load.assert_called_once_with(Path("frozen.json").resolve())
        load_config.assert_called_once_with()
        load_comparison.assert_not_called()
        write.assert_called_once()
        target, rendered = write.call_args.args
        self.assertEqual(
            target,
            Path("output/fantasy/index.html").resolve(),
        )
        self.assertIn('id="tab-fantasy"', rendered)
        self.assertIn('id="panel-fantasy"', rendered)
        self.assertIn("Rookie &lt;script&gt;", rendered)
        self.assertIn("McCabe Ratings</button>", rendered)

    def test_mccabe_is_primary_and_pgo_rows_start_in_pgo_rank_order(self):
        rows = [
            {
                "team": "Buffalo Bills", "mccabe_rank": 1,
                "mccabe_rating": 7.0, "full_strength_rank": 2,
                "full_strength_rating": 0.5, "availability_adjustment": 2.0,
                "current_lineup_rank": 1, "current_lineup_rating": 2.5,
                "rank_disagreement": 1, "rating_disagreement": -6.5,
            },
            {
                "team": "Miami Dolphins", "mccabe_rank": 2,
                "mccabe_rating": -4.5, "full_strength_rank": 1,
                "full_strength_rating": 1.0, "availability_adjustment": -2.0,
                "current_lineup_rank": 2, "current_lineup_rating": -1.0,
                "rank_disagreement": -1, "rating_disagreement": 5.5,
            },
        ]
        panel = pgo_comparison.render_comparison_panel(
            rows, self._held_receipt()
        )

        output = pgo_comparison.inject_comparison(self._base_html(), panel)

        tab_ids = ["tab-ratings", "tab-qbs", "tab-method", "tab-comparison"]
        self.assertEqual(
            sorted(tab_ids, key=lambda tab_id: output.index(f'id="{tab_id}"')),
            tab_ids,
        )
        self.assertIn('class="tab active" id="tab-ratings"', output)
        self.assertIn(
            'aria-selected="true" aria-controls="panel-ratings"', output
        )
        self.assertIn('class="panel active" id="panel-ratings"', output)
        self.assertIn('class="tab" id="tab-comparison"', output)
        self.assertIn(
            'aria-selected="false" aria-controls="panel-comparison"', output
        )
        self.assertIn('class="panel" id="panel-comparison"', output)
        self.assertIn('aria-labelledby="tab-comparison" hidden>', output)
        self.assertIn(">McCabe Ratings</button>", output)
        self.assertIn(">McCabe QBs</button>", output)
        self.assertIn(">McCabe Method</button>", output)
        self.assertIn("By Sean McCabe", output)
        self.assertIn('content="Sean McCabe’s board"', output)
        self.assertNotIn("By Postgame Outlet Model", output)
        self.assertLess(panel.index("Miami Dolphins"), panel.index("Buffalo Bills"))
        self.assertEqual(panel.count('aria-sort="ascending"'), 1)
        self.assertEqual(panel.count('aria-sort="none"'), 9)

    def test_generated_comparison_is_sortable_and_accessible(self):
        panel = pgo_comparison.render_comparison_panel(
            [{
                "team": "Buffalo Bills", "mccabe_rank": 1,
                "mccabe_rating": 7.0, "full_strength_rank": 2,
                "full_strength_rating": 0.5, "availability_adjustment": 2.0,
                "current_lineup_rank": 1, "current_lineup_rating": 2.5,
                "rank_disagreement": 1, "rating_disagreement": -6.5,
            }],
            self._held_receipt(),
        )
        base = self._base_html()
        output = pgo_comparison.inject_comparison(base, panel)

        self.assertEqual(panel.count('class="sort-button"'), 10)
        self.assertEqual(panel.count('aria-sort="ascending"'), 1)
        self.assertEqual(panel.count('aria-sort="none"'), 9)
        self.assertEqual(panel.count("data-sort="), 10)
        self.assertIn('data-sort="buffalo bills"', panel)
        self.assertIn('data-sort="-6.5"', panel)
        self.assertIn(
            'class="visually-hidden comparison-sort-status"', panel
        )
        self.assertIn("document.querySelector('#panel-comparison')", output)
        self.assertIn("const numeric = index !== 0;", output)
        self.assertIn(
            "a.children[0].dataset.sort.localeCompare(",
            output,
        )

    def test_fantasy_panel_is_reader_first_and_excludes_ineligible_rows(self):
        panel = pgo_comparison.render_fantasy_panel(
            self._fantasy_preview()
        )
        reader = panel.split('<details class="fantasy-details" id="fantasy-source-details">', 1)[0]
        self.assertIn('still being tested', reader)
        self.assertNotIn('gradeable', reader)
        self.assertNotIn('PREVIEW / HOLD', reader)
        self.assertEqual(panel, pgo_comparison._plain_fantasy_explanation(panel))

        self.assertEqual(panel.count('class="fantasy-row"'), 4)
        self.assertNotIn("Buffalo Backup", panel)
        self.assertEqual(panel.count('class="fantasy-view-button"'), 7)
        self.assertIn(
            'data-view="SUPERFLEX" aria-pressed="true"',
            panel,
        )
        self.assertIn('id="fantasy-player-search"', panel)
        self.assertIn('id="fantasy-team"', panel)
        self.assertIn('id="fantasy-columns"', panel)
        for label in ("SF#", "Player", "Pos", "Team", "Opp.", "Proj."):
            self.assertIn(f">{label}</button>", panel)
        for label in (
            "Original half-PPR Pos #",
            "Original half-PPR FLEX #",
            "Original half-PPR SF #",
            "Original half-PPR Baseline",
            "Original half-PPR Delta",
            "History",
            "Init",
            "Availability",
        ):
            self.assertIn(f">{label}</button>", panel)
        self.assertIn("PREVIEW / HOLD", panel)
        self.assertIn("pre-lock half-PPR", panel)
        self.assertIn("not gradeable", panel)
        self.assertIn("Player availability is unverified", panel)
        self.assertIn('role="status" aria-live="polite"', panel)
        self.assertIn("2026-09-03T13:52:56-04:00", panel)
        self.assertIn("pgo_fantasy_2026_baseline_v2", panel)
        self.assertIn("b" * 64, panel)
        self.assertIn("a" * 64, panel)
        self.assertIn('data-player-id="qb-buf"', panel)
        self.assertNotIn('data-player-id="qb-buf-backup"', panel)
        self.assertIn('step="any" required', panel)
        self.assertIn('id="fantasy-table-caption"', panel)
        self.assertIn("half-PPR base forecasts", panel)
        self.assertIn("score-adjust the displayed Proj. column", panel)

    def test_league_upgrade_adds_runtime_caption_and_source_labels_to_legacy_panel(self):
        preview = self._fantasy_preview()
        with patch.object(pgo_comparison, "add_fantasy_leagues", side_effect=lambda panel, rows: panel):
            legacy = pgo_comparison.render_fantasy_panel(preview)
        legacy = legacy.replace(' id="fantasy-table-caption"', '').replace("Original half-PPR ", "")
        legacy = legacy.replace("half-PPR base forecasts", "half-PPR projections")
        legacy = legacy.replace("League profiles can score-adjust the displayed Proj. column.", "")
        upgraded = pgo_comparison.add_fantasy_leagues(legacy, preview["rows"])
        self.assertEqual(upgraded.count('id="fantasy-table-caption"'), 1)
        for label in ("Pos #", "FLEX #", "SF #", "Baseline", "Delta"):
            self.assertIn(f">Original half-PPR {label}</button>", upgraded)
        self.assertIn("half-PPR base forecasts", upgraded)
        self.assertIn("score-adjust the displayed Proj. column", upgraded)
        pgo_comparison._validate_fantasy_leagues(upgraded, upgraded)
        with self.assertRaises(ValueError):
            missing = upgraded.replace('id="fantasy-table-caption"', 'id="missing-caption"')
            pgo_comparison._validate_fantasy_leagues(missing, missing)

    @staticmethod
    def _replace_scoring_payload(page, payload):
        match = re.search(
            r'(<script type="application/json" id="fantasy-scoring-data" )'
            r'data-sha256="[0-9a-f]{64}">(.*?)</script>',
            page,
            re.S,
        )
        if match is None:
            raise AssertionError("Fantasy scoring payload was not found")
        data = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=True
        ).replace("<", "\\u003c")
        digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
        return page[:match.start()] + (
            f'{match[1]}data-sha256="{digest}">{data}</script>'
        ) + page[match.end():]

    def _available_scoring_payload(self):
        components = {
            name: 0.0 for name in (
                "passing_yards", "passing_tds", "passing_interceptions",
                "passing_2pt_conversions", "rushing_yards", "rushing_tds",
                "rushing_2pt_conversions", "receptions", "receiving_yards",
                "receiving_tds", "receiving_2pt_conversions",
                "special_teams_tds", "fumbles_lost_total",
            )
        }
        players = {
            row["gsis_id"]: {
                "position": row["position"],
                "points": row["strong_prediction"],
                "components": dict(components),
            }
            for row in self._fantasy_preview()["rows"]
            if row["ranking_eligible"]
        }
        return {"schema_version": 1, "available": True, "players": players}

    def test_league_profile_form_and_source_data_survive_real_refresh(self):
        panel = pgo_comparison.render_fantasy_panel(self._fantasy_preview())
        self.assertIn('id="fantasy-league-form"', panel)
        self.assertIn('data-base-points="20.0"', panel)
        self.assertIn('data-view="LEAGUE"', panel)
        self.assertIn('id="fantasy-scoring-data"', panel)
        with (
            patch.object(pgo_comparison, "load_mccabe_rows", return_value=[]),
            patch.object(pgo_comparison, "mccabe_source_timestamp", return_value="2026-09-07T01:00:00+00:00"),
        ):
            published = pgo_comparison.inject_fantasy_preview(
                pgo_comparison.inject_comparison(self._base_html(),
                    pgo_comparison.render_comparison_panel([], self._held_receipt())), panel)
            refreshed = pgo_comparison.refresh_mccabe_page(self._base_html(), published)
            self.assertEqual(
                self._panel_inner(refreshed, "panel-fantasy"),
                self._panel_inner(panel, "panel-fantasy"),
            )
            for broken in (
                published.replace('id="fantasy-league-form"', 'id="missing-form"'),
                published.replace('id="fantasy-scoring-data"', 'id="missing-data"'),
                published.replace('"available":false', '"available":true'),
            ):
                with self.subTest(broken=broken[-60:]):
                    with self.assertRaisesRegex(ValueError, "league|scoring"):
                        pgo_comparison.refresh_mccabe_page(self._base_html(), broken)

    def test_refresh_upgrades_wr_bonus_controls_and_pinned_legacy_script(self):
        panel = pgo_comparison.render_fantasy_panel(self._fantasy_preview())
        field = re.search(r'<label class="fantasy-field">Extra points per WR reception<input[^>]+></label>', panel)
        self.assertIsNotNone(field)
        legacy_panel = panel.replace(field[0], '').replace('Scoring points and reception bonuses',
                                                         'Scoring points and TE premium')
        published = pgo_comparison.inject_fantasy_preview(
            pgo_comparison.inject_comparison(self._base_html(),
                pgo_comparison.render_comparison_panel([], self._held_receipt())), legacy_panel)
        legacy_script = "\n<script>\n'use strict';\nconst PGOLeague = {};\n</script>\n"
        old_page = published.replace(pgo_comparison.FANTASY_SCRIPT, legacy_script)
        with (
            patch.object(pgo_comparison, "LEGACY_FANTASY_SCRIPT_SHA256",
                         hashlib.sha256(legacy_script.encode()).hexdigest()),
            patch.object(pgo_comparison, "load_mccabe_rows", return_value=[]),
            patch.object(pgo_comparison, "mccabe_source_timestamp", return_value="2026-09-07T01:00:00+00:00"),
        ):
            refreshed = pgo_comparison.refresh_mccabe_page(self._base_html(), old_page)
            self.assertEqual(refreshed.count('name="score_wr_reception_bonus"'), 1)
            self.assertEqual(refreshed.count(pgo_comparison.FANTASY_SCRIPT), 1)
            self.assertEqual(pgo_comparison.refresh_mccabe_page(self._base_html(), refreshed), refreshed)
            self.assertEqual(re.findall(r'<tr class="fantasy-row".*?</tr>', old_page, re.S),
                             re.findall(r'<tr class="fantasy-row".*?</tr>', refreshed, re.S))
            pattern = r'<script type="application/json" id="fantasy-scoring-data".*?</script>'
            self.assertEqual(re.search(pattern, old_page, re.S)[0], re.search(pattern, refreshed, re.S)[0])
            with self.assertRaises(ValueError):
                pgo_comparison.refresh_mccabe_page(self._base_html(), old_page.replace('PGOLeague = {};', 'PGOLeague = {bad: 1};'))

    def test_refresh_rejects_scoring_payload_and_dom_population_drift(self):
        panel = pgo_comparison.render_fantasy_panel(self._fantasy_preview())
        panel = self._replace_scoring_payload(
            panel, self._available_scoring_payload()
        )
        published = pgo_comparison.inject_fantasy_preview(
            pgo_comparison.inject_comparison(
                self._base_html(),
                pgo_comparison.render_comparison_panel([], self._held_receipt()),
            ),
            panel,
        )
        payload_mutations = {
            "missing player": lambda data: data["players"].pop("qb-buf"),
            "wrong position": lambda data: data["players"]["qb-buf"].update(position="RB"),
            "wrong points": lambda data: data["players"]["qb-buf"].update(points=999),
            "missing component": lambda data: data["players"]["qb-buf"]["components"].pop("receptions"),
            "extra component": lambda data: data["players"]["qb-buf"]["components"].update(extra=0),
            "boolean component": lambda data: data["players"]["qb-buf"]["components"].update(receptions=True),
            "nonfinite component": lambda data: data["players"]["qb-buf"]["components"].update(receptions=math.nan),
            "malformed player": lambda data: data["players"].update({"qb-buf": None}),
            "wrong schema": lambda data: data.update(schema_version=2),
        }
        broken_pages = {
            "base points": published.replace(
                'data-player-id="qb-buf" data-base-points="20.0"',
                'data-player-id="qb-buf" data-base-points="999"',
                1,
            ),
            "duplicate id": published.replace(
                'data-player-id="rb-lar"', 'data-player-id="qb-buf"', 1
            ),
            "missing id": published.replace(
                ' data-player-id="qb-buf"', '', 1
            ),
            "changed inactive flag": published.replace('data-inactive="false"', 'data-inactive="true"', 1),
            "missing inactive flag": published.replace(' data-inactive="false"', '', 1),
            "invalid inactive flag": published.replace('data-inactive="false"', 'data-inactive="0"', 1),
            "missing cell": published.replace(
                '<td class="fantasy-league-value" data-sort="">&mdash;</td>',
                '',
                1,
            ),
        }
        for name, mutate in payload_mutations.items():
            data = self._available_scoring_payload()
            mutate(data)
            broken_pages[name] = self._replace_scoring_payload(published, data)
        with (
            patch.object(pgo_comparison, "load_mccabe_rows", return_value=[]),
            patch.object(
                pgo_comparison,
                "mccabe_source_timestamp",
                return_value="2026-09-07T01:00:00+00:00",
            ),
        ):
            for name, broken in broken_pages.items():
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, "league|scoring"):
                        pgo_comparison.refresh_mccabe_page(
                            self._base_html(), broken
                        )

    def test_orphaned_league_version_marker_is_rejected(self):
        orphaned = self._base_html().replace(
            "</body>", '<div data-league-version="1"></div></body>'
        )
        with self.assertRaisesRegex(ValueError, "orphaned"):
            pgo_comparison._extract_published_fantasy_panel(orphaned)

    def test_ui_source_guards_payload_and_activates_saved_fallback_atomically(self):
        source = (pgo_comparison.HERE / "fantasy_league_ui.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("Scoring adjustment data could not be validated", source)
        self.assertIn("scoring.schema_version !== 1", source)
        self.assertIn("function activateStoredProfile", source)
        self.assertIn("scoring: {...PGOLeague.HALF_PPR}", source)
        self.assertIn("the saved league remains unchanged", source)
        self.assertLess(
            source.index("activateStoredProfile(0, remaining)"),
            source.index("profiles = remaining"),
        )

    @unittest.skipUnless(shutil.which("node"), "Node is required for the browser scoring-engine checks")
    def test_league_javascript_behavior(self):
        result = pgo_comparison.subprocess.run(
            [shutil.which("node"), str(pgo_comparison.HERE / "tests/test_fantasy_league.js")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fantasy_panel_escapes_source_text(self):
        preview = self._fantasy_preview()
        preview["rows"][0]["player_name"] = 'D\'Andre "Quoted" & Sons'
        panel = pgo_comparison.render_fantasy_panel(preview)

        self.assertIn(
            "Rookie &lt;script&gt;alert(1)&lt;/script&gt;",
            panel,
        )
        self.assertNotIn("<script>alert(1)</script>", panel)
        self.assertIn("D&#x27;Andre &quot;Quoted&quot; &amp; Sons", panel)
        self.assertIn(
            'data-player="d&#x27;andre &quot;quoted&quot; &amp; sons"',
            panel,
        )
        self.assertNotIn('data-player="d\'andre "quoted" & sons"', panel)

    def test_fantasy_player_row_header_resets_shell_header_presentation(self):
        self.assertIn(
            """#panel-fantasy .fantasy-table tbody .fantasy-player {
  background:transparent; border-bottom:0; color:inherit; font:inherit;
  letter-spacing:normal; text-transform:none; user-select:text;
  text-align:left; white-space:normal; overflow-wrap:anywhere;
}
#panel-fantasy .fantasy-table tbody .fantasy-player:hover {
  background:transparent; color:inherit;
}""",
            pgo_comparison.FANTASY_CSS,
        )

    def test_canonical_week1_preview_loads_into_real_renderer(self):
        fixture = ProspectiveFantasyFixture()
        preview = fixture.week1_site_preview()
        with tempfile.TemporaryDirectory() as directory:
            path = fixture.write_json(
                Path(directory) / "preview.json",
                preview,
                canonical=True,
            )
            loaded = pgo_comparison.fantasy_prospective.load_week1_preview(path)

        panel = pgo_comparison.render_fantasy_panel(loaded)
        self.assertIn('id="panel-fantasy"', panel)
        self.assertEqual(panel.count('class="fantasy-row"'), 35)
        self.assertIn(preview["artifact_sha256"], panel)

    def test_fantasy_plan_uses_replayable_playwright_commands(self):
        plan = (
            Path(__file__).parents[1]
            / "docs"
            / "superpowers"
            / "plans"
            / "2026-09-03-pgo-fantasy-week-1-site-preview.md"
        ).read_text(encoding="utf-8")

        self.assertIn('panel.count(\'class="fantasy-view-button"\')', plan)
        self.assertIn('self.assertIn("dataset.view", pgo_comparison.FANTASY_SCRIPT)', plan)
        self.assertIn(
            "& $gitBash -lc '\"$1\" --session pgo-fantasy-week1 eval \"$PGO_EVAL\"' _ $playwrightCli",
            plan,
        )
        self.assertNotIn(
            "& $gitBash $playwrightCli --session pgo-fantasy-week1 eval",
            plan,
        )
        self.assertNotIn(r'querySelector(\"', plan)
        self.assertNotIn(r'querySelectorAll(\"', plan)
        self.assertIn(
            """$env:PGO_EVAL = 'document.querySelector(".fantasy-sort[data-column=''5'']").click()'""",
            plan,
        )
        self.assertNotIn("[data-column=5]", plan)
        self.assertIn("requests --static", plan)
        self.assertNotIn("pgo-fantasy-week1 network", plan)

    def test_fantasy_assets_cover_filters_sorting_columns_and_mobile(self):
        self.assertIn("dataset.view", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("fantasy-player-search", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("fantasy-team", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("fantasy-columns", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("aria-sort", pgo_comparison.FANTASY_SCRIPT)
        self.assertNotIn("fetch(", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("@media (max-width:480px)", pgo_comparison.FANTASY_CSS)
        self.assertIn(
            "#panel-fantasy.show-technical .fantasy-technical",
            pgo_comparison.FANTASY_CSS,
        )

    def test_fantasy_injection_keeps_mccabe_active_and_preserves_other_panels(self):
        comparison = pgo_comparison.render_comparison_panel(
            [], self._held_receipt()
        )
        fantasy = pgo_comparison.render_fantasy_panel(
            self._fantasy_preview()
        )

        existing = pgo_comparison.inject_comparison(
            self._base_html(), comparison
        )
        output = pgo_comparison.inject_fantasy_preview(
            existing, fantasy
        )

        tab_ids = [
            "tab-ratings", "tab-qbs", "tab-method", "tab-comparison",
            "tab-fantasy",
        ]
        self.assertEqual(
            sorted(tab_ids, key=lambda tab_id: output.index(f'id="{tab_id}"')),
            tab_ids,
        )
        self.assertEqual(output.count('class="tab active"'), 1)
        self.assertEqual(output.count('aria-selected="true"'), 1)
        self.assertIn('class="tab active" id="tab-ratings"', output)
        self.assertIn(
            'aria-selected="true" aria-controls="panel-ratings"', output
        )
        for panel in ("comparison", "fantasy"):
            self.assertIn(f'class="tab" id="tab-{panel}"', output)
            self.assertIn(
                f'aria-selected="false" aria-controls="panel-{panel}"', output
            )
            self.assertIn(f'class="panel" id="panel-{panel}"', output)
            self.assertIn(f'aria-labelledby="tab-{panel}" hidden>', output)
        self.assertIn('class="panel active" id="panel-ratings"', output)
        self.assertIn("McCabe Ratings</button>", output)
        self.assertIn("McCabe QBs</button>", output)
        self.assertIn("McCabe Method</button>", output)
        self.assertEqual(output.count(pgo_comparison.FANTASY_SCRIPT), 1)
        with self.assertRaisesRegex(ValueError, "already has"):
            pgo_comparison.inject_fantasy_preview(output, fantasy)

    def test_fantasy_injection_accepts_only_the_known_additive_model_style(self):
        from pgo_model_updates import STYLE
        plain = pgo_comparison.inject_comparison(self._base_html(),
            pgo_comparison.render_comparison_panel([], self._held_receipt()))
        fantasy = pgo_comparison.render_fantasy_panel(self._fantasy_preview())
        panel = pgo_comparison.extract_comparison_panel(plain)
        def with_style(style):
            return plain.replace(panel, panel.replace('</section>', style + '</section>', 1), 1)
        styled = with_style(STYLE)
        output = pgo_comparison.inject_fantasy_preview(styled, fantasy)
        self.assertEqual(output.replace(STYLE, '', 1),
                         pgo_comparison.inject_fantasy_preview(plain, fantasy))
        self.assertEqual(output.count(STYLE), 1)
        for extra in ('<style>unrecognized</style>', STYLE + STYLE,
                      STYLE.replace('margin-top:28px', 'margin-top:29px')):
            with self.subTest(extra=extra[:30]), self.assertRaisesRegex(ValueError, 'markers changed'):
                pgo_comparison.inject_fantasy_preview(with_style(extra), fantasy)

    def test_track_record_survives_repeated_fantasy_refresh_with_strict_styles(self):
        from pgo_model_updates import STYLE
        plain = pgo_comparison.inject_comparison(self._base_html(),
            pgo_comparison.render_comparison_panel(self._saved_comparison_rows(), self._held_receipt()))
        fantasy = pgo_comparison.render_fantasy_panel(self._fantasy_preview())
        published = pgo_comparison.inject_fantasy_preview(plain, fantasy)
        panel = pgo_comparison.extract_comparison_panel(published)
        published = published.replace(panel, panel.replace('</section>', STYLE + '</section>', 1), 1)
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / 'data' / 'records.json'
            records.parent.mkdir()
            records.write_text(json.dumps({'generated': '2026-09-16', 'season_record': {
                'model': {'open': {'win': 10, 'loss': 6}, 'close': {'win': 9, 'loss': 7}}}}))
            with patch.object(pgo_comparison, 'HERE', Path(temporary)):
                published = pgo_comparison.inject_record_block(published)
            block = re.search(r'<!--track-record-start-->.*?<!--track-record-end-->', published, re.S).group(0)
            style = re.search(r'<style>.*?</style>', block, re.S).group(0)
            for refresh in range(2):
                if refresh:
                    records.unlink()
                try:
                    published = pgo_comparison.refresh_mccabe_page(self._base_html(), published)
                    with patch.object(pgo_comparison, 'HERE', Path(temporary)):
                        published = pgo_comparison.inject_record_block(published)
                except ValueError as error:
                    self.fail('Known track-record style blocked refresh: ' + str(error))
                self.assertEqual(published.count(block), 1)
                self.assertIn(block, pgo_comparison.extract_comparison_panel(published))
                self.assertEqual(published.count(STYLE), 1)
                self.assertEqual(published.count(pgo_comparison.FANTASY_SCRIPT), 1)
                self.assertEqual(pgo_comparison._extract_published_fantasy_panel(published),
                                 pgo_comparison._extract_published_fantasy_panel(
                                     pgo_comparison.inject_fantasy_preview(plain, fantasy)))

        panel = pgo_comparison.extract_comparison_panel(plain)
        for extra in (style, STYLE + style):
            styled = plain.replace(panel, panel.replace('</section>', extra + '</section>', 1), 1)
            self.assertEqual(pgo_comparison.inject_fantasy_preview(styled, fantasy).count(style), 1)
        for invalid in (style * 2, style + '<style>unknown</style>',
                        style.replace('margin:14px', 'margin:15px'), style.replace('</style>', '')):
            broken = plain.replace(panel, panel.replace('</section>', invalid + '</section>', 1), 1)
            with self.subTest(style=invalid[:80]), self.assertRaisesRegex(ValueError, 'markers changed'):
                pgo_comparison.inject_fantasy_preview(broken, fantasy)
        with self.assertRaisesRegex(ValueError, 'markers changed'):
            pgo_comparison.inject_fantasy_preview(plain.replace('</body>', style + '</body>', 1), fantasy)

    def test_injection_without_fantasy_remains_byte_identical(self):
        output = pgo_comparison.inject_comparison(
            self._base_html(),
            '<section class="panel active" id="panel-comparison" '
            'aria-labelledby="tab-comparison">Rows</section>',
        )
        digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        self.assertEqual(
            digest,
            # Comparison script now also binds saved-rating drawer triggers.
            "43c330c99f9a116e19c72edbc367f68d5f37a3268a36f7b90968d49b19d24178",
        )

    def test_injection_adds_one_accessible_tab_and_preserves_base_page(self):
        base = self._base_html()
        panel = (
            '<section class="panel active" id="panel-comparison" '
            'aria-labelledby="tab-comparison">Rows</section>'
        )
        output = pgo_comparison.inject_comparison(base, panel)
        self.assertEqual(output.count('id="tab-comparison"'), 1)
        self.assertEqual(output.count('id="panel-comparison"'), 1)
        self.assertIn('aria-controls="panel-comparison"', output)
        self.assertIn("<style>base", output)

    def test_injection_suppresses_browser_favicon_request(self):
        base = self._base_html()
        output = pgo_comparison.inject_comparison(
            base,
            '<section class="panel active" id="panel-comparison" '
            'aria-labelledby="tab-comparison">Rows</section>',
        )
        self.assertEqual(output.count('<link rel="icon" href="data:,">'), 1)

    def test_refresh_mccabe_updates_only_current_mccabe_fields(self):
        stale_rows = [
            {
                "team": "Los Angeles Rams", "mccabe_rank": 1,
                "mccabe_rating": 7.5, "full_strength_rank": 2,
                "full_strength_rating": 6.653245,
                "availability_adjustment": 0.0,
                "current_lineup_rank": 2, "current_lineup_rating": 6.653245,
                "rank_disagreement": 1,
                "rating_disagreement": -0.846755,
            },
            {
                "team": "San Francisco 49ers", "mccabe_rank": 7,
                "mccabe_rating": 4.5, "full_strength_rank": 7,
                "full_strength_rating": 4.134241,
                "availability_adjustment": 0.0,
                "current_lineup_rank": 7, "current_lineup_rating": 4.134241,
                "rank_disagreement": 0,
                "rating_disagreement": -0.365759,
            },
            {
                "team": "New Orleans Saints", "mccabe_rank": 25,
                "mccabe_rating": -0.5, "full_strength_rank": 23,
                "full_strength_rating": -2.638712,
                "availability_adjustment": 0.0,
                "current_lineup_rank": 23, "current_lineup_rating": -2.638712,
                "rank_disagreement": -2,
                "rating_disagreement": -2.138712,
            },
        ]
        current_rows = [
            {"team": "Los Angeles Rams", "abbr": "LAR", "rank": 1, "rating": 7.3},
            {"team": "San Francisco 49ers", "abbr": "SF", "rank": 9, "rating": 3.2},
            {"team": "New Orleans Saints", "abbr": "NO", "rank": 25, "rating": -0.8},
        ]
        published = pgo_comparison.inject_comparison(
            self._base_html(),
            pgo_comparison.render_comparison_panel(stale_rows, self._held_receipt()),
        )
        published = published.replace(
            pgo_comparison.COMPARISON_TAB,
            pgo_comparison.ACTIVE_COMPARISON_TAB,
            1,
        ).replace(
            'class="tab active" id="tab-ratings"',
            'class="tab" id="tab-ratings"',
            1,
        ).replace(
            'aria-selected="true" aria-controls="panel-ratings" tabindex="0"',
            'aria-selected="false" aria-controls="panel-ratings" tabindex="-1"',
            1,
        ).replace(
            '<section class="panel active" id="panel-ratings"',
            '<section class="panel" id="panel-ratings"',
            1,
        ).replace(
            'aria-labelledby="tab-ratings">',
            'aria-labelledby="tab-ratings" hidden>',
            1,
        ).replace(
            '<section class="panel" id="panel-comparison"',
            '<section class="panel active" id="panel-comparison"',
            1,
        ).replace(
            'aria-labelledby="tab-comparison" hidden>',
            'aria-labelledby="tab-comparison">',
            1,
        )
        current_base = self._base_html().replace(
            'id="panel-ratings" role="tabpanel">McCabe</section>',
            'id="panel-ratings" role="tabpanel">Updated McCabe</section>',
        )

        with (
            patch.object(pgo_comparison, "load_mccabe_rows", return_value=current_rows),
            patch.object(
                pgo_comparison,
                "mccabe_source_timestamp",
                return_value="2026-08-18T02:09:47-07:00",
            ),
        ):
            output = pgo_comparison.refresh_mccabe_page(current_base, published)
            rerun = pgo_comparison.refresh_mccabe_page(current_base, output)

        self.assertEqual(output, rerun)
        self.assertIn('data-sort="1">1</td><td data-sort="7.3">+7.3', output)
        self.assertIn('data-sort="9">9</td><td data-sort="3.2">+3.2', output)
        self.assertIn('data-sort="25">25</td><td data-sort="-0.8">-0.8', output)
        self.assertIn('>+1</td><td data-sort="-0.6467549999999997">-0.6', output)
        self.assertIn('>-2</td><td data-sort="0.9342410000000001">+0.9', output)
        self.assertIn('>-2</td><td data-sort="-1.838712">-1.8', output)
        self.assertNotIn('data-sort="7.5">+7.5', output)
        self.assertNotIn('data-sort="4.5">+4.5', output)
        self.assertNotIn('data-sort="-0.5">-0.5', output)
        self.assertIn('data-sort="6.653245">+6.7', output)
        self.assertIn('data-sort="4.134241">+4.1', output)
        self.assertIn('data-sort="-2.638712">-2.6', output)
        self.assertIn("Experimental model", output)
        self.assertIn("HOLD", output)
        self.assertIn("test-receipt-ref", output)
        self.assertIn("PGO pgo_v1 as of", output)
        self.assertIn("2026-07-21T12:00:00-04:00", output)
        self.assertIn("Current McCabe ratings from data/ratings.csv as of", output)
        self.assertIn("2026-08-18T02:09:47-07:00", output)
        self.assertIn("Historical Preseason 2026 snapshot locked", output)
        self.assertIn("2026-07-16T11:22:52-04:00", output)

    def test_refresh_mccabe_preserves_published_fantasy_panel(self):
        comparison_rows = [{
            "team": "Los Angeles Rams", "mccabe_rank": 1, "mccabe_rating": 7.5,
            "full_strength_rank": 2, "full_strength_rating": 6.653245,
            "availability_adjustment": 0.0, "current_lineup_rank": 2,
            "current_lineup_rating": 6.653245, "rank_disagreement": 1,
            "rating_disagreement": -0.846755,
        }]
        current_rows = [{"team": "Los Angeles Rams", "abbr": "LAR", "rank": 3, "rating": 5.5}]
        fantasy_panel = pgo_comparison.render_fantasy_panel(self._fantasy_preview())
        published = pgo_comparison.inject_fantasy_preview(
            pgo_comparison.inject_comparison(
                self._base_html(),
                pgo_comparison.render_comparison_panel(comparison_rows, self._held_receipt()),
            ),
            fantasy_panel,
        )
        published = published.replace(
            pgo_comparison.FANTASY_TAB,
            pgo_comparison.ACTIVE_FANTASY_TAB,
            1,
        ).replace(
            'class="tab active" id="tab-ratings"',
            'class="tab" id="tab-ratings"',
            1,
        ).replace(
            'aria-selected="true" aria-controls="panel-ratings" tabindex="0"',
            'aria-selected="false" aria-controls="panel-ratings" tabindex="-1"',
            1,
        ).replace(
            '<section class="panel active" id="panel-ratings"',
            '<section class="panel" id="panel-ratings"',
            1,
        ).replace(
            'aria-labelledby="tab-ratings">',
            'aria-labelledby="tab-ratings" hidden>',
            1,
        ).replace(
            '<section class="panel" id="panel-fantasy"',
            '<section class="panel active" id="panel-fantasy"',
            1,
        ).replace(
            'aria-labelledby="tab-fantasy" hidden>',
            'aria-labelledby="tab-fantasy">',
            1,
        )
        with (
            patch.object(pgo_comparison, "load_mccabe_rows", return_value=current_rows),
            patch.object(pgo_comparison, "mccabe_source_timestamp", return_value="2026-09-04T12:00:00-04:00"),
        ):
            output = pgo_comparison.refresh_mccabe_page(self._base_html(), published)
        self.assertEqual(
            self._panel_inner(output, "panel-fantasy"),
            self._panel_inner(fantasy_panel, "panel-fantasy"),
        )
        self.assertEqual(output.count('id="tab-fantasy"'), 1)
        self.assertEqual(output.count('id="panel-fantasy"'), 1)
        self.assertEqual(output.count(pgo_comparison.FANTASY_CSS), 1)
        self.assertEqual(output.count(pgo_comparison.FANTASY_SCRIPT), 1)
        self.assertIn(pgo_comparison.FANTASY_TAB, output)
        self.assertIn('<section class="panel active" id="panel-ratings"', output)
        self.assertIn('<section class="panel" id="panel-fantasy"', output)
        self.assertIn('aria-labelledby="tab-fantasy" hidden>', output)
        self.assertNotIn('<section class="panel active" id="panel-comparison"', output)
        self.assertIn('data-sort="3">3</td><td data-sort="5.5">+5.5', output)

    def test_refresh_mccabe_preserves_availability_panel_and_assets(self):
        availability_css = getattr(
            pgo_comparison, "FANTASY_AVAILABILITY_CSS", None
        )
        self.assertIsNotNone(availability_css)
        fantasy_panel = pgo_comparison.render_fantasy_panel(
            self._fantasy_preview()
        ).replace(
            "Buffalo QB</th>",
            'Buffalo QB<span class="fantasy-availability">'
            '<span class="fantasy-game-state">PREVIEW</span></span></th>',
            1,
        )

        with tempfile.TemporaryDirectory() as temp:
            mccabe_path = Path(temp) / "ratings.csv"
            mccabe_path.write_bytes(pgo_comparison.MCCABE_PATH.read_bytes())
            current_rows = pgo_comparison.load_mccabe_rows(mccabe_path)
            comparison_rows = [
                {
                    "team": row["team"],
                    "mccabe_rank": row["rank"],
                    "mccabe_rating": row["rating"],
                    "full_strength_rank": row["rank"],
                    "full_strength_rating": row["rating"],
                    "availability_adjustment": 0.0,
                    "current_lineup_rank": row["rank"],
                    "current_lineup_rating": row["rating"],
                    "rank_disagreement": 0,
                    "rating_disagreement": 0.0,
                }
                for row in current_rows
            ]
            comparison = pgo_comparison.inject_comparison(
                self._base_html(),
                pgo_comparison.render_comparison_panel(
                    comparison_rows, self._held_receipt()
                ),
            )
            published = pgo_comparison.inject_fantasy_preview(
                comparison, fantasy_panel
            )
            invalid_pages = {
                "missing": published.replace(availability_css, "", 1),
                "duplicate": published.replace(
                    "</style>", availability_css + "\n</style>", 1
                ),
                "orphaned": pgo_comparison.inject_fantasy_preview(
                    comparison,
                    pgo_comparison.render_fantasy_panel(
                        self._fantasy_preview()
                    ),
                ).replace(
                    "</style>", availability_css + "\n</style>", 1
                ),
            }
            with patch.object(
                pgo_comparison,
                "mccabe_source_timestamp",
                return_value="2026-09-06T12:00:00-04:00",
            ):
                output = pgo_comparison.refresh_mccabe_page(
                    self._base_html(), published, mccabe_path
                )
                for case, page in invalid_pages.items():
                    with self.subTest(case=case):
                        with self.assertRaisesRegex(
                            ValueError, "availability CSS"
                        ):
                            pgo_comparison.refresh_mccabe_page(
                                self._base_html(), page, mccabe_path
                            )

        self.assertEqual(
            self._panel_inner(output, "panel-fantasy"),
            self._panel_inner(fantasy_panel, "panel-fantasy"),
        )
        self.assertEqual(output.count(pgo_comparison.FANTASY_TAB), 1)
        self.assertEqual(output.count(pgo_comparison.FANTASY_CSS), 1)
        self.assertEqual(output.count(availability_css), 1)
        self.assertEqual(output.count(pgo_comparison.FANTASY_SCRIPT), 1)

    def test_refresh_mccabe_rejects_invalid_fantasy_markers(self):
        comparison_rows = [{
            "team": "Los Angeles Rams", "mccabe_rank": 1, "mccabe_rating": 7.5,
            "full_strength_rank": 2, "full_strength_rating": 6.653245,
            "availability_adjustment": 0.0, "current_lineup_rank": 2,
            "current_lineup_rating": 6.653245, "rank_disagreement": 1,
            "rating_disagreement": -0.846755,
        }]
        current_rows = [{"team": "Los Angeles Rams", "abbr": "LAR", "rank": 3, "rating": 5.5}]
        comparison = pgo_comparison.inject_comparison(
            self._base_html(),
            pgo_comparison.render_comparison_panel(comparison_rows, self._held_receipt()),
        )
        complete = pgo_comparison.inject_fantasy_preview(
            comparison, pgo_comparison.render_fantasy_panel(self._fantasy_preview())
        )
        invalid_pages = (
            comparison.replace(pgo_comparison.COMPARISON_TAB, pgo_comparison.COMPARISON_TAB + pgo_comparison.FANTASY_TAB, 1),
            complete.replace(pgo_comparison.FANTASY_TAB, pgo_comparison.FANTASY_TAB + pgo_comparison.FANTASY_TAB, 1),
            comparison.replace("</style>", pgo_comparison.FANTASY_CSS + "\n</style>", 1),
            comparison.replace("</body>", pgo_comparison.FANTASY_SCRIPT + "\n</body>", 1),
        )
        with (
            patch.object(pgo_comparison, "load_mccabe_rows", return_value=current_rows),
            patch.object(pgo_comparison, "mccabe_source_timestamp", return_value="2026-09-04T12:00:00-04:00"),
        ):
            for page in invalid_pages:
                with self.subTest(page=page[:80]):
                    with self.assertRaisesRegex(ValueError, "fantasy preview markers are incomplete or duplicated"):
                        pgo_comparison.refresh_mccabe_page(self._base_html(), page)

    def test_refresh_mccabe_rejects_ambiguous_active_panels(self):
        comparison = pgo_comparison.inject_comparison(
            self._base_html(),
            pgo_comparison.render_comparison_panel([], self._held_receipt()),
        )
        ambiguous = comparison.replace(
            pgo_comparison.COMPARISON_TAB,
            pgo_comparison.ACTIVE_COMPARISON_TAB,
            1,
        ).replace(
            '<section class="panel" id="panel-comparison"',
            '<section class="panel active" id="panel-comparison"',
            1,
        ).replace(
            'aria-labelledby="tab-comparison" hidden>',
            'aria-labelledby="tab-comparison">',
            1,
        )
        with self.assertRaisesRegex(
            ValueError, "active tab or panel state"
        ):
            pgo_comparison.refresh_mccabe_page(self._base_html(), ambiguous)

    def test_refresh_mccabe_rejects_malformed_inactive_tabs_and_panels(self):
        comparison = pgo_comparison.inject_comparison(
            self._base_html(),
            pgo_comparison.render_comparison_panel([], self._held_receipt()),
        )
        qbs_tab = re.search(
            r'<button\b[^>]*id="tab-qbs".*?</button>', comparison, re.S
        ).group(0)
        qbs_panel = re.search(
            r'<section\b[^>]*id="panel-qbs".*?</section>', comparison, re.S
        ).group(0)
        method_panel = re.search(
            r'<section\b[^>]*id="panel-method".*?</section>', comparison, re.S
        ).group(0)
        malformed = {
            "missing PGO tab": comparison.replace(
                pgo_comparison.COMPARISON_TAB, "", 1
            ),
            "duplicate PGO tab": comparison.replace(
                pgo_comparison.COMPARISON_TAB,
                pgo_comparison.COMPARISON_TAB * 2,
                1,
            ),
            "duplicate QB tab": comparison.replace(qbs_tab, qbs_tab * 2, 1),
            "missing QB panel": comparison.replace(qbs_panel, "", 1),
            "duplicate method panel": comparison.replace(
                method_panel, method_panel * 2, 1
            ),
            "active ratings panel hidden": comparison.replace(
                'aria-labelledby="tab-ratings">',
                'aria-labelledby="tab-ratings" hidden>',
                1,
            ),
            "active ratings panel empty hidden": comparison.replace(
                'aria-labelledby="tab-ratings">',
                'aria-labelledby="tab-ratings" hidden="">',
                1,
            ),
            "active ratings panel named hidden": comparison.replace(
                'aria-labelledby="tab-ratings">',
                'aria-labelledby="tab-ratings" hidden="hidden">',
                1,
            ),
            "inactive QB tab in tab order": comparison.replace(
                'aria-selected="false" aria-controls="panel-qbs" tabindex="-1"',
                'aria-selected="false" aria-controls="panel-qbs" tabindex="0"',
                1,
            ),
            "inactive QB panel visible": comparison.replace(
                'aria-labelledby="tab-qbs" hidden>',
                'aria-labelledby="tab-qbs">',
                1,
            ),
        }
        with (
            patch.object(pgo_comparison, "load_mccabe_rows", return_value=[]),
            patch.object(
                pgo_comparison,
                "mccabe_source_timestamp",
                return_value="2026-09-07T01:00:00+00:00",
            ),
        ):
            for name, page in malformed.items():
                with self.subTest(name=name):
                    with self.assertRaisesRegex(
                        ValueError, "active tab or panel state"
                    ):
                        pgo_comparison.refresh_mccabe_page(
                            self._base_html(), page
                        )

    def test_comparison_team_labels_have_contrasting_backgrounds(self):
        self.assertIn(
            "#panel-comparison .comparison-table thead th:first-child {\n"
            "  background:var(--panel2);",
            pgo_comparison.MODEL_CSS,
        )
        self.assertIn(
            "#panel-comparison .comparison-table tbody th:first-child {\n"
            "  background:var(--panel); color:var(--ink);",
            pgo_comparison.MODEL_CSS,
        )

    def test_cli_rejects_output_outside_preview_root(self):
        with redirect_stderr(io.StringIO()):
            code = pgo_comparison.main(["--output", "docs/index.html"])
        self.assertEqual(code, 1)

    def test_cli_publish_targets_only_docs_index(self):
        with (
            patch.object(
                pgo_comparison,
                "load_comparison_rows",
                return_value=(self._saved_comparison_rows(), self._held_receipt()),
            ),
            patch.object(pgo_comparison, "atomic_write_text") as write,
        ):
            code = pgo_comparison.main(["--publish"])

        self.assertEqual(code, 0)
        target = Path(write.call_args.args[0]).resolve()
        self.assertEqual(
            target,
            (pgo_comparison.HERE / "docs" / "index.html").resolve(),
        )
