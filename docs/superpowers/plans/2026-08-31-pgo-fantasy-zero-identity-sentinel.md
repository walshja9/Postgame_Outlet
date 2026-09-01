# PGO Fantasy Zero-Identity Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admit only zero-point, unmapped-position nflverse sentinel rows to the
development-only prior-observed parser without changing any modeled row,
coverage denominator, baseline, status, or publication boundary.

**Architecture:** Add one guard at the shared `_load_prior_observed_stats()`
trust boundary before natural-key registration and `by_week` insertion. Reuse
the existing `unsupported_position` diagnostic and existing cohort fixtures;
add no helper, schema, dependency, CLI, or output writer.

**Tech Stack:** Python standard library, existing `pgo_fantasy.py`,
`unittest`, Git, and PowerShell.

## Global Constraints

- A missing `player_id` is diagnostic-only exactly when
  `POSITION_MAP.get(raw_position) is None` and `half_ppr(row) == 0.0`.
- The admitted sentinel emits the existing `unsupported_position` diagnostic
  with an empty `gsis_id` and never enters `by_week`.
- A missing ID with a mapped QB/RB/FB/WR/TE position or any nonzero half-PPR
  target remains a fatal `ValueError`.
- Every nonempty ID is registered under `(season, week, gsis_id)` before the
  unsupported-position filter; mixed supported/unsupported duplicates remain
  fatal.
- Never infer identity from display name or any other field.
- Do not change cohort membership, history, targets, coverage, folds,
  baselines, audit schema, or gate thresholds.
- The model remains `BASELINE_ONLY`, `DEVELOPMENT_ONLY`, `HOLD`,
  `EXPERIMENTAL`, and `REVIEW_REQUIRED`.
- Add no dependency, helper abstraction, diagnostic class, runtime file, CLI,
  source provider, PFF integration, or workflow.
- Do not fetch or refresh a source, write research evidence, tune a model,
  change the site/store, push, or deploy.
- Protect `research/pgo_v1/`, `research/pgo_stability_blend/`,
  `research/pgo_fantasy/`, `prospective_evidence/`, `docs/index.html`,
  `.github/workflows/`, and `SHOPIFY.md`.
- Preserve unrelated files; use exact-path staging and never `git add -A`.
- Changed-path base is design commit
  `b2f780791fe57bf335722d8f5f594c650894c45c`.
- A frozen-cache shadow requires a clean reviewed implementation commit and
  separate user approval for that exact SHA. It runs once with no retry.

## File Map

- Modify `pgo_fantasy.py`: classify the approved sentinel before player-key
  registration and exclude it from modeling state.
- Modify `tests/test_pgo_fantasy.py`: prove diagnostic-only exclusion and the
  mapped/nonzero/duplicate fail-closed boundaries.
- Create no runtime or evidence file.

---

### Task 1: Add the narrow parser guard with TDD

**Files:**
- Modify: `pgo_fantasy.py:509-553`
- Test: `tests/test_pgo_fantasy.py:318-479`

**Interfaces:**
- Consumes `_load_prior_observed_stats(source_rows, team_weeks)` and the
  existing `_prior_observed_diagnostic(reason, row, last_known_team="")`.
- Preserves the return type `tuple[dict, list[dict]]` and every public caller.
- Produces no new function, constant, schema, or diagnostic class.

- [ ] **Step 1: Add the focused sentinel regression**

Add this method to `PriorObservedCohortTests` immediately after
`test_unsupported_position_is_diagnostic_only`:

```python
def test_zero_point_unidentified_sentinel_is_diagnostic_only(self):
    schedule, stats = self._source_rows(counts={"QB": 1})
    with tempfile.TemporaryDirectory() as baseline_directory:
        baseline_rows, baseline_audit = self._build(
            baseline_directory, schedule, stats
        )
    source = next(row for row in stats[2022] if row["week"] == "2")
    stats[2022].append({
        **source,
        "player_id": "",
        "position": "",
        "receiving_yards": "0",
    })

    with tempfile.TemporaryDirectory() as sentinel_directory:
        rows, audit = self._build(sentinel_directory, schedule, stats)

    self.assertEqual(rows, baseline_rows)
    self.assertEqual(audit["coverage"], baseline_audit["coverage"])
    sentinels = [
        row for row in audit["diagnostics"]
        if row["reason"] == "unsupported_position"
        and row["gsis_id"] == ""
    ]
    self.assertEqual(len(sentinels), 1)
    self.assertEqual(sentinels[0]["fantasy_points"], 0.0)
```

