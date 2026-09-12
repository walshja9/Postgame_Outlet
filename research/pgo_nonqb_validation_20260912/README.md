# Non-QB injury validation — September 12, 2026

**Source admission is incomplete. No numerical injury adjustment has qualified
for PGO forecasts.** The audit and automatic participation checks are separate
from a test of prediction accuracy.

## What the audit found

The [new source audit](report01/source-admission.json) verifies 13 pinned injury
files covering 68,274 regular-season records and the 6,814 corresponding completed
team-game schedule entries. Every season is retained in the report.

- All **5,477 offensive/defensive non-QB injury records from 2025 lack update
  timestamps**. Another 82 non-QB records are special teams and excluded from the
  proposed offensive/defensive adjustment. The absence of clocks prevents a check
  of what was known before kickoff minus 60 minutes; it does not mean no injuries.
- Earlier offensive/defensive non-QB records include 25 at or after that deadline
  and 16 without a matching completed game in this schedule. Those records cannot
  pass the timing gate. A timestamp on an older row still does not prove which
  historical file version was available then. Complete team-report coverage is unknown.
- The original identity source remains STOP. A separately qualified corrected
  package resolves the identified conflicts: 219 roster corrections, zero remaining
  conflicts across 310,475 compared regular-season snap rows. Its PASS covers
  **identity only**. The 8,461 unresolved snap rows remain unknown. The 16 ambiguous
  Cincinnati snap rows were not forced into a match. That repair does not supply missing clocks.

The earlier [availability diagnostic](../pgo_nonqb_availability_20260909/diagnostic-20260909/README.md)
has 2,127 games. We verified its saved manifest and independently recomputed its
aggregate errors without refitting:

| Saved comparison | Average absolute margin error |
|---|---:|
| With the old availability terms | 10.0995 points |
| With those observed terms set to zero | 10.0974 points |

The estimated gain is −0.0020 points, with the preserved 95% season-block interval
[−0.0086, +0.0034]; four of eight seasons improve. This gives no demonstrated lift.
It also includes historical quarterback losses and guessed participation probabilities,
so it cannot answer the isolated non-QB question. These reused seasons are diagnostic,
not fresh confirmation evidence. No new fit or weight search was run.

## Fresh playing-time evidence

The actual [September 12 target receipt](../pgo_injury_usage_20260911/source02/receipt.json)
was captured at 16:49:24 UTC: HTTP 200, 16,543 bytes, 187 rows covering NE–SEA and
SF–LAR. The original [unavailable-player cohort replay](../pgo_injury_usage_20260911/report03/admission.json)
still admits **0 of 14 eligible final-game player rows**. SF–LAR is now in the file,
but the absent defenders from that saved cohort have no matching rows. We do not
turn omitted players into observed zero usage.

The separate [full-inventory replay](../pgo_defender_inventory_20260911/report02/admission.json)
contains 1,050 player-game rows across 14 upcoming games. All await finals; 324 lack
prior playing-time history and all 1,050 have unknown official availability in that
selected pregame edition. The two completed openers precede eligible full inventories
and are excluded. Later injury reports do not change this archived observation.

The snap source defines offensive, defensive and special-team play counts separately;
these are playing-time observations, not player-quality or replacement grades.
See the [provider's snap dictionary](https://nflreadr.nflverse.com/articles/dictionary_snap_counts.html)
and [injury timestamp definition](https://nflreadr.nflverse.com/articles/dictionary_injuries.html).

## What now runs automatically

The season updater calls `pgo_injury_usage_monitor.refresh_shadow` independently
of the main predictions. For each verified final, it selects the latest original,
versioned full defender inventory durably saved before T-60, then freezes that
pointer. The selected archive must reproduce from its preserved sources. An invalid
selected capture blocks the check; it does not cause fallback to an easier cohort.

When such a completed cohort exists, the monitor captures the actual snap response
at most once per 24 hours, with an additional check when a newly eligible final was
observed after the previous attempt. Failed requests remain recorded and throttled.
Source bytes, clocks, cohort pointers, player-level exclusions and reports stay
under `docs/evidence/season-2026/injury-usage/` in immutable artifacts. A changed
source creates a new report; old reports remain auditable. The public summary shows
distinct games and rows, explicit positive/zero usage, missing targets and exclusions.

This automated cohort covers **defenders only**. It checks whether we can follow
the players from a pregame list into a postgame file. It does not measure the
point value of an absence, identify who replaced whom, cover every offensive injury,
or automatically change model weights. Main forecasts, confidence allocations,
locked sportsbook lines and accepted results retain their original records.

## The next numerical gate

A prior-usage-only injury test does not require historical depth charts. It does
require qualified report timing, identity, role and missingness rules for both
offense and defense. Depth and replacement-quality claims need additional evidence.
The current September 8 scenario coefficients must not be transplanted into the
current postseason-based weekly model.

The [locked charter](charter.md) calls for a separate, fixed two-input absence-burden
candidate against the corresponding PGO baseline on identical chronological games,
with margin error and every season/early-season slice reported. Before prospective
scoring, the candidate, endpoint, practical improvement threshold and sample rule
must be frozen. Team rank movement is not a success criterion. We will not fill
missing histories with zero quality or invent point deductions to force a ranking.

## Reproduce the checks

```powershell
python research/pgo_nonqb_validation_20260912/audit_sources.py --self-check
python research/pgo_nonqb_validation_20260912/audit_sources.py --output research/pgo_nonqb_validation_20260912/report02
python -m unittest tests.test_pgo_injury_usage_monitor tests.test_pgo_injury_usage tests.test_pgo_defender_inventory
```

Use a new output directory for every audit. The source audit reads the exact pinned
local historical cache paths recorded in earlier receipts; it does not download
replacement files if those inputs are missing. Its report and receipt preserve
source/code/charter hashes. The automatic monitor uses archived season evidence
and has no dependency on that local historical cache. The existing inventory CLI's
relative-path failure and successful repair are recorded separately in its study.
