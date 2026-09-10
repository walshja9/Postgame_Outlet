# Passing inputs and win probabilities: fixed September 10 study

**Neither feature ablation improved margin accuracy, and no probability variant passed the predeclared further-study screen. All variants remain EXPERIMENTAL / HOLD. The main model and its published picks are unchanged.**

This study asks whether two groups of overlapping passing statistics can be simplified, and whether adding an intercept to probability calibration helps. It does not evaluate sportsbook spreads, against-the-spread picks or betting returns.

The [charter](charter.md) fixed the candidates before fitting. The original regular-season plus postseason-history model is the control. One ablation removes five QB passing-performance features while retaining QB volume, experience, draft and rushing information. The other removes team passing EPA and offensive sack avoidance while retaining the rest of the offense and defense information. Each refits the remaining coefficients; the resulting changes are not manual point deductions.

| Margin construction | Games | Mean absolute error | Seasons better than control | Further-study screen |
|---|---:|---:|---:|---|
| Original postseason model | 2,127 | 10.102102 | Control | Control |
| Without five QB passing-performance fields | 2,127 | 10.151334 | 2 of 8 | FAIL |
| Without team passing EPA and sack avoidance | 2,127 | 10.117879 | 3 of 8 | FAIL |

Lower error is better. The paired 95% season-block interval for improvement was **[-0.083490, -0.015755]** for removing the QB block and **[-0.045976, 0.018479]** for removing the team passing block. Negative values mean higher error than the control. These results do not support simplifying either block in the main model on the strength of this study.

Probabilities were evaluated separately. Every probability fit used only earlier seasons' out-of-fold margin predictions, with 2018-2019 as warmup and 2020-2025 as evaluation. Both probability curves keep a separately estimated training-only tie probability. The scalar curve fits a nonnegative slope; the second also fits an intercept. The intercept can change the probability favorite without changing the margin forecast, so these remain separately identified outputs.

| Margin model / probability curve | Games | Three-way log loss | Three-way Brier | Further-study screen |
|---|---:|---:|---:|---|
| Original / scalar | 1,615 | 0.647142 | 0.440351 | Control |
| Original / intercept | 1,615 | 0.647367 | 0.439995 | FAIL |
| Without QB passing / scalar | 1,615 | 0.649338 | 0.442361 | FAIL |
| Without QB passing / intercept | 1,615 | 0.649535 | 0.441990 | FAIL |
| Without team passing / scalar | 1,615 | 0.647036 | 0.440447 | FAIL |
| Without team passing / intercept | 1,615 | 0.647276 | 0.440136 | FAIL |
| Training-only constant reference | 1,615 | 0.711287 | 0.501591 | Reference |

Lower log loss and Brier are better; Brier sums squared error across home win, away win and tie, with range 0-2. The smallest log-loss difference was only 0.000106 in favor of the team-passing ablation's scalar curve, with a paired 95% interval **[-0.001802, 0.001960]**. It failed the fixed practical-size and uncertainty requirements. The original model's intercept curve changed the probability favorite in 60 of 1,615 games and had slightly worse log loss, despite slightly lower Brier. There is no selected replacement.

The run used 18 new margin fits and 42 calibration fits, once, from 20:29:47 to 20:30:06 UTC on September 10. All 3,407 saved original feature rows were retained apart from the two explicitly dropped blocks. The saved control predictions replayed within 3.56e-15, and the new serialized fits within 5.33e-15. All 810 existing evidence files included in the before/after inventory were unchanged; the mutable season pointer was explicitly outside that inventory.

Historical source vintages remain **REVIEW REQUIRED**. These seasons have already been inspected in earlier studies, so they are diagnostic rather than a fresh holdout. Chronological folds and calibration boundaries were verified, but this does not recreate historically captured T-60 roster and source feeds. The several fixed comparisons are not multiplicity-adjusted discoveries, and a passing descriptive screen would not itself authorize scientific promotion.

Prospective tracking is implemented separately in `pgo_weights_monitor.py`. It freezes all three margin models and all six probability curves on the same eligible future games. Each issuance must replay the control to the current saved primary margin, retain the exact matchup vector and source evidence, and finish before T-60. Previously issued pairs cannot be replaced; verified finals grade them without refitting. The completed NE-Seattle opener is excluded from new issuance. Actual saved prospective counts and status appear in the season state; a successful local preview is not a claim that issuance has been published.

Evidence:

- [No-fit preparation manifest](prepare-attempt01/manifest.json), [source preservation and replay](prepare-attempt01/run-receipt.json).
- [Final run manifest](run-attempt01/manifest.json), SHA-256 `481d64fec1512934da21066c5a5c40b3f43dc4ad45ef7295d243948deba9e814`.
- [Margin predictions](run-attempt01/matched-predictions.csv), [margin metrics, paired intervals and screens](run-attempt01/margin-metrics.json).
- [Probability predictions](run-attempt01/probability-predictions.json), [probability metrics, fixed reliability bins, intervals and screens](run-attempt01/probability-metrics.json).
- [Final margin fits](run-attempt01/final-fits.json), [final calibrations](run-attempt01/final-calibrations.json), [fit and preservation receipt](run-attempt01/run-receipt.json).

Reproduction uses `python -B -m research.pgo_weights_candidate_20260910.candidate prepare --output <new-directory>` and then its explicit `fit` command with the preparation manifest hash. Those commands create new scientific attempts; verifying the existing manifest and saved predictions requires no refit. The issued run must never be overwritten or silently rerun.
