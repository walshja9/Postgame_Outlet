# Confirmed non-QB absence burden: frozen research definition

Declared September 13, 2026, before implementation, fitting or candidate scoring.
Protocol cohort cutoff: `2026-09-13T05:20:00Z` (features are not outcome-selected).
Baseline checkout: `70c54db3de2e4b31dfb4c3b498a7eb0250a84ebb`.
Status: **RESEARCH ONLY / SOURCE ADMISSION BLOCKED**. This is a new experiment;
the September 12 charters, previous diagnostics and issued forecasts are unchanged.

## Question and decision time

Does adding two measures of confirmed injury-related absences to the exact issued
PGO home-margin forecast improve future margin accuracy? One row is one NFL
regular-season game. Target is final home score minus away score, including
overtime. T is scheduled kickoff minus 60 minutes. Every feature, source version,
identity witness and selected cohort must have durable evidence strictly before T.
Final scores and subsequent participation are target-only observations.

This first implementation defines and checks the arithmetic. It does not admit
source data, fit coefficients, change ratings or connect a new forecast model.
Normal weekly ranking updates and original game locking/grading continue.

## Fixed feature definition

For each canonical GSIS player, use the provider's directly reported unit snap
fraction (`offense_pct` or `defense_pct`, normalized to [0, 1]). Prior usage is the
median of the last one to four observed regular-season games in the current or
immediately preceding season, strictly before T. Select by actual kickoff, with
game ID as a deterministic secondary key; duplicate player/game rows are invalid.
History follows GSIS across team changes. An explicit zero is an observation and
stays in the median. No history is unknown, including rookies. Malformed or late
selected observations must block the calculation, not trigger an older fallback.
Each selected row requires aware clocks with
`kickoff < final_observed_at <= source_captured_at < T`.
Season, game type, game identity and unit must be normalized before calculation.
This arithmetic check does not establish original source publication/custody.

Sum prior usage separately for offense (RB, FB, WR, TE, OL and its named positions)
and defense (DL/DE/DT/NT/EDGE, LB/ILB/OLB/MLB, DB/CB/S/FS/SS). Exclude QB, K, P
and LS. Include only a confirmed OUT or INACTIVE designation with a documented
injury reason in the selected official evidence. An explicitly non-injury scratch
is excluded. An OUT/INACTIVE with unknown reason has unknown injury membership
and blocks the complete unit total. Questionable, doubtful and practice absence
do not count as confirmed absence. Roster RES/INA/DEV alone is not injury evidence.
An unavailable player's reserve membership must not count them twice.

The report must be admitted as complete for that team and decision time. Missing
report coverage, unresolved identity or prior usage for a qualifying absence, or
unknown injury membership produces an unknown total. Preserve the known subtotal
and reasons separately. Complete evidence with no confirmed injury absences gives
zero *confirmed-absence burden*, not proof of full health. Do not divide by roster
size: two absent players each with 0.8 prior usage produce 1.6. This is a sum of
prior participation shares, not a percentage of the lineup, player talent,
replacement quality, lost future snaps or NFL scoreboard points.

For home H and away A:

```
x_off = burden(A, offense) - burden(H, offense)
x_def = burden(A, defense) - burden(H, defense)
candidate_home_margin = issued_PGO_home_margin + beta_off*x_off + beta_def*x_def
```

Both coefficients are constrained nonnegative, with no intercept, imputation,
interactions, position weights or guessed questionable probabilities. A missing
unit total makes the candidate unavailable for that game. Coefficients are not
defined or fitted in this implementation. No win-probability, total-score,
confidence-pool or rankings conversion is implied by this margin-only experiment.

## Source admission before any numerical dataset

Replay the existing versioned offensive and defensive inventory loaders. Choose
the latest durable eligible pre-T inventory solely by saved clocks and game ID;
freeze the selection and never substitute a convenient older version. Verify raw
hashes, identity joins, complete official reports, source-version evidence,
24-hour inventory freshness and prior usage history. Joining future observed
snaps validates participation linkage; it does not establish an injury point cost.
Do not confuse current source capture with historical pregame publication.

