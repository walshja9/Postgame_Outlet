# PGO Site Update Implementation Plan

> **For agentic workers:** Use subagent-driven-development for bounded implementation and review tasks; the parent owns Shopify operations and final integration.

**Goal:** Finish the existing editorial Shopify site and integrate the reviewed Week 1 availability board into the actual PGO website.

**Architecture:** Keep the existing Shopify theme, native content, and commerce. Keep the ratings application on GitHub Pages. Reuse the approved content-first design and existing sections; introduce no framework, service, or new dependency.

**Authorization:** On September 6, after being told that the public homepage and ratings app had not received the improvements, the user instructed: "proceed with updates to the site". This is authority to implement the described site updates. Earlier documentation-only and preview-setup checkpoints are historical. Preserve model/evidence constraints and prepare and verify the complete update before any production release action.

## Constraints

- Preserve source receipts, frozen models, projections, eligibility, and all prior qualification artifacts. Preliminary availability remains annotation-only and the model remains EXPERIMENTAL / HOLD.
- Use the existing content-first worktree on `codex/content-first-fresh-base-port`; leave the dirty challenger worktree's qualified source intact.
- Capture the current live theme before changing it. Reconcile fresh settings and integrations; preserve products, cart, checkout, fulfillment, and customer data.
- Reuse existing preview resources only for their existing PGO purpose after inspecting their contents. Preserve unrelated menu items and content; do not delete resources or change metafield definitions to force compatibility.
- The user's subsequent "injury reports also dropped" update authorized a fresh official-report capture. Preserve earlier captures and do not rerun model fitting, evaluation, or game locks.
- Public release must retain current McCabe and PGO team content, even if it is newer than the private fantasy package. Verify the public refresh path preserves the integrated fantasy panel.
- Never invent articles, authors, publication times, healthy status, movements, or model performance. Use reviewed existing content and explicit unavailable states.

## Tasks

- [x] Verify authenticated Shopify and GitHub access, current branches, the existing theme plan, and the published board. Theme baseline: 12 tests pass. Remote main is `a681e84468ab429176d3efcc22ae07a615389d10`; live Spotlight theme is `145035722984`.
- [x] Capture and compare the complete current live theme with the September 3 baseline; retain the original for rollback. All 368 files were byte-identical to baseline `3f5e7c641ee2cb1ad9320488352b45cb64ad0c60`.
- [x] Repair the article methodology rendering to accept the store's existing single-line text as escaped text while retaining page-reference links. Native preview verified populated text/sources and blank metadata behavior. Shared article cards now use the same escaped byline fallback as the article and hero.
- [x] Inspect existing menus, pages, and articles. Configure existing sections and canonical destinations. Publish the factual Week 1 article `598924296424`, Fantasy `/pages/fantasy`, Methodology, and Authors; retain existing article history, accountability, and commerce. Primary navigation is Home, Power Ratings, Fantasy, Shop; footer destinations are canonical.
- [x] Prepare and release the public board. Release `43de5fb1a686fa216a6165bf90b2f8b6278c19f5` passed 411 tests and independent/browser reviews; CI refresh `dc3d398f82c6f1fe88aa384dd3aa7d0cc05ef69d` is live. All 447 projections and the full fantasy panel remain unchanged by refresh. Navy source-link text improves contrast to 8.35:1; protected v4 evidence is unchanged.
- [x] Upload theme `159107678440` as unpublished and verify the real Shopify storefront at desktop and mobile sizes. Homepage, ratings, Fantasy, articles, commerce, navigation, keyboard behavior, and iframe sizing passed. Preserve the native QA screenshots and report.
- [x] Independently review the final files and release package. Theme checks remain 429 baseline offenses with zero introduced; 12 theme tests pass. Review accepted the final metadata, no-image hero, list-marker, line-height, and article-card fixes.
- [x] Publish theme `159107678440` (`PGO Site Update 2026-09-06`) after review. CLI confirms role `live`; prior Spotlight `145035722984` remains unpublished for rollback. A clean public session verified homepage, article, ratings, Fantasy, Methodology, and Authors. Final public QA caught a hidden Fantasy page; publication, title, and SEO were corrected with individual saves and reloads, and the final canonical route returns HTTP 200.

## Release follow-up

- The existing Klaviyo shipping popup and teaser still appear on editorial pages. Its targeting requires a separate Klaviyo login; the login tab is open for the user. Preserve the embedded newsletter and installed integrations. Once authenticated, restrict the shipping form through native URL targeting to commerce routes and verify its teaser follows the same targeting.
- Shopify's final theme round trip contains the same 375 files: 372 byte-identical, two page templates with formatting-only differences, and settings data that omits two existing Inbox color properties (`secondary_color` and `ternary_color`). The enabled Inbox block and other settings remain intact; its launcher renders publicly.
- Final Theme Check has 393 errors and 36 warnings, matching the 429 baseline findings by file/check/severity/message. Two existing warning source positions moved; no finding was introduced. These baseline findings are not a clean-lint claim.
- Final release identities, evidence, and rollback details are recorded in `output/site-update-20260906/site-release-report.md`.

## Verification and evidence

Use `python -B -m unittest tests.test_shopify_theme` for the existing theme contracts and the installed Shopify CLI 4.7.1 for Theme Check and theme transfer. Compare Theme Check findings with the existing baseline; do not claim its historical offenses are new failures. Run focused board-refresh checks if code changes there. Prior 535-test evidence remains applicable only while its source hashes remain unchanged.

Store current captures, configuration records, browser evidence, and the final release report under `output/site-update-20260906/`. Keep the plan checkboxes current. A local file, unpublished Shopify theme, and published website are distinct outcomes.
