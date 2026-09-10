# PGO six improvements and ATS release - September 10, 2026

Published source: `f24d0340aa23a6bf92c8e1ef28f815cc5672ab02`. Final tested board render: `a90998934bee77534372b5a1fc4354a250579a05`. Latest verified scheduled state: `2026-09-10T21:41:23.934778+00:00`, published by `e0b265286737165c252a9c4b543c6ee351520301`.

Live: https://postgameoutlet.com/pages/power-ratings (PGO Model tab). Direct spread view: https://walshja9.github.io/Postgame_Outlet/index.html#season-ats.

## Delivered

- Full board tests run outside the shared publisher lock. The publisher admits newer operational data only after verifying the tested source. Ranking, availability, result and automation clocks are distinct.
- Eastern-date game cards show the winner pick, win chance, kickoff, lock, availability context and saved sportsbook line. Existing controls survive in-place refresh.
- Accuracy includes straight-up records, margin/total error, probability diagnostics and clearly named expected/earned pool points. Comparisons use identical eligible games; late probabilities remain excluded from pregame probability evidence.
- Four fixed totals rules now have frozen historical results and prospective comparisons.
- Replacement-depth observations preserve player identities, prior experience and missingness; numerical injury fitting remains blocked by absent historical depth dates and capture clocks.
- Three fixed margin models and six probability methods now have separate historical and prospective comparisons. Penalty monitoring continues under its existing fixed rules.

All original main forecasts, the complete opener, and 15 saved pairs in each penalty/totals/weights series were preserved. McCabe's incoming Raiders update and concurrent automated archives were retained. The main model remains EXPERIMENTAL / HOLD; no research candidate or new injury coefficient was adopted.

## Spread records

The original straight-up W/L/T record remains separate from three additional checks:

1. Winner pick versus PGO's projected line: Exceeded / Below / Matched.
2. Winner pick versus the saved sportsbook line: Covered / Not covered / Push.
3. Model ATS suggestion versus the saved sportsbook line: Covered / Not covered / Push.

Example: LAR winning by six exceeds PGO's approximately -4.3 projection and covers a saved LAR -3.5 sportsbook line. It earns one straight-up win, with independent comparison outcomes. Exceeding a projection is not a measure of closeness; margin error supplies that measure.

DraftKings provider 100 quotes come from the ESPN scoreboard captures already archived by PGO. Source hashes, event identity, signs and clocks are checked. Quotes and ATS selections may revise before T-60; older versions remain archived. The last eligible pre-lock record freezes, retaining stale reasons when necessary. No cover probability, confidence reallocation or profit estimate was added.

There are 15 eligible market comparisons. The completed opener has no saved pre-lock market quote, so its sportsbook results remain unavailable. Its authentic original margin is eligible for the separate PGO-line check, currently Below projection.

## Scientific limits

On 2,127 historical games, total error fell from 11.035389 to 10.742026 and 10.760222 for the fixed four/eight-game blends. Both passed the further-study screen; the main total rule remains unchanged. Removing QB passing or team passing worsened margin error. No probability alternative passed its improvement screen. Familiar historical seasons and unverified source vintages remain diagnostic evidence. Prospective comparisons cannot automatically promote a model. See the dated research READMEs and public model-update note for methods, full artifacts and review thresholds.

## Verification

- Full CI [34532200946](https://github.com/walshja9/Postgame_Outlet/actions/runs/34532200946): SUCCESS. 802 tests in 840.345 seconds, one optional skip; corrected and defensive research checks passed 14 tests each. Tested-source guard and both page renders passed.
- Controlled refresh [34532230152](https://github.com/walshja9/Postgame_Outlet/actions/runs/34532230152): SUCCESS, 145 tests. It published during the long full-test job, proving that those tests no longer hold the season writer lock.
- Actual scheduled refresh [34533456761](https://github.com/walshja9/Postgame_Outlet/actions/runs/34533456761): SUCCESS, 145 tests in 18.386 seconds. Independent audit verified 904 prior evidence files, unchanged forecasts/experimental rows and valid pre-lock quotes. All numeric monitors READY; replacement capture descriptive with historical fitting blocked.
- Pages [34534080303](https://github.com/walshja9/Postgame_Outlet/actions/runs/34534080303): SUCCESS at `a909989`.
- Initial public verification: 918 files matched exact release bytes. Actual Shopify iframe passed at 320px inside a 375px viewport without outer overflow. Desktop tables scroll inside their containers. Two real automated editions arrived without navigation reload or closing the open ATS details.

Exact logs, hashes, final public verification and screenshots are retained under `output/six-improvements-20260910/` and `output/playwright/`. These are local ignored receipts; scientific artifacts and public notes are committed separately. The final documentation-only commit does not change tested application code or predictions.

## Routine operation

The scheduled workflow runs approximately every 15 minutes, subject to GitHub queues and source availability. Availability and quote capture run before each game's one-hour lock. Verified finals grade saved selections; a completed week plus verified statistics advances rankings and the next slate using the established model. Previous weeks remain archived. Missing sources or conflicting results retain an explicit blocked/stale reason. Numerical injury work and model promotion require their documented evidence gates; routine monitoring does not rerun historical fits.
