# PGO Fantasy QB Depth Eligibility Design

**Date:** September 2, 2026

**Status:** APPROVED DESIGN — USER SELECTED OPTION 1

**Scope:** Use a frozen QB depth source to decide which current-roster QB is
eligible for Standard position ranks and Superflex ranks, without changing any
player projection.

**Release boundary:** This document authorizes only its own commit. Code,
source normalization, a new model configuration, preview regeneration, T-60
locking, site changes, push, and deployment remain separate later gates.

## 1. Decision

PGO will keep every rostered QB projection visible but rank no more than one QB
per team. The rank-eligible QB is the lowest valid depth rank among that team's
current ACT-roster QBs who are not verified inactive.

This removes known backups from fantasy ranking pools while preserving the
existing point model. It is the smallest useful correction before opening
night: no paid source, role-share model, opponent adjustment, or all-position
depth system is added.

The current roster remains authoritative for player identity, team, position,
and population. The depth source supplies only QB priority. It cannot add a
player, move a player, change a position, or change projected points.

## 2. Scientific contract

| Item | Contract |
|---|---|
| Question | At preview time or T-60, which current-roster QB on each scheduled team is eligible to enter PGO fantasy ranks? |
| Analysis type | Deterministic eligibility rule; not a new point-prediction candidate |
| Competition | 2026 NFL regular season |
| Population | ACT-roster QBs on teams in the supplied schedule; RB, WR, and TE behavior is unchanged |
| Grain | One player-game |
| Natural key | `(season, week, game_id, gsis_id)` |
| Preview time | Explicit timezone-bearing `generated_at` |
| Lock decision time | `T = scheduled kickoff - 60 minutes` |
| Baseline | Every non-inactive ACT-roster QB is rank eligible |
| Selected rule | One non-inactive QB per team: minimum positive frozen depth rank |
| Point target | Unchanged PGO half-PPR target |
| Primary evaluation | Existing 96-player prospective pool and MAE gate, under a new evidence epoch |
| Initial status | `BASELINE_ONLY / EXPERIMENTAL — HOLD` |

This rule has no separate historical performance claim. It is accepted by
source, identity, chronology, determinism, and prospective evidence gates. The
existing null-versus-strong-baseline season test remains the scientific
promotion test.

The point formula, position means, history window, half-life, pseudo-games,
primary-pool size, metrics, bootstrap, and PASS thresholds do not change.

## 3. Version boundary

Changing ranking eligibility creates a new evidence epoch under the approved
prospective initializer contract. The implementation uses model version
`pgo_fantasy_2026_baseline_v2` and a newly frozen canonical model configuration.
The configuration reuses the already accepted position-mean receipt and changes
no projection parameter.

The existing v1 Week 1 preview remains preserved, non-gradeable evidence. It is
not overwritten, relabeled, or pooled with v2 locks or grades. All 2026
gradeable locks for this track must share the v2 model/config/code/source epoch.

## 4. Frozen depth source

### 4.1 Normalized envelope

Depth is a new required local snapshot kind. It uses the existing frozen-source
envelope and receipt pattern:

- exact integer `schema_version`;
- provider artifact identity or URL plus its exact raw-source SHA-256;
- timezone-bearing `source_as_of` and `captured_at`;
- canonical, unique `teams_processed`;
- a `rows` list;
- byte count and SHA-256 in the derived receipt; and
- one immutable byte read used for both hashing and parsing.

The model performs no network fetch. Acquisition and normalization happen
before preview or lock execution. The first provider may be the nflverse 2026
depth-chart file, which is ESPN-derived; PFF is not required.

The receipt hashes the normalized model-input bytes. Its `source` identity also
binds the upstream raw artifact digest, matching the existing roster and
schedule snapshot convention; a URL without that digest is insufficient.

### 4.2 Row contract

Each normalized row contains exactly:

```json
{
  "gsis_id": "00-0000000",
  "team": "NE",
  "position": "QB",
  "depth_rank": 1
}
```

Validation requires:

