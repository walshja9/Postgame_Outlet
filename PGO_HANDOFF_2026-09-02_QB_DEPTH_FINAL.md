# Postgame Outlet QB Depth Eligibility — Final Engineering Handoff

Status captured: September 2, 2026 (America/New_York)

This handoff supersedes `PGO_HANDOFF_2026-09-02_QB_DEPTH.md` for resume state.
The earlier file remains unchanged as historical reboot evidence.

## Final local state

- Worktree: `D:\CodexWorktrees\Postgame_Outlet-fantasy-qb-depth-eligibility`
- Branch: `codex/pgo-fantasy-qb-depth-eligibility`
- Verified code commit: `ef8714a4fe1d04eebac961cda9c24920f67adbd7`
- Governing design: `docs/superpowers/specs/2026-09-02-pgo-fantasy-qb-depth-eligibility-design.md`
- Governing plan: `docs/superpowers/plans/2026-09-02-pgo-fantasy-qb-depth-eligibility.md`
- Durable evidence: `D:\Claude Context\Postgame_Outlet\.git\worktrees\Postgame_Outlet-fantasy-qb-depth-eligibility\sdd`

The final handoff commit is a documentation-only descendant of the verified
code commit. Resolve it with `git rev-parse HEAD` after checkout.

## Delivered behavior

- Every current-roster QB remains projected and visible.
- Exactly one non-inactive QB per required team is rank eligible: the QB with
  the lowest positive frozen depth rank.
- A verified inactive QB1 is zeroed and promotes the next depth-ranked QB.
- A team with no remaining QB candidate fails closed.
- RB, WR, and TE projections, eligibility, FLEX behavior, and frozen point
  formulas are unchanged.
- Preview depth may be captured through preview `generated_at`; lock evidence
  retains T-60 enforcement.
- Lock verification requires predictions for both required teams.
- Availability cannot move a known GSIS identity across roster teams.
- FINAL results must be finalized after kickoff and carry an authoritative
  kickoff matching the lock. A postponed game therefore preserves its old lock
  ungraded and requires a new T-60 lock.
- v1 and v2 evidence remain isolated, and exact source/lock/result bytes remain
  bound through grading and season reconstruction.

## Commit lineage

- `a0cc628c0e34ce60611b8816c9ef82da075834e6` — validate prospective QB depth.
- `b25bd68719247101742072376760ea214681603a` — verify embedded depth receipts.
- `268a8f3aee3f4e4dccf796da5e74ba80cab17a7b` — preserved Task 2 WIP checkpoint.
- `aeed3f68ae4d8c4f3984f0bd49481cb331906772` — preserved reboot handoff.
- `3db44e00d34413e8afbae98db4a847b87a6d3113` — Task 2 completion checkpoint.
- `23414aa4ed5dcf6672d449e82300db7b0cf45498` — Task 3 evidence regressions.
- `0af6d2a5707d9140d3d307ea54bebdfdd857cebe` — close four final-review gaps.
- `ef8714a4fe1d04eebac961cda9c24920f67adbd7` — bind official results to locked kickoff.

## Accepted verification

All commands used Python 3.14 with warning-as-error coverage where specified.

| Gate | Result | Test time | Captured duration |
|---|---:|---:|---:|
| Focused five-fix regression set | 16/16, exit 0 | 1.208s | 1.757s |
| Prospective module | 94/94, exit 0 | 324.309s | 324.681s |
| Related fantasy/challenger/comparison/prospective modules | 234/234, exit 0 | 21.352s | 21.814s |
| Full repository discovery | 388/388, exit 0 | 348.198s | 348.668s |
| `py_compile` | exit 0 | — | — |
| Diff/whitespace/protected-scope checks | exit 0 | — | — |

Accepted durable logs:

- `accepted-prospective-20260902T172613989.*`
- `final-related-20260902T171903907.*`
- `final-discover-20260902T171939700.*`

The protected diff from design commit
`62c149959f93ec652d7a2dd1ee9450fe8e5c772c` was empty for `data`, `research`,
`docs/index.html`, `.github`, and `SHOPIFY.md`. The public page still contains
`Experimental model — HOLD`.

## Independent reviews

- Correctness: no remaining critical, important, or minor finding; static
  approval at `ef8714a`.
- Leakage: **CLEAN** for the code contract and approved for local integration.
- Live operational qualification: **NOT READY / REVIEW REQUIRED**.

Review records under the durable evidence directory:

- `final-correctness-review-ef8714a.md`
- `final-leakage-review-ef8714a.md`

## Preserved rejected evidence

Do not cite these as verification:

- `final-prospective-20260902T171549124.*` — launcher failed before a suite ran.
- `final-prospective-20260902T171321553.*` — began before `ef8714a`, loaded only
  93 tests, and overlapped another run.
- `final-prospective-20260902T171620313.*` — later duplicate deliberately
  terminated; no successful exit artifact.

They remain preserved so failed and superseded provenance is explicit.

## Operational stop gate

No real provider source was fetched or frozen. No real preview, lock, result,
grade, or promoted model artifact was created. Nothing was pushed, published,
deployed, or merged to `main`.

The separately authorized opening-night phase must use fresh provider bytes,
recheck all current roster QBs, obtain complete definitive inactive coverage,
and use new append-only output paths before the September 9, 2026 7:20 PM
Eastern T-60 deadline. Its result importer must source revision-aware kickoff
independently from the lock. Missing evidence means `BLOCKED`, never fallback.

The model remains **EXPERIMENTAL — HOLD**.
