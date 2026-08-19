# PGO Lineup Fragility Challenger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three leakage-safe lineup-fragility features to the existing PGO challenger and evaluate them under the unchanged frozen validation contract.

**Architecture:** Extend the existing `lineup_views()` path with two concentration measures derived from prior snap shares and one quarterback depth-uncertainty measure derived from the existing pregame depth-chart weights. The existing matchup differencing, preprocessing, Huber-ridge selection, receipt generation, and release gates remain the only downstream consumers.

**Tech Stack:** Python 3, NumPy, `unittest`, existing `pgo_challenger.py` source/receipt pipeline, frozen local source cache.

## Global Constraints

- Keep the frozen source lock, cache, and `as_of` snapshot unchanged.
- Keep the 2,127-game outer evaluation population covering seasons 2018 through 2025.
- Keep PGO v0 as the incumbent benchmark and scoring-margin MAE as the primary metric.
- Keep chronological folds; no post-kickoff row may influence a feature, preprocessor, or parameter choice.
- Keep `half_life_games = (2, 4, 8, 16, 32)`, `alpha = (0.25, 1.0, 10.0, 100.0)`, and `delta = (0.75, 1.0, 1.5)`.
- Keep Huber-ridge loss, deterministic tie-breaking, paired season-week bootstrap, 10,000 samples, seed `20260721`, and the requirement that the 95% lower bound be strictly positive.
- Keep all existing integrity, current-team, paired-ID, deterministic, MAE, subgroup, and artifact gates.
- A `HOLD` or `BLOCKED` run must leave `research/pgo_v1` and `docs/index.html` byte-identical.
- Do not add sources, change the target or loss, alter PGO v0, expand the evaluation window, change bootstrap rules, add interactions, introduce recent-form state, blend with McCabe, or edit Pages, Shopify, or public wording.
- Only a reproducible `PASS` is eligible for a later promotion decision; this plan does not publish automatically.

---

## File Map

- **Modify:** `pgo_challenger.py`
  - Add the two availability-concentration and one QB-uncertainty helpers.
  - Populate their full-strength/current-lineup values in `lineup_views()`.
  - Let existing matchup differencing and feature-manifest generation consume the new keys.
- **Modify:** `tests/test_pgo_challenger.py`
  - Add red/green unit coverage in `LineupTests` and `FeatureTests`.
  - Extend the synthetic end-to-end receipt assertion for the feature manifest.
- **Read-only verification:** `research/pgo_v1/*`, `docs/index.html`, and the frozen cache under `.cache/pgo_v1`.

### Task 1: Lock the lineup-fragility behavior with failing tests

**Files:**
- Modify: `tests/test_pgo_challenger.py:2766-2960` (`LineupTests`)
- Modify: `tests/test_pgo_challenger.py:620-1100` (`FeatureTests`)
- Modify: `tests/test_pgo_challenger.py:2463-2540` (`OutputTests.test_small_synthetic_pipeline_runs_end_to_end`)

**Interfaces:**
- The tests define the production helper names and expected contracts:
  - `_unavailable_concentration(players, share_name) -> float | None`
  - `_expected_qb_uncertainty(depth_chart) -> float | None`
  - `lineup_views()` returns the keys `offense_availability_concentration`, `defense_availability_concentration`, and `qb_depth_uncertainty` in both full/current dictionaries.

- [ ] **Step 1: Add concentration and QB-uncertainty tests**

Add these methods to `LineupTests`:

```python
def test_availability_concentration_squares_prior_snap_share(self):
    concentrated = [
        {"offense_snap_share": 0.8, "probability": 0.0},
    ]
    diffuse = [
        {"offense_snap_share": 0.4, "probability": 0.0},
        {"offense_snap_share": 0.4, "probability": 0.0},
    ]

    concentrated_value = pgo_challenger._unavailable_concentration(
        concentrated, "offense_snap_share"
    )
    diffuse_value = pgo_challenger._unavailable_concentration(
        diffuse, "offense_snap_share"
    )

    self.assertAlmostEqual(concentrated_value, 0.64)
    self.assertAlmostEqual(diffuse_value, 0.32)
    self.assertGreater(concentrated_value, diffuse_value)

def test_qb_depth_uncertainty_uses_existing_probability_weights(self):
    depth_chart = [
        ("starter", {"qb_value": 1.0, "probability": 0.5}),
        ("backup", {"qb_value": 0.0, "probability": 1.0}),
    ]

    self.assertAlmostEqual(
        pgo_challenger._expected_qb_uncertainty(depth_chart), 0.25
    )

def test_qb_depth_uncertainty_stays_missing_when_probability_mass_is_unmodeled(self):
    depth_chart = [
        ("starter", {"qb_value": 1.0, "probability": 0.0}),
    ]

    self.assertIsNone(pgo_challenger._expected_qb_uncertainty(depth_chart))

def test_lineup_fragility_features_are_zero_when_everyone_is_available(self):
    full, current = pgo_challenger.lineup_views(
        "LV", self._snapshot(starter_probability=1.0), {}
    )

    for name in (
        "offense_availability_concentration",
        "defense_availability_concentration",
        "qb_depth_uncertainty",
    ):
        self.assertEqual(full[name], 0.0)
        self.assertEqual(current[name], 0.0)
```

