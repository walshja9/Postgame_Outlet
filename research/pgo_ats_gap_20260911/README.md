# Saved sportsbook benchmark and ATS gap monitoring

This is descriptive monitoring. It does not change PGO predictions, sportsbook
quotes, ATS suggestions, model weights or grades. No minimum gap has been
validated. Prospective research status remains **UNAVAILABLE**.

The [frozen charter](charter.md) defines one game per row, matching forecasts and
quotes issued before kickoff minus 60 minutes, exact signed-home arithmetic,
common-game margin error, separate winner/no-pick/tie records, and fixed ATS gap
bands. [The freeze receipt](charter-lock.json) is a local clock and hash, not a
prior public publication witness.

The initial [summary](attempt01/summary.json) uses 16 saved Week 1 forecasts.
Only SF–LAR has both a valid saved quote and a final result. PGO's average margin
error is 24.2660544984 points; DraftKings' is 23.5, a difference of +0.7660544984
points (PGO minus book). Both straight-up selections lost. The ATS suggestion
also lost. Fourteen games are pending, and NE–SEA has no saved pre-lock quote.
One completed comparison cannot establish which forecast is stronger.

The [initial receipt](attempt01/receipt.json), [completion](attempt01/completion.json)
and [manifest](attempt01/manifest.json) pin the exact archived state and source
files. The report replayed each quoted ESPN response and explicit FINAL result
against the saved values, and checked that inputs remained unchanged. Exact
executed code and test copies are retained in [implementation01](implementation01/manifest.json).
They preserve this attempt if production code is later repaired; the initial
output must not be overwritten.

Attempt 01 verified the current pointer's manifest hash while selecting its
archive, but did not retain the pointer's exact bytes or hash. Its archived
state/source pins remain intact; the original pointer custody evidence is
unavailable and cannot be reconstructed after the fact. This limitation is
preserved with the original attempt and implementation.

New attempts selected from the current pointer retain its exact `current.json`
bytes and hash in the output. Explicit `--archive` replays record pointer
provenance as `UNAVAILABLE`, because they do not select through a current pointer.

Run a new attempt from the current verified pointer:

```powershell
python research/pgo_ats_gap_20260911/report.py --output research/pgo_ats_gap_20260911/attempt02
```

For the same archived cohort, add `--archive` with the `archive` path recorded in
the initial receipt. The command verifies that archive's manifest/state pin and
replays source bytes. Each output directory must be new. A later changed
implementation is a new diagnostic, not a rewrite of the original result.

Focused checks:

```powershell
python -m unittest tests.test_pgo_market_benchmark tests.test_pgo_ats tests.test_pgo_season_accuracy
```

`pgo_market_benchmark.summarize(state)` is the pure production interface. The
caller normally passes `pgo_season.load_current()` output, which verifies source
hashes. The summary rechecks schedule/forecast/quote/final identities, timing and
arithmetic, recomputes grades, and excludes a retained quote whose PGO basis no
longer matches the saved weekly forecast. Structural duplicate or unknown game
IDs raise `ValueError`; individual exclusions use documented `reason_labels`.

All rows remain descriptive, including games arriving after this file appears.
A separate witnessed protocol and explicit admission process would be required
to change that status. No profitability or closing-line claim is made.
