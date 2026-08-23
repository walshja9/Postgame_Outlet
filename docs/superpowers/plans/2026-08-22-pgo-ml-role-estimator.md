# PGO ML Role Estimator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a leakage-safe learned healthy-role estimator that fills missing injury-overlay snap shares while preserving the existing PGO team-margin model, full-strength ratings, and HOLD safeguards.

**Architecture:** Reuse the existing chronological `_walk` state, NumPy preprocessing, Huber-ridge solver, and current-lineup overlay path. Historical player-week states produce two role targets—healthy offensive and defensive snap share—then the fitted role models fill only missing current overlay role fields. Availability probability remains source-derived. A separate sidecar audit records whether all 32 current teams were processed; no provider-specific scraper is added.

**Tech Stack:** Python 3, NumPy, existing `unittest` suite, CSV/JSON standard-library receipts, existing frozen nflverse cache, existing Huber-ridge implementation.

## Global Constraints

- Preserve the frozen historical source lock, cache, `as_of`, 2,127-game evaluation, PGO v0 benchmark, target, loss, bootstrap seed `20260721`, gates, and HOLD/PASS semantics.
- Do not alter full-strength ratings, McCabe ratings, `data/snapshots.json`, `docs/index.html`, Shopify files, or deployment workflows.
- Use only pregame historical information for role features and targets; reject post-kickoff mutations.
- Explicit overlay role estimates override learned estimates; learned estimates override generic priors; generic priors remain the final fallback.
- Do not add scikit-learn, a new model framework, an undocumented injury-feed dependency, or a second end-to-end team-margin model.
- Keep all new model results research-only unless the existing gates produce a real `PASS`.

---

### Task 1: Add failing role-state and fold-boundary tests

**Files:**
- Modify: `tests/test_pgo_challenger.py`
- Test helpers: `tests/test_pgo_challenger.py:_synthetic_paths`

**Interfaces:**
- Consumes: Existing synthetic schedule, roster, injury, and snap fixtures.
- Produces: Red tests for `build_role_training_rows`, `fit_role_models`, and current-overlay role precedence.

- [ ] **Step 1: Extend the synthetic fixture with a non-QB player whose healthy week-two snap share is known.**

Add one WR to the synthetic roster and snap files for two chronological games. Give the WR a week-one offensive share of `0.40`, a week-two offensive share of `0.60`, no injury rows, and a stable GSIS/PFR identity. Keep the existing fixture rows unchanged so current challenger tests retain their expected values.

- [ ] **Step 2: Write the failing training-row test.**

Add this test shape to `AvailabilityOverlayTests`:

```python
def test_role_training_rows_use_pregame_state_and_exclude_unavailable_rows(self):
    rows = pgo_challenger.build_role_training_rows(
        paths, 4, as_of="2014-09-08T12:00:00-04:00"
    )
    row = next(row for row in rows if row.player_id == "gsis-future-wr")
    self.assertEqual(row.features["position_skill"], 1.0)
    self.assertAlmostEqual(row.features["prior_offense_snap_share"], 0.40)
    self.assertAlmostEqual(row.target_offense_snap_share, 0.60)
    self.assertTrue(all(row.availability_probability == 1.0 for row in rows))
```

The test must initially fail because the role-row builder does not exist.

- [ ] **Step 3: Write the failing model and precedence tests.**

Add tests that require a fitted role model to return a finite share in `[0, 1]`, that an explicit overlay role remains unchanged when a role model is supplied, and that a missing overlay role is marked `learned` before the generic fallback is considered.

```python
def test_learned_role_fills_missing_overlay_role_without_touching_full_strength(self):
    role_models = pgo_challenger.RoleModels(
        offense=pgo_challenger.RoleModel(
            pgo_challenger.Preprocessor(("position_skill",), np.array([1.0]), np.array([1.0]), ()),
            np.array([0.0, 0.30]),
        ),
        defense=None,
    )
    players = {"wr": {
        "gsis_id": "gsis-wr", "position": "WR", "probability": 0.0,
        "offense_snap_share": None, "defense_snap_share": 0.0,
    }}
    updated, _ = pgo_challenger.apply_availability_overlay(
        "BUF", players, {("BUF", "gsis-wr"): {
            "availability_probability": 0.0,
            "offense_snap_share": None, "defense_snap_share": None,
        }}, role_models=role_models,
    )
    self.assertEqual(updated["wr"]["role_source"], "learned")
    self.assertAlmostEqual(updated["wr"]["offense_snap_share"], 0.30)
```

