# Content-First Fresh-Base Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved editorial-first Postgame Outlet experience on a fresh capture of the current Shopify theme, qualify it locally, and stop after a visually approved unpublished Shopify draft.

**Architecture:** Shopify remains the content and commerce shell; the existing GitHub Pages ratings application remains the interactive ratings owner. Capture the live theme into this isolated branch, freeze its commerce-critical bytes, then port only the approved 15-file Liquid/JSON/CSS/JavaScript delta from immutable Git reference `bebee2ac8fbc3be140747ebd7e02c81ac88b604c`. Local packaging and remote draft creation are separate gates; no live theme, canonical route, model artifact, or deployment changes under this plan.

**Tech Stack:** Shopify Spotlight theme primitives, Liquid, JSON templates, plain CSS and JavaScript, Python 3.14 standard-library `unittest`, PowerShell, Git, Node.js 24.14.0, npm 11.9.0, and pinned on-demand Shopify CLI 4.7.1. No new repository dependency or build system.

## Global Constraints

- Work only in `D:\CodexWorktrees\Postgame_Outlet-content-first-fresh-base-port` on `codex/content-first-fresh-base-port`.
- Treat `qxfvhq-zn.myshopify.com` as the expected store. Stop if authenticated Shopify output names another store or the user cannot confirm the account.
- Never use Shopify CLI flags `--live`, `--allow-live`, `--publish`, `--password`, `--verbose`, or `--auto-correct` in this plan.
- Tasks 1-6 may read Shopify only to identify and pull the current live theme. They may not create, update, delete, upload, publish, or replace remote Shopify state.
- Task 7 is an explicit external-write gate. Do not begin it from general plan-execution approval; show the local evidence package and obtain fresh user authorization for the listed draft-only mutations.
- Never publish a theme, page, article, menu, redirect, model result, or ratings artifact. Never assign a template to a canonical live page.
- Preserve `docs/index.html` byte-for-byte at SHA-256 `5094AD484807BACB8CE5DDDF19CFF38798ED86A07C1501D1BCBF09F84DD932FE`.
- Do not edit PGO, McCabe, Prediction Lab, Fantasy Lab, source, lock, grading, deployment, or workflow code.
- Use `f786980..bebee2ac` only as a semantic reference. Do not merge or cherry-pick `codex/content-first-site-preview`, and do not restore any reconciled file wholesale.
- Store transient receipts, Theme Check output, ZIPs, and screenshots under ignored `output/content-first-fresh-base/`. Never put credentials there.
- Preserve failures as evidence. If a stop condition fires, write a local diagnostic under that ignored output directory and stop without fallback.

---

## File Map

### Added from the immutable semantic reference, then minimally adapted

- `shopify-theme/assets/postgame-content.css` - navy/slate/orange editorial system and responsive layout.
- `shopify-theme/assets/postgame-content.js` - product-click analytics and origin-checked ratings iframe messaging.
- `shopify-theme/sections/postgame-featured-story.liquid` - flagship story and optional reviewed model-status panel.
- `shopify-theme/sections/postgame-ratings-preview.liquid` - exactly five reviewed ratings plus optional movers.
- `shopify-theme/sections/postgame-ratings.liquid` - crawlable native ratings context before the independent app.
- `shopify-theme/sections/postgame-tagged-articles.liquid` - latest-analysis, Dynasty, DFS, and related-analysis lane.
- `shopify-theme/templates/page.fantasy.json` - Fantasy editorial landing template.
- `shopify-theme/templates/page.power-ratings.json` - native ratings wrapper template.

### Fresh files reconciled in place

- `shopify-theme/layout/theme.liquid` - load shared assets once and identify content surfaces.
- `shopify-theme/sections/header-group.json` - point only the draft theme at `content-first-preview`.
- `shopify-theme/sections/footer-group.json` - add preview links and avoid duplicate email embeds.
- `shopify-theme/sections/main-article.liquid` - render trust metadata and optional evidence fields.
- `shopify-theme/templates/index.json` - approved editorial-first order while reusing current app and merchandise objects.
- `shopify-theme/templates/article.json` - related analysis and one disabled-by-default product module.
- `shopify-theme/templates/blog.json` - readable grid with authors.

### Test and evidence files

- `tests/fixtures/shopify-theme-commerce.sha256` - seven fresh-capture commerce hashes.
- `tests/test_shopify_theme.py` - dependency-free structural contract adapted from the immutable legacy test.
- `docs/superpowers/specs/2026-09-02-content-first-fresh-base-port-design.md` - approved source specification; only approval status changes.
- `docs/superpowers/plans/2026-09-02-content-first-fresh-base-port.md` - this plan.
- `output/content-first-fresh-base/` - ignored receipts, diagnostics, packages, and screenshots; never staged or packaged.

No `package.json`, lockfile, framework, bundler, custom packager, API client, or new model module is created.

---

### Task 1: Capture and freeze the current Shopify theme

**Files:**

- Create: `shopify-theme/**` from the current remote live theme
- Create: `tests/fixtures/shopify-theme-commerce.sha256`
- Create, ignored: `output/content-first-fresh-base/live-theme.json`
- Create, ignored: `output/content-first-fresh-base/baseline-theme-check.json`
- Create, ignored: `output/content-first-fresh-base/baseline-receipt.json`

- [ ] **Step 1: Prove the local starting point**

```powershell
$ErrorActionPreference = 'Stop'
$expectedBranch = 'codex/content-first-fresh-base-port'
$actualBranch = (git branch --show-current).Trim()
if ($actualBranch -ne $expectedBranch) { throw "Wrong branch: $actualBranch" }
git merge-base --is-ancestor 87ce5a84485eb06f07763195d7d005a54e212de9 HEAD
if ($LASTEXITCODE -ne 0) { throw 'Approved design commit is not an ancestor of HEAD.' }
if (git status --porcelain) { throw 'Worktree is not clean.' }
if (Test-Path -LiteralPath 'shopify-theme') { throw 'shopify-theme already exists; do not overwrite it.' }
git cat-file -e bebee2ac8fbc3be140747ebd7e02c81ac88b604c^{commit}
if ($LASTEXITCODE -ne 0) { throw 'Immutable semantic-reference commit is unavailable.' }
```

Expected: all commands exit `0`, the worktree is clean, and `shopify-theme/` is absent. Stop on any mismatch.

- [ ] **Step 2: Obtain read-only Shopify capture confirmation**

Show the user this exact scope before authenticating:

```text
Read-only Shopify action: list the one live theme for qxfvhq-zn.myshopify.com and pull that exact theme into the isolated local worktree. No remote object will be created, edited, deleted, uploaded, or published. The authenticated browser must visibly be the intended Postgame Outlet account.
```

Expected: explicit confirmation for this read-only capture and human confirmation of the visible account. Stop if either is absent or ambiguous.

- [ ] **Step 3: Pin the local toolchain without adding a dependency**