The QB fixture must use the existing `qb_value` fallback accepted by
`_qb_feature()`, so the test remains independent of the full source loader.

- [ ] **Step 2: Add missing-value and pregame immutability tests**

Add a direct missing-value assertion:

```python
self.assertIsNone(
    pgo_challenger._unavailable_concentration(
        [{"probability": 0.0}], "offense_snap_share"
    )
)
```

Extend the existing `FeatureTests.test_snapshot_as_of_week_two_ignores_later_roster_and_injury` case. After capturing `historical`, append only week-3 rows to the 2013 weekly-roster, injury, and snap-count files, then rebuild the same `2013-09-08T14:00:00-04:00` snapshot and assert:

```python
with_current_source = pgo_challenger.build_snapshot_states(
    paths, "2013-09-08T14:00:00-04:00", 4
)
self.assertEqual(historical, with_current_source)
```

The added rows must have no corresponding pre-week-3 game and must not alter
the schedule, target margin, or any pregame row. This proves later roster,
injury, and snap data cannot change the earlier feature state.

- [ ] **Step 3: Extend the synthetic receipt manifest assertion**

In `OutputTests.test_small_synthetic_pipeline_runs_end_to_end`, after loading
`backtest.json`, assert that the feature manifest contains all three names:

```python
features = set(backtest["feature_manifest"]["features"])
self.assertTrue({
    "offense_availability_concentration",
    "defense_availability_concentration",
    "qb_depth_uncertainty",
}.issubset(features))
```

- [ ] **Step 4: Run the focused tests and confirm the intentional RED state**

Run:

```powershell
python -m unittest tests.test_pgo_challenger.LineupTests tests.test_pgo_challenger.FeatureTests -v
```

Expected: FAIL because the three helper names and lineup keys do not yet
exist. No production code is changed in this task.

- [ ] **Step 5: Commit the tests**

```powershell
git add tests/test_pgo_challenger.py
git commit -m "test: specify PGO lineup fragility features"
```

### Task 2: Implement the minimum leakage-safe lineup features

**Files:**
- Modify: `pgo_challenger.py:211-244` (`lineup_views`)
- Modify: `pgo_challenger.py:2036-2075` (QB/availability helpers)

**Interfaces:**
- Consumes the existing `depth_chart` list produced by `lineup_views()` and
  the existing per-player `probability`, `offense_snap_share`, and
  `defense_snap_share` values.
- Produces three numeric-or-missing feature keys in both full/current lineup
  dictionaries; downstream `_difference()`, preprocessing, and receipt code
  require no new interface.

- [ ] **Step 1: Add the minimal concentration helper**

Implement `_unavailable_concentration(players, name)` beside
`_unavailable_share()`:

```python
def _unavailable_concentration(players, name):
    total = 0.0
    for player in players:
        missing = 1.0 - _probability(player)
        if not missing:
            continue
        share = player.get(name)
        if share is None:
            return None
        total += float(share) ** 2 * missing
    return total
```

This reuses the existing probability validation and fails closed on missing
required share data.

- [ ] **Step 2: Add the QB uncertainty helper**

Implement `_expected_qb_uncertainty(depth_chart)` beside
`_expected_qb_feature()` using the same sequential weights:

```python
def _expected_qb_uncertainty(depth_chart):
    weighted = []
    remaining = 1.0
    for _, player in depth_chart:
        weight = remaining * _probability(player)
        value = _qb_feature(player, "qb_epa_per_dropback")
        if weight and value is None:
            return None
        if weight:
            weighted.append((weight, float(value)))
        remaining -= weight
    if remaining > 1e-12 or not weighted:
        return None
    total = sum(weight for weight, _ in weighted)
    mean = sum(weight * value for weight, value in weighted) / total
    return sum(weight * (value - mean) ** 2 for weight, value in weighted) / total
```

The helper must not inspect game results or future rows. It must return
`None` when a nonzero probability mass has no usable QB value or when the
depth chart leaves residual probability unmodeled.

