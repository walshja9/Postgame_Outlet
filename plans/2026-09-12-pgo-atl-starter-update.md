# Atlanta expected-starter update release record

> COMPLETE AND PUBLISHED September 12, 2026. The official Cooper Rush starter update passed offline, production, repeated-refresh, public-byte and browser checks. The starting-state notes below are retained as historical evidence; final publication and CI results are recorded at the end.

**Goal:** Admit a dated, official starter announcement into the existing pre-lock QB revision path while preserving issued forecasts and fixed confidence points.

**Architecture:** Keep the existing roster identities, frozen model and revision/archive machinery. Add only an evidence-backed, game-scoped expected-QB selection before availability capture and model evaluation; persist its authority through repeated pre-lock refreshes.

**Tech stack:** Existing Python standard-library season updater and immutable JSON/source archives; no new dependency or fitted weight.

## Starting state and lock boundary

At inspected code `fd3abeefeef4328736df46c4adc963f55dc2663a`, ATL-PIT is safely held: `pick=null`, `confidence=null`, `blocked_by_availability=true`, and `withheld_confidence.points=4`. The saved expected ATL QB remains Tua Tagovailoa, whom the archived official report marks OUT. The previous margin and its original issue time remain in the archived record. This is not a resolved starter update.

Game `2026_01_ATL_PIT` kicks off September 13, 2026 at **17:00 UTC / 1:00 PM EDT**. Any changed forecast must be durably saved **strictly before 16:00 UTC / noon EDT**, including the final save-time check. A late announcement or failed update must not rewrite the locked forecast.

This follow-up is separate from the September 12 non-QB validation release, whose implementation, evidence work and full CI verification are complete (Update board run 34707613897: 955 passed, one skipped). No numerical non-QB adjustment, new fit, manual point spread or forecast change was made for this handoff.

## Evidence to preserve

