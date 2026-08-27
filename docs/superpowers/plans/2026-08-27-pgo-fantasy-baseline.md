# PGO Fantasy Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify the first independent nflverse-only fantasy rung: exact half-PPR scoring, an audited weekly `ACT` population, leakage-safe chronological null and strong baselines, and a deterministic fold report.

**Architecture:** Add one pure-Python module, `pgo_fantasy.py`, and one focused `unittest` module. The code consumes already-locked schedule, weekly-roster, and player-weekly-stat paths, returns plain dictionaries and rows, and performs no network fetch, canonical source capture, model fitting, prospective lock, public-site change, or deployment.

**Tech Stack:** Python standard library, existing `pgo_sources.SourceSpec`, `pgo_sources.open_csv`, and `pgo_sources.normalize_team`; repository `unittest` conventions; no new dependency.

## Global Constraints

- Work from an isolated Git worktree created from the approved documentation commit.
- Preserve every unrelated untracked file in `D:\Claude Context\Postgame_Outlet`; never use `git add -A`.
- Do not modify `pgo_sources.source_specs()` or any team-model source, receipt, July prospective, stability-blend, public-board, workflow, Shopify, or deployment artifact.
- Historical fantasy scope is NFL regular season 2020-2025; outer test seasons are exactly 2022, 2023, 2024, and 2025.
- Population is weekly-roster `status == ACT` for QB/RB/FB/WR/TE; map FB to RB. `ACT` means active roster, not game-day active.
- Missing stats become exactly zero only after identity, team-week, and schedule validation. Any unreconciled eligible stat row outside the `ACT` roster population blocks the run.
- Scoring is exactly 0.04/pass yard, 4/pass TD, -2/interception, 0.1/rush or receiving yard, 6/rush or receiving TD, 0.5/reception, -2/fumble lost, 2/two-point conversion, and 6/special-teams TD.
- All rows in a season-week are predicted before any outcome from that week updates state.
- The null baseline is the fixed training-season position mean.
- The strong baseline uses the player's eight most recent eligible outcomes, newest first, weight `2 ** (-i / 4)`, and four pseudo-games at the time-safe position mean; cold start is that position mean.
- Primary selection is deterministic: top 24 QB, 24 RB, 24 WR, 12 TE, then 12 remaining RB/WR/TE by strong-baseline prediction with GSIS ID ascending as the tie-break.
- Fantasy status remains `HOLD` and publication status `EXPERIMENTAL`; this slice cannot promote a model because it contains no candidate.
- Do not read PFF, injury, practice, game-status, inactive, depth-chart, current-game participation, betting, or paid-source fields.
- Use synthetic fixtures only. Do not freeze current remote bytes or run a canonical 2020-2025 backtest in this plan.

---

## File Structure

- Create `pgo_fantasy.py`: fantasy-only source inventory, scoring, source/population audit, chronological baseline evaluation, primary-pool selection, and deterministic in-memory serialization.
- Create `tests/test_pgo_fantasy.py`: synthetic contract, identity, chronology, selection, fold, and serialization regressions.
- Modify `docs/superpowers/specs/2026-08-27-pgo-team-and-fantasy-model-design.md`: already adds the approved strictly-prior-week state rule.

No CLI or output writer is included. The approved slice forbids a canonical run, so returning deterministic serialized bytes is sufficient; add file publication only with the later canonical-source authorization.

---

### Task 1: Lock the fantasy source and scoring contract

**Files:**
- Create: `pgo_fantasy.py`
- Create: `tests/test_pgo_fantasy.py`

**Interfaces:**
- Consumes: `pgo_sources.SourceSpec` and the existing nflverse URL conventions.
- Produces: `fantasy_source_specs() -> tuple[SourceSpec, ...]` and `half_ppr(row: dict[str, str]) -> float`.

- [ ] **Step 1: Write failing source-inventory and scoring tests**

Add tests that assert the inventory contains only one schedule plus six roster and six player-stat sources, requires `status`, includes every scoring component, and contains none of `injury`, `practice`, `inactive`, `depth_chart`, `pff`, or `betting`. Add this exact scoring example:

