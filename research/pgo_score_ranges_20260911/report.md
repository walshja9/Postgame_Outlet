# Score-range research - September 11, 2026

**Public numerical outcome ranges: UNAVAILABLE. Scientific status: EXPERIMENTAL / HOLD. Leakage verdict: REVIEW REQUIRED.**

A fixed, predeclared chronological residual recipe has been executed. Historical intervals are diagnostics only; no production forecast, source, renderer, workflow or older attempt was modified.

## Recipe and evidence

The charter was saved before execution and its hash is recorded in run-start.json. Margin uses the saved postseason candidate; total uses the saved pfpa_prior scoring rule, without selecting an improved totals candidate. For each test season, take the 80% finite-sample order statistic of absolute residuals from earlier seasons only. Require two prior seasons and 500 games. Hold each radius fixed for the complete test season and center on each original point prediction. Bounds are inclusive, unrounded and unclipped. These are outcome residual ranges, not coefficient sensitivity, MAE, or confidence intervals for average performance.

Exactly 2,127 identical REG game IDs from 2018-2025 passed hash, manifest, identity, date and finite-value checks. The 512 games from 2018-2019 calibrate only; 1,615 games from 2020-2025 are evaluated. No 2026 game enters the analysis. Cohorts are 256, 256, 256, 272, 271, 272, 272, 272 by input season.

## Coverage and width

Coverage is game-weighted; width is upper minus lower in NFL points. Nominal target is 80%, a diagnostic reference rather than a guaranteed coverage level.

| Season | Calibration n | Evaluated n | Margin coverage | Margin width | Total coverage | Total width |
|---|---:|---:|---:|---:|---:|---:|
| 2020 | 512 | 256 | 82.8% | 34.28 | 80.9% | 37.44 |
| 2021 | 768 | 272 | 76.5% | 33.63 | 81.2% | 36.91 |
| 2022 | 1040 | 271 | 85.6% | 34.26 | 82.3% | 36.50 |
| 2023 | 1311 | 272 | 79.0% | 33.38 | 83.5% | 36.26 |
| 2024 | 1583 | 272 | 82.4% | 33.54 | 84.2% | 35.94 |
| 2025 | 1855 | 272 | 81.6% | 33.37 | 80.5% | 35.44 |

| Pooled slice | n | Margin coverage | Margin width | Total coverage | Total width |
|---|---:|---:|---:|---:|---:|
| all | 1615 | 81.3% | 33.74 | 82.1% | 36.40 |
| week1 | 96 | 85.4% | 33.74 | 89.6% | 36.41 |
| weeks1_4 | 383 | 83.3% | 33.74 | 85.1% | 36.41 |
| weeks5_18 | 1232 | 80.7% | 33.74 | 81.2% | 36.40 |

| Season, Weeks 1-4 | n | Margin coverage | Total coverage |
|---|---:|---:|---:|
| 2020 | 63 | 92.1% | 82.5% |
| 2021 | 64 | 82.8% | 89.1% |
| 2022 | 64 | 89.1% | 84.4% |
| 2023 | 64 | 73.4% | 85.9% |
| 2024 | 64 | 78.1% | 87.5% |
| 2025 | 64 | 84.4% | 81.2% |

Complete season-by-slice coverage and width are retained in attempt01/metrics.json; every evaluated bound is in attempt01/ranges.csv. Coverage failures are retained, with no tuning or omitted season.

## Timing audit and limitations

- All 2,127 rows lack issued_at, inputs_available_at and final_verified_at; prospective admissible count is zero. These are three overlapping missingness counts, not 6,381 separate games. Kickoff is available and timezone-aware; it is not an issuance witness.
- Parent margin and total charters explicitly retain unresolved historical source/revision and starter timing. The total prior/current history dates precede the game day. Earlier-season residual separation passes, but cannot prove historical input availability or repair unknown source vintages.
- All historical seasons were already inspected in earlier experiments. This is reused diagnostic history, never new prospective proof. The once-per-season fitted point model also changes across folds; residual exchangeability is not established. Repeated teams, season dependence and possible drift prevent a distribution-free coverage claim.
- A strict admission helper rejects missing/naive/invalid timestamps, input publication after issuance, issuance after T-60, impossible final timing, and calibration labels not yet verified at later issuance. It does not fabricate timestamps or attest to feed truth.
- Marginal 80% ranges for margin and total do not imply simultaneous 80% coverage for both or a joint home/away score interval. No score-pair range, calibrated probability, or betting recommendation follows.

## Path to public readiness

Keep the public state unavailable. A separately approved frozen prospective protocol must capture exact model/source/recipe versions, inputs_available_at and issued_at before real T-60, preserve the issued bounds and calibration game identities, then append verified final timestamps/results. Under this unchanged recipe, first accumulate at least two complete timestamp-admissible calibration seasons and 500 games; then evaluate a later full season with at least 150 games over 12 weeks including 40 games in Weeks 1-4. Freeze numerical acceptance criteria before that series and examine coverage uncertainty, width, early-season behavior and time dependence. A shorter protocol requires a new charter rather than retrospective admission or fitting from two 2026 results. This work neither starts the series nor authorizes promotion.

## Verification and reproduction

- `python -m unittest tests.test_pgo_score_ranges -q`: 5 tests passed. Checks cover finite-sample quantile, minimum sample, same/future-season outcome perturbation, later-season responsiveness, duplicate IDs, time overlap, timestamp/cutoff boundaries, inclusive coverage and early-cohort denominators.
- Executed exactly once: `python -m research.pgo_score_ranges_20260911.experiment --output research/pgo_score_ranges_20260911/attempt01` (exit 0). Existing output directories are refused. Preserve this attempt; any new execution must use a newly declared output.
- Source CSV hashes match their parent manifests. Charter, executable, source CSV and parent-manifest hashes match before/after. The new attempt manifest pins its output members. No old attempt was rewritten.

## Recorded input/code hashes

| File | SHA-256 |
|---|---|
| `research\pgo_score_ranges_20260911\charter.md` | `2cb485b84212da6cfc16e29719d3f5f1d08294991ceba9a326dfbd6cffbad7e6` |
| `research\pgo_score_ranges_20260911\experiment.py` | `3e8db385625803188cefbc8e5cf98bea3e84e5ed2d06b46eb9b2660acbc2f4c8` |
| `research\pgo_postseason_candidate\run-20260909-attempt01\matched-predictions.csv` | `3df4dbf26743a3686b6253bb4eb578457d0e2629dde1f0218f215c462feea0cf` |
| `research\pgo_totals_candidate_20260910\attempt01\predictions.csv` | `f96c85bf348a7df7c88dc6288bc2d470c4270134505d5bb95ce84c2fc534fce8` |
| `research\pgo_postseason_candidate\run-20260909-attempt01\manifest.json` | `a58aeff835471182a555e4b926beafd0db01c7c5e3fe19827ddf56bd03f2514a` |
| `research\pgo_totals_candidate_20260910\attempt01\manifest.json` | `790fd10b4d3d8afa431c41737b5f8361387844c44d354b175459eba1cf9c0183` |

Independent verification: direct calculation from ranges.csv reproduced 1,313/1,615 margin hits and 1,326/1,615 total hits; all new attempt manifest hashes and byte counts verified.
