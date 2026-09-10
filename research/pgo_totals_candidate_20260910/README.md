# Updating game totals: fixed-formula diagnostic

**Both predeclared formulas passed the further-study screen. They remain EXPERIMENTAL / HOLD; no live forecast changed.** Updating each team's scoring history during the season reduced historical total-point error, compared with holding the previous season's averages fixed. The familiar 2018â€“2025 seasons and unresolved historical publication timestamps prevent a fresh-validation claim.

The [charter](charter.md) was written and hashed before the one [attempt](attempt01/manifest.json). This tested two formulas, not a parameter search or coefficient refit. For each team's points scored and allowed, four or eight pseudo-games of its preceding-season average are combined with its observed current-season games. Both teams' four rates are summed and divided by two. No game from the current Eastern game day enters an estimate.

Lower total MAE is better; units are NFL points. All formulas use the identical 2,127 regular-season games.

| Formula | Total MAE | RMSE | Bias, predicted minus actual |
|---|---:|---:|---:|
| Prior-season REG+POST league mean | 11.074173 | 13.987295 | -0.174985 |
| Prior-season REG+POST team PF/PA | 11.035389 | 13.916996 | -0.248334 |
| Updating, four pseudo-games | 10.742026 | 13.573598 | -0.050558 |
| Updating, eight pseudo-games | 10.760222 | 13.595872 | -0.099879 |

Against the team PF/PA control, the four-pseudo-game formula improves MAE by **0.293363** points (about 2.7%). Its paired season-cluster 95% interval is **[0.156533, 0.453672]**; the predeclared 97.5% interval accounting for two candidate decisions is **[0.138148, 0.479658]**. The eight-pseudo-game formula improves by **0.275166**, with 95% interval **[0.164747, 0.404436]**, and 97.5% interval **[0.149639, 0.423114]**. Both improve all eight seasons against both controls. Season-week sensitivity intervals are also positive; they do not replace the season-cluster analysis.

| Evaluation slice | Prior PF/PA MAE | Four pseudo-games | Eight pseudo-games |
|---|---:|---:|---:|
| Week 1 | 10.504296 | 10.504296 | 10.504296 |
| Weeks 1â€“4 | 10.824229 | 10.713369 | 10.737885 |
| Weeks 5â€“18 | 11.101817 | 10.751041 | 10.767249 |
| 2018 | 11.492611 | 11.049534 | 11.071030 |
| 2019 | 11.241644 | 10.957232 | 10.959544 |
| 2020 | 11.435862 | 10.672284 | 10.794865 |
| 2021 | 11.536123 | 11.230036 | 11.246108 |
| 2022 | 11.196621 | 10.875764 | 10.925541 |
| 2023 | 10.538801 | 10.531814 | 10.505959 |
| 2024 | 10.107965 | 9.942536 | 9.942385 |
| 2025 | 10.796662 | 10.704143 | 10.669001 |

The four-pseudo-game formula did not win every head-to-head season against eight; both remain separately declared candidates. Week 1 estimates equal the old rule because there are no current-season observations yet. This test therefore would not have changed the opener's score estimate.

History contains 3,562 completed 2013â€“2025 games (3,407 REG and 155 postseason), or 7,124 team-game observations. Each season uses its own immediately preceding-season REG+POST prior; evaluation targets remain REG. The 2025 prior rates and league mean reproduce the current saved scoring-rate package exactly. This REG+POST control differs from the older REG-only totals diagnostic, so its MAEs must not be substituted into that older comparison.

Verification: five focused unit tests passed; the recorded attempt verifies exact cohort identities/counts, all source/package hashes, exact current scoring-rule replay, and a current-day/future-outcome perturbation. All 227 protected static evidence/prior-experiment files and the used code/source hashes match before and after. A separate direct CSV calculation reproduced the four pooled MAEs, and all manifest member digests checked. These are implementation checks, not independent scientific approval. The [leakage report](leakage-audit.md) retains REVIEW REQUIRED for unavailable source-publication timing.

Next: a separately approved before-T-60 prospective comparison can record both fixed formulas and both controls from identical verified prior-day history, without changing main margins, scores, probabilities or confidence points. Preserve each pair and source witness once issued, then grade verified finals. Formal review is after the 2026 regular season with at least 150 common pairs across 12 weeks; otherwise report insufficient evidence. Do not tune after each result or choose an arm solely because its retrospective average is lowest.

Artifacts: [complete metrics and intervals](attempt01/metrics.json), [all forecasts and history counts](attempt01/predictions.csv), [small public summary](attempt01/public-summary.json), [before/after receipt](attempt01/run-receipt.json). Manifest SHA-256: `790fd10b4d3d8afa431c41737b5f8361387844c44d354b175459eba1cf9c0183`.

Focused check: `python -m unittest tests.test_pgo_totals_candidate -q`.

Recorded command: `python -m research.pgo_totals_candidate_20260910.candidate --output research/pgo_totals_candidate_20260910/attempt01`. It refuses an existing output directory. Do not rerun this frozen attempt; new research versions require their own declaration and output.

Portability: the frozen runner resolves its historical schedule through the original source inventory, which names an external Windows cache under `D:/Postgame_Outlet-pgo-model/.cache/pgo_v1/`. Its exact source path and digest are recorded in the attempt inputs. Reproduction on another machine requires providing those exact bytes at the declared location or a separately versioned, reviewed path-resolution change; the executed runner has not been silently rewritten. The saved predictions, metrics and manifest remain directly inspectable without that cache.
