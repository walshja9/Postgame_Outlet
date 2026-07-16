# Content-First Preview Handoff

## Current state

No production theme, live menu, canonical page, redirect, published article,
GitHub Pages artifact, ratings snapshot, analytics setting, or ratings source row
has been changed.

- Theme source branch: `codex/shopify-theme-capture`
- Theme source commit: `c773476`
- Captured Spotlight rollback baseline: `f786980`
- Unpublished upload ZIP:
  `C:\Users\Alex\Downloads\postgame-content-first-theme-c773476.zip`
- ZIP files: 375
- ZIP SHA-256:
  `dd27561600b7f0d798801685f3811c80f2c22b1f5cbbd59b42b3b2248059dbc5`
- Theme tests: 9 passing
- Theme JSON: 85 files parsed
- Theme Check: unchanged captured baseline of 52 files with findings,
  392 errors, and 36 warnings
- Ratings source branch: `codex/content-first-preview`
- Ratings source commit: `04f5759`
- Ratings tests: 24 passing
- Editorial gate: intentionally closed by all 32 `needs_review=Y` rows

## Shopify Admin setup — unpublished only

1. Upload the ZIP as a new theme named `Content First Preview c773476`.
   Do not publish it.
2. Create an unreferenced menu with handle `content-first-preview`:
   1. Home → `/`
   2. Power Ratings → `/pages/power-ratings-preview`
   3. Fantasy → `/pages/fantasy-preview`
   4. Shop → `/collections/all`
3. Create an unreferenced menu with handle `content-footer-preview`:
   1. Methodology → `/pages/methodology-preview`
   2. Accountability → `/pages/accountability-preview`
   3. Authors → `/pages/authors-preview`
   4. Contact → `/pages/contact`
   5. Ratings archives → `/blogs/poweratings`
4. Create these optional Blog post metafield definitions; none is globally
   required:

   | Key | Type |
   |---|---|
   | `custom.deck` | Single-line text |
   | `custom.byline` | Single-line text |
   | `custom.updated_at` | Date and time |
   | `custom.model_version` | Single-line text |
   | `custom.key_takeaway` | Multi-line text |
   | `custom.sources` | Rich text |
   | `custom.methodology` | Page reference |
   | `custom.correction_history` | Rich text |
   | `custom.related_product` | Product reference |

5. Create hidden staging pages:

   | Title / handle | Template |
   |---|---|
   | Power Ratings Preview / `power-ratings-preview` | `page.power-ratings` |
   | Fantasy Preview / `fantasy-preview` | `page.fantasy` |
   | Methodology Preview / `methodology-preview` | Default page |
   | Accountability Preview / `accountability-preview` | Default page |
   | Authors Preview / `authors-preview` | Default page |

6. Keep one blog. Create, but do not publish, a flagship NFL ratings article,
   one current NFL analysis article, one Dynasty article, and one DFS article.
   Use `nfl` plus the relevant `power-ratings`, `dynasty`, or `dfs` tag and fill
   every applicable trust metafield.
7. Leave all ratings/top-five theme settings blank while any ratings row remains
   `needs_review=Y`. The theme is designed to show a safe waiting state.
8. Keep the existing Klaviyo onsite embed enabled and the inline form at the end
   of homepage content. Clone the welcome popup as a draft only: show after both
   15 seconds and 30% scroll, repeat 90 days after dismissal, never repeat after
   submission or URL action, exclude existing profiles, and allow dismissal on
   desktop and mobile.

## Cutover URL ledger — record only, do not activate

| Current URL | Approved later outcome |
|---|---|
| `/blogs/poweratings/final-power-ratings-25-26-season` | Keep as an archive; add `power-ratings`, `nfl`, and `archive`; identify edition and author; link to `/pages/power-ratings`. |
| `/blogs/poweratings/pre-big-game-power-ratings` | Keep as an archive/receipt; add source and capture context; state that the matchup line applied only to that game; link to `/pages/power-ratings`. |
| `/blogs/poweratings/week-9-power-ratings` | Redirect to `/pages/power-ratings` only at cutover. |
| `/blogs/poweratings/power-ratings-guide` | Move useful explanation to `/pages/methodology`, then redirect only at cutover. |
| `/blogs/poweratings` | Later rename display title to `Analysis`; defer handle change to `/blogs/analysis` and create the permanent redirect in the same cutover. |

## Browser review still required

The current Codex session had no attached browser backend, so upload and visual
checks remain unperformed. After the unpublished theme and draft content exist,
review the homepage, Power Ratings, Fantasy, one analysis article, one archive,
collection, product, cart, search, and contact.

Check 320px, 390px, 768px, and desktop for one meaningful H1, no document-level
horizontal scroll, visible focus, keyboard-operable navigation/content/ratings,
WCAG AA contrast, correct iframe height/drawer behavior, and no immediate
Klaviyo interruption. Verify collection, variant selection, add-to-cart, cart
update/remove, checkout start, and return-to-store without placing a real order.
Confirm one `postgame_content_product_click` event per content product click.

Capture the Shopify analytics baseline for 2026-06-17 through 2026-07-14 against
2026-05-20 through 2026-06-16: sessions, online-store conversion rate, orders,
gross sales, and total sales, including report names, timezone, currency, and
capture time.

## Release stop

Do not publish the theme, replace `docs/index.html`, clear editorial flags,
create a ratings snapshot, rename the blog handle, activate redirects, change
canonical page assignments, publish draft content, or change the live menu
without a separate explicit cutover approval after the combined review.
