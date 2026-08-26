# PGO Prospective Stability Blend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one immutable 25% PGO v1 / 75% PGO v0 prospective candidate, attest it before the first 2026 regular-season kickoff, and grade it without changing canonical PGO v1, its `HOLD` label, or the July 21 lock.

**Architecture:** Extend `pgo_prospective.py` in place. Reuse its canonical JSON, SHA-256, atomic writer, base lock/result validation, MAE, paired block bootstrap, and subgroup gates. Add explicit schema-2 behavior only for `candidate.kind == "fixed_convex_stability_blend"`; schema-1 behavior remains byte-identical. Keep the derived lock local and commit only the deterministic development receipt plus the external attestation.

**Tech Stack:** Python 3.11+, standard-library `argparse`/`csv`/`hashlib`/`json`, existing NumPy-backed PGO helpers, `unittest`, PowerShell, Git/GitHub CLI.

## Global Constraints

- Use test-driven development: add one failing behavior at a time, run it red, implement the minimum code, then rerun green.
- Modify only `pgo_prospective.py`, `tests/test_pgo_prospective.py`, `research/pgo_stability_blend/development.json`, and `research/pgo_stability_blend/prospective_attestation.json` during implementation.
- Do not add a package, module, dependency, generalized candidate framework, configuration layer, or second modeling pipeline.
- Keep the blend fixed at `0.75 * pgo_v0_prediction + 0.25 * challenger_prediction`; do not round, clip, refit, or fetch live data.
- Keep every schema-1 serialized byte and hash unchanged. The current synthetic regression digests are part of the test contract.
- Do not modify anything under `prospective_evidence/2026-07-21/`, `research/pgo_v1/`, `data/`, `.github/workflows/`, Shopify, or store files.
- The derived directory must not exist before derivation and must remain untracked. Never stage `prospective_evidence/`.
- Never use `git add -A`; stage only the exact paths listed in each task.
- A statistical `HOLD` is a valid outcome. Never weaken the fixed 95% interval, subgroup, population, or integrity gates.
- Stop before derivation if the current timestamp is not strictly earlier than every locked kickoff.
- Stop rather than overwrite any existing derived artifact or attestation.

---

### Task 1: Freeze schema-1 compatibility and build the development receipt

**Files:**

- Modify: `tests/test_pgo_prospective.py:18-24, 282`
- Modify: `pgo_prospective.py:21-29, 254-314, 847-864`
- Create: `research/pgo_stability_blend/development.json`
- Read only: `research/pgo_v1/validation_predictions.csv`

**Interfaces:**

- `load_development_predictions(path) -> {"rows": list[dict], "sha256": str}`
- `develop_stability_blend(source) -> dict`
- `_comparison_rows(rows, incumbent_key, candidate_key) -> list[dict]`
- `_verify_development_receipt(receipt) -> dict`
- `write_development_receipt(path, receipt) -> Path`
- `_cli_develop_blend(args) -> int`

- [ ] **Step 1: Add schema-1 byte-regression tests before changing shared serialization**

Add a new `ProspectiveSchemaOneRegressionTests` class that reuses the existing
synthetic fixtures and locks these four current SHA-256 values:

```python
def test_schema_one_serialized_bytes_are_frozen(self):
    lock_tests = ProspectiveLockTests()
    lock_tests.setUp()
    lock = pgo_prospective.lock_games(lock_tests.schedule, lock_tests.model_state, AS_OF)
    self.assertEqual(
        _sha256(pgo_prospective.serialize_lock(lock)),
        "38a32705b5ff09efcc60a1e12526acbfdf6960525aadac9c80847513f70b7ad0",
    )
    self.assertEqual(
        _sha256(pgo_prospective._prediction_csv(lock)),
        "97ac0f7f24786ef04bc67a493283b1e3f61422c45007b024d6f1facab4cf9c1d",
    )

    grade_tests = ProspectiveGradeTests()
    grade_tests.setUp()
    receipt = pgo_prospective.grade_locked_games(grade_tests.lock, grade_tests.results)
    receipt_text, rows_text = pgo_prospective.serialize_grade(receipt, receipt["rows"])
    self.assertEqual(_sha256(receipt_text), "10dfebd8f68d8327a533d373f79f1677a1b966f7dc7c995afe7b34c0fcaeeb26")
    self.assertEqual(_sha256(rows_text), "155ec3456adcd45dc9e05c1ddf4d92a45c3e07da1e5f93a950bc43417c6a5c41")
```

