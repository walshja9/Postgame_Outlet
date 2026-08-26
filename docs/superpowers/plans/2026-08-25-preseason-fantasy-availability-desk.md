# Preseason Fantasy Availability Desk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task by task. Keep the existing dirty-worktree baseline
> intact and stage only the paths named by each task.

**Goal:** Deliver one local, source-backed preseason availability slice from an
all-32-team official-source ledger through a protected PGO current-lineup shadow
run and into an unpublished Fantasy theme package.

**Architecture:** Reuse the existing availability CSV, challenger, and Shopify
theme. Add semantic source records to the local importer, reconcile its receipt
against the overlay in the shared loader, and keep editorial-only preseason
evidence out of model probabilities. All source and shadow artifacts remain
under ignored `output/`; only importer/loader tests, their minimal production
changes, and the generator file-handle repair become repository changes.

**Tech stack:** Python 3 standard library, NumPy through the existing PGO model,
`unittest`, JSON/CSV, PowerShell archive/hash tools, existing Shopify Liquid and
JSON templates.

## Global constraints

- Preserve `Experimental model — HOLD`, the existing MAE/gate definitions,
  July 16 comparison history, July 21 prospective lock, checked-in availability
  overlay, research receipts, `docs/index.html`, and both publication workflows.
- Do not tune or promote the model, infer healthy status from missing reports,
  coerce preseason rest/news into injury probability, scrape during model
  execution, add a dependency, upload a theme, push, deploy, or modify Shopify.
- Use exactly one official coverage record for each canonical team abbreviation.
- Stop on ambiguous player identity, unknown source semantics, count/key
  disagreement, timestamp conflict, roster mismatch, or protected-artifact drift.
- Preserve unrelated untracked files. Never use `git add -A`.

---

### Task 1: Reconcile coverage receipts in the authoritative overlay loader

**Files:**

- Modify: `tests/test_pgo_challenger.py`
- Modify: `pgo_challenger.py:301-386`

**Contract:** A passing receipt must describe the exact canonical team list,
per-team overlay counts, total row count, and exact `(team, gsis_id)` keys found
in its accompanying CSV.

- [ ] **Step 1: Write the failing regression.**

Extend `test_availability_coverage_audit_requires_all_32_teams` or add one
adjacent test using its temporary one-player overlay. Give the initially valid
receipt these required fields:

```python
"team_row_counts": {
    team: int(team == "LAR") for team in pgo_model.CURRENT_TEAMS
},
"player_row_count": 1,
"overlay_player_keys": [{"team": "LAR", "gsis_id": "00-0039075"}],
```

Then mutate one field at a time and require `ValueError` for:

- duplicate or noncanonical `teams_processed`;
- missing/extra team count keys;
- a boolean, negative, or non-integer count;
- a total count other than the sum of team counts;
- a per-team count different from the CSV;
- a player key different from the CSV.

Run:

```powershell
python -m unittest tests.test_pgo_challenger.AvailabilityOverlayTests.test_availability_coverage_audit_reconciles_overlay -v
```

Expected: failure because the current loader ignores receipt counts and keys.

- [ ] **Step 2: Implement the smallest shared-loader fix.**

Pass the parsed `overlay` mapping into `_availability_coverage`. Validate the
raw team list before converting it to a set, require canonical count keys and
non-boolean nonnegative integers, compare declared totals and exact sorted keys
to the overlay, and return the validated counts/keys in the receipt. Do not add
a second validator or provider-specific logic.

For a header-only overlay, use the coverage receipt timestamp and allow all
counts/keys to be empty; still require the receipt timestamp to be no later than
the model as-of.

- [ ] **Step 3: Run focused tests.**

```powershell
python -m unittest tests.test_pgo_challenger.AvailabilityOverlayTests.test_availability_coverage_audit_requires_all_32_teams -v
python -m unittest tests.test_pgo_challenger.AvailabilityOverlayTests.test_availability_coverage_audit_reconciles_overlay -v
```

Expected: both pass.

