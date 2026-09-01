# PGO Fantasy 2026 Prospective Initializer Design

**Date:** September 1, 2026

**Status:** APPROVED DESIGN — IMPLEMENTATION PLAN READY

**Scope:** Produce legal pregame 2026 half-PPR projections and standard,
FLEX, and Superflex rankings from immutable T-60 source snapshots

**Release boundary:** This document authorizes only its own commit. Code,
source capture, prospective execution, public-site changes, push, and deployment
remain later gates.

## 1. Decision

PGO will build the smallest prospective fantasy system that can create and
grade trustworthy 2026 player-game predictions. It will reuse the existing
half-PPR scoring, strong-baseline formula, primary-pool selection, canonical
serialization, hashing, and no-overwrite evidence patterns.

The first slice does not fit a new machine-learning model. It gives the existing
strong baseline a legally frozen pregame population, a simple cross-season
initializer, definitive game-day availability when verified, and an immutable
prospective evaluation track.

The public site may show clearly labeled experimental rankings before the model
earns scientific promotion. Fantasy analysis leads; store work remains outside
this slice.

## 2. Scientific contract

| Item | Contract |
|---|---|
| Question | At 60 minutes before kickoff, can PGO produce legal pregame half-PPR player projections and rankings using only information frozen by then? |
| Analysis type | Predictive continuous target; rankings are deterministic derivatives |
| Competition | 2026 NFL regular season only |
| Population | Frozen pregame-roster players at QB, RB/FB, WR, or TE |
| Grain | One player-game |
| Natural key | `(season, week, game_id, gsis_id)` |
| Decision time | `T = scheduled kickoff - 60 minutes` for that game |
| Forecast horizon | From `T` through the final official result of that game |
| Target | Existing PGO half-PPR scoring formula |
| Ranking views | Position, standard single-QB, FLEX, and Superflex |
| Primary metric | MAE on the locked 96-player weekly primary pool |
| Evidence role | 2026 prospective holdout |
| Initial status | `BASELINE_ONLY / EXPERIMENTAL — HOLD` |

FB maps to RB. Kicker, team-defense, postseason, preseason, DFS salary,
wagering, and dynasty-value targets are excluded.

The target formula is unchanged:

- passing yards: `0.04` points per yard;
- passing touchdowns: `4` points;
- interceptions thrown: `-2` points;
- rushing and receiving yards: `0.1` points per yard;
- rushing and receiving touchdowns: `6` points;
- receptions: `0.5` points;
- fumbles lost: `-2` points;
- successful passing, rushing, or receiving two-point conversions: `2` points;
  and
- return touchdowns: `6` points.

There are no yardage bonuses, first-down points, tight-end premium, or
platform-specific bonuses.

This T-60 contract supersedes the earlier fantasy T-90 rule only for this new
2026 prospective track. It does not alter the historical T-90 development
cohort, the July team-model prospective lock, or any team-rating artifact.

## 3. Preview and evidence are separate

The system has two output classes:

1. **Preview:** A replaceable, timestamped ranking generated earlier in the
   week from the latest validated inputs. It is useful to readers but is not
   gradeable evidence.
2. **T-60 lock:** An immutable prediction package for one game, generated from
   inputs captured no later than `T`. Only this package may be graded.

An earlier preview never becomes a lock by relabeling. A T-60 run independently
validates its own source bytes, timestamps, identities, coverage, model
configuration, and predictions.

The site must identify every displayed artifact as either `Preview` or
`T-60 locked`. An unverified player may remain visible in a preview with an
`UNVERIFIED` label. Unverified availability cannot enter a gradeable lock.

A weekly preview ranks the complete slate. A per-game lock freezes only that
game's player projections and eligibility. Cross-game ordinal ranks are derived
from the available rows and are not themselves evidence until every game in the
week has an immutable lock.

## 4. Minimal architecture and data flow

The implementation consumes explicitly supplied frozen local files. Source
acquisition is separate from projection math; the model does not fetch PFF or
add a new provider SDK, database, service, or modeling framework.

```text
frozen schedule + roster + availability + completed stats
                         |
                  strict validation
                         |
             normalized player-game state
                         |
         existing null and strong baseline math
                  /                  \
       replaceable preview       immutable T-60 lock
                                         |
                              finalized official results
                                         |
                                  immutable grade
```

