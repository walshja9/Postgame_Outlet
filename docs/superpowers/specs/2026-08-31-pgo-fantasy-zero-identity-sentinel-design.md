# PGO Fantasy Zero-Impact Missing-Identity Sentinel Design

**Date:** August 31, 2026

**Status:** APPROVED FOR PLANNING

**Scope:** Admit one narrow nflverse weekly-stat sentinel shape to the existing
development-only `PRIOR_OBSERVED_8_WEEK` parser.

**Release boundary:** This design, its later parser test/fix, and one authorized
read-only frozen-cache shadow are local research work. They do not authorize a
source refresh, canonical backtest, model promotion, public-site change, push,
or deployment.

## 1. Evidence and problem

The first real-cache shadow used the frozen 13-source bundle captured at
`2026-08-27T22:11:36-04:00` and bound to source lock SHA-256
`e2ec765babdc1319e36255e7ee2f69904aab4db2fd0dc9e7c7f5ea80793ce508`.
It stopped before evaluation with `Missing prior-observed stat identity`.

A read-only diagnostic scan found 107 missing-ID rows among 107,359 regular-
season stat rows. There is exactly one in every available season-week: 17 in
2020 and 18 in each season from 2021 through 2025. Every affected row has:

- an empty `player_id`;
- an empty, unmapped position;
- exactly zero computed half-PPR points.

No modeled-position row lacks an ID. The rows therefore carry no player target
and act as systematic provider sentinels, but the parser currently treats them
like malformed player records. No model metric was observed.

## 2. Decision

Change only `_load_prior_observed_stats()` at the shared parse boundary.

A missing-ID stat row is diagnostic-only when both conditions hold:

1. its raw position does not map to QB, RB, WR, or TE; and
2. `half_ppr(row)` is exactly zero.

The parser records the existing `unsupported_position` diagnostic with an
empty `gsis_id`, then excludes the row from `by_week`. It cannot enter player
history, the current-week target map, the evaluation population, coverage
denominators, or model metrics.

All other missing-ID rows remain fatal. In particular, the parser raises when
the row has a modeled position or any nonzero half-PPR value. It never joins on
a display name and never invents an identity.

## 3. Classification order

For each regular-season stat row, the parser will:

1. validate season, week, schedule identity, team, opponent, and finite
   half-PPR target as it does now;
2. map the raw position;
3. if `player_id` is empty, admit only the zero-point/unmapped sentinel rule,
   emit the diagnostic, and stop processing that row;
4. otherwise register `(season, week, gsis_id)` in the existing duplicate
   check before filtering unsupported positions;
5. preserve the current handling for every nonempty identity.

This keeps the mixed supported/unsupported duplicate defense intact. A
nonempty unsupported-position row still cannot hide a duplicate player-week.

## 4. Error and audit contract

| Input shape | Result |
|---|---|
| Missing ID, unmapped position, exactly zero half-PPR | `unsupported_position` diagnostic only |
| Missing ID, mapped position | `ValueError` |
| Missing ID, any nonzero half-PPR | `ValueError` |
| Nonempty duplicate `(season, week, gsis_id)` | `ValueError` |
| Nonempty unsupported position | Existing diagnostic behavior |

The sentinel diagnostic remains deterministically sortable even with an empty
ID. No audit schema, gate threshold, cohort rule, baseline, or status changes.
The model remains `DEVELOPMENT_ONLY`, `HOLD`, and `EXPERIMENTAL`.

## 5. Verification

Implementation must begin with a failing regression for a blank-ID,
blank-position, zero-point row. The smallest test set must also prove:

- blank ID plus a modeled position still blocks;
- blank ID plus an unmapped position and nonzero points still blocks;
- a mixed supported/unsupported duplicate with a nonempty ID still blocks;
- the existing unsupported-position diagnostic behavior remains intact.

Then run the focused prior-observed tests, the full fantasy tests, the full
repository suite with `ResourceWarning` promoted to an error, compilation,
`git diff --check`, and protected-path/HOLD-label checks.

## 6. Frozen shadow rerun

Only after implementation, verification, and code review may the same
seven-source shadow run once more from the existing frozen cache. Before the
run, revalidate every cached byte against the same 13-source lock. Do not
download, retry, refresh, or rewrite evidence.

The rerun is read-only and in-memory. It may report baseline metrics and the
existing coverage gates if parsing completes, but it may not tune a model or
persist a receipt. Whatever the metrics show, historical provider vintage
remains `REVIEW_REQUIRED`, and publication status remains HOLD.

Stop without inference if cache bytes differ, an unapproved input is needed,
any protected artifact would change, or any newly admitted missing-ID row
violates the exact zero-point/unmapped rule.

## 7. Non-goals

- No general missing-identity tolerance.
- No name-based identity recovery.
- No new diagnostic class or schema version.
- No source-provider change or PFF dependency.
- No cohort, feature, baseline, tuning, site, store, or deployment change.