```python
def test_half_ppr_scores_every_locked_component(self):
    row = {
        "passing_yards": "250", "passing_tds": "2",
        "passing_interceptions": "1", "rushing_yards": "25",
        "receiving_yards": "40", "rushing_tds": "1",
        "receiving_tds": "1", "receptions": "4",
        "fumbles_lost_total": "1", "passing_2pt_conversions": "1",
        "rushing_2pt_conversions": "1",
        "receiving_2pt_conversions": "1", "special_teams_tds": "1",
    }
    self.assertAlmostEqual(pgo_fantasy.half_ppr(row), 46.5)

def test_half_ppr_treats_blanks_as_zero_and_rejects_nonfinite(self):
    self.assertEqual(pgo_fantasy.half_ppr({}), 0.0)
    with self.assertRaisesRegex(ValueError, "finite"):
        pgo_fantasy.half_ppr({"passing_yards": "NaN"})
```

- [ ] **Step 2: Run the focused tests and observe RED**

Run: `python -m unittest tests.test_pgo_fantasy -v`

Expected: import failure because `pgo_fantasy` does not exist.

- [ ] **Step 3: Implement the fixed inventory and scoring formula**

Create constants for seasons, positions, source columns, and scoring fields. Use the existing `SourceSpec`; do not change the team source inventory. The scoring implementation is the direct formula below and must reject invalid or non-finite inputs:

```python
def _number(row, name):
    raw = row.get(name, "")
    try:
        value = 0.0 if raw in (None, "") else float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {name}: {raw!r}") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def half_ppr(row):
    return (
        0.04 * _number(row, "passing_yards")
        + 4 * _number(row, "passing_tds")
        - 2 * _number(row, "passing_interceptions")
        + 0.1 * _number(row, "rushing_yards")
        + 0.1 * _number(row, "receiving_yards")
        + 6 * (_number(row, "rushing_tds") + _number(row, "receiving_tds"))
        + 0.5 * _number(row, "receptions")
        - 2 * _number(row, "fumbles_lost_total")
        + 2 * sum(_number(row, name) for name in TWO_POINT_FIELDS)
        + 6 * _number(row, "special_teams_tds")
    )
```

`fantasy_source_specs()` must return schedule, weekly-roster, and player-stat `SourceSpec` objects for 2020-2025 only. Keep the required-column tuples explicit so prohibited fields cannot enter through a generic pass-through feature list.

- [ ] **Step 4: Run the focused tests and observe GREEN**

Run: `python -m unittest tests.test_pgo_fantasy -v`

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit the contract rung**

```powershell
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: define fantasy scoring contract"
```

---

### Task 2: Construct and audit the eligible player-game population

**Files:**
- Modify: `pgo_fantasy.py`
- Modify: `tests/test_pgo_fantasy.py`

**Interfaces:**
- Consumes: `paths: dict[tuple[str, int | None], pathlib.Path]` matching `fantasy_source_specs()`.
- Produces: `build_player_games(paths) -> tuple[list[dict], dict]`, where rows contain `season`, `week`, `game_id`, `gsis_id`, `player_name`, `team`, `opponent`, `position`, and finite `fantasy_points`.

- [ ] **Step 1: Add a compact six-season CSV fixture helper**

Use `tempfile.TemporaryDirectory`, `csv.DictWriter`, and the module's required-column constants. The helper must create all 13 required files but may leave unused seasons with one non-population kicker row so each source remains non-empty. It returns the exact source-key/path mapping consumed by `build_player_games`.

```python
def write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
```

- [ ] **Step 2: Write failing population and fail-closed identity tests**

Cover all of these cases with synthetic rows:

- ACT QB/RB/FB/WR/TE rows join by `(game_id, gsis_id)` and FB emits position RB.
- `INA`, K, and a rostered player on a bye do not enter the population.
- an eligible ACT row with no player-stat row emits `fantasy_points == 0.0`;
- schedule, team, opponent, season, week, source-season, mapped-position, and GSIS joins must agree;
- duplicate player-week roster identity, conflicting team membership, duplicate natural key, missing status, missing GSIS ID, or an eligible stat row outside the ACT population raises `ValueError`;
- a source with a missing required column, missing key, extra key, or zero rows raises `ValueError`;
- the returned audit binds every exact source byte string with byte count and SHA-256 and records eligible, zero-filled, bye-skipped, and matched-stat counts by season.

Use explicit assertions such as:

```python
rows, audit = pgo_fantasy.build_player_games(paths)
self.assertEqual(
    [(row["gsis_id"], row["position"], row["fantasy_points"]) for row in rows],
    [("00-QB", "QB", 10.0), ("00-FB", "RB", 0.0)],
)
self.assertTrue(all(audit["checks"].values()))

with self.assertRaisesRegex(ValueError, "outside ACT roster population"):
    pgo_fantasy.build_player_games(paths_with_unmatched_stat)
```

