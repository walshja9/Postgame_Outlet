# Independent Forward-Looking PGO Model Design

**Status:** Approved design; written specification awaiting final review
**Date:** July 21, 2026
**Product:** Postgame Outlet
**Model:** Independent, forward-looking NFL team Power Rating challenger

## 1. Decision

Postgame Outlet will develop a new shadow-only challenger to the existing PGO
team-results model. The challenger will remain completely independent from Sean
McCabe's ratings while adding objective, forward-looking information about
quarterbacks, roster continuity, injuries, coaching changes, and team
performance.

The model will produce one neutral-field team-strength rating in points, plus
the two values needed to explain it:

```text
full-strength rating + availability adjustment = current-lineup rating
```

The preseason headline is the hypothetical full-strength rating. During the
season, the headline is the current-lineup rating. Both values and the
availability adjustment remain available so the meaning never changes
silently.

This design supersedes the earlier restriction that the PGO model consume only
completed game identity and scores. It does not change the product boundary:
McCabe's human ratings and the PGO statistical model remain separate products
that may be compared but are not blended.

## 2. Goals

1. Estimate each NFL team's strength with its best expected roster healthy.
2. Adjust that estimate for the lineup expected to be available for a specific
   rating snapshot or game.
3. Distinguish temporary absences from lasting player or team improvement and
   decline.
4. Explain rating movement through performance, roster/coaching, and
   availability contributions.
5. Improve unseen-game margin prediction relative to the existing PGO v0 model.
6. Preserve chronological reproducibility, source provenance, and permanent
   validation receipts.
7. Keep the first implementation small enough to audit and finish.

## 3. Non-goals

- Reading, reproducing, or training on McCabe ratings
- Using betting markets as model inputs
- Scraping or training on PFF data from a personal subscription
- Assigning manual player, coach, or scheme grades
- Producing public ratings, articles, predictions, or betting recommendations
- Replacing the existing PGO v0 model before the challenger passes its gates
- Building a real-time service, database, dashboard, or automated publishing job
- Modeling subjective scheme taxonomies in the first version
- Claiming precise individual value where the available evidence is weak
- Refactoring unrelated ratings, generator, Shopify, or GitHub Pages code

## 4. Rating contract

### 4.1 Units and centering

Every rating is denominated in expected points versus a league-average team on
a neutral field. The 32 full-strength ratings are centered around league
average for each snapshot. Current-lineup ratings retain that same zero point
rather than being recentered independently, so the availability adjustment
remains an actual point difference and the rating identity remains exact.

Game context such as home field, rest, and travel may be used when evaluating
game predictions. It is set to neutral when deriving team ratings.

### 4.2 Full-strength rating

The full-strength view scores the best expected roster represented by the
snapshot as healthy and playing its normal role. It includes rostered players
who are temporarily injured or suspended, because it describes roster talent
rather than immediate eligibility. Released, retired, unsigned, or otherwise
departed players are excluded.

This number is a model-based counterfactual, not an observed historical label.
It is produced by the same conditional game model as the current-lineup value;
no separate full-strength model is trained.

### 4.3 Current-lineup rating

The current-lineup view uses the lineup expected to be available at the
snapshot timestamp. Confirmed active and inactive players receive probabilities
of one and zero. Uncertain players receive objectively estimated participation
and snap-share probabilities based on information available at that time.

Replacement quality is part of the calculation. Losing a starter to a capable
backup must have a smaller effect than losing the same starter to a replacement
with materially weaker evidence.

### 4.4 Availability adjustment

The availability adjustment is the current-lineup rating minus the
full-strength rating. It changes immediately when expected availability or
expected workload changes. It is removed when the player returns. It does not
rewrite the player's underlying full-strength estimate.

### 4.5 Movement receipts

Every rating change is attributable to exactly three reader-facing groups:

1. On-field performance
2. Roster or coaching change
3. Availability change

The model may use more detailed internal features, but the future reader-facing
explanation does not expose a misleading level of component precision.

## 5. Source hierarchy

### 5.1 Required reproducible foundation

The first challenger uses pinned, hash-verified historical files from the
nflverse ecosystem wherever coverage is adequate. The source audit may use:

- Schedules and completed regular-season results
- Play-by-play
- Weekly and seasonal rosters
- Stable player identifiers
- Weekly player statistics
- Snap counts and participation
- Injury reports
- Depth charts
- Draft and transaction information
- Publicly redistributed aggregate quarterback or Next Gen Stats fields when
  their provenance and license permit the intended use

Files are read directly from pinned releases when practical. Installing a data
client package is unnecessary when a stable file URL provides the same data.

Every admitted source records its location, version or commit, content hash,
coverage window, as-of behavior, and applicable license or attribution.

### 5.2 Optional external sources

ESPN, TeamRankings, FTN/DVOA, and public aggregate Next Gen Stats are optional
challenger inputs or benchmarks. A source is not admitted merely because it is
well known or correlated with winning. It must satisfy the feature-admission
rules below and add out-of-sample value beyond existing inputs.

### 5.3 PFF boundary

A personal PFF account is not a model data source. PFF data enters a future
model version only after Postgame Outlet obtains permission or a license that
explicitly permits the intended automated collection, storage, model training,
and publication. Credentials and paid-source exports never enter the repository.

### 5.4 Feature-admission rules

A source or feature enters a candidate model only when it:

1. Existed before the kickoff being predicted.
2. Has enough historical coverage for chronological evaluation.
3. Has stable team and player identity coverage.
4. Can be legally stored, processed, and attributed for the intended use.
5. Can be reproduced from an immutable snapshot.
6. Has an explicit missing-value policy learned and tested during development.
7. Improves chronological validation beyond correlated features already present.

The source audit chooses the earliest common modeling season based only on
coverage and quality, not on prediction outcomes. That date is frozen before
the final historical evaluation.

## 6. Observation grain and leakage controls

The training grain is one completed regular-season game. Each row contains a
home-minus-away feature vector and the observed home scoring margin.

Every feature has an `as_of` boundary at the scheduled kickoff. A row may use
only information that would have been available then. In particular:

- Season-to-date metrics are shifted so the current game is excluded.
- End-of-season aggregates cannot predict games from the same season.
- Injury and lineup inputs use the status known at the historical snapshot time.
- Transactions, coaching changes, and depth-chart changes apply only after their
  effective dates.
- Opponent adjustments are calculated only from games already completed.
- Feature normalization and imputation parameters are learned inside each
  training fold, never on the full dataset.

Postseason games remain excluded in the first challenger so its population
matches PGO v0. Neutral-site games remain included with zero home-field value.

## 7. Initial feature scope

### 7.1 Existing team-results state

The pregame PGO v0 rating is both the incumbent benchmark and one candidate
feature. It is generated chronologically without future information.

### 7.2 Team performance

The first candidate set contains a small number of lagged, opponent-adjusted
signals:

- Passing EPA per play and success rate, for and against
- Rushing EPA per play and success rate, for and against
- Explosive-play rate, for and against
- Sack and turnover rates, for and against
- Special-teams efficiency when reproducible coverage permits

Recent observations receive greater weight than older observations. Candidate
decay rates are selected only inside chronological development folds. Highly
correlated versions of the same concept are not all retained.

### 7.3 Quarterback

Quarterback features include:

- Expected starter and replacement
- Career and recent EPA per dropback
- Completion percentage over expected when reproducibly available
- Sack, interception, and fumble rates
- Rushing contribution
- Experience, dropback sample size, and time since last meaningful play
- Expected participation and expected snap share

Small samples receive stronger shrinkage toward the relevant population mean.
The model learns quarterback effects from objective data; it does not import
McCabe's quarterback values.

### 7.4 Roster

Roster features include:

- Returning snap share by position group
- Player additions, departures, and stable cross-team identities
- Draft capital and expected role
- Prior objective production where attribution is credible
- Position group continuity
- Replacement experience and prior workload

The first version does not force a precise standalone value for every
non-quarterback. Evidence that cannot reliably separate a player from teammates
and scheme is aggregated to the position-group or unit level and shrunk toward
average.

### 7.5 Coaching and scheme continuity

The initial coaching features are head coach, offensive coordinator, and
defensive coordinator identity; change versus continuity; and tenure with the
current roster. Regularization shrinks new or lightly sampled staff effects
toward neutral.

The first version does not assign subjective scheme labels. Coordinator change
and continuity are the reproducible initial proxies for scheme change.

