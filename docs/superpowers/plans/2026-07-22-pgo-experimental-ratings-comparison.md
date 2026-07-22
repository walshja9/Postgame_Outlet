# PGO Experimental Ratings Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit integrity-eligible PGO v1 ratings under the honest `Experimental - HOLD` label and show all 32 teams beside Sean McCabe's reviewed ratings in a private local preview.

**Architecture:** Keep model generation in `pgo_challenger.py`, adding a three-state release classification without changing the fitted model. Add one standard-library preview adapter that reuses `generate_site.py`'s existing private page, injects a comparison tab, and writes only under ignored `output/`; the production generator and published HTML stay byte-unchanged.

**Tech Stack:** Python 3 standard library, existing NumPy model code, `unittest`, existing self-contained HTML/CSS/vanilla JavaScript, Playwright CLI for browser QA.

## Global Constraints

- McCabe's ratings and PGO v1 remain independent and are never blended or used to train one another.
- `BLOCKED` means an integrity, coverage, 32-team, paired-game, or reproducibility failure and writes no ratings artifact.
- `HOLD` means integrity passed but statistical validation did not; it may write ratings only as `EXPERIMENTAL` with the failed gate visible.
- `PASS` is the only state that may be labeled `VALIDATED`.
- PGO v0 appears only in backtest evidence, never as a third current ranking.
- Use McCabe's existing `needs_review` release gate; never bypass, rewrite, or clear a review flag.
- Add no dependency and no new service, database, framework, or generalized publishing layer.
- Do not modify `data/**`, `generate_site.py`, `docs/index.html`, `shopify-theme/**`, `.github/workflows/**`, `.superpowers/**`, redirects, analytics, or any live service.
- Private previews write only under ignored `output/` and require a separate approval before any production integration.
- Do not push, merge, publish, deploy, or enable automation.

## File Map

- Modify `pgo_challenger.py`: classify `BLOCKED`/`HOLD`/`PASS`, attach publication metadata, and emit eligible HOLD ratings.
- Modify `tests/test_pgo_challenger.py`: preserve fail-closed integrity behavior while proving HOLD visibility and PASS-only validation.
- Create `pgo_comparison.py`: load reviewed McCabe rows and eligible PGO rows, build the 32-team comparison, and inject one tab into the existing private page.

- Create `tests/test_pgo_comparison.py`: cover review gating, joins, disagreement math, receipt validation, escaping, and preview injection.
- Modify `README.md`: document the two private preview commands and status language.
- Modify `research/pgo_v1/backtest.json`: generated receipt with publication classification and failed checks.
- Create `research/pgo_v1/ratings_2026_preseason.csv`: generated experimental artifact; never hand-edit it.
- Generate but do not commit `output/pgo-comparison-preview/2026-07-22/index.html`.

---

### Task 1: Separate integrity eligibility from statistical validation

**Files:**
- Modify: `pgo_challenger.py`
- Modify: `tests/test_pgo_challenger.py`

**Interfaces:**
- Produces: `GATE_CHECK_NAMES`, `INTEGRITY_GATE_NAMES`, and `classify_release(checks: dict[str, bool]) -> str`.
- Produces backtest fields: `status`, `publication_status`, and `failed_checks`.
- Preserves: `write_research_outputs(output_dir, audit, backtest, predictions, ratings) -> bool`, returning true only for PASS.
- Adds ratings fields: `validation_status` and `status_reason`.

- [ ] **Step 1: Write failing classification and output tests**

Extend `OutputTests.RATING_COLUMNS`, add one gate helper, replace the old HOLD-deletes-ratings test, and add a BLOCKED test:

```python
    RATING_COLUMNS = (
        "rank", "team", "full_strength_rating", "performance_points",
        "roster_coaching_points", "availability_adjustment",
        "current_lineup_rating", "headline_view", "headline_rating", "as_of",
        "validation_status", "status_reason",
    )

    @staticmethod
    def _gate_checks(**overrides):
        checks = {name: True for name in pgo_challenger.GATE_CHECK_NAMES}
        checks.update(overrides)
        return checks

    def test_release_classification_separates_integrity_from_statistics(self):
        self.assertEqual(
            pgo_challenger.classify_release(self._gate_checks()), "PASS"
        )
        self.assertEqual(
            pgo_challenger.classify_release(
                self._gate_checks(aggregate_improvement_ci_positive=False)
            ),
            "HOLD",
        )
        self.assertEqual(
            pgo_challenger.classify_release(
                self._gate_checks(audit_checks_pass=False)
            ),
            "BLOCKED",
        )

    def test_statistical_hold_writes_experimental_ratings(self):
        checks = self._gate_checks(aggregate_improvement_ci_positive=False)
        backtest = {
            "status": "HOLD",
            "publication_status": "EXPERIMENTAL",
            "failed_checks": ["aggregate_improvement_ci_positive"],
            "checks": checks,
        }
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            (output_dir / "ratings_old.csv").write_text("old", encoding="utf-8")
            passed = pgo_challenger.write_research_outputs(
                output_dir, self._passing_audit(), backtest, [], self._ratings()
            )
            with open(
                output_dir / "ratings_2026_preseason.csv",
                encoding="utf-8",
                newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))

        self.assertFalse(passed)
        self.assertEqual(len(rows), 32)
        self.assertEqual({row["validation_status"] for row in rows}, {"EXPERIMENTAL"})
        self.assertEqual(
            {row["status_reason"] for row in rows},
            {"Historical HOLD: aggregate_improvement_ci_positive"},
        )

    def test_blocked_run_removes_stale_ratings(self):
        checks = self._gate_checks(audit_checks_pass=False)
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            (output_dir / "ratings_old.csv").write_text("old", encoding="utf-8")
            passed = pgo_challenger.write_research_outputs(
                output_dir,
                {"checks": {"source": False}},
                {
                    "status": "BLOCKED",
                    "publication_status": "BLOCKED",
                    "failed_checks": ["audit_checks_pass"],
                    "checks": checks,
                },
                [],
                [],
            )
            self.assertFalse(passed)
            self.assertEqual(list(output_dir.glob("ratings_*.csv")), [])
            self.assertTrue((output_dir / "backtest.json").is_file())
```

Update all synthetic backtest dictionaries in `OutputTests` to use the complete check set and matching metadata. The existing PASS test must assert `VALIDATED` and `All historical gates passed`. Change the reproducibility-mismatch and failed-source-audit tests to expect BLOCKED; keep statistically inconclusive synthetic and real runs as HOLD.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
python -m unittest tests.test_pgo_challenger.OutputTests -v
```

Expected: failures for missing `GATE_CHECK_NAMES` or `classify_release`; the old implementation also fails the new HOLD artifact assertion.

- [ ] **Step 3: Implement the three-state classifier and receipt**

Add beside the existing gate constants:

```python
INTEGRITY_GATE_NAMES = frozenset((
    "audit_checks_pass",
    "all_32_current_teams",
    "paired_game_ids",
    "deterministic",
))
STATISTICAL_GATE_NAMES = frozenset((
    "challenger_mae_lower",
    "aggregate_improvement_ci_positive",
    "no_sufficient_subgroup_regression",
))
GATE_CHECK_NAMES = INTEGRITY_GATE_NAMES | STATISTICAL_GATE_NAMES
PUBLICATION_STATUS = {
    "BLOCKED": "BLOCKED",
    "HOLD": "EXPERIMENTAL",
    "PASS": "VALIDATED",
}


def classify_release(checks) -> str:
    if not isinstance(checks, dict) or set(checks) != GATE_CHECK_NAMES:
        raise ValueError("Backtest checks do not match the release contract")
    if any(type(value) is not bool for value in checks.values()):
        raise ValueError("Backtest checks must be explicit booleans")
    if not all(checks[name] for name in INTEGRITY_GATE_NAMES):
        return "BLOCKED"
    return "PASS" if all(checks.values()) else "HOLD"
```

Immediately before `_build_backtest` returns, derive:

```python
    status = classify_release(checks)
    failed_checks = sorted(name for name, passed in checks.items() if not passed)
```

Replace its final two dictionary entries with:

```python
        "checks": checks,
        "failed_checks": failed_checks,
        "publication_status": PUBLICATION_STATUS[status],
        "status": status,
