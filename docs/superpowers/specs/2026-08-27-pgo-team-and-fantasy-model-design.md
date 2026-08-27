# PGO Team and Fantasy Model Design

**Status:** Approved revised design; baseline-only code implemented and locally
verified; canonical source capture and model execution not started
**Date:** August 27, 2026
**Product:** Postgame Outlet NFL team ratings and weekly fantasy projections
**Release boundary:** Baseline implementation only. Model execution, source
capture, prospective locking, public-site changes, and deployment require later
gates.
**Revision:** Fantasy v1 is independent and nflverse-only. PFF and every other
paid source are excluded. Current-week injury and game-day inactive evidence are
not model inputs until a separately licensed, time-safe source is approved.

## 1. Decision

Postgame Outlet will maintain two independently evaluated models:

1. a pregame NFL team-margin model whose neutral-field ratings are a derived
   public view; and
2. a player-game model for weekly half-PPR season-long start/sit rankings.

The models may share frozen schedules, player identities, rosters, lagged player
and team statistics, and matchup context. They must not share targets,
validation receipts, promotion status, or unsupported claims. A PASS by one
model does not promote the other. Fantasy v1 cannot read PFF data or any
current-week injury, practice, game-status, or inactive field.

The website and store do not change in this design slice. Model integrity and
evidence come first; commerce remains downstream of fantasy content.

## 2. Scientific contracts

| Contract | Team model | Fantasy model |
|---|---|---|
| Question | Predict final home-team scoring margin | Predict each roster-eligible player's weekly half-PPR points |
| Analysis type | Predictive continuous target; ranking is derived | Predictive continuous target; rankings are derived |
| Competition | NFL regular season only | NFL regular season only |
| Grain | One game | One player-game |
| Natural key | `game_id` | `(game_id, gsis_id)` |
| Decision time `T` | 90 minutes before scheduled kickoff | 90 minutes before that player's scheduled kickoff |
| Target | `home_score - away_score` | Locked half-PPR scoring formula below |
| Historical evaluation | Existing 2018-2025 evidence | Expanding 2022-2025 test folds using 2020 onward |
| 2026 role | Existing immutable prospective lock | Lock the model before Week 1; lock predictions append-only at each T-90 window |
| Public derivatives | Neutral-field rating and rank | Position, FLEX, and Superflex rank |
| Initial status | Existing public `Experimental model — HOLD` | `Experimental model — HOLD` |

Game cancellations, games without final official results, and postseason and
preseason games are excluded from grading. A postponed game uses its actual
rescheduled kickoff and a new pregame evidence freeze.

## 3. Fantasy population and scoring

The historical fantasy population is every quarterback, running back, fullback,
wide receiver, and tight end whose nflverse weekly roster status is `ACT` for
the applicable regular-season week. `ACT` means on the NFL active roster; it
does not prove that the player dressed or participated in that game. Fullbacks
map to running back for rankings.

Every eligible roster row receives a target. A missing player-stat row is
exactly zero fantasy points after the source audit proves that the player and
team-week identities are valid. Healthy scratches, game-day inactives, and
active players with no recorded statistics therefore remain legitimate zero
outcomes instead of disappearing from evaluation.

Fantasy v1 does not emit `OUT` or claim confirmed game-day availability.
Prospective rows carry `availability_status = UNVERIFIED`. A start/sit surface
cannot hide this limitation or suppress a player based on an inferred status.

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
frozen schedule / identities / ACT rosters / lagged stats and snaps
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
- weekly rosters with `status`, stable GSIS identities, and all 32 teams;
- historical snap counts, shifted before the predicted game;
- historical player and team weekly statistics, shifted before the predicted
  game.

The existing nflverse sources remain suitable starting points, subject to the
new frozen fantasy lock and the audit rules below. The fantasy lock excludes
injury reports, depth charts, inactive lists, PFF, betting data, and every
source without a reproducible pregame contract.

### 5.3 Reconnaissance findings and historical boundary

The August 27 read-only source audit found:

- the current 2013 and 2025 remote player-weekly-stat bytes no longer match the
  hashes recorded in the July team lock, while their current schemas contain the
  required scoring components;
- weekly rosters provide stable GSIS keys and roster status, but roster status is
  not a substitute for the official game-day inactive list;
