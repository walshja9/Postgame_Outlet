# PGO Prospective Stability Blend Design

**Date:** 2026-08-26
**Status:** Approved after Fable review

## Goal

Freeze and grade a separate 2026 prospective candidate that applies only 25%
of the experimental PGO v1 correction to PGO v0. The candidate tests whether
shrinking the challenger produces a more stable replacement without modifying
the canonical PGO v1 model, its `HOLD` label, or the July 21 prospective lock.

## Scientific contract

- **Question:** Does a fixed convex blend of PGO v0 and the locked PGO v1
  challenger reduce 2026 regular-season game-margin MAE versus PGO v0?
- **Population:** The same 272 unplayed 2026 regular-season games frozen in the
  July 21 prospective evidence.
- **Grain and key:** One home-margin prediction per `game_id`.
- **Decision time:** The derived candidate's timezone-bearing lock timestamp,
  which must precede every locked kickoff.
- **Target:** Final home score minus final away score.
- **Primary metric:** MAE, lower is better.
- **Baselines:** PGO v0 is the promotion baseline. The unblended PGO v1
  challenger is retained as a diagnostic comparison and cannot independently
  trigger promotion from the 2026 results.
- **Validation:** One untouched prospective 2026 season. Predictions and the
  blend weight are immutable before the first kickoff.
- **Candidate family:** The 25% blend is the sole primary promotion candidate
  for the 2026 results. Further models may be researched, but their 2026 scores
  are exploratory and cannot supply untouched promotion evidence.
- **Uncertainty:** A two-sided 95% percentile interval from the existing paired
  `(season, week)` block bootstrap with 10,000 samples and seed `20260721`.
- **Acceptance:** Candidate MAE below PGO v0, bootstrap lower bound strictly
  greater than zero for candidate improvement versus PGO v0, no
  sufficient-evidence subgroup regression, and every integrity check passing.
- **Failure:** Any changed base prediction, post-kickoff lock timestamp,
  incomplete final results, non-finite value, hash mismatch, count mismatch, or
  failed statistical gate leaves this candidate `HOLD` or `BLOCKED`. A locked
  game that is cancelled, forfeited, or postponed beyond its locked identity
  blocks the complete grade; it is never excluded or relocked after outcomes.
- **Unsupported uses:** This experiment does not establish causal feature
  effects, wagering profitability, calibrated win probabilities, or authority
  to replace or publish a model.

## Development evidence and fixed weight

The existing leakage-safe, season walk-forward table contains 2,127 held-out
games from 2018 through 2025. The unblended challenger has MAE `10.205173`
versus PGO v0 MAE `10.266150`, but its paired improvement interval
`[-0.024395, 0.144917]` crosses zero. It improves six of eight seasons and
regresses in 2018 and 2025. The 2025 regression is concentrated in weeks
15-18, where its MAE is `0.583464` points worse than PGO v0.

The development experiment evaluates this fixed grid:

```text
weight = 0.00, 0.05, 0.10, ..., 1.00
candidate = pgo_v0 + weight * (pgo_v1 - pgo_v0)
```

The selection rule is fixed as the greatest challenger weight whose mean MAE
strictly improves on PGO v0 in every one of the eight historical seasons. The
selected weight is `0.25`; `0.30` is the first grid value that regresses in a
season.

At weight `0.25`, the development result is:

| Metric | Result |
|---|---:|
| Candidate MAE | `10.227241` |
| PGO v0 MAE | `10.266150` |
| Mean improvement | `0.038909` |
| Paired 95% interval | `[0.017797, 0.060136]` |
| Seasons improved | `8 / 8` |

The exact seasonal improvements, in points of MAE, are `0.002555`, `0.032681`,
`0.048907`, `0.045411`, `0.033111`, `0.038096`, `0.102142`, and `0.006436`
for 2018 through 2025 respectively.

This result is **development evidence only**. The weight and selection rule
were chosen after inspecting the historical evaluation period, so its positive
interval cannot promote the model. Only the untouched prospective 2026 grade
can supply promotion evidence for this candidate.

The prospective test has limited power: it contains 272 games across roughly
18 week blocks, compared with 2,127 historical development games, while the
development improvement is only `0.038909` points of MAE. A valid `HOLD` is a
plausible and acceptable result; the gate, population, and interval are not
relaxed after results arrive.