- [ ] **Step 4: Commit only the loader and its test.**

```powershell
git add -- pgo_challenger.py tests/test_pgo_challenger.py
git diff --cached --check
git commit -m "fix: reconcile availability coverage receipts"
```

---

### Task 2: Make the existing local importer preserve preseason source meaning

**Files:**

- Modify: `tests/test_pgo_injury_source.py`
- Modify: `pgo_injury_source.py`

**Input contract:** Replace the preliminary `teams_processed`-only snapshot with
exactly 32 `team_sources` records:

```json
{
  "source": "Official NFL club preseason availability sources",
  "source_as_of": "2026-08-25T12:00:00-04:00",
  "team_sources": [{
    "team": "LAR",
    "source_url": "https://www.therams.com/...",
    "source_kind": "formal_injury_report",
    "source_published_at": "2026-08-24T18:00:00-07:00",
    "target_game": "2026 PRE3",
    "coverage_note": "Official club report checked"
  }],
  "players": [{
    "team": "LAR",
    "gsis_id": "00-0039075",
    "player": "Puka Nacua",
    "position": "WR",
    "source_url": "https://www.therams.com/...",
    "injury": "knee",
    "practice_status": "Limited Participation",
    "game_status": "Questionable",
    "availability_text": ""
  }]
}
```

Allowed source kinds are `formal_injury_report`,
`preseason_availability_list`, `reserve_list`, `official_news`, and
`no_formal_report`.

- [ ] **Step 1: Write source-semantics and receipt regressions.**

Build a 32-team fixture with one formal LAR row and one
`preseason_availability_list` GB row. Assert:

- only LAR enters the overlay and still uses
  `availability_probability(game_status, practice_status)`;
- GB appears in an `exclusions` receipt entry with a deterministic reason;
- `source_player_count == 2`, `player_row_count == 1`, and excluded counts sum
  to one;
- all 32 source records, per-team counts, and exact overlay keys are preserved;
- a duplicate team source, mismatched player source URL, player attached to
  `no_formal_report`, unknown source kind, or later-than-capture publication
  timestamp fails closed.

Run:

```powershell
python -m unittest tests.test_pgo_injury_source -v
```

Expected: failures against the preliminary importer contract.

- [ ] **Step 2: Implement the semantic ledger parser.**

In `load_snapshot`, validate the capture timestamp, exact canonical team-source
coverage, HTTPS source URLs, source-kind enum, optional timezone-bearing
publication timestamps not later than capture, required coverage notes, stable
player identities, and each player's exact source URL match. Keep source text
factual and normalized only for surrounding whitespace.

- [ ] **Step 3: Filter model eligibility in one pass.**

Only `formal_injury_report` rows enter `build_overlay`; reuse the existing
fail-closed status mapper. Treat preseason availability lists, reserve lists,
official news, and no-formal-report coverage as editorial-only in this first
slice. Record every excluded player and reason. Do not add a manual
`eligible_for_model` override.

- [ ] **Step 4: Emit a reconciled coverage receipt.**

Write source records, per-team source/overlay/excluded counts, exclusion rows,
source and overlay totals, exact overlay keys, source timestamp, and raw source
SHA-256. Preserve deterministic sorting and the existing availability CSV
header. Continue writing only caller-supplied paths.

- [ ] **Step 5: Run focused integration tests.**

```powershell
python -m unittest tests.test_pgo_injury_source -v
python -m unittest tests.test_pgo_challenger -v
```

Expected: all pass; no checked-in data or public artifact changes.

- [ ] **Step 6: Commit exactly the importer paths.**

```powershell
git add -- pgo_injury_source.py tests/test_pgo_injury_source.py
git diff --cached --check
git commit -m "feat: import semantic preseason availability sources"
```

---

### Task 3: Close the three site-generator file handles

**Files:**

- Modify: `tests/test_ratings_release.py`
- Modify: `generate_site.py:97-104,250-270`

- [ ] **Step 1: Add one failing warning regression.**