- [ ] **Step 3: Populate full/current lineup dictionaries**

In `lineup_views()`, initialize the three full-strength keys to `0.0` beside
the existing `qb_current_minus_full`, `offense_availability`, and
`defense_availability` keys. After computing the current QB and availability
values, assign:

```python
offense = _unavailable_concentration(players.values(), "offense_snap_share")
defense = _unavailable_concentration(players.values(), "defense_snap_share")
current["offense_availability_concentration"] = -offense if offense is not None else None
current["defense_availability_concentration"] = -defense if defense is not None else None
current["qb_depth_uncertainty"] = _expected_qb_uncertainty(depth_chart)
```

Do not add these names to `ROSTER_COACHING_FEATURES`; they are availability
features and must remain zero in full-strength ratings.

- [ ] **Step 4: Run the focused tests green**

Run:

```powershell
python -m unittest tests.test_pgo_challenger.LineupTests tests.test_pgo_challenger.FeatureTests -v
```

Expected: all focused tests pass, including the existing lineup, timing, and
snapshot tests.

- [ ] **Step 5: Commit the implementation**

```powershell
git add pgo_challenger.py tests/test_pgo_challenger.py
git commit -m "feat: add PGO lineup fragility features"
```

### Task 3: Run the complete verification and frozen research challenger

**Files:**
- Read-only: `research/pgo_v1/source_audit.json`, `research/pgo_v1/backtest.json`, `research/pgo_v1/validation_predictions.csv`, `research/pgo_v1/ratings_2026_preseason.csv`, `docs/index.html`
- No tracked file may be modified by this task.

**Interfaces:**
- Consumes the committed implementation and the frozen lock/cache.
- Produces a temporary receipt and a reviewable PASS/HOLD/BLOCKED result; it
  does not promote or publish that result.

- [ ] **Step 1: Run the full test and static checks**

Run:

```powershell
python -m unittest discover -s tests
python -m py_compile pgo_challenger.py tests/test_pgo_challenger.py
git diff --check
```

Expected: the full suite passes, compilation exits 0, and `git diff --check`
reports no whitespace errors. Existing `generate_site.py` ResourceWarnings
remain non-blocking if they recur.

- [ ] **Step 2: Capture hashes of tracked research/public artifacts**

Run before the challenger:

```powershell
$before = @{}
foreach ($name in 'source_audit.json','backtest.json','validation_predictions.csv','ratings_2026_preseason.csv') {
  $before[$name] = (Get-FileHash -Algorithm SHA256 (Join-Path 'research/pgo_v1' $name)).Hash
}
$pageBefore = (Get-FileHash -Algorithm SHA256 'docs/index.html').Hash
```

- [ ] **Step 3: Run into a unique temporary output directory**

Run exactly:

```powershell
$tempOutput = Join-Path ([IO.Path]::GetTempPath()) ('pgo-v1-lineup-fragility-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tempOutput | Out-Null
python pgo_challenger.py --as-of 2026-07-21T12:00:00-04:00 --lock-path research/pgo_v1/sources.lock.json --cache-dir .cache/pgo_v1 --output-dir $tempOutput
$exitCode = $LASTEXITCODE
```

An exit code of `0` is a PASS; exit code `1` is an expected HOLD result; a
blocked or unexpected error must be reported separately. Do not rerun with
altered gates, seeds, source locks, or evaluation data.

- [ ] **Step 4: Inspect the receipt and verify artifact safety**

Read `$tempOutput\backtest.json` and record status, selected parameters,
challenger/P​​GO v0 MAEs, aggregate interval, all failed checks, and the three
feature names in `feature_manifest.features`. Then compare hashes:

```powershell
foreach ($name in $before.Keys) {
  $after = (Get-FileHash -Algorithm SHA256 (Join-Path 'research/pgo_v1' $name)).Hash
  if ($after -ne $before[$name]) { throw "Tracked artifact changed: $name" }
}
if ((Get-FileHash -Algorithm SHA256 'docs/index.html').Hash -ne $pageBefore) {
  throw 'Public page changed during temporary validation'
}
git diff -- docs/index.html research/pgo_v1
```

Expected: no tracked/public diff. A HOLD or BLOCKED result remains temporary
evidence only. If the receipt is PASS, stop and report it for an explicit
promotion decision; do not publish automatically.

- [ ] **Step 5: Commit only documentation/evidence if explicitly requested**

Do not commit temporary outputs or alter tracked research artifacts in this
task. The implementation commits from Task 1 and Task 2 plus the test/static
verification output are the complete code change.