Run this test alone and require it to pass before adding candidate code:

```powershell
python -m unittest tests.test_pgo_prospective.ProspectiveSchemaOneRegressionTests -v
```

- [ ] **Step 2: Add red development-contract tests**

Add `ProspectiveBlendDevelopmentTests` with these cases:

1. Load the tracked validation CSV and assert exact source hash
   `b697b6f8f5eee9ae1efe607272458964a681f99f440a94f86d8edce2ad5a19b7`,
   2,127 unique games, and seasons 2018 through 2025.
2. Produce 21 grid rows, select `0.25`, identify `0.30` as the first
   regressing weight, and reproduce the approved metrics.
3. Serialize twice and assert identical bytes.
4. Reject a changed header, duplicate `game_id`, missing row, wrong season,
   malformed boolean, non-finite value, changed source hash, and rehashed or
   unrehashed receipt tampering.

Use these exact assertions for the approved result:

```python
source = pgo_prospective.load_development_predictions(
    "research/pgo_v1/validation_predictions.csv"
)
receipt = pgo_prospective.develop_stability_blend(source)
self.assertEqual(receipt["status"], "DEVELOPMENT_ONLY")
self.assertEqual(receipt["candidate"]["kind"], "fixed_convex_stability_blend")
self.assertEqual(receipt["selection"]["selected_pgo_v1_weight"], 0.25)
self.assertEqual(receipt["selection"]["first_regressing_weight"], 0.30)
self.assertEqual(len(receipt["grid_results"]), 21)
self.assertAlmostEqual(receipt["metrics"]["candidate_mae"], 10.227241, places=6)
self.assertAlmostEqual(receipt["metrics"]["pgo_v0_mae"], 10.266150, places=6)
self.assertAlmostEqual(receipt["aggregate_interval"]["lower"], 0.017797, places=6)
self.assertAlmostEqual(receipt["aggregate_interval"]["upper"], 0.060136, places=6)
self.assertTrue(all(row["improvement"] > 0.0 for row in receipt["season_results"]))
```

Run the new class and confirm RED only because the new interfaces do not exist:

```powershell
python -m unittest tests.test_pgo_prospective.ProspectiveBlendDevelopmentTests -v
```

- [ ] **Step 3: Add only the fixed constants and strict CSV loader**

Add these constants beside `PREDICTION_COLUMNS`:

```python
BLEND_KIND = "fixed_convex_stability_blend"
BLEND_FORMULA = "0.75*pgo_v0_prediction+0.25*challenger_prediction"
BLEND_WEIGHT = 0.25
BLEND_GRID = tuple(index / 20 for index in range(21))
DEVELOPMENT_SOURCE_SHA256 = "b697b6f8f5eee9ae1efe607272458964a681f99f440a94f86d8edce2ad5a19b7"
DEVELOPMENT_GAME_COUNT = 2_127
DEVELOPMENT_SEASONS = tuple(range(2018, 2026))
DEVELOPMENT_COLUMNS = (
    "game_id", "season", "week", "kickoff", "actual_margin",
    "pgo_v0_prediction", "challenger_prediction", "changed_or_backup_qb",
    "major_availability_loss", "head_coach_change", "high_roster_turnover",
    "weeks_1_4", "weeks_5_18", "half_life_games", "alpha", "delta",
)
```

`load_development_predictions` must hash the exact bytes, require the exact
ordered header, normalize numeric values, accept only literal `true`/`false`
flags, reject duplicate IDs before returning, and never mutate the source file.
`develop_stability_blend` then requires the fixed source hash, count, and exact
season set.

- [ ] **Step 4: Implement the fixed grid and self-hashing receipt**

Use one numeric helper everywhere the blend is calculated:

```python
def _blend_prediction(pgo_v0, challenger, weight=BLEND_WEIGHT):
    return (1.0 - weight) * float(pgo_v0) + weight * float(challenger)


def _comparison_rows(rows, incumbent_key, candidate_key):
    return [
        {
            **row,
            "pgo_v0_prediction": row[incumbent_key],
            "challenger_prediction": row[candidate_key],
        }
        for row in rows
    ]
```

For each grid weight, add `candidate_prediction` to copied rows, use
`pgo_challenger.metric_summary`, and calculate per-season MAE improvement.
Select the maximum weight for which every seasonal improvement is strictly
greater than zero. Add the small two-key adapter shown in Task 3 now because it
is reused by both development and grading. For the selected rows, reuse the
existing paired block bootstrap without changing its implementation:

```python
comparison = _comparison_rows(
    selected_rows, "pgo_v0_prediction", "candidate_prediction"
)
interval = pgo_challenger.paired_block_bootstrap(
    comparison, samples=10_000, seed=20260721
)
```

The receipt must contain only deterministic values:

```text
schema_version, status, candidate, source_sha256, counts, seasons,
selection, metrics, aggregate_interval, season_results, grid_results,
artifact_sha256
```

Set `status` to `DEVELOPMENT_ONLY`; do not emit `PASS` or a publication status.
Reuse `_artifact_hash` and `_canonical`. `_verify_development_receipt` must
require schema 1, the exact status/kind/source hash/count/seasons/weight,
finite reported metrics, and a matching artifact hash.
It must also recompute the selected weight from `grid_results` and require the
top-level selected metrics and season rows to match that selected grid row, so
changing a value and merely recomputing the outer hash still fails.

- [ ] **Step 5: Add `develop-blend` CLI wiring and generate the tracked receipt**

Add this parser without changing the existing `lock` or `grade` arguments:

```python
develop = subparsers.add_parser("develop-blend")
develop.add_argument("--predictions", type=Path, required=True)
develop.add_argument("--output", type=Path, required=True)
```

Run:

```powershell
python -m unittest tests.test_pgo_prospective.ProspectiveBlendDevelopmentTests -v
python pgo_prospective.py develop-blend --predictions research/pgo_v1/validation_predictions.csv --output research/pgo_stability_blend/development.json
python -m unittest tests.test_pgo_prospective.ProspectiveSchemaOneRegressionTests -v
python -m py_compile pgo_prospective.py tests/test_pgo_prospective.py
git diff --check
```

Inspect the receipt with an executable assertion, not visual rounding:

```powershell
@'
import json
from pathlib import Path
import pgo_prospective
r = json.loads(Path("research/pgo_stability_blend/development.json").read_text(encoding="utf-8"))
pgo_prospective._verify_development_receipt(r)
assert r["selection"]["selected_pgo_v1_weight"] == 0.25
assert r["selection"]["first_regressing_weight"] == 0.30
assert len(r["grid_results"]) == 21
assert all(row["improvement"] > 0 for row in r["season_results"])
'@ | python -
```

Commit only the three exact paths:

```powershell
git add pgo_prospective.py tests/test_pgo_prospective.py research/pgo_stability_blend/development.json
git commit -m "feat: freeze PGO stability blend development evidence"
```

---

### Task 2: Derive a schema-2 lock and external attestation without touching the base

**Files:**

- Modify: `tests/test_pgo_prospective.py:25-167, 282-311`
- Modify: `pgo_prospective.py:273-355, 821-864`
- Read only: `prospective_evidence/2026-07-21/prospective_lock.json`
- Read only: `prospective_evidence/2026-07-21/prospective_predictions.csv`

**Interfaces:**

- `_prediction_integrity_hash(games, include_candidate=False) -> str`
- `derive_stability_blend(base_lock, development_receipt, development_file_sha256, as_of) -> dict`
- `_base_lock_from_derived(derived_lock) -> dict`
- `build_prospective_attestation(base_lock, base_lock_bytes, base_prediction_bytes, derived_lock, derived_lock_bytes, derived_prediction_bytes, development_receipt_bytes) -> dict`
- `_verify_prospective_attestation(attestation) -> dict`
- `_cli_derive_blend(args) -> int`

- [ ] **Step 1: Add red derivation and no-overwrite tests**

Add `ProspectiveBlendLockTests` using the existing two-game lock and the tracked
development receipt. Assert candidate predictions are exactly `3.5` and
`-6.75`, the input lock object is unchanged, and reconstruction returns the
original schema-1 object exactly.

Cover all fail-closed cases:

- schema-1 lock with a top-level or game-level candidate field;
- wrong schema or candidate discriminator;
- altered base prediction, base artifact hash, or base prediction hash;
- development receipt with a bad artifact, source hash, kind, or weight;
- candidate timestamp equal to or after a kickoff;
- candidate prediction or weight tampering, including recomputed outer hashes;
- an already-existing output directory or attestation path;
- a base prediction CSV whose bytes differ from `_prediction_csv(base_lock)`.

The core success assertion is:

```python
derived = pgo_prospective.derive_stability_blend(
    self.base_lock,
    self.development_receipt,
    self.development_file_sha256,
    "2026-08-21T12:00:00-04:00",
)
self.assertEqual(derived["schema_version"], 2)
self.assertEqual(
    [game["candidate_prediction"] for game in derived["games"]],
    [3.5, -6.75],
)
self.assertEqual(pgo_prospective._base_lock_from_derived(derived), self.base_lock)
self.assertEqual(self.base_lock, self.original_base_lock)
```

Run and confirm RED:

```powershell
python -m unittest tests.test_pgo_prospective.ProspectiveBlendLockTests -v
```

- [ ] **Step 2: Make prediction hashes schema-explicit and preserve the default**

Change `_prediction_integrity_hash` only by adding an opt-in parameter. The
default key tuple must remain byte-for-byte identical:

```python
def _prediction_integrity_hash(games, include_candidate=False):
    keys = (
        "game_id", "pgo_v0_prediction", "challenger_prediction",
        "challenger_full_strength_prediction", "subgroup_flags",
    )
    if include_candidate:
        keys += ("candidate_prediction",)
    return hashlib.sha256(_canonical([
        {key: game[key] for key in keys} for game in games
    ]).encode("utf-8")).hexdigest()
```

Update `_prediction_csv` similarly: use `PREDICTION_COLUMNS` for schema 1 and
`PREDICTION_COLUMNS + ("candidate_prediction",)` only when both schema 2 and
the exact candidate discriminator are present. Never infer the schema from a
game field.

- [ ] **Step 3: Implement explicit schema-2 derivation and verification**

Keep top-level `as_of` as the original July lock timestamp; store the new
boundary only at `candidate.as_of`. Deep-copy the verified base lock, then add:

```python
derived["schema_version"] = 2
derived["base_lock_artifact_sha256"] = base_lock["artifact_sha256"]
derived["base_prediction_integrity_sha256"] = base_lock["prediction_integrity_sha256"]
derived["candidate"] = {
    "kind": BLEND_KIND,
    "as_of": _timestamp(as_of),
    "pgo_v0_weight": 0.75,
    "pgo_v1_weight": BLEND_WEIGHT,
    "formula": BLEND_FORMULA,
    "development_receipt_sha256": development_file_sha256,
}
```

Add each candidate prediction with `_blend_prediction`, compute the candidate
prediction hash with `include_candidate=True`, then recompute the derived
artifact hash.

Extend `_verify_lock` with explicit branches:

- schema 1: retain current checks and reject any candidate fields;
- schema 2 with exact kind: validate fixed weights/formula/time, reconstruct
  schema 1 with `_base_lock_from_derived`, recursively validate that base,
  compare both saved base hashes, recompute every candidate prediction, then
  verify the candidate prediction and artifact hashes;
- anything else: reject.

Do not reorder or refactor the schema-1 receipt construction or serializers.

- [ ] **Step 4: Add deterministic attestation construction**

`build_prospective_attestation` receives exact input/output bytes and emits:

```json
{
  "schema_version": 1,
  "status": "LOCKED",
  "candidate": {
    "kind": "fixed_convex_stability_blend",
    "as_of": "the schema-2 candidate timestamp"
  },
  "earliest_kickoff": "the earliest locked kickoff",
  "development_receipt_file_sha256": "sha256 of exact receipt bytes",
  "base": {
    "lock_artifact_sha256": "schema-1 artifact hash",
    "lock_file_sha256": "sha256 of exact base JSON bytes",
    "prediction_integrity_sha256": "schema-1 prediction hash",
    "predictions_file_sha256": "sha256 of exact base CSV bytes"
  },
  "derived": {
    "lock_artifact_sha256": "schema-2 artifact hash",
    "lock_file_sha256": "sha256 of exact derived JSON bytes",
    "prediction_integrity_sha256": "schema-2 prediction hash",
    "predictions_file_sha256": "sha256 of exact derived CSV bytes"
  },
  "artifact_sha256": "canonical self-hash"
}
```

`_verify_prospective_attestation` validates schema/status/kind, timezone-bearing
timestamps, the candidate-before-kickoff boundary, 64-character lowercase hex
hashes, and the attestation artifact hash.

- [ ] **Step 5: Add `derive-blend` CLI with all-target preflight**

Add exactly these arguments:

```python
derive = subparsers.add_parser("derive-blend")
derive.add_argument("--base-lock", type=Path, required=True)
derive.add_argument("--base-predictions", type=Path, required=True)
derive.add_argument("--development-receipt", type=Path, required=True)
derive.add_argument("--as-of", required=True)
derive.add_argument("--output-dir", type=Path, required=True)
derive.add_argument("--attestation-output", type=Path, required=True)
```

