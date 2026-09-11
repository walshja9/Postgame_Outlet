# PGO official inactive monitoring implementation plan

> **For agentic workers:** Use `subagent-driven-development` or `executing-plans` for the assigned tasks; preserve the shared file ownership and publication review.

**Goal:** Keep official inactive coverage visible through kickoff without revising any locked forecast or sportsbook record.

**Architecture:** Reuse official-source discovery and hashed availability archives. Save a separate top-level `availability_context`; render its coverage and timing independently from numerical model inputs. Reuse the canonical season workflow, shared publishing lock and saved-state health summary.

**Tech stack:** Python standard library, existing HTML renderer and GitHub Actions; no service or new dependency.

## Constraints

- T-60 remains the forecast and sportsbook cutoff. Preserve main predictions, QB assumptions, confidence points, experimental pairs, results and grades; context is not a numerical forecast input.
- Watch kickoff minus two hours through kickoff. After kickoff recover only missing lists through +6 hours, excluding verified finals. Accept only official pregame publication/modification times; identify later captures as after-lock/after-kickoff observations.
- Pregame coverage: absent complete lists are `AWAITING` before T-75 and `MISSING` within T-75; complete lists are `STALE` if the last check is over ten minutes old and otherwise `VERIFIED`. Failures must retain prior evidence and display the exact missing/stale reason.
- Retain full checks on `7,22,37,52 * * * *`; add `2,12,17,27,32,42,47,57 * * * *` ticks that skip full work outside an eligible inactive watch window. Manual runs remain full checks. Keep `board-update`, `cancel-in-progress: false`, existing tests, publication paths and Pages request. [GitHub schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) can be delayed or dropped; five minutes is a request, not a deadline guarantee.

## Implementation and checks

- [ ] **Official-source replay:** Extend `pgo_injury_source.py` discovery to NFL.com/news alongside official team sources. Replay saved raw pages in source tests: exact matchup/date/team, complete lists, player resolution, unrelated links, partial lists and missing/future/after-kickoff publication or modification times. Preserve source bytes and hashes.
- [ ] **Context and lock invariance:** Add the watcher and separate context capture to `pgo_season.py` and validate context in its state reader; add `tests/test_pgo_inactive_monitor.py`. Validate identities, capture clocks and archive hashes before accepting context. Test the two-hour, T-75, ten-minute stale, kickoff and +6-hour boundaries; missing-list recovery; verified-final stop; malformed input; retained earlier evidence; and exact equality of all locked game and experiment rows before/after refresh.
- [ ] **Visible truth:** Update `pgo_season_view.py` and its focused tests to show coverage, actual check/capture/source times, missing teams/reasons and after-lock/after-kickoff context. Escape source labels/links and preserve stable view keys. Update `pgo_workflow_status.py` and tests so missing/stale inactive coverage emits an Actions warning without blocking publication of truthful state.
- [x] **Cadence:** Update `.github/workflows/update-season.yml`, `tests/test_public_board_workflow.py` and `docs/pgo-season-operations.md`. After dependencies, capture `checked_at = now()` once and route extra ticks using `availability_watch(load_current(), checked_at)['games']`. Run full work if any watch game has `utc(game['kickoff']) > utc(checked_at)` or `game['status'] != 'VERIFIED'`; otherwise skip tests/refresh/render/publish. Base/manual ticks remain full. Add `tests.test_pgo_inactive_monitor` to the existing test command. Execute the actual routing Python with empty, pregame verified, at/after-kickoff verified, and after-kickoff missing fixtures; verify the observed clock is passed once and every expensive step is gated. Red/green: `python -m unittest tests.test_public_board_workflow`.
- [ ] **Integrated verification:** Run the exact scheduled unittest command and full board gate. Replay the captured official lists; verify all existing forecasts, confidence, sportsbook lines and experimental issuances stay unchanged. Check rendered desktop/mobile coverage and source clocks, including visible missing/stale and late-capture cases.
- [ ] **Publication:** Publish reviewed source and generated pages; verify the tested-source guard, canonical push, Pages success and public byte hashes. Observe a real scheduled run on the new source, compare locked records and archived source hashes, and retain ignored receipts. Do not infer timely capture from cron configuration or backdate recovered lists.

## Operational limit

The two recent successful scheduled jobs took [195 seconds](https://github.com/walshja9/Postgame_Outlet/actions/runs/34541416897) and [239 seconds](https://github.com/walshja9/Postgame_Outlet/actions/runs/34542062656); the latest board publisher took [138 seconds](https://github.com/walshja9/Postgame_Outlet/actions/runs/34541191979). A five-minute interval leaves 61–105 seconds of recent runtime headroom before new discovery work and queue contention. Eight extra full checks per active watch hour imply 26–32 additional runner-minutes at those durations; idle ticks only pay setup/routing cost. Keep actual freshness and queue delays visible; do not promise an exact kickoff-time check or add a persistent poller.