- [ ] **Step 3: Run the population tests and observe RED**

Run: `python -m unittest tests.test_pgo_fantasy.FantasyPopulationTests -v`

Expected: failure because `build_player_games` is undefined.

- [ ] **Step 4: Implement exact-source validation and population construction**

Implement one read pass per source. Validate the exact expected source-key set and required columns before constructing rows. The algorithm must follow this order:

```python
schedule = load_completed_regular_season_games(source_rows[("schedule_results", None)])
rosters = load_act_eligible_rosters(source_rows, schedule)
stats = load_eligible_stats(source_rows, schedule)
unmatched = sorted(set(stats) - set(rosters))
if unmatched:
    raise ValueError(f"Eligible stat row outside ACT roster population: {unmatched[0]}")

rows = []
for key, roster in sorted(rosters.items()):
    stat = stats.get(key)
    if stat is not None and normalize_position(stat["position"]) != roster["position"]:
        raise ValueError(f"Position mismatch for {key}")
    rows.append({**roster, "fantasy_points": 0.0 if stat is None else half_ppr(stat)})
```

`load_completed_regular_season_games` must enforce unique `game_id` and unique `(season, week, team)` mappings for both teams. `load_act_eligible_rosters` must reject duplicate `(season, week, gsis_id)` before skipping non-ACT rows, then map completed team-weeks to natural keys. `load_eligible_stats` must validate its schedule-derived season, week, team, and opponent before joining. Sort returned rows by `(season, week, game_id, gsis_id)`.

The audit must be plain JSON-safe data and include:

```python
{
    "schema_version": 1,
    "scope": {"seasons": [2020, 2021, 2022, 2023, 2024, 2025],
              "game_type": "REG", "roster_status": "ACT"},
    "sources": source_receipts,
    "coverage": {
        str(season): {"eligible": 0, "matched_stats": 0,
                      "zero_filled": 0, "bye_skipped": 0}
        for season in MODEL_SEASONS
    },
    "checks": {"source_contract": True, "schedule_identity": True,
               "roster_identity": True, "stat_identity": True,
               "finite_targets": True},
}
```

- [ ] **Step 5: Run focused population and scoring tests**

Run: `python -m unittest tests.test_pgo_fantasy -v`

Expected: all Task 1-2 tests pass.

- [ ] **Step 6: Commit the audited population rung**

```powershell
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: audit fantasy player-game population"
```

---

### Task 3: Add strictly chronological null and strong baselines

**Files:**
- Modify: `pgo_fantasy.py`
- Modify: `tests/test_pgo_fantasy.py`

**Interfaces:**
- Consumes: sorted player-game rows from `build_player_games`.
- Produces: `strong_baseline(history: list[float], position_mean: float) -> float`, `select_primary_pool(rows: list[dict]) -> set[tuple[str, str]]`, and `backtest_baselines(rows: list[dict], source_audit: dict) -> tuple[dict, list[dict]]`.

- [ ] **Step 1: Write the exact strong-baseline unit test**

```python
def test_strong_baseline_uses_eight_games_half_life_four_and_four_pseudo_games(self):
    history = [float(value) for value in range(1, 11)]
    recent_newest_first = list(reversed(history[-8:]))
    weights = [2 ** (-index / 4) for index in range(8)]
    expected = (
        sum(value * weight for value, weight in zip(recent_newest_first, weights))
        + 4 * 12.0
    ) / (sum(weights) + 4)
    self.assertAlmostEqual(pgo_fantasy.strong_baseline(history, 12.0), expected)
    self.assertEqual(pgo_fantasy.strong_baseline([], 12.0), 12.0)
```

- [ ] **Step 2: Write the chronology regression before implementation**

Build a fold with at least two players and three 2022 weeks. Change one player's Week 2 outcome. Assert every Week 1 and Week 2 prediction remains byte-for-byte equal and at least that player's Week 3 strong prediction changes. This proves a result from one kickoff cannot enter another prediction in the same week.

