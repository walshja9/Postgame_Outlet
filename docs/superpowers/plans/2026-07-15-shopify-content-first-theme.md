# Content-First Shopify Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the captured Spotlight theme into an unpublished, content-first Shopify preview while preserving the existing catalog, product, cart, checkout, and fulfillment paths.

**Architecture:** Keep Shopify Spotlight 15.2.0 as the public shell and add a small set of focused Online Store 2.0 sections for the homepage, editorial pages, and the Power Ratings iframe. The independent ratings app remains the source of truth and is embedded from `https://walshja9.github.io/Postgame_Outlet/`; Shopify supplies crawlable context and publishes one content-to-product event. All theme and content work stays in an unpublished duplicate until a combined preview is explicitly approved.

**Tech Stack:** Shopify Liquid, Online Store 2.0 JSON templates, vanilla CSS and JavaScript, Python 3 standard-library `unittest`, Shopify Theme Check, Shopify Admin theme ZIP upload.

## Global Constraints

- Start from untouched theme baseline commit `f786980` and source ZIP SHA-256 `A2C27EC3ADD103CFA5474F083331131DC981B874FC82BCDBFF9680D45FA89A95`.
- Do not modify the current production theme, publish a theme, replace the live ratings artifact, activate redirects, or change live analytics/content before combined preview approval.
- Preserve Shopify ownership of navigation, homepage content, articles, metadata, products, cart, checkout, and commerce analytics.
- Preserve the ratings repository as owner of ratings data, calculations, snapshots, writeups, and interactive behavior.
- Keep one analysis blog. Use article tags `power-ratings`, `nfl`, `dynasty`, and `dfs`; do not add a CMS, frontend framework, database, or analytics vendor.
- Keep the public primary navigation order exactly `Home · Power Ratings · Fantasy · Shop`; Prediction Lab remains hidden.
- Render no top-five ratings preview until one reviewed edition supplies exactly five complete rows and no release row has `needs_review=Y`.
- Keep McCabe Power Ratings, Postgame Prediction Lab, market data, and Fantasy Lab explicitly separate.
- Never fabricate optional market or external-feed data; render `unavailable` or omit the comparison.
- Require one meaningful H1, useful metadata, crawlable summary content, keyboard operation, visible focus, sufficient contrast, and no document-level horizontal scrolling at 320px, 390px, 768px, or desktop widths.
- Keep orange/gold as a secondary accent only. Small text and links use the existing navy `#384f6f` or another AA-compliant foreground on white.
- Publish only one custom event: `postgame_content_product_click` with `content_type`, `content_identifier`, and `product_handle`. Continue using Shopify native commerce events.
- The unresolved ratings movement-lifecycle decision remains outside this theme plan. The theme consumes only the reviewed ratings artifact produced after that decision and the 32 row-level editorial flags are cleared.

---

## Captured Baseline Map

| Concern | Captured implementation | Consequence for this plan |
|---|---|---|
| Theme | Shopify Spotlight 15.2.0 | Extend existing Liquid patterns; do not replace the theme. |
| Homepage | `shopify-theme/templates/index.json` is a commerce-first slideshow, collection list, two 12-product grids, image promotion, then Klaviyo | Replace only homepage composition with the seven required content-first modules. |
| Power Ratings page | Public `/pages/power-ratings` currently renders only its H1 | Add a dedicated alternate template with native context before the iframe. |
| Editorial templates | `templates/blog.json` and `templates/article.json` hide author names | Enable author display and add deck, updated time, version, takeaway, sources, and correction metadata. |
| Header | `sections/header-group.json` points at `main-menu` | Point the duplicate theme at a new unreferenced preview menu so live navigation is untouched. |
| Footer | No link-list blocks; duplicate Klaviyo app section has a malformed `formId` containing HTML | Remove the duplicate footer app section in the new theme and use one preview footer menu plus the homepage embed form. |
| App embeds | GemPages, Klaviyo onsite, Multifeeds, and Shopify Inbox are enabled in `config/settings_data.json` | Leave app embeds unchanged in the first build; do not expand their scope. |
| Legacy templates | GemPages index/product/collection backups remain in `templates/` and `layout/` | Preserve them as rollback artifacts; do not route new content through GemPages. |
| Existing blog | Public handle is `/blogs/poweratings` with four ratings articles | Give each existing URL an explicit archive or redirect outcome at cutover. |
| Theme Check | 392 errors and 36 warnings pre-exist: 390 translation matches, 14 variable names, 9 undefined objects, 7 orphaned snippets, 4 unused assigns, 2 remote assets, 1 dynamic-tag HTML syntax finding, and 1 schema finding | Record the baseline and allow no new finding in changed files; do not turn this project into a Spotlight/GemPages cleanup. |

## File Structure

**Create:**

- `tests/test_shopify_theme.py` — dependency-free structural and commerce-regression checks.
- `shopify-theme/assets/postgame-content.css` — shared content, ratings, metadata, focus, and responsive styles.
- `shopify-theme/assets/postgame-content.js` — ratings iframe bridge and the single custom analytics event.
- `shopify-theme/snippets/postgame-article-meta.liquid` — article deck, author, dates, version, and takeaway.
- `shopify-theme/snippets/postgame-article-footer.liquid` — sources, methodology, and correction history.
- `shopify-theme/sections/postgame-featured-story.liquid` — explicitly selected flagship article hero.
- `shopify-theme/sections/postgame-ratings-preview.liquid` — fail-closed five-team native ratings preview.
- `shopify-theme/sections/postgame-tagged-articles.liquid` — reusable analysis lane filtered by one required tag and one optional alternate tag.
- `shopify-theme/sections/postgame-ratings.liquid` — native ratings context plus trusted iframe.
- `shopify-theme/sections/postgame-related-analysis.liquid` — up to three same-blog articles sharing a tag.
- `shopify-theme/sections/postgame-related-product.liquid` — zero or one article-linked product from a metafield.
- `shopify-theme/templates/page.power-ratings.json` — alternate template for the canonical ratings page.
- `shopify-theme/templates/page.fantasy.json` — native Dynasty and DFS landing template.

**Modify:**

- `shopify-theme/layout/theme.liquid:31-39,258-266,301-313` — load the shared assets and expose content identity to the event publisher.
- `shopify-theme/templates/index.json:1` — install the required seven-part homepage order.
- `shopify-theme/sections/main-article.liquid:44-72` — render the two metadata snippets around article content.
- `shopify-theme/templates/article.json:1` — show author, then related analysis and at most one product.
- `shopify-theme/templates/blog.json:1` — use a readable grid and show authors.
- `shopify-theme/sections/header-group.json:1` — use the preview navigation menu.
- `shopify-theme/sections/footer-group.json:1` — use the preview footer menu and remove the duplicate Klaviyo section.

**Do not modify:**

- `shopify-theme/templates/product.json`
- `shopify-theme/templates/collection.json`
- `shopify-theme/templates/cart.json`
- `shopify-theme/sections/main-product.liquid`
- `shopify-theme/sections/main-cart-items.liquid`
- `shopify-theme/sections/main-cart-footer.liquid`
- `shopify-theme/snippets/cart-drawer.liquid`
- GemPages layouts/templates or locale files

---

### Task 1: Add a Theme Regression Harness and Shared Shell

**Files:**

- Create: `tests/test_shopify_theme.py`
- Create: `shopify-theme/assets/postgame-content.css`
- Create: `shopify-theme/assets/postgame-content.js`
- Modify: `shopify-theme/layout/theme.liquid:31-39,258-266,301-313`

**Interfaces:**

- Consumes: Spotlight's existing `#MainContent`, theme color variables, and Shopify's `Shopify.analytics.publish` API.
- Produces: body attributes `data-postgame-content-type` and `data-postgame-content-id`; ratings-frame hook `[data-postgame-ratings-frame]`; custom event payload `{content_type, content_identifier, product_handle}`.

- [ ] **Step 1: Write the failing shared-shell tests**

Create `tests/test_shopify_theme.py` with this complete initial content:

```python
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "shopify-theme"


def text(relative):
    return (THEME / relative).read_text(encoding="utf-8")


def data(relative):
    return json.loads(text(relative))


class ShopifyThemeTests(unittest.TestCase):
    COMMERCE_HASHES = {
        "templates/product.json": "3ccc3a33ef1f95be8b4b8673ea22492ead4d13df54adc3a6e69e9b7fcf4da42d",
        "templates/collection.json": "5de97ba28f7245538cca35deda4c7183329226826f7f65f2d8a4343e34bcb42a",
        "templates/cart.json": "4f75bd249c0c720acba10768f0c80c8af79d9b1903c02706e70fb5f693b70ec7",
        "sections/main-product.liquid": "b165c0b41605fbaf73ac0a0221f3963367c59b13f832e6ab971963cd7e7b217f",
        "sections/main-cart-items.liquid": "8f68b4939841f6e17a650d17af7378cf59951df78b97b7c38353f23fe9518da6",
        "sections/main-cart-footer.liquid": "172a57669d38ede33919ad7f826bd1161e5f7256e99903934d55cb3035783122",
        "snippets/cart-drawer.liquid": "1a906b54b52cc75c81580fb279a42fccfdccc46fe5edd5e90b5e615c3d9e76f5",
    }

    def test_commerce_files_match_captured_baseline(self):
        for relative, expected in self.COMMERCE_HASHES.items():
            digest = hashlib.sha256((THEME / relative).read_bytes()).hexdigest()
            self.assertEqual(expected, digest, relative)

    def test_shared_assets_are_loaded_once(self):
        layout = text("layout/theme.liquid")
        self.assertEqual(1, layout.count("postgame-content.css"))
        self.assertEqual(1, layout.count("postgame-content.js"))
        self.assertIn("data-postgame-content-type", layout)
        self.assertIn("data-postgame-content-id", layout)

    def test_custom_event_has_exact_contract(self):
        script = text("assets/postgame-content.js")
        self.assertIn("postgame_content_product_click", script)
        for field in ("content_type", "content_identifier", "product_handle"):
            self.assertIn(field, script)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify the new shell is absent**

Run: `python -m unittest tests.test_shopify_theme -v`

Expected: commerce hash test passes; asset-loading and event-contract tests fail because the new assets are not present.

- [ ] **Step 3: Add the minimal shared assets**

Create `shopify-theme/assets/postgame-content.js`:

```javascript
(() => {
  'use strict';

  function publishProductClick(event) {
    const link = event.target.closest('#MainContent a[href*="/products/"]');
    if (!link) return;

    const body = document.body;
    const contentType = body.dataset.postgameContentType;
    const contentIdentifier = body.dataset.postgameContentId;
    if (!contentType || !contentIdentifier) return;

    const url = new URL(link.href, window.location.origin);
    const match = url.pathname.match(/^\/products\/([^/]+)\/?$/);
    if (!match || !window.Shopify?.analytics?.publish) return;

    window.Shopify.analytics.publish('postgame_content_product_click', {
      content_type: contentType,
      content_identifier: contentIdentifier,
      product_handle: decodeURIComponent(match[1]),
    }).catch(() => {});
  }

  function installRatingsBridge(frame) {
    const origin = new URL(frame.src).origin;

    function sendViewport() {
      const rect = frame.getBoundingClientRect();
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      frame.contentWindow?.postMessage({
        type: 'npr:viewport',
        top: Math.max(0, -rect.top),
        height: Math.max(0, Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0)),
      }, origin);
    }

    window.addEventListener('message', (event) => {
      if (event.source !== frame.contentWindow || event.origin !== origin || !event.data) return;
      if (event.data.type === 'npr:height') {
        const height = Number(event.data.height);
        if (Number.isFinite(height) && height >= 400 && height <= 30000) {
          frame.style.height = `${Math.ceil(height)}px`;
        }
      }
      if (event.data.type === 'npr:ready') sendViewport();
    });

    window.addEventListener('scroll', sendViewport, { passive: true });
    window.addEventListener('resize', sendViewport);
  }

  document.addEventListener('click', publishProductClick);
  document.querySelectorAll('[data-postgame-ratings-frame]').forEach(installRatingsBridge);
})();
```

Create `shopify-theme/assets/postgame-content.css`:

```css
.postgame-shell {
  width: min(100% - 3rem, 120rem);
  margin-inline: auto;
}

.postgame-kicker,
.postgame-meta {
  color: #384f6f;
  font-size: 1.4rem;
  letter-spacing: 0.04em;
}

.postgame-grid {
  display: grid;
  gap: 2.4rem;
}

.postgame-card,
.postgame-takeaway {
  border: 0.1rem solid rgba(56, 79, 111, 0.25);
  border-radius: 0.8rem;
  padding: 2rem;
}

.postgame-ratings-frame {
  display: block;
  width: 100%;
  min-height: 160rem;
  border: 0;
}

.postgame-shell a:focus-visible,
.postgame-shell button:focus-visible {
  outline: 0.3rem solid #384f6f;
  outline-offset: 0.3rem;
}