```powershell
$nodeVersion = (node --version).Trim()
$npmVersion = (npm --version).Trim()
$shopifyVersion = (npx --yes '@shopify/cli@4.7.1' version).Trim()
if ([version]$nodeVersion.TrimStart('v') -lt [version]'22.12.0') { throw "Node is too old: $nodeVersion" }
if ($shopifyVersion -ne '4.7.1') { throw "Unexpected Shopify CLI: $shopifyVersion" }
if (Test-Path Env:SHOPIFY_CLI_THEME_TOKEN) { throw 'Unset SHOPIFY_CLI_THEME_TOKEN and use visible interactive account authentication.' }
New-Item -ItemType Directory -Force -Path 'output/content-first-fresh-base' | Out-Null
@{ node = $nodeVersion; npm = $npmVersion; shopify_cli = $shopifyVersion } | ConvertTo-Json | Set-Content -LiteralPath 'output/content-first-fresh-base/toolchain.json' -Encoding utf8
```

Expected on the recorded baseline: Node `v24.14.0`, npm `11.9.0`, Shopify CLI `4.7.1`, and no token value is read or printed.

- [ ] **Step 4: Resolve exactly one live theme and record only non-secret identity**

Keep these commands in one PowerShell session:

```powershell
$store = 'qxfvhq-zn.myshopify.com'
$themeListLines = & npx --yes '@shopify/cli@4.7.1' theme list --store $store --role live --json
if ($LASTEXITCODE -ne 0) { throw 'Shopify live-theme listing failed.' }
$themeListRaw = $themeListLines -join [Environment]::NewLine
$themeListRaw | Set-Content -LiteralPath 'output/content-first-fresh-base/live-theme.json' -Encoding utf8
$liveThemes = @($themeListRaw | ConvertFrom-Json)
if ($liveThemes.Count -ne 1) { throw "Expected one live theme, found $($liveThemes.Count)." }
$liveTheme = $liveThemes[0]
if ($liveTheme.role -notin @('live', 'main')) { throw "Unexpected role: $($liveTheme.role)" }
if ($liveTheme.shop -and $liveTheme.shop -ne $store) { throw "Unexpected store: $($liveTheme.shop)" }
$liveTheme | Select-Object id, name, role, shop | Format-List
```

Expected: exactly one live/main theme for the expected store. The user confirms the displayed ID and name before the next step. Stop if the JSON shape, role, store, ID, or name is ambiguous.

- [ ] **Step 5: Pull that exact live theme into the absent directory**

```powershell
if (Test-Path -LiteralPath 'shopify-theme') { throw 'Refusing to pull over an existing directory.' }
& npx --yes '@shopify/cli@4.7.1' theme pull --store $store --theme $liveTheme.id --path 'shopify-theme'
if ($LASTEXITCODE -ne 0) { throw 'Theme pull failed.' }
$requiredRoots = 'assets','config','layout','locales','sections','snippets','templates'
foreach ($root in $requiredRoots) {
  if (-not (Test-Path -LiteralPath (Join-Path 'shopify-theme' $root))) { throw "Missing theme root: $root" }
}
```

Expected: a complete local theme tree and no remote write.

- [ ] **Step 6: Reject credentials, invalid JSON, or a crashing baseline check**

```powershell
$secretPattern = 'shpat_|shpca_|shppa_|sk_live_|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'
$secretFiles = @(rg -l --hidden -g '!*.png' -g '!*.jpg' -g '!*.jpeg' -g '!*.gif' -g '!*.webp' -g '!*.woff*' $secretPattern shopify-theme)
if ($LASTEXITCODE -gt 1) { throw 'Credential scan failed.' }
if ($secretFiles.Count) { throw "Credential-like material found in: $($secretFiles -join ', ')" }
Get-ChildItem -LiteralPath 'shopify-theme' -Recurse -File -Filter '*.json' | ForEach-Object {
  $source = Get-Content -LiteralPath $_.FullName -Raw
  $source = [regex]::Replace($source, '\A\s*/\*[\s\S]*?\*/\s*', '')
  try { $source | ConvertFrom-Json | Out-Null }
  catch { throw "Invalid JSON: $($_.FullName)" }
}
$baselineCheckLines = & npx --yes '@shopify/cli@4.7.1' theme check --path 'shopify-theme' --fail-level crash --output json
if ($LASTEXITCODE -ne 0) { throw 'Theme Check crashed on the fresh capture.' }
($baselineCheckLines -join [Environment]::NewLine) | Set-Content -LiteralPath 'output/content-first-fresh-base/baseline-theme-check.json' -Encoding utf8
```

Expected: no high-confidence credential marker, every JSON file parses, and baseline Theme Check completes. Existing findings are evidence, not permission to auto-correct inherited code.

- [ ] **Step 7: Generate the seven-file commerce manifest from fresh bytes**

```powershell
$protected = @(
  'templates/product.json',
  'templates/collection.json',
  'templates/cart.json',
  'sections/main-product.liquid',
  'sections/main-cart-items.liquid',
  'sections/main-cart-footer.liquid',
  'snippets/cart-drawer.liquid'
)
New-Item -ItemType Directory -Force -Path 'tests/fixtures' | Out-Null
$manifest = foreach ($relative in $protected) {
  $path = Join-Path 'shopify-theme' $relative
  if (-not (Test-Path -LiteralPath $path)) { throw "Missing protected file: $relative" }
  $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
  "$digest  $relative"
}
$manifest | Set-Content -LiteralPath 'tests/fixtures/shopify-theme-commerce.sha256' -Encoding ascii
if ($manifest.Count -ne 7) { throw 'Protected manifest does not contain seven entries.' }
```

Expected: seven lowercase SHA-256 lines, each with two spaces before its relative path.

- [ ] **Step 8: Commit the untouched capture as its own baseline**

```powershell
$identity = @(Get-Content -LiteralPath 'output/content-first-fresh-base/live-theme.json' -Raw | ConvertFrom-Json)[0]
$capturedAt = (Get-Date).ToUniversalTime().ToString('o')
git add -- shopify-theme tests/fixtures/shopify-theme-commerce.sha256
$staged = @(git diff --cached --name-only)
if (-not $staged.Count) { throw 'Nothing was staged.' }
if (@($staged | Where-Object { $_ -notlike 'shopify-theme/*' -and $_ -ne 'tests/fixtures/shopify-theme-commerce.sha256' }).Count) { throw 'Baseline staging includes an out-of-scope file.' }
git commit -m 'chore: capture current Shopify theme baseline' -m "Store: qxfvhq-zn.myshopify.com`nTheme: $($identity.name) ($($identity.id))`nCaptured UTC: $capturedAt`nShopify CLI: 4.7.1"
if ($LASTEXITCODE -ne 0) { throw 'Baseline commit failed.' }
$baselineSha = (git rev-parse HEAD).Trim()
@{ baseline_sha = $baselineSha; store = 'qxfvhq-zn.myshopify.com'; theme_id = $identity.id; theme_name = $identity.name; theme_role = $identity.role; captured_at_utc = $capturedAt; shopify_cli = '4.7.1' } | ConvertTo-Json | Set-Content -LiteralPath 'output/content-first-fresh-base/baseline-receipt.json' -Encoding utf8
if (git status --porcelain) { throw 'Tracked worktree is not clean after baseline commit.' }
```

Expected: one baseline commit containing only the exact capture and seven-hash manifest. Record `$baselineSha` in the final handoff.

---

### Task 2: Add the shared content shell with its smallest regression contract

**Files:**

- Create: `tests/test_shopify_theme.py`
- Create: `shopify-theme/assets/postgame-content.css`
- Create: `shopify-theme/assets/postgame-content.js`
- Modify: `shopify-theme/layout/theme.liquid`

- [ ] **Step 1: Write the shared-shell tests first**

Create `tests/test_shopify_theme.py` with this initial content:

```python
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "shopify-theme"
COMMERCE_MANIFEST = ROOT / "tests/fixtures/shopify-theme-commerce.sha256"


