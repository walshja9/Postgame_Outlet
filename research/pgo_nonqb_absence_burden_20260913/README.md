# Testing non-quarterback injuries in PGO

**Research preparation complete; numerical injury adjustments are not ready.**
This study defines a calculation that can be checked without inventing a point
penalty for an injured player. It has no effect on today's picks or rankings.

The proposed measure asks: **how much did the confirmed missing players usually
play?** For example, two injured players who each played 80% of their unit's snaps
contribute 0.8 + 0.8 = 1.6. Offense and defense are counted separately. This does
not yet tell us how many points their absence costs. That relationship needs to
be learned and tested against the same PGO predictions on the same games.

Use the median of up to four prior games' directly reported snap percentages.
An actual zero counts; an unknown history stays unknown. A rookie without NFL
history does not automatically get a zero-quality grade. A healthy scratch,
reserve roster label or questionable designation is not a confirmed injury
absence. Incomplete reports cannot produce a complete injury total.

## What the September 13 source check found

The audit fixes its view at the saved **12:55 AM Eastern** edition, rather than
claiming it is a later live injury report. There are 14 upcoming games and two
completed openers. Both openers lack an eligible original full-player inventory
and remain excluded from this prospective collection.

- Saved reports identify 22 non-QB players explicitly OUT with an injury reason:
  nine on offense and 13 on defense.
- Earlier usage summaries find history for 20 of them. **New Orleans TE Oscar
  Delp and Philadelphia TE Eli Stowers** have no observed history in that lookup.
  Those are coverage clues, not values calculated by the new formula: the earlier
helper used a different denominator and omitted zero-snap observations.
- Denver-Kansas City lacks a report in this edition's current versioned archive.
  All upcoming final inactive lists remain unconfirmed in this saved edition.
- No upcoming game has finished, so this cohort has no postgame usage joins yet.
  The existing collectors will check eligible finals as their sources arrive.

The historical review admitted **zero additional training games**. Annual files
do not establish what was available before each old kickoff. A narrower 2024
game-report archive is a useful lead, but identities and report completeness
still need qualification. See the [historical findings](source-review/findings.md)
and [current coverage audit](current-review/prospective-review.md).

## What happens next

The [frozen charter](charter.md) specifies source checks, the exact calculation,
the PGO baseline and a fixed future comparison. First collect qualifying reports
and prior usage; then verify the already scheduled postgame participation joins.
Only adequate, admitted data can support fitting and a separately frozen test.
The declared prospective design uses 2026 for development and 2027 for untouched
evaluation. It cannot establish a useful injury weight this morning. Extending
collection beyond 2026 is a remaining prerequisite, not an implemented feature.

Successful calculation tests establish that the formula handles inputs correctly.
They do not establish better predictions. Normal weekly PGO updates continue;
this experiment does not alter locked forecasts, ranks, grades or confidence points.

The [pinned prior-snap schema check](prior-snap-schema.json) also verified 25,395
regular-season rows: both direct-percentage fields contain valid fractions and
explicit zeros, with no duplicate game/team/player source keys. That confirms the
fields can represent the proposed measure; it does not qualify the player joins
or historical injury report timing.

Run the calculation checks from the repository root:

```
python -m unittest discover -s research/pgo_nonqb_absence_burden_20260913 -p test_features.py -v
```

Exact review artifacts and hashes are retained beside this document. The source
audits describe the captured editions and must not be presented as a live report.
