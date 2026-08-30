# PGO Fantasy Roster Position Authority Design

**Date:** August 29, 2026
**Status:** APPROVED FOR PLANNING
**Scope:** Revise fantasy source qualification to use a platform-neutral,
roster-authoritative position contract
**Release boundary:** Design and later synthetic implementation only. A new
remote freeze, source acceptance, canonical backtest, candidate model, public
fantasy board, push, and deployment remain separate gates.

## 1. Goal

Replace the overly strict roster/stat position-equality rule with one semantic
authority that is suitable for PGO's platform-neutral half-PPR, FLEX, and
Superflex products.

The weekly nflverse roster remains the only source that can establish fantasy
population membership and position. Player statistics provide targets after
identity and schedule validation; they never add a player or choose that
player's ranking position.

This revision must explain the August 27 source contradictions without a
player-specific allowlist, display-name join, paid source, or outcome-selected
population rule.

## 2. Prior evidence and reason for revision

The one permitted August 27 freeze at `2026-08-27T22:11:36-04:00` produced a
valid 13-source lock and a `BLOCKED` qualification receipt:

- candidate lock SHA-256:
  `e2ec765babdc1319e36255e7ee2f69904aab4db2fd0dc9e7c7f5ea80793ce508`;
- candidate receipt SHA-256:
  `587aa5cab7d4c385c6a3bade1c942b8100e0823555efd17ea4d6fcb4a5555a4b`;
- 45 `missing_roster` discrepancies;
- 44 collapsed `missing_roster_identity` natural keys; and
- 312 `position_contradiction` discrepancies.

These are historical v1 receipt findings, not a complete v2 diagnostic
inventory. Inspection of the exact locked bytes established:

- every missing-identity source row is outside the eligible population. The 51
  regular-season rows are `DEV` or `RES`; multiple rows share some of the 44
  old natural keys;
- every `missing_roster` stat row has one exact same-week GSIS roster row with
  `ACT` status, but the roster position is LB or DB. The 45 rows total 24.5
  admitted half-PPR points;
- every position contradiction has an exact roster and stat identity. The 312
  rows cover 34 hybrid or converted players, including Taysom Hill, and contain
  895.14 half-PPR points; and
- the locked roster-authoritative population contains 44,908 player-games.

The defect is therefore semantic, not missing identity resolution: the v1
qualifier treated every source position disagreement as a blocking identity
failure and required GSIS identity before determining whether a roster row was
eligible.

### August 30, 2026 inventory correction

The original one-shot wrote no development shadow. An owner-authorized,
aggregate-only, no-write capture at the same branch head corrected the complete
schema-2 diagnostic inventory without changing production, research, or public
artifacts. Its source lock SHA-256 was
`e2ec765babdc1319e36255e7ee2f69904aab4db2fd0dc9e7c7f5ea80793ce508`; its
in-memory receipt SHA-256 was
`888d1f5f707ed253a4279d6f3b2224de152d9f5b81d40ecf81f5d9db07b5e0b2`; and its
canonical aggregate stdout SHA-256 was
`b5dfdfffdb3ae1ba9693afd9e5ab40908aebc701d992a80539537c6661fb64f3`.

The schema-2 receipt was `PASS` for 13 sources with zero blocking
discrepancies. Its complete diagnostic counts, in order, were 312
`stat_position_disagreement`, 282 `act_unmodeled_roster_stat`, and 94
`noneligible_roster_missing_identity`; the first two point totals were 895.14
and 344.26. Coverage was 44,908 eligible, 35,519 matched, 9,389 zero-filled,
93 bye-skipped, and 282 excluded.

V1 filtered roster rows by modeled position before identity classification;
v2 diagnoses missing identity across all noneligible regular-season roster
rows. V2 also audits admitted-scoring stat rows when their exact `ACT` roster
position is unmodeled. These extra diagnostics remain outside the modeled
population, so they do not change eligible, matched, or zero-filled totals.
A later shadow write requires its own contract and remains development evidence
only.