def text(relative):
    return (THEME / relative).read_text(encoding="utf-8")


def data(relative):
    source = text(relative)
    if source.lstrip().startswith("/*"):
        source = source.split("*/", 1)[1]
    return json.loads(source)


class ShopifyThemeTests(unittest.TestCase):
    def test_commerce_files_match_fresh_capture(self):
        entries = [line.split("  ", 1) for line in COMMERCE_MANIFEST.read_text(encoding="ascii").splitlines()]
        self.assertEqual(7, len(entries))
        for digest, relative in entries:
            self.assertEqual(64, len(digest), relative)
            actual = hashlib.sha256((THEME / relative).read_bytes()).hexdigest()
            self.assertEqual(digest, actual, relative)

    def test_shared_content_assets_are_loaded_once(self):
        layout = text("layout/theme.liquid")
        self.assertEqual(1, layout.count("postgame-content.css"))
        self.assertEqual(1, layout.count("postgame-content.js"))
        self.assertIn("data-postgame-content-type", layout)
        self.assertIn("data-postgame-content-id", layout)
        self.assertIn("template.suffix == 'power-ratings' or template.suffix == 'fantasy'", layout)
        css = text("assets/postgame-content.css")
        for value in ("--postgame-navy", "--postgame-orange", ":focus-visible", "max-width: 749px"):
            self.assertIn(value, css)

    def test_shared_script_has_embed_and_analytics_contracts(self):
        script = text("assets/postgame-content.js")
        for value in (
            "postgame_content_product_click",
            "content_type",
            "content_identifier",
            "product_handle",
            "npr:height",
            "npr:ready",
            "npr:viewport",
            "event.origin !== origin",
            "event.source !== frame.contentWindow",
            "Number.isFinite(height)",
        ):
            self.assertIn(value, script)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run RED without weakening the commerce guard**

```powershell
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme.ShopifyThemeTests.test_commerce_files_match_fresh_capture -v
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme.ShopifyThemeTests.test_shared_content_assets_are_loaded_once tests.test_shopify_theme.ShopifyThemeTests.test_shared_script_has_embed_and_analytics_contracts -v
```

Expected: commerce passes; the two shared-content tests fail because the assets and layout hooks are absent. If commerce fails, stop and restore fresh protected bytes.

- [ ] **Step 3: Reuse the complete legacy assets and approved visual tokens**

```powershell
git restore --source=bebee2ac8fbc3be140747ebd7e02c81ac88b604c -- shopify-theme/assets/postgame-content.css shopify-theme/assets/postgame-content.js
```

Keep the JavaScript logic unchanged unless the fresh theme exposes a verified incompatibility. In CSS, retain the legacy selectors and responsive behavior, and make the approved palette explicit:

```css
:root {
  --postgame-navy: #263b58;
  --postgame-slate: #384f6f;
  --postgame-orange: #fd962f;
  --postgame-soft: #f5f7fa;
  --postgame-hold: #fff7ed;
}
```

Use a wide hero plus subordinate status panel at `750px` and above, one reading column below `750px`, five ratings columns that become five vertical rows, visible focus, and no `overflow-x: hidden` workaround on `html` or `body`.

- [ ] **Step 4: Reconcile three hooks into the fresh layout**

Inspect `git diff f786980..bebee2ac -- shopify-theme/layout/theme.liquid`, then use `apply_patch` at the equivalent fresh locations to load each asset once and add this body metadata:

```liquid
{% if template.name == 'index' %}
  data-postgame-content-type="homepage"
  data-postgame-content-id="home"
{% elsif template.name == 'article' %}
  data-postgame-content-type="article"
  data-postgame-content-id="{{ article.handle | escape }}"
{% elsif template.suffix == 'power-ratings' or template.suffix == 'fantasy' %}
  data-postgame-content-type="page"
  data-postgame-content-id="{{ page.handle | escape }}"
{% endif %}
```

Preserve every unrelated fresh script, stylesheet, body class, accessibility link, and app hook.

- [ ] **Step 5: Run GREEN and commit the isolated shell**

```powershell
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme -v
git diff --check
git add -- tests/test_shopify_theme.py shopify-theme/assets/postgame-content.css shopify-theme/assets/postgame-content.js shopify-theme/layout/theme.liquid
git commit -m 'feat: add shared content theme shell'
```

Expected: three tests pass, `git diff --check` prints nothing, and the commit touches only the four listed files.

---

### Task 3: Port the approved editorial-first homepage

**Files:**

- Modify: `tests/test_shopify_theme.py`
- Create: `shopify-theme/sections/postgame-featured-story.liquid`
- Create: `shopify-theme/sections/postgame-ratings-preview.liquid`
- Create: `shopify-theme/sections/postgame-tagged-articles.liquid`
- Modify: `shopify-theme/templates/index.json`
- Modify: `shopify-theme/sections/header-group.json`
- Modify: `shopify-theme/sections/footer-group.json`
- Modify: `shopify-theme/assets/postgame-content.css`

- [ ] **Step 1: Append homepage contract tests**

Add these methods to `ShopifyThemeTests` before the `__main__` block:

```python
    def test_homepage_has_approved_content_order(self):
        template = data("templates/index.json")
        types = [
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
                "postgame-tagged-articles",
                "multicolumn",
                "apps",
                "featured-collection",
            ],
            types,
        )
        self.assertEqual("dynasty", template["sections"]["dynasty"]["settings"]["required_tag"])
        self.assertEqual("dfs", template["sections"]["dfs"]["settings"]["required_tag"])
        self.assertEqual("/pages/accountability", template["sections"]["accountability"]["settings"]["button_link"])
        self.assertEqual(4, template["sections"]["merch"]["settings"]["products_to_show"])

    def test_featured_story_supports_reviewed_status_without_requiring_it(self):
        section = text("sections/postgame-featured-story.liquid")
        for value in ("section.settings.article", "status_label", "status_body", "postgame-model-status"):
            self.assertIn(value, section)
        self.assertIn("featured_article != blank", section)

    def test_ratings_preview_requires_reviewed_five_and_supports_movers(self):
        section = text("sections/postgame-ratings-preview.liquid")
        for value in (
            "team_count != 5",
            "block.type == 'team'",
            "block.type == 'mover'",
            "Rating points represent neutral-field strength",
            "View all 32 teams",
            "section.settings.ratings_link",
        ):
            self.assertIn(value, section)

    def test_preview_navigation_footer_and_email_are_isolated(self):
        header = data("sections/header-group.json")
        footer = data("sections/footer-group.json")
        self.assertEqual("content-first-preview", header["sections"]["header"]["settings"]["menu"])
        self.assertEqual(
            "content-footer-preview",
            footer["sections"]["footer"]["blocks"]["content_links"]["settings"]["menu"],
        )
        combined = json.dumps(data("templates/index.json")) + json.dumps(footer)
        self.assertEqual(1, combined.count("form-embed-block"))
```

- [ ] **Step 2: Run the four new tests RED**

```powershell
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme.ShopifyThemeTests.test_homepage_has_approved_content_order tests.test_shopify_theme.ShopifyThemeTests.test_featured_story_supports_reviewed_status_without_requiring_it tests.test_shopify_theme.ShopifyThemeTests.test_ratings_preview_requires_reviewed_five_and_supports_movers tests.test_shopify_theme.ShopifyThemeTests.test_preview_navigation_footer_and_email_are_isolated -v
```

Expected: failures for absent sections and the merchandise-first fresh template.

- [ ] **Step 3: Restore reusable sections, then apply only approved adaptations**

```powershell
git restore --source=bebee2ac8fbc3be140747ebd7e02c81ac88b604c -- shopify-theme/sections/postgame-featured-story.liquid shopify-theme/sections/postgame-ratings-preview.liquid shopify-theme/sections/postgame-tagged-articles.liquid
```

Use `apply_patch` for these changes:

- Featured story: add optional `status_label` text and `status_body` textarea settings; render them in `<aside class="postgame-model-status">` after story copy only when at least one value is nonblank.
- Ratings preview: add URL setting `ratings_link` with no schema default and use it for `View all 32 teams`; if blank, render the label as text rather than linking to a canonical route.
- Tagged articles: retain the current two-pass bounded loop, article-card render, author/date/excerpt output, and current-article exclusion. Do not add a data service or client-side filter.

- [ ] **Step 4: Reconcile fresh homepage, header, and footer instead of replacing them**

Inspect the current files and the immutable diff:

```powershell
git diff f786980..bebee2ac -- shopify-theme/templates/index.json shopify-theme/sections/header-group.json shopify-theme/sections/footer-group.json
```

Edit fresh JSON so enabled homepage section types are exactly this order:

```text
featured_story  -> postgame-featured-story
ratings_preview -> postgame-ratings-preview
latest_analysis -> postgame-tagged-articles
dynasty         -> postgame-tagged-articles
dfs             -> postgame-tagged-articles
accountability  -> multicolumn
email           -> apps
merch           -> featured-collection
```

Apply these contracts:

- `featured_story.article`, `status_label`, and `status_body` start blank; draft review supplies them.
- Ratings starts without team blocks and remains unavailable until exactly five reviewed rows, edition, author, and published time exist. Configure `/pages/power-ratings-preview` only in unpublished draft settings.
- Latest analysis uses blog `poweratings`, no required tag, limit `3`; Dynasty and DFS use their matching required tags and limit `3`.
- Accountability links to `/pages/accountability` and begins with an honest empty state, not invented performance claims.
- Email reuses the one exact current Klaviyo app-block object/settings from the fresh capture. If none or multiple candidates exist, stop rather than inventing or deleting an integration.
- Merchandise reuses the current featured-collection object, changes title to `From the Outlet`, shows four products, and stays last.
- Header changes only its menu to `content-first-preview`; preserve all other settings.
- Footer adds link-list block `content_links`, heading `Explore`, menu `content-footer-preview`; preserve unrelated settings/blocks and remove only the duplicate Klaviyo form moved to homepage.

Parse edited JSON:

```powershell
'templates/index.json','sections/header-group.json','sections/footer-group.json' | ForEach-Object {
  $source = Get-Content -LiteralPath (Join-Path 'shopify-theme' $_) -Raw
  [regex]::Replace($source, '\A\s*/\*[\s\S]*?\*/\s*', '') | ConvertFrom-Json | Out-Null
}
```

- [ ] **Step 5: Match approved responsive density in existing CSS**

Style existing classes only:

- `.postgame-featured-story`: desktop split near `1.45fr / .75fr`, navy/slate gradient, white story copy, stacked mobile layout.
- `.postgame-model-status`: subordinate panel with orange-bordered status pill and textual status.
- `.postgame-grid--5`: five compact columns on desktop, full-width bordered rows below `750px`.
- `.postgame-grid--3`: three cards on desktop, one column below `750px`.
- `.postgame-card`: restrained top accent and no fixed content height.

Do not encode mockup sample ratings or claims in CSS, Liquid, or template defaults.

- [ ] **Step 6: Run GREEN and commit**

```powershell
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme -v
git diff --check
git add -- tests/test_shopify_theme.py shopify-theme/assets/postgame-content.css shopify-theme/sections/postgame-featured-story.liquid shopify-theme/sections/postgame-ratings-preview.liquid shopify-theme/sections/postgame-tagged-articles.liquid shopify-theme/templates/index.json shopify-theme/sections/header-group.json shopify-theme/sections/footer-group.json
git commit -m 'feat: make the homepage editorial first'
```

Expected: seven tests pass and the commit contains no other theme file.

---

### Task 4: Add Power Ratings and Fantasy interior pages

**Files:**

- Modify: `tests/test_shopify_theme.py`
- Create: `shopify-theme/sections/postgame-ratings.liquid`
- Create: `shopify-theme/templates/page.power-ratings.json`
- Create: `shopify-theme/templates/page.fantasy.json`
- Modify: `shopify-theme/assets/postgame-content.css`

- [ ] **Step 1: Append two interior-page tests**