### 7.6 Game context

Home field, neutral site, rest, and travel may enter the game-margin predictor.
These values are neutralized when producing team ratings. Weather and market
information are excluded from the first version.

## 8. Model form

The first challenger is an explainable regularized linear model with a robust
loss. Regularization strength, recency decay, and other finite hyperparameters
are selected only inside chronological development folds.

Regularization provides partial pooling for correlated inputs and lightly
sampled player, quarterback, and coaching effects. Feature contribution groups
support the movement receipt without claiming that correlated predictors have
one uniquely correct causal decomposition.

A nonlinear model may be evaluated later as a separate challenger. It does not
replace the linear challenger unless it passes the same data, reproducibility,
explainability, and validation requirements by a meaningful margin.

## 9. Training and evaluation

### 9.1 Historical development

Historical evaluation uses rolling-origin splits over the common high-quality
feature window. Each fold trains only on earlier games and predicts a later
block. All feature selection and hyperparameter selection occur inside the
development process.

PGO v0 produces predictions for the identical games. A home-field-only model
remains a diagnostic baseline, but beating it is insufficient; the challenger
must beat PGO v0.

### 9.2 Primary and secondary metrics

The primary metric is mean absolute error of predicted scoring margin.
Secondary diagnostics are:

- Median absolute error
- Root mean squared error
- Frequency of misses greater than 14 and 21 points
- Mean signed error overall and by home/away side
- Year-by-year performance
- Calibration across predicted-margin bands

McCabe rating correlation and rank correlation are descriptive comparisons.
They are never model objectives or release gates.

### 9.3 Required subgroup checks

The evaluation reports paired challenger-versus-v0 results for:

- Backup or changed starting quarterback
- Major expected availability loss
- Head coach or coordinator change
- High roster turnover
- Weeks 1 through 4
- Remaining regular-season weeks

Subgroup definitions are frozen before final evaluation. A major availability
loss means a modeled availability adjustment of -1.5 points or lower. High
roster turnover means a team's returning snap share is in the bottom quartile
for that season. A subgroup requires at least 100 evaluation games; a smaller
group is labeled insufficient evidence rather than pass or fail.

### 9.4 Historical gate

The challenger earns historical `PASS` only when:

1. Required source, identity, leakage, coverage, and reproducibility checks pass.
2. All 32 current teams receive both rating views.
3. Challenger MAE is lower than PGO v0 MAE on identical evaluation games.
4. A paired week-block bootstrap 95% confidence interval for the MAE improvement
   lies entirely above zero.
5. No required subgroup with sufficient evidence has a paired 95% confidence
   interval for the MAE improvement lying entirely below zero.

For every gate, MAE improvement means `PGO v0 MAE - challenger MAE`; positive is
better. The paired bootstrap resamples season-week blocks while preserving the
v0 and challenger errors for the same games.

Any failed condition produces `HOLD`. A hold writes the diagnostic backtest
receipt but removes or declines to write the current ratings artifact.

### 9.5 Prospective gate

The previously examined 2018-2025 seasons are not described as a pristine
holdout for this new design. They support rolling historical validation.

The 2026 regular season is the first genuine prospective shadow evaluation.
Predictions and assumed lineups are locked before kickoff and graded afterward.
Historical `PASS` permits shadow ratings and prospective tracking only; it does
not authorize public integration. Public use requires a separate decision after
the prospective evidence is reviewed.

## 10. Snapshot and update behavior

The first implementation runs on demand rather than as an automated service.
Every run has an explicit as-of timestamp and produces deterministic output for
the same source snapshots.

An offseason snapshot headlines full strength. An in-season snapshot headlines
current lineup while retaining full strength and availability adjustment. When
final active/inactive information is available, it replaces earlier
probability-weighted availability in a newly timestamped snapshot; it never
rewrites an already locked pregame receipt.

Weekly automation, live injury polling, and last-minute publication are deferred
until the shadow workflow is reliable enough to justify them.

## 11. Outputs and accountability

The shadow workflow writes only versioned research artifacts under a new
research directory. The minimum artifacts are:

- `backtest.json`: model version, source hashes, coverage, feature manifest,
  parameters, metrics, subgroup results, confidence intervals, checks, and
  `PASS` or `HOLD`
