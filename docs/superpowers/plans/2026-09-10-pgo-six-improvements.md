# PGO six improvements implementation plan

> **For agentic workers:** Use subagent-driven-development to implement and review each independent task.

**Goal:** Make the live site easier to use and audit while testing three focused model improvements.

**Architecture:** Extend the existing saved season state, pure renderer, scheduled workflows and chronological research tools. Preserve all issued forecasts and existing experimental evidence. Root integrates and publishes; workers own disjoint files.

**Tech stack:** Existing Python, NumPy, unittest, native HTML/CSS/JavaScript and GitHub Actions. No new dependencies.

## Global constraints

- User approved all six improvements and publication. Implementation proceeds without another approval loop.
- Never replace a locked pick, refit an accepted live model implicitly, or rewrite an earlier experiment.
- Model candidates remain separate. Write the dated evaluation charter before fitting; familiar historical seasons remain diagnostic.
- Unknown player role, availability, rookie history or replacement coverage must remain unknown rather than zero quality.
- Preserve named reading controls, input validation, mathematical reconciliation and mobile accessibility.

## 1. Reliable publishing and truthful freshness

Files: `.github/workflows/update-board.yml`, a small tested publication guard, workflow tests; root owns `pgo_season_view.py` and its tests.

- [x] Move full tests to a job outside the shared writer lock. Publish only after that job passes.
- [x] Acquire the existing `board-update` lock for publishing, check out latest main and permit changes since the tested commit only in mutable season evidence and generated pages. Refuse stale code; never rebase stale renders over fresh state.
- [x] Display ranking calculation/input capture separately from availability and results checks. Explain the completed-game history date without implying kickoff was data availability. First-edition rank movement must say so.
- [x] Test source drift versus operational drift and visible stale/missing clocks. Run the relevant unittest modules.

## 2. Game-day summary

Files: `pgo_season_view.py`, `docs/pgo-theme.css`, `tests/test_pgo_season_view.py`.

- [x] Render today's Eastern-date games above rankings, with pick, saved win probability, kickoff, lock and important availability context; link to the existing detailed game row.
- [x] Keep final, withheld and late-probability cases explicit. Empty days get a useful next-game message. Do not manufacture absence names.
- [x] Test matching the Eastern date, escaping, no duplicate keys, retained detailed controls and no mutation of state. Inspect the real mobile iframe.

## 3. Season accuracy

Files: new `pgo_season_accuracy.py`, tests; root integrates its pure output in the season view.

- [x] Compute metrics from original saved game forecasts and verified finals: record, margin/total absolute error, full-probability Brier/log loss, fixed confidence earned and expected.
- [x] Exclude late confidence from probability evidence. State each metric's eligible count and exclusion count; compare models only on identical eligible game IDs.
- [x] Include fixed reliability bins with counts and plain-language guidance against conclusions from small samples. Reuse probability definitions already in `pgo_confidence_picks.py`.
- [x] Test a hand-calculated mix of wins, losses, ties, late entries, missing forecasts and unequal model schedules.

## 4. Score-total experiment

Files: new dated research directory with charter, runner, small tests and immutable attempt output.

- [x] Audit reusable historical game scores and as-of chronology. Predeclare a small fixed set of prior/current-season shrinkage blends and chronological folds before execution.
- [x] Evaluate identical games against the fixed prior-season total rule and a league-mean baseline. Report total MAE overall, Week 1, early season and each season, with paired uncertainty.
- [x] Write reproducible artifacts and public findings, including limitations. Do not change production totals automatically.

## 5. Injury and replacement-depth experiment

Files: new dated research directory and bounded availability capture integration if qualified data exists.

- [x] Audit historical role timing, stable player identity and league-wide role coverage before fitting.
- [x] Implement an explicit admission report for unavailable-role exposure and remaining experienced replacement coverage; preserve unknowns and source timestamps.
- [x] If historical role vintages cannot support the proposed policy, record the failed admission, implement prospective capture of the required evidence and omit invented historical fitted weights.
- [x] Publish what is measured, missing and required for a valid fit. Earlier failed defensive/non-QB artifacts remain unchanged.

## 6. Focused weights and probabilities

Files: new dated research directory with charter, runner, small tests and immutable attempt output.

- [x] Predeclare a bounded overlapping-block ablation and probability comparison using the existing pinned historical rows. All scaling, fitting and calibration use training history only.
- [x] Compare fixed candidate definitions on common chronological games. Report margin MAE and probability log loss/Brier/reliability separately; distinguish probability curves with a fixed midpoint from learned-midpoint curves that can change the selected team.
- [x] Preserve every attempt, publish diagnostic results and prepare prospective candidate capture where scientifically admissible. Existing penalty weights/review rules stay fixed.

## Integration and publication

- [x] Review worker diffs and run focused tests, the required full test suite and research checks once on final integrated source.
- [x] Render both public pages against the newest verified saved state; publish through the existing branch-based Pages flow.
- [x] Verify deployed bytes, mobile rendering, stable reading state and a scheduled refresh. Record exact commits, tests and known limits in a new handoff; do not overwrite earlier release receipts.

## User-requested ATS extension

The user approved both the original winner pick's coverage and a separate ATS suggestion, then requested comparison with PGO's own projected line as well. These are descriptive forecast checks using the existing model, not a new fitted model.

- [x] Read signed home and away handicaps from the already captured ESPN scoreboard, bind the named DraftKings provider and exact event/team/kickoff identity, and retain raw source hash and capture time. No extra feed dependency. Missing or conflicting lines remain unavailable.
- [x] Display PGO's projected line as the negative of its home-margin estimate. Choose the ATS side from model home margin plus sportsbook home handicap. Zero edge means no ATS selection. Do not create a cover probability or reuse the straight-up win probability.
- [x] Refresh unlocked quote/selection records until T-60 and archive each revision in the existing season state. Freeze the last eligible pre-lock record; preserve prior records when sources fail, with stale status and original timestamps. Check the actual durable-write clock.
- [x] Track three distinct comparisons: ATS suggestion against the sportsbook line; original winner pick against the sportsbook line; original winner pick against PGO's projected line. Keep original straight-up W/L and margin error separate. Pushes and unavailable records do not become wins or losses.
- [x] A completed game without a saved pre-lock sportsbook quote remains unavailable for sportsbook ATS. Its original authentic pre-lock margin can still receive a PGO-line comparison. Grade using saved full precision, with rounded display clearly identified.
- [x] Add concise game-day links and a detailed line/grade section with stable controls, source attribution, clocks and records. Test signed away favorites, loss-but-cover, win-without-cover, exact push, no edge, missing/conflicting/future sources and durable cutoff crossings; independently review and publish.
