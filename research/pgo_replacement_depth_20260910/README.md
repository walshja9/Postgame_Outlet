# Replacement-depth evidence ? September 10, 2026

**Historical admission: BLOCKED FOR FITTING. Current capture: DESCRIPTIVE / NOT IN MODEL.** No injury weights, player-quality values, score changes or probability changes were created. The [charter](charter.md) requires dated, identifiable historical roles before fitting an unavailable-player or replacement-depth effect.

The executable [admission audit](capture03/admission.json) checked the existing pinned historical preparation: 40 historical source records, 6,814 team-games and 1,017 stable 2025 player histories. It found **zero historical depth sources and zero source-publication/capture clocks** in that admitted inventory. These archived retrospective files cannot establish which depth or injury information was known before historical kickoffs. The result applies to this inventory, not a claim that suitable data cannot exist elsewhere.

## Current observation

The latest [snapshot](capture03/snapshot.json) was recorded September 10 at 20:36:33 UTC and completed at 20:36:35 UTC. It reuses hash-verified source archives; it does not fetch new sources. The newest input capture is 19:54:17 UTC. Current provider depth rows are dated 12:01:46 UTC. Source references include captured timestamps, member hashes and direct public archive links.

The capture describes all 32 teams: 793 ACT-roster defenders, 138 reserve defenders, 371 distinct players listed first in at least one provider defensive slot, 14 conservative depth-name conflicts and 20 unlisted ACT defenders. Multiple defensive packages can list more than eleven players first. Only SF and LAR have verified official reports in the eligible saved observations; the other 30 teams remain UNKNOWN. The completed NE?SEA opener is excluded. Fifteen still-unlocked matchups receive a new prospective observation; all-team current roster context is not retroactive evidence for the opener.

Prior playing-time shares describe observed 2025 usage. The sum for currently unavailable defenders is explicitly a **known-history subtotal**, not expected lost exposure, backup quality or an injury rating. Sixty unavailable defenders lack a prior role in this source window. Missing history and rookies remain unknown. `expected_unavailable_exposure` and `forecast_adjustment` are null. ACT does not mean healthy; not confirmed OUT does not mean available. Questionable status remains separate. DNP practice participation is not converted into OUT. Provider LB, OLB and DE labels are retained without guessing EDGE assignments.

## Integration contract

`capture(state, root, checked_at)` returns a compact descriptive object for the existing season-state writer. `root` is the season archive directory. It reads only archived references and pinned 2025 history; it does not mutate the supplied state. Missing or stale roster/depth references produce a separate BLOCKED result. Invalid bytes, paths, identity or source times raise an error for the caller to isolate from the main forecast pipeline.

The result contains `status`, `generated_at`, `source_as_of`, `historical_admission`, `forecast_adjustment`, `sources`, 32 `teams`, eligible `games` and limitations. Game `teams_with_saved_observations` means a saved package contains that team; consult each team's `report_status` and `final_inactives_status` for verified coverage. It does not mean every saved report is verified. The root writer must reject newly captured games whose cutoff elapsed before durable state publication, while retaining older archived observations. Latest team summaries may change; earlier append-only state captures remain the historical record.

Archive references are repository-relative and independently checked by raw digest and byte length, including compressed sources. This helper therefore does not depend on the original external Windows source paths. The historical preparation and prior-role package have fixed external manifest pins.

## Verification and lineage

Ten focused tests passed in 0.139 seconds. Checks cover hand-computed role subtotals, missing roles/identities, DNP versus OUT, uncertain backups, wrong names, future and stale depth rows, duplicate IDs, source hashes/path containment, cutoff eligibility, immutable input state, failed historical admission, and saved UNKNOWN reports not being labeled verified. All three completed capture manifests and their members were verified, and their source-state pointers stayed unchanged during each recording.

[Capture 01](capture01/manifest.json) and [capture 02](capture02/manifest.json) remain unchanged. Exact pre-repair source and test copies and repair reasons are retained in [repairs](repairs/README.md). The first repair kept officially resolved names visible when absent from a newer roster and added source links. The second renamed the saved-observation coverage field to avoid claiming verification for UNKNOWN reports. These are descriptive display repairs, not refits or historical-experiment retries.

Latest [manifest](capture03/manifest.json) SHA-256: `b934339a9a03589fb60949d9e03c3ba76336c4b7922ef1da1e0319abcef3f26a`. Its [receipt](capture03/receipt.json) pins the executed code, charter, season-state pointer and historical evidence. Do not overwrite completed captures.

Focused check: `python -m unittest tests.test_pgo_replacement_depth -q`.

Recorded command: `python -m research.pgo_replacement_depth_20260910.capture --output research/pgo_replacement_depth_20260910/capture03`. A future observation requires a new exclusive output directory and actual capture clock.
