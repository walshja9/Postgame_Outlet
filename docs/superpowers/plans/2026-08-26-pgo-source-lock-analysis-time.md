# PGO Source-Lock and Analysis-Time Repair Plan

**Goal:** Run a later injury-availability shadow against the approved immutable July model sources without refreezing or changing full-strength ratings.

**Architecture:** Keep the existing source inventory, URL, hash, coverage, and pinned-schedule checks. Treat each lock's `frozen_at` as the source-capture time: it may equal or precede the analysis `--as-of`, but it may not be later. Record the actual lock timestamps in the source audit.

**Tech Stack:** Python standard library, `unittest`, existing PGO CLI

## Constraints

- Do not rewrite `research/pgo_v1/sources.lock.json` or the July 21 prospective lock.
- Do not fetch replacement historical inputs.
- Full-strength ratings must be numerically identical to the canonical July artifact.
- The current injury overlay remains availability-only and may not invent probabilities from editorial news.
- Keep `Experimental model — HOLD` unless an existing evidence gate genuinely passes.

### Task 1: Repair the temporal source-lock contract

**Files:**
- Modify: `pgo_challenger.py`
- Test: `tests/test_pgo_challenger.py`

- [ ] Change the existing timestamp regression to require an older lock to pass, an equal lock to pass, and a future lock to fail.
- [ ] Assert that the source audit records the actual lock timestamp.
- [ ] Run the focused test first and confirm the current equality rule fails it.
- [ ] Replace the equality check with a future-time guard and add the audit field without weakening any other preflight check.
- [ ] Run the focused test, the full suite with `ResourceWarning` promoted to errors, and `git diff --check`.

### Task 2: Prove canonical-shadow isolation

- [ ] Hash protected checked-in public, research, and prospective artifacts before the run.
- [ ] Run `pgo_challenger.py` with the canonical July lock and preserved canonical cache, the August 25 availability snapshot, and a fresh local output directory.
- [ ] Require 32 full-strength rows to match `research/pgo_v1/ratings_2026_preseason.csv` exactly by team and value.
- [ ] Require current-lineup changes to arise only from accepted availability rows; with the current zero-row overlay, require zero adjustments.
- [ ] Confirm protected artifact hashes are unchanged and the release remains honestly classified by the existing gates.

### Task 3: Integrate and verify

- [ ] Commit only this plan, `pgo_challenger.py`, and `tests/test_pgo_challenger.py`.
- [ ] Push `main`, monitor any triggered workflows, and verify the public HOLD comparison remains unchanged.
- [ ] Preserve all unrelated untracked paths and leave Shopify untouched.