Before any write, require that `output_dir` and `attestation_output` do not
exist. Read and hash the exact three input files; require the base prediction
bytes to equal `_prediction_csv(base_lock).encode("utf-8")`. Build the derived
JSON, derived CSV, and attestation fully in memory. Then atomically write the
two files in the new derived directory and the single tracked attestation.
No path is inferred and no existing path is replaced.

- [ ] **Step 6: Run focused tests and commit**

```powershell
python -m unittest tests.test_pgo_prospective.ProspectiveBlendLockTests -v
python -m unittest tests.test_pgo_prospective.ProspectiveSchemaOneRegressionTests -v
python -m py_compile pgo_prospective.py tests/test_pgo_prospective.py
git diff --check
git add pgo_prospective.py tests/test_pgo_prospective.py
git commit -m "feat: add immutable PGO stability blend lock"
```

Do not generate the real derived lock or stage an attestation in this task.

---

### Task 3: Grade the candidate while leaving base grading byte-identical

**Files:**

- Modify: `tests/test_pgo_prospective.py:168-280`
- Modify: `pgo_prospective.py:317-587`

**Interfaces:**

- Reuse `_comparison_rows(rows, incumbent_key, candidate_key)` from Task 1
- `grade_locked_games(lock, results) -> dict` with an explicit schema-2 branch
- `serialize_grade(receipt, rows) -> tuple[str, str]` with conditional columns
- `_blocked_receipt(lock, results_path, error) -> dict` with an explicit schema-2 branch

- [ ] **Step 1: Add red schema-2 grading tests**

Add `ProspectiveBlendGradeTests` and assert the two-game candidate has:

```python
self.assertAlmostEqual(receipt["metrics"]["pgo_v0_mae"], 2.5)
self.assertAlmostEqual(receipt["metrics"]["challenger_mae"], 1.0)
self.assertAlmostEqual(receipt["metrics"]["candidate_mae"], 1.625)
self.assertEqual(receipt["status"], "PASS")
self.assertEqual(receipt["publication_status"], "VALIDATED")
self.assertEqual(receipt["bootstrap"]["samples"], 10_000)
self.assertEqual(receipt["bootstrap"]["seed"], 20260721)
self.assertIn("candidate_vs_challenger_interval", receipt)
```

Also test:

- candidate `HOLD` when v0 is perfect;
- candidate `BLOCKED` CLI receipt for a missing result, explicit
  cancelled/forfeited status, or changed kickoff;
- candidate prediction/hash/formula tampering;
- deterministic candidate JSON and CSV;
- schema-1 regression digests remain the four Task 1 values.

Run and confirm RED:

```powershell
python -m unittest tests.test_pgo_prospective.ProspectiveBlendGradeTests -v
```

- [ ] **Step 2: Reuse existing statistical helpers through the two-key adapter**

Do not change `pgo_challenger.py`. Task 1 added the adapter from copied rows to
the two fixed names its helpers already consume.

For the primary candidate comparison, call the existing bootstrap and subgroup
functions on `_comparison_rows(rows, "pgo_v0_prediction", "candidate_prediction")`.
For the secondary interval, compare
`"challenger_prediction"` against `"candidate_prediction"` the same way.

- [ ] **Step 3: Add only the explicit candidate grade branch**

Retain the current schema-1 code path and key order. For schema 2, add to each
row:

```text
candidate_absolute_error
candidate_improvement_vs_pgo_v0
candidate_improvement_vs_challenger
```

Return schema 2 with all three MAE summaries, primary `bootstrap` and
`aggregate_interval` for candidate versus v0, secondary
`candidate_vs_challenger_interval`, candidate-versus-v0 subgroup results, and
these checks:

```text
lock_artifact_integrity
result_integrity
counts_match
candidate_mae_lower
aggregate_improvement_ci_positive
no_sufficient_subgroup_regression
```

Use the current classification rule unchanged: failed integrity is `BLOCKED`;
passing integrity with any failed statistical check is `HOLD`; every check true
is `PASS`. A `PASS` describes only this candidate.

Treat explicit result statuses `CANCELLED`, `CANCELED`, `FORFEIT`, `FORFEITED`,
or `POSTPONED` as candidate integrity failures. Missing results and changed
kickoffs already fail through the existing exact-population checks. Do not
change schema-1 result handling.

