# Fixed updating score-total experiment — September 10, 2026

Declared before construction/evaluation. Owner: Postgame Outlet / Alex. All outputs are **EXPERIMENTAL / HOLD**. This is a new diagnostic attempt, never a revision of a prior experiment or an issued forecast.

Question: do fixed current-season scoring updates improve NFL regular-season total-point estimates over the existing prior-season PF/PA rule? One row is one game; target is final home plus away points, including overtime and tied games. Prospective decision time is kickoff minus 60 minutes. No margin, probability, confidence allocation or player-quality change is included.

Source and population: reuse the schedule bytes pinned by the September 9 postseason run (manifest `a58aeff835471182a555e4b926beafd0db01c7c5e3fe19827ddf56bd03f2514a`). Verify its complete member inventory and use its 2,127 saved 2018–2025 REG game IDs exactly: 256, 256, 256, 272, 271, 272, 272, 272 by season. Read 2013–2025 completed REG/WC/DIV/CON/SB games for prior histories, expected 3,562 games. Incomplete scores remain missing; an evaluation game without its required score or prior team history stops the attempt rather than dropping the game. Exact normalized team/game/season/week identities must agree. Scores are finite nonnegative integers; duplicate games and duplicate team/game-day appearances fail.

Four formulas, fixed now, with no coefficient fitting, tuning or alternative search:

1. `league_prior`: mean total points across the immediately preceding season's REG and postseason games.
2. `pfpa_prior`: each team's preceding-season REG+POST PF and PA per game; predict half the sum of both teams' PF and PA. This matches the current model's fixed 2025 REG+POST scoring method, rolled forward identically for each evaluation season.
3. `shrink_4`: for each team's PF and PA, use `(4 * prior-season rate + current-season points)/(4 + current-season games)`; combine rates with the same sum/2 rule.
4. `shrink_8`: exactly the same formula with eight pseudo-games.

Chronology: process Eastern scheduled game days in order. Every forecast for a date is formed before updating any game from that date; same-day outcomes are excluded even if another game began earlier. Current-season history starts empty each season; playoffs update the immediately preceding-season prior, not an extra rematch weight. Store prior/current counts and as-of history dates per row. Prior season must end before the forecast day. Historical final/publication timestamps are unavailable: this date embargo is a reproducible proxy, not proof of a historical T-60 feed. Overall leakage/source-vintage verdict stays **REVIEW REQUIRED**. Future/current-day outcome perturbations must leave preceding predictions unchanged.

Validation: fixed-formula rolling-origin prediction within each of eight 2018–2025 evaluation seasons, using only earlier dates; no random split or fitted preprocessing. These seasons have already been inspected in other research and are diagnostic, not a fresh holdout. No selection or promotion follows the best retrospective score.

Primary metric: identical-game mean absolute total error (MAE), lower is better. Also report RMSE and bias (predicted minus actual), Week 1, Weeks 1–4, Weeks 5–18, every season and per-season sample count. Retain all arms and all difficult games.

Uncertainty: paired 10,000 bootstrap draws, seed 20260910, resampling complete seasons as the primary cluster; resampling complete `(season, week)` clusters is a sensitivity analysis and cannot override season evidence. Each draw retains all games and both predictions in each selected cluster and weights by its resulting game count. Report 95% intervals for baseline MAE minus candidate MAE against both baselines. For the two predeclared candidate arms also report 97.5% season-cluster intervals (Bonferroni protection across the two arm decisions). Eight seasons provide limited independent information; week clustering does not eliminate repeated-team dependence across weeks.

Further-study screen per arm: at least 0.10 points lower pooled MAE than **each** baseline, lower MAE in at least five of eight seasons against **each** baseline, and the lower 97.5% season-cluster improvement bound above zero against **each** baseline. This is a diagnostic screen, never scientific acceptance. Week 1 is expected to equal the PF/PA prior before a team's first game; that is not a failure or a reason to change the formulas.

One exclusive `attempt01` execution after focused tests. No retries for unfavorable metrics; construction failures are preserved and any repair needs a distinct attempt with its reason. Save charter/code/source hashes before and after, pinned cohort reconciliation, all predictions and per-row source counts, metrics/intervals, leakage checks, a small public summary, and an immutable manifest. Prior experimental packages and issued static evidence must remain unchanged.

Prospective recipe: freeze and retain both formulas, capture identical-input totals plus both controls before real T-60, and grade only verified finals. Live source completion time must precede issuance; histories may use only verified prior-day finals and no missing outcome imputation. Store history witnesses, source hashes and fixed pseudo-game count with every pair; never replace issued pairs. Do not wire this into production in this task. A separately approved prospective series can begin only on still-eligible games; formal review after the 2026 regular season requires at least 150 common pairs across 12 weeks. Otherwise report insufficient evidence. Descriptive monitoring is not refitting or repeated acceptance testing.

Out of scope: changing current scores, ranks, winners, probabilities, penalty weights, injuries, EDGE/LB grades, wagering recommendations or profitability claims. Existing penalty, defensive and non-QB runs remain frozen.