```python
    def test_power_ratings_has_native_context_before_origin_checked_embed(self):
        template = data("templates/page.power-ratings.json")
        self.assertEqual("postgame-ratings", template["sections"]["main"]["type"])
        section = text("sections/postgame-ratings.liquid")
        native = section.split("<iframe", 1)[0]
        schema = json.loads(section.split("{% schema %}", 1)[1].split("{% endschema %}", 1)[0])
        for setting_id in ("ratings_url", "methodology_link", "accountability_link", "archive_link"):
            setting = next(item for item in schema["settings"] if item["id"] == setting_id)
            self.assertNotIn("default", setting, setting_id)
        settings = template["sections"]["main"]["settings"]
        self.assertEqual("https://walshja9.github.io/Postgame_Outlet/", settings["ratings_url"])
        self.assertEqual("/pages/methodology-preview", settings["methodology_link"])
        self.assertEqual("/pages/accountability", settings["accountability_link"])
        self.assertEqual("/blogs/poweratings", settings["archive_link"])
        self.assertLess(section.index("<h1"), section.index("<iframe"))
        for value in (
            "A Power Rating estimates",
            "PGO v1",
            "McCabe's human rating",
            "never blended",
            "hypothetical full-strength roster",
            "current-lineup",
            "section.settings.status_label",
            "data-postgame-ratings-frame",
        ):
            self.assertIn(value, native)
        self.assertNotIn("MAE", native)
        self.assertNotIn("backtest", native)

    def test_fantasy_is_editorial_dynasty_and_dfs_without_a_tool(self):
        template = data("templates/page.fantasy.json")
        self.assertEqual(
            ["main-page", "postgame-tagged-articles", "postgame-tagged-articles"],
            [template["sections"][key]["type"] for key in template["order"]],
        )
        self.assertEqual("dynasty", template["sections"]["dynasty"]["settings"]["required_tag"])
        self.assertEqual("dfs", template["sections"]["dfs"]["settings"]["required_tag"])
        source = text("templates/page.fantasy.json").lower()
        for forbidden in ("assistant", "league sync", "projection tool", "healthy assumption"):
            self.assertNotIn(forbidden, source)
```

- [ ] **Step 2: Run RED**

```powershell
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme.ShopifyThemeTests.test_power_ratings_has_native_context_before_origin_checked_embed tests.test_shopify_theme.ShopifyThemeTests.test_fantasy_is_editorial_dynasty_and_dfs_without_a_tool -v
```

Expected: both fail because the files are absent.

- [ ] **Step 3: Restore legacy files and apply preview-route/status delta**

```powershell
git restore --source=bebee2ac8fbc3be140747ebd7e02c81ac88b604c -- shopify-theme/sections/postgame-ratings.liquid shopify-theme/templates/page.power-ratings.json shopify-theme/templates/page.fantasy.json
```

Adapt minimally:

- Add optional text setting `status_label`; render a non-color-only badge before current-edition summary when nonblank.
- Add URL setting `archive_link` with no schema default and render `Archived editions` beside Methodology and Accountability.
- Keep native PGO/McCabe separation, full-strength/current-lineup distinction, H1-before-iframe order, HTTPS iframe, and `data-postgame-ratings-frame`.
- Keep detailed MAE/backtest values inside the app only.

Set Power Ratings template values exactly to:

```json
{
  "ratings_url": "https://walshja9.github.io/Postgame_Outlet/",
  "methodology_link": "/pages/methodology-preview",
  "accountability_link": "/pages/accountability",
  "archive_link": "/blogs/poweratings",
  "status_label": ""
}
```

Retain blank edition, author, published, updated, and summary settings until review. Keep Fantasy's `main-page`, `dynasty`, and `dfs`; its hidden page body owns waiting/T-60 explanation, so no new Fantasy section or JavaScript is needed.

- [ ] **Step 4: Extend page styles without duplicating the app**

Use selectors already owned by these files: a light native intro with orange rule, wrapping metadata/badges, link row before summary/iframe, full-width iframe with legacy height fallback, and two Fantasy editorial lanes that stack below `750px`. Do not restyle tables, tabs, drawers, or model status inside the iframe.

- [ ] **Step 5: Run GREEN and commit**

```powershell
Get-ChildItem -LiteralPath 'shopify-theme/templates' -File -Filter '*.json' | ForEach-Object {
  $source = Get-Content -LiteralPath $_.FullName -Raw
  [regex]::Replace($source, '\A\s*/\*[\s\S]*?\*/\s*', '') | ConvertFrom-Json | Out-Null
}
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme -v
git diff --check
git add -- tests/test_shopify_theme.py shopify-theme/assets/postgame-content.css shopify-theme/sections/postgame-ratings.liquid shopify-theme/templates/page.power-ratings.json shopify-theme/templates/page.fantasy.json
git commit -m 'feat: add ratings and fantasy editorial pages'
```

Expected: nine tests pass, template JSON parses, and no embedded-app code changes.

---

### Task 5: Add article trust fields and supporting content treatment

**Files:**

- Modify: `tests/test_shopify_theme.py`
- Modify: `shopify-theme/sections/main-article.liquid`
- Modify: `shopify-theme/templates/article.json`
- Modify: `shopify-theme/templates/blog.json`
- Modify: `shopify-theme/assets/postgame-content.css`

- [ ] **Step 1: Append the article contract test**

```python
    def test_articles_expose_trust_fields_and_native_related_modules(self):
        article = text("sections/main-article.liquid")
        for field in (
            "custom.deck",
            "custom.byline",
            "custom.updated_at",
            "custom.model_version",
            "custom.key_takeaway",
            "custom.sources",
            "custom.methodology",
            "custom.correction_history",
        ):
            self.assertIn(field, article)
        template = data("templates/article.json")
        ordered_types = [template["sections"][key]["type"] for key in template["order"]]
        main_index = ordered_types.index("main-article")
        related_index = ordered_types.index("postgame-tagged-articles")
        product_index = ordered_types.index("featured-product")
        self.assertLess(main_index, related_index)
        self.assertLess(related_index, product_index)
        product_key = template["order"][product_index]
        self.assertTrue(template["sections"][product_key]["disabled"])
        self.assertIn("candidate.id == article.id", text("sections/postgame-tagged-articles.liquid"))
        blog = data("templates/blog.json")["sections"]["main"]["settings"]
        self.assertEqual("grid", blog["layout"])
        self.assertTrue(blog["show_author"])
```

- [ ] **Step 2: Run RED**

```powershell
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme.ShopifyThemeTests.test_articles_expose_trust_fields_and_native_related_modules -v
```

Expected: failure because fresh articles do not expose all trust fields or both related modules.

- [ ] **Step 3: Apply semantic article diff to fresh files**

Inspect, but do not restore, the reconciled files:

```powershell
git diff f786980..bebee2ac -- shopify-theme/sections/main-article.liquid shopify-theme/templates/article.json shopify-theme/templates/blog.json
```

Use `apply_patch` to add the eight legacy metafield reads and conditional output at equivalent fresh title/content blocks. Preserve fresh Shopify block attributes, image/share behavior, settings, and unrelated sections.

Required behavior:

- byline falls back to `article.author`;
- deck, updated time, model/data version, and key takeaway are absent when blank;
- sources and correction history use `metafield_tag` only when values exist;
- methodology renders its page-reference title/link only when present;
- blank fields create no heading or fake metadata.

In `article.json`, add related analysis after the main article and one `featured-product` after analysis, disabled by default. Reconcile blocks/settings with the fresh `featured-product` schema. Preserve unrelated fresh sections unless they violate analysis-before-commerce. In `blog.json`, change only `layout` to `grid` and `show_author` to `true`.