Change the script entry point to `raise SystemExit(main())` so the CLI's
existing `PASS = 0`, `HOLD/BLOCKED = 1` contract reaches the operating system.
Add `main(argv)` assertions using complete `grade --lock-file --results-path
--output-dir` argument lists for each status; do not alter `_cli_grade`'s
schema-1 receipt bytes.

- [ ] **Step 4: Serialize candidate-only columns conditionally**

Keep `GRADE_RESULT_COLUMNS` unchanged. For a valid schema-2 receipt, append the
three candidate result columns; otherwise use the original tuple exactly.
Likewise, `_blocked_receipt` must return the original schema-1 dictionary
unchanged unless the lock explicitly identifies the schema-2 blend.

- [ ] **Step 5: Run focused and protected tests, then commit**

```powershell
python -m unittest tests.test_pgo_prospective.ProspectiveBlendGradeTests -v
python -m unittest tests.test_pgo_prospective.ProspectiveSchemaOneRegressionTests -v
python -m unittest tests.test_pgo_prospective -v
python -m unittest tests.test_pgo_challenger tests.test_pgo_comparison -v
python -m py_compile pgo_prospective.py tests/test_pgo_prospective.py
git diff --check
git add pgo_prospective.py tests/test_pgo_prospective.py
git commit -m "feat: grade PGO stability blend prospectively"
```

---

### Task 4: Generate the real derived evidence and inspect every linkage

**Files:**

- Create locally, never stage: `prospective_evidence/2026-08-26-stability-blend/prospective_lock.json`
- Create locally, never stage: `prospective_evidence/2026-08-26-stability-blend/prospective_predictions.csv`
- Create, stage later: `research/pgo_stability_blend/prospective_attestation.json`
- Read only: `prospective_evidence/2026-07-21/*`

- [ ] **Step 1: Verify the exact July evidence before derivation**

```powershell
if ((Get-FileHash -Algorithm SHA256 prospective_evidence/2026-07-21/prospective_lock.json).Hash.ToLowerInvariant() -ne "fe15fe1d576d9b024acaa89c78544194dd3ce4d1b35b6bce63f93b6d647ce672") { throw "July lock file changed" }
if ((Get-FileHash -Algorithm SHA256 prospective_evidence/2026-07-21/prospective_predictions.csv).Hash.ToLowerInvariant() -ne "59d75811f3194a840b5d8070272aacb1ab6b6c8f5f1679580c6fba9712ca0186") { throw "July prediction file changed" }
if ((Get-FileHash -Algorithm SHA256 research/pgo_v1/validation_predictions.csv).Hash.ToLowerInvariant() -ne "b697b6f8f5eee9ae1efe607272458964a681f99f440a94f86d8edce2ad5a19b7") { throw "Development source changed" }
@'
import json
from pathlib import Path
import pgo_prospective
lock = json.loads(Path("prospective_evidence/2026-07-21/prospective_lock.json").read_text(encoding="utf-8"))
pgo_prospective._verify_lock(lock)
assert lock["schema_version"] == 1
assert lock["artifact_sha256"] == "f5b63437342c0ba0b6b6dc4cb4a1e5ff8950ba221ffbb3972244165ba4a1ba3f"
assert lock["prediction_integrity_sha256"] == "2fb18fbe6ccd062149854c97b781b5e2ba7bbc5b09f8ea4a545d23afc856b821"
assert len(lock["games"]) == 272
'@ | python -
```

Stop immediately on any mismatch.

- [ ] **Step 2: Confirm every target is absent and derive once**

```powershell
$derivedDir = "prospective_evidence/2026-08-26-stability-blend"
$attestationPath = "research/pgo_stability_blend/prospective_attestation.json"
if (Test-Path -LiteralPath $derivedDir) { throw "Derived directory already exists" }
if (Test-Path -LiteralPath $attestationPath) { throw "Attestation already exists" }
$blendAsOf = [DateTimeOffset]::Now.ToString("yyyy-MM-ddTHH:mm:sszzz")
python pgo_prospective.py derive-blend --base-lock prospective_evidence/2026-07-21/prospective_lock.json --base-predictions prospective_evidence/2026-07-21/prospective_predictions.csv --development-receipt research/pgo_stability_blend/development.json --as-of $blendAsOf --output-dir $derivedDir --attestation-output $attestationPath
if ($LASTEXITCODE -ne 0) { throw "Blend derivation failed" }
```

Do not delete and retry if a target appears. Inspect the partial state and stop.

- [ ] **Step 3: Validate hashes, formula, population, and base reconstruction**

