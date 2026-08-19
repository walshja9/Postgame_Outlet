# PGO v1 Validation Grid Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Expand only the existing chronological hyperparameter candidates, rerun the frozen PGO v1 evaluation, and promote artifacts only if the unchanged statistical gate returns `PASS`.

**Architecture:** Keep `pgo_challenger.py`'s leakage-safe rolling evaluation, Huber-ridge model, receipt schema, and release gates unchanged. Replace the three candidate-grid constants with the pre-approved fixed tuples from the design, add one focused regression test for the grid contract, and run the challenger into a temporary output directory before any tracked artifact is touched.

**Tech Stack:** Python 3.12, NumPy, `unittest`, JSON/CSV receipts, existing `pgo_sources.py` lock and `pgo_challenger.py` CLI.

## Global Constraints

- Preserve `research/pgo_v1/sources.lock.json`, its frozen `as_of`, and the 2,127-game outer evaluation (`2018` through `2025`).
- Preserve PGO v0 as the incumbent, scoring-margin MAE, paired week-block bootstrap, 10,000 samples, seed `20260721`, and every existing integrity/statistical/subgroup gate.
- Use exactly these candidates: `HALF_LIFE_GRID = (2, 4, 8, 16, 32)`, `ALPHA_GRID = (0.25, 1.0, 10.0, 100.0)`, and `DELTA_GRID = (0.75, 1.0, 1.5)`.
- Do not add sources, features, interactions, model families, targets, losses, thresholds, or McCabe inputs.
- Do not write to tracked `research/pgo_v1/*` or `docs/index.html` during the exploratory run; use `--output-dir` under a temporary directory.
- A `HOLD` or `BLOCKED` result stops the work with tracked artifacts unchanged. Only an independently inspected `PASS` may be promoted.

---

### Task 1: Add the red grid-contract test

**Files:**
- Modify: `tests/test_pgo_challenger.py` near the existing parameter-selection tests around lines 1300-1337.

**Interfaces:**
- Consumes: `pgo_challenger.HALF_LIFE_GRID`, `ALPHA_GRID`, and `DELTA_GRID`.
- Produces: A regression assertion that locks the approved candidate set before implementation.

- [ ] **Step 1: Write the failing test**

Add one `unittest` method:

```python
def test_parameter_grid_matches_validation_design(self):
    self.assertEqual(pgo_challenger.HALF_LIFE_GRID, (2, 4, 8, 16, 32))
    self.assertEqual(
        pgo_challenger.ALPHA_GRID, (0.25, 1.0, 10.0, 100.0)
    )
    self.assertEqual(
        pgo_challenger.DELTA_GRID, (0.75, 1.0, 1.5)
    )
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```text
python -m unittest tests.test_pgo_challenger.ModelTests.test_parameter_grid_matches_validation_design -v
```

Expected: `FAIL` because the three constants still contain the original smaller tuples. If the test passes before the implementation edit, stop and report that the branch is not based on the expected baseline.

- [ ] **Step 3: Commit the red test**

```text
git add tests/test_pgo_challenger.py
git commit -m "test: lock the approved PGO validation grid"
```

---

### Task 2: Expand the candidate grid only

**Files:**
- Modify: `pgo_challenger.py:55-57`.
- Test: `tests/test_pgo_challenger.py` from Task 1.

**Interfaces:**
- Consumes: Existing `select_parameters()` loops and deterministic `ChallengerParameters` ordering.
- Produces: The approved candidate tuples used inside each chronological fold.

- [ ] **Step 1: Replace the constants with the approved tuples**

```python
HALF_LIFE_GRID = (2, 4, 8, 16, 32)
ALPHA_GRID = (0.25, 1.0, 10.0, 100.0)
DELTA_GRID = (0.75, 1.0, 1.5)
```

Do not alter `select_parameters()`, `_aggregate_gate_checks()`, `paired_block_bootstrap()`, `OUTER_SEASONS`, or receipt serialization.

- [ ] **Step 2: Run the focused challenger tests**

Run:

```text
python -m unittest tests.test_pgo_challenger -v
```

Expected: all challenger tests pass, including the new grid-contract test and the existing future-row/determinism tests.

- [ ] **Step 3: Run syntax and whitespace checks**

```text
python -m py_compile pgo_challenger.py tests/test_pgo_challenger.py
git diff --check
```

Expected: both commands exit successfully with no whitespace errors.

- [ ] **Step 4: Commit the implementation**

```text
git add pgo_challenger.py tests/test_pgo_challenger.py
git commit -m "research: expand PGO validation candidates"
```

---

### Task 3: Run the frozen challenger into a temporary output

**Files:**
- Read: `research/pgo_v1/sources.lock.json`, `research/pgo_v1/backtest.json`, `research/pgo_v1/ratings_2026_preseason.csv`.
- Write: Temporary directory outside the repository only.

**Interfaces:**
- Consumes: The existing locked source manifest and offline cache.
- Produces: Temporary `source_audit.json`, `backtest.json`, `validation_predictions.csv`, and `ratings_2026_preseason.csv`.

- [ ] **Step 1: Record the pre-run tracked hashes**

```powershell
$before = @{}
foreach ($name in 'source_audit.json','backtest.json','validation_predictions.csv','ratings_2026_preseason.csv') {
  $path = Join-Path 'research/pgo_v1' $name
  $before[$name] = (Get-FileHash -Algorithm SHA256 $path).Hash
}
```

- [ ] **Step 2: Run the locked analysis offline into a temporary directory**

```powershell
$tempOutput = Join-Path ([IO.Path]::GetTempPath()) ('pgo-v1-grid-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tempOutput | Out-Null
python pgo_challenger.py --as-of 2026-07-21T12:00:00-04:00 --lock-path research/pgo_v1/sources.lock.json --cache-dir .cache/pgo_v1 --output-dir $tempOutput
$exitCode = $LASTEXITCODE
```

Expected: the command completes offline and returns `0` for `PASS`, `1` for `HOLD`, or `2` for `BLOCKED`. Any other exit code is a failure requiring investigation.

- [ ] **Step 3: Inspect the temporary receipt before promotion**

```powershell
$receipt = Get-Content (Join-Path $tempOutput 'backtest.json') -Raw | ConvertFrom-Json
$receipt.status
$receipt.failed_checks
$receipt.metrics.challenger.mae
$receipt.metrics.pgo_v0.mae
$receipt.aggregate_interval
$receipt.parameters
```

Expected for promotion: `status` is `PASS`, `failed_checks` is empty, every value in `checks` is `true`, and `aggregate_interval.lower` is greater than `0`. A `HOLD` or `BLOCKED` result is a valid research outcome but is not a validated release.

- [ ] **Step 4: Confirm the exploratory run did not touch tracked artifacts**

```powershell
foreach ($name in $before.Keys) {
  $path = Join-Path 'research/pgo_v1' $name
  if ((Get-FileHash -Algorithm SHA256 $path).Hash -ne $before[$name]) { throw "Tracked artifact changed: $name" }
}
git diff -- docs/index.html research/pgo_v1
```

Expected: no tracked-artifact diff. If the result is not `PASS`, stop here and report the measured receipt; do not continue to promotion.

---

### Task 4: Promote only a reproducible PASS

**Files:**
- Modify only if Task 3 returns `PASS`: `research/pgo_v1/source_audit.json`, `research/pgo_v1/backtest.json`, `research/pgo_v1/validation_predictions.csv`, `research/pgo_v1/ratings_2026_preseason.csv`.
- Do not modify: `data/`, `docs/index.html`, Shopify files, workflow files, or source locks in this task.

**Interfaces:**
- Consumes: The inspected temporary PASS artifacts from Task 3.
- Produces: A committed PASS receipt and ratings artifact, or no changes when validation remains HOLD/BLOCKED.

- [ ] **Step 1: Promote the four temporary artifacts only after PASS**

```powershell
Copy-Item (Join-Path $tempOutput 'source_audit.json') research/pgo_v1/source_audit.json -Force
Copy-Item (Join-Path $tempOutput 'backtest.json') research/pgo_v1/backtest.json -Force
Copy-Item (Join-Path $tempOutput 'validation_predictions.csv') research/pgo_v1/validation_predictions.csv -Force
Copy-Item (Join-Path $tempOutput 'ratings_2026_preseason.csv') research/pgo_v1/ratings_2026_preseason.csv -Force
```

- [ ] **Step 2: Re-run the complete release gates**

```text
python -m unittest discover -s tests
python -m py_compile pgo_challenger.py tests/test_pgo_challenger.py
git diff --check
```

Expected: all tests pass and the only staged changes are the four research artifacts plus the already-committed grid/test changes.

- [ ] **Step 3: Inspect and commit the PASS artifacts**

```text
git add research/pgo_v1/source_audit.json research/pgo_v1/backtest.json research/pgo_v1/validation_predictions.csv research/pgo_v1/ratings_2026_preseason.csv
git diff --cached --check
git commit -m "research: record validated PGO v1 challenger"
```

Before any public-page update, verify the committed receipt still reports `PASS` and the artifact hashes are identical to the temporary PASS output. If `pgo_comparison.py --publish` rejects the current McCabe snapshot, stop and open a separate snapshot/release-lineage task; do not weaken that guard in this plan.

---

## Completion Criteria

- The candidate grid matches the approved design and is covered by tests.
- The frozen challenger is reproducible with the unchanged source lock, metric, bootstrap, seed, and gates.
- A `PASS` receipt has a positive bootstrap lower bound and no failed checks before any research artifact is promoted.
- If the expanded grid remains `HOLD` or becomes `BLOCKED`, tracked research artifacts and the public PGO page remain unchanged, and the measured failure is reported instead of relabeled.
