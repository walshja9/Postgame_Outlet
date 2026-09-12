# Atlanta expected-starter update implementation handoff

> This is unresolved operational follow-up under the user's existing authorization for pre-kickoff refreshes and publication. Execution requires supported source evidence and verification, with the source, clock and preservation checks below. This document makes no forecast changes. Use executing-plans or subagent-driven-development to carry out the follow-up.

**Goal:** Admit a dated, official starter announcement into the existing pre-lock QB revision path while preserving issued forecasts and fixed confidence points.

**Architecture:** Keep the existing roster identities, frozen model and revision/archive machinery. Add only an evidence-backed, game-scoped expected-QB selection before availability capture and model evaluation; persist its authority through repeated pre-lock refreshes.

**Tech stack:** Existing Python standard-library season updater and immutable JSON/source archives; no new dependency or fitted weight.

## Current operational state and boundary

At inspected code `fd3abeefeef4328736df46c4adc963f55dc2663a`, ATL-PIT is safely held: `pick=null`, `confidence=null`, `blocked_by_availability=true`, and `withheld_confidence.points=4`. The saved expected ATL QB remains Tua Tagovailoa, whom the archived official report marks OUT. The previous margin and its original issue time remain in the archived record. This is not a resolved starter update.

Game `2026_01_ATL_PIT` kicks off September 13, 2026 at **17:00 UTC / 1:00 PM EDT**. Any changed forecast must be durably saved **strictly before 16:00 UTC / noon EDT**, including the final save-time check. A late announcement or failed update must not rewrite the locked forecast.

This follow-up is separate from the September 12 non-QB validation release, whose implementation and evidence work is complete subject to full CI verification. No numerical non-QB adjustment, new fit, manual point spread or forecast change was made for this handoff.

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

- [ ] Start with an offline fixture of this blocked ATL game and the pinned roster/depth. Prove current selection returns Tua; a verified same-game announcement selects Rush without changing either source file.
- [ ] Exercise the real selection, `refresh_forecast_availability`, saved-fit `build_next`, and `save_state` path with only external fetching mocked. Confirm Rush appears consistently in rankings, game explanation and availability identity; an OUT designation for Rush must still hold the pick.
- [ ] Confirm restored confidence remains exactly **4**, with `expected_points = 4 * win_probability`; do not reallocate other fixed points. Retain other games' availability blocks, accepted results and locked sportsbook lines. Compare unaffected games' numerical values, allowing expected edition metadata and centered-board changes.
- [ ] Repeat with unchanged provider depth to prove no reversion to Tua. Reject missing/conflicting/tampered evidence, wrong roster identity, future timestamps and a Week 2 reuse of this Week 1 announcement.
- [ ] Cross T-60 during evaluation and during durable saving: preserve the complete old game and source/QB identity. Verify original state/source/manifest hashes and the prior archive pointer remain intact after a successful pre-lock update.
- [ ] Extend `tests/test_pgo_season_boundaries.py` (existing QB preservation test mocks selection and rebuilding) with the real blocked-to-supported-QB recovery path; add focused selection fixtures if needed. Run `python -m unittest tests.test_pgo_season_boundaries tests.test_pgo_season_availability tests.test_pgo_season`, then the scheduled gate and independent review before any operational refresh/publication.

Until those checks and the evidence-backed selection are implemented, keep ATL-PIT held with its four allocated points preserved. This handoff contains no replacement prediction and makes no claim that Rush's forecast is ready.
