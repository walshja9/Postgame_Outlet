# PGO Fantasy Prior-Observed Historical Cohort Design

**Date:** August 31, 2026

**Status:** APPROVED FOR PLANNING

**Scope:** Add a roster-independent historical development cohort for the
existing PGO half-PPR fantasy baselines

**Release boundary:** Design and a later synthetic-only implementation slice.
Remote source capture, real-cache shadow execution, canonical backtesting,
candidate fitting, prospective locks, public-site changes, push, and deployment
remain separate approval gates.

## 1. Decision

PGO will add a second, explicitly development-only historical population named
`PRIOR_OBSERVED_8_WEEK`.

For season-week `w`, a player is eligible when a valid nflverse weekly-stat row
for that player exists in one of weeks `w-8` through `w-1` of the same regular
season. The newest prior row supplies the player's team and position. FB maps
to RB. The population never reads the current week's roster or stat rows before
membership and predictions are fixed.

This does not replace the existing 13-source weekly-roster qualification path.
That path remains the authority for source QA and future exact T-90 roster
snapshots. The new cohort exists because the repository cannot prove when
retrospective weekly-roster revisions were available historically.

The first implementation slice evaluates only the existing null and strong
simple baselines on this cohort. It does not fit a new predictive model.

## 2. Scientific contract

| Item | Contract |
|---|---|
| Question | Predict weekly half-PPR points for previously observed NFL players |
| Analysis type | Predictive continuous target; rankings are derived |
| Grain | `(season, week, gsis_id)`; game and team are prediction context |
| Competition | NFL regular season only |
| Historical seasons | 2020 through 2025 |
| Evaluation weeks | Weeks 2 through 18 when a completed regular-season schedule exists |
| Decision time | Player T-90; population and state freeze for the complete week before any game in that week is learned |
| Candidate window | The preceding eight regular-season weeks in the same season |
| Target | The existing PGO half-PPR formula |
| Outer test folds | Expanding tests for 2022, 2023, 2024, and 2025 |
| Primary metric | MAE on the existing 96-player startable pool |
| Evidence role | `DEVELOPMENT_ONLY` |
| Model status | `HOLD` / `EXPERIMENTAL` |
| Leakage status | `REVIEW_REQUIRED` |

Thursday outcomes cannot update Sunday or Monday predictions. Every player in
a season-week is predicted before any target from that season-week updates a
history or position mean.

Week 1 and a player's first observed week are cold-start coverage, not primary
metric rows. A player first observed in week `w` can first enter the candidate
population in week `w+1`.

## 3. Source boundary

The historical cohort uses exactly seven logical sources:

- the existing pinned schedule source; and
- one nflverse player weekly-stat source for each season from 2020 through
  2025.

Weekly rosters are not inputs to this contract. Locking unused roster files
would preserve the unresolved vintage problem without affecting the cohort.

Implementation reuses the repository's existing `SourceSpec`, CSV parsing,
team normalization, hashing, half-PPR scoring, and schedule validation. It adds
no package, service, model framework, or source adapter.

A single loader reads each supplied source byte sequence once, validates its
required columns, parses that same snapshot, and records byte count, SHA-256,
and row count. Hashing one read and parsing a later read is prohibited.

The initial slice has no network operation, source-freeze command, lock writer,
or accepted research path. Synthetic fixtures exercise the seven-source
contract. A later real-cache shadow requires separate authorization.

## 4. Cohort construction

The cohort builder is a pure path-to-data boundary in the existing
`pgo_fantasy.py` module. Its logical interface is:

```text
build_prior_observed_games(paths) -> (player_game_rows, source_audit)
```

It returns plain dictionaries and performs no output write.

For each season, it processes weeks chronologically:

1. Validate completed regular-season games and unique team-week schedule
   mappings.
2. Before inspecting week `w` outcomes, select players with a valid mapped
   stat row in weeks `w-8` through `w-1`.
3. Use each player's most recent prior row for last-known team and position.
4. Create a prediction row only when that last-known team has a completed game
   in week `w`.
5. Predict the complete week from state ending at week `w-1`.
6. After all predictions are fixed, join week `w` targets by GSIS identity.
7. Assign zero only when the predicted player's last-known team played and no
   current-week stat row exists.