- a nonempty stable GSIS ID;
- a normalized current team;
- exact position `QB`;
- an exact integer `depth_rank > 0` with booleans rejected;
- canonical row order by `(team, depth_rank, gsis_id)`;
- one row per current ACT-roster QB in the required teams;
- no extra, duplicate, or display-name-only identity;
- the same team in roster and depth sources;
- unique depth ranks within each team; and
- at least one usable QB for every required team.

For a league preview, every scheduled team is required. For a game lock, both
participating teams are required. The normalized QB identity set for those
teams must exactly equal the ACT-roster QB identity set.

Roster data wins every authority conflict. A disagreement is `BLOCKED`; depth
data never repairs or overrides roster team or position.

### 4.3 Chronology

`source_as_of` must not be later than `captured_at`. The depth capture must be no
later than preview `generated_at`, and no later than T-60 for a lock. A later
depth update may support a new append-only preview or a later game's lock, but
it cannot rewrite an earlier artifact.

## 5. Eligibility algorithm

For each game:

1. Validate schedule, roster, history, model config, depth, and—when locking—
   definitive availability from their exact frozen bytes.
2. Group current ACT-roster QBs by team.
3. Exclude only QBs whose definitive availability status is `INACTIVE`.
4. Select the remaining QB with the lowest unique `depth_rank` for each team.
5. Block if either team has no remaining QB candidate.

Prediction and ranking behavior is then:

- every QB remains in the player-game rows;
- every QB keeps the existing null and strong projection, except the existing
  verified-inactive zero rule;
- the selected QB has `ranking_eligible = true`;
- every other QB has `ranking_eligible = false` even when active or unverified;
- a verified-inactive QB remains projected at zero and ineligible;
- RB, WR, and TE eligibility remains `not INACTIVE`;
- FLEX remains RB/WR/TE only; and
- position and Superflex ranks use only `ranking_eligible` rows.

With no complete availability source, a preview selects the frozen depth QB1
and labels availability `UNVERIFIED`, as it does today. If complete definitive
availability is supplied, the same algorithm promotes the next-lowest depth
rank after an inactive QB is removed. A T-60 lock still requires complete
availability for both teams.

No fallback may use player name, roster order, projection order, historical
points, or an inferred starter label.

## 6. Artifact changes and binding

Every preview and lock prediction row adds:

- `qb_depth_rank`: a positive exact integer for QB and `null` for RB/WR/TE.

The existing `ranking_eligible` field carries the selection result. No new role
object or parallel ranking engine is needed.

The depth source must appear in:

- preview `source_coverage`;
- game-lock coverage;
- the lock's ordered source receipts and aggregate receipt hash;
- prediction-integrity and artifact hashes through the new row schema; and
- reconstructive week and season grading through the exact embedded lock bytes.

The prospective leakage-audit contract advances to v2 and adds an explicit
`qb_depth_eligibility` inventory item covering source vintage, pre-T chronology,
roster authority, and the one-QB selection rule.

The lock verifier must allow an ACTIVE QB to be ineligible only when another
non-inactive QB on the same team has the lower frozen depth rank. It must still
reject an ACTIVE, ineligible RB, WR, or TE.

Canonical JSON, strict UTF-8, finite-number rules, source/lock/result binding,
code-SHA binding, package ownership, and append-only no-overwrite behavior stay
unchanged.

## 7. Failure behavior

Preview or lock generation stops before publication when:

- depth is missing, late, noncanonical, or unreadable;
- required team coverage is incomplete;
- any roster QB is missing from depth or any extra QB is present;
- GSIS identity, team, or QB position conflicts;
- a depth rank is non-integer, boolean, nonpositive, or duplicated by team;
- a required team has no QB candidate after verified inactives are removed;
- hashing and parsing do not bind the same source bytes; or
- an output path already exists or exclusive publication loses a race.

There is no “assume QB1,” name match, or make-all-QBs-eligible fallback. A
failure may produce only the existing path-disjoint, append-only `BLOCKED`
diagnostic.

