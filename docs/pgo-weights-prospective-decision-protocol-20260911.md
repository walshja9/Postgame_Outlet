# PGO weights and probabilities: prospective decision protocol

Recorded September 11, 2026 UTC during the approved audit repairs. Status remains **EXPERIMENTAL / HOLD**. This is a separate decision protocol, written after the historical study and after prospective issuance began; it is not a pre-issuance registration of those existing forecasts. It changes no fits, calibration, saved forecast, confidence allocation or historical charter.

The [saved September 11 02:30:41 UTC state](https://raw.githubusercontent.com/walshja9/Postgame_Outlet/main/docs/evidence/season-2026/runs-v2/20260911T023041564550Z/manifest.json) contains 15 weights/probability comparisons, first issued September 10 at 20:47:02 UTC, and zero completed paired games or weeks. Some games had already started. Those are the counts at that checkpoint, not a claim about later results. Its manifest SHA-256 is `eea05549be7be95695cde074684e75957ae01817204703840ce0ccfcffc3e9ba`.

## Fixed question and methods

Does either passing-feature ablation improve final home-minus-away NFL margin, including overtime, and does any of the five alternative probability methods improve home-win/away-win/tie probabilities versus the existing postseason scalar method? One row is one regular-season game; each game has equal weight. Ties remain a distinct probability outcome and remain in margin error.

Use only the already frozen package with manifest SHA-256 `481d64fec1512934da21066c5a5c40b3f43dc4ad45ef7295d243948deba9e814`. Its three margin arms are `postseason`, `without_qb_passing` and `without_team_passing`; each has `scalar` and `intercept` probability curves. The [historical charter](../research/pgo_weights_candidate_20260910/charter.md) defines their features and fits. No new training, tuning, feature selection, calibration or weekly significance decision occurs. Historical seasons remain reused diagnostics with source vintages REVIEW REQUIRED.

## Prospective cohort and timing

The formal cohort consists of 2026 regular-season Weeks 2-18 games whose original comparison is durably issued after this protocol's first successful publication and strictly before kickoff minus 60 minutes. Retain the publication receipt's actual UTC clock, Git commit and protocol file hash as the activation witness. If that witness is absent, formal review is BLOCKED. A backdated document or commit-author clock cannot establish activation.

All Week 1 comparisons, including the 15 already saved rows, remain in the existing descriptive monitor and are excluded from this formal cohort. Nothing is deleted or reissued. Later pre-activation or late rows also remain descriptive and are listed separately. Only the original saved comparison qualifies; a subsequent primary-model revision does not replace it.

Require the same verified game identity, original matchup vector, source witness, expected QBs, control replay and durable T-60 cutoff already enforced by `pgo_weights_monitor.py` and the season writer. Grade only verified finals. Use a common cohort with all three margins and six complete probability vectors for every primary comparison. Report every excluded/missing game and reason; never fill in a missing forecast or remove a poor result. An unresolved source, identity, accepted-final conflict or immutable-evidence mismatch blocks the formal decision until explicitly adjudicated without rewriting issued forecasts.

Review once, after the 2026 regular season and its eligible finals are verified, with at least **150 common paired games across 12 distinct weeks**, following the [totals protocol's evidence floor](../research/pgo_totals_candidate_20260910/prospective-charter.md). This floor is not a statistical power guarantee. Below either minimum, report **INSUFFICIENT EVIDENCE / HOLD**; do not lower the threshold or extend the season silently. The existing monitor may continue descriptive reporting before that review.

## Metrics and decision rules

There are seven fixed primary comparisons: each of two ablated margin arms against `postseason`, and each of five alternative probability curves against `postseason_scalar`. An intercept-versus-scalar comparison within an ablated arm is secondary and cannot independently earn a passing decision.

For each game, improvement is control loss minus candidate loss, so positive is better. Margin loss is absolute error in NFL points. Probability loss is three-class negative log likelihood using the saved probability of the actual outcome, floored at `1e-15`. Mean improvement weights games equally. A candidate must clear both its practical threshold and uncertainty check:

- Margin: at least **0.05 points lower MAE** than the control.
- Probability: at least **0.005 lower mean log loss** than the control.
- Consistency: positive mean improvement in at least two-thirds of eligible weeks, rounded up; ties in weekly improvement do not count as wins.
- Uncertainty: positive multiplicity-adjusted lower bound under both resampling schemes below. Report all seven decisions, including failures.

At the single formal review, use 10,000 paired bootstrap draws with seed `20260911`. Keep all games, arms and probability curves from a sampled week together; resample the observed weeks with replacement and recompute the game-weighted mean improvement. Use the same draws for all seven comparisons. The one-sided lower percentile is `0.05 / 7` (approximately 0.007142857), applying a fixed Bonferroni adjustment across the seven decisions. Also report ordinary 95% intervals as descriptive context.

Repeat as a dependence sensitivity using contiguous four-calendar-week moving blocks between the first and last eligible weeks, retaining empty weeks in that calendar sequence. Sample those blocks with replacement, concatenate and truncate to the original calendar length, and recompute game-weighted improvement. Use the same seed, draw count and adjusted percentile; redraw a sample containing no games. Weekly clustering alone does not eliminate dependence from recurring teams; even agreement between both schemes is limited, single-season evidence, not guaranteed family-wise coverage or independent replication.

Report per-week counts/losses and pooled results for every arm, alongside margin RMSE/bias/winner record, three-class sum Brier, ten fixed selected-team reliability bins with counts, ties and favorite disagreements. Show early versus late season and withheld/missing coverage descriptively; no slice becomes a new selection criterion. The existing frozen control is the primary baseline; do not invent unsaved historical or prospective baseline probabilities at review time.

## Disposition and preservation

A passing result means **eligible for independent scientific review**, not automatic adoption or promotion. Adequate sample size with a failed practical, consistency or uncertainty check means **NO DEMONSTRATED IMPROVEMENT / HOLD**. All candidates, original package hashes and every issued row remain unchanged regardless of result.

The reviewer must verify activation, cohort, source timing, saved numerical replay and original results before computing decisions. A separately recorded evaluation may replay saved rows without fitting. Preserve failed reviews and corrections as new artifacts. If the rules change after outcomes are inspected, version the protocol, label the affected analysis exploratory and reserve a new untouched cohort; never relabel this cohort as fresh again.