The implementation reuses existing repository helpers when their contracts
match. It must not duplicate the half-PPR formula, `strong_baseline()`, primary
pool selection, canonical JSON rules, or hardened no-overwrite behavior.

One deterministic command supports preview generation and T-60 locking through
explicit modes. Manual invocation is the opening-night fallback. Any later
scheduler calls the same command rather than introducing a second prediction
path.

## 5. Source contract

### 5.1 Required inputs

Each T-60 game package requires:

- a pinned schedule row containing season, official week, game ID, both teams,
  and timezone-bearing scheduled kickoff;
- a frozen pregame roster snapshot containing stable GSIS ID, displayed name,
  team, mapped position, and roster status;
- frozen official inactive or equivalent definitive availability evidence for
  both participating teams; and
- frozen completed regular-season player statistics used for player history.

The roster snapshot is authoritative for current team, opponent, position, and
population. Historical stat rows never override current roster context.

Player history may use only final games whose information was available before
`T`. The current player-game target, partial live stats, later corrections,
postgame fields, and any source captured after `T` are prohibited features.

### 5.2 Coverage and identity

A valid game lock must prove that both participating teams were processed by
the roster and availability sources. A league-wide preview must report every
scheduled team it did and did not process.

Every player requires one nonempty stable GSIS ID. The validator blocks on:

- duplicate natural identities;
- ambiguous or display-name-only matches;
- missing required fields;
- team, opponent, or schedule contradictions;
- unsupported positions other than the explicit FB-to-RB mapping;
- nonfinite values;
- timestamps without timezones;
- source capture after `T`; or
- incomplete two-team availability coverage.

Absence from an incomplete injury page never means healthy. Once a complete
official inactive source proves both teams were processed, rostered players not
declared inactive may be treated as active for this game lock.

### 5.3 Source receipt

Each source entry records:

- logical source kind and source identity or URL;
- raw byte count and SHA-256;
- source-provided as-of time when available;
- local capture time;
- parsed row count;
- teams processed; and
- schema version.

The model must hash and parse the same immutable byte sequence. Hashing one read
and parsing a later read is prohibited.

## 6. Projection and initialization

### 6.1 Frozen constants

Before Week 1, freeze:

- one position mean for QB, RB, WR, and TE from qualified 2020-2025
  stats-only baseline evidence;
- an eight-game player-history window;
- a four-game half-life;
- four position-mean pseudo-games;
- the half-PPR scoring formula; and
- deterministic ranking and tie-break rules.

Historical weekly roster files are not used to estimate the frozen position
means, so their unresolved publication vintage is not imported into this
prospective initializer.

The frozen model configuration records its timezone-bearing freeze time and the
SHA-256 of the accepted position-mean evidence receipt; a bare set of manually
entered means is not gradeable.

### 6.2 Strong baseline

For a player with legal history, use the existing strong-baseline calculation.
Let `y_0` be the newest prior outcome, let `w_i = 2^(-i / 4)`, and let
`mu_position` be the frozen position mean:

```text
prediction = (sum(y_i * w_i) + 4 * mu_position)
             / (sum(w_i) + 4)
```

History contains at most the eight most recent completed regular-season games
from the current season and the immediately preceding season under the same
GSIS ID. A 2025-to-2026 team change does not break identity; the current frozen
roster still supplies 2026 context. Games before the immediately preceding
season are too stale for this initializer and are ignored.

Position means and model parameters remain fixed throughout the 2026 holdout.
Final games may enter later player histories only after their official result
is available and only for later decision times.

### 6.3 Cold starts and availability

A player without legal 2025-2026 history receives the frozen position mean and
`initialization_reason = TRUE_COLD_START`. This is an explicit baseline prior,
not a claim that the model knows the player's role.

A verified inactive player remains in the immutable player-game package with a
projection of `0.0`, `availability_status = INACTIVE`, and
`ranking_eligible = false`. Verified active players retain the baseline
projection. An availability state that cannot be verified blocks the game lock
rather than triggering a guessed probability.

Each prediction row records:

- the natural key and displayed player context;
- scheduled kickoff and decision time;
- projection and ranking eligibility;
- availability status;
- history count;
- initialization reason;
- model/configuration hash; and
- source-lock and prediction-integrity hashes.

### 6.4 Ranking views

The same half-PPR projection powers every view:

- position rankings use the player's mapped position;
- the standard single-QB view consists of those position rankings plus FLEX;
- FLEX admits RB, WR, and TE;
- Superflex admits QB, RB, WR, and TE.

