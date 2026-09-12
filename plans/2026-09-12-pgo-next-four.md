# PGO starter workflow and prospective evidence implementation

> Approved by the user's September 12 "proceed" on the four recommendations. Execute continuously using the existing isolated publication worktree and independent reviews.

**Goal:** Make starter revisions visible and repeatable, collect offensive non-QB participation evidence, and begin correctly dated score-error collection for eventual outcome ranges.

**Baseline:** `8ca03a106f20aa1a71fbcbf9750bf04af433e7b9` on `codex/pgo-readable-games-20260910`; later mutable-only season publisher commits must be retained.

**Architecture:** Keep the current static site, season writer, raw-source archives and optional monitor hooks. Add two optional collection results to the season state. Reuse validation/read/write helpers where their contracts fit; do not change frozen historical study semantics. A small source-capture command prepares starter authority for explicit review and activation. The existing game explanation remains the destination of a new visible link.

**Global constraints**
- No new dependency, model fitting, weights, numerical injury deduction, public numerical outcome range or model promotion.
- Preserve all issued forecast values, expected QBs, source annotations, fixed confidence allocations, accepted results, locked ATS entries, old research attempts and archive bytes. Routine pre-lock updates remain governed by existing source and T-60 checks.
- New collection starts with actually saved future-game observations. No earlier game becomes prospective by reconstruction; publication/receipt/issuance/durable clocks remain distinct. Use strict T-60 and actual UTC clocks.
- Missing roles, players, sources or target rows remain unknown; only an explicit valid zero is zero. Rookies receive no quality penalty. Stable identity, same game/team/opponent and unique joins are required.
- Optional study failure must not suppress grading/publication; expose its own failure. Saved cohort choice is determined before outcomes and frozen once selected. No replacement of an invalid selected cohort with a nicer older archive.
- Source/config activation is an explicit operator step. Capturing/reviewing a draft does not publish or mutate a prediction. Keep current Rush authority unchanged while testing the new command.
- Root owns `pgo_season.py`, `pgo_season_view.py`, workflow/alerts/status/publication integration and their existing tests. Other tasks own the files listed in their briefs. No agent commits/pushes or performs live capture without root coordination.

## Task 1: Visible starter update (root)
- [x] Add a compact dated link beside the affected matchup when `starter_announcements` is present; use original forecast `issued_at` for "Starter updated", retain distinct source-capture clock inside explanation.
- [x] Link to an ID on the existing native explanation disclosure and reuse the existing disclosure-opening/deep-link behavior. No new JavaScript layer, duplicate IDs, or before/after numerical inference.
- [x] Add a focused view regression proving valid anchor, correct clock, escaped values, absence on unchanged games, and original input immutability. Run `python -m unittest tests.test_pgo_season_view` then desktop/390px public or staged checks.

## Task 2: Repeatable reviewed starter capture
- [x] Own new `pgo_starter_capture.py`, `tests/test_pgo_starter_capture.py`, `docs/pgo-starter-updates.md`; only narrowly reuse/extract primary-article parsing in `pgo_expected_starters.py` if needed while preserving archived verification.
- [x] Provide documented capture, review and activation steps. Capture accepts one explicit official club-news URL, current game ID, team, stable QB ID and exact announcement statement. Resolve game/current roster through verified saved state and existing source readers. Validate URL before request; prevent unapproved redirects from being followed. Preserve exact response bytes, status, headers and real start/completion timestamps in an exclusive draft, including unsuccessful receipts. No activation on capture failure.
- [x] A later explicit review validates the saved primary article, matchup, dates and exact player statement; record actual review time. Use `select_player` and `_announcement` for final identity/evidence admission. Produce the existing immutable source envelope/reference shape; never backdate review/capture.
- [x] Activation revalidates against current state/current active roster and actual clock, detects config drift/conflicting same-game/team entries, uses atomic config write, and adds only the reviewed game entry. No direct forecast refresh, fitting, push or publish. Refuse T-60 or later, missing/tampered/future/wrong-game evidence and unsafe paths.
- [x] Test the real archived Falcons HTML offline using mocked external request/clock seams: valid capture/review/activation, preflight URL refusal, redirect/error retention, duplicate/conflict/config drift, stale roster, tamper and crossed cutoff. Existing `tests.test_pgo_expected_starters` and `tests.test_pgo_starter_revision` must retain their behavior. Write tests first and report observed red/green.

