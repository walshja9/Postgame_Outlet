import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import pgo_challenger
import pgo_comparison


class ComparisonTests(unittest.TestCase):
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

    def test_injection_adds_one_accessible_tab_and_preserves_base_page(self):
        base = (
            "<html><style>base</style><body>"
            '<button type="button" class="tab" id="tab-method">Methodology</button>'
            '<section class="panel" id="panel-method">Method</section>'
            "</body></html>"
        )
        panel = '<section id="panel-comparison">Rows</section>'
        output = pgo_comparison.inject_comparison(base, panel)
        self.assertEqual(output.count('id="tab-comparison"'), 1)
        self.assertEqual(output.count('id="panel-comparison"'), 1)
        self.assertIn('aria-controls="panel-comparison"', output)
        self.assertIn("<style>base", output)

    def test_cli_rejects_output_outside_preview_root(self):
        with redirect_stderr(io.StringIO()):
            code = pgo_comparison.main(["--output", "docs/index.html"])
        self.assertEqual(code, 1)