The standard view does not invent a cross-position overall score or
value-over-replacement model. Superflex changes only eligibility in the
combined list.

Rank by projection descending, then GSIS ID ascending as the deterministic
tie-break. These are ranking views, not separately fitted models.

As each game reaches T-60, its locked player rows may replace their preview rows
on the site. The displayed ordinal ranks may therefore change as later games
lock, but no locked player projection changes. Grading reconstructs the final
weekly ranks and 96-player pool solely from the union of immutable per-game
locks, without reading outcomes.

No opponent adjustment, market line, paid grade, depth-chart inference, rookie
scouting model, injury-severity guess, or player-specific manual exception is
admitted in this slice.

## 7. Immutable artifacts

### 7.1 T-60 lock

A lock is append-only and bound to one game and model version. It contains:

- schema and model versions;
- code SHA and configuration hash;
- exact kickoff and decision timestamps;
- all source receipts and their aggregate hash;
- player rows and ranking eligibility;
- row counts and two-team coverage;
- prediction-integrity hash; and
- artifact SHA-256.

The locking command derives wall-clock time and code SHA itself. It refuses a
lock when any runtime model file differs from that committed SHA; callers do
not supply backdateable lock times or arbitrary code identities.

The lock and its human-readable prediction table are created as one accepted
package. An existing target path is a hard stop; no command overwrites it.

### 7.2 Result and grade

Results are a separate postgame input. Grading requires final official results,
the exact lock bytes, and matching source, configuration, prediction, and
artifact hashes. Missing player stats become zero only after game-result and
identity coverage prove the player belonged to the locked population.

Canceled games and games without final official results are not graded. A
postponed game keeps its old lock as preserved, ungraded evidence and requires a
new T-60 lock against the rescheduled kickoff.

## 8. Validation charter

### 8.1 Holdout and folds

The entire 2026 regular season is the untouched prospective holdout. No
scientific promotion decision occurs before the final regular-season game is
graded.

Each official NFL week is one reporting fold. Pooled results are
player-game-weighted, while every weekly result and failure remains visible.
The model cannot drop an unfavorable week.

### 8.2 Common primary pool

The deterministic weekly primary pool contains exactly 96 ranking-eligible
players selected by the strong baseline before outcomes:

- 24 QBs;
- 24 RBs;
- 24 WRs;
- 12 TEs; and
- the next 12 unselected RB, WR, or TE players as FLEX.

The null and strong baseline are graded on exactly these same rows. Inactive
players are not ranking eligible and therefore cannot enter the pool. Fewer
than 96 eligible rows blocks that week and the season-level promotion gate.

### 8.3 Metrics

The primary metric is half-PPR MAE, lower is better. The locked comparison is:

- **null:** frozen position mean; and
- **strong:** the approved eight-game, four-game-half-life, four-pseudo-game
  baseline.

Secondary diagnostics are RMSE, signed bias, weekly Spearman rank correlation,
primary MAE by position, true-cold-start performance, active/inactive counts,
largest misses, and missing/blocked coverage. They cannot replace the primary
metric.

### 8.4 Uncertainty and acceptance

Use a paired block bootstrap of the null-minus-strong absolute-error difference
with seed `20260901` and 10,000 resamples. Each resampled unit is one complete
official week, keeping players and games exposed to the same weekly environment
together.

Scientific `PASS` requires every condition below:

1. Every completed 2026 regular-season game has a valid T-60 lock.
2. Every regular-season week forms the complete 96-player primary pool.
3. Strong-baseline pooled primary MAE is at least 1% lower than null MAE.
4. The lower bound of the paired 95% improvement interval is above zero.
5. The strong baseline has lower primary MAE in a strict majority of weekly
   folds; a tie is not a win.
6. Source, identity, chronology, finiteness, common-row, hash, and grade-binding
   checks all pass.
7. A completed manual prospective leakage audit returns `CLEAN`.

A statistical shortfall is `HOLD` with publication status `EXPERIMENTAL`.
Missing, contradictory, after-T, or integrity-invalid evidence is `BLOCKED`.
Neither result may be converted to PASS by changing this gate after outcomes
are visible.

Passing this gate qualifies the simple prospective fantasy baseline. Any later
candidate must beat this strong baseline on identical locked rows under a new,
predeclared acceptance contract.

## 9. Versioning and tuning firewall