## Architecture

Extend the existing `pgo_prospective.py` command module rather than create a
second modeling pipeline. Reuse its canonical JSON serialization, artifact and
prediction hashes, lock validation, MAE summaries, paired bootstrap, subgroup
logic, atomic writes, and blocked-receipt behavior.

Keep schema version `1` for every existing base lock and base grade receipt.
Use schema version `2` only for the derived lock and its candidate grade
receipt; the development and attestation receipts each retain their own schema
version `1` contracts.

Add two commands while preserving `lock` and `grade`:

```text
python pgo_prospective.py develop-blend \
  --predictions research/pgo_v1/validation_predictions.csv \
  --output research/pgo_stability_blend/development.json

python pgo_prospective.py derive-blend \
  --base-lock prospective_evidence/2026-07-21/prospective_lock.json \
  --base-predictions prospective_evidence/2026-07-21/prospective_predictions.csv \
  --development-receipt research/pgo_stability_blend/development.json \
  --as-of <timezone-bearing timestamp before every kickoff> \
  --output-dir prospective_evidence/2026-08-26-stability-blend \
  --attestation-output research/pgo_stability_blend/prospective_attestation.json
```

`develop-blend` deterministically reproduces the fixed grid, selection rule,
historical metrics, seasonal results, source-file SHA-256, and its own artifact
hash. It writes status `DEVELOPMENT_ONLY`, not `PASS`.

`derive-blend` validates the existing July 21 lock, verifies that the supplied
base review CSV exactly matches that lock, and validates the development
receipt. It copies the immutable game records, adds one `candidate_prediction`
per game, records candidate metadata, and writes a schema-2 lock and review CSV
in a separate, previously absent directory plus the caller-supplied tracked
attestation path. It never refits PGO v0 or PGO v1 and never edits the base
lock.

## Derived lock contract

The derived lock retains every original source hash, source-lock hash,
schedule hash, PGO v0 prediction, PGO v1 current-lineup prediction, PGO v1
full-strength prediction, subgroup flag, and game identity field. It adds:

- `schema_version = 2`;
- `candidate.kind = "fixed_convex_stability_blend"`;
- `candidate.as_of`, validated before the earliest locked kickoff;
- `candidate.pgo_v0_weight = 0.75`;
- `candidate.pgo_v1_weight = 0.25`;
- the exact formula and development-receipt SHA-256;
- `base_lock_artifact_sha256`, copied from the verified base lock;
- `base_prediction_integrity_sha256`, copied from and independently
  revalidated against the base prediction fields;
- `games[].candidate_prediction`;
- `prediction_integrity_sha256`, recomputed over every base prediction field
  plus `candidate_prediction`;
- a newly calculated derived artifact hash.

The candidate calculation is exactly:

```python
candidate_prediction = (
    0.75 * pgo_v0_prediction
    + 0.25 * challenger_prediction
)
```

No clipping, rounding, matchup override, availability inference, or live fetch
is allowed. Identical inputs and `as_of` must produce byte-identical derived
artifacts. Serialization reuses the existing canonical JSON function: sorted
keys, compact separators, UTF-8, non-finite values rejected, and Python's
shortest round-trip float representation. A runtime change that alters bytes is
a contract change caught by deterministic fixture hashes.

The existing July 21 schema-1 lock remains byte-for-byte compatible and must
continue to validate to its current artifact and prediction hashes. The grader
enters candidate behavior only when `schema_version == 2` and
`candidate.kind == "fixed_convex_stability_blend"`; it does not infer lock kind
by sniffing optional game fields.

## Prospective grading

The existing `grade` command detects the explicit schema-2 candidate without
changing its behavior or serialized output for a schema-1 PGO v1 lock. For a
derived lock it reports:

- PGO v0, unblended PGO v1, and candidate MAE on identical game rows;
- candidate improvement versus PGO v0 as the primary paired interval;
- candidate improvement versus unblended PGO v1 as a secondary paired
  interval;
- the existing subgroup results calculated for candidate versus PGO v0;
- integrity, count, MAE, aggregate-interval, and subgroup checks;
- candidate-only `PASS`, `HOLD`, or `BLOCKED` status.

