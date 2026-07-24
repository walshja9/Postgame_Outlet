# PGO v1 Primary Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish PGO v1 as the first and default Power Ratings view while preserving its Experimental — HOLD disclosure and McCabe's independent human ratings.

**Architecture:** Create a release branch at the last v1-only commit so v1.1 and v1.2 research cannot enter the deployment. Extend the existing combined-page generator with PGO-first markup and one explicit, fixed-destination publication option; reuse the existing GitHub Pages file and Shopify iframe URL.

**Tech Stack:** Python 3.12 standard library, NumPy already required by the PGO model, `unittest`, generated static HTML, vanilla JavaScript, GitHub Pages.

## Global Constraints

- PGO v1 remains **Experimental model — HOLD** and must not be called validated, proven, or official.
- PGO v1 ratings, training, receipts, hashes, and status remain unchanged.
- McCabe's ratings remain visible, attributed, independent, and unblended.
- The default generator command remains preview-only under `output/`.
- Public generation requires one explicit option and may write only `docs/index.html`.
- Keep the existing Shopify iframe URL; do not edit Shopify, menus, themes, redirects, analytics, commerce, or workflows.
- Do not push v1.1, v1.2, `.superpowers/`, caches, or ignored previews.
- Add no dependency, service, database, workflow, or new public URL.
- Stop before deployment if tests, input gates, artifact checks, or visual review fail.

## File Map

- Modify `pgo_comparison.py`: PGO-first markup, PGO-rank initial order, and explicit fixed-destination publication.
- Modify `tests/test_pgo_comparison.py`: release-path, initial-state, order, disclosure, and separation checks.
- Modify `README.md`: document the explicit reviewed publication command.
- Modify generated `docs/index.html`: reviewed GitHub Pages artifact.
- Preserve `data/**`, `research/**`, `generate_site.py`, `.github/**`, and Shopify files byte-for-byte.

---

### Task 1: Build the scoped PGO-first release generator

**Files:**
- Modify: `pgo_comparison.py:20-410`
- Modify: `tests/test_pgo_comparison.py:1-179`
- Modify: `README.md:55-72`

**Interfaces:**
- Consumes: `load_comparison_rows(mccabe_path, model_path, backtest_path, snapshots_path=SNAPSHOTS_PATH)`, `render_comparison_panel(rows, receipt)`, `generate_site.build_html(rows, config, generated_at=None)`, and the existing fail-closed receipt/snapshot checks.
- Produces: `python pgo_comparison.py` for a private PGO-first preview and `python pgo_comparison.py --publish` for the fixed `docs/index.html` target.

- [ ] **Step 1: Create a v1-only release worktree**

Run from `C:\Users\Alex\Documents\Game Design\Postgame_Outlet-pgo-model`:

```powershell
git worktree add -b codex/pgo-v1-release "C:\Users\Alex\Documents\Game Design\Postgame_Outlet-pgo-v1-release" da6e03f
$planCommit = git rev-list -1 codex/pgo-team-model-workspace -- docs/superpowers/plans/2026-07-24-pgo-v1-primary-release.md
git -C "C:\Users\Alex\Documents\Game Design\Postgame_Outlet-pgo-v1-release" cherry-pick ad81de1 $planCommit
```

Expected: the new branch ends at the approved v1 release spec and this plan, and:

```powershell
git -C "C:\Users\Alex\Documents\Game Design\Postgame_Outlet-pgo-v1-release" log -1 --oneline
git -C "C:\Users\Alex\Documents\Game Design\Postgame_Outlet-pgo-v1-release" merge-base --is-ancestor da6e03f HEAD
git -C "C:\Users\Alex\Documents\Game Design\Postgame_Outlet-pgo-v1-release" merge-base --is-ancestor 9999800 HEAD
```

returns success for `da6e03f` and failure for `9999800`, proving the release includes v1 but excludes v1.1.

- [ ] **Step 2: Write failing primary-view and publication tests**

In `tests/test_pgo_comparison.py`, add:

```python
from unittest.mock import patch
```

Add these methods to `ComparisonTests`:

```python
    @staticmethod
    def _base_html():
        return (
            '<html><head><meta name="description" content="Sean McCabe\N{RIGHT SINGLE QUOTATION MARK}s board">'
            "<style>base</style></head><body>"
            '<div class="updated">By Sean McCabe &middot; Edition</div>'
            '    <button type="button" class="tab active" id="tab-ratings" '
            'role="tab" aria-selected="true" aria-controls="panel-ratings" '
            'tabindex="0" data-panel="ratings">Power Ratings</button>'
            '<button type="button" class="tab" id="tab-qbs" role="tab" '
            'aria-selected="false" aria-controls="panel-qbs" tabindex="-1" '
            'data-panel="qbs" style="display:block">QB Ratings</button>'
            '<button type="button" class="tab" id="tab-method" role="tab" '
            'aria-selected="false" aria-controls="panel-method" tabindex="-1" '
            'data-panel="method">Methodology</button>'
            '  <section class="panel active" id="panel-ratings" '
            'role="tabpanel">McCabe</section>'
            '<section class="panel" id="panel-method">Method</section>'
            "</body></html>"
        )

    def test_pgo_is_primary_and_rows_start_in_pgo_rank_order(self):
        rows = [
            {
                "team": "Buffalo Bills", "mccabe_rank": 1,
                "mccabe_rating": 7.0, "full_strength_rank": 2,
                "full_strength_rating": 0.5, "availability_adjustment": 2.0,
                "current_lineup_rank": 1, "current_lineup_rating": 2.5,
                "rank_disagreement": 1, "rating_disagreement": -6.5,
            },
            {
                "team": "Miami Dolphins", "mccabe_rank": 2,
                "mccabe_rating": -4.5, "full_strength_rank": 1,
                "full_strength_rating": 1.0, "availability_adjustment": -2.0,
                "current_lineup_rank": 2, "current_lineup_rating": -1.0,
                "rank_disagreement": -1, "rating_disagreement": 5.5,
            },
        ]
        panel = pgo_comparison.render_comparison_panel(
            rows, self._held_receipt()
        )
        base = (
            '<html><head><meta name="description" content="Sean McCabe\N{RIGHT SINGLE QUOTATION MARK}s board">'
            "<style>base</style></head><body>"
            '<div class="updated">By Sean McCabe &middot; Edition</div>'
            '    <button type="button" class="tab active" id="tab-ratings" '
            'role="tab" aria-selected="true" aria-controls="panel-ratings" '
            'tabindex="0" data-panel="ratings">Power Ratings</button>'
            '<button type="button" class="tab" id="tab-qbs" role="tab" '
            'aria-selected="false" aria-controls="panel-qbs" tabindex="-1" '
            'data-panel="qbs" style="display:block">QB Ratings</button>'
            '  <section class="panel active" id="panel-ratings" '
            'role="tabpanel">McCabe</section>'
            "</body></html>"
        )

        output = pgo_comparison.inject_comparison(self._base_html(), panel)

        self.assertLess(
            output.index('id="tab-comparison"'),
            output.index('id="tab-ratings"'),
        )
        self.assertIn(
            'class="tab active" id="tab-comparison"', output
        )
        self.assertIn(
            'aria-selected="true" aria-controls="panel-comparison"', output
        )
        self.assertIn(
            'class="panel active" id="panel-comparison"', output
        )
        self.assertIn(
            'class="panel" id="panel-ratings" hidden', output
        )
        self.assertIn(">McCabe Ratings</button>", output)
        self.assertIn(">McCabe QBs</button>", output)
        self.assertIn(">McCabe Method</button>", output)
        self.assertIn("By Postgame Outlet Model", output)
        self.assertIn(
            "Postgame Outlet’s independent PGO v1", output
        )
        self.assertLess(panel.index("Miami Dolphins"), panel.index("Buffalo Bills"))
        self.assertEqual(panel.count('aria-sort="ascending"'), 1)
        self.assertEqual(panel.count('aria-sort="none"'), 9)

    def test_cli_publish_targets_only_docs_index(self):
        with patch.object(pgo_comparison, "atomic_write_text") as write:
            code = pgo_comparison.main(["--publish"])

        self.assertEqual(code, 0)
        target = Path(write.call_args.args[0]).resolve()
        self.assertEqual(target, (pgo_comparison.HERE / "docs" / "index.html").resolve())
```

Delete the redundant local `base = (` block from
`test_pgo_is_primary_and_rows_start_in_pgo_rank_order`.

Replace the hand-built `base` values in
`test_generated_comparison_is_sortable_and_accessible`,
`test_injection_adds_one_accessible_tab_and_preserves_base_page`, and
`test_injection_suppresses_browser_favicon_request` with:

```python
        base = self._base_html()
```


Update `test_generated_comparison_is_sortable_and_accessible` to expect one initial sorted column:

```python
        self.assertEqual(panel.count('aria-sort="ascending"'), 1)
        self.assertEqual(panel.count('aria-sort="none"'), 9)
```

Add working public-link assertions to `test_panel_exposes_hold_metrics_and_no_third_ranking`:

```python
        self.assertIn("https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_v1/backtest.json", panel)
        self.assertIn("https://github.com/walshja9/Postgame_Outlet/blob/main/docs/superpowers/specs/2026-07-21-independent-forward-looking-pgo-model-design.md", panel)
```


- [ ] **Step 3: Run the focused tests to verify RED**

Run:

```powershell
python -m unittest tests.test_pgo_comparison -v
```

Expected: failures because the comparison tab is not initially active, rows remain McCabe-ranked, and `--publish` is unknown.

- [ ] **Step 4: Implement the minimal PGO-first rendering**

In `render_comparison_panel(rows, receipt)`, sort the supplied rows before rendering:

```python
def render_comparison_panel(rows, receipt):
    rows = sorted(
        rows,
        key=lambda row: (row["full_strength_rank"], row["team"]),
    )
    interval = receipt["aggregate_interval"]
```

Render cells and headers in this order:

```python
        f'<td data-sort="{row["full_strength_rank"]}">{row["full_strength_rank"]}</td>'
        f'<td data-sort="{row["full_strength_rating"]}">{_signed(row["full_strength_rating"])}</td>'
        f'<td data-sort="{row["availability_adjustment"]}">{_signed(row["availability_adjustment"])}</td>'
        f'<td data-sort="{row["current_lineup_rank"]}">{row["current_lineup_rank"]}</td>'
        f'<td data-sort="{row["current_lineup_rating"]}">{_signed(row["current_lineup_rating"])}</td>'
        f'<td data-sort="{row["mccabe_rank"]}">{row["mccabe_rank"]}</td>'
        f'<td data-sort="{row["mccabe_rating"]}">{_signed(row["mccabe_rating"])}</td>'
        f'<td data-sort="{row["rank_disagreement"]}">{row["rank_disagreement"]:+d}</td>'
        f'<td data-sort="{row["rating_disagreement"]}">{_signed(row["rating_disagreement"])}</td>'
```

Change the panel opening and heading to:

```html
  <section class="panel active" id="panel-comparison" role="tabpanel"
    aria-labelledby="tab-comparison">
    <div class="model-status">{html.escape(label)}</div>
    <h2>PGO v1 Power Ratings</h2>
    <p>Postgame Outlet's independent statistical rating, compared with McCabe's human rating and never blended.</p>
```

Replace the table header with:

```html
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="0">Team</button></th>
          <th scope="col" aria-sort="ascending"><button type="button" class="sort-button" data-column="1">PGO full #</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="2">PGO full</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="3">Avail.</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="4">PGO today #</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="5">PGO today</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="6">McCabe #</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="7">McCabe</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="8">Rank gap</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="9">Rating gap</button></th>
```

Replace the comparison links with public GitHub URLs that work from Pages:

```html
    <p class="comparison-links">
      <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_v1/backtest.json">Backtest receipt</a>
      &middot;
      <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/docs/superpowers/specs/2026-07-21-independent-forward-looking-pgo-model-design.md">Methodology and release rules</a>
    </p>
```


Make the PGO tab primary:

```python
COMPARISON_TAB = """
    <button type="button" class="tab active" id="tab-comparison" role="tab"
      aria-selected="true" aria-controls="panel-comparison" tabindex="0"
      data-panel="comparison">PGO Model</button>
"""
```

Initialize the sorter to the displayed order:

```javascript
    let activeColumn = 1;
    let ascending = true;
```

- [ ] **Step 5: Make the combined page PGO-first without changing the base generator**

Replace `inject_comparison(base_html, panel_html)` with:

```python
def inject_comparison(base_html, panel_html):
    rating_tab = (
        '    <button type="button" class="tab active" id="tab-ratings"'
    )
    rating_panel = (
        '  <section class="panel active" id="panel-ratings"'
    )
    fixed_replacements = (
        (
            '<meta name="description" content="Sean McCabe’s',
            '<meta name="description" content="Postgame Outlet’s independent PGO v1',
        ),
        (
            '<div class="updated">By Sean McCabe &middot;',
            '<div class="updated">By Postgame Outlet Model &middot;',
        ),
        (
            'aria-selected="true" aria-controls="panel-ratings" tabindex="0"',
            'aria-selected="false" aria-controls="panel-ratings" tabindex="-1"',
        ),
        (
            'data-panel="ratings">Power Ratings</button>',
            'data-panel="ratings">McCabe Ratings</button>',
        ),
        (">QB Ratings</button>", ">McCabe QBs</button>"),
        (">Methodology</button>", ">McCabe Method</button>"),
    )
    markers = (
        "</style>",
        "</body>",
        rating_tab,
        rating_panel,
        *(old for old, _new in fixed_replacements),
    )
    if any(base_html.count(marker) != 1 for marker in markers):
        raise ValueError("Base ratings template markers changed")

    output = base_html.replace(
        "</style>", MODEL_CSS + '\n</style>\n<link rel="icon" href="data:,">', 1
    )
    for old, new in fixed_replacements:
        output = output.replace(old, new, 1)
    output = output.replace(
        rating_tab,
        COMPARISON_TAB
        + '    <button type="button" class="tab" id="tab-ratings"',
        1,
    )
    output = output.replace(
        rating_panel,
        panel_html
        + '\n  <section class="panel" id="panel-ratings" hidden',
        1,
    )
    output = output.replace("</body>", COMPARISON_SCRIPT + "\n</body>", 1)
    return output
```

This reuses `generate_site.py` unchanged and fails closed if its expected HTML changes.

- [ ] **Step 6: Add the explicit fixed-destination publication option**

Add beside the existing path constants:

```python
PUBLIC_OUTPUT = HERE / "docs" / "index.html"
```

Replace `parse_args(argv=None)` with:

```python
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--output", type=Path, default=default_preview_path()
    )
    destination.add_argument(
        "--publish",
        action="store_true",
        help="write the reviewed combined page to docs/index.html",
    )
    return parser.parse_args(argv)
```

At the start of `main(argv=None)`, select the destination:

```python
        output = (
            PUBLIC_OUTPUT if args.publish else args.output
        ).resolve()
        preview_root = (HERE / "output").resolve()
        if not args.publish and preview_root not in output.parents:
            raise ValueError("Comparison output must stay under output/")
```

Keep every existing load, receipt, snapshot, integrity, and atomic-write check unchanged.

- [ ] **Step 7: Document the reviewed release command**

Append to the existing README comparison section:

````markdown
After editorial review and explicit publication approval, the fixed-destination
release command is:

```bash
python pgo_comparison.py --publish
```

It writes only `docs/index.html`. PGO v1 remains labeled
`Experimental model — HOLD`; the command does not modify Shopify or any rating
input.
````

- [ ] **Step 8: Run focused tests and commit**

Run:

```powershell
python -m unittest tests.test_pgo_comparison -v
python -m py_compile pgo_comparison.py
git diff --check
git status --short
```

Expected: all comparison tests pass; only `pgo_comparison.py`,
`tests/test_pgo_comparison.py`, and `README.md` are modified.

Commit:

```powershell
git add -- pgo_comparison.py tests/test_pgo_comparison.py README.md
git commit -m "Make PGO v1 the primary ratings view"
```

---

### Task 2: Generate and verify the public artifact

**Files:**
- Modify generated: `docs/index.html`

**Interfaces:**
- Consumes: the Task 1 `--publish` command and unchanged reviewed PGO/McCabe inputs.
- Produces: the exact static artifact served by GitHub Pages and the unchanged Shopify iframe.

- [ ] **Step 1: Run the complete repository test suite**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass. Stop if the command exits nonzero or does not print its final passing summary.

- [ ] **Step 2: Generate the dated release candidate**

Run:

```powershell
python pgo_comparison.py --output output/pgo-comparison-preview/2026-07-24/index.html
```

Expected:

```text
Wrote C:\Users\Alex\Documents\Game Design\Postgame_Outlet-pgo-v1-release\output\pgo-comparison-preview\2026-07-24\index.html
  32 teams | EXPERIMENTAL
```

- [ ] **Step 3: Inspect desktop and mobile behavior**

Serve the worktree:

```powershell
$server = Start-Process python -ArgumentList "-m","http.server","8765","--bind","127.0.0.1" -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru
```

Use the Playwright workflow to inspect:

```text
http://127.0.0.1:8765/output/pgo-comparison-preview/2026-07-24/index.html
```