Create minimal temporary `prior_2025.csv`, `ratings.csv`, and `qb_depth.csv`
files. Patch `generate_site.DATA`, call `load_prior()` and `load_qbs()`, force
garbage collection inside `warnings.catch_warnings(record=True)`, and assert no
captured warning is a `ResourceWarning` containing `unclosed file`.

Run:

```powershell
python -m unittest tests.test_ratings_release.ReleaseGateTests.test_site_csv_loaders_close_files -v
```

Expected: failure with three unclosed-file warnings.

- [ ] **Step 2: Apply the root fix.**

Replace the three `csv.DictReader(open(...))` expressions in `load_prior` and
`load_qbs` with ordinary `with open(..., encoding="utf-8", newline="")`
blocks. Do not introduce a helper or refactor unrelated loader code.

- [ ] **Step 3: Verify and commit.**

```powershell
python -m unittest tests.test_ratings_release.ReleaseGateTests.test_site_csv_loaders_close_files -v
python -m unittest tests.test_ratings_release -v
git add -- generate_site.py tests/test_ratings_release.py
git diff --cached --check
git commit -m "fix: close site generator CSV files"
```

---

### Task 4: Freeze and validate the all-32-team official preseason ledger

**Files:**

- Create locally: `output/preseason-fantasy-slice/nfl-preseason-availability.json`
- Generate locally: `output/preseason-fantasy-slice/nfl-availability.csv`
- Generate locally: `output/preseason-fantasy-slice/nfl-availability-coverage.json`

- [ ] **Step 1: Capture a bounded official-source record for every team.**

Use one current official NFL or club page per team. Record the exact URL,
source kind, visible publication/update time when supplied, target preseason
game, and a factual coverage note. `no_formal_report` records the checked page
and its explicit state; it does not assert a healthy roster.

- [ ] **Step 2: Record only identifiable player evidence.**

Copy short status facts, not article prose. Resolve each included player to a
single GSIS ID using the locked/current roster sources already used by PGO.
Stop on ambiguous or unmatched identity. Preserve editorial-only players in the
ledger even though they will be excluded from the model overlay.

- [ ] **Step 3: Import to temporary outputs.**

```powershell
python pgo_injury_source.py `
  --input output/preseason-fantasy-slice/nfl-preseason-availability.json `
  --overlay output/preseason-fantasy-slice/nfl-availability.csv `
  --coverage output/preseason-fantasy-slice/nfl-availability-coverage.json
