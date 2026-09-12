# Offensive non-QB participation collection

This prospective descriptive study starts with newly saved offensive inventories.
The charter fixes its scope and exclusions; no model fit, injury weights,
replacement-quality values or forecast changes are authorized by collection.

`pgo_offensive_inventory.capture(state, root, checked_at)` returns a detached
version-1 observation. The season writer saves it as `offensive_inventory`.
Healthy status is `DESCRIPTIVE / NOT IN MODEL`; fields include `generated_at`,
`sources`, `games`, `teams[].players` and `forecast_adjustment: null`. Source
maintenance already archives roster and depth bytes; availability packages are
verified and replayed. The capture function makes no downloads or state writes.
Roster status is context, never a diagnosis. Unresolved roster identities, depth
names and official names remain explicit. Provider depth older than 24 hours is
STALE even when its source was downloaded recently.

`pgo_offensive_usage_monitor.refresh_shadow(state, previous, root, checked_at)`
returns the optional `offensive_usage` result. Run it after the defender monitor
so it can reuse that monitor's latest snap-count source receipt. It writes only
immutable target/report evidence, never season state or forecasts. Target bytes
keep the existing `injury-usage/targets/<hash>/` custody path, shared by both
monitors. Offensive reports use `offensive-usage/reports/<hash>.json`.

The result exposes `status` (WAITING, READY or BLOCKED), `blocked_reason`,
`coverage_scope`, `selected_games`, `excluded_games`, `pending_games`, `games`,
`metrics`, `source`, `last_attempt` and `report` when available. Metrics count
games, cohort rows, eligible final rows, joined rows, observed zero/positive
usage, missing targets, pending target rows, coverage and invalid/unresolved
target rows. Detailed rows and exclusion reasons are in the hashed report.
`predictive_status` is always UNAVAILABLE and `forecast_adjustment` is null.

Selection uses the latest verified archive manifest strictly before T-60.
Generation time alone never qualifies an inventory. The selected inventory is
reproduced from its pinned roster/depth/availability sources before joining
offense_snaps. An invalid chosen snapshot blocks without selecting an older one.
Saved selections and missing-inventory exclusions persist across refreshes.
Targets captured at or before the verified final are pending, not admitted.
Missing source rows never become zero; duplicate identities are counted before
filtering malformed values. PFR identities, team/opponent and supplied target
player names must agree with the saved roster.

Run the bounded offline checks from the repository root:

```
python -m unittest tests.test_pgo_offensive_inventory tests.test_pgo_offensive_usage_monitor
```

The real-data test pins the September 12 18:55 UTC archived state, verifies its
sources and availability bytes, and performs an in-memory capture. It explicitly
rejects that old archive as prospective offensive evidence because no offensive
inventory was saved there. This engineering replay neither backfills the two
completed openers nor modifies any archive. Synthetic archive/target fixtures
write only temporary directories; network requests are mocked.
