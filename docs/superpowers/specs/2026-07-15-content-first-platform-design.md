# Postgame Outlet Content-First Platform Design

**Status:** Approved visual design; written specification awaiting final review
**Date:** July 15, 2026
**Product:** Postgame Outlet
**Architecture:** Shopify-native content and commerce with an independent ratings application

## 1. Product decision

Postgame Outlet will become a sports-content business with commerce as a supporting revenue stream. Power Ratings are the broad flagship. Fantasy football—initially Dynasty and DFS—is a major editorial section but not the entire brand. Merchandise remains available and visible without displacing analysis.

The platform will remain on Shopify. Shopify will own navigation, homepage content, articles, search metadata, products, cart, checkout, and customer analytics. The existing GitHub-hosted ratings application will remain independent and will continue to own ratings data, calculations, snapshots, writeups, and interactive behavior.

This design does not materially change the direction communicated by Osama Khot or Sean McCabe:

- Osama's content-first, commerce-second direction remains the governing product model.
- Power Ratings remain multi-sport in ambition while launching with validated NFL work only.
- Fantasy receives a meaningful section without redefining the entire site as fantasy-only.
- McCabe's Power Ratings and Postgame's statistical models remain separate products.
- Comparisons between McCabe, the Postgame model, and the market are shown transparently rather than blended.
- Ads, subscriptions, additional sports, and broader fantasy-platform integrations wait for demonstrated demand and reliable implementation.

## 2. Goals and success criteria

### Goals

1. Make sports analysis the first thing a visitor sees and understands.
2. Establish Power Ratings as Postgame Outlet's flagship recurring product.
3. Build trust through named authors, visible methodology, timestamps, immutable snapshots, disclosed corrections, and permanent result receipts.
4. Give Dynasty and DFS content a clear home without launching empty tools.
5. Preserve the existing Shopify catalog, cart, checkout, and fulfillment path.
6. Measure whether content produces merchandise customers and revenue.
7. Make the ratings experience usable on mobile and operable by keyboard.

### Primary business outcome

The primary outcome is increased merchandise revenue attributable to readers who entered through Postgame content. Supporting indicators are returning readers, ratings and fantasy engagement, email signups, content-to-product clicks, add-to-cart activity, and completed purchases.

### Non-goals for the first build

- WordPress, headless commerce, or a custom CMS
- Custom fantasy-team apparel
- A subscription paywall
- Display advertising
- Customer accounts, forums, or community features
- Unvalidated MLB, NBA, or other sport models
- Unsupported Yahoo, ESPN, or CBS integrations
- Automatic publishing without human review
- A native Shopify rewrite of the entire ratings application

## 3. Information architecture

The primary navigation is:

**Home · Power Ratings · Fantasy · Shop**

Supporting destinations such as Methodology, Accountability, Authors, Contact, and archived editions are linked contextually and from the footer. Prediction Lab is hidden by default at public launch. It may appear inside the Power Ratings experience only after a documented pregame paper-tracking period and explicit team approval; it receives primary navigation only after it produces reliable recurring coverage. Future sports stay hidden until their ratings and editorial coverage are real.

### Public routes

- `/` — content-first homepage
- `/pages/power-ratings` — native ratings context plus the interactive ratings application
- `/pages/fantasy` — Dynasty and DFS editorial landing page
- `/blogs/analysis/...` — native Shopify articles tagged by sport and content lane
- `/pages/methodology` — plain-language rating and model methods
- `/pages/accountability` — publication rules, corrections policy, and links to historical receipts
- Existing collection, product, cart, and checkout routes — unchanged

One Shopify analysis blog is sufficient. Article tags distinguish `power-ratings`, `nfl`, `dynasty`, and `dfs`; separate CMS structures are unnecessary at launch.

## 4. Experience design

### Site-wide visual direction