Existing legacy prior-role summaries are not this feature: they omit zero-snap
games and use a team maximum-player snap denominator. Existing defensive
`confirmed_unavailable` includes reserve roster context. Neither is a valid
shortcut. Annual injury files and the newly found 2024 injurybot subset remain
unadmitted until their separate timing, identity and completeness gaps are closed.

## Locked prospective comparison and endpoint

Development cohort: admitted 2026 regular-season games with T after this protocol
freeze. The two already completed opening games are excluded. Before fitting,
require at least 200 distinct common games, 12 weeks, all 32 teams, at least 50
nonzero observations for each unit difference and a rank-two feature matrix.
Use training data only for fitting; minimize squared residual error relative to
each game's exact issued baseline under the two nonnegative coefficient constraints.
No hyperparameter search or selecting among formulas using evaluation outcomes.

Fit once after the final 2026 regular-season game and freeze the candidate, code,
coefficients and input manifest strictly before T-60 of the first eligible 2027
regular-season game.
If admission or sample rules fail, status is INSUFFICIENT and no candidate is fit.
An exploratory historical comparison requires a separately declared diagnostic
protocol; the already inspected 2018-2025 seasons cannot supply untouched evidence.

Untouched evaluation: eligible 2027 regular-season games, scored once after its
final regular-season game, requiring at least 200 common games, 12 weeks and all
32 teams. Evaluate paired candidate/baseline predictions on identical games.
Primary metric is margin MAE; report RMSE, counts/exclusions, Week 1, Weeks 1-4,
later weeks and every week/season represented. No outcome-based inclusion.
For a practical screening pass require at least 0.15 points lower MAE, a positive
lower endpoint of a paired week-block 95% percentile bootstrap interval for MAE
improvement (10,000 resamples; fixed seed 20260913), overall RMSE no worse, and
Weeks 1-4 MAE degradation no more than 0.25 points with at least 40 early games.
These are declared practical screens, not a statistical power guarantee.
Week 1 remains descriptive because its sample is small. Report excluded-game
baseline accuracy separately to expose coverage bias. Insufficient coverage is
INSUFFICIENT, never a passing result or permission to move the endpoint.

Retain each issued baseline's edition, recipe/code hash and input hashes. Routine
weekly data updates are permitted under the same implementation. A numerical
baseline recipe change requires a newly declared cohort/version; do not rewrite
earlier forecasts or pool incompatible recipes. The historical saved challenger
contains old availability terms and is not interchangeable with today's live
path, which sets those terms to zero. No comparison here silently uses that path.

The current collection engine is scoped to 2026. Extending collection to 2027,
admitting sources and implementing a frozen candidate scorer are explicit gates
before the evaluation can run; this document does not claim they already exist.
Passing the screen supports independent model review and continued shadow testing,
not automatic public adoption. New England's rank is not a success criterion.

## Small executable contract

`features.py` will expose pure functions over already normalized records:

- `prior_share(rows, player_id=..., unit=..., season=..., lock_at=...)`: rows have
  `gsis_id`, `game_id`, `season`, `game_type`, `unit`, `kickoff`,
  `final_observed_at`, `source_captured_at`, `share`. Return median (or null), count,
  selected game IDs and status. Reject malformed selected observations.
- `unit_burden(players, unit=..., report_complete=...)`: player rows have
  `gsis_id`, `position`, `status`, `injury_documented` (true/false/null),
  `prior_usage` (fraction/null). Return full total (or null), known subtotal,
  qualifying count and explicit missingness. Duplicate eligible identities fail.
  Status must be an explicit recognized normalized label; absent or malformed
  labels fail instead of becoming a known zero. Legitimate no-designation rows
  must be normalized explicitly. Unknown-position confirmed injury absences block
  both units until unit membership is resolved.
- `margin_inputs(home, away)`: mappings of offense/defense totals, returning the
  two away-minus-home differences or null when a required total is unknown.

The runnable checks cover clocks, invalid fractions, explicit zeros, duplicates,
cross-team identity, missing report/identity/history, non-injury and unknown-reason
scratches, reserve-only context, unit exclusions and margin signs. They verify
implementation correctness only, not predictive benefit or source qualification.