The [official Falcons announcement](https://www.atlantafalcons.com/news/tua-tagovailoa-cooper-rush-michael-penix-jr-state-of-qb-atlanta), by Tori McElhaney, displays **September 11, 2026 at 2:12 PM**. It identifies Cooper Rush as the starter against Pittsburgh, Jack Strand as his backup, and Tua Tagovailoa and Michael Penix Jr. as unavailable. The rendered time does not state a timezone. The page was reviewed on September 12; this browser review is not a pinned production source capture. Preserve actual response bytes, URL, hash and real capture clock before using it as selection authority; do not backdate the capture to the article's displayed date.

All following paths are relative to `docs/evidence/season-2026/`:

| Evidence | Exact path and raw SHA-256 | Bytes / clock |
|---|---|---|
| Inspected state manifest | `runs-v2/20260912T171537323255Z/manifest.json`; `39db6d8767b9840c37ba8c805f99f7c75247e599e75a80392b4066ccd8cba5aa` | 840 bytes; state checked 2026-09-12T17:15:37.323255Z |
| Active roster | `source-archive/49de6434fb4ec3d13abb7de9906bf931fb35ea4fcb2e7ac357ca8e1d3e3d6e92.csv.gz`; SHA is the filename stem | 362,154 bytes; captured 2026-09-12T17:15:10.927163Z |
| Provider depth | `source-archive/ec813944a0d2c60ba9362bd066fc56ce135de0c2df793b170c5f22ea241bd744.csv.gz`; SHA is the filename stem | 10,031,927 bytes; captured 2026-09-12T17:15:11.101149Z |

The associated state is `runs-v2/20260912T171537323255Z/state.json.gz`, pinned by that manifest. Its availability archive is `availability-v2/20260912T171510827155Z/`.

The roster identifies **Cooper Rush: ATL, QB, ACT, season 2026, week 1, GSIS `00-0033662`, PFR `RushCo00`**. Its latest depth edition, `2026-09-12T11:36:06Z`, still ranks Tua (`00-0036212`) first, Penix (`00-0039917`) second, Rush third and Strand (`00-0041194`) fourth. A pure replay of `select_roster` on those bytes returns Tua. Refreshing identical bytes cannot resolve the discrepancy.

## Smallest existing integration points

- `pgo_season.py:423`, `select_roster(roster, depth, captured_at)`, selects only active roster QBs joined to the latest rank-one depth rows, with unique coverage of all 32 teams. There is no dated/manual override argument or supported CLI setting. `data/qb_depth.csv` belongs to the separate McCabe board.
- `pgo_season.py:590`, `refresh_forecast_availability(state, root)`, is the narrow integration point: apply verified game-scoped selection after normal roster selection and before `capture_availability`. The selected identity must drive both the availability gate and model evaluation. Reject wrong team/game/season, inactive or non-QB identity, conflicting announcements, missing source pins, future clocks and expired authority. Keep raw roster/depth unchanged.
- Reuse `build_next(..., completed=state['rankings']['completed_week'], selected=selected, roster_sources=refs)`. For Week 1, `completed=0` uses the saved seed/history/fit without fetching new team/player performance. Pin the starter authority among the edition sources. Do not transplant opening-night qualification files or human QB grades.
- Existing lines 613-616 restore points from `old.confidence` **or** `old.withheld_confidence` and recalculate expected pool points with the new win probability. `revise_game` checks identity/clocks; preservation comes from `refresh`'s archive chain and `save_state`'s exclusive files and durable-write gate. The same reviewed selection must survive the next refresh and expire for the next game/week.

## Required replay and preservation checks

- [x] Start with an offline fixture of this blocked ATL game and the pinned roster/depth. Prove current selection returns Tua; a verified same-game announcement selects Rush without changing either source file.
- [x] Exercise the real selection, `refresh_forecast_availability`, saved-fit `build_next`, and `save_state` path with only external fetching mocked. Confirm Rush appears consistently in rankings, game explanation and availability identity; an OUT designation for Rush must still hold the pick.
- [x] Confirm restored confidence remains exactly **4**, with `expected_points = 4 * win_probability`; do not reallocate other fixed points. Retain other games' availability blocks, accepted results and locked sportsbook lines. Compare unaffected games' numerical values, allowing expected edition metadata and centered-board changes.
- [x] Repeat with unchanged provider depth to prove no reversion to Tua. Reject missing/conflicting/tampered evidence, wrong roster identity, future timestamps and a Week 2 reuse of this Week 1 announcement.
- [x] Cross T-60 during evaluation and during durable saving: preserve the complete old game and source/QB identity. Verify original state/source/manifest hashes and the prior archive pointer remain intact after a successful pre-lock update.
- [x] Extend `tests/test_pgo_season_boundaries.py` (existing QB preservation test mocks selection and rebuilding) with the real blocked-to-supported-QB recovery path; add focused selection fixtures if needed. Run `python -m unittest tests.test_pgo_season_boundaries tests.test_pgo_season_availability tests.test_pgo_season`, then the scheduled gate and independent review before any operational refresh/publication.

Implementation, offline replay, operational publication and issued-forecast verification are complete. Offline fixture values remain diagnostic; the actual public forecast is recorded below.


## September 12 implementation evidence

The official announcement has now been captured and reviewed. JSON-LD dates are published `2026-09-11T18:12:22.097Z` and modified `2026-09-11T18:30:49.99Z`. Actual response capture is `2026-09-12T17:48:48.402488+00:00`; review is `2026-09-12T17:50:56.932245+00:00`. HTTP 200 returned the identical official URL. Raw HTML is 623,012 bytes, SHA-256 `66c9eab491409329a2901309645532976f9a23fffab1606fce535fd3e5171866`. The immutable envelope is `source-archive/08e9cb25040d8852f92854213db350cfef036763f4beaa2c3967bc4287367976.json`, 832,676 bytes, SHA-256 equal to its filename stem.

`pgo_expected_starters.py` validates the captured primary article, decision-time clocks, matchup, exact source bytes and current active roster identity. The normal pre-lock refresh uses that selection for both the frozen model and availability capture. Original announcement evidence remains verifiable in current and archived states. Later same-week board revisions and post-lock context retain the issued starter; next-week selection requires fresh authority. The durable T-60 guard covers announcement changes too.

The implementation also fixes a shared-list alias in revision source captures: display links appended to the returned list must not contaminate raw edition-source references. No fitted model, performance inputs, confidence allocation, non-QB weights or original archive is replaced. The game explanation links the official article and saved source evidence in plain language.

The existing model ages QB history using the elapsed calendar time (365.25-day half-life). A September 12 Tua control isolates this behavior from the starter substitution: changing only ATL to Rush produces exactly zero change to other games. Rebuilding on September 12 instead of September 9 changes other draft margins by at most 0.00798961747 points in the offline fixture. This is existing model behavior, not a new weight or injury adjustment.

Independent code review: SPEC PASS and QUALITY PASS, closed after verifying the final test receipt and file hashes. Four real integration regressions passed in 44.547 seconds. The exact scheduled workflow gate passed all 269 tests in 57.039 seconds (`output/atl-starter-20260912/scheduled-gate-01.log`). Local artifacts, including earlier failed checks, are retained under `output/atl-starter-20260912/` and `output/atl-starter-update-20260912/`. Offline fixture forecasts are diagnostic, not issued public forecasts.

Publication used the existing GitHub main/Pages workflow. Canonical CI and live archive checks passed for the published source commit; details follow.


## Published forecast and verification

Source release: `0507f78058e5635eb60deddf1703f9d2061d94c9`. Normal season run `34710601005` passed all 269 tests in 46.244 seconds and published `f1c7de432f9348035bc6048aaad1d832fe1682df`. Its primary state is READY; weekly rollover is correctly WAITING for the remaining games.

The issued ATL-PIT forecast is saved at `2026-09-12T18:15:59.179079+00:00`, before Sunday's `16:00 UTC` lock. Expected ATL quarterback is Cooper Rush. Pittsburgh is favored by 4.828082411 points; score averages are PIT 24.891165388 and ATL 20.063082978. The straight-up chance is 65.614328%; confidence remains 4 points, with 2.624573127 expected pool points. The current saved sportsbook comparison is PIT -6 / ATL +6; PGO's ATS suggestion is ATL +6, an approximately 1.17-point difference from that line. These remain experimental forecasts, not claims of proven accuracy.

Read-only production verification (`output/atl-starter-20260912/production-receipt01.json`) passed current/archive/source replay, original archive byte preservation, both locked games, accepted results, locked ATS entries and all 16 fixed confidence allocations (136 points). The saved-fit same-clock Tua control favors PIT by 1.124782626; unaffected draft scores differ by at most 5.55e-17, ordinary floating-point precision. No source fetch, forecast save or new fit occurred in this verification.

The published board, Forecast Lab and stylesheet returned HTTP 200 and matched the publisher's exact bytes (`public-f1c7de432f93.json`). Browser review confirmed the Shopify embed, revised game row, source-linked plain-language starter explanation, readable desktop and 390x844 phone layout, and no horizontal overflow; the temporary viewport was reset. Evidence: `browser-review01.json` in the same output directory.

Canonical full CI `34710594897` completed successfully. Discovery ran 945 tests in 730.591 seconds with one skipped; the two candidate suites each passed 14 tests (0.049 and 0.002 seconds). Total: 973 tests, 972 passed and one skipped. Exact tested source is `0507f78058e5635eb60deddf1703f9d2061d94c9`.


The next natural scheduled run `34710953537` also succeeded: 269 tests passed in 41.463 seconds, publishing `3df1e098dbbe78cc379f264adbbb7a24f1f654d9`. Its archive remains READY and preserves all 16 games' QB identities, starter annotations, original issuance clocks, score/margin/picks and confidence values from the first Rush publication. This verifies actual repeated-refresh persistence. The newly deployed board, Forecast Lab and stylesheet again matched that commit's bytes (`public-3df1e098dbbe.json`). The public raw GitHub manifest, state and announcement files returned HTTP 200 with exact expected hashes (`public-evidence01.json`); these are the archive destinations used by the rendered site links.


The full workflow's publication guard admitted only tested source plus newer mutable data at `3df1e098dbbe78cc379f264adbbb7a24f1f654d9`, then successfully published `13e6b5a9b3f62637e9f90b80a2da1470655ee864`. The final public board, Forecast Lab and stylesheet again matched that commit exactly at `2026-09-12T18:31:04.230746+00:00` (`public-13e6b5a9b3f6.json`). Final page publication changed only the rendered board; issued forecast archives were unchanged. The complete CI log is retained as `ci-board-log-20260912T183005003217Z.txt` in the local evidence directory.

Closure: all required work is complete. Normal availability refresh, T-60 locks, postgame grading, weekly rollover and immutable archives continue through the existing workflow. Non-QB injuries remain contextual while the already-published prospective validation monitor accumulates eligible evidence; no unvalidated non-QB numerical adjustment was admitted in this release.