- [ ] **Step 4: Style metadata and takeaway with existing selectors**

Add only needed rules for `.postgame-article-deck`, `.postgame-meta`, and `.postgame-takeaway`: readable measure, visible focus, and orange left rule. Do not create a typography framework.

- [ ] **Step 5: Run GREEN and commit**

```powershell
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme -v
git diff --check
git add -- tests/test_shopify_theme.py shopify-theme/assets/postgame-content.css shopify-theme/sections/main-article.liquid shopify-theme/templates/article.json shopify-theme/templates/blog.json
git commit -m 'feat: add editorial trust fields to articles'
```

Expected: ten tests pass and only the five listed files enter this commit.

---

### Task 6: Qualify and package the local implementation

**Files:**

- Create, ignored: `output/content-first-fresh-base/qualification-*/final-theme-check.json`
- Create, ignored: `output/content-first-fresh-base/qualification-*/package-a.zip`
- Create, ignored: `output/content-first-fresh-base/qualification-*/package-b.zip`
- Create, ignored: `output/content-first-fresh-base/qualification-*/postgame-content-first-fresh-base-*.zip`
- Create, ignored: `output/content-first-fresh-base/qualification-*/local-qualification.json`

- [ ] **Step 1: Prove the theme diff is inside the exact 15-file boundary**

```powershell
$baseline = Get-Content -LiteralPath 'output/content-first-fresh-base/baseline-receipt.json' -Raw | ConvertFrom-Json
$baselineSha = $baseline.baseline_sha
$shortSha = (git rev-parse --short=8 HEAD).Trim()
$qualificationDir = Join-Path (Resolve-Path -LiteralPath 'output/content-first-fresh-base').Path "qualification-$shortSha"
if (Test-Path -LiteralPath $qualificationDir) { throw 'Qualification evidence already exists for this implementation SHA; preserve it.' }
New-Item -ItemType Directory -Path $qualificationDir | Out-Null
$allowedTheme = @(
  'shopify-theme/assets/postgame-content.css',
  'shopify-theme/assets/postgame-content.js',
  'shopify-theme/layout/theme.liquid',
  'shopify-theme/sections/footer-group.json',
  'shopify-theme/sections/header-group.json',
  'shopify-theme/sections/main-article.liquid',
  'shopify-theme/sections/postgame-featured-story.liquid',
  'shopify-theme/sections/postgame-ratings-preview.liquid',
  'shopify-theme/sections/postgame-ratings.liquid',
  'shopify-theme/sections/postgame-tagged-articles.liquid',
  'shopify-theme/templates/article.json',
  'shopify-theme/templates/blog.json',
  'shopify-theme/templates/index.json',
  'shopify-theme/templates/page.fantasy.json',
  'shopify-theme/templates/page.power-ratings.json'
)
$changedTheme = @(git diff --name-only $baselineSha HEAD -- shopify-theme)
$outside = @($changedTheme | Where-Object { $_ -notin $allowedTheme })
if ($outside.Count) { throw "Theme allowlist violation: $($outside -join ', ')" }
$missing = @($allowedTheme | Where-Object { $_ -notin $changedTheme })
if ($missing.Count) { throw "Expected port file unchanged or missing: $($missing -join ', ')" }
$allChanged = @(git diff --name-only $baselineSha HEAD)
$allowedAll = $allowedTheme + 'tests/test_shopify_theme.py'
$unexpected = @($allChanged | Where-Object { $_ -notin $allowedAll })
if ($unexpected.Count) { throw "Post-baseline scope violation: $($unexpected -join ', ')" }
```

Expected: exactly 15 changed theme files plus `tests/test_shopify_theme.py`; no model, workflow, deployment, or ratings artifact file.

- [ ] **Step 2: Run structural and protected-byte gates**

```powershell
Get-ChildItem -LiteralPath 'shopify-theme' -Recurse -File -Filter '*.json' | ForEach-Object {
  $source = Get-Content -LiteralPath $_.FullName -Raw
  $source = [regex]::Replace($source, '\A\s*/\*[\s\S]*?\*/\s*', '')
  try { $source | ConvertFrom-Json | Out-Null }
  catch { throw "Invalid JSON: $($_.FullName)" }
}
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_shopify_theme -v
$docsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath 'docs/index.html').Hash
if ($docsHash -ne '5094AD484807BACB8CE5DDDF19CFF38798ED86A07C1501D1BCBF09F84DD932FE') { throw 'Protected ratings artifact changed.' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Whitespace validation failed.' }
```

Expected: ten theme tests pass, every JSON file parses, commerce hashes pass through the test, the ratings artifact hash matches, and `git diff --check` prints nothing.

- [ ] **Step 3: Re-run relevant ratings/public-board regressions**

```powershell
C:\Python314\python.exe -B -W error::ResourceWarning -m unittest tests.test_pgo_comparison tests.test_public_board_workflow tests.test_ratings_release -v
```

Expected: 44 tests pass. Longer fantasy week/season qualification remains separate because this port changes no fantasy model code or output.

- [ ] **Step 4: Reject new Theme Check findings in changed files**

```powershell
$finalCheckLines = & npx --yes '@shopify/cli@4.7.1' theme check --path 'shopify-theme' --fail-level crash --output json
if ($LASTEXITCODE -ne 0) { throw 'Final Theme Check crashed.' }
($finalCheckLines -join [Environment]::NewLine) | Set-Content -LiteralPath (Join-Path $qualificationDir 'final-theme-check.json') -Encoding utf8
$baselineReports = @(Get-Content -LiteralPath 'output/content-first-fresh-base/baseline-theme-check.json' -Raw | ConvertFrom-Json)
$finalReports = @(Get-Content -LiteralPath (Join-Path $qualificationDir 'final-theme-check.json') -Raw | ConvertFrom-Json)
foreach ($report in @($baselineReports) + @($finalReports)) {
  if (-not $report.path -or $report.PSObject.Properties.Name -notcontains 'offenses') { throw 'Unexpected Theme Check JSON shape.' }
}
$changedRelative = $changedTheme | ForEach-Object { $_ -replace '^shopify-theme/', '' }
function Get-ThemeRelativePath([string]$path) {
  $normalized = $path.Replace('\', '/')
  $marker = '/shopify-theme/'
  $index = $normalized.LastIndexOf($marker, [StringComparison]::OrdinalIgnoreCase)
  if ($index -ge 0) { return $normalized.Substring($index + $marker.Length) }
  return $normalized.TrimStart([char[]]'./')
}
$baselineKeys = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($report in $baselineReports) {
  $path = Get-ThemeRelativePath $report.path
  foreach ($finding in @($report.offenses)) {
    [void]$baselineKeys.Add("$path|$($finding.check)|$($finding.severity)|$($finding.message)")
  }
}
$introduced = foreach ($report in $finalReports) {
  $path = Get-ThemeRelativePath $report.path
  foreach ($finding in @($report.offenses)) {
    $key = "$path|$($finding.check)|$($finding.severity)|$($finding.message)"
    if ($path -in $changedRelative -and -not $baselineKeys.Contains($key)) {
      [pscustomobject]@{ path = $path; check = $finding.check; severity = $finding.severity; message = $finding.message }
    }
  }
}
if (@($introduced).Count) {
  $introduced | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $qualificationDir 'introduced-theme-check-findings.json') -Encoding utf8
  throw 'A changed file introduces a Theme Check finding.'
}
```

