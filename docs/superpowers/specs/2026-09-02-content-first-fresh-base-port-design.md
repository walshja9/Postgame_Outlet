# Content-First Fresh-Base Port Design

**Status:** Approved design and written specification

**Date:** September 2, 2026

**Product:** Postgame Outlet Shopify website

**Repository baseline:** `ff7ec59f94674a93ec71288ad0785149cb785f1c`

**Implementation branch:** `codex/content-first-fresh-base-port`

## 1. Decision

Postgame Outlet will port the approved content-first website onto a fresh capture
of the current Shopify theme. The July theme at
`bebee2ac8fbc3be140747ebd7e02c81ac88b604c` is a semantic reference, not the new
base and not a merge target.

The work ends at a fully verified, unpublished Shopify draft. The current live
theme, navigation, pages, content, redirects, analytics configuration, ratings
artifact, model inputs, and commerce behavior remain unchanged. Publishing or
cutting over requires a separate explicit decision after the real draft receives
visual approval.

This is the selected alternative because the July branch is materially behind
current `main`, while its intended theme change is narrow: 15 theme files. A
fresh capture protects any Shopify changes made since July without rebuilding
the approved design.

## 2. Current state

As observed on September 2, 2026:

- The live homepage remains merchandise-first.
- The live Power Ratings page contains its heading and the independent ratings
  iframe, but no meaningful native introduction or metadata description.
- `/pages/fantasy` and `/pages/methodology` return 404.
- `/pages/accountability` exists and contains substantive public copy.
- The old content-first ZIP is no longer present locally.
- The immutable Git reference `bebee2ac` remains available on
  `codex/content-first-site-preview`.
- The legacy branch must not be merged: current `main` has 233 commits that the
  branch does not, and the branch has 17 commits absent from current `main`.
- Forty-four focused ratings, release-gate, and public-board tests pass from the
  new branch baseline. `docs/index.html` retains SHA-256
  `5094AD484807BACB8CE5DDDF19CFF38798ED86A07C1501D1BCBF09F84DD932FE`.

## 3. Goals

1. Preserve the current Shopify theme as the source baseline.
2. Make analysis the first useful content on the homepage.
3. Give Power Ratings crawlable Shopify context before the independent app.
4. Create a real Fantasy editorial landing page without exposing an unqualified
   fantasy model.
5. Preserve products, collections, cart, checkout, fulfillment, app embeds, and
   existing live content.
6. Produce a deterministic draft-theme package and a reviewable Shopify preview.
7. Require a second visual approval against the real draft before any cutover is
   designed or authorized.

## 4. Non-goals

- Publishing or activating a theme
- Editing the live navigation or footer
- Assigning alternate templates to canonical live pages
- Publishing articles or making hidden pages public
- Creating or activating redirects
- Installing an analytics vendor or changing live analytics settings
- Replacing `docs/index.html` or changing the GitHub Pages deployment
- Changing PGO, McCabe, Prediction Lab, Fantasy Lab, source, lock, or grading code
- Publishing PGO fantasy projections before their independent gates pass
- Adding a frontend framework, CMS, database, API service, or build dependency
- Cleaning up inherited Spotlight, GemPages, translation, or Theme Check debt

## 5. Architecture

Shopify remains the content and commerce shell. The GitHub-hosted ratings page
remains the independent interactive application and source of ratings behavior.
The port adds only Shopify-native content structure around that application.

| Component | Responsibility |
|---|---|
| Current Shopify theme | Read-only remote source for the fresh local baseline |
| New isolated worktree | Theme capture, approved semantic port, tests, and package |
| Shopify Liquid/JSON theme | Homepage, navigation, article trust fields, Power Ratings wrapper, and Fantasy landing page |
| Existing ratings app | Ratings calculations, tables, snapshots, drawer, model labeling, and accessibility behavior |
| Hidden Shopify resources | Preview menus, pages, metafields, and draft articles |
| Unpublished Shopify theme | Real browser and commerce review surface |

The one-way flow is:

`current theme capture -> frozen baseline commit -> 15-file semantic port -> local verification -> deterministic ZIP -> unpublished Shopify draft -> browser review -> explicit approval stop`

There is no publish step in this design.

## 6. Approved visual contract

### Homepage

The homepage uses the approved **Editorial desk** hierarchy:

1. Primary navigation: `Home · Power Ratings · Fantasy · Shop`
2. Named, dated flagship analysis
3. A clearly subordinate `Experimental · HOLD` model-status treatment
4. Five-team Power Ratings preview with a link to all 32 teams
5. Latest NFL analysis
6. Separate Dynasty and DFS editorial lanes
7. Accountability summary and ledger link
8. Existing email signup after useful content
9. One restrained merchandise module labeled `From the Outlet`

Desktop uses a wide editorial hero and compact supporting cards. Mobile uses one
reading column in the same order, a collapsed native menu, a vertical top-five
list, and stacked story cards. Neither layout may create document-level
horizontal scrolling.

### Power Ratings

The Shopify page supplies, before the iframe:

- One H1 and the current edition
- Named author plus published/updated time
- A plain-language definition of neutral-field rating points
- Separate identities for PGO and McCabe; the two are never blended
- `Experimental · HOLD` status where applicable
- Methodology, Accountability, and archive links
- A concise current-edition summary

The native wrapper does not duplicate detailed backtest metrics already exposed
inside the app. The iframe remains the only owner of interactive ratings tables,
sorting, snapshots, and team drawers.

### Fantasy

Fantasy is an editorial landing page with distinct Dynasty and DFS lanes. During
the opening-night wait, it may state that definitive inactive information is not
yet available and explain the T-60 process. It must not expose private preview
rows, infer healthy status, or present rankings/projections as locked.

No empty assistant, league-sync, or model interface appears. A future qualified
Fantasy Lab artifact requires its own publication design and approval.

### Supporting pages and articles

Methodology, Accountability, Authors, and analysis articles inherit the same
light canvas, navy/slate type, orange secondary accent, readable measure, visible
focus, and trust metadata. Article product placement is optional, limited to one
relevant module, and follows the analysis.

## 7. Fresh capture and provenance

Before any theme source is written:

1. Confirm the intended Shopify store, authenticated account, live theme ID,
   theme name, and theme role.
2. Record the Shopify CLI version and capture timestamp without recording any
   credential value.
3. Stop if the store, account, theme identity, or authorization is ambiguous.

Pull the current live theme into `shopify-theme/` in this isolated branch. Scan
the capture for credential material before staging it. Parse every JSON file and
run Theme Check to record the inherited baseline. Commit the untouched capture
as its own baseline commit before porting the content-first changes. The
resulting baseline SHA belongs in the implementation handoff; it is generated by
the capture and is not predeclared by this specification.

The baseline commit, rather than the July ZIP, becomes the byte authority for
untouched theme files. Seven commerce-critical files retain explicit SHA-256
guards derived from the fresh capture:

- `templates/product.json`
- `templates/collection.json`
- `templates/cart.json`
- `sections/main-product.liquid`
- `sections/main-cart-items.liquid`
- `sections/main-cart-footer.liquid`
- `snippets/cart-drawer.liquid`

## 8. Port boundary

Port the behavior from `f786980..bebee2ac` only within this 15-file theme
allowlist:

**Add or recreate:**

- `assets/postgame-content.css`
- `assets/postgame-content.js`
- `sections/postgame-featured-story.liquid`
- `sections/postgame-ratings-preview.liquid`
- `sections/postgame-ratings.liquid`
- `sections/postgame-tagged-articles.liquid`
- `templates/page.fantasy.json`
- `templates/page.power-ratings.json`

**Reconcile against the fresh captured versions:**

- `layout/theme.liquid`
- `sections/footer-group.json`
- `sections/header-group.json`
- `sections/main-article.liquid`
- `templates/article.json`
- `templates/blog.json`
- `templates/index.json`

Do not check out whole July versions of the seven reconciled files. Apply their
semantic changes to the fresh files so current theme settings and compatible
Shopify changes survive. Any required theme-file change outside this allowlist
stops the port and requires a spec amendment.

The existing dependency-free `tests/test_shopify_theme.py` contract is restored
and updated only where the fresh baseline supplies new protected hashes or
current native structures. No new runtime dependency is needed.

## 9. Content and preview resources

After local verification and explicit action-time confirmation of the Shopify
Admin session:

- Upload a new unpublished theme named with `Content First Fresh Base` and the
  short implementation SHA.
- Create unreferenced preview header and footer menus.
- Create hidden preview pages for Power Ratings, Fantasy, Methodology, and
  Authors. Reuse the existing live Accountability page unless review shows the
  draft requires non-public replacement copy.
- Assign alternate templates only to hidden preview pages.
- Create draft editorial entries needed to exercise the approved homepage and
  the Dynasty/DFS lanes.