Any `PASS` belongs only to the stability-blend candidate. It does not alter the
historical PGO v1 receipt, the July 21 prospective lock, public ratings, or the
site's `Experimental model — HOLD` label.

Every locked result must retain the original game ID, teams, kickoff, and game
type. A cancellation, forfeit, or postponement that prevents completion under
that exact identity makes the receipt `BLOCKED`; the grader does not drop the
game, substitute a later prediction, or reduce the denominator.

## Fail-closed behavior

Development fails on a changed CSV schema, missing or duplicate `game_id`,
non-finite margin/prediction, an evaluation population other than seasons
2018-2025, or failure to select exactly weight `0.25` under the declared rule.

Derivation fails on a missing or tampered base lock, missing or tampered
base prediction CSV, missing or tampered development receipt, a candidate
timestamp at or after any kickoff, an invalid weight, an existing candidate
field, a non-finite derived prediction, or a changed base prediction hash. It
also fails before writing anything if the output directory, either derived
artifact path, or attestation path already exists, preventing an accidental
lock rewrite.

Grading writes `BLOCKED` and exits nonzero for any lock/result integrity error.
That includes a cancelled, forfeited, or rescheduled locked game without an
exact final result. A valid statistical `HOLD` also exits nonzero and remains an
acceptable model result rather than an infrastructure failure.

## Testing

Use test-driven development in `tests/test_pgo_prospective.py`:

1. Reproduce the 21-value grid and select weight `0.25` from a controlled
   walk-forward fixture.
2. Reject malformed, duplicated, incomplete, non-finite, or wrong-season
   development rows.
3. Verify deterministic development serialization and tamper detection.
4. Derive exact candidate predictions from a valid base lock while leaving the
   input object and July 21 artifact unchanged.
5. Reject an invalid weight, post-kickoff timestamp, wrong schema or candidate
   discriminator, tampered base lock, tampered development receipt, and
   repeated derivation into an existing path.
6. Verify the old schema-1 lock bytes, hashes, and grading output remain
   unchanged when no candidate exists.
7. Grade a derived synthetic lock and verify candidate metrics, both paired
   intervals, subgroup checks, and `PASS`/`HOLD`/`BLOCKED` classification.
8. Verify a cancelled, forfeited, or kickoff-changed game blocks the whole
   grade without changing the denominator.
9. Require deterministic JSON/CSV output and no writes outside caller-supplied
   paths.
10. Generate and validate an attestation whose hashes exactly match the base
    lock, derived lock, prediction CSVs, and development receipt.

Run the focused prospective suite, protected PGO suites, then the complete
repository suite with `ResourceWarning` promoted to an error.

## Artifact and release boundaries

- Commit this design and its implementation plan at their review gates.
- Commit the implementation, tests, and deterministic `DEVELOPMENT_ONLY`
  receipt only after their verification gates pass.
- Write the derived 2026 lock under the untracked
  `prospective_evidence/2026-08-26-stability-blend/` directory.
- Generate `research/pgo_stability_blend/prospective_attestation.json` with the
  candidate kind and timestamp, earliest kickoff, development-receipt hash,
  base lock artifact/file and prediction-file hashes, and derived lock
  artifact/file and prediction-file hashes.
- Commit and push that attestation to `origin/main` before the earliest locked
  kickoff. The remote commit is the external evidence that the exact hashed
  candidate existed before results; a local timestamp alone is insufficient.
- Do not rewrite anything under `prospective_evidence/2026-07-21/`.
- Do not modify `research/pgo_v1/`, `data/mccabe_availability.csv`,
  `data/snapshots.json`, workflows, Shopify, or store files. An existing board
  workflow may refresh only its generated public timestamp after the authorized
  attestation push; protected PGO and McCabe content must remain unchanged.
- Do not publish, promote, or remove `HOLD` without a separately reviewed
  prospective receipt and release decision.

## Alternatives rejected

An artifact-only formula manifest would be shorter now but would defer
integrity-safe grading until after the season. A nested or time-varying blend
would add tuning complexity after the historical folds have already been
inspected. The fixed derived lock is the smallest complete experiment: one
immutable formula, one untouched future season, and reuse of the existing
grader.
