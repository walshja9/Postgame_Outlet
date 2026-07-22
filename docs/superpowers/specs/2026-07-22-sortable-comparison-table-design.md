# Sortable Private Comparison Table Design

**Date:** 2026-07-22

## Goal

Keep the existing private McCabe-versus-PGO comparison view and URL unchanged, while making all ten table columns sortable. The feature is presentation-only: it must not change either rating system, their source artifacts, or their default comparison order.

## Scope

The change is limited to the private comparison preview generator in `pgo_comparison.py`, its focused tests, and regeneration of the ignored preview under `output/`.

The following remain untouched:

- `generate_site.py` and its existing public ratings table
- `docs/index.html` and every live or publishable output
- model training, ratings, backtest, receipts, and source snapshots
- Shopify, GitHub Pages, workflows, redirects, and analytics

## User Experience

The comparison table continues to open in its current McCabe-rank order. Each column heading becomes a native button:

- The first activation sorts that column in its natural ascending direction.
- A second activation reverses the direction.
- Team names sort case-insensitively from A to Z or Z to A.
- Rank, rating, adjustment, and gap columns sort numerically rather than as displayed text.
- Ties resolve alphabetically by team name so the result is deterministic.

Sorting only reorders the 32 displayed rows in the browser. It does not rewrite the model CSV, McCabe snapshot, receipt, or generated source data. The sticky Team column and the existing mobile horizontal table scrolling remain intact.

## Accessibility

Native buttons make every sort control keyboard-operable without custom key handlers. Each column header begins with `aria-sort="none"`. After sorting, the active header reports `ascending` or `descending`, and all other headers return to `none`.

A visually hidden live status message announces the selected column and direction, for example, `PGO full # sorted ascending`.

## Implementation

`pgo_comparison.py` will emit comparison-specific markup, styles, and a small vanilla-JavaScript sorter scoped to `#panel-comparison`. The implementation may follow the existing public table sorter's proven behavior, but it will not refactor or modify `generate_site.py` and will add no dependency.

Each comparison cell will expose an explicit raw sort value where necessary. The sorter will read those values instead of parsing formatted strings such as `+2.4`. It will reorder only the comparison table body and use the team name as its secondary key.

The comparison script will be inserted through the generator's existing fail-closed template-marker mechanism. The preview will be regenerated at the same dated private path:

`output/pgo-comparison-preview/2026-07-22/index.html`

## Verification

Focused automated tests will first establish a failing case, then verify that:

- all ten headers expose native sort buttons;
- headers and the live region have the required accessibility state;
- numeric cells preserve explicit raw sort values;
- the script is scoped to the comparison panel and includes deterministic team-name tie-breaking;
- existing comparison receipt and source-integrity checks still pass.

After the full test suite passes, browser QA will verify desktop and mobile behavior:

- PGO full rank sorts ascending and descending;
- Team sorts A to Z and Z to A;
- `aria-sort` and the live announcement update correctly;
- all 32 unique teams remain present after sorting;
- keyboard activation works;
- the page has no new console errors or document-level mobile overflow.

## Explicit Non-Goals

This change does not add filtering, search, pagination, export, saved sort preferences, a third-party table library, or a public comparison page. Any such feature requires a separate decision.