8. Update histories only after every row in week `w` has been predicted and
   graded.

The builder also returns current-week mapped stat observations that were not
prediction candidates, including Week 1, first appearances, transition/bye
misses, and returns after expiry. These rows carry
`evaluation_eligible: false`. They never enter a pool or metric, but their
outcomes update player history after the complete week is frozen. Prediction
rows carry `evaluation_eligible: true`. Each GSIS identity still has at most
one row per season-week.

The natural identity is `(season, week, gsis_id)`. A team change cannot create
a second player row. When a predicted player records current-week statistics
for a different team, the actual target remains attached to the stable GSIS
identity and a `team_transition` diagnostic records the context mismatch.

When the last-known team is on bye, no prediction row is created. If the player
scores for another team that week, the audit records a transition/bye miss and
its positive point mass remains in the coverage denominator.

A player expires after eight consecutive unobserved weeks. Unsupported
positions never enter the cohort. FB is normalized to RB; no other position is
inferred.

## 5. Baseline evaluation

The existing baseline math remains authoritative:

- the null prediction is the fixed training-fold position mean; and
- the strong prediction uses up to eight prior player outcomes, a four-game
  half-life, and four position-mean pseudo-games.

The implementation reuses the existing chronological prediction, primary-pool,
and metric functions. It extends the baseline report boundary only enough to
accept the separately validated cohort audit and emit
`population: PRIOR_OBSERVED_8_WEEK`. It must not duplicate baseline formulas or
create a second evaluation framework.

Player histories consume both prediction rows and state-only observations,
always after the applicable week has been predicted. Training-fold and live
position means, pool selection, predictions, and metrics consume only
`evaluation_eligible: true` rows. Legacy roster rows have no marker and retain
their existing implicit value of `true`.

The primary pool remains exactly:

- 24 QBs;
- 24 RBs;
- 24 WRs;
- 12 TEs; and
- 12 remaining RB/WR/TE FLEX players.

Every evaluated season-week must fill all 96 slots. Missing predictions are
failures; they cannot disappear from the metric.

Point coverage measures positive modeled-position production:

```text
sum(max(target, 0) for graded cohort players)
------------------------------------------------
sum(max(target, 0) for all valid current-week QB/RB/FB/WR/TE stat rows)
```

The denominator includes cold starts, expired players, and transition/bye
misses. It excludes unsupported positions and invalid rows. A zero denominator
or coverage below 95% in any evaluated season-week blocks the report.

The first report remains `BASELINE_ONLY`, `DEVELOPMENT_ONLY`, `HOLD`, and
`EXPERIMENTAL`, regardless of whether the strong baseline beats the null.

## 6. Later candidate advancement gate

This design freezes the evaluation gate for a later simple candidate without
authorizing that candidate now. A candidate advances to prospective paper
tracking only when all of the following hold on identical cohort rows:

1. pooled primary MAE is at least 1% lower than the strong baseline;
2. primary MAE is lower in at least three of the four test seasons;
3. the lower bound of a paired 95% bootstrap interval for MAE improvement is
   above zero when resampling complete season-week blocks;
4. no position's pooled primary MAE is more than 1% worse; and
5. every identity, chronology, finiteness, 96-slot, and point-coverage gate
   passes.

Even a historical win is `DEVELOPMENT_ONLY — HOLD`. It authorizes only a
separately approved prospective paper track using exact pregame captures. It
does not authorize publication or promotion.

## 7. Audit and failure handling

The run blocks rather than infers when it encounters:

- a missing, unexpected, empty, unreadable, or schema-invalid source;
- a source byte/hash mismatch;
- missing or duplicate relevant GSIS identity;
- duplicate player-week statistics;
- invalid season, week, game, team, opponent, or schedule mapping;
- an ambiguous last-known team;
- a missing or invalid position on an otherwise relevant modeled-player row;
- a nonfinite scoring component, target, prediction, or metric;
- current-week or future information influencing membership or prediction;
- fewer than 96 primary-pool rows; or
- weekly positive-point coverage below 95%.