```

- [ ] **Step 4: Emit labeled ratings for HOLD and PASS only**

Append the two status columns to `RATING_COLUMNS`. Replace `_rating_csv` with:

```python
def _rating_csv(ratings, backtest):
    status = backtest["status"]
    failed_checks = backtest.get("failed_checks", [])
    reason = (
        "All historical gates passed"
        if status == "PASS"
        else "Historical HOLD: " + ", ".join(failed_checks)
    )
    rows = []
    for rating in sorted(ratings, key=lambda row: row["rank"]):
        full = _quantized(rating["full_strength_rating"])
        roster = _quantized(rating["roster_coaching_points"])
        current = _quantized(rating["current_lineup_rating"])
        row = dict(rating)
        row.update({
            "full_strength_rating": _decimal_text(full),
            "performance_points": _decimal_text(full - roster),
            "roster_coaching_points": _decimal_text(roster),
            "availability_adjustment": _decimal_text(current - full),
            "current_lineup_rating": _decimal_text(current),
            "headline_rating": _decimal_text(full),
            "validation_status": PUBLICATION_STATUS[status],
            "status_reason": reason,
        })
        rows.append(row)
    return _csv_receipt(RATING_COLUMNS, rows)
```

Change `_serialized_outputs` to serialize ratings when status is HOLD or PASS, and make `_in_memory_serialization` return `_serialized_outputs(*outputs)`. Before any write, validate:

```python
    expected_status = classify_release(checks)
    failed_checks = sorted(name for name, passed in checks.items() if not passed)
    if status != expected_status:
        raise ValueError("Backtest status does not match checks")
    if backtest.get("publication_status") != PUBLICATION_STATUS[status]:
        raise ValueError("Backtest publication status does not match release status")
    if backtest.get("failed_checks") != failed_checks:
        raise ValueError("Backtest failed checks do not match checks")
```

Rename `_pass_audit_is_valid` to `_release_audit_is_valid`. Require that audit and exactly 32 current teams for HOLD and PASS. BLOCKED writes diagnostics, removes all stale ratings, and returns false. HOLD and PASS atomically write `ratings_2026_preseason.csv`; the function returns `status == "PASS"`. Map CLI exit codes explicitly:

```python
    status = outputs[1]["status"]
    print(f"{status}: pgo_v1 research gate")
    return {"PASS": 0, "HOLD": 1, "BLOCKED": 2}[status]
```

- [ ] **Step 5: Run GREEN verification and commit**

```powershell
python -m unittest tests.test_pgo_challenger.OutputTests -v
python -m unittest tests.test_pgo_challenger -v
python -m py_compile pgo_challenger.py
git diff --check
git add pgo_challenger.py tests/test_pgo_challenger.py
git commit -m "Publish eligible PGO ratings as experimental"
```

Expected: all challenger tests pass; HOLD writes 32 labeled rows, BLOCKED removes ratings, and PASS alone returns true.

### Task 2: Build the private McCabe-versus-PGO comparison tab

**Files:**
- Create: `pgo_comparison.py`
- Create: `tests/test_pgo_comparison.py`

**Interfaces:**
- Consumes: `release_ratings.load_release_rows`, `generate_site.build_html`, the PGO backtest receipt, and the PGO ratings CSV.
- Produces: `load_comparison_rows(mccabe_path, model_path, backtest_path) -> tuple[list[dict], dict]`.
- Produces: `render_comparison_panel(rows, receipt) -> str` and `inject_comparison(base_html, panel_html) -> str`.
- CLI: `python pgo_comparison.py --output output/pgo-comparison-preview/2026-07-22/index.html`.

- [ ] **Step 1: Write focused loader and rendering tests**

Create `tests/test_pgo_comparison.py` with these imports and focused tests:

```python
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
```

- [ ] **Step 2: Run the new tests and verify RED**

```powershell
python -m unittest tests.test_pgo_comparison -v
```

Expected: import failure because `pgo_comparison.py` does not exist.

- [ ] **Step 3: Implement strict loading and comparison math**

Create `pgo_comparison.py` with these imports and constants:

```python
#!/usr/bin/env python3
"""Build a private McCabe-versus-PGO ratings comparison preview."""

import argparse
import csv
import html
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import generate_site
import pgo_challenger
import pgo_model
import snapshot
from release_ratings import atomic_write_text, load_release_rows


HERE = Path(__file__).resolve().parent
MCCABE_PATH = HERE / "data" / "ratings.csv"
MODEL_PATH = HERE / "research" / "pgo_v1" / "ratings_2026_preseason.csv"
BACKTEST_PATH = HERE / "research" / "pgo_v1" / "backtest.json"
SNAPSHOTS_PATH = HERE / "data" / "snapshots.json"
MCCABE_SNAPSHOT_LABEL = "Preseason 2026"
MODEL_NUMBER_FIELDS = (
    "full_strength_rating",
    "availability_adjustment",
    "current_lineup_rating",
    "headline_rating",
)


