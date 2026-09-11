# PGO readable games polish

**Goal:** Make existing weekly picks, explanations and confidence accounting easier to read in McCabe's theme.

**Approach:** Keep the existing seven-column table and saved-data renderer. Give its cells visible labels when the same table reflows into game cards in narrow containers. Lead saved calculations with short team-based steps; keep exact arithmetic in an expandable disclosure. Put late-entry counts and earned points beside weekly confidence totals. Use existing Python, CSS container queries and native details elements.

**Constraints:** Presentation only. Preserve all forecast values, grades, saved market lines, confidence allocations, source clocks, archives, validation, reading keys and experimental labels. No new dependencies or model changes. Existing authorization covers implementation and publication.

- [x] In `pgo_season_view.py`, add `.season-picks-table`, semantic table roles, `.season-cell-label` labels, and `.season-cell-value` wrappers for the six data cells. Keep seven columns, game IDs and explanation rows. Show a plain-language explanation before the existing exact calculation, using saved neutral/venue/rest values and existing spread formatting. Omit raw saved availability summary codes when structured team rows already explain coverage. Add late-entry count and earned pool points to the weekly summary.
- [x] In `docs/pgo-theme.css`, style only `.season-picks-table` and the new explanation/late-total classes. Use readable desktop spacing, top alignment, and existing theme colors. At a narrow table container, retain accessible column headers while presenting each game as labeled cells and its existing explanation underneath. No horizontal page overflow at 320, 375, 800 and 1226 pixels; retain keyboard access and all values.
- [x] Extend existing renderer tests only for meaningful conditions: positive/negative/zero explanation direction and preserved arithmetic; late confidence totals including zero earned; structured availability does not expose status enums; all game cells retain corresponding accessible labels. Reuse existing state-invariance tests.
- [ ] Render actual saved state in both the board and Forecast Lab. Inspect responsive layouts, expand score explanations, and verify reading keys and locked rows. Run focused existing suites, review the diff independently, then publish source through the full existing CI and guarded page generation. Confirm public bytes and live embedded view.

No changes to the existing model, operational capture cadence or Shopify theme are required for this pass.
