# Preserve roster-inactive defenders in future inventory

The source-refresh release exposed an existing cohort gap: seven defensive roster rows with status INA retained current team identity but were excluded from the named inventory. Bethune and Prysock also match the saved official SF-LAR inactive list; five other INA exclusions already existed before the refresh. Exact evidence: output/source-refresh-20260912/defender-ina-contract.json and defender-identity-delta.json. This is descriptive coverage, not a numerical prediction defect.

The user authorized continued recommended fixes and publication. Correct future captures now; preserve version 1 reproduction and all forecasts. No new approval gate is needed.

- [x] Capture/reader: explicit inventory version 2 includes INA as dated roster context; it does not infer injury or future absence. Preserve version 1 defaults/output and replay each saved inventory with its own version. Reject unsupported versions. Reuse the existing identity, source, timing and usage checks. Add an inactive roster count and retain source season/week/game type where available. Regression-check v1 equivalence, v2 retention, no automatic OUT, future-game context and usage linkage.
- [x] Production/UI: explicitly request version 2 for new scheduled captures. Accept both known versions in presentation; show inactive roster names as dated context separately from confirmed current-game absences. Explain the older cohort's omission without changing its saved count. Keep all numerical model outputs and locked records unchanged.
- [ ] Protocol/release: add a dated version 2 addendum without editing the original charter; update the living README. Review changes, run the exact scheduled gate and full release CI, observe a normal fresh capture, replay both versions from their exact archives, verify old file bytes and all saved picks, and inspect the published page. No fitting, retrospective relabeling, new target capture or rebuilt old inventory.

This extends the source-refresh release only to repair the coverage issue revealed by its verified new inputs. It does not authorize a learned injury effect or claim a model-quality improvement.

## Integration evidence

Six added tests cover version-selected archive replay/linkage, unsupported versions, inactive-only depth positions, conditional addendum receipt pins and public scope labels; existing production and T-60 tests now also require the v2 opt-in and preserve locked v1 observations. Meaningful red failures were observed before the fixes. Final exact scheduled gate: 236 passed in 22.634 seconds. Independent review approved the final diff after correcting the inactive-only all-zero role-row issue. Existing v1 archive runs-v2/20260912T050141312123Z reproduces exactly with 1,193 defenders; no archived source or state was modified. Release CI and fresh production v2 observation remain pending.