The test must initially fail because `RoleModels`, `RoleModel`, and the
`role_models` argument do not exist.

- [ ] **Step 4: Run the red tests.**

Run:

```powershell
python -m pytest tests/test_pgo_challenger.py -q -k "role_training or learned_role"
```

Expected: failure naming the missing role-training/model interfaces.

### Task 2: Implement deterministic historical role training and inference

**Files:**
- Modify: `pgo_challenger.py` near `FeatureRow`, `Preprocessor`, `fit_huber_ridge`, `_walk`, and `_update_after_game`
- Test: `tests/test_pgo_challenger.py`

**Interfaces:**
- Consumes: `_walk`, `_players_for_team`, historical injury timing, snap history, and existing Huber-ridge helpers.
- Produces:
  - `RoleTrainingRow(player_id, kickoff, features, target_offense_snap_share, target_defense_snap_share, availability_probability)`
  - `RoleModel(preprocessor, coefficients)`
  - `RoleModels(offense, defense)`
  - `build_role_training_rows(paths, half_life_games, as_of=None)`
  - `fit_role_models(rows)`
  - `predict_role_share(model, features)`

- [ ] **Step 1: Add the minimal role dataclasses and fixed feature names.**

Use numeric features only: `position_quarterback`, `position_skill`, `position_line`, `position_defense`, `years_exp`, `prior_offense_snap_share`, `prior_defense_snap_share`, `prior_offense_missing`, `prior_defense_missing`, and `prior_starter`. Use the existing `Preprocessor` and `fit_huber_ridge`; do not introduce a new dependency.

- [ ] **Step 2: Add role-row collection to the chronological walk.**

At each game, pair each roster player's pregame state from `metadata["roster"]` with the postgame snap share computed in `_update_after_game`. Append a row only when the player has a valid identity, a finite target, and `probability == 1.0`. Record both sides independently so a missing defensive target does not discard a valid offensive target. The target row must be appended before mutating the player's snap history.

- [ ] **Step 3: Add fold-safe model fitting and bounded prediction.**

`build_role_training_rows` must call `_walk` with the supplied `as_of` boundary and return only rows before that boundary. `fit_role_models` must fit each side only on rows with a finite target, use deterministic feature ordering, and return `None` for a side without enough data. `predict_role_share` must return `None` for missing models or non-finite inputs and otherwise clamp the finite prediction to `[0.0, 1.0]`.

- [ ] **Step 4: Run the focused tests green.**

Run:

```powershell
python -m pytest tests/test_pgo_challenger.py -q -k "role_training or learned_role"
```

Expected: all new role-training and bounded-prediction tests pass.

### Task 3: Integrate learned roles into current-lineup overlay processing

**Files:**
- Modify: `pgo_challenger.py:load_availability_overlay`, `apply_availability_overlay`, `_team_views`, `build_snapshot_states`, `_analyze_once`, `_build_backtest`
- Modify: `tests/test_pgo_challenger.py`

**Interfaces:**
- Consumes: `RoleModels`, current normalized availability overlay, and historical role rows through the model `as_of` boundary.
- Produces: Current-lineup ML role estimates with provenance in the analysis audit; unchanged full-strength states.

- [ ] **Step 1: Add role provenance to overlay application.**

Extend `apply_availability_overlay(..., role_models=None)` so each matched player records `role_source` as one of `explicit`, `learned`, `generic`, or `unavailable`. Explicit low/base/high fields always win. A learned estimate fills only a missing role field. The generic prior runs only when the learned estimate returns `None`.

- [ ] **Step 2: Thread `role_models` through the existing current-lineup path.**