def default_preview_path(today=None):
    today = today or datetime.now().astimezone().date()
    return HERE / "output" / "pgo-comparison-preview" / today.isoformat() / "index.html"
```

Use `load_release_rows(mccabe_path)` before reading any McCabe values. The
model uses abbreviations while McCabe's CSV uses full names, so join through the
existing `generate_site.TEAM` mapping:

```python
def _finite(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"Invalid {label}: {value!r}")
    return number


def load_mccabe_rows(path):
    parsed = []
    for row in load_release_rows(path):
        team = row.get("team", "")
        if team not in generate_site.TEAM:
            raise ValueError(f"Unknown McCabe team: {team!r}")
        rating = round(sum(
            _finite(row.get(name), f"{team} {name}")
            for name in ("qb_value", "off_value", "def_value")
        ), 1)
        parsed.append({
            "team": team,
            "abbr": generate_site.TEAM[team][0],
            "rating": rating,
        })
    expected = set(pgo_model.CURRENT_TEAMS)
    if len(parsed) != 32 or {row["abbr"] for row in parsed} != expected:
        raise ValueError("McCabe comparison requires exactly the 32 current teams")
    parsed.sort(key=lambda row: -row["rating"])
    for rank, row in enumerate(parsed, 1):
        row["rank"] = rank
    return parsed
```

The stable rating-only sort deliberately matches `generate_site.load_teams`
and preserves CSV order for tied McCabe ratings. Require a dated immutable
McCabe snapshot that exactly matches those reviewed current rows:

```python
def load_mccabe_snapshot(path, rows):
    snaps = snapshot.load_snaps(path)
    if MCCABE_SNAPSHOT_LABEL not in snaps:
        raise ValueError(f"Missing McCabe snapshot: {MCCABE_SNAPSHOT_LABEL}")
    entry = snapshot.normalize_snapshot_entry(snaps[MCCABE_SNAPSHOT_LABEL])
    if not entry["published_at"]:
        raise ValueError("McCabe comparison snapshot has no published_at")
    current = {row["team"]: row["rating"] for row in rows}
    frozen = {
        row["team"]: _finite(row.get("rating"), f"{row.get('team')} rating")
        for row in entry["rows"]
    }
    if frozen != current:
        raise ValueError("Reviewed McCabe ratings do not match the frozen snapshot")
    return {
        "mccabe_edition": MCCABE_SNAPSHOT_LABEL,
        "mccabe_published_at": entry["published_at"],
    }
```

Implement receipt validation exactly as:

```python
def validate_receipt(receipt):
    status = receipt.get("status")
    expected_publication = pgo_challenger.PUBLICATION_STATUS.get(status)
    if (
        status not in {"HOLD", "PASS"}
        or receipt.get("publication_status") != expected_publication
    ):
        raise ValueError("PGO model receipt is not eligible for comparison")
    checks = receipt.get("checks")
    if pgo_challenger.classify_release(checks) != status:
        raise ValueError("PGO model receipt status contradicts its checks")
    if not all(checks[name] for name in pgo_challenger.INTEGRITY_GATE_NAMES):
        raise ValueError("PGO model integrity gates did not pass")
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed != receipt.get("failed_checks"):
        raise ValueError("PGO model failed-check receipt is inconsistent")
    return receipt
