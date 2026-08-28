# PGO Fantasy Source Qualification Design

**Date:** August 27, 2026
**Status:** APPROVED FOR PLANNING
**Scope:** Freeze and qualify the historical fantasy inputs only

## 1. Goal

Create a reproducible, fantasy-specific nflverse snapshot and prove that its
2020-2025 schedule, weekly-roster, and player-stat rows satisfy the approved
half-PPR population contract. Commit the source lock and qualification receipt
only when every required check passes.

This slice does not run a canonical backtest, generate 2026 projections, change
the public site, push, deploy, publish a source bundle, or use PFF.

## 2. Decision

Qualification is strict. There is no manual exception allowlist.

- A player-stat row cannot add a player to the historical population.
- Only a regular-season weekly-roster row with an eligible position, stable
  GSIS ID, and `status == ACT` establishes population eligibility.
- Every eligible player-stat row outside that population is a blocking source
  contradiction, even when the total is small.
- An eligible `ACT` roster row with no player-stat row becomes zero fantasy
  points only after its schedule, team, identity, and source coverage pass.

If the frozen source fails, keep only a local diagnostic under `output/` and do
not create or commit accepted research evidence. A later design must approve
any change to the population contract or source family.

## 3. Alternatives rejected

An explicit exception manifest is deferred because it would introduce
row-specific judgment and possible hindsight bias before the source defect is
understood. Unioning player-stat rows into the roster population is prohibited
because the target data would determine who was eligible for prediction.

## 4. Source inventory

Use `fantasy_source_specs()` as the sole inventory:

- the immutable pinned schedule source already used by PGO;
- weekly nflverse rosters for 2020 through 2025;
- nflverse player-weekly statistics for 2020 through 2025.

The inventory is exactly 13 logical sources. No injury, inactive, practice,
depth-chart, participation, betting, or paid-source field is admitted.

One timezone-bearing `frozen_at` value applies to all entries. Raw bytes go to
the ignored content-addressed `.cache/pgo_fantasy/` directory. The existing
`pgo_sources` fetch, hash, cache, and locked-load behavior is reused; no second
downloader or new dependency is added.

The implementation footprint is limited to `pgo_fantasy.py`, its existing
focused test module, the implementation plan, and LF enforcement for the two
accepted JSON paths. No new source module or workflow is introduced.

## 5. Qualification flow

1. Preflight the exact source inventory, the timezone-bearing capture time,
   ignored cache location, and candidate output paths.
2. Freeze the 13 sources to the content-addressed cache and the ignored
   `output/pgo-fantasy-source-candidate.lock.json` candidate lock.
3. Reload every source through its recorded byte count and SHA-256. Reject a
   missing file, changed byte count, changed digest, duplicate logical source,
   missing source, or unexpected source.
4. Validate required columns, declared season, regular-season scope, completed
   schedule identity, normalized teams, finite scoring inputs, and all 32 teams
   in each roster season.
5. Reconcile roster and stat identities for all six seasons and produce a
   complete, deterministically sorted discrepancy inventory.
6. On failure, write
   `output/pgo-fantasy-source-qualification.json` with `BLOCKED` status and
   return nonzero. Do not write under `research/pgo_fantasy/`.
7. On success, generate the final lock and `PASS` receipt under `output/`,
   inspect them, then add both together to a new `research/pgo_fantasy/`
   directory and commit them with an exact path allowlist.

The model-facing `build_player_games()` remains fail closed. Qualification may
collect all discrepancies for diagnosis, but it cannot make blocked rows valid
or weaken the model-facing checks.

## 6. Reconciliation rules

GSIS ID is authoritative. Names are display-only and never join rows.

For each eligible-position regular-season stat row, the audit checks the
season, week, game, player, team, opponent, roster status, and normalized
position. It reports at least these blocking classes:

- no same-season/week GSIS roster row;
- matching roster row with status other than `ACT`;
- conflicting or duplicate team membership;
- missing or duplicated stable identity;
- schedule, game, team, or opponent contradiction;
- roster/stat position contradiction after `FB` maps to `RB`.

The receipt contains the total and per-season count for every class plus the
full sorted natural keys. `PASS` requires every blocking count to equal zero.
The audit also records matched-stat, verified-zero-fill, bye-skipped, and total
eligible counts for each season.

## 7. Accepted artifacts

`research/pgo_fantasy/sources.lock.json` records:

- schema version and historical scope;
- logical source name and season;
- canonical URL and timezone-bearing capture time;
- exact raw byte count and SHA-256;
- repository-relative content-addressed cache path;
- required columns and allowed season/game-type scope.

`research/pgo_fantasy/source_qualification.json` records:

- `qualification_status: PASS`;
- `artifact_availability: LOCAL_CACHE_ONLY`;
- SHA-256 of the exact serialized source lock;
- source inventory and coverage totals;
- zero blocking discrepancy counts;
- the checks performed and their boolean results.

Both JSON files use deterministic UTF-8, LF-only, sorted-key serialization with
finite values and a terminal newline. The receipt is invalid if its lock hash
does not match the committed lock bytes.

The exact raw cache is not committed. `LOCAL_CACHE_ONLY` therefore qualifies
the inputs on this machine but does not authorize canonical execution. A
GitHub Release asset or another approved immutable source bundle remains a
separate authorization gate.

## 8. Failure and write boundaries

- Existing accepted output paths cause a stop; qualification never overwrites
  research evidence.
- A fetch, parse, schema, identity, reconciliation, serialization, or write
  failure returns nonzero.
- A failed run cannot leave a `PASS` receipt.
- The existing team source lock, team research artifacts, July prospective
  evidence, public HTML, workflows, and Shopify paths are protected.
- Only the source-qualification code/tests/spec/plan and, after `PASS`, the two
  accepted fantasy research files may be staged.

## 9. Verification

Implementation follows test-driven development and must cover:

- exact 13-source inventory and timezone validation;
- content-addressed cache and lock-byte verification;
- missing, duplicate, changed, or unexpected sources;
- every discrepancy class and complete deterministic reporting;
- no population expansion from player statistics;
- no accepted research writes on `BLOCKED`;
- no overwrite of existing accepted paths;
- deterministic lock and receipt bytes plus receipt-to-lock binding;
- a passing synthetic source set and a blocked synthetic source set;
- unchanged behavior of `build_player_games()` and existing baseline receipts.

Focused tests, the full warning-as-error repository suite, compilation,
`git diff --check`, prohibited-field scans, and protected-artifact hashes must
all pass before a commit is described as complete.

## 10. Completion and stop conditions

This slice completes only when the real frozen snapshot produces a `PASS`
qualification, the two accepted artifacts are committed together, and all
verification gates pass.

Stop without accepted artifacts if any source cannot be frozen, any of the 13
files is incomplete, any stable identity or team/week coverage is ambiguous,
any discrepancy remains, the local cache cannot prove the lock bytes, an
accepted path already exists, or a protected artifact changes.