```python
original = pgo_fantasy.backtest_baselines(rows, audit)[1]
mutated = pgo_fantasy.backtest_baselines(rows_with_changed_week_2_target, audit)[1]
key = lambda row: (row["season"], row["week"], row["game_id"], row["gsis_id"])
before = {key(row): row for row in original if row["season"] == 2022}
after = {key(row): row for row in mutated if row["season"] == 2022}
self.assertEqual(
    [(key(row), row["strong_prediction"]) for row in original if row["season"] == 2022 and row["week"] <= 2],
    [(key(row), row["strong_prediction"]) for row in mutated if row["season"] == 2022 and row["week"] <= 2],
)
self.assertNotEqual(before[week_3_key]["strong_prediction"], after[week_3_key]["strong_prediction"])
```

- [ ] **Step 3: Write deterministic primary-pool tests**

Generate tied strong predictions with unique GSIS IDs. Assert exactly 24 QB, 24 RB, 24 WR, 12 TE, and 12 remaining RB/WR/TE keys are selected, no key is duplicated, and ties select lexicographically smaller GSIS IDs. Test a short pool raises `ValueError` rather than silently changing the primary population.

- [ ] **Step 4: Run the new tests and observe RED**

Run: `python -m unittest tests.test_pgo_fantasy.FantasyBaselineTests -v`

Expected: failure because baseline functions are undefined.

- [ ] **Step 5: Implement the baseline and week-batched state update**

Use lists and dictionaries; no estimator abstraction is needed. The strong formula is:

```python
def strong_baseline(history, position_mean):
    if not math.isfinite(position_mean):
        raise ValueError("Position mean must be finite")
    recent = list(reversed(history[-8:]))
    if not recent:
        return position_mean
    weights = [2 ** (-index / 4) for index in range(len(recent))]
    return (
        sum(value * weight for value, weight in zip(recent, weights))
        + 4 * position_mean
    ) / (sum(weights) + 4)
```

For each test season, seed player histories and position sums/counts from all rows in strictly earlier seasons. Fix null means from that seed. Then process the test season by week:

```python
for week in sorted(test_weeks):
    week_predictions = []
    for row in sorted(test_weeks[week], key=row_key):
        position = row["position"]
        live_mean = position_sums[position] / position_counts[position]
        week_predictions.append({
            **row,
            "null_prediction": null_means[position],
            "strong_prediction": strong_baseline(histories.get(row["gsis_id"], []), live_mean),
        })
    primary = select_primary_pool(week_predictions)
    for prediction in week_predictions:
        prediction["primary_pool"] = natural_key(prediction) in primary
    predictions.extend(week_predictions)
    for row in test_weeks[week]:
        histories.setdefault(row["gsis_id"], []).append(row["fantasy_points"])
        position_sums[row["position"]] += row["fantasy_points"]
        position_counts[row["position"]] += 1
```

Never sort or filter on the target when selecting the primary pool. Require all four position means and all five quotas for every evaluated week.

- [ ] **Step 6: Run focused tests and observe GREEN**

Run: `python -m unittest tests.test_pgo_fantasy -v`

Expected: all Task 1-3 tests pass.

- [ ] **Step 7: Commit the baseline rung**

```powershell
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: add chronological fantasy baselines"
```

---

### Task 4: Produce a deterministic baseline-only receipt

**Files:**
- Modify: `pgo_fantasy.py`
- Modify: `tests/test_pgo_fantasy.py`

**Interfaces:**
- Consumes: source audit plus the 2022-2025 validation predictions.
- Produces: the report returned by `backtest_baselines`, `serialize_baseline_report(report) -> str`, and `serialize_baseline_predictions(rows) -> str`.

- [ ] **Step 1: Write failing fold-report tests**

Build a small but quota-complete synthetic table for 2020-2025 and assert:

- fold order is 2022, 2023, 2024, 2025 with expanding `train_seasons`;
- each fold and pooled block reports counts plus null/strong MAE for primary and all eligible rows;
- pooled position metrics use the common primary rows;
- all metrics are finite and recompute exactly from returned predictions;
- `stage == BASELINE_ONLY`, `status == HOLD`, and `publication_status == EXPERIMENTAL`;
- no candidate, PASS, injury, PFF, or availability claim appears;
- `source_audit_sha256` is SHA-256 of compact canonical source-audit JSON;
- JSON and CSV serializers are deterministic under input-row permutation, reject non-finite values, end with one LF, and quote through `json`/`csv` rather than hand-built text.

- [ ] **Step 2: Run report tests and observe RED**

Run: `python -m unittest tests.test_pgo_fantasy.FantasyReceiptTests -v`

Expected: failure because receipt serializers and metrics are incomplete.