Weekly grades are descriptive monitoring, not tuning data for the active 2026
epoch. Position means, weights, scoring, pool rules, metrics, thresholds, and
source semantics stay frozen.

Any formula, feature, source-schema, parameter, target, population, or ranking
eligibility change creates a new model version and evidence epoch. Evidence
from different versions cannot be pooled. A midseason version may run as a
clearly labeled shadow, but it cannot rewrite earlier locks or inherit the
original full-season promotion claim.

Historical roster provenance remains `REVIEW_REQUIRED`. Clean prospective 2026
captures do not retroactively certify historical source availability.

## 10. Failure and write behavior

All trust-boundary validation completes before an accepted package is
published. Output bytes use strict UTF-8, canonical finite JSON, stable ordering,
and one terminal newline.

Complete outputs are staged and durably flushed before exclusive promotion.
On failure, cleanup removes only paths demonstrably owned by that run. A failed
run leaves no accepted partial lock and never deletes or overwrites a foreign
artifact.

A retry may occur only while the current time is no later than `T`. Once `T`
passes, a missing lock produces a `BLOCKED` diagnostic and cannot be recreated
as if it were timely.

Stop rather than infer when:

- a required source, team, player identity, or timestamp is missing;
- source bytes change between hashing and parsing;
- roster, availability, schedule, or game-result coverage conflicts;
- any feature is not proven available by `T`;
- output already exists or exclusive publication loses a race;
- any value or serialized artifact is nonfinite or noncanonical;
- grading cannot bind the exact original lock; or
- a protected team, historical, prospective, public, workflow, or unrelated
  artifact changes.

## 11. Proof requirements

Focused tests must prove:

- exact T-60 acceptance and after-T rejection;
- changing current-game or future results cannot alter an earlier lock;
- only finalized pre-T games enter history;
- the eight-game window, cross-season boundary, half-life, shrinkage, and true
  cold-start prior are exact;
- current roster context overrides historical team and position context;
- FB maps to RB and unsupported positions block;
- inactive players lock at zero and cannot rank;
- unverified availability may appear only in preview and blocks a game lock;
- duplicate identity, incomplete two-team coverage, and schedule contradiction
  fail closed;
- input reordering produces byte-identical canonical artifacts;
- hashing and parsing use the same byte snapshot;
- existing outputs, concurrent publishers, interrupted writes, and cleanup
  failures never overwrite or delete foreign evidence;
- postponed games require a new lock and preserve the old lock;
- grading requires exact lock, source, configuration, prediction, and result
  binding;
- the weekly rank and primary pool reconstructed from per-game locks are
  deterministic and outcome-independent;
- every weekly pool contains exactly 96 unique player-games; and
- PASS, HOLD, and BLOCKED receipts follow the locked gate exactly.

Repository verification also requires:

- focused fantasy and prospective suites;
- the full test suite with `ResourceWarning` elevated;
- Python compilation;
- `git diff --check`;
- protected-artifact hash comparison;
- unchanged July team and historical evidence; and
- the public `Experimental model — HOLD` label remaining intact until a genuine
  release decision.

## 12. Site and release boundary

The site may consume the latest verified weekly preview or a ranking view
derived from per-game T-60 locks. The fantasy surface must visibly show:

- `EXPERIMENTAL — HOLD`;
- artifact update time;
- `Preview` or `T-60 locked`;
- half-PPR scoring; and
- a methodology or receipt link.

Analysis appears before merchandise. This slice adds no store work, theme
redesign, PFF integration, league synchronization, lineup optimizer, or new web
service.

The first implementation and verification remain local. Source capture,
opening-night execution, public artifact generation, push, and deployment are
separate recorded actions after their prerequisites pass. A successful local
implementation does not itself publish anything.

The July team-model lock, McCabe comparison, historical snapshots, checked-in
ratings, and unrelated untracked files remain untouched.

## 13. Shape of done

The implementation slice is complete when one deterministic path can:

1. validate frozen prospective sources;
2. generate a labeled preview;
3. create an immutable T-60 game lock;
4. produce deterministic standard, FLEX, and Superflex rankings;
5. grade the exact lock after final results; and
6. pass every focused, repository, integrity, and protected-scope check.

That completion means the prospective evidence system is operational. It does
not mean the model has earned PASS. Scientific promotion remains impossible
until the complete 2026 regular season satisfies Section 8.4.

The next step after user review of this written specification is a detailed
implementation plan. No implementation begins from this document alone.
