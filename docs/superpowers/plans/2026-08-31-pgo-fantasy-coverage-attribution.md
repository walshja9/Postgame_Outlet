# PGO Fantasy Coverage Attribution Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attribute the frozen prior-observed cohort's 94.4835% minimum weekly positive-point coverage to exact weeks, state reasons, positions, and stable player IDs without changing or evaluating the model.

**Architecture:** Run one self-checking, standard-library Python process from the existing clean worktree pinned to code SHA `3762847e51f6b4bc2170e90b3a6e23971b8f6cfe`. The process reuses the existing frozen-source loader and cohort builder, reconciles every reported total to the validated rows and audit, prints deterministic JSON, and writes nothing.

**Tech Stack:** PowerShell, Git, Python 3.14 standard library, `unittest.mock`, `pgo_sources.py`, and `pgo_fantasy.py`.

## Global Constraints

- Run only after the user explicitly authorizes exact code SHA `3762847e51f6b4bc2170e90b3a6e23971b8f6cfe` for this attribution.
- Invoke the cohort builder at most once. Do not retry after any result.
- Read only the frozen lock, qualification receipt, and 13 cache files captured at `2026-08-27T22:11:36-04:00`.
- Require lock SHA-256 `e2ec765babdc1319e36255e7ee2f69904aab4db2fd0dc9e7c7f5ea80793ce508` and receipt SHA-256 `587aa5cab7d4c385c6a3bade1c942b8100e0823555efd17ea4d6fcb4a5555a4b`.
- Forbid network access, source refresh, cache writes, evidence rewrites, model evaluation, tuning, threshold changes, research artifacts, site changes, push, and deployment.
- Never call `backtest_baselines`; this slice ends after cohort attribution.
- Preserve the 95% weekly point-coverage gate, eight-week history window, 96-player primary-pool contract, and all HOLD/EXPERIMENTAL status boundaries.
- Keep historical provider vintage `REVIEW_REQUIRED`.
- A nonzero result is a truthful blocker. Record it and stop; do not patch or rerun.

## File Structure

- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-prior-observed-cohort/pgo_fantasy.py`
- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-prior-observed-cohort/pgo_sources.py`
- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-source-qualification/output/pgo-fantasy-source-candidate.lock.json`
- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-source-qualification/output/pgo-fantasy-source-qualification.json`
- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-source-qualification/.cache/pgo_fantasy/*`
- Modify during execution: none

The existing cohort builder is the only production path used. No reusable
helper, dependency, test module, receipt, or research file is created for this
single-use diagnostic.

---

### Task 1: Review and execute the frozen coverage attribution once

**Files:**
- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-prior-observed-cohort/pgo_fantasy.py:489-692`
- Read: `D:/CodexWorktrees/Postgame_Outlet-fantasy-prior-observed-cohort/pgo_sources.py:169-188`
- Read: the five frozen-input paths listed in **File Structure**
- Modify: none

**Interfaces:**
- Consumes: `pgo_sources.load_locked_sources(lock_path, cache_dir) -> dict[tuple[str, int | None], Path]`
- Consumes: `pgo_fantasy.prior_observed_source_specs() -> tuple[SourceSpec, ...]`
- Consumes: `pgo_fantasy.build_prior_observed_games(paths) -> tuple[list[dict], dict]`
- Consumes: `pgo_fantasy._validate_prior_observed_audit(audit, rows) -> None`
- Produces: one terminal JSON object with `diagnostic_status: ATTRIBUTED`, or one fail-closed nonzero blocker

- [ ] **Step 1: Confirm exact authorization and the two checkout boundaries**

Run:

```powershell
$executionRoot = 'D:\CodexWorktrees\Postgame_Outlet-fantasy-prior-observed-cohort'
$primaryRoot = 'D:\Claude Context\Postgame_Outlet'
$expectedHead = '3762847e51f6b4bc2170e90b3a6e23971b8f6cfe'

git -C $executionRoot rev-parse HEAD
git -C $executionRoot status --porcelain=v1
git -C $executionRoot diff --exit-code `
  b2f780791fe57bf335722d8f5f594c650894c45c..HEAD -- `
  research/pgo_v1 research/pgo_stability_blend research/pgo_fantasy `
  prospective_evidence docs/index.html .github/workflows SHOPIFY.md
git -C $primaryRoot status --porcelain=v1
git -C $primaryRoot diff --exit-code "$expectedHead..HEAD" -- `
  research/pgo_v1 research/pgo_stability_blend research/pgo_fantasy `
  prospective_evidence docs/index.html .github/workflows SHOPIFY.md
```

Expected:

- execution HEAD is exactly `3762847e51f6b4bc2170e90b3a6e23971b8f6cfe`;
- execution status is empty;
- both protected diffs are empty; and
- primary status contains exactly these pre-existing untracked paths:

```text
?? .superpowers/
?? CLAUDE_HANDOFF_2026-07-15.md
?? CLAUDE_HANDOFF_2026-07-16.md
?? docs/superpowers/plans/2026-07-15-ratings-application-repair.md
?? docs/superpowers/plans/2026-07-15-shopify-theme-capture.md
?? docs/superpowers/plans/2026-08-24-pgo-injury-source-importer.md
?? prospective_evidence/
```

Stop before Python if any line differs.

- [ ] **Step 2: Run this complete PowerShell block exactly once**

Do not extract or rerun the Python portion. The wrapper repeats the preflight
immediately before cohort construction and performs postflight even when Python
returns nonzero.

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$executionRoot = 'D:\CodexWorktrees\Postgame_Outlet-fantasy-prior-observed-cohort'
$primaryRoot = 'D:\Claude Context\Postgame_Outlet'
$expectedHead = '3762847e51f6b4bc2170e90b3a6e23971b8f6cfe'
$protectedBase = 'b2f780791fe57bf335722d8f5f594c650894c45c'
$protectedPaths = @(
  'research/pgo_v1',
  'research/pgo_stability_blend',
  'research/pgo_fantasy',
  'prospective_evidence',
  'docs/index.html',
  '.github/workflows',
  'SHOPIFY.md'
)
$expectedPrimaryStatus = @(
  '?? .superpowers/',
  '?? CLAUDE_HANDOFF_2026-07-15.md',
  '?? CLAUDE_HANDOFF_2026-07-16.md',
  '?? docs/superpowers/plans/2026-07-15-ratings-application-repair.md',
  '?? docs/superpowers/plans/2026-07-15-shopify-theme-capture.md',
  '?? docs/superpowers/plans/2026-08-24-pgo-injury-source-importer.md',
  '?? prospective_evidence/'
)

$actualHead = (git -C $executionRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualHead -ne $expectedHead) {
  throw "Execution HEAD is not the approved code SHA: $actualHead"
}
$executionStatusBefore = @(git -C $executionRoot status --porcelain=v1)
if ($LASTEXITCODE -ne 0 -or $executionStatusBefore.Count -ne 0) {
  throw "Execution worktree is not clean"
}
$primaryStatusBefore = @(git -C $primaryRoot status --porcelain=v1)
if (
  $LASTEXITCODE -ne 0 -or
  ($primaryStatusBefore -join "`n") -ne ($expectedPrimaryStatus -join "`n")
) {
  throw "Primary untracked inventory differs from the approved boundary"
}
git -C $executionRoot diff --exit-code `
  "$protectedBase..HEAD" -- $protectedPaths
if ($LASTEXITCODE -ne 0) {
  throw "Execution worktree protected paths differ"
}
git -C $primaryRoot diff --exit-code `
  "$expectedHead..HEAD" -- $protectedPaths
if ($LASTEXITCODE -ne 0) {
  throw "Primary protected paths changed after the approved code SHA"
}

$diagnosticExit = 1
Push-Location $executionRoot
try {
@'
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import math

import pgo_fantasy
import pgo_sources

EXECUTION_SHA = "3762847e51f6b4bc2170e90b3a6e23971b8f6cfe"
ROOT = Path(r"D:\CodexWorktrees\Postgame_Outlet-fantasy-source-qualification")
LOCK = ROOT / "output/pgo-fantasy-source-candidate.lock.json"
RECEIPT = ROOT / "output/pgo-fantasy-source-qualification.json"
CACHE = ROOT / ".cache/pgo_fantasy"
LOCK_SHA256 = "e2ec765babdc1319e36255e7ee2f69904aab4db2fd0dc9e7c7f5ea80793ce508"
RECEIPT_SHA256 = "587aa5cab7d4c385c6a3bade1c942b8100e0823555efd17ea4d6fcb4a5555a4b"
FROZEN_AT = "2026-08-27T22:11:36-04:00"
EXPECTED_MINIMUM = 0.9448352555623889
TOLERANCE = 1e-12
STATE_ONLY_REASONS = {"cold_start", "recency_expired", "bye_transition"}


def digest(path):
    data = Path(path).read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def same(left, right):
    return math.isclose(
        float(left), float(right), rel_tol=0.0, abs_tol=TOLERANCE
    )


def stop(message):
    raise SystemExit(message)


lock_bytes = LOCK.read_bytes()
receipt_bytes = RECEIPT.read_bytes()
if hashlib.sha256(lock_bytes).hexdigest() != LOCK_SHA256:
    stop("Frozen lock hash changed")
if hashlib.sha256(receipt_bytes).hexdigest() != RECEIPT_SHA256:
    stop("Frozen qualification receipt hash changed")

lock = pgo_fantasy._load_fantasy_source_lock(
    lock_bytes.decode("utf-8", errors="strict")
)
if len(lock["sources"]) != 13:
    stop("Frozen lock no longer contains 13 sources")
if {row["frozen_at"] for row in lock["sources"]} != {FROZEN_AT}:
    stop("Frozen source timestamps changed")
if sum(row["bytes"] for row in lock["sources"]) != 98_883_191:
    stop("Frozen source byte total changed")

with patch(
    "urllib.request.urlopen",
    side_effect=AssertionError("Network access is forbidden in attribution"),
):
    paths = pgo_sources.load_locked_sources(LOCK, CACHE)
    if len(paths) != 13:
        stop("Frozen loader did not return 13 sources")
    before = {key: digest(path) for key, path in paths.items()}
    prior_keys = {
        (spec.name, spec.season)
        for spec in pgo_fantasy.prior_observed_source_specs()
    }
    if len(prior_keys) != 7 or not prior_keys <= set(paths):
        stop("Prior-observed source set changed")
    prior_paths = {key: paths[key] for key in prior_keys}

    try:
        rows, audit = pgo_fantasy.build_prior_observed_games(prior_paths)

        try:
            pgo_fantasy._validate_prior_observed_audit(audit, rows)
        except ValueError as error:
            if str(error) != "Prior-observed point coverage is blocked":
                raise
        else:
            stop("Frozen cohort unexpectedly passed the known coverage gate")

        expected_checks = set(pgo_fantasy.PRIOR_OBSERVED_CHECKS)
        if set(audit["checks"]) != expected_checks:
            stop("Prior-observed audit check set changed")
        if audit["checks"]["point_coverage"] is not False:
            stop("Known point-coverage blocker is absent")
        if any(
            value is not True
            for name, value in audit["checks"].items()
            if name != "point_coverage"
        ):
            stop("A non-coverage audit check failed")

        sentinels = [
            item for item in audit["diagnostics"]
            if item["gsis_id"] == ""
        ]
        if len(sentinels) != 107 or any(
            item["reason"] != "unsupported_position"
            or item["raw_position"] in pgo_fantasy.POSITION_MAP
            or item["fantasy_points"] != 0.0
            for item in sentinels
        ):
            stop("Admitted missing-ID rows violate the sentinel rule")

        expected_weeks = {
            (season, week)
            for season in pgo_fantasy.TEST_SEASONS
            for week in range(2, 19)
        }
        coverage_index = {
            (item["season"], item["week"]): item
            for item in audit["coverage"]
            if item["season"] in pgo_fantasy.TEST_SEASONS
            and item["week"] >= 2
        }
        if set(coverage_index) != expected_weeks:
            stop("Test-week coverage matrix changed")

        test_rows = [
            row for row in rows
            if row["season"] in pgo_fantasy.TEST_SEASONS
            and row["week"] >= 2
        ]
        row_index = {}
        for row in test_rows:
            key = row["season"], row["week"], row["gsis_id"]
            if key in row_index:
                stop(f"Duplicate diagnostic player-week: {key}")
            row_index[key] = row

        reason_index = {}
        for item in audit["diagnostics"]:
            if (
                item["season"] not in pgo_fantasy.TEST_SEASONS
                or item["week"] < 2
                or item["reason"] not in STATE_ONLY_REASONS
            ):
                continue
            key = item["season"], item["week"], item["gsis_id"]
            if key in reason_index:
                stop(f"Duplicate state-only reason: {key}")
            reason_index[key] = item

        state_only_keys = {
            key for key, row in row_index.items()
            if row["evaluation_eligible"] is False
        }
        if set(reason_index) != state_only_keys:
            stop("State-only rows do not bind one-to-one to allowed reasons")

        weekly_coverage = []
        failing_details = []
        for season, week in sorted(expected_weeks):
            week_rows = [
                row for row in test_rows
                if row["season"] == season and row["week"] == week
            ]
            audit_row = coverage_index[(season, week)]
            captured = math.fsum(
                max(row["fantasy_points"], 0.0)
                for row in week_rows
                if row["evaluation_eligible"] is True
            )
            missing = math.fsum(
                max(row["fantasy_points"], 0.0)
                for row in week_rows
                if row["evaluation_eligible"] is False
            )
            total = math.fsum(
                max(row["fantasy_points"], 0.0) for row in week_rows
            )
            coverage = captured / total if total > 0.0 else 0.0
            if (
                total <= 0.0
                or not same(captured, audit_row["positive_points_captured"])
                or not same(total, audit_row["positive_points_total"])
                or not same(coverage, audit_row["positive_point_coverage"])
                or not same(
                    missing,
                    audit_row["positive_points_total"]
                    - audit_row["positive_points_captured"],
                )
                or sum(
                    row["evaluation_eligible"] is True for row in week_rows
                ) != audit_row["eligible"]
                or sum(
                    row["evaluation_eligible"] is False for row in week_rows
                ) != audit_row["state_only"]
            ):
                stop(f"Coverage does not reconcile for {(season, week)}")

            weekly_coverage.append({
                "season": season,
                "week": week,
                "positive_points_captured": captured,
                "positive_points_total": total,
                "missing_positive_points": missing,
                "positive_point_coverage": coverage,
                "passes_95_percent": coverage >= 0.95,
            })
            if coverage >= 0.95:
                continue

            players = []
            for key in sorted(state_only_keys):
                if key[:2] != (season, week):
                    continue
                row = row_index[key]
                points = max(row["fantasy_points"], 0.0)
                if points == 0.0:
                    continue
                diagnostic = reason_index[key]
                players.append({
                    "season": season,
                    "week": week,
                    "game_id": row["game_id"],
                    "gsis_id": row["gsis_id"],
                    "team": row["team"],
                    "last_known_team": diagnostic["last_known_team"],
                    "position": row["position"],
                    "fantasy_points": points,
                    "reason": diagnostic["reason"],
                })
            players.sort(key=lambda item: (
                -item["fantasy_points"],
                item["reason"],
                item["position"],
                item["gsis_id"],
                item["team"],
                item["game_id"],
            ))

            by_reason = []
            for reason in sorted({item["reason"] for item in players}):
                members = [item for item in players if item["reason"] == reason]
                by_reason.append({
                    "reason": reason,
                    "player_rows": len(members),
                    "positive_points": math.fsum(
                        item["fantasy_points"] for item in members
                    ),
                })
            by_position = []
            for position in sorted({item["position"] for item in players}):
                members = [
                    item for item in players
                    if item["position"] == position
                ]
                by_position.append({
                    "position": position,
                    "player_rows": len(members),
                    "positive_points": math.fsum(
                        item["fantasy_points"] for item in members
                    ),
                })

            player_points = math.fsum(
                item["fantasy_points"] for item in players
            )
            reason_points = math.fsum(
                item["positive_points"] for item in by_reason
            )
            position_points = math.fsum(
                item["positive_points"] for item in by_position
            )
            if not all(same(value, missing) for value in (
                player_points, reason_points, position_points
            )):
                stop(f"Attribution groups do not reconcile for {(season, week)}")

            failing_details.append({
                "season": season,
                "week": week,
                "positive_points_captured": captured,
                "positive_points_total": total,
                "missing_positive_points": missing,
                "positive_point_coverage": coverage,
                "state_only_rows": audit_row["state_only"],
                "excluded_positive_player_rows": len(players),
                "by_reason": by_reason,
                "by_position": by_position,
                "players": players,
                "reconciliation": {
                    "audit_missing_points": (
                        audit_row["positive_points_total"]
                        - audit_row["positive_points_captured"]
                    ),
                    "player_points": player_points,
                    "reason_points": reason_points,
                    "position_points": position_points,
                },
            })

        minimum = min(
            item["positive_point_coverage"] for item in weekly_coverage
        )
        if not same(minimum, EXPECTED_MINIMUM):
            stop("Frozen minimum point coverage changed")
        if not failing_details:
            stop("No failing week was available to attribute")

        result = {
            "diagnostic_status": "ATTRIBUTED",
            "execution_sha": EXECUTION_SHA,
            "lock_sha256": LOCK_SHA256,
            "qualification_receipt_sha256": RECEIPT_SHA256,
            "sentinel_count": len(sentinels),
            "minimum_point_coverage": minimum,
            "weekly_coverage": weekly_coverage,
            "failing_weeks": failing_details,
            "model_boundary": {
                "stage": "BASELINE_ONLY",
                "evidence_role": "DEVELOPMENT_ONLY",
                "status": "HOLD",
                "publication_status": "EXPERIMENTAL",
                "leakage_status": "REVIEW_REQUIRED",
                "model_metrics_emitted": False,
            },
        }
    finally:
        if LOCK.read_bytes() != lock_bytes:
            raise RuntimeError("Frozen lock bytes changed during attribution")
        if RECEIPT.read_bytes() != receipt_bytes:
            raise RuntimeError(
                "Frozen qualification receipt changed during attribution"
            )
        if {key: digest(path) for key, path in paths.items()} != before:
            raise RuntimeError("Frozen cache bytes changed during attribution")

print(json.dumps(
    result, indent=2, sort_keys=True, allow_nan=False
))
'@ | python -B -
  $diagnosticExit = $LASTEXITCODE
}
finally {
  Pop-Location
}

$executionStatusAfter = @(git -C $executionRoot status --porcelain=v1)
if ($LASTEXITCODE -ne 0 -or $executionStatusAfter.Count -ne 0) {
  throw "Execution worktree changed during attribution"
}
$primaryStatusAfter = @(git -C $primaryRoot status --porcelain=v1)
if (
  $LASTEXITCODE -ne 0 -or
  ($primaryStatusAfter -join "`n") -ne ($expectedPrimaryStatus -join "`n")
) {
  throw "Primary untracked inventory changed during attribution"
}
git -C $executionRoot diff --exit-code `
  "$protectedBase..HEAD" -- $protectedPaths
if ($LASTEXITCODE -ne 0) {
  throw "Execution protected paths changed during attribution"
}
git -C $primaryRoot diff --exit-code `
  "$expectedHead..HEAD" -- $protectedPaths
if ($LASTEXITCODE -ne 0) {
  throw "Primary protected paths changed during attribution"
}
if ($diagnosticExit -ne 0) {
  exit $diagnosticExit
}
```

Expected success:

- native exit code `0`;
- exactly one JSON object with `diagnostic_status: ATTRIBUTED`;
- `minimum_point_coverage: 0.9448352555623889`;
- at least one entry in `failing_weeks`;
- every player, reason, position, and audit missing-point total reconciles within
  `1e-12`;
- `model_metrics_emitted: false`; and
- empty execution status, unchanged primary untracked inventory, unchanged
  frozen evidence, and empty protected diffs.

Expected blocker:

- native exit code nonzero with the first exact failed invariant;
- no second invocation, repair, threshold change, or interpretation beyond that
  demonstrated blocker; and
- the same no-write postflight.

- [ ] **Step 3: Record the result without creating an artifact**

Report in the user handoff:

- native exit code and invocation count `1`;
- exact failing season-week set;
- minimum coverage and shortfall from `0.95`;
- missing positive points by allowed reason and mapped position;
- every contributing GSIS ID, team, last-known team, position, and point total;
- all reconciliation results;
- frozen lock, receipt, and cache integrity results;
- no-write postflight; and
- unchanged `BASELINE_ONLY`, `DEVELOPMENT_ONLY`, `HOLD`, `EXPERIMENTAL`, and
  `REVIEW_REQUIRED` boundaries.

Do not commit a terminal transcript or diagnostic artifact. Stop after this
handoff so that any repair is designed from the observed attribution rather
than bundled into the measurement run.

## Completion Boundary

Completion means one authorized frozen-cache invocation has either attributed
the known point-coverage gap or produced a narrower fail-closed blocker. It
does not authorize model evaluation, cohort repair, source changes, promotion,
publication, push, or deployment.
