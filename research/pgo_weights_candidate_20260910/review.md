# Independent implementation review ? September 10, 2026

**Computational and monitor-module review: PASS within the scope below. Scientific status: EXPERIMENTAL / HOLD.** Both margin ablations and all declared probability improvements failed their historical further-study screens. This review does not promote an arm or convert reused seasons into a fresh holdout.

The reviewer did not fit models, rerun the experiment, issue prospective pairs or change source/model files. The fixed run manifest is `481d64fec1512934da21066c5a5c40b3f43dc4ad45ef7295d243948deba9e814` in [run-attempt01](run-attempt01/manifest.json).

## Research checks

- Reviewed the locked charter, exact feature ablations, inherited preprocessing/fitting policy, and chronological split construction before fitting. Preparation manifest `80bac38379f4955e9f74b8c2d0020d585d387706f67c560614b5b8fc66bac8c4` and all five members checked. All 3,407 saved design rows match the baseline; 2,127 control predictions replay with maximum absolute difference 3.55e-15.
- Verified all 33 completed-run manifest members. Recorded counts are 18 margin fits, 42 calibration fits, 2,127 margin evaluation games and 1,615 probability evaluation games. The receipt reports protected inputs unchanged and maximum serialized margin replay difference 5.33e-15.
- Independently calculated pooled MAE from each of the three saved margin columns; all match recorded metrics. Independently calculated three-class log loss and sum Brier for all seven probability methods; all match within 1e-12.
- Independently checked calibration training IDs/seasons and kickoff order for all six evaluation seasons. Training uses only earlier out-of-fold seasons. Training-only smoothed tie mass matches exactly; saved probabilities reproduce from saved calibration coefficients within 2.22e-16.
- This bounded review did not independently resample bootstrap intervals. Source-publication vintages remain REVIEW REQUIRED, and the reused-season diagnostic limitation is unchanged.

## Prospective monitor review

Read `pgo_weights_monitor.py` and its focused tests. No actionable defect was found at its documented boundary: the caller supplies a verified season state. New rows require the same ranking edition, input clock and expected QB identities as the main game, exact feature inventory, and original-control margin replay within 1e-8. The fixed package uses the externally pinned run manifest. Original seed features are matched to the verified initial snapshot; later current references depend on the caller's raw-hash verification.

The monitor records three margin arms and six probability curves from the same feature vector. It never allocates confidence points or changes main picks. Old pairs remain unchanged on later main revisions or package failure. Verified final identities/times/scores grade saved forecasts; corrections to accepted finals are rejected. The durable guard forbids removals or changes to issued fields and checks the actual write clock is strictly before T-60 for new pairs. Failure has a separate BLOCKED status.

Independent command: `python -m unittest tests.test_pgo_weights_monitor -q` ? **6 tests passed in 0.202 seconds**. Tests cover matched control/QB/source rejection, immutable pairs, cutoff boundaries, withheld rows, final grading, and package failure preservation. Monitor SHA-256: `7ef638594bacfe06d4c05118b6fc5b5fb116e05b77130a405a7cedd7fd1d5dd3`; test SHA-256: `2c360e821547e717666000175fde8adaa0bf8ad6eb7b70e0ed19ed6b56cf56a2`.

At review time, automatic season refresh and durable-write hooks for this monitor were still root-owned integration work. Operational publication requires both hooks, verified current-source loading, generated-state review and deployment checks. This module review alone is not a claim that the scheduled monitor is already running.
