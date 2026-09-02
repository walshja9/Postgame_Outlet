# Postgame Outlet QB Depth Eligibility — Final Engineering Handoff

Status captured: September 2, 2026 (America/New_York)

This handoff supersedes `PGO_HANDOFF_2026-09-02_QB_DEPTH.md` for resume state.
The earlier file remains unchanged as historical reboot evidence.

## Final local state

- Worktree: `D:\CodexWorktrees\Postgame_Outlet-fantasy-qb-depth-eligibility`
- Branch: `codex/pgo-fantasy-qb-depth-eligibility`
- Verified code commit: `5c9ca270f2c77e842a58092f91809bc270439c96`
- Governing design: `docs/superpowers/specs/2026-09-02-pgo-fantasy-qb-depth-eligibility-design.md`
- Governing plan: `docs/superpowers/plans/2026-09-02-pgo-fantasy-qb-depth-eligibility.md`
- Durable evidence: `D:\Claude Context\Postgame_Outlet\.git\worktrees\Postgame_Outlet-fantasy-qb-depth-eligibility\sdd`

The commit carrying this corrected handoff is a documentation-only descendant
of the verified code commit. Resolve it with `git rev-parse HEAD` after checkout.

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
- Result schema-v1 game rows remain exactly `game_id`, `status`, and
  `finalized_at`. Weekly grading joins each unique FINAL game by exact `game_id`
  and requires `finalized_at` to be strictly after the verified lock kickoff.
- Schedule revisions and postponements remain a separate operational
  qualification gate; result schema v1 does not serialize kickoff.
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
- `ef8714a4fe1d04eebac961cda9c24920f67adbd7` — superseded intermediate result-kickoff schema change.
- `241940ba29ef16ee8a0640cdbd9013373f636138` — first final handoff, superseded by this correction.
- `5c9ca270f2c77e842a58092f91809bc270439c96` — preserve result schema v1 while retaining strict lock-owned finalization chronology.

## Accepted verification

All commands used Python 3.14 with warning-as-error coverage where specified.

| Gate | Result | Test time | Captured duration |
|---|---:|---:|---:|
| Focused final invariant set | 16/16, exit 0 | 1.200s | 1.7s controller wall |
| Prospective module | 94/94, exit 0 | 323.860s | 324.244s |
| Related fantasy/challenger/comparison/prospective modules | 234/234, exit 0 | 21.072s | 21.526s |
| Full repository discovery | 388/388, exit 0 | 343.862s | 344.334s |
| `py_compile` | exit 0 | — | — |
| Diff/whitespace/protected-scope checks | exit 0 | — | — |

Accepted durable logs:

- `final3-prospective-20260902T174511922.*`
- `final3-related-20260902T175049575.*`
- `final3-discover-20260902T175134758.*`
- `schema-v1-fix-report.md` and `final-controller-verification-5c9ca27.md`

The protected diff from design commit
`62c149959f93ec652d7a2dd1ee9450fe8e5c772c` was empty for `data`, `research`,
`docs/index.html`, `.github`, and `SHOPIFY.md`. The public page still contains
`Experimental model — HOLD`.

## Independent reviews

- Correctness: no remaining critical, important, or minor code finding; ready
  for local integration at `5c9ca27`.
- Leakage: **CLEAN** for the code/scientific contract at `5c9ca27`.
- Live operational qualification: **NOT READY / REVIEW REQUIRED**.

Review records under the durable evidence directory:

- `final-correctness-review-5c9ca27.md`
- `final-leakage-review-5c9ca27.md`

The `ef8714a` review records remain preserved as superseded historical
evidence; they do not describe the final schema-v1 code.

## Preserved rejected evidence

Do not cite these as verification:

- `final-prospective-20260902T171549124.*` — launcher failed before a suite ran.
- `final-prospective-20260902T171321553.*` — began before `ef8714a`, loaded only
  93 tests, and overlapped another run.
- `final-prospective-20260902T171620313.*` — later duplicate deliberately
  terminated; no successful exit artifact.
- `accepted-prospective-20260902T172613989.*`,
  `final-related-20260902T171903907.*`, and
  `final-discover-20260902T171939700.*` — passed at superseded code commit
  `ef8714a`, then replaced by the exact-`5c9ca27` `final3-*` runs.

They remain preserved so failed and superseded provenance is explicit.

## Operational stop gate

No real provider source was fetched or frozen. No real preview, lock, result,
grade, or promoted model artifact was created. Nothing was pushed, published,
deployed, or merged to `main`.

The separately authorized opening-night phase must use fresh provider bytes,
recheck all current roster QBs, obtain complete definitive inactive coverage,
and use new append-only output paths before the September 9, 2026 7:20 PM
Eastern T-60 deadline. An independently qualified adjacent check must detect
schedule revisions or postponements and block a mismatched event while keeping
the three-field result schema v1 unchanged. Serializing kickoff requires an
explicit new schema version. Missing evidence means `BLOCKED`, never fallback.

The model remains **EXPERIMENTAL — HOLD**.