```

Load the model CSV with this contract:

```python
def load_model_rows(path, receipt):
    expected_label = pgo_challenger.PUBLICATION_STATUS[receipt["status"]]
    expected_reason = (
        "All historical gates passed"
        if receipt["status"] == "PASS"
        else "Historical HOLD: " + ", ".join(receipt["failed_checks"])
    )
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != pgo_challenger.RATING_COLUMNS:
            raise ValueError("PGO ratings schema does not match the release contract")
        rows = list(reader)
    if len(rows) != 32 or {row["team"] for row in rows} != set(pgo_model.CURRENT_TEAMS):
        raise ValueError("PGO comparison requires exactly the 32 current teams")
    if {row["validation_status"] for row in rows} != {expected_label}:
        raise ValueError("PGO ratings label contradicts the receipt")
    if {row["status_reason"] for row in rows} != {expected_reason}:
        raise ValueError("PGO ratings reason contradicts the receipt")
    if {row["as_of"] for row in rows} != {str(receipt["as_of"])}:
        raise ValueError("PGO ratings as-of time contradicts the receipt")

    parsed = []
    for row in rows:
        item = dict(row)
        try:
            item["rank"] = int(row["rank"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid PGO rank for {row['team']}") from error
        for name in MODEL_NUMBER_FIELDS:
            item[name] = _finite(row.get(name), f"{row['team']} {name}")
        if not math.isclose(
            item["full_strength_rating"] + item["availability_adjustment"],
            item["current_lineup_rating"],
            abs_tol=1e-6,
        ):
            raise ValueError(f"PGO rating algebra failed for {row['team']}")
        if item["headline_view"] not in {"full_strength", "current_lineup"}:
            raise ValueError(f"Invalid PGO headline view for {row['team']}")
        expected_headline = item[
            "full_strength_rating"
            if item["headline_view"] == "full_strength"
            else "current_lineup_rating"
        ]
        if not math.isclose(item["headline_rating"], expected_headline, abs_tol=1e-6):
            raise ValueError(f"PGO headline rating failed for {row['team']}")
        parsed.append(item)
    if sorted(row["rank"] for row in parsed) != list(range(1, 33)):
        raise ValueError("PGO full-strength ranks must be 1 through 32")
    return parsed
```

Join and calculate disagreement as:

```python
def build_comparison_rows(mccabe_rows, model_rows):
    mccabe_by_abbr = {row["abbr"]: row for row in mccabe_rows}
    model_by_abbr = {row["team"]: row for row in model_rows}
    if set(mccabe_by_abbr) != set(model_by_abbr):
        raise ValueError("McCabe and PGO team sets do not match")
    current_ranks = {
        row["team"]: rank
        for rank, row in enumerate(
            sorted(
                model_rows,
                key=lambda row: (-row["current_lineup_rating"], row["team"]),
            ),
            1,
        )
    }
    output = []
    for mccabe in sorted(mccabe_rows, key=lambda row: row["rank"]):
        model = model_by_abbr[mccabe["abbr"]]
        current_rank = current_ranks[model["team"]]
        headline_rank = (
            model["rank"]
            if model["headline_view"] == "full_strength"
            else current_rank
        )
        output.append({
            "team": mccabe["team"],
            "abbr": mccabe["abbr"],
            "mccabe_rank": mccabe["rank"],
            "mccabe_rating": mccabe["rating"],
            "full_strength_rank": model["rank"],
            "full_strength_rating": model["full_strength_rating"],
            "availability_adjustment": model["availability_adjustment"],
            "current_lineup_rank": current_rank,
            "current_lineup_rating": model["current_lineup_rating"],
            "rank_disagreement": headline_rank - mccabe["rank"],
            "rating_disagreement": model["headline_rating"] - mccabe["rating"],
        })
    return output


def load_comparison_rows(
    mccabe_path,
    model_path,
    backtest_path,
    snapshots_path=SNAPSHOTS_PATH,
):
    receipt = validate_receipt(
        json.loads(Path(backtest_path).read_text(encoding="utf-8"))
    )
    mccabe_rows = load_mccabe_rows(mccabe_path)
    receipt = {
        **receipt,
        **load_mccabe_snapshot(snapshots_path, mccabe_rows),
    }
    return build_comparison_rows(
        mccabe_rows,
        load_model_rows(model_path, receipt),
    ), receipt
```

Positive rank disagreement means PGO ranks the team lower. Positive rating
disagreement means PGO rates it higher. Both differences are valid because both
approved products use neutral-field points versus league average.

- [ ] **Step 4: Render and inject the comparison tab**

Render one accessible, horizontally contained table with these exact columns:

```text
Team | McCabe # | McCabe | PGO full # | PGO full | Avail. | PGO today # | PGO today | Rank gap | Rating gap
```

Add a small scoped stylesheet and renderer:

```python
MODEL_CSS = """
#panel-comparison .model-status {
  display:inline-block; margin:0 0 12px; padding:6px 10px;
  border:1px solid var(--orange); border-radius:999px;
  color:var(--ink); font-weight:700;
}
#panel-comparison .comparison-summary { color:var(--mut); max-width:78ch; }
#panel-comparison .comparison-table th:first-child,
#panel-comparison .comparison-table td:first-child { text-align:left; }
#panel-comparison .comparison-table th:first-child {
  position:sticky; left:0; background:var(--panel); z-index:1;
}
#panel-comparison .comparison-links { margin-top:16px; }
@media (max-width:680px) {
  #panel-comparison .comparison-table { font-size:12px; }
  #panel-comparison .comparison-table th,
  #panel-comparison .comparison-table td { padding:8px 7px; }
}
"""


def _signed(value):
    return f"{value:+.1f}"


def render_comparison_panel(rows, receipt):
    interval = receipt["aggregate_interval"]
    metrics = receipt["metrics"]
    label = (
        "Validated model \N{EM DASH} PASS"
        if receipt["status"] == "PASS"
        else "Experimental model \N{EM DASH} HOLD"
    )
    reason = (
        "All historical gates passed"
        if not receipt["failed_checks"]
        else "Hold reason: " + ", ".join(
            name.replace("_", " ") for name in receipt["failed_checks"]
        )
    )
    body = "\n".join(
        "<tr>"
        f'<th scope="row">{html.escape(row["team"])}</th>'
        f'<td>{row["mccabe_rank"]}</td>'
        f'<td>{_signed(row["mccabe_rating"])}</td>'
        f'<td>{row["full_strength_rank"]}</td>'
        f'<td>{_signed(row["full_strength_rating"])}</td>'
        f'<td>{_signed(row["availability_adjustment"])}</td>'
        f'<td>{row["current_lineup_rank"]}</td>'
        f'<td>{_signed(row["current_lineup_rating"])}</td>'
        f'<td>{row["rank_disagreement"]:+d}</td>'
        f'<td>{_signed(row["rating_disagreement"])}</td>'
        "</tr>"
        for row in rows
    )
    summary = (
        f'Backtest: v1 MAE {metrics["challenger"]["mae"]:.3f} vs '
        f'v0 {metrics["pgo_v0"]["mae"]:.3f}; improvement '
        f'{interval["mean"]:+.3f}, 95% CI '
        f'{interval["lower"]:+.3f} to {interval["upper"]:+.3f}.'
    )
    return f"""
  <section class="panel" id="panel-comparison" role="tabpanel"
    aria-labelledby="tab-comparison" hidden>
    <div class="model-status">{html.escape(label)}</div>
    <h2>McCabe vs. the independent PGO model</h2>
    <p>Two independent ratings of overall team strength. They are compared, never blended.</p>
    <p class="comparison-summary">{html.escape(summary)}<br>
      McCabe {html.escape(receipt["mccabe_edition"])} locked
      {html.escape(receipt["mccabe_published_at"])}.<br>
      PGO {html.escape(receipt["version"])} as of
      {html.escape(str(receipt["as_of"]))}. {html.escape(reason)}.</p>
    <div class="table-shell">
      <table class="comparison-table">
        <caption class="visually-hidden">All 32 NFL teams comparing McCabe and PGO ratings</caption>
        <thead><tr>
          <th scope="col">Team</th><th scope="col">McCabe #</th>
          <th scope="col">McCabe</th><th scope="col">PGO full #</th>
          <th scope="col">PGO full</th><th scope="col">Avail.</th>
          <th scope="col">PGO today #</th><th scope="col">PGO today</th>
          <th scope="col">Rank gap</th><th scope="col">Rating gap</th>
        </tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
    <p class="legend">Positive rank gap means PGO ranks the team lower.
      Positive rating gap means PGO rates the team higher.</p>
    <p class="comparison-links">
      <a href="/research/pgo_v1/backtest.json">Backtest receipt</a>
      &middot;
      <a href="/docs/superpowers/specs/2026-07-21-independent-forward-looking-pgo-model-design.md">Methodology and release rules</a>
    </p>
  </section>
"""
```

Inject into the existing page with strict drift checks:

```python
COMPARISON_TAB = """
    <button type="button" class="tab" id="tab-comparison" role="tab"
      aria-selected="false" aria-controls="panel-comparison" tabindex="-1"
      data-panel="comparison">Model comparison</button>
"""


def inject_comparison(base_html, panel_html):
    markers = (
        "</style>",
        '<button type="button" class="tab" id="tab-method"',
        '<section class="panel" id="panel-method"',
    )
    if any(base_html.count(marker) != 1 for marker in markers):
        raise ValueError("Base ratings template markers changed")
    output = base_html.replace("</style>", MODEL_CSS + "\n</style>", 1)
    output = output.replace(markers[1], COMPARISON_TAB + "    " + markers[1], 1)
    output = output.replace(markers[2], panel_html + "\n  " + markers[2], 1)
    return output
```

Finish the private-only CLI:

```python
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_preview_path())
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        output = args.output.resolve()
        preview_root = (HERE / "output").resolve()
        if preview_root not in output.parents:
            raise ValueError("Comparison output must stay under output/")
        comparison_rows, receipt = load_comparison_rows(
            MCCABE_PATH, MODEL_PATH, BACKTEST_PATH
        )
        config = generate_site.load_config()
        site_rows = generate_site.load_teams(generate_site.load_prior())
        team_ratings = {row["team"]: row["rating"] for row in site_rows}
        generate_site.build_html.qb_data = generate_site.load_qbs(team_ratings)
        base_html = generate_site.build_html(site_rows, config)
        preview = inject_comparison(
            base_html,
            render_comparison_panel(comparison_rows, receipt),
        )
        atomic_write_text(output, preview)
    except (csv.Error, KeyError, OSError, TypeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    print(f"  {len(comparison_rows)} teams | {receipt['publication_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The existing tab JavaScript discovers the added ARIA tab automatically. Do not
add sorting, filters, client-side data fetching, a second page template, or a
production-output mode.

- [ ] **Step 5: Run GREEN verification and commit**

```powershell
python -m unittest tests.test_pgo_comparison -v
python -m unittest discover -s tests -v
python -m py_compile pgo_comparison.py
git diff --check
git add pgo_comparison.py tests/test_pgo_comparison.py
git commit -m "Add private PGO ratings comparison preview"
```

Expected: all tests pass with no new dependency and the generator continues to block any `needs_review=Y` McCabe row.

### Task 3: Regenerate the immutable HOLD receipt and experimental ratings

**Files:**
- Modify: `research/pgo_v1/backtest.json`
- Create: `research/pgo_v1/ratings_2026_preseason.csv`
- Verify unchanged: `research/pgo_v1/sources.lock.json`, `research/pgo_v1/source_audit.json`, `research/pgo_v1/validation_predictions.csv`

**Interfaces:**
- Consumes: the locked source snapshot already committed under `research/pgo_v1/` and `.cache/pgo_v1/`.
- Produces: a byte-deterministic `HOLD` receipt with `publication_status: EXPERIMENTAL` and 32 labeled ratings rows.

- [ ] **Step 1: Run the locked model without downloading**

```powershell
python pgo_challenger.py --as-of 2026-07-21T12:00:00-04:00
```

Expected exit code: `1`, with `HOLD: pgo_v1 research gate`. Do not adjust features, thresholds, or seeds in response. The expected evidence remains v0 MAE `10.266150`, v1 MAE `10.205173`, improvement `0.060977`, and 95% CI `[-0.024395, 0.144917]`; only `aggregate_improvement_ci_positive` fails.

- [ ] **Step 2: Verify the generated classification and 32-team artifact**

```powershell
$b = Get-Content -Raw research/pgo_v1/backtest.json | ConvertFrom-Json
$b.status
$b.publication_status
$b.failed_checks
(Import-Csv research/pgo_v1/ratings_2026_preseason.csv).Count
(Import-Csv research/pgo_v1/ratings_2026_preseason.csv | Group-Object validation_status).Name
```

Expected output is `HOLD`, `EXPERIMENTAL`, one failed check named `aggregate_improvement_ci_positive`, count `32`, and status `EXPERIMENTAL`.

- [ ] **Step 3: Prove offline byte determinism in a second directory**

```powershell
python pgo_challenger.py --as-of 2026-07-21T12:00:00-04:00 --output-dir output/pgo-v1-determinism
Compare-Object (Get-FileHash research/pgo_v1/backtest.json,research/pgo_v1/ratings_2026_preseason.csv -Algorithm SHA256 | Select-Object Hash) (Get-FileHash output/pgo-v1-determinism/backtest.json,output/pgo-v1-determinism/ratings_2026_preseason.csv -Algorithm SHA256 | Select-Object Hash)
```

Expected: the model again exits `1`; `Compare-Object` prints nothing.

- [ ] **Step 4: Verify artifact scope and commit**

```powershell
git status --short
git diff --exit-code -- research/pgo_v1/sources.lock.json research/pgo_v1/source_audit.json research/pgo_v1/validation_predictions.csv
git add research/pgo_v1/backtest.json research/pgo_v1/ratings_2026_preseason.csv
git commit -m "Record experimental PGO ratings hold"
```

Expected: only the backtest receipt and new ratings CSV are committed; source locks, audit evidence, and validation predictions remain byte-identical.

### Task 4: Document, generate, and review the private preview

**Files:**
- Modify: `README.md`
- Generate untracked/ignored: `output/pgo-comparison-preview/2026-07-22/index.html`
- Verify unchanged: `data/**`, `generate_site.py`, `docs/index.html`, `shopify-theme/**`, `.github/workflows/**`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: a local review artifact and desktop/mobile QA evidence; no public artifact.

- [ ] **Step 1: Add the minimal README workflow**

Add this section after the existing ratings preview commands:

```markdown
## Independent PGO model comparison (private preview)

`python pgo_challenger.py --as-of 2026-07-21T12:00:00-04:00` rebuilds the
locked pgo_v1 receipt. Exit `0` is validated `PASS`, exit `1` is an honest
statistical `HOLD`, and exit `2` is `BLOCKED`. An integrity-eligible `HOLD`
writes 32 ratings labeled `EXPERIMENTAL`; `BLOCKED` writes no ratings.

`python pgo_comparison.py` compares the eligible PGO snapshot with Sean
McCabe's reviewed ratings and writes a dated private page under
`output/pgo-comparison-preview/`. It never changes `docs/index.html` or any
live service. PGO v0 remains backtest evidence only.
```

- [ ] **Step 2: Generate the dated preview**

```powershell
python pgo_comparison.py --output output/pgo-comparison-preview/2026-07-22/index.html
```

Expected: exit `0`, 32 comparison rows, explicit `Experimental model - HOLD`, and the exact output path. The command must fail instead if McCabe has any uncleared review flag or the PGO receipt/artifact is inconsistent.

- [ ] **Step 3: Run browser QA at desktop and mobile sizes**

Start a hidden local server from the repository root:

```powershell
$server = Start-Process -WindowStyle Hidden -FilePath python -ArgumentList '-m','http.server','8765','--directory','.' -PassThru
```

Then run the bundled Playwright CLI:

```powershell
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh open http://127.0.0.1:8765/output/pgo-comparison-preview/2026-07-22/index.html --headed
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh resize 1440 1000
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh snapshot
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh eval "document.getElementById('tab-comparison').click()"
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh snapshot
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh screenshot
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh resize 390 844
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh eval "document.documentElement.scrollWidth === document.documentElement.clientWidth"
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh screenshot
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh console error
```

Expected: both snapshots expose the comparison tab and 32-team table; the width expression returns `true`; the table itself scrolls inside `.table-shell`; screenshots show no clipped status, rank, or team labels; console errors are empty.

Verify the existing keyboard tab behavior reaches the new tab:

```powershell
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh eval "document.getElementById('tab-comparison').focus()"
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh press ArrowRight
bash /mnt/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh eval "document.activeElement.id"
```

Expected: `tab-method`. Stop the server after QA:

```powershell
Stop-Process -Id $server.Id
```

- [ ] **Step 4: Run complete verification and production-isolation checks**

```powershell
python -m unittest discover -s tests -v
python -m py_compile pgo_model.py pgo_sources.py pgo_challenger.py pgo_comparison.py release_ratings.py generate_site.py snapshot.py spreads.py
git diff --check
git diff --exit-code main -- data generate_site.py docs/index.html shopify-theme .github/workflows
git status --short
```

Expected: all tests and compilation pass; the production-isolation diff exits `0`; ignored `output/` does not appear in status; no `.superpowers/` content is staged.

- [ ] **Step 5: Commit documentation and stop at the publication gate**

```powershell
git add README.md
git commit -m "Document PGO comparison preview"
git status --short
git log -5 --oneline
```

Expected: a clean worktree. Return the local preview path, desktop/mobile captures, exact model metrics, 32-team comparison proof, test count, deterministic hashes, local commits, and production-isolation result. Do not modify or generate `docs/index.html`, push, merge, publish, deploy, or change any live service. Production integration requires a new explicit approval after the user reviews this preview.