The site should feel like an independent sports desk, not a betting tout page or a generic merchandise store. Use the existing Postgame identity with a restrained light background, dark ink/navy foundation, blue analytical accent, and gold secondary accent. Typography prioritizes headlines and long-form reading. Motion is minimal. High contrast, visible focus, and readable type sizes are release requirements.

Content leads every page. Merchandise modules appear only after useful analysis and use contextual copy such as “From the Outlet” or “Merch supports the work.” Immediate promotional overlays must not interrupt a first-time reader before the page has delivered value.

### Homepage

The homepage follows this order:

1. Latest flagship story or Power Ratings edition
2. Current NFL Power Ratings top-five preview with a link to all 32 teams
3. Latest sports analysis
4. Dynasty and DFS stories
5. Accountability summary and open ledger link
6. Small featured-merchandise section
7. Content-focused email signup

The hero identifies the author, publish or update time, and edition or model version when applicable. The top-five preview must explain that rating points represent neutral-field strength versus a league-average team.

### Power Ratings page

The Shopify document supplies crawlable context before the embedded application:

- Page title and current edition
- Named author
- Published and updated timestamps
- Short definition of a Power Rating
- Methodology and corrections links
- A concise current-edition summary

The interactive application supplies:

- Mobile-safe 1–32 ratings board
- Rating, ordinal rank, team name, movement, and team explanation
- Edition history and previous snapshots
- Optional featured matchup comparison when a reviewed prediction exists
- Methodology and accountability access

The product is called **Power Ratings**. The board may show ordinal positions 1–32 for orientation, but explanatory copy refers to team-strength scores as ratings rather than renaming the product “rankings.”

### Fantasy page

Fantasy launches as an editorial landing page with two visible lanes: Dynasty and DFS. It leads with published analysis. It does not show empty assistant, league-sync, or model interfaces.

Fantasy Lab models remain separate from McCabe's NFL ratings and from the Prediction Lab game model. A future league assistant may reuse proven Sleeper work. Yahoo, ESPN, and CBS support is added one platform at a time only after each integration is reliable enough to claim publicly.

### Article pages

Articles remain native Shopify content and include:

- Headline and short deck
- Named author
- Published and updated timestamps
- Model or data version when applicable
- Clear key takeaway
- Readable body content
- Sources, methodology links, and correction history
- Related analysis
- At most one relevant product module after the analysis

### Shop

The current Shopify catalog, product pages, cart, and checkout remain the commerce system. The shop remains one primary navigation item. Content may link to relevant products, but products do not interrupt analysis or imply an editorial recommendation without a real relationship.

## 5. Model and editorial boundaries

### McCabe Power Ratings

- Owner: Sean McCabe
- Purpose: estimate overall NFL team strength
- Primary output: points above or below a league-average team on a neutral field
- Matchup use: derive a McCabe-implied game line after adding opponent and venue context
- Publication: named, timestamped, versioned, and manually reviewed

### Postgame Prediction Lab

- Owner: Postgame Outlet
- Purpose: independently price one game using reviewed statistical inputs, opponent context, and home field
- Primary output: fair matchup line
- Relationship to McCabe: compared but never blended initially
- Publication: visible only after documented pregame paper tracking and explicit team approval

### Market

- Owner: external
- Purpose: provide a benchmark for one matchup
- Primary output: current or closing spread
- Publication requirement: source and capture timestamp
- Failure behavior: unavailable market data removes the comparison without removing Power Ratings

### Fantasy Lab

- Owner: Postgame Outlet
- Purpose: support Dynasty and DFS analysis using separately evaluated models
- Relationship: independent of McCabe Power Ratings and the game Prediction Lab
- Publication: model-specific version, inputs, timestamps, and evaluation record

The core language is:

> McCabe rates teams. Prediction Lab prices games. The market supplies the benchmark.

## 6. Matchup-comparison design

Overall ratings and one-game predictions must never appear as if they answer the same question.

