# PGO Fantasy Live Release Refresh Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the verified 2026 Week 1 fantasy rankings on the tracked PGO ratings page without allowing the automatic McCabe refresh to remove them.

**Architecture:** Keep fantasy generation private-only. Teach the existing refresh path to extract an already published fantasy panel, rebuild the normal ratings page and comparison panel, then reinsert the preserved fantasy panel through the existing checked-in injector. Promote the independently verified private artifact once, push `main`, and verify the workflow, Pages build, and live browser surface.

**Tech Stack:** Python 3 standard library, `unittest`, Git, GitHub CLI, GitHub Actions/Pages, PowerShell, and Playwright CLI. No new dependency, service, endpoint, or Shopify mutation.

## Global Constraints

- Repository: `D:\Claude Context\Postgame_Outlet`, branch `main`.
- Approved design: `docs/superpowers/specs/2026-09-04-pgo-fantasy-live-release-refresh-preservation-design.md` at `21aa549a1330951c3daa513da98b417fad3eb632`.
- Confirmed GitHub account: `walshja9`; remote: `https://github.com/walshja9/Postgame_Outlet.git`.
- Fetched remote base: `origin/main` at `8aae9438d251c645509d3df15a31bb86d50059b9`; it was zero commits ahead of local `main` at planning time.
- Verified private artifact: `D:\CodexWorktrees\Postgame_Outlet-fantasy-qb-depth-eligibility\output\fantasy-week1-site-preview\20260904-020644\index.html`.
- Required artifact SHA-256: `209a0d7ec237d8df816f9e1b9d9e562a4796f3d113b4ac14b71422b38d629382`.
- Frozen source: `prospective_evidence\fantasy-2026-week-01\operational-v2-2026-09-03-134700\preview-week-1-v2-2026-09-03-135256.json`.
- Required source SHA-256: `65b90d8860044613e9acce45cf644b62dbbc3bf22ffae25c309fe19a111548a2`.
- Keep `--fantasy-preview` private-only; do not add a reusable public-generation flag.
- Preserve the fantasy panel's rendered rankings bytes during McCabe refreshes.
- Preserve the legacy refresh result when no fantasy tab is present.
- Fail closed on missing, partial, duplicate, or structurally changed fantasy/comparison markers.
- Keep `Experimental model — HOLD`, `PREVIEW / HOLD`, non-gradeable status, and all provenance disclosures.
- Preserve the seven pre-existing untracked path groups. Stage files with explicit paths only.
- Do not change Shopify, frozen model/source evidence, Pages settings, workflows, or the externally managed feature worktree.
- Stop before push if `origin/main` advances, any verification fails, or the outbound scan finds sensitive material.
- Stop after push if the workflow, Pages build, remote ancestry, live content, browser console, or network gate fails; do not attempt a second mutation automatically.

---

### Task 1: Preserve an Existing Fantasy Surface During McCabe Refresh

**Files:**
- Modify: `tests/test_pgo_comparison.py` after `test_refresh_mccabe_updates_only_current_mccabe_fields`
- Modify: `pgo_comparison.py:955-967`
- Modify: `pgo_comparison.py:1111-1118`

**Interfaces:**
- Consumes: `extract_comparison_panel(existing_html: str) -> str`, `inject_comparison(base_html: str, panel_html: str) -> str`, and `inject_fantasy_preview(existing_html: str, panel_html: str) -> str`.
- Produces: `_extract_published_fantasy_panel(existing_html: str) -> str | None` and a `refresh_mccabe_page()` result that preserves one valid published fantasy panel.

- [ ] **Step 1: Add two failing refresh regression tests**

Add these methods to `ComparisonTests` immediately after the existing McCabe refresh test:

```python
    def test_refresh_mccabe_preserves_published_fantasy_panel(self):
        comparison_rows = [{
            "team": "Los Angeles Rams",
            "mccabe_rank": 1,
            "mccabe_rating": 7.5,
            "full_strength_rank": 2,
            "full_strength_rating": 6.653245,
            "availability_adjustment": 0.0,
            "current_lineup_rank": 2,
            "current_lineup_rating": 6.653245,
            "rank_disagreement": 1,
            "rating_disagreement": -0.846755,
        }]
        current_rows = [{
            "team": "Los Angeles Rams",
            "abbr": "LAR",
            "rank": 3,
            "rating": 5.5,
        }]
        fantasy_panel = pgo_comparison.render_fantasy_panel(
            self._fantasy_preview()
        )
        published = pgo_comparison.inject_fantasy_preview(
            pgo_comparison.inject_comparison(
                self._base_html(),
                pgo_comparison.render_comparison_panel(
                    comparison_rows, self._held_receipt()
                ),
            ),
            fantasy_panel,
        )

        with (
            patch.object(
                pgo_comparison, "load_mccabe_rows", return_value=current_rows
            ),
            patch.object(
                pgo_comparison,
                "mccabe_source_timestamp",
                return_value="2026-09-04T12:00:00-04:00",
            ),
        ):
            output = pgo_comparison.refresh_mccabe_page(
                self._base_html(), published
            )

        self.assertIn(fantasy_panel, output)
        self.assertEqual(output.count('id="tab-fantasy"'), 1)
        self.assertEqual(output.count('id="panel-fantasy"'), 1)
        self.assertEqual(output.count(pgo_comparison.FANTASY_CSS), 1)
        self.assertEqual(output.count(pgo_comparison.FANTASY_SCRIPT), 1)
        self.assertIn(pgo_comparison.FANTASY_TAB, output)
        self.assertIn(
            '<section class="panel active" id="panel-fantasy"', output
        )
        self.assertNotIn(
            '<section class="panel active" id="panel-comparison"', output
        )
        self.assertIn(
            'data-sort="3">3</td><td data-sort="5.5">+5.5', output
        )

    def test_refresh_mccabe_rejects_invalid_fantasy_markers(self):
        comparison_rows = [{
            "team": "Los Angeles Rams",
            "mccabe_rank": 1,
            "mccabe_rating": 7.5,
            "full_strength_rank": 2,
            "full_strength_rating": 6.653245,
            "availability_adjustment": 0.0,
            "current_lineup_rank": 2,
            "current_lineup_rating": 6.653245,
            "rank_disagreement": 1,
            "rating_disagreement": -0.846755,
        }]
        current_rows = [{
            "team": "Los Angeles Rams",
            "abbr": "LAR",
            "rank": 3,
            "rating": 5.5,
        }]
        comparison = pgo_comparison.inject_comparison(
            self._base_html(),
            pgo_comparison.render_comparison_panel(
                comparison_rows, self._held_receipt()
            ),
        )
        complete = pgo_comparison.inject_fantasy_preview(
            comparison,
            pgo_comparison.render_fantasy_panel(self._fantasy_preview()),
        )
        invalid_pages = (
            comparison.replace(
                pgo_comparison.COMPARISON_TAB,
                pgo_comparison.COMPARISON_TAB + pgo_comparison.FANTASY_TAB,
                1,
            ),
            complete.replace(
                pgo_comparison.FANTASY_TAB,
                pgo_comparison.FANTASY_TAB + pgo_comparison.FANTASY_TAB,
                1,
            ),
        )

        with (
            patch.object(
                pgo_comparison, "load_mccabe_rows", return_value=current_rows
            ),
            patch.object(
                pgo_comparison,
                "mccabe_source_timestamp",
                return_value="2026-09-04T12:00:00-04:00",
            ),
        ):
            for page in invalid_pages:
                with self.subTest(page=page[:80]):
                    with self.assertRaisesRegex(
                        ValueError,
                        "fantasy preview markers are incomplete or duplicated",
                    ):
                        pgo_comparison.refresh_mccabe_page(
                            self._base_html(), page
                        )
```

- [ ] **Step 2: Run the two tests and verify RED**

Run:

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_comparison.ComparisonTests.test_refresh_mccabe_preserves_published_fantasy_panel `
  tests.test_pgo_comparison.ComparisonTests.test_refresh_mccabe_rejects_invalid_fantasy_markers -v
```

Expected: nonzero exit. The preservation case raises `Existing public board has no PGO comparison panel`; at least one invalid-marker subtest reports that the required `ValueError` was not raised or had the wrong message.