- Use a reviewed human byline and verify every date, rating, model version, and
  source statement immediately before draft creation.
- Keep PGO v2 and private fantasy preview evidence out of public-facing copy.

Mockup copy establishes hierarchy, not automatic publication copy. Editorial
text remains hidden until it passes factual and byline review.

## 10. Packaging

Package only `shopify-theme/`. ZIP entries must use forward slashes and contain
no repository metadata, test output, screenshots, credentials, theme-check
reports, `.superpowers/` files, or outer wrapper directory.

Record:

- Implementation commit SHA
- File and ZIP-entry counts
- ZIP SHA-256
- Fresh baseline commit SHA
- Theme Check baseline and changed-file delta
- Protected-commerce hashes

The old missing ZIP is not reconstructed or reused as an operational artifact.
The fresh package receives a new name and digest.

## 11. Failure behavior

The work stops without fallback when:

- Shopify authentication or store/theme identity is uncertain.
- A fresh current-theme capture cannot be obtained.
- Captured JSON is invalid or credential material is detected.
- The post-port diff touches a theme file outside the allowlist.
- A protected commerce hash changes.
- A changed file introduces a Theme Check finding.
- Homepage top-five data is incomplete or not editorially reviewed.
- Ratings iframe origin or messaging validation changes unexpectedly.
- The package contains backslash paths, extra roots, or unapproved files.
- Draft upload would replace or publish an existing theme.
- Hidden content cannot be kept isolated from current navigation and canonical
  routes.

Failures produce a local diagnostic/handoff. They never trigger a stale-base
fallback, live edit, or partial publication.

## 12. Verification

### Local structural gates

- All theme JSON parses.
- Focused Shopify theme tests pass.
- All existing relevant ratings/public-board tests remain green.
- The diff from the fresh baseline is confined to the 15-file theme allowlist,
  the theme test, and approved documentation.
- All seven protected commerce hashes match the fresh baseline.
- Theme Check adds no finding in a changed file.
- `git diff --check` passes.
- No secret or credential value appears in tracked content.
- The ZIP manifest and digest reproduce exactly.

### Draft browser gates

Review at 320px, 390px, 768px, and desktop widths:

- Homepage matches the approved Editorial desk hierarchy.
- Power Ratings supplies native context before the iframe.
- Fantasy contains real Dynasty/DFS draft content and no empty tool.
- Navigation, tabs, sorting, article links, and drawer behavior work by keyboard.
- Focus is visible and text contrast meets WCAG AA.
- No document-level horizontal scrolling appears.
- Iframe height and drawer viewport messaging work from Shopify preview.
- Missing optional data renders unavailable or stays absent.
- Product, collection, variant selection, add-to-cart, cart update/remove,
  checkout start, and return-to-store work without placing a real order.
- Existing app embeds do not interrupt the reader before useful content.

The approval package contains the unpublished preview URL, theme and ZIP hashes,
desktop/mobile captures, test output, Theme Check delta, editorial checklist,
commerce smoke-test record, and rollback identity.

## 13. Approval gates

1. **Design gate — passed:** Fresh-base port selected.
2. **Mockup gate — passed:** Editorial-first responsive homepage, Power Ratings,
   and Fantasy structures approved.
3. **Written-spec gate — passed:** User approved this file on September 2, 2026.
4. **Implementation-plan gate — pending:** No port begins before plan review.
5. **Draft gate — pending:** No Shopify draft resources are created before local
   qualification and action-time confirmation.
6. **Real visual gate — pending:** The uploaded unpublished draft must be reviewed
   against the approved mockups.
7. **Cutover gate — outside scope:** Publication requires a separate design,
   verification package, and explicit authorization.

## 14. Acceptance criteria

This project is complete when:

- A fresh current Shopify theme capture is preserved as an immutable local Git
  baseline.
- Only the approved semantic delta is applied to the 15-file theme allowlist.
- The approved homepage, Power Ratings, and Fantasy visual hierarchy is present
  on desktop and mobile.
- Tests, JSON parsing, protected hashes, diff scope, Theme Check delta, packaging,
  accessibility, iframe, and commerce checks pass.
- A new unpublished Shopify draft and hidden preview content are reviewable.
- The real draft receives an explicit visual verdict.
- The live store, canonical pages, navigation, redirects, analytics, ratings
  artifact, and model evidence remain unchanged.
- No push, publication, deployment, or cutover occurs under this specification.