```powershell
@'
import hashlib
import json
from pathlib import Path
import pgo_prospective

base_path = Path("prospective_evidence/2026-07-21/prospective_lock.json")
base_predictions_path = base_path.with_name("prospective_predictions.csv")
derived_path = Path("prospective_evidence/2026-08-26-stability-blend/prospective_lock.json")
derived_predictions_path = derived_path.with_name("prospective_predictions.csv")
development_path = Path("research/pgo_stability_blend/development.json")
attestation_path = Path("research/pgo_stability_blend/prospective_attestation.json")

base = json.loads(base_path.read_text(encoding="utf-8"))
derived = json.loads(derived_path.read_text(encoding="utf-8"))
attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
pgo_prospective._verify_lock(base)
pgo_prospective._verify_lock(derived)
pgo_prospective._verify_prospective_attestation(attestation)
assert pgo_prospective._base_lock_from_derived(derived) == base
assert len(derived["games"]) == 272
assert all(
    game["candidate_prediction"] == 0.75 * game["pgo_v0_prediction"] + 0.25 * game["challenger_prediction"]
    for game in derived["games"]
)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert attestation["development_receipt_file_sha256"] == sha(development_path)
assert attestation["base"]["lock_file_sha256"] == sha(base_path)
assert attestation["base"]["predictions_file_sha256"] == sha(base_predictions_path)
assert attestation["derived"]["lock_file_sha256"] == sha(derived_path)
assert attestation["derived"]["predictions_file_sha256"] == sha(derived_predictions_path)
'@ | python -
```

- [ ] **Step 4: Re-run the command only as a no-overwrite test**

Run the same `derive-blend` command again with the existing targets. Require a
nonzero exit and verify all three output hashes remain unchanged:

```powershell
$derivedDir = "prospective_evidence/2026-08-26-stability-blend"
$attestationPath = "research/pgo_stability_blend/prospective_attestation.json"
$targets = @(
    "$derivedDir/prospective_lock.json",
    "$derivedDir/prospective_predictions.csv",
    $attestationPath
)
$before = @{}
foreach ($target in $targets) { $before[$target] = (Get-FileHash -Algorithm SHA256 $target).Hash }
$blendAsOf = @'
import json
from pathlib import Path
print(json.loads(Path("prospective_evidence/2026-08-26-stability-blend/prospective_lock.json").read_text(encoding="utf-8"))["candidate"]["as_of"])
'@ | python -
python pgo_prospective.py derive-blend --base-lock prospective_evidence/2026-07-21/prospective_lock.json --base-predictions prospective_evidence/2026-07-21/prospective_predictions.csv --development-receipt research/pgo_stability_blend/development.json --as-of $blendAsOf --output-dir $derivedDir --attestation-output $attestationPath
if ($LASTEXITCODE -eq 0) { throw "Repeated derivation unexpectedly succeeded" }
foreach ($target in $targets) {
    if ((Get-FileHash -Algorithm SHA256 $target).Hash -ne $before[$target]) { throw "Existing artifact changed: $target" }
}
```

Do not remove the artifacts after this check.

---

### Task 5: Run the complete verification and review gates

**Files:**

- Modify: none unless a test exposes a root-cause defect within the four allowed implementation paths
- Inspect: all changed files and protected paths

- [ ] **Step 1: Run focused, protected, and full suites**

```powershell
python -m unittest tests.test_pgo_prospective -v
python -m unittest tests.test_pgo_challenger tests.test_pgo_comparison tests.test_pgo_injury_source -v
python -W error::ResourceWarning -m unittest discover -s tests -v
python -m py_compile pgo_prospective.py tests/test_pgo_prospective.py
git diff --check
```

Every command must exit zero. If the warning-as-error run exposes an existing
resource leak, stop and diagnose it separately; do not suppress or weaken the
gate inside this feature.

- [ ] **Step 2: Verify the protected surface and dirty baseline**

```powershell
git diff --exit-code df00b0b -- research/pgo_v1 data .github/workflows docs/index.html
git status --short
```

Expected implementation changes are limited to the two Python files and two
new `research/pgo_stability_blend` receipts. The previously untracked handoffs,
`.superpowers/`, older plans, and `prospective_evidence/` must remain untracked
and unstaged.

Repeat the three exact hash assertions from Task 4 Step 1. Also verify the
canonical backtest still says `HOLD` / `EXPERIMENTAL` and the public page still
contains `Experimental model — HOLD`.

- [ ] **Step 3: Request correctness review before release**

Use the `superpowers:requesting-code-review` skill against all changes after the
plan commit. Review specifically for:

- schema-1 byte drift;
- any outcome-dependent candidate choice;
- hash or timestamp fields that are asserted but not independently recomputed;
- candidate comparisons using unequal rows;
- overwrite or caller-path escapes;
- accidental model promotion or public-label changes.

Apply only verified findings with `superpowers:receiving-code-review`, rerun the
focused red/green test for each fix, then repeat Steps 1 and 2 in full.

---

### Task 6: Commit the attestation, push before kickoff, and smoke-test Pages

**Files:**

- Stage: `research/pgo_stability_blend/prospective_attestation.json`
- Never stage: `prospective_evidence/`
- Inspect only: GitHub Actions and the deployed Pages HTML

- [ ] **Step 1: Commit only the attestation after all gates are green**

```powershell
git add research/pgo_stability_blend/prospective_attestation.json
git diff --cached --name-only
git commit -m "chore: attest 2026 PGO stability blend"
```

The cached-name output must contain exactly the attestation path. If anything
else is staged, stop and unstage that exact unrelated path without discarding
its working-tree content.

- [ ] **Step 2: Perform one final pre-push audit**

```powershell
python -m unittest tests.test_pgo_prospective -v
python -W error::ResourceWarning -m unittest discover -s tests
git diff --check HEAD~1 HEAD
git status --short
git log --oneline --decorate -6
```

Require no tracked worktree changes and only the preserved untracked baseline,
including both prospective evidence directories under the single untracked
`prospective_evidence/` entry.

- [ ] **Step 3: Push the reviewed commits to `origin/main` before kickoff**

```powershell
$earliest = @'
import json
from pathlib import Path
print(json.loads(Path("research/pgo_stability_blend/prospective_attestation.json").read_text(encoding="utf-8"))["earliest_kickoff"])
'@ | python -
if ([DateTimeOffset]::Now -ge [DateTimeOffset]::Parse($earliest)) { throw "Earliest kickoff has passed; do not push as prospective evidence" }
git push origin main
if ($LASTEXITCODE -ne 0) { throw "Push failed" }
$localHead = git rev-parse HEAD
$remoteHead = (git ls-remote origin refs/heads/main).Split("`t")[0]
if ($localHead -ne $remoteHead) { throw "Remote main does not match local HEAD" }
```

- [ ] **Step 4: Verify GitHub publication and protected live content**

The repository's `update-board.yml` path filter does not match this code and
research-only push, so do not dispatch it manually. List any automatic Pages or
CI runs for the pushed SHA and watch the identifiers returned by this query:

```powershell
$headSha = git rev-parse HEAD
$runs = gh run list --branch main --limit 20 --json databaseId,headSha,name,status,conclusion | ConvertFrom-Json
$runs | Where-Object { $_.headSha -eq $headSha } | Format-Table databaseId,name,status,conclusion
$runs | Where-Object { $_.headSha -eq $headSha } | ForEach-Object { gh run watch $_.databaseId --exit-status }
```

Finally fetch the live page and require its protected content:

```powershell
$html = (Invoke-WebRequest -UseBasicParsing https://walshja9.github.io/Postgame_Outlet/).Content
$required = @(
    "Experimental model — HOLD",
    "2026-08-18T02:09:47-07:00",
    "2026-07-16T11:22:52-04:00",
    '<td data-sort="7.3">+7.3</td>',
    '<td data-sort="3.2">+3.2</td>',
    '<td data-sort="-0.8">-0.8</td>'
)
foreach ($value in $required) {
    if (-not $html.Contains($value)) { throw "Protected live content missing: $value" }
}
```

The only permitted public change is the generated board timestamp. Do not
touch Shopify or store files.

---

## STOP Conditions

Stop without inferring or repairing around the evidence if any of these occur:

- the development source hash, 2,127-game count, or 2018-2025 population differs;
- the fixed rule does not select exactly `0.25` or the documented metrics do not reproduce;
- either July file hash or either internal July hash differs;
- the base review CSV does not exactly serialize from the verified base lock;
- the candidate timestamp is at or after any kickoff;
- an output or attestation target already exists before the one authorized derivation;
- schema-1 serialization changes by one byte;
- candidate rows do not reconstruct the base lock exactly;
- any game/result identity, denominator, or comparison population differs;
- the full suite or warning-as-error gate fails;
- a protected PGO v1, McCabe, workflow, data, Shopify, store, or public-label artifact changes;
- unrelated untracked content would be staged;
- the attestation cannot be committed and pushed to remote `main` before kickoff.
