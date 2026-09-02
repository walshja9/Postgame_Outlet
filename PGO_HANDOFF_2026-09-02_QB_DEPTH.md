# Postgame Outlet QB Depth Eligibility Handoff

Status captured: September 2, 2026 (America/New_York)

## Resume location

- Worktree: `D:\CodexWorktrees\Postgame_Outlet-fantasy-qb-depth-eligibility`
- Branch: `codex/pgo-fantasy-qb-depth-eligibility`
- Saved Task 2 code checkpoint: `268a8f3aee3f4e4dccf796da5e74ba80cab17a7b`
- Governing design: `docs/superpowers/specs/2026-09-02-pgo-fantasy-qb-depth-eligibility-design.md`
- Governing plan: `docs/superpowers/plans/2026-09-02-pgo-fantasy-qb-depth-eligibility.md`
- SDD state: `D:\Claude Context\Postgame_Outlet\.git\worktrees\Postgame_Outlet-fantasy-qb-depth-eligibility\sdd`

The worktree had no running Python process when this handoff was written. The project is saved in local Git commits. Nothing was pushed or deployed.

## Product and model decision

PGO remains fantasy/model first and store second. For the first Standard and Superflex slice:

- Keep every QB projection visible.
- Rank only one current non-inactive QB per team.
- Select the eligible QB by the lowest frozen depth rank.
- If QB1 is inactive, promote the next depth-ranked non-inactive QB.
- If every QB for a team is inactive, fail closed.
- Roster data remains identity, team, and position authority.
- RB, WR, and TE behavior and frozen v1 projection math remain unchanged.
- The team model remains `Experimental model — HOLD`.

The season opener is September 9, 2026. Real evidence capture and the append-only T-60 lock are later operational gates, not part of this implementation checkpoint.

## Completed and approved

Task 1 is complete and independently approved.

- `a0cc628c0e34ce60611b8816c9ef82da075834e6` — frozen depth parsing, canonicalization, v2 epoch, CLI input, and receipt coverage.
- `b25bd68719247101742072376760ea214681603a` — shared reconstruction validation for exact depth source identity and required `source_as_of`.
- Focused boundary/CLI gate: 30/30 passed.
- Full prospective module after the review fix: 82/82 passed.
- Independent Task 1 verdict: APPROVED, with no remaining finding.

## Task 2 saved state — not complete

Task 2 changes are saved in `268a8f3aee3f4e4dccf796da5e74ba80cab17a7b` and touch only:

- `pgo_fantasy_prospective.py`
- `tests/test_pgo_fantasy_prospective.py`

Implemented so far:

- `qb_depth_rank` is bound into locked prediction rows.
- A shared QB starter-selection path chooses one eligible non-inactive QB per team.
- All QB projection rows remain present.
- Backup QBs are excluded from Standard QB ranks and Superflex unless promoted.
- All-inactive QB rooms fail closed.
- Lock validation reconstructs the same QB eligibility semantics.
- Weekly synthetic tests now use the approved 12-game, 24-team shape.

TDD evidence captured before the reboot checkpoint:

- RED: backup QBs were incorrectly ranked.
- RED: an all-inactive QB room did not fail.
- RED: lock reconstruction still treated `buf-qb2` as eligible.
- GREEN: two focused projection tests, 2/2.
- GREEN: focused lock reconstruction/tamper test, 1/1.
- GREEN: combined `ProspectiveProjectionTests` plus `ProspectiveGameLockTests`, 28/28.
- `py_compile` passed after the long run was stopped.
- `git diff --check` passed before the checkpoint commit.

Still required before Task 2 can be called complete:

1. Run the WeekGrade and SeasonGrade classes. The prior attempt was interrupted for the reboot before a result was recorded.
2. Run the complete prospective module.
3. Fix any failure with focused RED/GREEN evidence.
4. Perform diff, scope, protected-path, and self-review gates.
5. Add a normal Task 2 completion commit after the WIP checkpoint; do not rewrite or hide the checkpoint.
6. Write `sdd/task-2-report.md` and obtain an independent Task 2 review before starting Task 3.

Required commands, run sequentially from the worktree:

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveProjectionTests `
  tests.test_pgo_fantasy_prospective.ProspectiveGameLockTests -v

python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveWeekGradeTests `
  tests.test_pgo_fantasy_prospective.ProspectiveSeasonGradeTests -v

python -B -W error::ResourceWarning -m unittest tests.test_pgo_fantasy_prospective -v
```

Use a timeout of at least 10 minutes for the WeekGrade/SeasonGrade and complete-module commands. Do not run mutable-file tests concurrently.

## Remaining plan

After Task 2 passes independent review:

1. Execute Task 3 from the governing plan: evidence, chronology, CLI, and regression boundaries.
2. Run the full warning-as-error repository suite and protected-path verification.
3. Obtain independent correctness and scientific/leakage reviews.
4. Write the final dated engineering handoff.
5. Integrate locally only after the branch is green and reviewed.

## Hard boundaries

Until separately authorized, do not:

- fetch or freeze a real depth provider source;
- create a real preview or T-60 lock;
- alter the July prospective lock or protected historical evidence;
- remove `Experimental model — HOLD`;
- modify the public site or store;
- push, publish, or deploy.

## Reboot resume check

```powershell
Set-Location 'D:\CodexWorktrees\Postgame_Outlet-fantasy-qb-depth-eligibility'
git status --short
git log --oneline -6
Get-Content -Raw .\PGO_HANDOFF_2026-09-02_QB_DEPTH.md
```

Expected: clean worktree and this branch at or after the handoff commit that follows code checkpoint `268a8f3`.