## Task 3: Offensive non-QB inventory and usage observation
- [x] Own new `pgo_offensive_inventory.py`, `pgo_offensive_usage_monitor.py`, their dedicated test files, and `research/pgo_offensive_usage_20260912/charter.md` plus README. Shared private helpers may be imported; propose any edit to an existing other-owned module before making it.
- [x] Declare future-only descriptive grain game/team/GSIS; RB/FB/WR/TE and offensive-line provider positions, excluding QB and special teams. Include roster ACT/RES/DEV/EXE/INA with the actual status retained as context. The source's roster status alone is not an injury diagnosis. Capture current role/depth, official availability and explicit missingness using verified archived roster/depth/availability bytes and current source-maintenance outputs. Require source age <=24h, preserve provider depth clock, exact source hashes, all32 team coverage and unique identities. No manufactured past membership or prior-quality value.
- [x] API `capture(state, root, checked_at)` returns detached offensive inventory (version1) with `status`, `generated_at`, `sources`, `games`, `teams`, `forecast_adjustment=None`. Root stores under `offensive_inventory` before invoking usage monitor.
- [x] API `refresh_shadow(state, previous, root, checked_at)` returns optional result under `offensive_usage`, with `status`, `blocked_reason`, `coverage_scope`, `selected_games`, pending/excluded games, `metrics`, evidence refs, `forecast_adjustment=None`, `predictive_status='UNAVAILABLE'`. Select latest actual durable pre-T60 offensive inventory per verified final; verify/replay chosen source. Preserve prior exclusions and selected pointers.
- [x] Reuse the existing nflverse snap target source/receipt acquisition where valid to avoid duplicate downloads. Require `offense_snaps`, actual source capture after verified final, strict PFR-to-GSIS game/team/opponent joins, duplicate detection before missing-value filtering, and explicit unknown vs zero. Preserve targets, failures, cohort and report bytes. Current two completed openers lack this inventory and remain excluded.
- [x] Add focused end-to-end offline tests for capture/replay, delayed finals/targets, roster identity/team moves, missing/zero/duplicate/malformed targets, exact T60 and durable crossing, preserved selected cohorts/exclusions, optional failure, and zero mutation of main/defensive records. Test against actual archived roster/depth in a bounded offline replay. Send root exact summary shape for UI and integration.

## Task 4: Future score-error calibration collection
- [x] Own new `pgo_score_range_monitor.py`, `tests/test_pgo_score_range_monitor.py`, `research/pgo_score_ranges_20260912_collection/charter.md` and README. Leave the September11 charter/attempt untouched.
- [x] Declare a collection-only phase before execution. Reuse the existing 80-percent residual recipe/minimums as context; do not issue ranges, fit a model, shorten two complete calibration seasons/500 games or claim acceptance. A later evaluation still requires its predeclared protocol/criteria.
- [x] API `refresh_shadow(state, previous, root, checked_at)` returns `score_range_collection` with actual collection/version/recipe identifiers, verified source and forecast references, per-game calibration observations, eligibility/exclusions, complete/partial-season counts, `forecast_adjustment=None`, `predictive_status='UNAVAILABLE'`, numeric ranges absent/null. Read verified previously durable archives; capture future eligible picks with actual collector clock before T60. Keep original model issue/input clocks separately. Record source/code/model identity adequate to distinguish changed forecasting recipes.
- [x] Freeze the selected pregame record by cutoff, retaining earlier revisions/evidence. Save final/error only after exact final-source replay; no latest hindsight roster/forecast substitute. Late or unavailable captures and the two completed games remain explicitly excluded. Do not count repeated snapshots or both team perspectives twice. Different model recipes cannot silently pool as one calibration series. Full-season qualification requires actual eligible schedule coverage, not reaching a row count alone.
- [x] Validate source pins/clocks, exact forecast identity/numerics and durable original archive before admission; preserve the chosen original pregame data and reject changed evidence/results. Handle T60 crossed during actual durable saving with a root integration check, rather than trusting a stale start time.
- [x] Tests: future-only admission; eligibility at/crossing T60; capture before kickoff but after cutoff; pending then verified final; missing/future source clocks; source/forecast tamper; repeated revisions; no after-lock substitution; duplicate games; incomplete seasons/500 rows; recipe mismatch; unchanged production forecasts. No live fetch or state publication by the task agent.

## Integration and release (root)
- [x] Integrate optional operations in dependency order with dedicated status/alert handling and plain-language displays. Preserve old monitor semantics. Add any needed durable validation in save/load/archive readers with meaningful regression.
- [x] Pin source/test/charter byte behavior; add tests to scheduled gate and new paths to tested-publication rules only as needed. Update operations docs in this release, including exact completed evidence rather than deferring a closure-only push.
- [ ] Review each task and full diff independently, fix substantive findings, run affected tests and the exact scheduled gate. Full canonical Python3.12 suite is the release gate.
- [ ] Publish through existing authorized main/Pages workflow, coordinate with the single writer; perform one normal refresh to capture actual future offensive and score-error observations. Check exact public bytes, desktop/phone update-link behavior, archive/source replay, unchanged all16 forecast values/allocations and both locked games/results/ATS.
- [ ] Record actual collection counts and missingness, never describe successful software execution as validated injury effects or reliable outcome ranges. Keep the worktree clean and publish a concise completion report.

## Verification notes before publication

- Root view and health/integration checks pass. The unchanged shared fragment handler opens the new starter disclosure by click and Enter; the 390px viewport has a 375px document width.
- First exact scheduled gate: 316 tests passed in 67.678 seconds. Independent review then identified additional scientific-custody cases; final gate follows those repairs.
- No source activation, forecast rewrite or live collection has been performed in implementation tests. The current starter configuration and frozen historical study bytes remain unchanged.

- Final independent reviews passed for all four tasks. Repairs cover concurrent starter activation, failed-response custody, stale roster/cutoff handling, conflicting offensive roles, no fallback from a damaged latest inventory, dependency recipe identity, and persistent exclusions. Current candidate collection replay:14future games,2excluded openers; no numerical adjustments/ranges.

- Final exact scheduled gate passed:320tests in61.141seconds after all review fixes. Canonical full Python3.12 CI and live publication checks follow this source commit.
