# Named defenders and observed playing time

**DESCRIPTIVE / NOT IN MODEL.** This extension saves the identities already
constructed by the defensive-depth capture, including listed starters, backups,
unlisted players and reserve/practice-squad context. Rookies and missing histories
remain unknown. A listed backup is not necessarily the actual replacement;
defensive snaps do not establish assignment, talent or causal injury impact.

The [original protocol](charter.md) and [September 12 version 2 addendum](inventory-v2-addendum.md)
apply only to newly saved, versioned inventories. Existing forecasts, injury values and model weights do not change.
Earlier captures without this inventory cannot be backfilled or admitted.

## Capture contract

`research.pgo_replacement_depth_20260910.capture.capture(state, root, checked_at)`
retains the compatibility default `inventory_version: 1`; each team has the same version and
a `defenders` list. These are the exact already constructed player records.
Existing `unavailable_players`, role summaries and prior-usage subtotals remain
unchanged. A player listed in several provider positions occurs once, retaining
all of those roles. Unresolved roster identities remain separately visible in
`unresolved_roster`; the inventory does not invent their identities.

The scheduled writer explicitly passes `inventory_version=2` for new captures.
Version 2 also retains roster rows marked `INA`, their supplied season/week/game
type context, and a separate `inactive_roster_defenders` team count. A roster
label can describe a prior game: it does not establish an injury or automatically
mark a player unavailable for the next game. Version 1 omitted these rows; its
saved membership and counts remain unchanged. Readers reproduce each known
version with its own rules and reject unsupported versions.

The season writer retains source archives and enforces durable saving before
T-60. A newly generated preview is not a previously published pregame inventory.

## Usage reader

`inventory.link(snapshot, roster, snaps, finals, target_captured_at)` uses the
unchanged September 11 injury usage join through a detached copy, with the full
inventory replacing its unavailable-player cohort only inside that copy. It
retains strict game/team/opponent/PFR-to-GSIS identity, timing, duplicate and
missing-value checks. Duplicate player identities or a changed unavailable subset
are rejected. A game missing either team's versioned inventory has no admitted
player rows and appears in `unavailable_inventory_games`.

The result retains existing admission fields and adds `observed_zero`,
`observed_positive`, `pending`, `missing_target` and `unavailable_inventory_games`.
`pending` counts player rows without verified finals; `missing_target` counts
rows without a matching target after a final exists. Other invalidity reasons
may overlap these counts and remain explicit in `exclusions`. Zero is reported
only for an admitted source row containing zero. Adjustment remains null and
prospective predictive status remains UNAVAILABLE.

The CLI verifies an exact pregame season pointer/manifest/state, reproduces new
inventories from their archived roster/depth/availability/history sources, and
uses the archive's durable creation clock. It separately verifies and replays
current final-source bytes. Snap source folders use the existing injury usage
receipt format (`response.bin`, `receipt.json`, source URL, actual start/capture
clocks, HTTP status, byte count and SHA-256). Failed HTTP retrieval is preserved
as no target rows; missing or malformed 200-response schemas are rejected.

From the repository root:

```powershell
python -m research.pgo_defender_inventory_20260911.inventory --pregame-pointer <saved-pregame-pointer.json> --source <preserved-snap-source-folder> --output research/pgo_defender_inventory_20260911/report01
python -m unittest tests.test_pgo_defender_inventory tests.test_pgo_replacement_depth tests.test_pgo_injury_usage
```

Output directories must be new. Each report preserves both selected pointers,
the target receipt and code/test/protocol pins. Do not overwrite a report to
hide late clocks, missing source coverage or an unfavorable result.

## Readiness at implementation

A read-only preview of the verified current sources constructed 1,194 resolved
defender records for 32 teams and 14 future games. Removing only the new version
and inventory fields reproduced the prior implementation's complete output
exactly; the input season state remained unchanged. This preview was not saved
as pregame evidence and creates no admitted target links.

No fresh target download was needed: the two completed games precede the new
inventory schema and cannot be admitted. New scheduled season captures will
save the inventories for eligible future games. After those games finish, retain
a new actual snap-source response and run a new report against the original
pregame pointer. This is data collection for later testing, not a fitted injury
model or evidence of improved predictions.

## September 12 replay

`pregame-pointer01.json` selects the original September 12 16:40 UTC version 2
archive. The first relative-path CLI invocation failed before creating a report;
`attempt01-path-failure.json` retains that failure. Normalizing the source argument
before constructing receipt paths repaired the command; the existing receipt test
failed before the repair and passed afterward.

`report02` is the successful replay against injury-usage `source02`: 1,050 pending
player-game rows across 14 games, including 324 unknown prior histories and 1,050
unknown official availability observations. Neither completed opener has an eligible
full inventory, so both remain excluded; no completed player-game rows are admitted.
These counts describe this selected archive, not future injury-report coverage.

The [September 12 protocol](../pgo_nonqb_validation_20260912/charter.md) adds
automatic postgame checks using the existing readers. The latest original inventory
saved before T-60 is selected once per final game and retained. Later target releases
can supply observed playing time; they cannot rewrite that pregame cohort.