The ratings section first shows the complete league board and defines the selected team's score. A separate full-width matchup section then names the teams, venue, event time, and lock status. Its three columns are:

1. McCabe-implied matchup line
2. Postgame Prediction Lab fair line
3. Sourced market line

The comparison must state explicitly that the lines apply only to the named matchup, not to either team's overall league position. A short “Where the matchup numbers disagree” explanation identifies the major assumptions driving the gap. This full-width stack avoids the empty-space and context problems found in earlier module mockups.

## 7. Accountability lifecycle

Every prediction follows the same permanent lifecycle:

1. **Draft — private:** incomplete, failed-validation, or `needs_review=Y` work is not public.
2. **Published — locked:** forecast, model version, inputs, and market timestamp are frozen before kickoff.
3. **Settled — scored:** final score, closing line, result, and grading attach to the original snapshot.
4. **Corrected — disclosed:** the original remains visible and a dated note explains what changed and why.

Required guardrails:

- No review-flagged item reaches public output.
- No market comparison appears without its source and capture time.
- No prediction can be created or altered after kickoff without a disclosed correction.
- A missing external feed produces “unavailable,” never a fabricated value.
- Wins, losses, pushes, and misses remain equally visible.
- Every public edition has one immutable snapshot.

## 8. Technical architecture and data flow

### Shopify responsibility

Shopify owns the public shell: theme, homepage, navigation, articles, fantasy landing page, crawlable ratings context, products, checkout, and first-party analytics. Before edits begin, Shopify CLI captures the duplicate unpublished theme under `shopify-theme/` in this repository. Theme deployment remains a manual command from an approved commit; no automatic production deployment is introduced.

### Ratings repository responsibility

The existing repository owns source rating data, writeups, calculations, optional matchup data, snapshots, and generated interactive output. Its first implementation pass repairs rather than replaces the current generator and application.

The initial repair must:

- Abort generation with a clear error when any release row remains `needs_review=Y`
- Eliminate horizontal page scrolling on mobile
- Make tabs, sorting, team rows, and the detail drawer keyboard-operable
- Give the drawer correct dialog semantics and focus behavior
- Add useful document metadata and a canonical URL
- Retain the current fail-open behavior when optional ESPN or market data is unavailable
- Preserve generated snapshots and team writeups

No new frontend framework, database, API service, or CMS is required.

### Short-term integration

The `/pages/power-ratings` Shopify page remains the integration point. It adds useful native context around the interactive application instead of relying on an empty Shopify document containing only an iframe. A native rewrite of the full ratings table is deferred until analytics or maintenance evidence shows that the repaired embed is a material constraint.

### Preview environments

- Ratings work occurs on a `codex/` branch and is reviewed from a local generated preview before any Pages deployment.
- Theme work occurs in an unpublished duplicate Shopify theme.
- The approval package combines the Shopify theme-preview link with the local ratings preview and responsive captures; no additional preview-hosting platform is introduced.
- The current production theme and current root ratings output remain rollback targets.
- A production publish requires explicit approval after the combined desktop, mobile, content, ratings, accessibility, analytics, and checkout review.

## 9. Editorial and publishing workflow

The minimum workflow is:

1. Author creates or updates ratings, analysis, model output, and source notes.
2. A second person clears required fields, language, numbers, sources, and the review flag.
3. The generator creates a dated artifact without replacing production.
4. The team reviews the unpublished theme and local ratings preview on desktop and mobile.
5. The approved artifact and theme version are published.
6. Results or corrections attach later without replacing the original receipt.

This workflow applies to ratings, Prediction Lab output, Fantasy Lab analysis, and corrections. It does not require a new workflow service; repository review plus Shopify draft/unpublished-theme controls are sufficient.

## 10. SEO and content hygiene

Every public page needs one meaningful H1, a useful title and meta description, a canonical URL, and crawlable summary content. Native Shopify article pages provide the main search surface. The ratings iframe supplements rather than replaces native page context.