Expected: no new finding in a changed file. Do not auto-correct inherited findings or broaden scope to clean them up.

- [ ] **Step 5: Scan final theme without printing candidate values**

```powershell
$secretPattern = 'shpat_|shpca_|shppa_|sk_live_|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'
$secretFiles = @(rg -l --hidden -g '!*.png' -g '!*.jpg' -g '!*.jpeg' -g '!*.gif' -g '!*.webp' -g '!*.woff*' $secretPattern shopify-theme)
if ($LASTEXITCODE -gt 1) { throw 'Final credential scan failed.' }
if ($secretFiles.Count) { throw "Credential-like material found in: $($secretFiles -join ', ')" }
```

Expected: no high-confidence credential marker; only filenames are reported if the gate fails.

- [ ] **Step 6: Package twice with Shopify's native packager**

```powershell
$artifactDir = $qualificationDir
function New-ThemePackage([string]$destination) {
  Push-Location 'shopify-theme'
  try {
    $started = Get-Date
    & npx --yes '@shopify/cli@4.7.1' theme package --path '.'
    if ($LASTEXITCODE -ne 0) { throw 'Shopify theme package failed.' }
    $generated = Get-ChildItem -LiteralPath '.' -File -Filter '*.zip' | Where-Object { $_.LastWriteTime -ge $started.AddSeconds(-2) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $generated) { throw 'Generated theme ZIP was not found.' }
    Copy-Item -LiteralPath $generated.FullName -Destination $destination
    $resolvedTheme = (Resolve-Path -LiteralPath '.').Path
    if (-not $generated.FullName.StartsWith($resolvedTheme, [StringComparison]::OrdinalIgnoreCase)) { throw 'Refusing to remove ZIP outside theme directory.' }
    Remove-Item -LiteralPath $generated.FullName
  } finally {
    Pop-Location
  }
}
$packageA = Join-Path $artifactDir 'package-a.zip'
$packageB = Join-Path $artifactDir 'package-b.zip'
New-ThemePackage $packageA
New-ThemePackage $packageB
$hashA = (Get-FileHash -Algorithm SHA256 -LiteralPath $packageA).Hash
$hashB = (Get-FileHash -Algorithm SHA256 -LiteralPath $packageB).Hash
if ($hashA -ne $hashB) { throw 'Native package bytes are not reproducible; stop for a plan amendment.' }
$finalPackage = Join-Path $artifactDir "postgame-content-first-fresh-base-$shortSha.zip"
Copy-Item -LiteralPath $packageA -Destination $finalPackage -Force
```

Expected: two native packages have identical SHA-256. If not, stop rather than inventing a custom packager.

