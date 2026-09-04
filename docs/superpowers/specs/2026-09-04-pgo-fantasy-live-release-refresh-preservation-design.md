# PGO Fantasy Live Release Refresh Preservation Design

**Status:** Approved 2026-09-04

## Goal

Publish the already verified 2026 Week 1 fantasy preview on the tracked PGO ratings page and keep it present when the existing `update-board.yml` workflow refreshes McCabe data.

## Constraints

- Keep `--fantasy-preview` private-only; do not add a reusable public-generation flag.
- Preserve the fantasy panel's rendered rankings bytes during McCabe refreshes.
- Preserve the legacy refresh result exactly when no fantasy tab is present.
- Fail closed on missing, partial, or duplicate fantasy/comparison markers.
- Keep `Experimental model — HOLD` and all existing provenance disclosures.
- Do not change Shopify, model inputs, frozen source evidence, Pages settings, or unrelated untracked files.

## Design

`refresh_mccabe_page()` will retain its current fresh-base rebuild. When the existing public HTML contains one complete fantasy tab and panel, it will:

1. Extract the existing fantasy panel without rerendering its rankings.
2. Extract and normalize the hidden comparison panel to the active form expected by the existing McCabe refresh path.
3. Refresh the comparison rows and metadata against `data/ratings.csv` and inject them into the freshly generated base page.
4. Reuse `inject_fantasy_preview()` to add the preserved fantasy panel and the current checked-in fantasy CSS, tab, and script.

When no fantasy markers exist, the function will execute the current code path unchanged. A partial or duplicate fantasy surface will raise `ValueError` before output is written.

This keeps the initial publication an explicit artifact promotion while allowing later automated board refreshes to preserve that approved publication. It does not create a CLI route that can originate or replace fantasy rankings on the public page.

## Test and Release Gate

- Add a regression test that first creates a fantasy-enabled page with the real injectors, refreshes McCabe data, and proves the fantasy panel remains exact, singular, active, and usable while McCabe cells update.
- Run the test red before implementation and green afterward.
- Run compilation, the focused release tests, and full discovery before committing the public artifact.
- Promote the verified artifact byte-for-byte to `docs/index.html`; verify its SHA-256 before commit.
- Push `main` once, monitor the triggered `Update board` workflow and Pages deployment, then verify the live URL at desktop and mobile widths with no console or network failures.
- Confirm the live page contains one Fantasy Week 1 tab, the expected rankings/source identity, and the unchanged HOLD disclosure.

## Rejected Alternatives

- A two-push manual promotion would disappear on the next data refresh.
- Disabling automatic refresh would leave McCabe data stale.
- Adding `--fantasy-preview --publish` would broaden the publication surface beyond this release.