- `validation_predictions.csv`: game identifier, kickoff, actual margin, PGO v0
  prediction, challenger prediction, and frozen subgroup flags
- `ratings_<snapshot>.csv`: rank, team, full-strength rating, availability
  adjustment, current-lineup rating, headline view, and as-of timestamp; written
  only after historical `PASS`

The implementation plan chooses the exact versioned directory and model name.
Artifacts never overwrite the existing `research/pgo/` v0 receipts.

## 12. Data-quality and failure behavior

The run fails closed when:

- A required source is missing, stale, hash-mismatched, or outside its declared
  coverage window.
- Team or player identity joins fall below the predeclared coverage requirement.
- A pregame feature contains post-kickoff information.
- A required feature has unhandled missingness or an out-of-range value.
- A source changes schema without an explicit compatible parser update.
- Fewer than 32 current teams receive a valid rating.
- Repeating the same run does not produce identical artifacts.
- The historical gate returns `HOLD`.

Missing values never become zero implicitly. A model may use an imputed value and
missingness indicator only when that behavior was learned and validated during
training. A model version that requires a paid or optional source does not
silently fall back to a different feature set; the reproducible core model is a
separate version.

## 13. Testing requirements

The implementation plan must include focused checks for:

- Pregame feature shifting and explicit look-ahead leakage traps
- Team relocation aliases and stable player identity joins
- Full-strength/current-lineup algebra
- Active, inactive, uncertain, and limited-snap availability
- Replacement-player effects
- Offseason roster and coaching transitions
- Training-fold-only normalization, imputation, and hyperparameter selection
- Chronological split isolation
- Paired metric and confidence-interval calculations
- Required-source and schema failures
- `HOLD` removal of stale ratings
- Deterministic repeated output
- Production-isolation diff

One small synthetic end-to-end fixture is sufficient for pipeline behavior.
Historical source data is used for the full reproducibility and gate run. The
repository's existing `unittest` workflow remains the test runner.

## 14. Implementation and production boundaries

All subsequent work remains on a `codex/` branch in an isolated worktree. The
first implementation extends or reuses existing PGO source validation, aliases,
chronological handling, atomic writes, and receipt conventions instead of
rewriting them.

The implementation must not modify or publish:

- `data/ratings.csv`
- McCabe rating calculations or writeups
- `generate_site.py` production behavior
- Generated production ratings pages
- Shopify theme or content
- GitHub Pages output or deployment workflows
- Redirects, analytics, or live services

No push, merge, publish, deploy, automation enablement, or production integration
occurs without separate explicit authorization.

## 15. Acceptance criteria

The design is implemented successfully only when:

- The model remains independent from McCabe and market inputs.
- All required sources have recorded provenance, coverage, hashes, and permitted
  use.
- Historical feature rows are reproducibly constrained to pre-kickoff data.
- Full-strength and current-lineup ratings come from the same conditional model.
- Availability changes do not permanently rewrite underlying player strength.
- Rating receipts explain performance, roster/coaching, and availability movement.
- The historical gate compares the challenger with PGO v0 on identical games.
- All gate calculations and confidence intervals are reproducible.
- `HOLD` cannot leave a stale challenger ratings artifact.
- The current PGO v0 receipts and every production surface remain unchanged.
- The 2026 prospective predictions can be locked and graded without rewriting
  their original inputs.

## 16. Source references

- nflverse play-by-play repository and data-release guidance:
  <https://github.com/nflverse/nflverse-pbp>
- nflverse Python data-access and dataset coverage documentation:
  <https://github.com/nflverse/nfl_data_py>
- NFL Football Operations description of Next Gen Stats:
  <https://operations.nfl.com/gameday/technology/nfl-next-gen-stats>
- FTN historical DVOA description:
  <https://ftnfantasy.com/learn-more-about-dvoa>
- PFF terms governing subscription data, automated extraction, and machine
  learning use: <https://www.pff.com/terms>

These references document current availability and constraints. The
implementation source audit must record the terms and dataset versions actually
in force when a source is admitted.

## 17. Authorization boundary

This specification authorizes implementation planning only. It does not
authorize model implementation, data acquisition requiring new terms, use of
Sean's PFF credentials, production integration, publishing, deployment, or any
change to a live service.
