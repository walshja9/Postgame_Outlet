# PGO Lineup Fragility Challenger Design

**Status:** Approved design  
**Date:** August 19, 2026  
**Product:** Postgame Outlet NFL Power Ratings  
**Model:** Independent PGO v1 lineup-fragility challenger

## 1. Goal

Give the current PGO challenger one bounded, leakage-safe feature extension
that can address roster and quarterback uncertainty without changing the
frozen validation contract. The current expanded-grid run remains `HOLD` and
is not modified or promoted.

This challenger is research-only until it produces a reproducible `PASS`.

## 2. Fixed validation contract

The following remain unchanged:

- The frozen source lock, cache, and `as_of` snapshot.
- The 2,127-game outer evaluation population covering seasons 2018 through
  2025.
- PGO v0 as the incumbent benchmark and scoring-margin MAE as the primary
  metric.
- Chronological folds; no post-kickoff row may influence a feature,
  preprocessor, or parameter choice.
- The approved candidate grid:

  ```text
  half_life_games = (2, 4, 8, 16, 32)
  alpha           = (0.25, 1.0, 10.0, 100.0)
  delta           = (0.75, 1.0, 1.5)
  ```

- Huber-ridge loss, deterministic tie-breaking, paired season-week bootstrap,
  10,000 samples, seed `20260721`, and the requirement that the 95% lower
  bound be strictly positive.
- All existing integrity, current-team, paired-ID, deterministic, MAE,
  subgroup, and artifact gates.
- Existing `HOLD`, `BLOCKED`, and `PASS` semantics. No threshold, seed, sample
  count, evaluation window, source lock, receipt field, or status label may be
  changed.

## 3. New feature family

Add exactly three team-state features, calculated before each game from
already-locked roster, injury, snap, and player-history data.

### 3.1 Offensive availability concentration

For each rostered player with a valid prior offensive snap share `s` and
pregame availability probability `p`, calculate the missing offensive mass
`(1 - p) * s^2` and sum it for the team. The current-lineup feature is the
negative of that sum; the full-strength feature is `0.0`.

The square makes a single high-share loss distinguishable from diffuse losses
with the same total unavailable share. A required missing snap share yields a
missing feature rather than an invented zero.

Feature name: `offense_availability_concentration`.

### 3.2 Defensive availability concentration

Apply the same calculation to prior defensive snap share. The current-lineup
feature is the negative sum and the full-strength feature is `0.0`.

Feature name: `defense_availability_concentration`.

### 3.3 Quarterback depth uncertainty

Use the existing pregame quarterback depth-chart weights: the starter's
availability probability, then the remaining probability mass passed to the
next quarterback. For each quarterback with a usable pregame
`qb_epa_per_dropback`, calculate the weighted variance around the weighted
expected value. If any quarterback carrying nonzero probability lacks the
required value, return a missing feature. The current-lineup feature is this
variance; the full-strength feature is `0.0`.

Feature name: `qb_depth_uncertainty`.

The calculation must use the same availability probabilities and depth-chart
ordering already used by `_expected_qb_feature`; it must not inspect the game
being predicted or any later row.

## 4. Data flow and model integration

- Reuse existing source loading, injury timing, roster identity, snap-history,
  missingness, preprocessing, matchup-difference, and receipt mechanisms.
- Compute the three team-state values in the existing lineup-view path so
  matchup rows receive home-minus-away differences consistently with current
  features.
- Include the feature names in the existing feature manifest and model input
  schema. Do not add a second model implementation or a new source adapter.
- Keep the existing full-strength/current-lineup distinction: availability
  features are zero in full-strength state and present only in current-lineup
  state.
- Preserve the existing temporary-output boundary. A `HOLD` or `BLOCKED` run
  must leave `research/pgo_v1` and `docs/index.html` byte-identical.

## 5. Testing and verification

Focused tests must prove:

- Concentration calculations use prior snap shares and availability
  probabilities, including concentrated-vs-diffuse losses.
- QB uncertainty uses the existing depth-chart weights and has deterministic
  missing-value behavior.
- Mutating post-kickoff roster, snap, injury, or QB rows cannot change a
  pregame feature row.
- Full-strength rows zero the availability-only features.
- The synthetic pipeline runs end to end, receipts remain deterministic, and
  the feature manifest includes exactly the three new names.

Before any promotion decision:

1. Run the focused challenger tests.
2. Run the full test suite.
3. Run compilation and whitespace checks.
4. Run the challenger with the frozen lock/cache into a unique temporary
   output directory.
5. Inspect status, selected parameters, MAEs, confidence interval, and every
   gate.
6. Promote only if the receipt is `PASS`; otherwise retain the existing
   experimental HOLD artifacts and report the result.

## 6. Non-goals and boundaries

This challenger does not add sources, change the target or loss, alter PGO v0,
expand the evaluation window, change bootstrap rules, add interactions,
introduce recent-form state, blend with McCabe, or edit Pages, Shopify, or
public wording. If it remains `HOLD`, stop and design a separate challenger
instead of stacking more lineup features.