These observations are development evidence. They do not convert the failed
receipt into a PASS and do not authorize a replay of the same gate.

## 3. Decision

PGO fantasy v1 uses nflverse weekly-roster position as its platform-neutral
position authority.

- Eligible raw positions are QB, RB, FB, WR, and TE.
- FB maps to RB.
- The emitted model and ranking position always comes from the applicable
  weekly `ACT` roster row.
- The player-stat position is diagnostic metadata only.
- Position, FLEX, and Superflex ranks are deterministic views of the same
  projection. They are not separate models.

PGO does not claim to mirror ESPN, Yahoo, Sleeper, or another platform's
multi-position eligibility. A later platform overlay requires its own frozen,
time-safe source contract and cannot change this base model's population or
historical receipt.

## 4. Source inventory

The source family does not change. It remains exactly:

- one pinned schedule source;
- weekly rosters for 2020 through 2025; and
- player weekly statistics for 2020 through 2025.

The lock therefore remains source-lock schema 1 and continues to bind exactly
13 URLs, raw byte counts, SHA-256 values, required columns, allowed scope, and
one timezone-bearing capture time.

No injury, practice, game-status, inactive, depth-chart, participation, PFF,
betting, market, display-name identity, or paid-source field is admitted.

## 5. Roster population contract

Roster processing follows this order for regular-season rows:

1. Validate source season, week, team, game type, and team-week coverage.
2. Read raw position and status before requiring player identity.
3. Treat a row as eligible only when `status == ACT` and raw position maps to
   QB, RB, FB, WR, or TE.
4. Require a nonblank GSIS ID for every eligible row.
5. Map FB to RB and retain the roster position as `fantasy_position`.
6. Exclude every other roster row from the model population.

A missing GSIS ID on an eligible `ACT` row is blocking. A missing GSIS ID on a
non-eligible row is a diagnostic because that row cannot enter the model.
Display name may appear in the diagnostic for human review but can never join,
deduplicate, or recover an identity.

Missing status on an otherwise eligible-position row is blocking because
eligibility cannot be established. Duplicate GSIS player-weeks, conflicting
teams, or ambiguous membership remain blocking whenever the identity can affect
population or a relevant stat join.

## 6. Player-stat reconciliation

Player-stat processing validates declared source season and regular-season
scope before reconciliation.

For this audit, a stat row is relevant when its raw position maps to a fantasy
position, at least one admitted half-PPR scoring component is nonzero, or its
nonblank GSIS ID matches an eligible roster identity. An unmodeled zero-target
row with no eligible roster match is irrelevant: it cannot enter the population
or satisfy team-week stat coverage.

For each relevant stat row:

1. Require GSIS identity.
2. Resolve the exact season-week GSIS roster row without using player name.
3. Validate unique identity, roster status, game ID, team, opponent, season,
   week, and the completed schedule mapping.
4. Use the stat row only as the half-PPR target for an exact eligible `ACT`
   roster row.
5. Emit the roster's `fantasy_position`, regardless of stat position.

An exact eligible roster row with no stat row remains a verified zero target
after team-week stat coverage passes.

A mapped or nonblank stat position that differs from the authoritative roster
position produces a diagnostic. It does not change eligibility, target, or
rank position. Mutating only the current-game stat-position field must leave
model-facing player rows byte-for-byte unchanged.

A stat row attached to one exact `ACT` roster identity whose roster position is
outside QB/RB/FB/WR/TE cannot add that player to the population. When its stat
position maps to a fantasy position or its admitted half-PPR components are
nonzero, record it as an excluded diagnostic. Unmodeled zero-target rows such
as ordinary kicker rows remain irrelevant and cannot satisfy team-week stat
coverage.

A relevant stat row with no roster identity, a non-`ACT` matching roster, a
duplicate identity, or a schedule/team contradiction remains blocking.

Each completed team-week must contain at least one stat row joined to an exact
eligible `ACT` roster identity. This prevents an empty or junk-only stat source
from turning the entire roster population into plausible zeros.

## 7. Shared model and qualification path