Pass the models through `build_snapshot_states` to `_team_views`, and apply them after base continuity features are calculated, exactly where the existing overlay is applied. Keep `full` calculated from the unmodified base state and keep `current` as the only view receiving learned roles.

- [ ] **Step 3: Fit the role models inside `_analyze_once`.**

Build role rows with the same locked paths and final historical boundary used for the team model, fit the two role models, and add a deterministic `role_model` audit entry containing feature names, offense/defense row counts, model as-of, and role-model coefficients. Pass the models to `build_snapshot_states`. Do not add a new release gate or change existing status semantics.

- [ ] **Step 4: Add coverage-sidecar validation without fabricating rows.**

Add an optional JSON audit input with `source`, `source_as_of`, `raw_source_sha256`, and `teams_processed`. When supplied, require exactly the 32 `pgo_model.CURRENT_TEAMS`, require its timestamp to match the overlay, and include the result in the overlay receipt. When absent, preserve research execution but mark current injury coverage as incomplete so a release cannot claim complete source coverage.

- [ ] **Step 5: Run the focused overlay and isolation tests.**

Run:

```powershell
python -m pytest tests/test_pgo_challenger.py -q -k "AvailabilityOverlayTests or generic_role_prior or full_strength"
```

Expected: explicit roles, learned roles, generic fallbacks, coverage rejection, and full-strength isolation all pass.

### Task 4: Add the bounded historical ML shadow comparison

**Files:**
- Modify: `tests/test_pgo_challenger.py` only for deterministic evaluator coverage
- Temporary: unique system temporary directory for the cached comparison script; do not add a permanent backtest framework

**Interfaces:**
- Consumes: frozen source lock/cache, `build_role_training_rows`, `fit_role_models`, the locked baseline predictions, and existing paired-bootstrap rules.
- Produces: low/base/high research-only comparison metrics for role MAE, team-margin MAE, changed games, maximum prediction delta, and paired interval.

- [ ] **Step 1: Add a deterministic synthetic test for fold exclusion.**

Fit a role model with an `as_of` boundary, mutate a post-boundary snap row, refit, and assert the model coefficients and training-row hash are unchanged. This test must fail if role training accidentally consumes future rows.

- [ ] **Step 2: Run the cached low/base/high counterfactual.**

For each role scenario, train only from rows before the validation fold, fill only missing historical injured-player roles, score the same 2,127-game population, and use seed `20260721` for paired bootstrap. Print one JSON result per scenario and retain no generated research artifacts in the repository.

- [ ] **Step 3: Interpret the result using the existing release rule.**

Require lower team-margin MAE and a strictly positive paired lower bound before considering promotion. Any interval crossing zero, incomplete current source coverage, or failed integrity gate leaves the role layer research-only and PGO `HOLD`.

### Task 5: Verify the implementation and hand off without publishing

**Files:**
- Modify: none beyond the implementation and tests above
- Inspect: `git diff`, `docs/index.html`, `research/pgo_v1/*`

- [ ] **Step 1: Run focused tests.**

```powershell
python -m pytest tests/test_pgo_challenger.py -q
python -m pytest tests/test_pgo_comparison.py tests/test_public_board_workflow.py tests/test_ratings_release.py -q
```

- [ ] **Step 2: Run the full suite and static checks.**

```powershell
python -m pytest -q
python -m py_compile pgo_challenger.py pgo_sources.py tests/test_pgo_challenger.py
git diff --check
```

Expected: all tests pass; compilation succeeds; whitespace check reports no errors.

- [ ] **Step 3: Confirm protected artifacts and status.**

Verify `docs/index.html`, `research/pgo_v1/backtest.json`, `research/pgo_v1/validation_predictions.csv`, `research/pgo_v1/ratings_2026_preseason.csv`, and `research/pgo_v1/source_audit.json` remain unchanged. Confirm the worktree contains only the intended local implementation, tests, spec, plan, and explicitly supplied overlay data.

- [ ] **Step 4: Report publication readiness.**

Report the role MAE, team-margin MAE, paired interval, team coverage, test counts, and exact HOLD/PASS result. Do not commit, regenerate `docs/index.html`, push, deploy, or change public wording without separate authorization.
