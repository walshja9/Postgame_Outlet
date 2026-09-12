# Preserve roster-inactive defenders in future inventory

The source-refresh release exposed an existing cohort gap: seven defensive roster rows with status INA retained current team identity but were excluded from the named inventory. Bethune and Prysock also match the saved official SF-LAR inactive list; five other INA exclusions already existed before the refresh. Exact evidence: output/source-refresh-20260912/defender-ina-contract.json and defender-identity-delta.json. This is descriptive coverage, not a numerical prediction defect.

The user authorized continued recommended fixes and publication. Correct future captures now; preserve version 1 reproduction and all forecasts. No new approval gate is needed.

- [x] Capture/reader: explicit inventory version 2 includes INA as dated roster context; it does not infer injury or future absence. Preserve version 1 defaults/output and replay each saved inventory with its own version. Reject unsupported versions. Reuse the existing identity, source, timing and usage checks. Add an inactive roster count and retain source season/week/game type where available. Regression-check v1 equivalence, v2 retention, no automatic OUT, future-game context and usage linkage.
- [x] Production/UI: explicitly request version 2 for new scheduled captures. Accept both known versions in presentation; show inactive roster names as dated context separately from confirmed current-game absences. Explain the older cohort's omission without changing its saved count. Keep all numerical model outputs and locked records unchanged.
- [x] Protocol/release: add a dated version 2 addendum without editing the original charter; update the living README. Review changes, run the exact scheduled gate and full release CI, observe a normal fresh capture, replay both versions from their exact archives, verify old file bytes and all saved picks, and inspect the published page. No fitting, retrospective relabeling, new target capture or rebuilt old inventory.

This extends the source-refresh release only to repair the coverage issue revealed by its verified new inputs. It does not authorize a learned injury effect or claim a model-quality improvement.

## Integration evidence

Six added tests cover version-selected archive replay/linkage, unsupported versions, inactive-only depth positions, conditional addendum receipt pins and public scope labels; existing production and T-60 tests now also require the v2 opt-in and preserve locked v1 observations. Meaningful red failures were observed before the fixes. Final exact scheduled gate: 236 passed in 22.634 seconds. Independent review approved the final diff after correcting the inactive-only all-zero role-row issue. Existing v1 archive runs-v2/20260912T050141312123Z reproduces exactly with 1,193 defenders; no archived source or state was modified. Release CI and fresh production v2 observation remain pending.

## Published result

Source ee671af was merged with canonical mutable data into tested head a620ff285bf2661081e08b0f5aa6fe1c884f347b. Full release run 34675490973 succeeded: main 912 tests in 910.280 seconds (911 passed, one skipped), supplemental 14 plus 14 passed. Total 939 passed, one skipped. Independent review approved the final source and integration; the original v1 charter and saved evidence were not edited.

Normal production run 34675490607 passed all 236 scheduled checks and saved version 2 at runs-v2/20260912T052514986561Z. Both v1 and v2 replay exactly. Membership changed from 1,193 to 1,200 by retaining seven INA defenders: Mike Morris, Ty Okada, Nick Emmanwori, Tatum Bethune, Ephesians Prysock, Karon Prunty and Erick Hunter. All seven remain dated Week 1 roster context with unknown future-game availability; INA alone did not set confirmed_unavailable. Fresh existing roster/depth receipts and bytes were reused unchanged. Role tables retain their prior scope, and no new all-zero INA-only position rows were added.

All 16 original winner/score/confidence forecasts, rankings, accepted finals, calibration, model records and locked sportsbook comparisons were preserved. Rollover observation succeeded with WAITING because Week 1 is incomplete; notification health allowed resolution. Numerical injury effects remain absent and historical fitting admission remains blocked.

The public page showed the 1,200-record count and separate NE/SF inactive context; the phone layout and caveat were visually checked, and the viewport was restored. The anonymous Shopify page referenced the verified public iframe. Final publisher b7219970b40feb43ca07517b1ec00fd9cf8ef1b6 and Pages run 34676276214 succeeded. At 05:44:08 UTC, public index, Forecast Lab and CSS bytes exactly matched that commit. At 05:44:11 UTC, the newer canonical state runs-v2/20260912T053023991725Z also replayed and retained identical full saved weeks, rankings, records and defender membership.

Evidence is under output/source-refresh-20260912/: live-inactive-inventory.json, live-inactive-browser-verification.json, public-wrapper-verification.json, final-publication-preservation.json, public-b7219970b40f.json and release-34675490973-* logs/counts. The prior source-refresh receipts remain separate. Future scheduled availability checks and the real end-of-week rollover are subsequent operational observations, not unfinished release steps.
