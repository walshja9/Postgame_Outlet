# Task C: prospective McCabe capture

Implemented locally on the approved isolated worktree based on `ae2dbdb14c3580208e26f83a0c5c2c999a4be3ee`. Changes remain uncommitted for review. No real refresh, network request, deployment, model fitting, numerical-source edit, historical reconstruction or tracked public-page generation was performed.

## Files and behavior

- `mccabe_forecasts.py`: optional first-game-capture collector, exact embedded input bundles, offline arithmetic/market replay, immutable preservation and durable cutoff guard.
- `pgo_season.py`: collector registration, read validation, and optional durable-write handling. Only `LateCapture` permits McCabe fallback; arbitrary integrity failures reject the new pointer. Both optional collectors are checked again after a rewrite so the rewritten clock cannot silently cross the other collector's cutoff.
- `tests/test_mccabe_forecasts.py`: 17 focused tests including invalid-input subcases, storage integration and actual archived-market parsing.
- `.github/workflows/update-season.yml`: adds only the dedicated test module to the existing verification command.
- `docs/pgo-season-operations.md`: policy, replay, first-capture semantics, preserved spread convention, unavailable-market semantics and limits.

The collector requires a current regular-season `Week N YYYY` edition matching the season's current week, 32 unique reviewed finite teams, exact selected-snapshot QB/component/total/team-metadata agreement, and a published snapshot clock no later than issuance. It never captures an old or unrelated future week, accepted final, or game at/after T-60. Later editorial input changes cannot replace a captured game.

Every game retains selected QBs and components/totals, HFA inputs, raw margin, rounded spread, edition, issue/kickoff/cutoff times and the input-bundle identity. Bundles preserve exact UTF-8 source bytes through their text plus byte length/SHA-256 for ratings, config, HFA and snapshots. Validation reconstructs these without reading today's editorial files. A changed/removed old record or bundle fails preservation.

The calculation reuses `spreads.is_primetime` and `spreads.round_half`, normalizing an aware kickoff to UTC before passing it to the UTC-hour helper. The existing HFA-at-neutral-venues convention is explicitly recorded and unchanged. `config.csv`'s workbook HFA is not substituted for `hfa.csv`.

When already captured source data passes the existing DraftKings parser, a market witness includes the exact source reference, line, provider and observed capture time. Provider publication time remains explicitly unavailable. A missing/unqualified quote produces `UNAVAILABLE`; it does not invent a line or trigger another feed.

## Red/green evidence

1. Initial `python -B -m unittest tests.test_mccabe_forecasts`: 10 test methods, 28 failures/subcase failures, all the deliberate missing-module assertion.
2. After collector implementation: the remaining failures specifically covered missing season registration, missing read/preservation validation and missing durable fallback. Adding those hooks produced 20 passing tests across the then-10 dedicated methods and the 10 existing season-experiment tests.
3. Added archived multi-game market and earlier-issue-time regressions: each failed before its fix, then passed after selecting and validating the single witnessed event from the exact full provider source and checking the new issue clock against collection time.
4. Added the equivalent-offset kickoff regression: failed with HFA 2.0 instead of 2.5; passed after UTC normalization.
5. Added writer-boundary blocked-schedule/accepted-final subcases: both failed before their explicit admission guard, then passed.
6. Added a cross-collector rewrite regression: McCabe initially passes at 15:59:59, score-range fallback forces another write at 16:00:00, and the writer then discards only new McCabe records. The third durable check at 16:00:01 preserves the old McCabe evidence and primary forecast while both optional statuses are blocked.

Final expanded approved verification command:

```text
python -B -m unittest tests.test_mccabe_forecasts tests.test_pgo_season tests.test_pgo_season_storage tests.test_pgo_season_boundaries tests.test_pgo_publication_guard tests.test_pgo_workflow_status tests.test_public_board_workflow tests.test_pgo_season_experiments tests.test_pgo_score_range_monitor
```

Result: **83 tests passed**, exit 0, 14.161 seconds. Workflow-status test messages about refresh routing and mock alert creation were expected test output; no real refresh or delivery was performed. `git diff --check` returned exit 0; Git also reported existing/autocrlf warnings for other task-owned files.

## Limits and review

Operational review follow-up: `pgo_workflow_status.py` now includes the collection in the existing Actions JSON summary and escaped warning path. `UNKNOWN`/`WAITING` stay quiet; `BLOCKED` retains its reason without changing primary `READY`. Total/current-week capture counts distinguish old retained evidence from current-week coverage. Three focused workflow tests first failed in six subcases for missing fields, then passed. `python -B -m unittest tests.test_pgo_workflow_status tests.test_mccabe_forecasts tests.test_public_board_workflow` passed **39 tests** in 1.107 seconds; scoped `git diff --check` returned 0 with only autocrlf notices. No new notification channel or real message was introduced.

This is future collection infrastructure, not an accuracy or ATS record. It has not been deployed or observed collecting a real prospective game. No new grader, probability model, public comparison table or alert channel was added. Existing historical PGO leakage work remains outside this task. Input trust is the explicitly reviewed matching human edition, not a claim that its injury or player assessment has been independently verified.

Storage round trips, no-current-file replay, exact source hashing, changed-input immutability, missing/invalid/future/NaN inputs, wrong/duplicate game identity, old/future weeks, cutoff equality/after-cutoff, crossing during durable save, preservation of older games when discarding a new late game, rehashed-but-unreplayable archive rejection, market source tampering, and optional collector failure isolation all have passing checks. Parent review and the final combined verification remain pending.
