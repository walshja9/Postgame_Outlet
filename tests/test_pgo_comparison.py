import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import pgo_challenger
import pgo_comparison


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
            "https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_v1/backtest.json",
            panel,
        )
        self.assertIn(
            "https://github.com/walshja9/Postgame_Outlet/blob/main/docs/superpowers/specs/2026-07-21-independent-forward-looking-pgo-model-design.md",
            panel,
        )

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
        with patch.object(pgo_comparison, "atomic_write_text") as write:
            code = pgo_comparison.main(["--publish"])

        self.assertEqual(code, 0)
        target = Path(write.call_args.args[0]).resolve()
        self.assertEqual(
            target,
            (pgo_comparison.HERE / "docs" / "index.html").resolve(),
        )
