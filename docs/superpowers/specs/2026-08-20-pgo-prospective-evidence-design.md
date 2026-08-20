# PGO Prospective Evidence Design

**Date:** 2026-08-20  
**Status:** Approved design; implementation pending

## Goal

Create a reproducible 2026 prospective shadow-evaluation path that freezes
pregame predictions before kickoff, grades only those locked predictions after
final results exist, and produces evidence that can support a later PGO release
decision without changing the existing historical HOLD receipt.

## Non-goals

- Do not change the existing historical evaluation window, grid, bootstrap seed,
  sample count, or release gates.
- Do not rewrite `research/pgo_v1/backtest.json`, its ratings CSV, or
  `docs/index.html`.
- Do not fetch data implicitly during lock or grade.
- Do not promote, publish, or relabel the model automatically.
- Do not treat prospective evidence as a historical `PASS` without an explicit
  release-policy decision; the current historical receipt remains authoritative
  for the existing PGO v1 classification.

## Design

Add a focused `pgo_prospective.py` module with two commands:

```text
python pgo_prospective.py lock \
  --as-of <ISO-8601> \
  --lock-path <frozen-source-lock.json> \
  --cache-dir <read-only-cache> \
  --schedule-snapshot <locked-schedule.csv> \
  --output-dir <prospective-output>

python pgo_prospective.py grade \
  --lock-file <prospective-output/prospective_lock.json> \
  --results-path <final-results.csv> \
  --output-dir <prospective-output>
```

The lock command consumes an already frozen source lock and cache plus a
separately frozen schedule snapshot. The schedule snapshot must contain
completed historical games plus unplayed 2026 regular-season games. It is
hashed independently because the existing historical source lock is not
rewritten when future schedule rows become available. The command uses the
existing historical sources to fit the exact PGO v1 challenger and PGO v0
benchmark, then generates predictions for each unplayed game at its kickoff-
time information boundary.

The grade command consumes only the immutable lock file and a results CSV. It
joins results by `game_id`, verifies the locked teams, kickoff, and game type,
rejects duplicates, missing games, extra games, changed predictions, and
non-final results, and never edits the lock file.

## Lock artifact

`prospective_lock.json` contains:

- schema/version and lock `as_of` timestamp;
- the frozen source hashes, source-lock hash, and schedule-snapshot hash;
- challenger parameters, feature names, missingness features, preprocessor
  medians/scales, and fitted coefficients;
- PGO v0 benchmark parameters and final ratings state;
- one record per locked game with game ID, season/week, kickoff, teams,
  venue/rest inputs, PGO v0 prediction, challenger current-lineup prediction,
  challenger full-strength prediction, and pre-treatment subgroup flags;
- status `LOCKED` and a deterministic artifact hash.

`prospective_predictions.csv` is a review-friendly projection of the same
records. It contains no actual margins.

Locking fails closed when a game is already final, kickoff is missing or not
strictly after the lock boundary, source rows are duplicated, source hashes do
not match the manifest, a required feature is missing, or a prediction is not
finite.

## Grading artifact

The results CSV must contain exactly one finalized row per locked game:

```text
game_id,home_team,away_team,home_score,away_score,finalized_at
```

The grader calculates actual margins, challenger and PGO v0 absolute errors,
MAE, paired week-block bootstrap improvement using `10_000` samples and seed
`20260721`, and the existing sufficient-evidence subgroup checks. It writes:

- `prospective_results.csv`, with the locked predictions and actual margins;
- `prospective_receipt.json`, with source/lock hashes, counts, metrics, gates,
  failed checks, and `PASS`/`HOLD`/`BLOCKED` status.

The prospective receipt is evidence only. A `PASS` does not modify the current
historical PGO v1 receipt or public app; promotion remains a separate,
explicitly authorized release action.

## Leakage and integrity rules

- Every prediction uses only rows whose source revision is at or before that
  game's kickoff.
- The lock artifact is append-free: later injury, roster, schedule, and score
  updates cannot alter any locked prediction.
- The grader never refits the model and never reads post-kickoff feature data.
- The source lock and schedule snapshot are hashed into the lock artifact.
- Re-running lock from identical inputs must produce byte-identical artifacts.

## Testing

Add focused tests that:

1. lock a synthetic historical-plus-unplayed schedule and verify predictions,
   hashes, subgroup flags, and deterministic reruns;
2. reject a post-kickoff source mutation and a changed locked game row;
3. grade finalized synthetic results and verify MAE, paired bootstrap metadata,
   and status classification;
4. reject duplicate, missing, extra, and non-final result rows;
5. verify the existing historical receipt and public files remain byte-for-byte
   unchanged while lock and grade run.

## Promotion boundary

The current PGO v1 historical result remains `HOLD` until its existing fixed
historical gate passes. This prospective path supplies stronger forward-looking
evidence and a separate receipt; it does not silently redefine the historical
gate or authorize publication.