Qualification and `build_player_games()` must use one shared reconciliation
result. The result contains only plain data:

- eligible roster index;
- validated stat index;
- model-facing player-game rows;
- per-season coverage;
- blocking discrepancies; and
- nonblocking diagnostics.

The implementation deletes the duplicate blocked-coverage traversal rather
than adding another source adapter, class hierarchy, or dependency. A PASS
receipt and the model-facing builder must therefore interpret the same bytes
and rows identically.

`build_player_games()` refuses any blocking discrepancy. Diagnostics are
returned in its source audit but do not alter population, positions, targets,
or ordering.

## 8. Qualification receipt schema 2

The source lock remains schema 1. The qualification receipt advances to schema
2 so an old v1 receipt cannot be accepted under the revised policy.

The receipt separates:

### 8.1 Blocking discrepancies

These include at minimum:

- incomplete team, team-week, or relevant-stat team-week coverage;
- missing identity on an eligible roster or relevant stat row;
- missing eligibility status;
- duplicate or conflicting roster/stat identity;
- relevant stat identity with no roster row;
- relevant stat row matched only to a non-`ACT` roster; and
- schedule, game, season, week, team, opponent, source-byte, schema, or
  finiteness failure.

Every blocking class has total and per-season counts plus complete,
deterministically sorted natural keys. `qualification_status == PASS` requires
every blocking count to equal zero and every required check to be true.

### 8.2 Diagnostics

The nonblocking diagnostic classes are:

- `stat_position_disagreement`;
- `act_unmodeled_roster_stat`; and
- `noneligible_roster_missing_identity`.

Diagnostics record total and per-season counts and complete sorted rows. Rows
with GSIS identity include season, week, game, GSIS ID, team, roster status,
raw roster position, mapped roster position when any, and raw stat position.
The missing-identity diagnostic may include display name and source row number
only for review; neither value is used by the model.

The first two diagnostic classes also report finite admitted half-PPR point
totals. These outcome summaries document data impact but never select rows or
positions.

The receipt records `position_authority: NFLVERSE_WEEKLY_ROSTER`, the fixed
FB-to-RB mapping, and explicit counts for eligible, matched-stat, zero-filled,
bye-skipped, and excluded-stat rows.

## 9. Versioned write boundary

The August 27 candidate files remain untouched. V2 uses separate ignored
candidate paths:

- `output/pgo-fantasy-source-v2-candidate.lock.json`;
- `output/pgo-fantasy-source-v2-qualification.json`; and
- `output/.pgo-fantasy-source-v2-candidate.claim`.

Candidate publication retains exclusive no-overwrite creation, fixed-claim
ownership, exact-byte validation, rollback of owned files only, and fail-closed
behavior under interruption or concurrent writers.

Accepted paths remain:

- `research/pgo_fantasy/sources.lock.json`; and
- `research/pgo_fantasy/source_qualification.json`.

They may be created only from a newly frozen, schema-2 PASS pair after separate
authorization. Acceptance rereads raw bytes without newline normalization,
rejects duplicate JSON keys, rehashes every cached source, requalifies offline,
and refuses any existing accepted directory.

## 10. Evidence roles and execution order

The evidence sequence is fixed:

1. Implement the policy with synthetic fixtures only.
2. Run focused, repository, leakage, scope, and adversarial review gates.
3. Use the August 27 cache once as a development shadow under a new ignored
   `output/pgo-fantasy-source-v2-development-shadow.json` file. Do not modify
   either old candidate file or call the shadow accepted evidence.
4. Lock the code, policy, and expected receipt schema before another source
   capture.
5. Require separate approval for one new v2 remote freeze.
6. Accept only exit 0 PASS or exit 1 BLOCKED. Never retry to seek different
   bytes or change the contract after seeing the result.
7. Treat every other exit as an operational failure that cannot produce
   accepted evidence.
8. Even after PASS, label artifacts `LOCAL_CACHE_ONLY` until an approved
   immutable external source bundle exists.

No canonical fantasy backtest runs in this slice. The predictive holdout and
candidate ladder remain untouched.

