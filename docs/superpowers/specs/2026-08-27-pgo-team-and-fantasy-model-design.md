# PGO Team and Fantasy Model Design

**Status:** Approved design; implementation not started
**Date:** August 27, 2026
**Product:** Postgame Outlet NFL team ratings and weekly fantasy projections
**Release boundary:** Specification commit only. Model execution, source capture,
prospective locking, public-site changes, and deployment require later gates.

## 1. Decision

Postgame Outlet will maintain two independently evaluated models:

1. a pregame NFL team-margin model whose neutral-field ratings are a derived
   public view; and
2. a player-game model for weekly half-PPR season-long start/sit rankings.

The models may share frozen schedules, player identities, rosters, injuries,
official inactive lists, and matchup context. They must not share targets,
validation receipts, promotion status, or unsupported claims. A PASS by one
model does not promote the other.

The website and store do not change in this design slice. Model integrity and
evidence come first; commerce remains downstream of fantasy content.

## 2. Scientific contracts

| Contract | Team model | Fantasy model |
|---|---|---|
| Question | Predict final home-team scoring margin | Predict each active player's weekly half-PPR points |
| Analysis type | Predictive continuous target; ranking is derived | Predictive continuous target; rankings are derived |
| Competition | NFL regular season only | NFL regular season only |
| Grain | One game | One player-game |
| Natural key | `game_id` | `(game_id, gsis_id)` |
| Decision time `T` | 90 minutes before scheduled kickoff | 90 minutes before that player's scheduled kickoff |
| Target | `home_score - away_score` | Locked half-PPR scoring formula below |
| Historical evaluation | Existing 2018-2025 evidence | Expanding 2022-2025 test folds using 2020 onward |
| 2026 role | Existing immutable prospective lock | New immutable prospective lock before Week 1 |
| Public derivatives | Neutral-field rating and rank | Position, FLEX, and Superflex rank |
| Initial status | Existing public `Experimental model — HOLD` | `Experimental model — HOLD` |

Game cancellations, games without final official results, and postseason and
preseason games are excluded from grading. A postponed game uses its actual
rescheduled kickoff and a new pregame evidence freeze.

## 3. Fantasy population and scoring

The fantasy population is every officially game-day-active quarterback,
running back, fullback, wide receiver, and tight end. Fullbacks map to running
back for rankings. Officially inactive players are marked `OUT`, assigned no
rank, and retained in the audit rather than silently dropped.

The locked scoring formula is:

- passing yards: `0.04` points per yard;
- passing touchdowns: `4` points;
- interceptions thrown: `-2` points;
- rushing yards: `0.1` points per yard;
- receiving yards: `0.1` points per yard;
- rushing and receiving touchdowns: `6` points;
- receptions: `0.5` points;
- fumbles lost: `-2` points;
- successful passing, rushing, or receiving two-point conversions: `2` points;
- return touchdowns: `6` points.

No yardage bonuses, first-down points, tight-end premium, kicker scoring, team
defense scoring, or platform-specific bonuses are admitted in v1.

FLEX combines RB/FB, WR, and TE. Superflex combines QB, RB/FB, WR, and TE. Both
are deterministic rankings of the same player projections, not separate models.

## 4. Architecture and ownership

The two pipelines share a small evidence boundary and remain independent after
feature construction:

```text
frozen schedule / identities / rosters / injuries / official inactives
                              |
                 time-safe shared evidence
                     /                 \
          team-margin pipeline     player-game pipeline
          team receipt + lock      fantasy receipt + lock
```

The team pipeline cannot read fantasy outcomes. The fantasy pipeline cannot use
team outcomes, current-game player statistics, or current-game participation
after `T`. Neither pipeline reads data from the public website.

Implementation should reuse the repository's existing standard-library and
NumPy source validation, hashing, regularized fitting, receipt, and atomic-write
patterns. No new framework, service, or ML dependency is warranted for v1.

## 5. Data contract and provenance

### 5.1 Separate locks

Create a fantasy-specific source lock and cache. Do not edit or regenerate
`research/pgo_v1/sources.lock.json`, the July team research artifacts, the July
21 prospective lock, or the existing stability-blend attestation.

Every fantasy source entry records:

- logical source name and season;
- canonical URL;
- timezone-bearing capture time;
- exact raw byte count and SHA-256;
- content-addressed cache path;
- required schema and allowed season/game-type scope.

A URL and hash without preserved bytes is not a reproducible snapshot. Initial
development may use a local content-addressed cache. A future accepted run must
package the exact cache as a GitHub Release asset or another explicitly approved
immutable artifact. Creating that external artifact is a separate authorization.

### 5.2 Required sources

Shared evidence requires:

- schedule and official kickoff timestamps;
- weekly rosters with stable GSIS identities;
- official injury/practice reports and their available-at metadata;
- complete official game-day inactive evidence for both teams in every game;
- historical snap counts, shifted before the predicted game;
- historical player and team weekly statistics, shifted before the predicted
  game.

