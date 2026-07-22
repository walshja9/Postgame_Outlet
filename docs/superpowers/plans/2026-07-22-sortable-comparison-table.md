# Sortable Private Comparison Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add accessible client-side sorting to all ten columns of the existing private McCabe-versus-PGO comparison table without changing its URL, default order, or data.

**Architecture:** Extend `pgo_comparison.py` to emit raw sort values, native header buttons, a live status region, and one dependency-free script scoped to `#panel-comparison`. Reuse the base page's existing `.sort-button` styling; do not modify or abstract the public sorter in `generate_site.py`.

**Tech Stack:** Python 3 standard library, generated HTML, vanilla JavaScript, `unittest`, existing browser QA workflow

## Global Constraints

- Work only on `codex/pgo-team-model-workspace` and keep the result preview-only.
- Do not push, merge, publish, deploy, or change any live service.
- Do not touch `generate_site.py`, `docs/index.html`, model training, ratings, backtest, receipts, source snapshots, Shopify, GitHub Pages, workflows, redirects, or analytics.
- Do not add dependencies, filtering, search, pagination, export, saved sort preferences, or a public comparison page.
- Preserve the current McCabe-rank default order, all 32 rows, sticky Team column, and mobile table scrolling.
- Regenerate only `output/pgo-comparison-preview/2026-07-22/index.html`; `output/` remains ignored and uncommitted.
- Do not add or commit `.superpowers/`.

---

### Task 1: Add the comparison-scoped sorter

**Files:**
- Modify: `tests/test_pgo_comparison.py:86-123`
- Modify: `pgo_comparison.py:223-347`
- Regenerate, do not commit: `output/pgo-comparison-preview/2026-07-22/index.html`

**Interfaces:**
- Consumes: `render_comparison_panel(rows: list[dict], receipt: dict) -> str` and `inject_comparison(base_html: str, panel_html: str) -> str`
- Produces: ten `.sort-button` controls with zero-based `data-column` values, `data-sort` values on every row cell, `.comparison-sort-status`, and `COMPARISON_SCRIPT` inserted before `</body>`

- [ ] **Step 1: Write one failing generated-output test**

Add this method to `ComparisonTests` in `tests/test_pgo_comparison.py`:

```python
    def test_generated_comparison_is_sortable_and_accessible(self):
        panel = pgo_comparison.render_comparison_panel(
            [{
                "team": "Buffalo Bills", "mccabe_rank": 1,
                "mccabe_rating": 7.0, "full_strength_rank": 2,
                "full_strength_rating": 0.5, "availability_adjustment": 2.0,
                "current_lineup_rank": 1, "current_lineup_rating": 2.5,
                "rank_disagreement": 1, "rating_disagreement": -6.5,
            }],
            self._held_receipt(),
        )
        base = (
            "<html><head><style>base</style></head><body>"
            '<button type="button" class="tab" id="tab-method">Methodology</button>'
            '<section class="panel" id="panel-method">Method</section>'
            "</body></html>"
        )
        output = pgo_comparison.inject_comparison(base, panel)

        self.assertEqual(panel.count('class="sort-button"'), 10)
        self.assertEqual(panel.count('aria-sort="none"'), 10)
        self.assertEqual(panel.count("data-sort="), 10)
        self.assertIn('data-sort="buffalo bills"', panel)
        self.assertIn('data-sort="-6.5"', panel)
        self.assertIn('class="visually-hidden comparison-sort-status"', panel)
        self.assertIn("document.querySelector('#panel-comparison')", output)
        self.assertIn("const numeric = index !== 0;", output)
        self.assertIn(
            "a.children[0].dataset.sort.localeCompare(",
            output,
        )
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
python -m unittest tests.test_pgo_comparison.ComparisonTests.test_generated_comparison_is_sortable_and_accessible -v
```

Expected: `FAIL`, first reporting `AssertionError: 0 != 10` because the current comparison headers are plain text.

- [ ] **Step 3: Emit raw values and accessible sort controls**

In `render_comparison_panel()`, replace the row construction with:

```python
    body = "\n".join(
        "<tr>"
        f'<th scope="row" data-sort="{html.escape(row["team"].casefold())}">'
        f'{html.escape(row["team"])}</th>'
        f'<td data-sort="{row["mccabe_rank"]}">{row["mccabe_rank"]}</td>'
        f'<td data-sort="{row["mccabe_rating"]}">{_signed(row["mccabe_rating"])}</td>'
        f'<td data-sort="{row["full_strength_rank"]}">{row["full_strength_rank"]}</td>'
        f'<td data-sort="{row["full_strength_rating"]}">{_signed(row["full_strength_rating"])}</td>'
        f'<td data-sort="{row["availability_adjustment"]}">{_signed(row["availability_adjustment"])}</td>'
        f'<td data-sort="{row["current_lineup_rank"]}">{row["current_lineup_rank"]}</td>'
        f'<td data-sort="{row["current_lineup_rating"]}">{_signed(row["current_lineup_rating"])}</td>'
        f'<td data-sort="{row["rank_disagreement"]}">{row["rank_disagreement"]:+d}</td>'
        f'<td data-sort="{row["rating_disagreement"]}">{_signed(row["rating_disagreement"])}</td>'
        "</tr>"
        for row in rows
    )
```

