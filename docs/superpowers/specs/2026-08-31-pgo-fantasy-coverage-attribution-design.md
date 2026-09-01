# PGO Fantasy Coverage Attribution Design

**Date:** August 31, 2026

**Status:** AWAITING WRITTEN-SPEC REVIEW

**Scope:** Explain the frozen prior-observed cohort's 94.4835% minimum weekly
positive-point coverage without changing the cohort, gate, model, or evidence.

**Release boundary:** This is a local, read-only diagnostic. It does not
authorize source refresh, model evaluation, research publication, site change,
push, or deployment.

## 1. Problem and objective

The sole authorized frozen-cache shadow at code SHA
`3762847e51f6b4bc2170e90b3a6e23971b8f6cfe` passed the 107-row sentinel guard
and then stopped before baseline evaluation. Its minimum test-week positive-
point coverage was `0.9448352555623889`, below the locked `0.95` gate by
`0.0051647444376111`.

The combined gate result does not identify the failing season-week or explain
which excluded players and state transitions account for the missing positive
point mass. The next slice must produce that attribution before any eligibility
rule, history window, source, or threshold is reconsidered.

## 2. Considered approaches

1. **Frozen-cache attribution (selected).** Rebuild the same cohort once from
   the same verified bytes, stop before `backtest_baselines()`, and report the
   weekly and player-level composition of the coverage miss. This answers the
   open question without changing the scientific contract.
2. **Broaden the cohort now (rejected).** Extending history or admitting new
   player states after seeing the result would change the estimand before the
   failure is understood.
3. **Lower the 95% threshold (rejected).** Moving a locked gate to fit an
   observed result is outcome-selected tuning and would invalidate the gate.

## 3. Inputs and execution boundary

The diagnostic will run once, uninterrupted, at a separately approved exact
local `main` SHA. It will consume only:

- the frozen source lock whose SHA-256 is
  `e2ec765babdc1319e36255e7ee2f69904aab4db2fd0dc9e7c7f5ea80793ce508`;
- the frozen qualification receipt whose SHA-256 is
  `587aa5cab7d4c385c6a3bade1c942b8100e0823555efd17ea4d6fcb4a5555a4b`;
- the 13 already-cached source files bound by that lock; and
- the existing `build_prior_observed_games()` cohort builder.

All input bytes are hashed before cohort construction and rechecked afterward.
Network access is forbidden. A missing or changed byte, unexpected repository
state, or protected-path diff stops the process before attribution. There is no
retry without separate authorization.

The tracked tree must be clean. The primary checkout's existing untracked
inventory is snapshotted before the process and must match afterward; the
diagnostic neither reads nor stages those paths.

## 4. Attribution data flow

The one-off terminal script will:

1. verify the exact approved HEAD, repository state, protected paths, lock,
   receipt, 13 source identities, timestamps, byte counts, and hashes;
2. call `build_prior_observed_games()` once using only the seven locked inputs
   required by the prior-observed cohort;
3. select test-season weeks 2 through 18 from the validated coverage audit;
4. join each `evaluation_eligible: false` modeled-position row to exactly one
   same-player, same-week diagnostic in `cold_start`, `recency_expired`, or
   `bye_transition`;
5. recompute captured points, total points, missing positive points, and
   coverage for every test week from cohort rows with `math.fsum`, then require
   agreement with the audit at the existing `1e-12` absolute tolerance; and
6. emit deterministic JSON to the terminal only.

The diagnostic will not use display-name matching. Player attribution uses the
stable GSIS ID because the locked prior-observed inputs do not carry a name
column.

## 5. Terminal output contract

The JSON result will include:

- approved HEAD and frozen evidence hashes;
- sentinel count;
- every test week's coverage, captured points, total points, and missing
  positive points;
- every week below 95%, sorted by season and week;
- for each failing week, excluded positive points grouped by reason and by
  position;
- for each failing week, every excluded positive-point player row with season,
  week, game, GSIS ID, team, last-known team, mapped position, points, and
  reason, sorted by descending points with deterministic tie-breaking; and
- reconciliation totals proving that player rows, reason groups, position
  groups, and the audit's missing point mass agree.

Zero-point state-only rows may be counted but cannot contribute to the missing
point mass. `team_transition` and `unsupported_position` diagnostics are not
coverage exclusions and must not be attributed as causes.

## 6. Failure handling and scientific boundary

The process exits nonzero without inference when:

- any frozen or protected byte differs;
- any structural or integrity check other than the already-known point-
  coverage failure fails;
- a state-only row has no unique allowed reason;
- recomputed totals do not match the audit;
- a reported aggregate does not equal its contributing player rows; or
- the process would need to write an artifact or access the network.

No baseline or candidate model runs, so this slice produces no MAE, calibration,
fold, pooled, ranking, or promotion evidence. The 95% threshold, eight-week
history, primary-pool rules, statuses, and historical-vintage assessment remain
unchanged. The model stays `BASELINE_ONLY`, `DEVELOPMENT_ONLY`, `HOLD`, and
`EXPERIMENTAL`; leakage remains `REVIEW_REQUIRED`.

No production helper or dependency will be added. The execution plan contains
one self-checking standard-library script because the diagnostic has no reusable
runtime role after the gap is explained.

## 7. Verification and completion

The execution plan must contain the complete one-off script and pre/postflight
commands. Before execution, review the script statically against this design
and approve its exact SHA. After execution, confirm the input hashes and loaded
cache bytes are unchanged, the repository has no new tracked diff, and the
preserved untracked inventory is unchanged.

Completion means the exact coverage gap is attributed from frozen evidence.
It does not authorize a repair. Any proposed cohort or source change requires a
new design based on the attribution result.