- [ ] **Step 3: Broaden comparison extraction and add strict fantasy extraction**

Replace `extract_comparison_panel()` and add the private helper immediately after it:

```python
def extract_comparison_panel(existing_html):
    identifier = 'id="panel-comparison"'
    if existing_html.count(identifier) == 0:
        raise ValueError(
            "Existing public board has no PGO comparison panel; publish an approved PGO release first"
        )
    start_markers = (
        '<section class="panel active" id="panel-comparison"',
        '<section class="panel" id="panel-comparison"',
    )
    matches = [
        marker for marker in start_markers
        if existing_html.count(marker) == 1
    ]
    if existing_html.count(identifier) != 1 or len(matches) != 1:
        raise ValueError("Existing PGO comparison panel markers changed")
    start = existing_html.find(matches[0])
    end_marker = "</section>"
    end = existing_html.find(end_marker, start)
    if end < 0:
        raise ValueError("Existing PGO comparison panel is incomplete")
    return existing_html[start:end + len(end_marker)]


def _extract_published_fantasy_panel(existing_html):
    tab_count = existing_html.count('id="tab-fantasy"')
    panel_count = existing_html.count('id="panel-fantasy"')
    if tab_count == panel_count == 0:
        return None
    if (
        tab_count != 1
        or panel_count != 1
        or existing_html.count(FANTASY_TAB) != 1
        or existing_html.count(FANTASY_CSS) != 1
        or existing_html.count(FANTASY_SCRIPT) != 1
    ):
        raise ValueError(
            "Existing fantasy preview markers are incomplete or duplicated"
        )
    start_marker = '<section class="panel active" id="panel-fantasy"'
    start = existing_html.find(start_marker)
    end_marker = "</section>"
    end = existing_html.find(end_marker, start)
    if start < 0 or end < 0:
        raise ValueError(
            "Existing fantasy preview markers are incomplete or duplicated"
        )
    return existing_html[start:end + len(end_marker)]
```

- [ ] **Step 4: Preserve the extracted fantasy panel in `refresh_mccabe_page()`**

Replace the function with:

```python
def refresh_mccabe_page(base_html, existing_html, mccabe_path=MCCABE_PATH):
    mccabe_rows = load_mccabe_rows(mccabe_path)
    fantasy_panel = _extract_published_fantasy_panel(existing_html)
    comparison_panel = extract_comparison_panel(existing_html)
    if fantasy_panel is not None:
        inactive_start = '<section class="panel" id="panel-comparison"'
        hidden_label = 'aria-labelledby="tab-comparison" hidden>'
        if (
            comparison_panel.count(inactive_start) != 1
            or comparison_panel.count(hidden_label) != 1
        ):
            raise ValueError("Existing fantasy preview comparison state changed")
        comparison_panel = (
            comparison_panel
            .replace(
                inactive_start,
                '<section class="panel active" id="panel-comparison"',
                1,
            )
            .replace(
                hidden_label,
                'aria-labelledby="tab-comparison">',
                1,
            )
        )
    panel = _refresh_comparison_panel(
        comparison_panel,
        mccabe_rows,
        mccabe_source_timestamp(mccabe_path),
    )
    output = inject_comparison(base_html, panel)
    if fantasy_panel is not None:
        output = inject_fantasy_preview(output, fantasy_panel)
    return output
```

- [ ] **Step 5: Run the two tests and verify GREEN**

Run the Step 2 command again.

Expected: `Ran 2 tests` and `OK`.

- [ ] **Step 6: Run focused refresh and workflow regressions**

Run:

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_comparison `
  tests.test_public_board_workflow -v
```

Expected: `Ran 32 tests` and `OK`.

- [ ] **Step 7: Review and commit the focused implementation**

Run:

```powershell
git diff --check
git diff -- pgo_comparison.py tests/test_pgo_comparison.py
git status --short
git add -- pgo_comparison.py tests/test_pgo_comparison.py
git commit -m "fix: preserve fantasy tab during board refresh"
```

Expected: only the two named files are staged; the commit succeeds; the seven pre-existing untracked path groups remain untracked.

---

### Task 2: Qualify and Commit the Public Artifact

**Files:**
- Modify mechanically: `docs/index.html`

