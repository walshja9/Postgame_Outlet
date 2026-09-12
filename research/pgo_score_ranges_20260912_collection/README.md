# Future score-error collection

This collects evidence for possible later outcome ranges. **Numerical ranges
and predictive qualification remain unavailable.** It changes no forecast,
confidence allocation, sportsbook comparison, model weight or accepted result.
The [collection charter](charter.md) is separate from the unchanged
[September 11 range study](../pgo_score_ranges_20260911/README.md).

`pgo_score_range_monitor.refresh_shadow(state, previous, root, checked_at)` reads
the actual current durable archive and verifies its manifest, forecast, source
pins, availability and original clocks. The passed clock is the real season
refresh check time. A forecast newly changed during that refresh waits until
its first actual archive exists. Unchanged snapshots are not extra observations.
Revisions collected before T-60 are retained, with the latest eligible observed
forecast selected; selection cannot change at or after that deadline.
If a collected forecast becomes unavailable before the deadline, its old
observation remains archived but its selection is cleared. That exclusion
remains explicit after T-60; a later refresh cannot restore the old selection.

The first collected observation is pending its own durable receipt. On a later
refresh, the collector verifies the hash-linked archive that actually stored
that observation before T-60 and retains its pointer. An older forecast archive
alone does not prove that the new collection was timely. The season writer also
checks the actual write time: if the optional collection crosses T-60, it keeps
the prior collection, reports that failure, and rechecks the remaining primary
save boundaries. It does not backfill completed games.

After an exact replay of the first accepted provider FINAL response, the selected
forecast receives margin and combined-points errors. Signed error is prediction
minus actual; absolute error is stored separately. Missing, conflicting or
unverified targets remain unavailable. Changed original evidence blocks this
collector rather than selecting a different past record.

`score_range_collection.metrics` reports recorded observations, selected games,
eligible games with durable collection receipts, finalized games, pending
receipts, and complete/partial seasons for each recipe. Producer code and frozen
model identities separate cohorts conservatively. Dependency hashes checked at
collection are explicitly distinct from proof of original code execution.
The recipe pins the weekly model, current QB-history helper, corrected scorer,
score splitter, source normalization, model constants, exposure features and
pinned postseason feature constructor. Later helper edits change new recipe
identities; unchanged forecast observations retain their original receipts.

A complete calibration season requires verified coverage of every game in its
preserved full regular-season schedule under one recipe. Repeated snapshots,
500 rows spread across partial seasons, or different recipes do not meet that
requirement. The two completed 2026 openers are excluded, so 2026 cannot become
a fully covered calibration season under this collection.

The September 11 context still requires two full calibration seasons and at
least 500 games, followed by a separately declared evaluation. This collector
does not issue 80-percent ranges, shorten those requirements, evaluate coverage,
claim exchangeability, or authorize promotion. `ranges` and `forecast_adjustment`
are null, `predictive_status` is UNAVAILABLE, and `eligible_for_ranges` is false.

Focused checks, using disposable local archives and no network:

```powershell
python -B -m unittest tests.test_pgo_score_range_monitor -v
```

No separate live capture command is provided. The existing season updater owns
ordinary collection and durable publication; the monitor only reads its inputs
and returns an optional payload.
