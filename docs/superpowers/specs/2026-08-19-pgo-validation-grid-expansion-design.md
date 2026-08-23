# PGO v1 Validation Grid Expansion Design

**Status:** Approved design
**Date:** August 19, 2026
**Product:** Postgame Outlet NFL Power Ratings
**Model:** Independent PGO v1 challenger

## 1. Goal

Give PGO v1 a legitimate path from `HOLD` to `PASS` without changing the
evaluation population, evidence contract, or release gate. The current receipt
contains 2,127 paired games and a mean MAE improvement of `+0.060977`, but its
paired week-block bootstrap interval is `[-0.024395, +0.144917]`; the lower
bound is not above zero.

## 2. Fixed validation contract

The following remain unchanged:

- The frozen source lock and `as_of` snapshot.
- The 2,127-game outer evaluation population (seasons 2018 through 2025).
- PGO v0 as the incumbent benchmark and scoring-margin MAE as the primary
  metric.
- Chronological training and validation folds; no future rows may influence a
  fold's features, preprocessing, or parameter choice.
- The paired season-week bootstrap, 10,000 samples, seed `20260721`, and the
  requirement that the 95% lower bound exceed zero.
- All integrity, 32-team, paired-ID, determinism, MAE, subgroup, and artifact
  gates.
- The `HOLD`/`PASS` classification and public wording. A new run remains
  `HOLD` unless every existing gate passes.

No threshold, seed, sample count, evaluation window, receipt field, or status
label may be changed to manufacture a pass.

## 3. Model change

Expand only the existing chronological hyperparameter candidate set. The
candidate grid is fixed before the next run:

```text
half_life_games = (2, 4, 8, 16, 32)
alpha           = (0.25, 1.0, 10.0, 100.0)
delta           = (0.75, 1.0, 1.5)
```

The current candidates remain in the grid. Selection continues to minimize
chronological validation MAE, with the existing deterministic tie-break order.
No new data source, feature family, target, loss function, model family, or
McCabe input is introduced in this iteration.

## 4. Artifact and release behavior

The expanded-grid run must first write to a temporary research output and be
evaluated independently. Existing tracked `research/pgo_v1` artifacts and the
public page are not replaced by a `HOLD` result. Only a reproducible `PASS`
with all gates true may replace the research receipt/ratings artifact and
advance the public status. A `HOLD` result is retained as diagnostic evidence
for review but does not authorize publication.

The receipt records the selected parameter values and the unchanged bootstrap
contract so another run can reproduce the result. Existing artifact schema and
status semantics remain intact.

## 5. Testing and verification

Focused tests must prove:

- Every grid dimension contains the old candidates and the new pre-specified
  candidates.
- Parameter selection remains chronological and deterministic; future rows and
  feature names cannot affect a fold's choice.
- Receipt classification still rejects a failed bootstrap lower bound and only
  permits `PASS` when every gate is true.
- Temporary-run output does not alter tracked research artifacts or
  `docs/index.html` when the result is `HOLD`.

Before any publication decision:

1. Run `python -m unittest tests.test_pgo_challenger -v`.
2. Run `python -m unittest discover -s tests`.
3. Run `python -m py_compile pgo_challenger.py` and `git diff --check`.
4. Run the frozen challenger into a temporary output directory.
5. Inspect the receipt's status, selected parameters, MAE, interval, and every
   gate.
6. Publish only if the receipt is `PASS`; otherwise report the measured result
   and keep the public `HOLD` page unchanged.

## 6. Boundaries

This iteration does not add features, expand the historical window, alter
source locks, change the bootstrap method, weaken subgroup checks, blend PGO
with McCabe, or edit Shopify/Pages configuration. If the expanded grid still
fails the unchanged statistical gate, stop and design a separate feature or
model-family challenger rather than continuing unbounded tuning.
