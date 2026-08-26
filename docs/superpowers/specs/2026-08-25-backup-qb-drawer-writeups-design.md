# Backup QB Drawer Writeups

## Problem

Backup-quarterback drawers show the selected backup's identity and rating but reuse the team's starter-quarterback writeup. The generator loads the team writeup before it considers the backup-specific note in `data/qb_depth.csv`.

## Approved behavior

- A dedicated `data/qb_writeups/<player-slug>.md` file remains highest priority for every quarterback.
- A starter without a dedicated file continues to use the team's `## Quarterback` section.
- A backup without a dedicated file uses that row's existing `qb_depth.csv` note.
- If neither backup prose source exists, retain the current "No write-up yet" stub.
- Ratings, ranks, model inputs, and team drawers do not change.

## Implementation and verification

Pass the team abbreviation to the existing writeup loader only for starter rows. This preserves its override behavior while allowing the existing backup-note fallback to run. Add one regression test covering both sides: a backup must not inherit the starter section, and a starter still must.

Regenerate `docs/index.html`, run the focused test and full suite, then publish and smoke-test one backup and one starter drawer.