The audit reports, without silently changing the population:

- first appearances and other cold starts;
- team transitions;
- a last-known-team bye when the player scores elsewhere;
- expiration after the eight-week window; and
- excluded unsupported-position rows.

Diagnostics remain nonblocking unless their effect causes a locked coverage
gate to fail. No display-name join, manual player allowlist, same-week
participation inference, or outcome-selected repair is permitted.

Historical row selection is structurally chronological, but the provider files
do not prove when every historical revision became available. The audit must
therefore say `REVIEW_REQUIRED`, never `CLEAN`. No metric from this cohort is
canonical evidence.

## 8. Proof requirements

Synthetic tests must prove:

- changing or deleting same-week roster data cannot change cohort rows,
  predictions, or audit bytes;
- changing current-week or future-week stats cannot alter earlier membership
  or predictions;
- every week is completely predicted before state updates;
- week 1 is outside the primary metric but seeds Week 2 player history;
- state-only cold-start and transition observations update later player
  history without entering position means, pools, predictions, or metrics;
- a first appearance enters no earlier than the following week;
- a player expires after eight consecutive unobserved weeks;
- the most recent prior team and position are used and FB maps to RB;
- a missing current-week stat row becomes zero only when the last-known team
  played;
- cold-start, transition, bye-transition, expiry, and unsupported-position
  cases produce deterministic diagnostics;
- duplicate identities and schedule contradictions block;
- the 96-slot and 95% point-coverage gates fail closed;
- reversing input order produces identical canonical rows and audit; and
- the existing weekly-roster population and qualification behavior remain
  unchanged.

Verification also requires the focused fantasy suite, full repository suite
with `ResourceWarning` elevated, compilation, `git diff --check`, protected
artifact hashes, and the public `Experimental model — HOLD` label to remain
green and unchanged.

## 9. First implementation slice

The implementation plan should touch only the existing fantasy module, its
focused tests, and the approved plan document. The smallest sufficient slice
is:

1. define the seven-source historical contract;
2. build and audit the prior-observed rows with synthetic fixtures;
3. route those rows through the existing baseline evaluation; and
4. produce a deterministic in-memory development report.

It explicitly does not:

- fetch or freeze remote files;
- read the real local nflverse cache;
- write a research receipt, predictions file, or source lock;
- run a canonical or real-data backtest;
- fit a regularized candidate;
- change public HTML, workflows, Shopify, or store content;
- alter team-model or prospective evidence;
- push, deploy, or publish.

After that slice passes review, a real local-cache shadow is a separate owner
decision. Candidate fitting follows only if the shadow proves that population
and coverage are usable without changing this contract after seeing results.

## 10. Alternatives rejected

### Keep historical same-week rosters as the population

The exact bytes are useful for development QA, but their historical
publication/revision times are not preserved. They cannot establish a clean
pregame population retrospectively.

### Use current-week stat rows as the population

This would select players from the outcome being predicted, delete true zeroes,
and leak participation into evaluation.

### Add PFF or another paid source now

No paid source is required to test whether the existing model ladder has useful
signal. Licensing and API access can be evaluated later against a specific
measured gap.

### Build a new modeling framework

The repository already has the scoring, chronological baseline, pool selection,
metrics, serialization, and source-validation primitives this slice needs.
Duplicating them would add risk without evidence value.

## 11. Stop conditions

Stop rather than infer if:

- a current-week or future row affects historical membership or prediction;
- the seven-source contract cannot be validated from one read per source;
- the cohort cannot fill all 96 weekly slots or capture 95% of positive points;
- a stable GSIS identity or schedule mapping is ambiguous;
- the implementation requires a display-name join or player exception list;
- any existing 13-source qualification behavior changes;
- any protected research, prospective, public, workflow, or store artifact
  changes;
- a real-cache shadow, candidate fit, source capture, canonical backtest, push,
  publication, or deployment lacks separate authorization; or
- anyone attempts to relabel the historical leakage status from
  `REVIEW_REQUIRED` to `CLEAN` without genuine provider-vintage evidence.

The next step after written-spec approval is a detailed implementation plan.
This document does not authorize implementation or execution by itself.