The existing nflverse sources remain suitable starting points, subject to the
new frozen fantasy lock and the audit rules below. Official inactive evidence
must retain source identity, source URL, applicable game, capture/publication
time, exact raw hash, and every listed player identity.

### 5.3 Reconnaissance findings and historical boundary

The August 27 read-only source audit found:

- the current 2013 and 2025 remote player-weekly-stat bytes no longer match the
  hashes recorded in the July team lock, while their current schemas contain the
  required scoring components;
- weekly rosters provide stable GSIS keys and roster status, but roster status is
  not a substitute for the official game-day inactive list;
- the sampled 2013 injury file contains `date_modified`, while the sampled 2025
  file does not, so injury-row revision timing alone cannot reconstruct every
  90-minute state;
- player-stat rows outside the same-week `ACT` roster universe fall from 195 in
  2019 to 9, 15, 0, 5, 3, and 13 in 2020-2025 respectively. Earlier seasons have
  materially larger roster/status disagreement.

Fantasy v1 therefore starts in 2020. The pipeline must reconcile and explain
every remaining stat/roster exception rather than treating the small counts as
automatically valid. The team model retains its existing historical window.

### 5.4 Identity and availability rules

GSIS ID is authoritative for roster, injury, inactive, and player-stat joins.
PFR IDs may join snap counts only through an audited one-to-one mapping. Display
name joins are prohibited. Ambiguous, duplicate, or missing identities block the
affected run.

An official inactive designation at `T` overrides every projection and produces
`OUT`. An unresolved status is not interpreted as healthy. If complete inactive
coverage is unavailable for either team, the final prediction window is
`BLOCKED`.

## 6. Team-model track

The current development candidate remains the fixed convex stability blend:

```text
0.75 * pgo_v0_prediction + 0.25 * challenger_prediction
```

Its committed development receipt reports 2,127 games over eight test seasons,
MAE `10.227240775858016` versus pgo v0 MAE `10.266150229901271`, mean improvement
`0.038909454043254854`, and paired interval
`[0.017797136148700477, 0.060136010087280437]`. All eight recorded seasonal mean
improvements are positive. This remains development evidence, not a public PASS.

The derived 2026 predictions and attestation are immutable. Do not change their
weights, predictions, hashes, decision time, schedule, or grade rules. The
existing prospective grader remains authoritative. The public team model stays
`Experimental model — HOLD` until that locked candidate earns a genuine
prospective PASS.

Further team work may analyze errors or create a separately versioned v2
development candidate. It cannot retune or rewrite the locked 2026 candidate.

## 7. Fantasy-model ladder

Candidates climb only when the prior rung is implemented and evaluated on the
same rows and folds:

1. **Null baseline:** training-fold historical mean by position.
2. **Strong simple baseline:** a shifted player rolling mean shrunk toward the
   position mean, with a documented cold-start fallback.
3. **First candidate:** a small regularized direct half-PPR model using only
   time-safe prior information.

The first candidate may use:

- shifted prior fantasy points over declared short and medium windows;
- shifted offensive snaps and snap share;
- shifted attempts, carries, targets, receptions, and opportunity shares;
- pregame roster role, experience, and cold-start indicators;
- time-safe team and opponent context;
- injury, practice, game-status, and inactive evidence available by `T`.

The following are prohibited:

- current-game snaps, attempts, carries, targets, receptions, yards, scores, or
  participation derived from the final box score;
- full-season or end-of-season aggregates joined backward into earlier weeks;
- post-kickoff injury revisions or corrected records without an as-of vintage;
- opponent features that include the game being predicted;
- global preprocessing, feature selection, imputation, or tuning across a test
  fold;
- display-name joins or outcome-selected row filters.

A locked team forecast may enter only as a fantasy ablation candidate. It is
retained only if it improves the fantasy acceptance metrics on identical rows;
the baseline must not depend on it.

Direct half-PPR prediction is the v1 candidate. Component-stat models, boosted
trees, neural networks, simulations, and separate position models are deferred
until the simpler model's held-out errors demonstrate a specific need.

## 8. Fantasy validation

### 8.1 Walk-forward folds

Use expanding season folds with two training-only seasons:

| Train | Test |
|---|---|
| 2020-2021 | 2022 |
| 2020-2022 | 2023 |
| 2020-2023 | 2024 |
| 2020-2024 | 2025 |

After candidates, features, and gates are frozen, generate an immutable 2026
prospective prediction lock before Week 1. The 2026 outcomes are not available
for tuning.

All transforms and parameters are fitted inside each training fold. Player rows
from the same game stay in the same fold. Candidates and baselines use identical
eligible rows. Missing predictions count as failures rather than disappearing
from the comparison.

### 8.2 Primary population and metric

The primary metric is MAE, lower is better, on a common 12-team startable pool
selected before outcomes by the locked strong simple baseline each week:

- top 24 QBs, covering QB and Superflex demand;
- top 24 RB/FB players;
- top 24 WRs;
- top 12 TEs;
- top 12 remaining RB/FB, WR, or TE FLEX players.

The baseline-selected pool is fixed and shared by every candidate. A candidate
cannot choose its own easier evaluation rows.

Secondary diagnostics include all-active-player MAE, position MAE, RMSE, signed
bias, rank correlation, cold-start performance, injury-status slices, and the
largest misses. These diagnostics cannot replace the locked primary metric.

### 8.3 Acceptance gate

Fantasy v1 earns historical PASS only when every condition is true:

1. pooled primary MAE is at least 1% lower than the strong simple baseline;
2. primary MAE is lower in at least three of the four outer test seasons;
3. the lower bound of a paired 95% bootstrap interval for MAE improvement is
   above zero, clustering all player rows by season-week;
4. no position has pooled primary MAE more than 1% worse than the strong simple
   baseline;
5. source, coverage, identity, finiteness, and common-row checks pass;
6. the completed manual leakage audit verdict is `CLEAN`.

Failure to establish improvement is `HOLD`, not an infrastructure error. Missing
or contradictory evidence, identity ambiguity, non-finite values, leakage, or
receipt-integrity failure is `BLOCKED`. Neither outcome is converted to PASS by
changing the gate after viewing results.

## 9. Leakage and uncertainty controls

Before any metric is trusted, the audit must:

- inventory every raw feature with event, publication, and revision time;
- prove every retained value was available by `T`;
- verify stable ordering and shift-before-roll behavior;
- perturb future outcomes and prove earlier feature rows do not change;
- trace roster, injury, inactive, opponent, and team-context join cardinality;
- prove training precedes testing and preprocessing is fold-local;
- run automated target-alias, duplicate, and suspicious-correlation checks;
- manually resolve every automated review item.

Automated heuristics cannot issue `CLEAN`. An unresolved audit is
`REVIEW REQUIRED` and blocks predictive promotion.

The paired improvement interval resamples season-week blocks so players and
games sharing the same weekly environment move together. Report every fold and
position slice; do not hide an unfavorable season.

## 10. Outputs and execution

The smallest acceptable implementation is one fantasy module plus focused
tests, reusing existing helpers where their contracts match. It supports four
explicit operations:

1. freeze and validate fantasy sources;
2. build and audit the time-safe player-game table;
3. backtest baselines and the fixed candidate;
4. create or grade immutable prospective predictions.

Each prospective prediction row records:

- game ID, GSIS ID, displayed player name, team, opponent, and position;
- scheduled kickoff and exact decision timestamp;
- availability status;
- half-PPR projection;
- position, FLEX, and Superflex rank when eligible;
- source-lock, model-artifact, and prediction-integrity hashes.

Final runs are schedule-driven by kickoff window. They require complete official
inactive coverage and use no overwrite semantics. Existing output paths cause a
stop. A failed write leaves no accepted partial package.

Required evidence artifacts are:

- modeling and validation charter;
- fantasy source lock and source audit;
- fold and baseline report;
- validation predictions;
- leakage audit;
- historical backtest receipt;
- 2026 prospective predictions and lock;
- later, an outcome-grade receipt and model card.

## 11. Public and authorization boundaries

No implementation step in this design authorizes:

- overwriting any checked-in team artifact or existing prospective evidence;
- acquiring or publishing a new source bundle;
- running a canonical fantasy backtest or 2026 prediction lock;
- changing public team status;
- altering the Shopify theme, navigation, store, or GitHub Pages artifact;
- pushing, deploying, or publishing fantasy rankings.

After a structurally valid 2026 fantasy lock exists, an explicitly experimental
fantasy board may be proposed separately. It must show source and update time,
model status, scoring format, and methodology/accountability links. Merchandise
remains after the fantasy analysis.

## 12. Verification and stop conditions

Implementation is not complete until focused and full repository tests pass,
protected artifacts have identical hashes, all generated values are finite,
source and prediction receipts bind exact bytes, and a manual code/leakage
review finds no unresolved issue.

Stop rather than infer when:

- an official inactive source is incomplete or ambiguous;
- a source hash differs from the accepted lock;
- a required historical source cannot be preserved reproducibly;
- a player lacks a stable identity;
- a feature's availability at `T` cannot be proved;
- evaluation populations differ between candidates;
- a protected team or prospective artifact changes;
- a result is being used to justify a post-hoc metric, fold, feature, or gate
  change;
- public or external mutation lacks explicit authorization.

## 13. Non-goals for v1

- DFS salary optimization, prop or wagering recommendations
- Dynasty valuation or waiver automation
- League-account synchronization
- Kicker or team-defense projections
- A lineup optimizer or personalized roster assistant
- Component-stat, simulation, boosted-tree, or neural-network systems without a
  demonstrated held-out need
- A website redesign or store change

The next step after review of this specification is a test-driven implementation
plan. No implementation begins from this design document alone.