If a future v2 freeze retrieves byte-identical historical files, the receipt
records those hashes explicitly. A later timestamp does not turn identical
bytes into statistically independent evidence.

## 11. Corrected development-shadow inventory

The August 30 aggregate-only capture establishes the exact inventory required
by any separately authorized future development shadow:

- 312 `stat_position_disagreement` diagnostics;
- 282 `act_unmodeled_roster_stat` diagnostics totaling 344.26 points;
- 94 `noneligible_roster_missing_identity` diagnostics;
- zero unexplained blocking discrepancies;
- 44,908 eligible player-games;
- 35,519 matched-stat rows; and
- 9,389 verified zero-filled rows, with 93 bye-skipped and 282 excluded stat
  rows.

The exact serialized schema-2 receipt SHA-256 is
`888d1f5f707ed253a4279d6f3b2224de152d9f5b81d40ecf81f5d9db07b5e0b2`. The
895.14 points on position-disagreement rows remain in model targets and are
assigned to the weekly roster position. These values are development assertions
against already inspected bytes, not a promotion gate. Any mismatch between the
implementation and this inventory stops for diagnosis; it is not fixed by
changing expected counts.

## 12. Verification

Test-driven implementation must prove:

- eligible `ACT` roster identity is required;
- non-eligible missing identity is diagnostic only;
- FB maps to RB;
- a Taysom-like QB roster / TE stat row emits QB with the correct target;
- changing only stat position cannot change model-facing rows;
- exact `ACT` LB/DB roster identities with offensive stats remain excluded and
  audited;
- player stats cannot expand the population;
- relevant stats with no roster, non-`ACT` roster, duplicate identity, or
  schedule/team contradiction block;
- all-postseason, empty, or junk-only stat coverage blocks;
- schema-1 qualification receipts cannot be accepted as schema 2;
- diagnostics and blockers are complete and deterministically sorted;
- JSON is canonical UTF-8, finite, LF-only, and bound to exact lock bytes;
- CRLF, duplicate-key, noncanonical, unpinned, or rehashed evidence fails;
- candidate claims, exclusive writes, interruption cleanup, foreign-writer
  preservation, and accepted-directory no-overwrite semantics remain intact;
- the old lock and receipt hashes remain unchanged; and
- team research, prospective evidence, public HTML, workflows, and store paths
  have no diff.

Focused tests, the complete repository suite with `ResourceWarning` elevated,
compilation, `git diff --check`, prohibited-input scans, and an independent
correctness/leakage review must pass before the implementation is accepted.

## 13. Alternatives rejected

### Exclude every hybrid identity

This would remove legitimate fantasy targets, including Taysom Hill, and make
source disagreement determine which players disappear. It is more biased than
using one predeclared roster authority.

### Infer position from current or prior player statistics

Current-game stat position is postgame metadata and cannot define a pregame
rank. A prior-stat state machine adds complexity and unstable cold-start rules
without a proven benefit.

### Add a manual exception list

Player-specific exceptions invite hindsight and do not generalize to future
hybrid players. No allowlist is permitted.

### Mirror a fantasy platform now

Platform eligibility is a separate product layer with its own source,
timestamp, license, and historical consistency requirements. PGO v1 remains
platform-neutral.

## 14. Stop conditions

Stop rather than infer if:

- any blocker remains under the approved v2 semantics;
- a diagnostic cannot be reproduced from exact frozen bytes;
- names are required to join identities;
- a stat row would add a player to the population;
- a current-game stat position affects model-facing eligibility or rank;
- the August 27 lock or receipt changes;
- the new candidate path, claim, or accepted research path already exists;
- source timestamps, hashes, schemas, or cache bytes disagree;
- a write failure leaves partial accepted evidence;
- protected team, prospective, public, workflow, or store artifacts change;
- a new remote freeze has not been separately authorized;
- a canonical backtest, candidate fit, public fantasy board, push, or deployment
  has not been separately authorized.

The next step after this approved design is a written implementation plan. It
does not authorize implementation or execution by itself.