```

Expected: exact 32-team coverage, reconciled totals/keys, and no mutation under
`data/`, `research/`, `docs/`, or `prospective_evidence/`.

- [ ] **Step 4: Re-load the generated pair through the authoritative loader.**

Use the frozen capture timestamp as model as-of and require
`receipt["coverage"]["passed"] is True`. Independently inspect the exclusion
reasons and source URLs before accepting the snapshot.

Do not commit these artifacts in this slice.

---

### Task 5: Run the protected current-lineup shadow analysis

**Files:**

- Generate locally: `output/preseason-fantasy-slice/pgo-shadow/**`
- Create locally: `output/preseason-fantasy-slice/protected-hashes-before.json`
- Create locally: `output/preseason-fantasy-slice/protected-hashes-after.json`

- [ ] **Step 1: Hash protected artifacts before execution.**

Include `data/mccabe_availability.csv`, `data/snapshots.json`,
`research/pgo_v1/backtest.json`, `research/pgo_v1/ratings_2026_preseason.csv`,
`research/pgo_v1/validation_predictions.csv`, `docs/index.html`, and every file
under `prospective_evidence/2026-07-21`.

- [ ] **Step 2: Run the shadow.**

```powershell
python pgo_challenger.py `
  --as-of "<frozen source_as_of>" `
  --lock-path research/pgo_v1/sources.lock.json `
  --cache-dir .cache/pgo_v1 `
  --output-dir output/preseason-fantasy-slice/pgo-shadow `
  --availability-overlay output/preseason-fantasy-slice/nfl-availability.csv `
  --availability-audit output/preseason-fantasy-slice/nfl-availability-coverage.json `
  --headline-view current_lineup `
  --role-scenario base
```

A statistical HOLD exit/result is acceptable. A source, identity, coverage,
finite-value, or artifact-integrity failure is not.

- [ ] **Step 3: Compare model views and artifacts.**

Require numerically identical unrounded full-strength ratings, current-lineup
changes only for matched eligible players, explicit/learned/generic role-source
precedence, finite outputs, exact before/after protected hashes, and unchanged
HOLD/EXPERIMENTAL status. Record actual changed teams and adjustments for the
Fantasy copy; do not promote the output.

---

### Task 6: Build one local content-first Fantasy theme package

**Files:**

- Read: `D:\Game Design\Postgame_Outlet-preview-packages\postgame-content-first-theme-bebee2a.zip`
- Modify locally after extraction:
  `output/preseason-fantasy-slice/theme/templates/page.fantasy.json`
- Create locally:
  `output/preseason-fantasy-slice/postgame-preseason-fantasy-preview.zip`
- Create locally: `output/preseason-fantasy-slice/theme-review.json`

- [ ] **Step 1: Verify and extract the known package.**

Require SHA-256
`ba0a6ce637c516d63f494eb1f6e6510fca4ef4ecaaebe85670391ad1bda1a56e`.
If a fresh authenticated duplicate-theme capture is unavailable, record that
the month-old `bebee2a` package is the commerce baseline and keep the result
local.

- [ ] **Step 2: Reuse native sections only.**

Update `templates/page.fantasy.json` with existing `rich-text`,
`postgame-tagged-articles`, and `featured-collection` sections. Put in order:

1. source timestamp, coverage explanation, and HOLD disclaimer;
2. verified Dynasty implications;
3. named-slate DFS implications;
4. existing tagged Dynasty/DFS article feeds;
5. methodology/accountability links;
6. existing `From the Outlet` merchandise treatment.

Use `PGO Editorial Staff`. Do not add Liquid, JavaScript, CSS, an empty tool,
or model-derived player projections.

- [ ] **Step 3: Validate the package structurally.**

Parse every JSON file, require the expected section order/copy/byline/source
timestamp, ensure there is no wrapper directory, and compare every file except
`templates/page.fantasy.json` byte-for-byte with the source ZIP. Record source
and output hashes plus changed-file inventory in `theme-review.json`.

- [ ] **Step 4: Keep visual/live gates honest.**

Run mobile/desktop, keyboard, heading, link, contrast, iframe, cart, and checkout
checks only if an authenticated browser/theme preview is available. Otherwise
mark them unrun; do not upload or publish.

---

### Task 7: Full verification and local handoff

**Files:**

- Verify all changed repository files and local evidence artifacts.

- [ ] **Step 1: Run focused suites.**

```powershell
python -m unittest tests.test_pgo_injury_source -v
python -m unittest tests.test_pgo_challenger -v
python -m unittest tests.test_ratings_release -v
python -m unittest tests.test_pgo_comparison -v
python -m unittest tests.test_pgo_prospective -v
python -m unittest tests.test_public_board_workflow -v
```

- [ ] **Step 2: Run the full repository suite and warning check.**

```powershell
python -W error::ResourceWarning -m unittest discover -s tests
git diff --check
```

Expected: all tests pass with no ResourceWarning and no whitespace errors.

- [ ] **Step 3: Audit scope.**

Confirm only the approved code/test/docs paths are tracked changes; protected
hashes match; all evidence/theme outputs remain ignored/local; unrelated
untracked paths remain untouched; and no push, deployment, Shopify upload, or
live mutation occurred.

- [ ] **Step 4: Report certification layers separately.**

Report code/tests, source/data integrity, model shadow, local theme structure,
and unrun visual/Shopify/live gates as separate outcomes. Ask separately before
any source-evidence commit, checked-in overlay update, theme upload, push,
deployment, or publication.
