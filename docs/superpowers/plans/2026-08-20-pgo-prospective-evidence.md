# PGO Prospective Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task with review checkpoints.

**Goal:** Add a separate, immutable pregame lock-and-grade runner that produces prospective PGO evidence without changing the historical HOLD receipt or public artifacts.

**Architecture:** Create \`pgo_prospective.py\` as a thin orchestration layer over the existing PGO challenger and v0 model helpers. The lock command fits and serializes the exact model state, hashes a separate schedule snapshot, and records predictions before kickoff; the grade command validates final results against that lock and reuses the fixed MAE/bootstrap/subgroup gates. Keep all outputs in a caller-provided directory.

**Tech Stack:** Python 3.11+, standard library \`csv\`/\`json\`/\`hashlib\`/\`argparse\`, existing NumPy model code, \`unittest\`.

## Global Constraints

- Historical PGO v1 evaluation window, grid, bootstrap sample count (\`10_000\`), and seed (\`20260721\`) remain unchanged.
- \`research/pgo_v1/backtest.json\`, \`research/pgo_v1/ratings_2026_preseason.csv\`, \`research/pgo_v1/validation_predictions.csv\`, \`research/pgo_v1/source_audit.json\`, and \`docs/index.html\` must not be modified.
- Lock and grade never fetch data; all source and schedule bytes are supplied by the caller and hashed.
- Only locked pre-kickoff information may enter predictions; grading never refits or reads post-kickoff features.
- A prospective \`PASS\` is evidence only and does not automatically promote or publish any artifact.
- New code must use existing \`_walk\`, \`_team_views\`, \`_matchup_features\`, \`select_parameters\`, \`fit_preprocessor\`, \`fit_huber_ridge\`, \`predict\`, \`paired_block_bootstrap\`, and \`subgroup_results\` behavior rather than reimplementing model math.

---

### Task 1: Add red tests for lock/grade contracts

**Files:**
- Create: \`tests/test_pgo_prospective.py\`
- Read-only fixtures/helpers: \`tests/test_pgo_challenger.py\`

**Interfaces:**
- Tests will call the planned pure helpers:
  \`pgo_prospective.lock_games(schedule_snapshot, model_state, as_of)\`,
  \`pgo_prospective.grade_locked_games(lock, results)\`,
  \`pgo_prospective.write_lock(output_dir, lock)\`, and
  \`pgo_prospective.write_grade(output_dir, receipt, rows)\`.
- A lock record must contain \`game_id\`, \`season\`, \`week\`, \`kickoff\`, \`home\`,
  \`away\`, \`pgo_v0_prediction\`, \`challenger_prediction\`,
  \`challenger_full_strength_prediction\`, and \`subgroup_flags\`.

- [ ] **Step 1: Write deterministic lock tests**

Create synthetic unplayed 2026 schedule rows with an exact source hash and a
small injected model state.
Assert that two calls with identical inputs produce identical serialized lock
bytes, the lock contains no \`actual_margin\`, and the schedule hash is recorded.

\`\`\`python
def test_lock_is_deterministic_and_pregame_only(self):
    first = pgo_prospective.lock_games(
        self.schedule, self.model_state, as_of="2026-08-20T12:00:00-04:00"
    )
    second = pgo_prospective.lock_games(
        self.schedule, self.model_state, as_of="2026-08-20T12:00:00-04:00"
    )
    self.assertEqual(pgo_prospective.serialize_lock(first),
                     pgo_prospective.serialize_lock(second))
    self.assertNotIn("actual_margin", first["games"][0])
    self.assertEqual(len(first["games"]), 2)
\`\`\`

- [ ] **Step 2: Write lock rejection tests**

Cover duplicate game IDs, a final score in a supposedly unplayed row, missing
kickoff, kickoff at or before the lock boundary, and non-finite predictions.
Each must raise \`ValueError\` with a stable message prefix.

- [ ] **Step 3: Write grade metric and tamper tests**

Use two locked games and finalized results. Assert actual margins, challenger
and v0 MAE, bootstrap metadata, and the returned status. Then assert grade
rejects missing, extra, duplicate, changed-team, and changed-kickoff rows.

\`\`\`python
def test_grade_rejects_changed_locked_game(self):
    results = [{**self.results[0], "home_team": "BUF"}, self.results[1]]
    with self.assertRaisesRegex(ValueError, "locked home team"):
        pgo_prospective.grade_locked_games(self.lock, results)
\`\`\`

- [ ] **Step 4: Write protected-artifact test**

Hash the five protected historical/public files, run lock serialization and
grade serialization in a temporary output directory, and assert every hash is
unchanged.

- [ ] **Step 5: Run focused tests to confirm intentional RED**

Run:

\`\`\`powershell
python -m unittest tests.test_pgo_prospective -v
\`\`\`

Expected: import/helper failures only; no existing PGO challenger tests may
fail. Commit the tests with:

\`\`\`powershell
git add tests/test_pgo_prospective.py
git commit -m "test: specify PGO prospective evidence contracts"
\`\`\`

---

### Task 2: Implement immutable lock generation

**Files:**
- Create: \`pgo_prospective.py\`
- Modify: none unless a narrowly scoped shared helper export is required

**Interfaces:**
- \`load_schedule_snapshot(path) -> {"rows": list[dict], "sha256": str}\`
- \`lock_games(schedule_snapshot, model_state, as_of) -> dict\`
- \`serialize_lock(lock) -> str\`
- \`write_lock(output_dir, lock) -> Path\`
- CLI example: \`python pgo_prospective.py lock --as-of 2026-08-20T12:00:00-04:00 --lock-path research/pgo_v1/sources.lock.json --cache-dir D:\\CodexWorktrees\\Postgame_Outlet-pgo-v2-roster\\.cache\\pgo_v1 --schedule-snapshot C:\\Users\\Alex\\AppData\\Local\\Temp\\pgo-2026-schedule.csv --output-dir C:\\Users\\Alex\\AppData\\Local\\Temp\\pgo-prospective-lock\`

- [ ] **Step 1: Implement schedule validation and hashing**

Read the supplied CSV once, require regular-season rows with unique IDs,
normalized teams, valid kickoff/rest/venue fields, and blank scores for target
2026 games. Hash the exact source bytes with SHA-256 and retain the digest in
the lock.

- [ ] **Step 2: Implement final model-state fitting**

Load the existing frozen source lock/cache, fit the selected challenger using
the existing \`select_parameters\`, \`build_feature_rows\`, \`fit_preprocessor\`,
\`fit_huber_ridge\`, and \`predict\` functions, and serialize parameters,
feature/missingness names, medians, scales, and coefficients. Fit the v0
benchmark using \`pgo_model.select_parameters\` and \`walk_forward\`; serialize
its parameters and final ratings state.

- [ ] **Step 3: Implement kickoff-time prediction rows**

For each unplayed 2026 game, use only source rows available before kickoff,
build both team lineup views, calculate current and full-strength matchup
features, predict both challenger views, and calculate the v0 benchmark. Store
the subgroup flags before any result is known. Reject non-finite output.

- [ ] **Step 4: Implement canonical serialization and atomic output**

Serialize JSON with sorted keys and stable separators. Include schema/version,
lock timestamp, source hashes, model state, games, \`status: "LOCKED"\`, and a
SHA-256 artifact hash. Write \`prospective_lock.json\` and
\`prospective_predictions.csv\` atomically; never write to \`research/pgo_v1\` by
default.

- [ ] **Step 5: Run focused tests green and commit**

Run:

\`\`\`powershell
python -m unittest tests.test_pgo_prospective -v
python -m py_compile pgo_prospective.py tests/test_pgo_prospective.py
git diff --check
\`\`\`

Commit:

\`\`\`powershell
git add pgo_prospective.py tests/test_pgo_prospective.py
git commit -m "feat: add immutable PGO prospective lock"
\`\`\`

---

### Task 3: Implement tamper-proof grading and receipt gates

**Files:**
- Modify: \`pgo_prospective.py\`
- Modify: \`tests/test_pgo_prospective.py\`

**Interfaces:**
- \`grade_locked_games(lock, results) -> dict\`
- \`serialize_grade(receipt, rows) -> tuple[str, str]\`
- \`write_grade(output_dir, receipt, rows) -> Path\`
- CLI example: \`python pgo_prospective.py grade --lock-file C:\\Users\\Alex\\AppData\\Local\\Temp\\pgo-prospective-lock\\prospective_lock.json --results-path C:\\Users\\Alex\\AppData\\Local\\Temp\\pgo-2026-results.csv --output-dir C:\\Users\\Alex\\AppData\\Local\\Temp\\pgo-prospective-grade\`

- [ ] **Step 1: Validate final results against the lock**

Require exactly one result per locked game, matching \`game_id\`, teams, kickoff,
and regular-season status. Require numeric finalized scores and a non-empty
\`finalized_at\`; reject every missing, extra, duplicate, changed, or non-final
row before computing metrics.

- [ ] **Step 2: Compute fixed evidence metrics**

Join actual margins to the locked predictions, compute challenger/v0 MAE and
paired improvements, call \`paired_block_bootstrap(rows, samples=10_000,
seed=20260721)\`, and call \`subgroup_results(rows)\` using the locked flags. The
prospective gate passes only when counts match, challenger MAE is lower, the
interval lower bound is above zero, and no sufficient subgroup regresses.

- [ ] **Step 3: Emit status and receipt**

Use \`PASS\` when every prospective integrity/statistical check passes, \`HOLD\`
when integrity passes but a statistical check fails, and \`BLOCKED\` for any
integrity failure. The Python API fails closed on integrity errors; the CLI
writes a `BLOCKED` receipt and exits nonzero. Include failed checks, lock hash,
results hash, source hashes, sample count, seed, feature manifest, and publication status
(\`VALIDATED\` only for \`PASS\`, \`EXPERIMENTAL\` for \`HOLD\`).

- [ ] **Step 4: Run focused tests and commit**

Run:

\`\`\`powershell
python -m unittest tests.test_pgo_prospective -v
python -m py_compile pgo_prospective.py tests/test_pgo_prospective.py
git diff --check
\`\`\`

Commit:

\`\`\`powershell
git add pgo_prospective.py tests/test_pgo_prospective.py
git commit -m "feat: grade PGO prospective evidence"
\`\`\`

---

### Task 4: Full verification and dry-run safety audit

**Files:**
- Modify: none
- Inspect: \`research/pgo_v1/*\`, \`docs/index.html\`

- [ ] **Step 1: Run the full suite and static checks**

\`\`\`powershell
python -m unittest discover -s tests
python -m py_compile pgo_challenger.py pgo_prospective.py tests/test_pgo_challenger.py tests/test_pgo_prospective.py
git diff --check
\`\`\`

- [ ] **Step 2: Run the synthetic lock/grade end-to-end flow**

Run the focused test fixture into a unique temporary directory, inspect both
receipts, and verify lock and grade are deterministic and tamper rejection is
fail-closed.

- [ ] **Step 3: Run a live lock only when a real unplayed schedule snapshot is available**

Use the exact approved source lock/cache and a separately hashed schedule
snapshot. If no unplayed 2026 rows exist, report that as an expected data
availability blocker rather than fabricating predictions.

- [ ] **Step 4: Verify artifact safety**

Hash \`research/pgo_v1/*\` and \`docs/index.html\` before and after. Require an
empty \`git diff -- docs/index.html research/pgo_v1\` and a clean worktree.

- [ ] **Step 5: Commit only if code changed and report evidence**

Record test counts, lock/grade hashes, status, failed gates, source snapshot
dates, and the explicit rule that prospective evidence does not authorize
publication by itself.