Before launch, existing ratings-related blog URLs receive an intentional outcome:

- Historically useful editions remain public, are labeled as archives, and link to the current ratings page.
- Duplicate, thin, or superseded pages receive a permanent redirect to the closest relevant current destination.
- No obsolete URL remains indexed accidentally.

Shopify's existing sitemap remains authoritative. Additional sitemap infrastructure is unnecessary.

## 11. Accessibility and responsive requirements

Release-blocking requirements are:

- No horizontal document scrolling at 320px, 390px, 768px, or desktop widths
- A single logical heading hierarchy
- Keyboard-operable navigation, tabs, sorting, team selection, and drawer close behavior
- Visible focus indicators
- Correct button, table, status, and dialog semantics
- Drawer focus containment and focus return
- Sufficient color contrast without relying on color alone
- Store, cart, and checkout smoke-tested after theme changes

Accessibility is part of the first repair, not a deferred enhancement.

## 12. Measurement

Use Shopify analytics and any analytics integration already installed before adding another vendor. Add one first-party `postgame_content_product_click` event containing content type, content identifier, and product handle. Use Shopify's native commerce events for product views, add-to-cart, checkout start, and purchase when available.

The measurement path is:

**Content visit → qualified reading → product click → cart/checkout → purchase**

Weekly reporting should answer:

- Which content brought readers to the site?
- Which ratings, Dynasty, or DFS pages produced product interest?
- Which content sessions produced carts and purchases?
- Did content-attributed revenue and conversion increase versus the pre-launch baseline?

Ads and a new analytics stack are deferred until traffic or reporting gaps justify them.

## 13. Rollout and rollback

### Phase 0 — Capture and protect

- Export the current Shopify theme and preserve a rollback copy.
- Capture theme source in version control.
- Record baseline content traffic, store conversion, orders, and revenue.
- Confirm the current ratings output and Shopify page remain unchanged.

### Phase 1 — Build privately

- Repair the ratings application on a feature branch.
- Build the content-first Shopify experience in an unpublished duplicate theme.
- Draft native articles, author information, methodology, fantasy, and accountability pages without publishing them.

### Phase 2 — Review everything

- Review desktop and mobile page layouts.
- Verify copy, ratings, matchup scope, model labels, timestamps, and correction language.
- Run keyboard, responsive, metadata, link, analytics, product, cart, and checkout checks.
- Confirm old URL outcomes and rollback readiness.

### Phase 3 — Approve and cut over

- Obtain explicit team approval.
- Publish the approved ratings artifact and Shopify theme in a controlled window.
- Monitor errors, responsive behavior, checkout, content-to-product events, and sales.
- Restore the previous theme immediately if commerce or navigation fails.

No production theme publish, live ratings replacement, URL cleanup, redirect, or analytics mutation occurs before the complete preview is approved.

## 14. Acceptance criteria

The first build is ready for production only when:

- The team approves all public copy and ratings.
- The homepage is visibly content-first on desktop and mobile.
- Power Ratings show the full current league board and define the rating scale.
- Overall ratings and one-game predictions are unambiguously separated.
- McCabe, Prediction Lab, market, and Fantasy Lab outputs retain separate identities.
- Review-flagged data cannot be generated into public output.
- Authors, timestamps, versions, and correction links are visible where required.
- Ratings remain usable when optional external data fails.
- Mobile widths do not create horizontal page scrolling.
- The interactive ratings experience passes its keyboard path.
- Existing URLs have intentional archive or redirect behavior.
- Content-to-product tracking is verifiable.
- Product, cart, and checkout smoke tests pass.
- The previous production theme is available for immediate rollback.

## 15. Implementation constraint

This document authorizes planning, not implementation. The live Shopify theme, published ratings output, redirects, analytics configuration, and production content remain unchanged until the implementation plan is reviewed and the preview-first work is explicitly authorized.