## 8. Proof requirements

Focused tests must prove:

- one QB per team is rank eligible while every QB remains projected;
- QB2 receives no position or Superflex rank when QB1 is available;
- a verified-inactive QB1 remains at zero and promotes QB2;
- all inactive QBs on a required team block the lock;
- RB, WR, and TE projections, eligibility, FLEX, and rank ordering are
  semantically unchanged;
- all player point projections equal the v1 formula for identical legal inputs;
- strict type checks reject boolean, float, zero, and negative depth ranks;
- missing, extra, duplicate, team-mismatched, position-mismatched, and late
  depth evidence fails closed;
- noncanonical depth-row order is rejected before projection;
- any change to the frozen source bytes changes its receipt and downstream
  artifact hashes;
- preview coverage, lock receipts, prediction hashes, week grades, and season
  evidence bind the exact depth bytes;
- a coordinated rehash cannot replace the original depth evidence;
- existing outputs and concurrent writers remain byte-preserving failures; and
- v1 and v2 evidence cannot be pooled.

Repository verification also requires the complete prospective suite, the full
suite with `ResourceWarning` elevated, Python compilation, `git diff --check`,
protected-artifact comparison, and confirmation that the public team model
still reads `Experimental model — HOLD`.

## 9. Current Week 1 evidence

The local September 2 diagnostic is enough to design the QB-only contract, not
to publish or lock it:

- 87 of 87 current ACT-roster QBs matched by stable ID across all 32 teams;
- exactly one depth-rank-1 QB existed per team;
- no QB team mismatch was found; and
- Justin Fields (KC depth rank 2) was the only backup in the current projected
  top 24 QBs, at QB23.

The raw ESPN-derived nflverse depth file was captured at
`2026-09-02T13:08:47.158283-04:00`, with SHA-256
`f33af21139638915af18d83de754fa055126b77296b0ac711c5d5baaa7520d48`.
The local diagnostic file SHA-256 is
`6f1f97738cafa05ed9e1f68ff165deed6022f0b3e489ef9e36f68c24eade79c6`.

The broad all-position diagnostic remains `BLOCKED` because two non-QBs were
missing and one TE/FB position conflicted. Those failures are neither waived nor
used as model inputs: this design qualifies only the complete QB subset. Any
future RB/WR/TE depth use requires a separate design and qualification.

## 10. Opening-night runbook boundary

The Week 1 opener is scheduled for September 9 at 8:20 PM Eastern, so its T-60
deadline is 7:20 PM Eastern. Before that deadline, the later execution phase
must freeze and validate:

1. schedule, roster, completed history, and v2 config;
2. a fresh normalized QB depth snapshot;
3. complete definitive inactive coverage for both teams; and
4. the clean committed runtime code SHA.

The lock command is run manually only after those inputs exist and while the
clock is no later than T-60. If definitive availability or any QB-depth gate is
missing, the correct result is `BLOCKED`; no backdated or inferred lock is
allowed. A new path is required for every preview rerun.

## 11. Out of scope and protected boundaries

This slice adds no:

- QB projection adjustment;
- RB, WR, or TE depth/role weighting;
- opponent, weather, market, or paid-grade feature;
- PFF dependency;
- lineup optimizer, league integration, or store work;
- historical backtest claim from unavailable depth vintages;
- public-site change, push, or deployment; or
- removal of any `HOLD` label.

The July team-model lock, McCabe comparison, historical snapshots, checked-in
ratings, prior v1 preview, and unrelated untracked files remain untouched.

## 12. Shape of done

Implementation is complete only when the existing prospective path can consume
one frozen QB depth snapshot, produce the v2 preview and T-60 locks under the
rule above, reconstruct grades from the exact evidence, and pass every focused,
repository, integrity, and protected-scope gate.

That completion makes the eligibility rule operational. It does not make the
fantasy model `PASS`. Scientific promotion still requires the full untouched
2026 regular-season prospective gate.

The next step after user review of this specification is a detailed
implementation plan. No implementation begins from this document alone.