**Interfaces:**
- Consumes: the exact verified private artifact and the preservation behavior from Task 1.
- Produces: the tracked GitHub Pages document with one 447-row fantasy surface.

- [ ] **Step 1: Revalidate the frozen source and private artifact before copying**

Run:

```powershell
$source = 'prospective_evidence\fantasy-2026-week-01\operational-v2-2026-09-03-134700\preview-week-1-v2-2026-09-03-135256.json'
$artifact = 'D:\CodexWorktrees\Postgame_Outlet-fantasy-qb-depth-eligibility\output\fantasy-week1-site-preview\20260904-020644\index.html'
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
$artifactHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash.ToLowerInvariant()
if ($sourceHash -ne '65b90d8860044613e9acce45cf644b62dbbc3bf22ffae25c309fe19a111548a2') { throw "Source hash changed: $sourceHash" }
if ($artifactHash -ne '209a0d7ec237d8df816f9e1b9d9e562a4796f3d113b4ac14b71422b38d629382') { throw "Artifact hash changed: $artifactHash" }
```

Expected: exit 0 with no output.

- [ ] **Step 2: Promote the artifact byte-for-byte**

Run this mechanical artifact copy; do not edit the HTML manually:

```powershell
Copy-Item -LiteralPath $artifact -Destination 'docs\index.html'
$publicHash = (Get-FileHash -Algorithm SHA256 -LiteralPath 'docs\index.html').Hash.ToLowerInvariant()
if ($publicHash -ne $artifactHash) { throw "Public artifact copy changed bytes: $publicHash" }
```

Expected: exit 0 and `docs/index.html` SHA-256 equals `209a0d7e...d629382`.

- [ ] **Step 3: Run deterministic public-document checks**

Run:

```powershell
$html = [IO.File]::ReadAllText((Resolve-Path 'docs\index.html'))
$checks = [ordered]@{
  fantasy_tab = ([regex]::Matches($html, 'id="tab-fantasy"')).Count -eq 1
  fantasy_panel = ([regex]::Matches($html, 'id="panel-fantasy"')).Count -eq 1
  fantasy_rows = ([regex]::Matches($html, '<tr class="fantasy-row"')).Count -eq 447
  title = $html.Contains('2026 Week 1 Fantasy Rankings')
  row_receipt = $html.Contains('Rows: 502 total, 447 ranking-eligible.')
  hold = $html.Contains('PREVIEW / HOLD') -and $html.Contains('non-gradeable')
}
$failed = @($checks.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object Key)
if ($failed.Count) { throw "Public artifact checks failed: $($failed -join ', ')" }
```

Expected: exit 0 with no output.

- [ ] **Step 4: Run the complete pre-publication verification gate**

Run each command separately and stop on any nonzero exit:

```powershell
python -B -m py_compile pgo_fantasy_prospective.py pgo_comparison.py
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveWeek1PreviewLoadTests `
  tests.test_pgo_comparison.ComparisonTests `
  tests.test_public_board_workflow -v
python -B -W error::ResourceWarning -m unittest discover -s tests -v
git diff --check
```

Expected: compile exit 0; focused `Ran 39 tests` and `OK`; discovery `Ran 409 tests` and `OK`; diff check exits 0 without output.

- [ ] **Step 5: Audit and commit only the public document**

Run:

```powershell
git status --short
git diff --stat -- docs/index.html
git diff --numstat -- docs/index.html
git add -- docs/index.html
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 1 -or $staged[0] -ne 'docs/index.html') { throw "Unexpected staged files: $staged" }
git commit -m "release: publish Week 1 fantasy preview"
```

Expected: the release commit contains only `docs/index.html`; unrelated untracked paths remain untouched.

---

### Task 3: Push, Monitor, and Verify the Public Release

**Files:**
- No planned source edits.
- The GitHub Actions bot may add one `docs/index.html`-only refresh commit.

**Interfaces:**
- Consumes: verified local `main`, confirmed `walshja9` authentication, `update-board.yml`, and branch-based GitHub Pages.
- Produces: a successful remote workflow/build and a verified live page at `https://walshja9.github.io/Postgame_Outlet/`.