- [ ] **Step 7: Prove the ZIP is wrapper-free and theme-only**

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($finalPackage)
try {
  $entries = @($archive.Entries | Where-Object { $_.Name })
  $entryNames = @($entries.FullName)
  if (@($entryNames | Where-Object { $_ -match '\\' }).Count) { throw 'ZIP contains a backslash path.' }
  $allowedRoots = 'assets','blocks','config','layout','listings','locales','sections','snippets','templates'
  $badRoots = @($entryNames | Where-Object { ($_ -split '/', 2)[0] -notin $allowedRoots })
  if ($badRoots.Count) { throw "ZIP contains a non-theme root: $($badRoots -join ', ')" }
  $themeRoot = (Resolve-Path -LiteralPath 'shopify-theme').Path
  $sourceNames = foreach ($root in $allowedRoots) {
    $rootPath = Join-Path 'shopify-theme' $root
    if (Test-Path -LiteralPath $rootPath) {
      Get-ChildItem -LiteralPath $rootPath -Recurse -File | ForEach-Object { $_.FullName.Substring($themeRoot.Length + 1).Replace('\', '/') }
    }
  }
  if (Compare-Object ($sourceNames | Sort-Object) ($entryNames | Sort-Object)) { throw 'ZIP manifest differs from standard theme source folders.' }
} finally {
  $archive.Dispose()
}
$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $finalPackage).Hash
@{ implementation_sha = (git rev-parse HEAD).Trim(); baseline_sha = $baselineSha; package = (Split-Path -Leaf $finalPackage); package_sha256 = $zipHash; zip_entries = $entryNames.Count; protected_files = 7; theme_files_changed = $changedTheme.Count; focused_regression_tests = 44; theme_contract_tests = 10 } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $qualificationDir 'local-qualification.json') -Encoding utf8
git status --short --branch
```

Expected: source and ZIP manifests match, entry paths use forward slashes, the receipt records exact SHAs/digest, and tracked state is clean.

---

### Task 7: Create one isolated unpublished Shopify draft

**External changes:**

- Create one unpublished theme
- Create two preview-only menus
- Create hidden preview pages and draft/hidden articles
- Create or reuse compatible article/page metafield definitions
- Save settings only on the unpublished theme

- [ ] **Step 1: Present the local gate and request action-time authorization**

Show the user:

- source store, live theme ID/name, capture timestamp, and baseline SHA;
- implementation SHA and exact 15-file theme diff;
- 10/10 theme tests and 44/44 focused regression tests;
- baseline/final Theme Check counts and zero introduced findings in changed files;
- seven protected commerce hashes;
- ZIP name, entry count, and SHA-256;
- the exact proposed external mutation inventory above;
- an explicit statement that the live theme ID will not be targeted and nothing will be published.

Stop until the user explicitly authorizes these draft-only external writes. Mockup approval is not action-time authorization.

- [ ] **Step 2: Audit preview-resource collisions before any write**

In Shopify Admin, search these exact names/handles without editing:

```text
Content First Preview                 handle content-first-preview
Content Footer Preview                handle content-footer-preview
Power Ratings Preview                 handle power-ratings-preview
Fantasy Preview                       handle fantasy-preview
Methodology Preview                   handle methodology-preview
Authors Preview                       handle authors-preview
```

Also inspect article metafield definitions in namespace `custom` for keys `deck`, `byline`, `updated_at`, `model_version`, `key_takeaway`, `sources`, `methodology`, and `correction_history`.

Expected: no conflicting resource, or existing definitions with compatible types. Stop rather than overwrite, rename around, or repurpose a collision.

- [ ] **Step 3: Push a new unpublished theme by name, never existing ID**

After the collision audit:

```powershell
$store = 'qxfvhq-zn.myshopify.com'
$shortSha = (git rev-parse --short=8 HEAD).Trim()
$draftName = "Content First Fresh Base $shortSha"
$pushArgs = @('theme','push','--store',$store,'--unpublished','--theme',$draftName,'--path','shopify-theme','--json')
$forbidden = '--live','--allow-live','--publish','--password','--verbose'
if (@($pushArgs | Where-Object { $_ -in $forbidden }).Count) { throw 'Unsafe Shopify push argument.' }
$pushLines = & npx --yes '@shopify/cli@4.7.1' @pushArgs
if ($LASTEXITCODE -ne 0) { throw 'Unpublished theme push failed.' }
$pushRaw = $pushLines -join [Environment]::NewLine
$pushRaw | Set-Content -LiteralPath 'output/content-first-fresh-base/draft-theme.json' -Encoding utf8
$draft = ($pushRaw | ConvertFrom-Json).theme
if ($draft.role -ne 'unpublished') { throw "Draft role is not unpublished: $($draft.role)" }
if ($draft.shop -ne $store) { throw "Draft store mismatch: $($draft.shop)" }
if ($draft.name -ne $draftName) { throw "Draft name mismatch: $($draft.name)" }
$draft | Select-Object id, name, role, shop, editor_url, preview_url | Format-List
```

Expected: a new theme with role `unpublished`, exact SHA-bearing name, and machine-readable editor/preview URLs.

- [ ] **Step 4: Re-prove live theme identity did not move**

```powershell
$before = Get-Content -LiteralPath 'output/content-first-fresh-base/baseline-receipt.json' -Raw | ConvertFrom-Json
$afterLines = & npx --yes '@shopify/cli@4.7.1' theme list --store $store --role live --json
if ($LASTEXITCODE -ne 0) { throw 'Post-push live-theme listing failed.' }
$after = @(($afterLines -join [Environment]::NewLine) | ConvertFrom-Json)
if ($after.Count -ne 1 -or [string]$after[0].id -ne [string]$before.theme_id) { throw 'Live theme identity changed.' }
```

Expected: live theme ID remains exactly the captured ID. Stop immediately on mismatch.

- [ ] **Step 5: Prove hidden content is reviewable before building all resources**

Create only `Power Ratings Preview` as Hidden, assign template suffix `power-ratings`, save, and use Shopify Admin's Preview action with the unpublished theme. Confirm it renders native context plus the app without becoming visible on the live storefront.

Then create one hidden/draft test article with a reviewed human byline and use Admin Preview to confirm the article template renders while its public live route remains unavailable.

Expected: both are reviewable through authenticated Admin preview and absent from the public live storefront. If either cannot be isolated and reviewed, stop and report the platform limitation; do not make it visible as a workaround.

- [ ] **Step 6: Create remaining isolated preview resources**

- Create Hidden pages `Fantasy Preview`, `Methodology Preview`, and `Authors Preview` with exact handles.
- Assign `page.fantasy` only to Fantasy Preview; leave Methodology and Authors on the fresh default page template. Keep Power Ratings Preview on `page.power-ratings`.
- Reuse the existing live Accountability page read-only; do not edit it.
- Create `Content First Preview` menu in order: Home, Power Ratings Preview, Fantasy Preview, Shop.
- Create `Content Footer Preview` with Methodology Preview, Accountability, Authors Preview, Power Ratings archive, and Shop.
- Create only hidden/draft articles needed to exercise one flagship, latest NFL analysis, Dynasty, DFS, and T-60 process card. Nothing is made visible.
- Create missing compatible metafield definitions with types: deck `single_line_text_field`; byline `single_line_text_field`; updated_at `date_time`; model_version `single_line_text_field`; key_takeaway `multi_line_text_field`; sources `rich_text_field`; methodology `page_reference`; correction_history `rich_text_field`.
- If Shopify names a type differently or rejects one, stop and record the Admin validation message instead of guessing.
- Verify every displayed date, rating, model version, source statement, human byline, and HOLD label immediately before saving.
- Keep PGO v2, private fantasy preview rows, inferred healthy status, and unlocked projections out of every resource.
- Fantasy body states that official opening-night inactives are pending and explains the T-60 lock without projecting availability.

- [ ] **Step 7: Configure only the unpublished theme**

Open `$draft.editor_url` and configure the flagship article/status, exactly five reviewed ratings, latest/Dynasty/DFS sources, accountability link, one existing email form after useful content, four-item `From the Outlet` module last, and reviewed ratings metadata/links.

Save only in the SHA-named unpublished theme. Do not click Publish, edit code in Admin, alter live menus, assign templates to canonical pages, create redirects, or change analytics settings.

---

### Task 8: Perform real visual, accessibility, iframe, and commerce approval

**Files:**

- Create, ignored: `output/content-first-fresh-base/screenshots/**`
- Create, ignored: `output/content-first-fresh-base/draft-review.md`

- [ ] **Step 1: Capture the real draft at approved widths**

Use the `playwright` skill against the authenticated unpublished preview; do not add Playwright to the repository. Capture homepage, Power Ratings, Fantasy, one article, one collection, one product, and cart at widths `320`, `390`, `768`, and `1440` pixels.

Expected: approved editorial order, one mobile reading path, no document-level horizontal scrolling, and merchandise last/subordinate.

- [ ] **Step 2: Run keyboard and accessibility checks**

Verify one H1 per content page; visible focus; keyboard menu/traversal; meaningful image alt; textual badge meaning; WCAG AA contrast; no empty optional headings/separators; and no two-dimensional scrolling at 200% zoom with `320px` CSS width. Record pass/fail evidence in `draft-review.md`.

- [ ] **Step 3: Verify iframe integration without changing its artifact**

Verify native context precedes the iframe; origin is exactly `https://walshja9.github.io`; tabs, sorting, snapshots, and drawer work by keyboard; `npr:ready`, bounded `npr:height`, and `npr:viewport` work; spoofed-origin messages cannot resize the frame; and `docs/index.html` retains its protected hash. Do not regenerate or deploy it.

- [ ] **Step 4: Smoke-test commerce without an order**

Verify collection navigation, product cards, variant selection, add-to-cart, quantity update/removal, checkout start, return-to-store, and nonblocking app embeds. Stop before order placement; do not charge, fulfill, edit inventory, or change commerce settings.

- [ ] **Step 5: Present approval package and stop**

Present unpublished preview/editor URLs and theme identity; baseline/implementation SHAs; unchanged live theme identity; ZIP manifest/hash; test and Theme Check evidence; commerce hashes; desktop/mobile captures; editorial checklist; keyboard/iframe/commerce results; and every failed or unavailable check.

Ask for an explicit visual verdict. Approval completes this plan only at the unpublished-draft boundary. Revisions stay inside the 15-file allowlist and the same unpublished theme, followed by Tasks 6 and 8 again. Publishing, canonical-route changes, redirects, live navigation, Git push, merge, deployment, and cutover require a separate approved plan.