- [ ] **Step 3: Implement direct metric aggregation and serialization**

Use one MAE helper and explicit slices. The report shape is:

```python
{
    "schema_version": 1,
    "model": "pgo_fantasy_baselines_v1",
    "stage": "BASELINE_ONLY",
    "status": "HOLD",
    "publication_status": "EXPERIMENTAL",
    "status_reason": "No candidate is evaluated in the baseline-only slice",
    "scoring": "HALF_PPR",
    "population": "WEEKLY_ROSTER_ACT_QB_RB_FB_WR_TE",
    "source_audit_sha256": canonical_sha256(source_audit),
    "folds": fold_metrics,
    "pooled": metric_block(predictions),
}
```

Serialize JSON with `sort_keys=True`, `indent=2`, `allow_nan=False`, and a final newline. Serialize validation rows sorted by `(season, week, game_id, gsis_id)` with this fixed header:

```python
PREDICTION_COLUMNS = (
    "season", "week", "game_id", "gsis_id", "player_name", "team",
    "opponent", "position", "fantasy_points", "null_prediction",
    "strong_prediction", "primary_pool",
)
```

Use `io.StringIO(newline="")` and
`csv.DictWriter(handle, fieldnames=PREDICTION_COLUMNS, lineterminator="\n")`.
Validate every numeric output with `math.isfinite` before serialization.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m unittest tests.test_pgo_fantasy -v`

Expected: all focused tests pass.

Run: `python -W error::ResourceWarning -m unittest discover -s tests -p "test_*.py"`

Expected: the full repository suite passes with warnings treated as errors.

- [ ] **Step 5: Commit the receipt rung**

```powershell
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: report fantasy baseline folds"
```

---

### Task 5: Perform leakage, scope, and protected-artifact verification

**Files:**
- Verify only: `pgo_fantasy.py`
- Verify only: `tests/test_pgo_fantasy.py`
- Verify unchanged: team model, research, prospective, public-site, workflow, and store paths.

**Interfaces:**
- Consumes: the completed baseline implementation and its test evidence.
- Produces: a review result; no generated model artifact or deployment.

- [ ] **Step 1: Run syntax and whitespace checks**

```powershell
python -m py_compile pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --check
```

Expected: both commands exit 0 with no output.

- [ ] **Step 2: Run the focused chronology/leakage checks**

```powershell
python -m unittest tests.test_pgo_fantasy.FantasyBaselineTests -v
```

Expected: all future-perturbation, same-week batching, target-independent pool, and fold-order tests pass.

- [ ] **Step 3: Audit every admitted input**

Read `fantasy_source_specs`, `build_player_games`, and `backtest_baselines` end to end. Confirm each prediction reads only:

- stable schedule and GSIS/team identity;
- current weekly `ACT` only for population membership;
- fantasy outcomes from strictly earlier weeks;
- the current player's earlier eligible outcomes and earlier-week position outcomes.

Search for prohibited surfaces:

```powershell
rg -n -i "pff|injur|practice|game.?status|inactive|depth.?chart|participation|market|betting|current.game" pgo_fantasy.py tests/test_pgo_fantasy.py
```

Expected: only negative assertions or explanatory error/test text; no input column, feature, join, or prediction branch uses a prohibited surface.

- [ ] **Step 4: Verify protected paths are unchanged**

Capture the implementation worktree's starting commit in `$fantasyBase`, then run:

```powershell
git diff --name-only $fantasyBase...HEAD
git status --short
```

Expected tracked paths are exactly `pgo_fantasy.py` and `tests/test_pgo_fantasy.py`; the documentation-plan commit is already in `$fantasyBase`. No file under `data/`, `research/`, `prospective_evidence/`, `docs/index.html`, `.github/workflows/`, or Shopify/theme paths appears.

- [ ] **Step 5: Run final verification from the committed tree**

```powershell
python -m unittest tests.test_pgo_fantasy -v
python -W error::ResourceWarning -m unittest discover -s tests -p "test_*.py"
git diff --check
git status --short --branch
```

Expected: focused and full suites pass; whitespace check passes; only authorized tracked files differ from the starting commit.

- [ ] **Step 6: Stop at the authorized boundary**

Do not download or freeze nflverse bytes, add reconciliation exceptions for the known 2020-2025 roster/stat disagreements, run a canonical backtest, implement a candidate, create 2026 locks, edit the site, push, or deploy. Report the verified code slice and the remaining source-reconciliation gate for separate approval.