- [ ] **Step 1: Repeat the remote and outbound safety gate**

Run:

```powershell
gh auth status -h github.com
git fetch --prune origin main
$divergence = git rev-list --left-right --count origin/main...main
if (-not $divergence.StartsWith("0`t")) { throw "origin/main advanced: $divergence" }
$changed = @(git diff --name-only origin/main..main)
$sensitive = @(git grep -l -I -E 'gho_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,}|ANTHROPIC_API_KEY[[:space:]]*=|OPENAI_API_KEY[[:space:]]*=|password[[:space:]]*[:=][[:space:]]*[^<{$]' HEAD -- $changed 2>$null)
if ($sensitive.Count) { throw "Sensitive outbound files: $sensitive" }
git status --short --branch
git log --oneline origin/main..main
git diff --name-status origin/main..main
```

Expected: authenticated account is `walshja9`; remote is zero commits ahead; no sensitive files are reported; tracked state is clean; outbound files match the reviewed PGO fantasy/design/test/public scope.

- [ ] **Step 2: Push `main` once**

Run:

```powershell
$releaseSha = git rev-parse HEAD
git push origin main
```

Expected: fast-forward push succeeds with native exit code 0. Do not retry automatically if it fails.

- [ ] **Step 3: Locate and watch the triggered Update board run**

Run:

```powershell
$deadline = (Get-Date).AddMinutes(5)
do {
  $runs = @(gh run list --repo walshja9/Postgame_Outlet --workflow update-board.yml --commit $releaseSha --limit 1 --json databaseId,status,conclusion,url,headSha | ConvertFrom-Json)
  if ($runs.Count) { $run = $runs[0]; break }
  Start-Sleep -Seconds 5
} while ((Get-Date) -lt $deadline)
if ($null -eq $run) { throw "No Update board run found for $releaseSha" }
$run | Format-List databaseId,status,conclusion,url,headSha
gh run watch $run.databaseId --repo walshja9/Postgame_Outlet --exit-status
```

Expected: one run for `$releaseSha`; `gh run watch` exits 0 with conclusion `success`.

- [ ] **Step 4: Reconcile the workflow's final remote commit**

Run:

```powershell
git fetch origin main
$remoteHead = git rev-parse origin/main
git merge-base --is-ancestor $releaseSha $remoteHead
if ($LASTEXITCODE -ne 0) { throw "Release commit is not on origin/main" }
if ($remoteHead -ne $releaseSha) {
  $botFiles = @(git diff --name-only "$releaseSha..$remoteHead")
  if ($botFiles.Count -ne 1 -or $botFiles[0] -ne 'docs/index.html') { throw "Unexpected workflow files: $botFiles" }
  git log --oneline "$releaseSha..$remoteHead"
  git merge --ff-only origin/main
}
```

Expected: the release is an ancestor of final `origin/main`; any workflow commit changes only `docs/index.html`; local `main` fast-forwards to the remote result.

- [ ] **Step 5: Wait for the matching GitHub Pages build**

Run:

```powershell
$deadline = (Get-Date).AddMinutes(10)
do {
  $build = gh api repos/walshja9/Postgame_Outlet/pages/builds/latest | ConvertFrom-Json
  if ($build.commit -eq $remoteHead -and $build.status -eq 'built') { break }
  if ($build.commit -eq $remoteHead -and $build.status -eq 'errored') { throw "Pages build errored for $remoteHead" }
  Start-Sleep -Seconds 10
} while ((Get-Date) -lt $deadline)
if ($build.commit -ne $remoteHead -or $build.status -ne 'built') { throw "Pages did not build $remoteHead" }
$pages = gh api repos/walshja9/Postgame_Outlet/pages | ConvertFrom-Json
$build | Select-Object commit,status,created_at,updated_at,duration
$pages | Select-Object html_url,status,cname
```

Expected: latest Pages build has the exact final remote commit and status `built`; the configured URL remains the existing GitHub Pages URL.

- [ ] **Step 6: Verify live HTML and preserved ranking bytes**

Run:

```powershell
$liveUrl = "https://walshja9.github.io/Postgame_Outlet/?release=$remoteHead"
$liveHtml = (Invoke-WebRequest -UseBasicParsing $liveUrl).Content
$localHtml = [IO.File]::ReadAllText((Resolve-Path 'docs\index.html'))
function Get-FantasyPanel([string]$text) {
  $startMarker = '<section class="panel active" id="panel-fantasy"'
  $start = $text.IndexOf($startMarker, [StringComparison]::Ordinal)
  if ($start -lt 0) { throw 'Fantasy panel start missing' }
  $endMarker = '</section>'
  $end = $text.IndexOf($endMarker, $start, [StringComparison]::Ordinal)
  if ($end -lt 0) { throw 'Fantasy panel end missing' }
  $text.Substring($start, $end + $endMarker.Length - $start)
}
function Get-TextSha256([string]$text) {
  $sha = [Security.Cryptography.SHA256]::Create()
  try { ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text)))).Replace('-', '').ToLowerInvariant() }
  finally { $sha.Dispose() }
}
$livePanelHash = Get-TextSha256 (Get-FantasyPanel $liveHtml)
$localPanelHash = Get-TextSha256 (Get-FantasyPanel $localHtml)
if ($livePanelHash -ne $localPanelHash) { throw "Live fantasy panel differs: $livePanelHash" }
if (([regex]::Matches($liveHtml, 'id="tab-fantasy"')).Count -ne 1) { throw 'Live fantasy tab count changed' }
if (([regex]::Matches($liveHtml, '<tr class="fantasy-row"')).Count -ne 447) { throw 'Live fantasy row count changed' }
if (-not $liveHtml.Contains('PREVIEW / HOLD') -or -not $liveHtml.Contains('Rows: 502 total, 447 ranking-eligible.')) { throw 'Live HOLD or row receipt missing' }
```

Expected: direct Pages response has one fantasy tab, 447 eligible rows, the HOLD/row receipt, and the exact same fantasy-panel hash as final tracked `docs/index.html`.

- [ ] **Step 7: Verify desktop and mobile behavior in a real browser**

Run from PowerShell after the live HTML gate:

```powershell
$pw = @('--yes', '--package', '@playwright/cli', 'playwright-cli', '--session', 'pgo-live-release')
& npx.cmd @pw open $liveUrl
& npx.cmd @pw snapshot
& npx.cmd @pw resize 1440 1000
& npx.cmd @pw run-code "await page.waitForLoadState('networkidle'); const tab=page.locator('#tab-fantasy'); if(await tab.count()!==1) throw new Error('fantasy tab count'); await tab.click(); if(await tab.getAttribute('aria-selected')!=='true') throw new Error('fantasy tab inactive'); if(await page.locator('#fantasy-rows .fantasy-row').count()!==447) throw new Error('fantasy row count');"
& npx.cmd @pw console error
& npx.cmd @pw network
& npx.cmd @pw resize 390 844
& npx.cmd @pw reload
& npx.cmd @pw snapshot
& npx.cmd @pw run-code "await page.waitForLoadState('networkidle'); if(await page.locator('#tab-fantasy').getAttribute('aria-selected')!=='true') throw new Error('mobile fantasy tab inactive'); const overflow=await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth); if(overflow) throw new Error('mobile page overflow');"
& npx.cmd @pw console error
& npx.cmd @pw network
& npx.cmd @pw close
```

Expected: every command exits 0; snapshots show the fantasy surface at both widths; no console errors or failed network requests appear; the mobile document does not overflow.

- [ ] **Step 8: Record and report the final release state**

Run:

```powershell
git rev-parse HEAD
git rev-parse origin/main
git status --short --branch
(Get-FileHash -Algorithm SHA256 -LiteralPath 'docs\index.html').Hash.ToLowerInvariant()
```

Append the final local/remote SHA, workflow URL/conclusion, Pages build commit/status, live fantasy-panel hash, test counts, and boundary statement to:

`D:\Claude Context\Postgame_Outlet\.git\worktrees\Postgame_Outlet-fantasy-qb-depth-eligibility\sdd\progress.md`

Use `apply_patch`; state that Shopify and the externally managed feature worktree were untouched.

Expected: local `main` and `origin/main` match; only the seven pre-existing untracked path groups remain; the durable handoff contains exact evidence.