- [ ] **Step 2: Run the regression and capture RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedCohortTests.test_zero_point_unidentified_sentinel_is_diagnostic_only `
  -v
```

Expected: one error containing
`ValueError: Missing prior-observed stat identity`. If it passes or fails for a
different reason, stop and reconcile the plan with the live code.

- [ ] **Step 3: Add the nonzero-unmapped fail-closed case**

Extend the existing `mutations` tuple in
`test_invalid_relevant_stats_fail_closed` with the final lambda below; retain
all existing cases:

```python
mutations = (
    lambda row: row.update(player_id=""),
    lambda row: row.update(team="ATL"),
    lambda row: row.update(receiving_yards="NaN"),
    lambda row: row.update(
        player_id="", position="K", receiving_yards="10"
    ),
)
```

The first case continues to prove that a missing ID on a mapped QB row blocks.
The last case proves that an unmapped row with nonzero points blocks. The
existing `test_mixed_position_duplicate_player_week_fails_closed` remains the
nonempty-ID duplicate regression.

- [ ] **Step 4: Implement the minimum shared-boundary guard**

Replace only the current unconditional missing-ID error inside
`_load_prior_observed_stats()`:

```python
if not gsis_id:
    if parsed["position"] is not None or fantasy_points != 0.0:
        raise ValueError("Missing prior-observed stat identity")
    diagnostics.append(_prior_observed_diagnostic(
        "unsupported_position", parsed
    ))
    continue
```

Leave natural-key registration and `by_week` insertion immediately after this
branch. The `continue` is the mechanism that prevents an admitted sentinel
from entering current targets, history, population, or coverage.

- [ ] **Step 5: Run the exact boundary tests and capture GREEN**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedCohortTests.test_zero_point_unidentified_sentinel_is_diagnostic_only `
  tests.test_pgo_fantasy.PriorObservedCohortTests.test_invalid_relevant_stats_fail_closed `
  tests.test_pgo_fantasy.PriorObservedCohortTests.test_unsupported_position_is_diagnostic_only `
  tests.test_pgo_fantasy.PriorObservedCohortTests.test_mixed_position_duplicate_player_week_fails_closed `
  -v
```

Expected: `Ran 4 tests` and `OK`.

- [ ] **Step 6: Run the complete cohort class**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedCohortTests -v
```

Expected: all tests pass with no warning or error.

- [ ] **Step 7: Review and commit only the parser and test**

```powershell
git diff -- pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --check
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --cached --check
git diff --cached --name-only
git commit -m "fix: admit zero-impact fantasy sentinels"
```

Expected staged inventory before commit:

```text
pgo_fantasy.py
tests/test_pgo_fantasy.py
```

---

### Task 2: Verify the repository and freeze the review SHA

**Files:**
- Read: `pgo_fantasy.py`
- Read: `tests/test_pgo_fantasy.py`
- Read: protected paths listed in Global Constraints
- Modify: none unless review finds a reproduced defect

**Interfaces:**
- Consumes the Task 1 commit.
- Produces a clean, reviewed exact SHA that can be presented for separate
  frozen-shadow authorization.

