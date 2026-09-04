import hashlib
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import pgo_challenger
import pgo_comparison
from tests.test_pgo_fantasy_prospective import ProspectiveFantasyFixture


class ComparisonTests(unittest.TestCase):
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
            'role="tabpanel">McCabe</section>'
            '<section class="panel" id="panel-method">Method</section>'
            "</body></html>"
        )

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
                return_value=([], receipt),
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
            [], self._held_receipt()
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
        load_config.assert_not_called()
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

    def test_pgo_is_primary_and_rows_start_in_pgo_rank_order(self):
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

        self.assertLess(
            output.index('id="tab-comparison"'),
            output.index('id="tab-ratings"'),
        )
        self.assertIn(
            'class="tab active" id="tab-comparison"', output
        )
        self.assertIn(
            'aria-selected="true" aria-controls="panel-comparison"', output
        )
        self.assertIn(
            'class="panel active" id="panel-comparison"', output
        )
        self.assertIn(
            'class="panel" id="panel-ratings" hidden', output
        )
        self.assertIn(">McCabe Ratings</button>", output)
        self.assertIn(">McCabe QBs</button>", output)
        self.assertIn(">McCabe Method</button>", output)
        self.assertIn("By Postgame Outlet Model", output)
        self.assertIn(
            "Postgame Outlet’s independent PGO v1", output
        )
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

        self.assertEqual(panel.count('class="fantasy-row"'), 4)
        self.assertNotIn("Buffalo Backup", panel)
        self.assertEqual(panel.count('class="fantasy-view-button"'), 6)
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
            "Pos #",
            "FLEX #",
            "SF #",
            "Baseline",
            "Delta",
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
        self.assertNotIn("qb-buf", panel)

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

    def test_fantasy_injection_selects_new_tab_and_preserves_other_panels(self):
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

        self.assertLess(
            output.index('id="tab-comparison"'),
            output.index('id="tab-fantasy"'),
        )
        self.assertLess(
            output.index('id="tab-fantasy"'),
            output.index('id="tab-ratings"'),
        )
        self.assertIn(
            'class="tab active" id="tab-fantasy"',
            output,
        )
        self.assertIn(
            'aria-selected="true" aria-controls="panel-fantasy"',
            output,
        )
        self.assertIn(
            'class="tab" id="tab-comparison"',
            output,
        )
        self.assertIn(
            'aria-selected="false" aria-controls="panel-comparison"',
            output,
        )
        self.assertIn(
            'class="panel" id="panel-comparison"',
            output,
        )
        self.assertIn(
            'aria-labelledby="tab-comparison" hidden>',
            output,
        )
        self.assertIn(
            'class="panel active" id="panel-fantasy"',
            output,
        )
        self.assertIn('id="panel-ratings" hidden', output)
        self.assertIn("McCabe Ratings</button>", output)
        self.assertIn("McCabe QBs</button>", output)
        self.assertIn("McCabe Method</button>", output)
        self.assertEqual(output.count(pgo_comparison.FANTASY_SCRIPT), 1)
        with self.assertRaisesRegex(ValueError, "already has"):
            pgo_comparison.inject_fantasy_preview(output, fantasy)

    def test_injection_without_fantasy_remains_byte_identical(self):
        output = pgo_comparison.inject_comparison(
            self._base_html(),
            '<section id="panel-comparison">Rows</section>',
        )
        digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        self.assertEqual(
            digest,
            "6da6eac6d26cf88ecd3679f0706f430c4352d128af7d2eb039fd3c920f8bc50f",
        )

    def test_injection_adds_one_accessible_tab_and_preserves_base_page(self):
        base = self._base_html()
        panel = '<section id="panel-comparison">Rows</section>'
        output = pgo_comparison.inject_comparison(base, panel)
        self.assertEqual(output.count('id="tab-comparison"'), 1)
        self.assertEqual(output.count('id="panel-comparison"'), 1)
        self.assertIn('aria-controls="panel-comparison"', output)
        self.assertIn("<style>base", output)

    def test_injection_suppresses_browser_favicon_request(self):
        base = self._base_html()
        output = pgo_comparison.inject_comparison(
            base, '<section id="panel-comparison">Rows</section>'
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
        with (
            patch.object(pgo_comparison, "load_mccabe_rows", return_value=current_rows),
            patch.object(pgo_comparison, "mccabe_source_timestamp", return_value="2026-09-04T12:00:00-04:00"),
        ):
            output = pgo_comparison.refresh_mccabe_page(self._base_html(), published)
        self.assertIn(fantasy_panel, output)
        self.assertEqual(output.count('id="tab-fantasy"'), 1)
        self.assertEqual(output.count('id="panel-fantasy"'), 1)
        self.assertEqual(output.count(pgo_comparison.FANTASY_CSS), 1)
        self.assertEqual(output.count(pgo_comparison.FANTASY_SCRIPT), 1)
        self.assertIn(pgo_comparison.FANTASY_TAB, output)
        self.assertIn('<section class="panel active" id="panel-fantasy"', output)
        self.assertNotIn('<section class="panel active" id="panel-comparison"', output)
        self.assertIn('data-sort="3">3</td><td data-sort="5.5">+5.5', output)

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
        )
        with (
            patch.object(pgo_comparison, "load_mccabe_rows", return_value=current_rows),
            patch.object(pgo_comparison, "mccabe_source_timestamp", return_value="2026-09-04T12:00:00-04:00"),
        ):
            for page in invalid_pages:
                with self.subTest(page=page[:80]):
                    with self.assertRaisesRegex(ValueError, "fantasy preview markers are incomplete or duplicated"):
                        pgo_comparison.refresh_mccabe_page(self._base_html(), page)

    def test_comparison_team_labels_have_contrasting_backgrounds(self):
        self.assertIn(
            "#panel-comparison .comparison-table thead th:first-child {\n"
            "  background:var(--ink);",
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
                return_value=([], self._held_receipt()),
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
