# PGO v1 Primary Release Design

**Status:** Approved design awaiting written-spec review  
**Date:** July 24, 2026  
**Product:** Postgame Outlet NFL Power Ratings  
**Model:** Independent PGO v1

## 1. Decision

Postgame Outlet will publish PGO v1 as the first and default Power Ratings view.
Sean McCabe has approved the release, and the site owner has explicitly
authorized shipment.

PGO v1 remains an integrity-eligible statistical `HOLD`. Every public model
view must therefore say **Experimental model — HOLD** and show the failed
historical gate. The release must not call v1 validated, proven, or official.

McCabe's ratings remain visible as the independent human comparison. The two
ratings are never blended.

## 2. Public behavior

- The page header identifies the primary ranking as the Postgame Outlet model.
- The PGO comparison table is the first tab, selected on initial page load.
- Its initial row order is PGO full-strength rank.
- The table retains sortable PGO full-strength, availability, current-lineup,
  McCabe, and disagreement columns.
- The `Experimental model — HOLD` label, model version, as-of time, backtest
  MAE, confidence interval, and failed gate are visible in the primary view.
- McCabe's team and quarterback ratings remain available as named human views.
- Existing accessibility, mobile scrolling, team labels, and sorting behavior
  remain intact.

## 3. Release path

The existing `pgo_comparison.py` generator remains the single source for the
combined page.

- Its default command continues to write only a dated private preview.
- One explicit publication option writes only `docs/index.html`; it does not
  accept an arbitrary live destination.
- Publication reuses the existing frozen McCabe snapshot and PGO v1 receipt.
- Review flags, snapshot mismatches, receipt inconsistencies, missing teams, or
  failed integrity gates stop generation before the public file is replaced.
- The reviewed commit is pushed to `main` so the repository's existing GitHub
  Pages configuration serves the updated `docs/index.html`.
- The Shopify iframe URL remains unchanged. No Shopify content, menu, theme,
  redirect, analytics, or commerce file changes are required.

## 4. Testing and verification

Focused tests must prove:

- the private default cannot write outside `output/`;
- publication requires the explicit option and targets only
  `docs/index.html`;
- the PGO tab and panel are initially selected and visible;
- the initial table order follows PGO full-strength rank;
- the HOLD label and gate evidence remain visible;
- McCabe's ratings remain present and separate;
- existing release-input checks still fail closed.

Before publication:

1. Run the focused comparison and release tests.
2. Run the complete unit-test suite.
3. Generate and inspect the private page at desktop and mobile widths.
4. Generate `docs/index.html` with the explicit publication option.
5. Confirm no unintended production or data files changed.
6. Push the reviewed release commit to `main`.
7. Verify the public GitHub Pages URL and embedded Shopify page.

## 5. Boundaries

- This release does not change PGO v1 training, ratings, receipts, or status.
- It does not publish PGO v1.1 or v1.2.
- It does not modify McCabe's ratings or attribution.
- It does not add a dependency, service, database, workflow, or new public URL.
- It does not start PGO v2 implementation.

PGO v2 remains a separate nflverse-only challenger. It may replace v1 only
after beating v1 on the same 2,127 games with a paired 95% improvement interval
entirely above zero and no sufficiently powered subgroup regression.

## 6. Acceptance criteria

The release is complete when:

- PGO v1 is the public default ranking and is initially ordered by PGO rank.
- Its experimental HOLD status and exact evidence are prominent.
- McCabe remains available as the independent human comparison.
- The existing Shopify embed continues to load the ratings page without an
  iframe URL change.
- Tests pass, the generated page is reviewed at desktop and mobile widths, and
  the public page is verified after deployment.