@media screen and (min-width: 750px) {
  .postgame-grid--3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .postgame-grid--5 { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}

@media screen and (max-width: 749px) {
  .postgame-shell { width: min(100% - 2rem, 120rem); }
  .postgame-grid--5 { grid-template-columns: 1fr; }
}
```

In `shopify-theme/layout/theme.liquid`, add the deferred script beside the existing global scripts, add the stylesheet after `base.css`, and replace the opening body tag with:

```liquid
<body
  class="gradient{% if settings.animations_hover_elements != 'none' %} animate--hover-{{ settings.animations_hover_elements }}{% endif %}"
  {% if template.name == 'index' %}
    data-postgame-content-type="homepage"
    data-postgame-content-id="home"
  {% elsif template.name == 'article' %}
    data-postgame-content-type="article"
    data-postgame-content-id="{{ article.handle | escape }}"
  {% endif %}
>
```

Use exactly these asset tags:

```liquid
<script src="{{ 'postgame-content.js' | asset_url }}" defer="defer"></script>
{{ 'postgame-content.css' | asset_url | stylesheet_tag }}
```

- [ ] **Step 4: Run the shell tests**

Run: `python -m unittest tests.test_shopify_theme -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_shopify_theme.py shopify-theme/assets/postgame-content.css shopify-theme/assets/postgame-content.js shopify-theme/layout/theme.liquid
git commit -m "Add content theme shell and regression checks"
```

---

### Task 2: Build the Content-First Homepage

**Files:**

- Create: `shopify-theme/sections/postgame-featured-story.liquid`
- Create: `shopify-theme/sections/postgame-ratings-preview.liquid`
- Create: `shopify-theme/sections/postgame-tagged-articles.liquid`
- Modify: `shopify-theme/templates/index.json:1`
- Modify: `tests/test_shopify_theme.py`

**Interfaces:**

- Consumes: one selected Shopify article; one reviewed five-row ratings edition; the `poweratings` blog during preview; tags `nfl`, `dynasty`, and `dfs`; existing `best-sellers` collection; existing Klaviyo form block `WzBS2Z`.
- Produces: homepage order `featured story → ratings preview → analysis → fantasy → accountability → merchandise → email`.

- [ ] **Step 1: Add a failing homepage-order test**

Add this method to `ShopifyThemeTests`:

```python
    def test_homepage_has_required_content_first_order(self):
        template = data("templates/index.json")
        enabled = [
            template["sections"][section_id]["type"]
            for section_id in template["order"]
            if not template["sections"][section_id].get("disabled", False)
        ]
        self.assertEqual(
            [
                "postgame-featured-story",
                "postgame-ratings-preview",
                "postgame-tagged-articles",
                "postgame-tagged-articles",
                "rich-text",
                "featured-collection",
                "apps",
            ],
            enabled,
        )
```

- [ ] **Step 2: Run the test and verify the commerce-first baseline fails**

Run: `python -m unittest tests.test_shopify_theme.ShopifyThemeTests.test_homepage_has_required_content_first_order -v`

Expected: FAIL; the actual first enabled section is `slideshow`.

- [ ] **Step 3: Create the three focused homepage sections**

Implement `postgame-featured-story.liquid` so it renders nothing when `section.settings.article` is blank. When selected, render one `<h1>`, article image, excerpt, author, published time, optional `article.metafields.custom.updated_at`, and a link to the article. Its schema has one `article` setting and one `color_scheme` setting.

Use this complete file:

```liquid
{%- liquid
  assign featured_article = section.settings.article
  assign featured_teaser = featured_article.excerpt
  if featured_teaser == blank
    assign featured_teaser = featured_article.content
  endif
-%}
{%- if featured_article != blank -%}
  <section class="postgame-shell color-{{ section.settings.color_scheme }} gradient">
    <article class="postgame-featured-story">
      {%- if featured_article.image -%}
        <a href="{{ featured_article.url }}" aria-label="{{ featured_article.title | escape }}">
          {{ featured_article.image | image_url: width: 1600 | image_tag: loading: 'eager', widths: '375, 750, 1100, 1500, 1600', alt: featured_article.image.alt }}
        </a>
      {%- endif -%}
      <div class="postgame-featured-story__content">
        <p class="postgame-kicker">Latest analysis</p>
        <h1><a href="{{ featured_article.url }}">{{ featured_article.title | escape }}</a></h1>
        <p class="postgame-meta">
          By {{ featured_article.metafields.custom.byline.value | default: featured_article.author | escape }}
          · Published {{ featured_article.published_at | time_tag: format: 'date' }}
          {%- if featured_article.metafields.custom.updated_at.value != blank -%}
            · Updated {{ featured_article.metafields.custom.updated_at.value | time_tag: format: 'date_at_time' }}
          {%- endif -%}
        </p>
        <div class="rte">
          {{ featured_teaser | strip_html | truncatewords: 42 }}
        </div>
        <a class="button" href="{{ featured_article.url }}">Read the analysis</a>
      </div>
    </article>
  </section>
{%- endif -%}

{% schema %}
{
  "name": "Postgame featured story",
  "settings": [
    { "type": "article", "id": "article", "label": "Featured article" },
    { "type": "color_scheme", "id": "color_scheme", "label": "Color scheme", "default": "scheme-1" }
  ],
  "presets": [{ "name": "Postgame featured story" }]
}
{% endschema %}
```

Implement `postgame-tagged-articles.liquid` so it accepts `heading`, `blog`, `required_tag`, optional `alternate_tag`, and `limit`; loops through `section.settings.blog.articles`; renders only articles whose tags contain the required tag or the nonblank alternate tag; skips output entirely if zero articles match; and uses the existing `article-card` snippet with date and author enabled. Cap `limit` at 6.

Use this complete file:

```liquid
{{ 'component-article-card.css' | asset_url | stylesheet_tag }}
{{ 'component-card.css' | asset_url | stylesheet_tag }}

{%- liquid
  assign matching_count = 0
  for candidate in section.settings.blog.articles
    assign candidate_matches = false
    if candidate.tags contains section.settings.required_tag
      assign candidate_matches = true
    elsif section.settings.alternate_tag != blank and candidate.tags contains section.settings.alternate_tag
      assign candidate_matches = true
    endif
    if candidate_matches
      assign matching_count = matching_count | plus: 1
      if matching_count >= section.settings.limit
        break
      endif
    endif
  endfor
-%}

{%- if matching_count > 0 -%}
  <section class="postgame-shell">
    <h2>{{ section.settings.heading | escape }}</h2>
    <div class="postgame-grid postgame-grid--3">
      {%- assign rendered_count = 0 -%}
      {%- for candidate in section.settings.blog.articles -%}
        {%- liquid
          assign candidate_matches = false
          if candidate.tags contains section.settings.required_tag
            assign candidate_matches = true
          elsif section.settings.alternate_tag != blank and candidate.tags contains section.settings.alternate_tag
            assign candidate_matches = true
          endif
        -%}
        {%- if candidate_matches -%}
          <article class="postgame-card">
            {%- render 'article-card',
              article: candidate,
              media_height: 'medium',
              media_aspect_ratio: candidate.image.aspect_ratio,
              show_image: true,
              show_date: true,
              show_author: true,
              show_excerpt: true
            -%}
          </article>
          {%- assign rendered_count = rendered_count | plus: 1 -%}
          {%- if rendered_count >= section.settings.limit -%}{%- break -%}{%- endif -%}
        {%- endif -%}
      {%- endfor -%}
    </div>
  </section>
{%- endif -%}

{% schema %}
{
  "name": "Postgame tagged articles",
  "settings": [
    { "type": "text", "id": "heading", "label": "Heading", "default": "Latest analysis" },
    { "type": "blog", "id": "blog", "label": "Blog" },
    { "type": "text", "id": "required_tag", "label": "Required tag", "default": "nfl" },
    { "type": "text", "id": "alternate_tag", "label": "Alternate tag" },
    { "type": "range", "id": "limit", "label": "Article limit", "min": 1, "max": 6, "step": 1, "default": 3 }
  ],
  "presets": [{ "name": "Postgame tagged articles" }]
}
{% endschema %}
```

Implement `postgame-ratings-preview.liquid` with this fail-closed gate before any markup:

```liquid
{%- liquid
  assign release_ready = true
  if section.settings.edition == blank or section.settings.author == blank or section.settings.published_at == blank
    assign release_ready = false
  endif
  if section.blocks.size != 5
    assign release_ready = false
  endif
  for block in section.blocks
    if block.settings.ordinal == blank or block.settings.team == blank or block.settings.rating == blank or block.settings.movement == blank
      assign release_ready = false
    endif
  endfor
-%}
```

When `release_ready` is true, render a section headed `NFL Power Ratings`, the edition, author, published time, this exact definition — `Rating points represent neutral-field strength versus a league-average team.` — and five ordered cards. Each card shows the ordinal, team, signed rating, and text movement. End with a link to `/pages/power-ratings`. The schema must allow exactly five `team` blocks and no preset blocks.

Use the gate above followed by this complete markup/schema:

```liquid
{%- if release_ready -%}
  <section class="postgame-shell" aria-labelledby="ratings-preview-{{ section.id }}">
    <p class="postgame-kicker">{{ section.settings.edition | escape }}</p>
    <h2 id="ratings-preview-{{ section.id }}">NFL Power Ratings</h2>
    <p class="postgame-meta">By {{ section.settings.author | escape }} · Published {{ section.settings.published_at | escape }}</p>
    <p>Rating points represent neutral-field strength versus a league-average team.</p>
    <ol class="postgame-grid postgame-grid--5">
      {%- for block in section.blocks -%}
        <li class="postgame-card" {{ block.shopify_attributes }}>
          <span>{{ block.settings.ordinal | escape }}</span>
          <strong>{{ block.settings.team | escape }}</strong>
          <span>Rating {{ block.settings.rating | escape }}</span>
          <span>Movement {{ block.settings.movement | escape }}</span>
        </li>
      {%- endfor -%}
    </ol>
    <a class="button" href="/pages/power-ratings">View all 32 teams</a>
  </section>
{%- endif -%}

{% schema %}
{
  "name": "Postgame ratings preview",
  "max_blocks": 5,
  "settings": [
    { "type": "text", "id": "edition", "label": "Edition" },
    { "type": "text", "id": "author", "label": "Author" },
    { "type": "text", "id": "published_at", "label": "Published time" }
  ],
  "blocks": [
    {
      "type": "team",
      "name": "Reviewed team",
      "settings": [
        { "type": "text", "id": "ordinal", "label": "Ordinal" },
        { "type": "text", "id": "team", "label": "Team" },
        { "type": "text", "id": "rating", "label": "Signed rating" },
        { "type": "text", "id": "movement", "label": "Movement text" }
      ]
    }
  ],
  "presets": [{ "name": "Postgame ratings preview" }]
}
{% endschema %}
```

- [ ] **Step 4: Replace the homepage JSON with the exact preview composition**

Set `shopify-theme/templates/index.json` to seven enabled sections in this order:

1. `postgame-featured-story` with an intentionally blank article selector so no unreviewed story is implied.
2. `postgame-ratings-preview` with blank edition metadata and no blocks so ratings remain fail-closed.
3. `postgame-tagged-articles` titled `Latest analysis`, blog `poweratings`, required tag `nfl`, limit 3.
4. `postgame-tagged-articles` titled `Dynasty & DFS`, blog `poweratings`, required tag `dynasty`, alternate tag `dfs`, limit 4.
5. Native `rich-text` titled `Accountability`, with copy `Every public edition is reviewed, timestamped, and preserved.` and a button to `/pages/accountability` labeled `Open the ledger`.
6. Native `featured-collection` titled `From the Outlet`, description `Merch supports the work.`, collection `best-sellers`, 4 products, 4 desktop columns, 2 mobile columns, no quick add, no slider.
7. The existing Klaviyo `apps` section using form block type `shopify://apps/klaviyo-email-marketing-sms/blocks/form-embed-block/2632fe16-c075-4321-a88b-50b567f42507` and `formId` `klaviyo-form-WzBS2Z`.

Use this complete JSON shape; keep the selected article and ratings release data intentionally empty until Task 7:

```json
{
  "sections": {
    "featured_story": {
      "type": "postgame-featured-story",
      "settings": { "article": "", "color_scheme": "scheme-1" }
    },
    "ratings_preview": {
      "type": "postgame-ratings-preview",
      "settings": { "edition": "", "author": "", "published_at": "" }
    },
    "latest_analysis": {
      "type": "postgame-tagged-articles",
      "settings": {
        "heading": "Latest analysis",
        "blog": "poweratings",
        "required_tag": "nfl",
        "alternate_tag": "",
        "limit": 3
      }
    },
    "fantasy": {
      "type": "postgame-tagged-articles",
      "settings": {
        "heading": "Dynasty & DFS",
        "blog": "poweratings",
        "required_tag": "dynasty",
        "alternate_tag": "dfs",
        "limit": 4
      }
    },
    "accountability": {
      "type": "rich-text",
      "blocks": {
        "heading": { "type": "heading", "settings": { "heading": "Accountability", "heading_size": "h1" } },
        "text": { "type": "text", "settings": { "text": "<p>Every public edition is reviewed, timestamped, and preserved.</p>" } },
        "button": {
          "type": "button",
          "settings": {
            "button_label": "Open the ledger",
            "button_link": "/pages/accountability",
            "button_style_secondary": true,
            "button_label_2": "",
            "button_link_2": "",
            "button_style_secondary_2": false
          }
        }
      },
      "block_order": ["heading", "text", "button"],
      "settings": {
        "desktop_content_position": "center",
        "content_alignment": "center",
        "color_scheme": "scheme-1",
        "full_width": true,
        "padding_top": 36,
        "padding_bottom": 36
      }
    },
    "merch": {
      "type": "featured-collection",
      "settings": {
        "title": "From the Outlet",
        "heading_size": "h1",
        "description": "<p>Merch supports the work.</p>",
        "show_description": true,
        "description_style": "body",
        "collection": "best-sellers",
        "products_to_show": 4,
        "columns_desktop": 4,
        "full_width": false,
        "show_view_all": true,
        "view_all_style": "outline",
        "enable_desktop_slider": false,
        "color_scheme": "scheme-1",
        "image_ratio": "square",
        "image_shape": "default",
        "show_secondary_image": true,
        "show_vendor": false,
        "show_rating": false,
        "quick_add": "none",
        "columns_mobile": "2",
        "swipe_on_mobile": false,
        "padding_top": 36,
        "padding_bottom": 36
      }
    },
    "email": {
      "type": "apps",
      "blocks": {
        "klaviyo": {
          "type": "shopify://apps/klaviyo-email-marketing-sms/blocks/form-embed-block/2632fe16-c075-4321-a88b-50b567f42507",
          "settings": { "formId": "klaviyo-form-WzBS2Z" }
        }
      },
      "block_order": ["klaviyo"],
      "settings": { "include_margins": true }
    }
  },
  "order": ["featured_story", "ratings_preview", "latest_analysis", "fantasy", "accountability", "merch", "email"]
}
```

Delete the old slideshow, collection list, 12-product grids, image promotion, and disabled expired-sale sections from the new homepage template. They remain recoverable in baseline commit `f786980`.

- [ ] **Step 5: Run structural checks**

Run: `python -m unittest tests.test_shopify_theme -v`

Expected: 4 tests pass; the commerce hashes remain unchanged.

Run: `npx --yes @shopify/cli@latest theme check --path shopify-theme --fail-level error --output json > theme-check-after-home.json`

Expected: exit 1 from recorded baseline debt, with no finding whose path is one of the three new sections or `templates/index.json`.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_shopify_theme.py shopify-theme/sections/postgame-featured-story.liquid shopify-theme/sections/postgame-ratings-preview.liquid shopify-theme/sections/postgame-tagged-articles.liquid shopify-theme/templates/index.json
git commit -m "Build content-first Shopify homepage"
```

---

### Task 3: Add Native Power Ratings Context and the Trusted Embed

**Files:**

- Create: `shopify-theme/sections/postgame-ratings.liquid`
- Create: `shopify-theme/templates/page.power-ratings.json`
- Modify: `tests/test_shopify_theme.py`

**Interfaces:**

- Consumes: approved ratings artifact at `https://walshja9.github.io/Postgame_Outlet/`; message types `npr:height`, `npr:ready`, and `npr:viewport`; page title; section-configured edition metadata.
- Produces: one native H1, crawlable rating definition and summary, methodology/accountability links, and an auto-height iframe titled `NFL Power Ratings`.

- [ ] **Step 1: Add a failing ratings-template test**

Add this method:

```python
    def test_power_ratings_template_has_native_context_before_embed(self):
        template = data("templates/page.power-ratings.json")
        self.assertEqual(["main"], template["order"])
        self.assertEqual("postgame-ratings", template["sections"]["main"]["type"])
        section = text("sections/postgame-ratings.liquid")
        self.assertLess(section.index("<h1"), section.index("<iframe"))
        self.assertIn("data-postgame-ratings-frame", section)
        self.assertIn("https://walshja9.github.io/Postgame_Outlet/", section)
```

- [ ] **Step 2: Run the new test and verify the template is absent**

Run: `python -m unittest tests.test_shopify_theme.ShopifyThemeTests.test_power_ratings_template_has_native_context_before_embed -v`

Expected: ERROR because `templates/page.power-ratings.json` does not exist.

- [ ] **Step 3: Implement the ratings section**

Create `postgame-ratings.liquid` with:

- `<h1>{{ page.title | escape }}</h1>`.
- Kicker `NFL · {{ section.settings.edition }}` only when edition is nonblank.
- Named author, published time, and updated time only when each is nonblank.
- This exact definition before the iframe: `A Power Rating estimates how many points stronger or weaker a team is than a league-average team on a neutral field.`
- A rich-text `summary` setting.
- Links to `/pages/methodology` and `/pages/accountability`.
- An iframe only when `show_embed` is true and `ratings_url` is nonblank.

Use this iframe markup:

```liquid
<iframe
  class="postgame-ratings-frame"
  src="{{ section.settings.ratings_url | escape }}"
  title="NFL Power Ratings"
  loading="eager"
  data-postgame-ratings-frame
></iframe>
```

Its schema defaults `ratings_url` to `https://walshja9.github.io/Postgame_Outlet/`, `show_embed` to true, and leaves edition, author, dates, and summary blank for reviewed editorial input.

Use this complete file:

```liquid
<section class="postgame-shell postgame-ratings" aria-labelledby="ratings-title-{{ section.id }}">
  {%- if section.settings.edition != blank -%}
    <p class="postgame-kicker">NFL · {{ section.settings.edition | escape }}</p>
  {%- endif -%}
  <h1 id="ratings-title-{{ section.id }}">{{ page.title | escape }}</h1>
  {%- if section.settings.author != blank or section.settings.published_at != blank or section.settings.updated_at != blank -%}
    <p class="postgame-meta">
      {%- if section.settings.author != blank -%}By {{ section.settings.author | escape }}{%- endif -%}
      {%- if section.settings.published_at != blank -%} · Published {{ section.settings.published_at | escape }}{%- endif -%}
      {%- if section.settings.updated_at != blank -%} · Updated {{ section.settings.updated_at | escape }}{%- endif -%}
    </p>
  {%- endif -%}
  <p>A Power Rating estimates how many points stronger or weaker a team is than a league-average team on a neutral field.</p>
  {%- if section.settings.summary != blank -%}<div class="rte">{{ section.settings.summary }}</div>{%- endif -%}
  <p>
    <a href="/pages/methodology">Methodology</a>
    <span aria-hidden="true"> · </span>
    <a href="/pages/accountability">Corrections and accountability</a>
  </p>
  {%- if section.settings.show_embed and section.settings.ratings_url != blank -%}
    <iframe
      class="postgame-ratings-frame"
      src="{{ section.settings.ratings_url | escape }}"
      title="NFL Power Ratings"
      loading="eager"
      data-postgame-ratings-frame
    ></iframe>
  {%- endif -%}
</section>

{% schema %}
{
  "name": "Postgame Power Ratings",
  "settings": [
    { "type": "text", "id": "edition", "label": "Edition" },
    { "type": "text", "id": "author", "label": "Author" },
    { "type": "text", "id": "published_at", "label": "Published time" },
    { "type": "text", "id": "updated_at", "label": "Updated time" },
    { "type": "richtext", "id": "summary", "label": "Current-edition summary" },
    { "type": "url", "id": "ratings_url", "label": "Ratings application URL", "default": "https://walshja9.github.io/Postgame_Outlet/" },
    { "type": "checkbox", "id": "show_embed", "label": "Show ratings application", "default": true }
  ],
  "presets": [{ "name": "Postgame Power Ratings" }]
}
{% endschema %}
```

- [ ] **Step 4: Add the alternate JSON template**

Create `templates/page.power-ratings.json` with a single `main` section of type `postgame-ratings`. Set `ratings_url` to the GitHub Pages URL, `show_embed` true, and leave edition-specific fields blank. The section still renders the native title, definition, and policy links; the final preview gate requires the edition fields and summary to be populated in the duplicate theme editor.

Use this complete file:

```json
{
  "sections": {
    "main": {
      "type": "postgame-ratings",
      "settings": {
        "edition": "",
        "author": "",
        "published_at": "",
        "updated_at": "",
        "summary": "",
        "ratings_url": "https://walshja9.github.io/Postgame_Outlet/",
        "show_embed": true
      }
    }
  },
  "order": ["main"]
}
```

- [ ] **Step 5: Verify**

Run: `python -m unittest tests.test_shopify_theme -v`

Expected: 5 tests pass.

Run Theme Check and confirm no new finding in `postgame-ratings.liquid` or `page.power-ratings.json`.

Manually open the alternate-template preview and verify the iframe accepts height messages only from `https://walshja9.github.io`, has no inner scrollbar after load, and the ratings drawer remains pinned to the visible viewport.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_shopify_theme.py shopify-theme/sections/postgame-ratings.liquid shopify-theme/templates/page.power-ratings.json
git commit -m "Add native Power Ratings page integration"
```

---

### Task 4: Add Fantasy Editorial Lanes Without Empty Tools

**Files:**

- Create: `shopify-theme/templates/page.fantasy.json`
- Modify: `tests/test_shopify_theme.py`

**Interfaces:**

- Consumes: the existing `main-page` section, one analysis blog, and `postgame-tagged-articles` from Task 2.
- Produces: a native page introduction followed by independently hidden Dynasty and DFS lanes.

- [ ] **Step 1: Add the failing fantasy-template test**

```python
    def test_fantasy_template_has_two_editorial_lanes(self):
        template = data("templates/page.fantasy.json")
        types = [template["sections"][key]["type"] for key in template["order"]]
        self.assertEqual(["main-page", "postgame-tagged-articles", "postgame-tagged-articles"], types)
        self.assertEqual("dynasty", template["sections"]["dynasty"]["settings"]["required_tag"])
        self.assertEqual("dfs", template["sections"]["dfs"]["settings"]["required_tag"])
```

- [ ] **Step 2: Run the test and verify the template is absent**

Run: `python -m unittest tests.test_shopify_theme.ShopifyThemeTests.test_fantasy_template_has_two_editorial_lanes -v`

Expected: ERROR because `page.fantasy.json` does not exist.

- [ ] **Step 3: Create the Fantasy template**

Create `page.fantasy.json` with:

- `main`: standard `main-page`, padding top 36 and bottom 20; the page title/body supply the one H1 and intro.
- `dynasty`: `postgame-tagged-articles`, heading `Dynasty`, blog `poweratings`, required tag `dynasty`, limit 3.
- `dfs`: `postgame-tagged-articles`, heading `DFS`, blog `poweratings`, required tag `dfs`, limit 3.
- Order: `main`, `dynasty`, `dfs`.

Because the shared tagged section renders nothing when it has no matching articles, the page cannot display an empty assistant, league-sync, integration, or model interface.

Use this complete file:

```json
{
  "sections": {
    "main": {
      "type": "main-page",
      "settings": { "padding_top": 36, "padding_bottom": 20 }
    },
    "dynasty": {
      "type": "postgame-tagged-articles",
      "settings": {
        "heading": "Dynasty",
        "blog": "poweratings",
        "required_tag": "dynasty",
        "alternate_tag": "",
        "limit": 3
      }
    },
    "dfs": {
      "type": "postgame-tagged-articles",
      "settings": {
        "heading": "DFS",
        "blog": "poweratings",
        "required_tag": "dfs",
        "alternate_tag": "",
        "limit": 3
      }
    }
  },
  "order": ["main", "dynasty", "dfs"]
}
```

- [ ] **Step 4: Verify and commit**

Run: `python -m unittest tests.test_shopify_theme -v`

Expected: 6 tests pass.

```powershell
git add tests/test_shopify_theme.py shopify-theme/templates/page.fantasy.json
git commit -m "Add Dynasty and DFS editorial landing template"
```

---

### Task 5: Add Article Trust Metadata, Related Analysis, and One Product

**Files:**

- Create: `shopify-theme/snippets/postgame-article-meta.liquid`
- Create: `shopify-theme/snippets/postgame-article-footer.liquid`
- Create: `shopify-theme/sections/postgame-related-analysis.liquid`
- Create: `shopify-theme/sections/postgame-related-product.liquid`
- Modify: `shopify-theme/sections/main-article.liquid:44-72`
- Modify: `shopify-theme/templates/article.json:1`
- Modify: `shopify-theme/templates/blog.json:1`
- Modify: `tests/test_shopify_theme.py`

**Interfaces:**

- Consumes article metafields:
  - `custom.deck` — single-line text
  - `custom.byline` — single-line text, falling back to `article.author`
  - `custom.updated_at` — date and time
  - `custom.model_version` — single-line text
  - `custom.key_takeaway` — multi-line text
  - `custom.sources` — rich text
  - `custom.methodology` — page reference
  - `custom.correction_history` — rich text
  - `custom.related_product` — product reference
- Produces visible trust metadata, related analysis, and zero or one tracked product card.

- [ ] **Step 1: Add failing article-contract tests**

```python
    def test_article_template_exposes_trust_metadata(self):
        article = text("sections/main-article.liquid")
        self.assertIn("render 'postgame-article-meta'", article)
        self.assertIn("render 'postgame-article-footer'", article)
        meta = text("snippets/postgame-article-meta.liquid")
        for key in ("custom.deck", "custom.byline", "custom.updated_at", "custom.model_version", "custom.key_takeaway"):
            self.assertIn(key, meta)
        footer = text("snippets/postgame-article-footer.liquid")
        for key in ("custom.sources", "custom.methodology", "custom.correction_history"):
            self.assertIn(key, footer)

    def test_article_has_one_optional_product_section(self):
        template = data("templates/article.json")
        product_sections = [
            value for value in template["sections"].values()
            if value["type"] == "postgame-related-product"
        ]
        self.assertEqual(1, len(product_sections))
        self.assertIn("custom.related_product", text("sections/postgame-related-product.liquid"))
```

- [ ] **Step 2: Run the tests and verify the snippets/section are absent**

Run both new tests with `python -m unittest ... -v`.

Expected: failures for missing render calls and files.

- [ ] **Step 3: Implement article metadata snippets**

`postgame-article-meta.liquid` must:

- Render the deck as a paragraph when nonblank.
- Render `By {{ custom.byline | default: article.author }}`.
- Always render `Published` with `article.published_at`.
- Render `Updated` and `Model/data version` only when their metafields are nonblank.
- Render the key takeaway in an `<aside class="postgame-takeaway" aria-label="Key takeaway">`.

`postgame-article-footer.liquid` must render separate `<section>` elements for Sources, Methodology, and Correction history only when the corresponding metafield is nonblank. Link the page-reference metafield using its `.url` and `.title` values. Do not render empty headings.

Use this complete `postgame-article-meta.liquid`:

```liquid
{%- liquid
  assign deck = article.metafields.custom.deck.value
  assign byline = article.metafields.custom.byline.value | default: article.author
  assign updated_at = article.metafields.custom.updated_at.value
  assign model_version = article.metafields.custom.model_version.value
  assign key_takeaway = article.metafields.custom.key_takeaway.value
-%}
{%- if deck != blank -%}<p class="postgame-article-deck">{{ deck | escape }}</p>{%- endif -%}
<p class="postgame-meta">
  By {{ byline | escape }}
  · Published {{ article.published_at | time_tag: format: 'date_at_time' }}
  {%- if updated_at != blank -%} · Updated {{ updated_at | time_tag: format: 'date_at_time' }}{%- endif -%}
  {%- if model_version != blank -%} · Model/data version {{ model_version | escape }}{%- endif -%}
</p>
{%- if key_takeaway != blank -%}
  <aside class="postgame-takeaway" aria-label="Key takeaway">
    <strong>Key takeaway</strong>
    <p>{{ key_takeaway | escape | newline_to_br }}</p>
  </aside>
{%- endif -%}
```

Use this complete `postgame-article-footer.liquid`:

```liquid
{%- liquid
  assign sources = article.metafields.custom.sources
  assign methodology = article.metafields.custom.methodology.value
  assign correction_history = article.metafields.custom.correction_history
-%}
{%- if sources.value != blank -%}
  <section aria-labelledby="article-sources"><h2 id="article-sources">Sources</h2>{{ sources | metafield_tag }}</section>
{%- endif -%}
{%- if methodology != blank -%}
  <section aria-labelledby="article-methodology">
    <h2 id="article-methodology">Methodology</h2>
    <p><a href="{{ methodology.url }}">{{ methodology.title | escape }}</a></p>
  </section>
{%- endif -%}
{%- if correction_history.value != blank -%}
  <section aria-labelledby="article-corrections"><h2 id="article-corrections">Correction history</h2>{{ correction_history | metafield_tag }}</section>
{%- endif -%}
```

In `main-article.liquid`, replace the current date/optional-author spans inside the title block with `{% render 'postgame-article-meta', article: article %}`. After `{{ article.content }}`, render `{% render 'postgame-article-footer', article: article %}`.

The changed title/content fragments must be exactly:

```liquid
<h1 class="article-template__title">{{ article.title | escape }}</h1>
{% render 'postgame-article-meta', article: article %}
```

```liquid
<div
  class="article-template__content page-width page-width--narrow rte{% if settings.animations_reveal_on_scroll %} scroll-trigger animate--slide-in{% endif %}"
  {{ block.shopify_attributes }}
>
  {{ article.content }}
  {% render 'postgame-article-footer', article: article %}
</div>
```

- [ ] **Step 4: Implement related analysis and product sections**

`postgame-related-analysis.liquid` loops over `blog.articles`, skips the current article, and renders up to three articles sharing at least one tag with the current article. Use `article-card` with image, date, and author enabled. Render nothing if no related item exists.

Use this complete file:

```liquid
{{ 'component-article-card.css' | asset_url | stylesheet_tag }}
{{ 'component-card.css' | asset_url | stylesheet_tag }}
{%- liquid
  assign related_count = 0
  for candidate in blog.articles
    assign shares_tag = false
    if candidate.id != article.id
      for current_tag in article.tags
        if candidate.tags contains current_tag
          assign shares_tag = true
          break
        endif
      endfor
    endif
    if shares_tag
      assign related_count = related_count | plus: 1
      if related_count == 3
        break
      endif
    endif
  endfor
-%}
{%- if related_count > 0 -%}
  <section class="postgame-shell" aria-labelledby="related-analysis-{{ section.id }}">
    <h2 id="related-analysis-{{ section.id }}">Related analysis</h2>
    <div class="postgame-grid postgame-grid--3">
      {%- assign rendered_count = 0 -%}
      {%- for candidate in blog.articles -%}
        {%- liquid
          assign shares_tag = false
          if candidate.id != article.id
            for current_tag in article.tags
              if candidate.tags contains current_tag
                assign shares_tag = true
                break
              endif
            endfor
          endif
        -%}
        {%- if shares_tag -%}
          <article class="postgame-card">
            {%- render 'article-card', article: candidate, media_height: 'medium', media_aspect_ratio: candidate.image.aspect_ratio, show_image: true, show_date: true, show_author: true, show_excerpt: true -%}
          </article>
          {%- assign rendered_count = rendered_count | plus: 1 -%}
          {%- if rendered_count == 3 -%}{%- break -%}{%- endif -%}
        {%- endif -%}
      {%- endfor -%}
    </div>
  </section>
{%- endif -%}
{% schema %}
{ "name": "Postgame related analysis", "settings": [], "presets": [{ "name": "Postgame related analysis" }] }
{% endschema %}
```

`postgame-related-product.liquid` resolves:

```liquid
{% assign related_product = article.metafields.custom.related_product.value %}
```

If present, render heading `From the Outlet`, copy `Merch supports the work.`, and one existing `card-product` snippet. If absent, render nothing. Do not add quick-add behavior.

Use this complete file:

```liquid
{{ 'component-card.css' | asset_url | stylesheet_tag }}
{{ 'component-price.css' | asset_url | stylesheet_tag }}
{%- assign related_product = article.metafields.custom.related_product.value -%}
{%- if related_product != blank -%}
  <section class="postgame-shell" aria-labelledby="related-product-{{ section.id }}">
    <h2 id="related-product-{{ section.id }}">From the Outlet</h2>
    <p>Merch supports the work.</p>
    <div class="grid product-grid grid--1-col">
      <div class="grid__item">
        {%- render 'card-product',
          card_product: related_product,
          media_aspect_ratio: 'square',
          image_shape: 'default',
          show_secondary_image: true,
          show_vendor: false,
          show_rating: false,
          lazy_load: true,
          skip_styles: true,
          quick_add: 'none',
          section_id: section.id
        -%}
      </div>
    </div>
  </section>
{%- endif -%}
{% schema %}
{ "name": "Postgame related product", "settings": [], "presets": [{ "name": "Postgame related product" }] }
{% endschema %}
```

- [ ] **Step 5: Update article and blog JSON**

Keep the existing article block order `featured_image`, `title`, `share`, `content`; set `blog_show_date` and `blog_show_author` true. Add exactly one `postgame-related-analysis` section and one `postgame-related-product` section after `main`.

Change `templates/blog.json` to grid layout with image, date, and author enabled. Keep the existing main-blog implementation.

Use this complete `templates/article.json`:

```json
{
  "sections": {
    "main": {
      "type": "main-article",
      "blocks": {
        "featured_image": { "type": "featured_image", "settings": { "image_height": "adapt" } },
        "title": { "type": "title", "settings": { "blog_show_date": true, "blog_show_author": true } },
        "share": { "type": "share", "settings": { "share_label": "Share" } },
        "content": { "type": "content", "settings": {} }
      },
      "block_order": ["featured_image", "title", "share", "content"],
      "settings": {}
    },
    "related_analysis": { "type": "postgame-related-analysis", "settings": {} },
    "related_product": { "type": "postgame-related-product", "settings": {} }
  },
  "order": ["main", "related_analysis", "related_product"]
}
```

Use this complete `templates/blog.json`:

```json
{
  "sections": {
    "main": {
      "type": "main-blog",
      "settings": {
        "layout": "grid",
        "show_image": true,
        "image_height": "medium",
        "show_date": true,
        "show_author": true,
        "padding_top": 36,
        "padding_bottom": 36
      }
    }
  },
  "order": ["main"]
}
```

- [ ] **Step 6: Verify and commit**

Run: `python -m unittest tests.test_shopify_theme -v`

Expected: 8 tests pass.

Run Theme Check; no new finding may reference the two snippets, two sections, `main-article.liquid`, `article.json`, or `blog.json`.

```powershell
git add tests/test_shopify_theme.py shopify-theme/snippets/postgame-article-meta.liquid shopify-theme/snippets/postgame-article-footer.liquid shopify-theme/sections/postgame-related-analysis.liquid shopify-theme/sections/postgame-related-product.liquid shopify-theme/sections/main-article.liquid shopify-theme/templates/article.json shopify-theme/templates/blog.json
git commit -m "Add article trust and related content modules"
```

---

### Task 6: Stage Navigation, Footer, and Klaviyo Without Touching Live Menus

**Files:**

- Modify: `shopify-theme/sections/header-group.json:1`
- Modify: `shopify-theme/sections/footer-group.json:1`
- Modify: `tests/test_shopify_theme.py`

**Interfaces:**

- Consumes new unreferenced Shopify menus with handles `content-first-preview` and `content-footer-preview`; existing Klaviyo onsite embed and form `WzBS2Z`.
- Produces preview navigation `Home · Power Ratings · Fantasy · Shop`, a supporting footer, and one inline email form after homepage content.

- [ ] **Step 1: Create the two unreferenced menus in Shopify Admin**

Create `content-first-preview` with this exact order:

1. Home → `/`
2. Power Ratings → `/pages/power-ratings-preview`
3. Fantasy → `/pages/fantasy-preview`
4. Shop → `/collections/all`

Create `content-footer-preview` with:

1. Methodology → `/pages/methodology-preview`
2. Accountability → `/pages/accountability-preview`
3. Authors → `/pages/authors-preview`
4. Contact → `/pages/contact`
5. Ratings archives → `/blogs/poweratings`

These menus remain invisible to the live theme because no live section references them. At an approved cutover, change the preview-page targets to the canonical routes in the same controlled window; do not change the labels or order.

- [ ] **Step 2: Add failing menu tests**

```python
    def test_duplicate_theme_uses_preview_menus_and_one_klaviyo_form(self):
        header = data("sections/header-group.json")
        footer = data("sections/footer-group.json")
        self.assertEqual("content-first-preview", header["sections"]["header"]["settings"]["menu"])
        self.assertEqual("content-footer-preview", footer["sections"]["footer"]["blocks"]["content_links"]["settings"]["menu"])
        combined = json.dumps(data("templates/index.json")) + json.dumps(footer)
        self.assertEqual(1, combined.count("form-embed-block"))
```

- [ ] **Step 3: Run the test and verify current menus/duplicate form fail**

Run the new test.

Expected: FAIL because the header still uses `main-menu`, the footer has no link block, and the Klaviyo form appears in both homepage and footer groups.

- [ ] **Step 4: Change only the duplicate theme group JSON**

Set the header section's menu to `content-first-preview` and retain all other header settings.

In `footer-group.json`, delete the app section `17561845887a385770`. Add one footer block:

```json
{
  "content_links": {
    "type": "link_list",
    "settings": {
      "heading": "Explore",
      "menu": "content-footer-preview"
    }
  }
}
```

Set `block_order` to `["content_links"]`. Preserve payment icons, policy links, selectors, colors, and spacing.

The complete changed header group is:

```json
{
  "name": "t:sections.header.name",
  "type": "header",
  "sections": {
    "announcement_bar_YnH6gg": {
      "type": "announcement-bar",
      "blocks": {
        "announcement_CWhqA3": { "type": "announcement", "settings": { "text": "Free Shipping on orders over $50!", "link": "" } },
        "announcement_48WwUb": { "type": "announcement", "settings": { "text": "Not affiliated with the NBA, MLB, NHL, NFL, OR NCAA", "link": "" } }
      },
      "block_order": ["announcement_CWhqA3", "announcement_48WwUb"],
      "settings": {
        "color_scheme": "scheme-2",
        "show_line_separator": true,
        "show_social": false,
        "auto_rotate": true,
        "change_slides_speed": 3,
        "enable_country_selector": false,
        "enable_language_selector": false
      }
    },
    "header": {
      "type": "header",
      "settings": {
        "logo_position": "top-center",
        "menu": "content-first-preview",
        "menu_type_desktop": "dropdown",
        "sticky_header_type": "on-scroll-up",
        "show_line_separator": true,
        "color_scheme": "scheme-d0e50468-479c-48b5-abd4-e091b2b42030",
        "menu_color_scheme": "scheme-d0e50468-479c-48b5-abd4-e091b2b42030",
        "enable_country_selector": true,
        "enable_language_selector": true,
        "enable_customer_avatar": true,
        "mobile_logo_position": "center",
        "margin_bottom": 0,
        "padding_top": 12,
        "padding_bottom": 8
      }
    }
  },
  "order": ["announcement_bar_YnH6gg", "header"]
}
```

The complete changed footer group is:

```json
{
  "name": "t:sections.footer.name",
  "type": "footer",
  "sections": {
    "footer": {
      "type": "footer",
      "blocks": {
        "content_links": {
          "type": "link_list",
          "settings": { "heading": "Explore", "menu": "content-footer-preview" }
        }
      },
      "block_order": ["content_links"],
      "settings": {
        "color_scheme": "scheme-d0e50468-479c-48b5-abd4-e091b2b42030",
        "newsletter_enable": false,
        "newsletter_heading": "Subscribe to our emails",
        "enable_follow_on_shop": false,
        "show_social": false,
        "enable_country_selector": true,
        "enable_language_selector": true,
        "payment_enable": true,
        "show_policy": true,
        "margin_top": 0,
        "padding_top": 56,
        "padding_bottom": 52
      }
    }
  },
  "order": ["footer"]
}
```

- [ ] **Step 5: Configure Klaviyo behavior in preview/draft state**

Keep the existing onsite app embed enabled. Keep the inline homepage form at the end of useful content. In Klaviyo, clone the current welcome popup into a draft and set:

- Timing: based on rules.
- After 15 seconds.
- After 30% scroll.
- Require all timing rules.
- Show again 90 days after dismissal.
- Never show again after submission or URL-button action.
- Do not show to existing Klaviyo profiles.
- Allow dismissal on desktop and mobile.

Do not publish the cloned form before combined approval. Embedded forms remain inline and do not interrupt the reader.

- [ ] **Step 6: Verify and commit**

Run: `python -m unittest tests.test_shopify_theme -v`

Expected: 9 tests pass.

```powershell
git add tests/test_shopify_theme.py shopify-theme/sections/header-group.json shopify-theme/sections/footer-group.json
git commit -m "Stage content navigation and email placement"
```

---

### Task 7: Stage Shopify Content and Metafields Without Publishing

**Files:**

- No repository files change in this task.
- Shopify Admin draft/hidden resources only.

**Interfaces:**

- Consumes the alternate page templates and article metafield keys from Tasks 3–5.
- Produces reviewable draft content with no public URL or live-menu change.

- [ ] **Step 1: Create article metafield definitions**

In Shopify Admin → Settings → Custom data → Blog posts, create the nine `custom.*` definitions listed in Task 5 with the exact types stated there. Do not make any field required globally; the release checklist enforces completeness only for public editorial articles.

- [ ] **Step 2: Create hidden staging pages**

Create hidden pages titled `Power Ratings Preview`, `Fantasy Preview`, `Methodology Preview`, `Accountability Preview`, and `Authors Preview`. Use URL handles ending `-preview`. Their purpose is theme/content review, not launch routing.

Assign `page.power-ratings` to Power Ratings Preview and `page.fantasy` to Fantasy Preview. Use the default page template for Methodology, Accountability, and Authors Preview.

- [ ] **Step 3: Create draft analysis content in one blog**

Keep one blog. Draft the flagship, latest NFL analysis, at least one Dynasty article, and at least one DFS article in the existing Power Ratings Updates blog. Apply `nfl` plus the appropriate lane tag; use `power-ratings`, `dynasty`, and `dfs` exactly. Populate every trust metafield that applies. Do not publish the drafts.

- [ ] **Step 4: Populate fail-closed theme settings only from reviewed data**

After the ratings repository passes Task 6 and all 32 `needs_review` flags are cleared, populate the duplicate theme's top-five section with exactly five rows copied from that reviewed edition. Use ordinal, team name, signed rating, and text movement. Populate edition, Sean McCabe byline, published time, updated time, and current-edition summary in the Power Ratings section.

If the ratings review gate remains closed, leave those settings blank; the section intentionally renders no unreviewed top five.

- [ ] **Step 5: Perform an editorial content gate**

For each draft or section, verify headline, deck, named author, published/updated time, model/data version when applicable, key takeaway, sources, methodology, correction history, tags, meta title, and meta description. Confirm that McCabe ratings, Prediction Lab, market, and Fantasy Lab language is never blended.

Expected: no draft is made public and no canonical page is edited.

---

### Task 8: Give Every Existing Ratings URL an Intentional Outcome

**Files:**

- No repository files change in this task.
- Shopify Admin changes remain recorded but inactive until cutover approval.

**Interfaces:**

- Consumes the four verified public articles under `/blogs/poweratings`.
- Produces a cutover redirect/archive ledger with no accidental obsolete URL.

- [ ] **Step 1: Record the exact URL ledger**

Use these outcomes:

| Current URL | Approved outcome to stage |
|---|---|
| `/blogs/poweratings/final-power-ratings-25-26-season` | Keep as an archive, add `power-ratings`, `nfl`, and `archive` tags, identify the edition and author, and link to `/pages/power-ratings`. |
| `/blogs/poweratings/pre-big-game-power-ratings` | Keep as an archive/receipt, add source and capture context, disclose that its matchup line applied only to that named game, and link to `/pages/power-ratings`. |
| `/blogs/poweratings/week-9-power-ratings` | Redirect at cutover to `/pages/power-ratings`; the public title says Week 16, the handle says Week 9, and the body is too thin to preserve as a useful archive. |
| `/blogs/poweratings/power-ratings-guide` | Move the useful explanation into `/pages/methodology`, then redirect this URL to `/pages/methodology` at cutover. |
| `/blogs/poweratings` | Rename the blog display title to `Analysis`; defer changing the handle to `/blogs/analysis` until the controlled cutover and create a permanent redirect from the old blog root. |

- [ ] **Step 2: Prepare redirects without activating them**

Record the source/target pairs in the cutover checklist. Do not delete an article, rename the blog handle, or activate a redirect while the production theme is still live.

- [ ] **Step 3: Verify archives before approval**

In preview, confirm retained archives are visibly labeled `Archive`, retain their original publication date, add any correction note without rewriting the original receipt, and link to the current ratings page.

Expected: all five current URL shapes have one named outcome and none are silently abandoned.

---

### Task 9: Build and Review the Combined Unpublished Preview

**Files:**

- Theme source from Tasks 1–6.
- No production files or settings change.

**Interfaces:**

- Consumes the committed theme branch, Shopify Admin duplicate-theme upload, local reviewed ratings preview, and approved draft content.
- Produces one approval package and a rollback-ready release candidate.

- [ ] **Step 0: Record the commerce baseline without changing analytics**

In Shopify Analytics, export or capture sessions, online-store conversion rate, orders, gross sales, and total sales for `2026-06-17` through `2026-07-14`, with `2026-05-20` through `2026-06-16` as the comparison period. Record the report names, timezone, currency, and capture time in the approval package. Do not install or configure another analytics product.

- [ ] **Step 1: Run fresh automated verification**

Run:

```powershell
python -m unittest tests.test_shopify_theme -v
Get-ChildItem shopify-theme -Recurse -Filter *.json | ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json | Out-Null }
npx --yes @shopify/cli@latest theme check --path shopify-theme --fail-level error --output json > theme-check-final.json
git diff --check f786980..HEAD
```

Expected: all unit tests pass; all JSON parses; no whitespace errors; Theme Check contains only recorded baseline findings and no finding in a created/modified file.

- [ ] **Step 2: Confirm the commerce guardrail**

Run: `python -m unittest tests.test_shopify_theme.ShopifyThemeTests.test_commerce_files_match_captured_baseline -v`

Expected: PASS for all seven protected files.

- [ ] **Step 3: Package and upload only as an unpublished theme**

From the repository root, run:

```powershell
Compress-Archive -Path shopify-theme\* -DestinationPath postgame-content-first-theme.zip -Force
```

In Shopify Admin → Online Store → Themes, upload `postgame-content-first-theme.zip` as a new theme. Do not publish it. Confirm its label clearly includes `Content First Preview` and the commit short SHA.

- [ ] **Step 4: Review the exact page set**

Review homepage, Power Ratings alternate template, Fantasy alternate template, one analysis article, one archive, collection, product, cart, search, and contact. Use Shopify's generated preview URL or Admin page preview; do not assign alternate templates to canonical live pages yet.

- [ ] **Step 5: Run responsive and accessibility gates**

At 320px, 390px, 768px, and desktop:

- No document-level horizontal scrolling.
- Exactly one meaningful H1.
- Header/menu, article links, ratings controls, iframe content, and cart are keyboard-operable.
- Focus is visible.
- Ratings board and drawer retain their existing table/dialog semantics.
- Overall ratings appear before any featured matchup; McCabe-implied, Prediction Lab, and sourced market lines remain in a separate full-width matchup stack and state that they apply only to the named game.
- Text contrast passes WCAG AA; orange is not the only cue or a small-text foreground.
- Klaviyo inline form appears only after useful homepage content; no popup appears immediately.

- [ ] **Step 6: Verify analytics and commerce**

Subscribe to `all_custom_events` in an existing Shopify custom pixel or use the browser console in preview. Click the single homepage merchandise module and the optional article product card. Confirm one `postgame_content_product_click` event per click with the three exact fields. Then verify Shopify's native product-view, add-to-cart, checkout-start, and purchase test events remain intact.

Smoke-test product variant selection, add to cart, cart update/remove, checkout start, shipping step, and return to store. Do not place a real order unless the store's approved test-payment path is active.

- [ ] **Step 7: Assemble the approval package**

Include:

- Unpublished Shopify theme-preview link.
- Local reviewed ratings preview path and ratings commit.
- Desktop and 390px captures of homepage, Power Ratings, Fantasy, article, product, and cart.
- Theme commit SHA and source ZIP SHA-256.
- Theme Check baseline/delta summary.
- Editorial checklist and the exact four-article URL ledger.
- Analytics payload capture.
- Commerce smoke-test record.
- Rollback target: current production theme plus baseline commit `f786980`.

- [ ] **Step 8: Stop at explicit approval**

Do not publish the theme, replace GitHub Pages output, rename the blog handle, activate redirects, change canonical page assignments, or publish draft content. Those actions require a separate, explicit cutover approval.

- [ ] **Step 9: Commit the verified implementation**

```powershell
git status --short
git add shopify-theme tests
git commit -m "Prepare content-first Shopify preview"
```

Expected before commit: only intended theme/test changes; no ZIP, Theme Check output, screenshots, secrets, or `.superpowers/` files staged.

---

## Final Review Checklist

- [ ] Homepage visibly follows the required seven-part content order on mobile and desktop.
- [ ] Power Ratings page supplies native, crawlable context before the app.
- [ ] Top five and edition context come only from a reviewed release.
- [ ] Fantasy shows real Dynasty/DFS articles and no empty tools.
- [ ] Articles show author, timestamps, version, takeaway, sources, methodology, corrections, and related analysis where applicable.
- [ ] At most one relevant product follows article analysis.
- [ ] Existing product, collection, cart, drawer, and checkout paths still work.
- [ ] Primary nav is exactly `Home · Power Ratings · Fantasy · Shop`.
- [ ] Existing ratings URLs have explicit archive/redirect outcomes.
- [ ] The custom click event is verifiable and no new analytics vendor was added.
- [ ] Klaviyo does not interrupt a first-time reader before useful content.
- [ ] Previous theme and production ratings output remain immediate rollback targets.
- [ ] No production mutation occurs before explicit approval.