Replace the comparison `<thead>` with the following and add the live status immediately before `.table-shell`:

```html
    <p class="visually-hidden comparison-sort-status" role="status" aria-live="polite"></p>
    <div class="table-shell">
      <table class="comparison-table">
        <caption class="visually-hidden">All 32 NFL teams comparing McCabe and PGO ratings</caption>
        <thead><tr>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="0">Team</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="1">McCabe #</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="2">McCabe</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="3">PGO full #</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="4">PGO full</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="5">Avail.</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="6">PGO today #</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="7">PGO today</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="8">Rank gap</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="9">Rating gap</button></th>
        </tr></thead>
```

- [ ] **Step 4: Add the minimal scoped vanilla-JavaScript sorter**

Add this constant after `COMPARISON_TAB`:

```python
COMPARISON_SCRIPT = """
<script>
  (() => {
    const panel = document.querySelector('#panel-comparison');
    const body = panel && panel.querySelector('.comparison-table tbody');
    const status = panel && panel.querySelector('.comparison-sort-status');
    const buttons = panel ? [...panel.querySelectorAll('.comparison-table .sort-button')] : [];
    if (!body || !status || buttons.length === 0) return;

    let activeColumn = null;
    let ascending = true;

    function value(row, index) {
      const raw = row.children[index].dataset.sort;
      const numeric = index !== 0;
      return numeric ? Number(raw) : raw;
    }

    buttons.forEach(button => {
      button.addEventListener('click', () => {
        const column = Number(button.dataset.column);
        ascending = column === activeColumn ? !ascending : true;
        activeColumn = column;
        [...body.rows].sort((a, b) => {
          const left = value(a, column);
          const right = value(b, column);
          const order = typeof left === 'number'
            ? left - right
            : left.localeCompare(right);
          const directed = ascending ? order : -order;
          return directed || a.children[0].dataset.sort.localeCompare(
            b.children[0].dataset.sort
          );
        }).forEach(row => body.appendChild(row));
        buttons.forEach(candidate => {
          candidate.closest('th').setAttribute('aria-sort', 'none');
        });
        button.closest('th').setAttribute(
          'aria-sort', ascending ? 'ascending' : 'descending'
        );
        status.textContent = button.textContent.trim() + ' sorted '
          + (ascending ? 'ascending' : 'descending');
      });
    });
  })();
</script>
"""
```

Extend `inject_comparison()` so `</body>` is a required one-time marker and the script is inserted immediately before it:

```python
    markers = (
        "</style>",
        '<button type="button" class="tab" id="tab-method"',
        '<section class="panel" id="panel-method"',
        "</body>",
    )
```

After the existing panel insertion, add:

```python
    output = output.replace("</body>", COMPARISON_SCRIPT + "\n</body>", 1)
```

- [ ] **Step 5: Run focused and full automated verification**

Run:

```powershell
python -m unittest tests.test_pgo_comparison -v
python -m unittest discover -s tests -v
python -m py_compile pgo_comparison.py
git diff --check
```

Expected: 9 comparison tests pass, all 114 repository tests pass, compilation exits `0`, and `git diff --check` produces no output.

- [ ] **Step 6: Regenerate the same private preview**

Run:

```powershell
python pgo_comparison.py --output output/pgo-comparison-preview/2026-07-22/index.html
```

Expected:

```text
Wrote ...\output\pgo-comparison-preview\2026-07-22\index.html
  32 teams | EXPERIMENTAL
```

- [ ] **Step 7: Verify behavior in a real browser at desktop and mobile widths**

Use the `playwright` skill to open:

```text
file:///C:/Users/Alex/Documents/Game%20Design/Postgame_Outlet-pgo-model/output/pgo-comparison-preview/2026-07-22/index.html
```

Activate `Model comparison`, then verify:

1. The initial McCabe rank sequence is `1` through `32`.
2. Activating `PGO full #` produces `1` through `32`, `aria-sort="ascending"`, and the live text `PGO full # sorted ascending`.
3. Activating it again produces `32` through `1`, `aria-sort="descending"`, and the matching descending live text.
4. Activating `Team` produces A-to-Z team names; activating it again produces Z-to-A names.
5. Pressing `Enter` while `Rating gap` is focused sorts it and updates `aria-sort`.
6. Every sort leaves exactly 32 unique team rows.
7. At a 390-pixel viewport the table scrolls internally, the document does not overflow horizontally, and the sticky Team column remains visible.
8. The browser console has no errors.

- [ ] **Step 8: Commit only source and test changes**

Run:

```powershell
git status --short
git add -- pgo_comparison.py tests/test_pgo_comparison.py
git commit -m "Add sortable PGO comparison columns"
git status --short --branch
```

Expected: only `pgo_comparison.py` and `tests/test_pgo_comparison.py` enter the implementation commit; `output/` and `.superpowers/` are absent; the final worktree is clean on `codex/pgo-team-model-workspace`.