- [nflverse documents](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html#nflverse-roster-data)
  that roster data update daily, while historical weekly rows do not preserve
  an original per-row capture timestamp. Historical `ACT` is therefore a
  population rule, not a predictive feature; prospective runs must capture and
  hash the exact roster bytes available at T;
- the sampled 2013 injury file contains `date_modified`, while the sampled 2025
  file does not, so injury-row revision timing alone cannot reconstruct every
  90-minute state;
- [nflverse's current availability documentation](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html#injury-data)
  says its injury source died after the 2024 season and provides no 2025 data,
  so current-week injury fields cannot form a consistent 2020-2025 feature
  family;
- player-stat rows outside the same-week `ACT` roster universe fall from 195 in
  2019 to 9, 15, 0, 5, 3, and 13 in 2020-2025 respectively. Earlier seasons have
  materially larger roster/status disagreement.

Fantasy v1 therefore starts in 2020. The pipeline must reconcile and explain
every remaining stat/roster exception rather than treating the small counts as
automatically valid. The team model retains its existing historical window.

### 5.4 Identity and availability rules

GSIS ID is authoritative for roster and player-stat joins.
PFR IDs may join snap counts only through an audited one-to-one mapping. Display
name joins are prohibited. Ambiguous, duplicate, or missing identities block the
affected run.

`status == ACT` establishes only active-roster eligibility. It is prohibited as
evidence that a player is game-day active or healthy. `INA`, `PUP`, `RES`, `SUS`,
`DEV`, and every other non-`ACT` roster status are outside the v1 population.
Missing status, a missing GSIS ID, conflicting team membership, or a duplicated
player-week identity blocks the affected run.

No same-week injury, practice, game-status, inactive, depth-chart, or
participation value enters fantasy v1. A future availability overlay must be a
separately versioned candidate with its own licensed source, historical
decision-time evidence, ablation, validation receipt, and approval.

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
2. **Strong simple baseline:** the player's eight most recent eligible games,
   exponentially weighted with a four-game half-life and shrunk toward the
   time-safe position mean with four pseudo-games. For newest-to-oldest prior
   outcomes, weight game `i` by `2 ** (-i / 4)`. Predict
   `(weighted_player_sum + 4 * position_mean) / (weight_sum + 4)`. A player with
   no prior eligible game receives the position mean.
3. **First candidate:** a small regularized direct half-PPR model using only
   time-safe prior information.

The first candidate may use:

- shifted prior fantasy points over declared short and medium windows;
- shifted offensive snaps and snap share;
- shifted attempts, carries, targets, receptions, and opportunity shares;
- position, experience, draft capital, and cold-start indicators available by
  `T`;
- time-safe team and opponent context;
- weekly `ACT` roster eligibility, used for population construction only.

The following are prohibited:

- current-game snaps, attempts, carries, targets, receptions, yards, scores, or
  participation derived from the final box score;
- full-season or end-of-season aggregates joined backward into earlier weeks;
- post-kickoff injury revisions or corrected records without an as-of vintage;
- same-week injury, practice, game-status, inactive, depth-chart, or
  participation fields, even when they appear in the frozen files;
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

Before 2026 Week 1, freeze the model artifact, feature manifest, scoring rules,
and evaluation charter. At each kickoff window, lock predictions at T-90 before
any outcome is known. The 2026 outcomes are not available for tuning.

All transforms and parameters are fitted inside each training fold. Player rows
from the same game stay in the same fold. Candidates and baselines use identical
eligible rows. Missing predictions count as failures rather than disappearing
from the comparison.

Within a test season, every player-game in a season-week is predicted from
outcomes in strictly earlier weeks. Results from an earlier kickoff in the same
week cannot update player history or the time-safe position mean for a later
kickoff. The pipeline predicts the complete week first and updates all state
only after every row in that week has been scored.

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

Secondary diagnostics include all-roster-eligible-player MAE, position MAE,
RMSE, signed bias, rank correlation, cold-start performance, zero-outcome
slices, and the largest misses. These diagnostics cannot replace the locked
primary metric.

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
- trace roster, player-stat, snap, opponent, and team-context join cardinality;
- prove training precedes testing and preprocessing is fold-local;
- run automated target-alias, duplicate, and suspicious-correlation checks;
- manually resolve every automated review item.

Automated heuristics cannot issue `CLEAN`. An unresolved audit is
`REVIEW REQUIRED` and blocks predictive promotion.

The paired improvement interval resamples season-week blocks so players and
games sharing the same weekly environment move together. Report every fold and
position slice; do not hide an unfavorable season.

## 10. Outputs and execution

The full v1 implementation is one fantasy module plus focused tests, reusing
existing helpers where their contracts match. It eventually supports four
explicit operations:

1. freeze and validate fantasy sources;
2. build and audit the time-safe player-game table;
3. backtest baselines and, only later, the fixed candidate;
4. create or grade immutable prospective predictions.

Implementation is rung-by-rung. The first authorized code slice stops after
scoring, population construction, chronological feature state, the null
baseline, the locked strong simple baseline, and their fold report. It does not
fit the regularized candidate, capture canonical source bytes, create a 2026
lock, or change the website. Candidate implementation begins only after the
baseline slice passes its structural, identity, chronology, and leakage tests.

Each prospective prediction row records:

- game ID, GSIS ID, displayed player name, team, opponent, and position;
- scheduled kickoff and exact decision timestamp;
- roster status `ACT` and `availability_status = UNVERIFIED`;
- half-PPR projection;
- position, FLEX, and Superflex rank when eligible;
- source-lock, model-artifact, and prediction-integrity hashes.

The model artifact, feature manifest, validation contract, and scoring rules are
frozen before 2026 Week 1. Player predictions are then schedule-driven and
locked append-only at each kickoff window's T-90 boundary. Every run requires
complete `ACT` roster coverage for both teams, uses no overwrite semantics, and
records the exact frozen roster snapshot. Existing output paths cause a stop. A
failed write leaves no accepted partial package.

These locks provide prospective model evidence; they do not prove that every
listed player will dress. Grading treats a locked eligible player with no
player-stat row as zero fantasy points after identity and game-result coverage
pass.

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

After structurally valid 2026 fantasy locks exist, an explicitly experimental
fantasy research board may be proposed separately. Until a validated
availability layer exists, it must say that game-day availability is unverified
and cannot be presented as a complete start/sit product. It must also show
source and update time, model status, scoring format, and
methodology/accountability links. Merchandise remains after the fantasy
analysis.

## 12. Verification and stop conditions

Implementation is not complete until focused and full repository tests pass,
protected artifacts have identical hashes, all generated values are finite,
source and prediction receipts bind exact bytes, and a manual code/leakage
review finds no unresolved issue.

Stop rather than infer when:

- weekly `ACT` roster coverage is incomplete or ambiguous;
- a source hash differs from the accepted lock;
- a required historical source cannot be preserved reproducibly;
- a player lacks a stable identity;
- a feature's availability at `T` cannot be proved;
- any same-week injury, practice, game-status, inactive, depth-chart, or
  participation value enters fantasy v1;
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
- Current-week injury or game-day availability adjustment in fantasy v1
- A website redesign or store change

The next step after review of this specification is a test-driven implementation
plan. No implementation begins from this design document alone.
