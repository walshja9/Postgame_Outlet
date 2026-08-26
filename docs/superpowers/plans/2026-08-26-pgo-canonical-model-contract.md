# PGO Canonical Model Contract Repair Plan

**Goal:** Make the default `pgo_v1` code reproduce its locked July receipt before applying later availability evidence.

**Evidence:** With identical source hashes, current defaults selected `delta=0.75`, added three fragility features, produced MAE `10.213847`, and moved all 32 full-strength ratings. A read-only counterfactual using the original grid and feature manifest reproduced MAE `10.2051728553`, parameters `4/100/1`, and every published rating at six-decimal precision.

**Architecture:** Restore the original validated parameter grid and default feature manifest. Remove the failed fragility candidate from the authoritative path; retain the experiment in Git history. Keep the learned role estimator confined to current-lineup overlays.

## Constraints

- Do not change the source lock, July research receipts, prospective evidence, public page, or checked-in availability overlay.
- Do not weaken HOLD/PASS, leakage, coverage, hash, or determinism gates.
- Do not add a second runtime mode or dependency for an unpromoted experiment.

### Task 1: Lock the canonical defaults

- [ ] Change the grid regression to require half-lives `(4, 8, 16)`, alphas `(1.0, 10.0, 100.0)`, and deltas `(1.0, 1.5)`.
- [ ] Change the feature-manifest regression to exclude the three unpromoted fragility fields.
- [ ] Run both tests and confirm they fail against current defaults.
- [ ] Restore the grid and remove the fragility fields/helpers and their isolated candidate tests.
- [ ] Run focused and full repository verification.

### Task 2: Repeat the canonical injury shadow

- [ ] Run the August 25 zero-row availability overlay against the canonical July lock/cache.
- [ ] Require serialized full-strength ratings to match all 32 canonical CSV values exactly.
- [ ] Require zero availability adjustments, canonical MAE/parameters, HOLD/EXPERIMENTAL status, and unchanged protected hashes.

### Task 3: Integrate safely

- [ ] Commit only the two implementation/test files and this plan.
- [ ] Push `main`, monitor triggered workflows, and smoke-test the protected public page.
- [ ] Leave Shopify and unrelated untracked paths untouched.