Check at `1440x900` and `390x844`:

- PGO Model is the selected first tab.
- Experimental model — HOLD is visible without opening another tab.
- New England is the first row with PGO full rank 1.
- PGO columns precede McCabe columns.
- Sorting each representative text/numeric column updates the row order and announced sort state.
- McCabe Ratings and McCabe QBs remain reachable.
- Keyboard arrows move between tabs.
- The sticky team column and horizontal table scrolling work at mobile width.
- No clipped text, inaccessible controls, page-level horizontal overflow, or console errors appear.

Stop the server:

```powershell
Stop-Process -Id $server.Id
```

- [ ] **Step 4: Generate the fixed public artifact**

Run:

```powershell
python pgo_comparison.py --publish
```

Expected:

```text
Wrote C:\Users\Alex\Documents\Game Design\Postgame_Outlet-pgo-v1-release\docs\index.html
  32 teams | EXPERIMENTAL
```

- [ ] **Step 5: Verify scope and immutable inputs**

Run:

```powershell
git diff --check
git diff --exit-code -- data research generate_site.py .github
git status --short
```

Expected: only `docs/index.html` is modified; no input, model, receipt, workflow, Shopify, or ignored preview is staged.

Confirm the public artifact contains the release contract:

```powershell
rg -n "PGO Model|Experimental model — HOLD|PGO v1 Power Ratings|aggregate improvement ci positive|McCabe Ratings|McCabe QBs" docs/index.html
```

Expected: every phrase is present.

- [ ] **Step 6: Commit the generated artifact**

```powershell
git add -- docs/index.html
git commit -m "Publish PGO v1 primary ratings page"
```

---

### Task 3: Deploy and verify production

**Files:**
- No additional file changes.

**Interfaces:**
- Consumes: the tested release branch ending in the reviewed `docs/index.html`.
- Produces: a fast-forward update to remote `main`, the GitHub Pages deployment, and verification of the existing Shopify embed.

- [ ] **Step 1: Confirm the remote Pages target before pushing**

Run:

```powershell
gh api repos/walshja9/Postgame_Outlet/pages
```

Expected: Pages is enabled and reports a source using the repository's `docs/` artifact. Record the returned `html_url`.

- [ ] **Step 2: Rebase on current remote main and reverify**

Run:

```powershell
git pull --rebase origin main
python -m unittest tests.test_pgo_comparison -v
python -m unittest discover -s tests -v
git status --short
```

Expected: rebase succeeds, both test commands pass, and the worktree is clean.

- [ ] **Step 3: Push the scoped release to main**

Run:

```powershell
git push origin HEAD:main
```

Expected: a fast-forward update to `main`. The release history must not contain `9999800`:

```powershell
git merge-base --is-ancestor 9999800 HEAD
```

Expected: exit code 1.

- [ ] **Step 4: Wait for the Pages deployment**

Run:

```powershell
gh run list --branch main --limit 10
```

If a Pages workflow run is listed, watch that exact run:

```powershell
$run = gh run list --branch main --limit 10 --json databaseId,name,status |
    ConvertFrom-Json |
    Where-Object { $_.name -match "Pages" } |
    Select-Object -First 1
gh run watch $run.databaseId --exit-status
```

If Pages deployment is not represented as an Actions run, poll:

```powershell
gh api repos/walshja9/Postgame_Outlet/pages
```

until its status is built. Do not wait more than 60 seconds between updates.

- [ ] **Step 5: Verify GitHub Pages and Shopify**

Open the `html_url` returned by the Pages API and:

```text
https://postgameoutlet.com/pages/power-ratings
```

At desktop and mobile widths verify:

- the first selected tab is PGO Model;
- Experimental model — HOLD and the failed gate are visible;
- New England is PGO rank 1;
- McCabe Ratings and McCabe QBs work;
- sorting, keyboard tab navigation, table scrolling, and iframe sizing work;
- no console or network errors originate from the ratings artifact.

If GitHub Pages is correct but Shopify remains stale, confirm cache behavior before changing anything. This release does not authorize a Shopify edit.

- [ ] **Step 6: Record the release result**

Run:

```powershell
git log -3 --oneline
git status --short
```

Report the deployed commit, Pages URL, Shopify verification result, exact test totals, and that v1.1/v1.2 were excluded. Then return to the separate PGO v2 design workflow; do not implement v2 from this plan.