- [ ] **Step 1: Run focused and module verification**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedCohortTests -v
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy -v
```

Expected: both commands end with `OK`.

- [ ] **Step 2: Run the full repository gate**

```powershell
python -B -W error::ResourceWarning -m unittest discover -s tests -v
```

Expected: the complete suite ends with `OK`; warnings are failures.

- [ ] **Step 3: Run structural checks**

```powershell
python -B -m py_compile pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --check b2f780791fe57bf335722d8f5f594c650894c45c..HEAD
```

Expected: both commands exit zero with no output.

- [ ] **Step 4: Enforce the changed-path and protected-path allowlists**

```powershell
$allowed = @(
  'docs/superpowers/plans/2026-08-31-pgo-fantasy-zero-identity-sentinel.md',
  'docs/superpowers/specs/2026-08-31-pgo-fantasy-zero-identity-sentinel-design.md',
  'pgo_fantasy.py',
  'tests/test_pgo_fantasy.py'
)
$changed = @(git diff --name-only `
  b2f780791fe57bf335722d8f5f594c650894c45c..HEAD)
$unexpected = @($changed | Where-Object { $_ -notin $allowed })
if ($unexpected) { throw "Unexpected changed path: $unexpected" }

git diff --exit-code `
  b2f780791fe57bf335722d8f5f594c650894c45c..HEAD -- `
  research/pgo_v1 `
  research/pgo_stability_blend `
  research/pgo_fantasy `
  prospective_evidence `
  docs/index.html `
  .github/workflows `
  SHOPIFY.md
rg -F "Experimental model — HOLD" docs/index.html
```

Expected: no unexpected path, empty protected diff, and the public HOLD label
is found.

- [ ] **Step 5: Perform the trust-boundary review**

```powershell
git diff b2f780791fe57bf335722d8f5f594c650894c45c..HEAD -- `
  pgo_fantasy.py tests/test_pgo_fantasy.py
rg -n "def _load_prior_observed_stats|if not gsis_id|seen.add|by_week" `
  pgo_fantasy.py tests/test_pgo_fantasy.py
```

Confirm directly that:

- schedule and finite-target validation still precede the exception;
- only `position is None` plus `fantasy_points == 0.0` admits a missing ID;
- the admitted row is diagnosed and skipped before `seen` and `by_week`;
- every nonempty ID still reaches duplicate registration before unsupported
  filtering;
- no name join, schema/status change, output write, source access, or unrelated
  refactor was added; and
- the new test proves rows and coverage are byte-for-byte equivalent with and
  without the synthetic sentinel.

If any conclusion fails, add one focused RED regression, make the smallest
shared-boundary correction, commit only the two authorized code paths, and
rerun all of Task 2.

- [ ] **Step 6: Record and present the exact review SHA**

```powershell
git status --short --branch
git rev-parse HEAD
git log -4 --oneline --decorate
```

Expected: the worktree is clean. Stop here and request separate user approval
for one frozen-cache shadow at this exact SHA. Do not run Task 3 from a general
implementation approval.

---

### Task 3: Run the separately approved frozen-cache shadow once

**Files:**
- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-source-qualification/output/pgo-fantasy-source-candidate.lock.json`
- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-source-qualification/output/pgo-fantasy-source-qualification.json`
- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-source-qualification/.cache/pgo_fantasy/*`
- Modify: none

**Interfaces:**
- Consumes the exact reviewed Task 2 SHA and the immutable 13-source cache.
- Produces terminal-only development results or one terminal-only blocker.
- Creates no lock, receipt, prediction, report, research artifact, or commit.

- [ ] **Step 1: Confirm the exact authorization and clean preflight**

```powershell
git rev-parse HEAD
git status --porcelain=v1
git diff --exit-code `
  b2f780791fe57bf335722d8f5f594c650894c45c..HEAD -- `
  research/pgo_v1 research/pgo_stability_blend research/pgo_fantasy `
  prospective_evidence docs/index.html .github/workflows SHOPIFY.md
```

Expected: HEAD exactly matches the SHA the user approved, status is empty, and
the protected diff is empty. Otherwise stop without running the shadow.

- [ ] **Step 2: Run this one uninterrupted in-memory process exactly once**

```powershell
@'
from collections import Counter
from pathlib import Path
from unittest.mock import patch
import hashlib
import json

import pgo_fantasy
import pgo_sources

ROOT = Path(r"D:\CodexWorktrees\Postgame_Outlet-fantasy-source-qualification")
LOCK = ROOT / "output/pgo-fantasy-source-candidate.lock.json"
RECEIPT = ROOT / "output/pgo-fantasy-source-qualification.json"
CACHE = ROOT / ".cache/pgo_fantasy"
LOCK_SHA256 = "e2ec765babdc1319e36255e7ee2f69904aab4db2fd0dc9e7c7f5ea80793ce508"
RECEIPT_SHA256 = "587aa5cab7d4c385c6a3bade1c942b8100e0823555efd17ea4d6fcb4a5555a4b"
FROZEN_AT = "2026-08-27T22:11:36-04:00"

def digest(path):
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()

lock_bytes = LOCK.read_bytes()
receipt_bytes = RECEIPT.read_bytes()
if hashlib.sha256(lock_bytes).hexdigest() != LOCK_SHA256:
    raise SystemExit("Frozen lock hash changed")
if hashlib.sha256(receipt_bytes).hexdigest() != RECEIPT_SHA256:
    raise SystemExit("Frozen qualification receipt hash changed")

lock_text = lock_bytes.decode("utf-8", errors="strict")
lock = pgo_fantasy._load_fantasy_source_lock(lock_text)
if len(lock["sources"]) != 13:
    raise SystemExit("Frozen lock no longer contains 13 sources")
if {row["frozen_at"] for row in lock["sources"]} != {FROZEN_AT}:
    raise SystemExit("Frozen source timestamps changed")
if sum(row["bytes"] for row in lock["sources"]) != 98_883_191:
    raise SystemExit("Frozen source byte total changed")

paths = pgo_sources.load_locked_sources(LOCK, CACHE)
before = {key: digest(path) for key, path in paths.items()}
prior_keys = {
    (spec.name, spec.season)
    for spec in pgo_fantasy.prior_observed_source_specs()
}
prior_paths = {key: paths[key] for key in prior_keys}

try:
    with patch(
        "urllib.request.urlopen",
        side_effect=AssertionError("Network access is forbidden in shadow"),
    ):
        rows, audit = pgo_fantasy.build_prior_observed_games(prior_paths)

    sentinels = [
        row for row in audit["diagnostics"] if row["gsis_id"] == ""
    ]
    if len(sentinels) != 107 or any(
        row["reason"] != "unsupported_position"
        or row["raw_position"] in pgo_fantasy.POSITION_MAP
        or row["fantasy_points"] != 0.0
        for row in sentinels
    ):
        raise SystemExit("Admitted missing-ID rows violate the sentinel rule")

    test_coverage = [
        row for row in audit["coverage"]
        if row["season"] in pgo_fantasy.TEST_SEASONS and row["week"] >= 2
    ]
    coverage_ok = bool(test_coverage) and all(
        row["positive_points_total"] > 0.0
        and row["positive_point_coverage"] >= 0.95
        for row in test_coverage
    )
    if not all(audit["checks"].values()) or not coverage_ok:
        print(json.dumps({
            "shadow_status": "BLOCKED",
            "reason": "prior_observed_coverage_gate",
            "sentinel_count": len(sentinels),
            "minimum_point_coverage": min(
                row["positive_point_coverage"] for row in test_coverage
            ) if test_coverage else None,
        }, indent=2, sort_keys=True, allow_nan=False))
        raise SystemExit(1)

    report, predictions = pgo_fantasy.backtest_baselines(rows, audit)
    primary_slots = Counter(
        (row["season"], row["week"])
        for row in predictions if row["primary_pool"]
    )
    expected_weeks = {
        (row["season"], row["week"]) for row in test_coverage
    }
    if set(primary_slots) != expected_weeks or any(
        count != 96 for count in primary_slots.values()
    ):
        print(json.dumps({
            "shadow_status": "BLOCKED",
            "reason": "primary_pool_slot_gate",
            "minimum_slots": min(primary_slots.values(), default=0),
            "maximum_slots": max(primary_slots.values(), default=0),
        }, indent=2, sort_keys=True, allow_nan=False))
        raise SystemExit(1)

    required = {
        "stage": "BASELINE_ONLY",
        "status": "HOLD",
        "publication_status": "EXPERIMENTAL",
        "evidence_role": "DEVELOPMENT_ONLY",
        "leakage_status": "REVIEW_REQUIRED",
    }
    if any(report.get(key) != value for key, value in required.items()):
        raise SystemExit("Shadow report status boundary changed")

    print(json.dumps({
        "shadow_status": "COMPLETED_HOLD",
        "lock_sha256": LOCK_SHA256,
        "sentinel_count": len(sentinels),
        "player_game_rows": len(rows),
        "prediction_rows": len(predictions),
        "evaluated_weeks": len(primary_slots),
        "minimum_point_coverage": min(
            row["positive_point_coverage"] for row in test_coverage
        ),
        "report": report,
    }, indent=2, sort_keys=True, allow_nan=False))
finally:
    if LOCK.read_bytes() != lock_bytes or RECEIPT.read_bytes() != receipt_bytes:
        raise RuntimeError("Frozen evidence bytes changed during shadow")
    if {key: digest(path) for key, path in paths.items()} != before:
        raise RuntimeError("Frozen cache bytes changed during shadow")
'@ | python -B -
```

Expected: the process either prints one `COMPLETED_HOLD` JSON summary and exits
zero, or prints/raises one truthful blocker and exits nonzero. A statistical
HOLD is a valid model result. Do not rerun, tune, patch the contract, or refresh
the cache after seeing either outcome.

- [ ] **Step 3: Confirm the run wrote nothing**

```powershell
git status --porcelain=v1
git diff --exit-code `
  b2f780791fe57bf335722d8f5f594c650894c45c..HEAD -- `
  research/pgo_v1 research/pgo_stability_blend research/pgo_fantasy `
  prospective_evidence docs/index.html .github/workflows SHOPIFY.md
```

Expected: status and protected diff remain empty. Record terminal output and
the native exit code in the handoff; create no commit.

## Completion Boundary

Task 1 completion means the parser admits only the proven zero-impact sentinel
shape. Task 2 completion means the implementation is locally reviewed and
verified. Task 3 completion, if separately authorized, produces development-
only shadow evidence; it cannot establish historical provider vintage,
predictive promotion, canonical backtest validity, or publication readiness.
