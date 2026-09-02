# PGO Fantasy QB Depth Eligibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make exactly one current, non-inactive QB per team eligible for PGO Standard position ranks and Superflex ranks using an exact frozen depth snapshot, without changing any point projection.

**Architecture:** Extend the existing `pgo_fantasy_prospective.py` source envelope with one strict `depth` kind, then reuse the existing projection, ranking, lock, grade, canonical JSON, and append-only publication path. A small shared selector derives the minimum valid depth rank per team for both projection construction and lock verification; no importer, provider client, alternate ranking engine, or new runtime module is added.

**Tech Stack:** Python standard library, existing PGO modules, `unittest`, Git, and PowerShell. No new dependency, service, database, workflow, paid source, or network call.

## Global Constraints

- Approved design base is `62c149959f93ec652d7a2dd1ee9450fe8e5c772c` on branch `codex/pgo-fantasy-qb-depth-eligibility` in `D:\CodexWorktrees\Postgame_Outlet-fantasy-qb-depth-eligibility`.
- Runtime implementation changes are limited to `pgo_fantasy_prospective.py` and `tests/test_pgo_fantasy_prospective.py`.
- Keep `docs/superpowers/specs/2026-09-02-pgo-fantasy-qb-depth-eligibility-design.md` and this plan as documentation-only changes.
- Do not create a depth importer, provider SDK, new runtime module, database, scheduler, or alternate projection/ranking path.
- Model version is exactly `pgo_fantasy_2026_baseline_v2`; v1 preview bytes remain preserved and cannot enter the v2 grade epoch.
- Leakage-audit contract is exactly `PGO_FANTASY_PROSPECTIVE_2026_SCIENTIFIC_V2` and its inventory includes `qb_depth_eligibility`.
- The row grain remains `(season, week, game_id, gsis_id)` for the 2026 NFL regular season.
- Decision time remains `T = scheduled kickoff - 60 minutes`.
- The current ACT roster remains authoritative for population, stable GSIS identity, team, and position.
- The depth source supplies only QB priority. It cannot add players, move teams, remap positions, or change projections.
- The normalized depth source contains exactly `gsis_id`, `team`, `position`, and `depth_rank` per row; rows are ordered by `(team, depth_rank, gsis_id)`.
- `depth_rank` is an exact positive integer. Reject booleans, floats, zero, negatives, duplicate GSIS IDs, and duplicate `(team, depth_rank)` keys.
- The depth `source` value binds the upstream artifact as `<identity-or-url>|sha256:<64-lowercase-hex>`; bare URLs or identities fail closed.
- A preview requires depth coverage for every scheduled team. A game lock requires depth and definitive availability coverage for both participating teams.
- Every required ACT-roster QB must match exactly one depth row by GSIS ID and team; extra or missing depth QBs block.
- Select the lowest depth rank among roster QBs not marked `INACTIVE`. No remaining QB candidate blocks the artifact.
- Every QB remains projected. Only the selected QB is `ranking_eligible`; RB/WR/TE eligibility stays `not INACTIVE`.
- Add `qb_depth_rank`: positive integer for QB, `None` for RB/WR/TE.
- The half-PPR formula, position means, history window, half-life, pseudo-games, cold-start rule, pool size, metrics, bootstrap, and PASS thresholds do not change.
- Use the existing exact-byte snapshot loader, source receipts, lock bytes, reconstructive grades, strict UTF-8 JSON, code SHA, and append-only/no-overwrite writers.
- All tests use synthetic temporary files. Do not read `prospective_evidence/`, real caches, accepted research directories, or the network.
- Do not change `pgo_fantasy.py`, `pgo_prospective.py`, `pgo_challenger.py`, `pgo_sources.py`, `research/`, `data/`, `docs/index.html`, `.github/workflows/`, Shopify/theme files, or protected July artifacts.
- Do not capture a new provider source, freeze the v2 real config, generate a real preview, create a T-60 lock, push, publish, or deploy during implementation.
- Preserve `Experimental model — HOLD` and all unrelated untracked paths. Never use `git add -A`.

## File Map

- Modify `pgo_fantasy_prospective.py`: strict depth source shape, v2 config identity, QB-depth/roster reconciliation, eligibility selection, prediction-row validation, receipt coverage, and CLI `--depth` plumbing.
- Modify `tests/test_pgo_fantasy_prospective.py`: synthetic depth fixture, strict boundary cases, one-QB-per-team behavior, realistic multi-game weekly evidence, grade binding, CLI containment, and regressions.
- Modify no other runtime file. The legacy `depthchart.py`, `data/qb_depth.csv`, team-model depth logic, and site generators are unrelated and remain untouched.

---

### Task 1: Add the frozen depth trust boundary and v2 source epoch

**Files:**
- Modify: `pgo_fantasy_prospective.py:23-50, 228-303, 425-456, 540-586, 730-788, 863-1006, 2064-2153`
- Modify: `tests/test_pgo_fantasy_prospective.py:14-163, 166-477, 776-962, 1576-end`

**Interfaces:**
- Produces `DEPTH_FIELDS = frozenset({"gsis_id", "team", "position", "depth_rank"})`.
- Extends `SOURCE_KINDS` to the exact order `("schedule", "roster", "availability", "history", "depth")`.
- Produces `_depth_ranks(depth: dict, roster: list[dict], teams: set[str]) -> dict[str, int]`.
- Requires `--depth PATH` for both `preview` and `lock`.
- Changes the accepted config identity to `pgo_fantasy_2026_baseline_v2` without changing any numeric parameter.
- Adds depth coverage to preview and lock receipts; later tasks consume `_depth_ranks` for selection.

- [ ] **Step 1: Add isolated RED tests for the depth snapshot and v2 config**

Add these fixture helpers inside `ProspectiveFantasyFixture` without yet changing `source_values()`:

```python
    @staticmethod
    def depth_rows():
        return [
            {"gsis_id": "buf-qb1", "team": "BUF", "position": "QB", "depth_rank": 1},
            {"gsis_id": "buf-qb2", "team": "BUF", "position": "QB", "depth_rank": 2},
            {"gsis_id": "lar-qb1", "team": "LAR", "position": "QB", "depth_rank": 1},
            {"gsis_id": "lar-qb2", "team": "LAR", "position": "QB", "depth_rank": 2},
        ]

    def depth_envelope(self, rows=None, teams=("BUF", "LAR"), captured=None):
        value = self.envelope(
            self.depth_rows() if rows is None else rows,
            teams=teams,
            captured=captured,
        )
        value["source"] = "synthetic-depth|sha256:" + "f" * 64
        return value
```

Add these tests to `ProspectiveSourceBoundaryTests`:

```python
    def test_depth_snapshot_requires_raw_digest_and_strict_qb_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = prospective.load_snapshot(
                self.write_json(root / "depth.json", self.depth_envelope()),
                "depth",
            )
            self.assertEqual(valid["receipt"]["kind"], "depth")
            self.assertEqual(valid["snapshot"]["rows"], self.depth_rows())

            cases = []
            bare = self.depth_envelope()
            bare["source"] = "https://example.invalid/depth.csv.gz"
            cases.append(("bare-source", bare))
            missing_as_of = self.depth_envelope()
            missing_as_of["source_as_of"] = None
            cases.append(("missing-as-of", missing_as_of))
            for label, value in (
                ("boolean", True), ("float", 1.0), ("zero", 0), ("negative", -1),
            ):
                changed = self.depth_envelope()
                changed["rows"][0]["depth_rank"] = value
                cases.append((label, changed))
            wrong_position = self.depth_envelope()
            wrong_position["rows"][0]["position"] = "WR"
            cases.append(("position", wrong_position))
            reversed_rows = self.depth_envelope(list(reversed(self.depth_rows())))
            cases.append(("row-order", reversed_rows))

            for label, value in cases:
                with self.subTest(label=label):
                    with self.assertRaises(ValueError):
                        prospective.load_snapshot(
                            self.write_json(root / f"{label}.json", value), "depth"
                        )

    def test_depth_snapshot_rejects_duplicate_identity_and_team_rank(self):
        cases = []
        duplicate_id = self.depth_rows()
        duplicate_id[1] = {**duplicate_id[1], "gsis_id": "buf-qb1"}
        cases.append(("identity", duplicate_id))
        duplicate_rank = self.depth_rows()
        duplicate_rank[1] = {**duplicate_rank[1], "depth_rank": 1}
        cases.append(("rank", duplicate_rank))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for label, rows in cases:
                with self.subTest(label=label), self.assertRaises(ValueError):
                    prospective.load_snapshot(
                        self.write_json(root / f"{label}.json", self.depth_envelope(rows)),
                        "depth",
                    )

    def test_model_config_requires_the_qb_depth_v2_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = self.config()
            current["model_version"] = "pgo_fantasy_2026_baseline_v2"
            prospective.load_model_config(
                self.write_json(root / "v2.json", current, canonical=True)
            )
            old = self.config()
            old["model_version"] = "pgo_fantasy_2026_baseline_v1"
            with self.assertRaisesRegex(ValueError, "model config"):
                prospective.load_model_config(
                    self.write_json(root / "v1.json", old, canonical=True)
                )
```

- [ ] **Step 2: Run the focused tests and capture the expected RED**

Run:

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveSourceBoundaryTests.test_depth_snapshot_requires_raw_digest_and_strict_qb_rows `
  tests.test_pgo_fantasy_prospective.ProspectiveSourceBoundaryTests.test_depth_snapshot_rejects_duplicate_identity_and_team_rank `
  tests.test_pgo_fantasy_prospective.ProspectiveSourceBoundaryTests.test_model_config_requires_the_qb_depth_v2_epoch -v
```

Expected: FAIL/ERROR because `depth` is not a known source kind and v2 is rejected. Existing unrelated tests must not be run concurrently with a changing fixture.

- [ ] **Step 3: Implement strict depth parsing and the exact roster join**

At the constants, use:

```python
SOURCE_KINDS = ("schedule", "roster", "availability", "history", "depth")
DEPTH_FIELDS = frozenset({"gsis_id", "team", "position", "depth_rank"})

ROW_FIELDS = {
    "schedule": SCHEDULE_FIELDS,
    "roster": ROSTER_FIELDS,
    "availability": AVAILABILITY_FIELDS,
    "history": HISTORY_FIELDS,
    "depth": DEPTH_FIELDS,
}
```

Make `_validate_row()` use an explicit depth branch before history:

```python
    elif kind == "depth":
        for field in ("gsis_id", "position"):
            _row_text(row, field, kind)
        _row_team(row, "team", teams, kind)
        if (
            row["position"] != "QB"
            or type(row["depth_rank"]) is not int
            or row["depth_rank"] <= 0
        ):
            raise ValueError("depth snapshot row is invalid")
    else:
        parse_timestamp(row["finalized_at"], f"{kind} snapshot finalized_at")
        for field in ("gsis_id", "position"):
            _row_text(row, field, kind)
        _row_team(row, "team", teams, kind)
        for field in pgo_fantasy.SCORING_FIELDS:
            if type(row[field]) not in (int, float) or not math.isfinite(row[field]):
                raise ValueError(f"{kind} snapshot {field} is invalid")
        pgo_fantasy.half_ppr(row)
```

After validating every row in `_snapshot_from_bytes()`, add the depth-only trust checks:

```python
    if kind == "depth":
        identity, marker, digest = value["source"].rpartition("|sha256:")
        if (
            not identity.strip()
            or marker != "|sha256:"
            or value["source"].count("|sha256:") != 1
            or not _hex_digest(digest, 64)
            or value["source_as_of"] is None
            or rows != sorted(
                rows,
                key=lambda row: (
                    normalize_team(row["team"]),
                    row["depth_rank"],
                    row["gsis_id"],
                ),
            )
            or len({row["gsis_id"] for row in rows}) != len(rows)
            or len({(row["team"], row["depth_rank"]) for row in rows}) != len(rows)
        ):
            raise ValueError("depth snapshot contract is invalid")
```

Add `_depth_ranks()` immediately after `_roster_rows()`:

```python
def _depth_ranks(depth, roster, teams):
    required = set(teams)
    if not required <= set(depth["receipt"]["teams_processed"]):
        raise ValueError("Prospective depth coverage is incomplete")
    roster_qbs = {
        row["gsis_id"]: row for row in roster if row["position"] == "QB"
    }
    if {row["team"] for row in roster_qbs.values()} != required:
        raise ValueError("Prospective roster QB coverage is incomplete")
    observed = {}
    for row in depth["snapshot"]["rows"]:
        team = normalize_team(_required_text(row["team"], "depth team"))
        if team not in required:
            continue
        gsis_id = _required_text(row["gsis_id"], "depth gsis_id")
        player = roster_qbs.get(gsis_id)
        if player is None or player["team"] != team or row["position"] != "QB":
            raise ValueError("Prospective depth identity contradicts roster")
        observed[gsis_id] = row["depth_rank"]
    if set(observed) != set(roster_qbs):
        raise ValueError("Prospective depth QB coverage is incomplete")
    return observed
```

Change `_validate_model_config()` to accept only:

```python
config["model_version"] == "pgo_fantasy_2026_baseline_v2"
```

- [ ] **Step 4: Add RED/GREEN reconciliation tests for `_depth_ranks()`**

Add this complete test, run it once before adding `_depth_ranks()`, then again after Step 3:

```python
    def test_depth_rows_exactly_match_current_roster_qbs(self):
        roster_rows = [
            {"gsis_id": "buf-qb1", "player_name": "BUF QB1", "team": "BUF", "position": "QB", "status": "ACT"},
            {"gsis_id": "buf-qb2", "player_name": "BUF QB2", "team": "BUF", "position": "QB", "status": "ACT"},
            {"gsis_id": "lar-qb1", "player_name": "LAR QB1", "team": "LAR", "position": "QB", "status": "ACT"},
            {"gsis_id": "lar-qb2", "player_name": "LAR QB2", "team": "LAR", "position": "QB", "status": "ACT"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roster_source = prospective.load_snapshot(
                self.write_json(root / "roster.json", self.envelope(roster_rows)),
                "roster",
            )
            roster = prospective._roster_rows(roster_source, {"BUF", "LAR"})
            valid = prospective.load_snapshot(
                self.write_json(root / "depth.json", self.depth_envelope()), "depth"
            )
            self.assertEqual(
                prospective._depth_ranks(valid, roster, {"BUF", "LAR"}),
                {"buf-qb1": 1, "buf-qb2": 2, "lar-qb1": 1, "lar-qb2": 2},
            )

            cases = {}
            cases["missing"] = self.depth_rows()[:-1]
            cases["extra"] = self.depth_rows() + [
                {"gsis_id": "lar-qb3", "team": "LAR", "position": "QB", "depth_rank": 3}
            ]
            cases["team"] = sorted([
                *self.depth_rows()[:3],
                {**self.depth_rows()[3], "team": "BUF", "depth_rank": 3},
            ], key=lambda row: (row["team"], row["depth_rank"], row["gsis_id"]))
            for label, rows in cases.items():
                with self.subTest(label=label):
                    loaded = prospective.load_snapshot(
                        self.write_json(root / f"{label}.json", self.depth_envelope(rows)),
                        "depth",
                    )
                    with self.assertRaises(ValueError):
                        prospective._depth_ranks(loaded, roster, {"BUF", "LAR"})
```

Expected RED before Step 3: `AttributeError` for missing `_depth_ranks`. Expected GREEN after Step 3: PASS.

- [ ] **Step 5: Wire depth through the existing fixture, receipts, coverage, and CLI**

In `ProspectiveFantasyFixture._bare_config()`, replace the model version with `pgo_fantasy_2026_baseline_v2`.

Append these four rows to the existing roster list in `source_values()` so the existing first three indexes remain stable:

```python
            {"gsis_id": "buf-qb1", "player_name": "BUF QB1", "team": "BUF", "position": "QB", "status": "ACT"},
            {"gsis_id": "buf-qb2", "player_name": "BUF QB2", "team": "BUF", "position": "QB", "status": "ACT"},
            {"gsis_id": "lar-qb1", "player_name": "LAR QB1", "team": "LAR", "position": "QB", "status": "ACT"},
            {"gsis_id": "lar-qb2", "player_name": "LAR QB2", "team": "LAR", "position": "QB", "status": "ACT"},
```

Add depth immediately before the existing `if availability:` block so preview
fixtures without availability still retain mandatory depth:

```python
        values["depth"] = self.depth_envelope()
```

Make source validation require depth:

```python
    required = {"schedule", "roster", "history", "depth"}
    if set(sources) - set(SOURCE_KINDS):
        raise ValueError("Unexpected prospective source")
```

Add depth to preview coverage:

```python
                ("depth", sources["depth"]),
```

Before the preview game loop, make accepted v2 previews require complete roster
and depth team coverage rather than silently skipping a game:

```python
    depth_teams = set(sources["depth"]["receipt"]["teams_processed"])
    if not scheduled_teams <= roster_teams:
        raise ValueError("Prospective preview roster coverage is incomplete")
    if not scheduled_teams <= depth_teams:
        raise ValueError("Prospective preview depth coverage is incomplete")
```

The existing loop can then project every scheduled game directly. Keep
`teams_missing` as an empty accepted-artifact field for schema continuity; do
not publish a partial v2 preview.

Set lock coverage to:

```python
"coverage": {"roster": True, "availability": True, "depth": True},
```

Require all three coverage values in `verify_game_lock()` and ensure the derived receipt coverage includes `depth`.

In `_common_sources()` load:

```python
        "depth": load_snapshot(args.depth, "depth"),
```

In `_parser().sources()` add:

```python
        command.add_argument("--depth", type=Path, required=True)
```

In `_inputs()` include `args.depth` between roster and history:

```python
        return (
            args.schedule, args.roster, args.depth, args.history, args.config,
            *(() if args.availability is None else (args.availability,)),
        )
```

Use `rg -n '"--roster"' tests/test_pgo_fantasy_prospective.py` and insert this exact pair after every preview/lock roster argument:

```python
                    "--depth", str(paths["depth"]),
```

Do not add it to `grade-week` or `grade-season`; those commands reconstruct depth identity from embedded lock receipts.

Also replace the one explicit fixture tuple
`("schedule", "roster", "availability", "history")` with
`("schedule", "roster", "availability", "history", "depth")` so its direct
lock construction consumes the required frozen source.

Add this source-coverage regression to `ProspectiveProjectionTests`:

```python
    def test_preview_blocks_incomplete_roster_or_depth_team_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, _ = self.loaded_sources(root)
            for kind in ("roster", "depth"):
                with self.subTest(kind=kind):
                    changed = deepcopy(sources)
                    snapshot = deepcopy(changed[kind]["snapshot"])
                    snapshot["teams_processed"] = ["BUF"]
                    snapshot["rows"] = [
                        row for row in snapshot["rows"] if row["team"] == "BUF"
                    ]
                    changed[kind] = prospective.load_snapshot(
                        self.write_json(root / f"missing-{kind}.json", snapshot),
                        kind,
                    )
                    with self.assertRaisesRegex(ValueError, "coverage"):
                        prospective.build_preview(changed, model, 1, self.CAPTURED)
```

- [ ] **Step 6: Run Task 1 verification**

Run sequentially:

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveSourceBoundaryTests `
  tests.test_pgo_fantasy_prospective.ProspectiveFantasyCommandTests -v
python -B -W error::ResourceWarning -m unittest tests.test_pgo_fantasy_prospective -v
```

Expected: all selected tests PASS, no `ResourceWarning`, v1 config rejection remains explicit, every preview/lock command supplies depth, and all four CLI operations remain local-only.

- [ ] **Step 7: Commit Task 1**

```powershell
git diff --check
git status --short
git add -- pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git commit -m "feat: validate prospective fantasy QB depth"
```

Expected: one commit containing only the two authorized runtime/test files.

---

### Task 2: Apply one-QB-per-team eligibility and reconstruct it in locks

**Files:**
- Modify: `pgo_fantasy_prospective.py:647-860`
- Modify: `tests/test_pgo_fantasy_prospective.py:478-1325`

**Interfaces:**
- Produces `_qb_starters(players: list[dict], depth_ranks: dict[str, int], inactive: set[str]) -> set[str]`.
- Adds `qb_depth_rank` to `LOCK_PREDICTION_COLUMNS` and every preview/lock/grade row.
- Makes `project_game()` select exactly one non-inactive QB per team.
- Makes `_validate_lock_predictions()` reconstruct the same selection from locked rows and reject self-consistent eligibility tampering.
- Advances `LEAKAGE_AUDIT_CONTRACT` to `PGO_FANTASY_PROSPECTIVE_2026_SCIENTIFIC_V2` and inserts `qb_depth_eligibility` in `LEAKAGE_AUDIT_ITEMS`.
- Rebuilds weekly synthetic evidence across 12 games/24 teams so the unchanged 24-QB primary-pool gate remains scientifically valid.

- [ ] **Step 1: Add RED behavior tests**

Add these tests to `ProspectiveProjectionTests`:

```python
    def test_only_depth_qb1_ranks_while_all_qbs_remain_projected(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(
                directory, availability=False
            )
            rows = prospective.project_game(
                sources, model, game_id, self.CAPTURED, lock_mode=False
            )["rows"]
        qbs = {row["gsis_id"]: row for row in rows if row["position"] == "QB"}
        self.assertEqual(set(qbs), {"buf-qb1", "buf-qb2", "lar-qb1", "lar-qb2"})
        self.assertEqual(
            {player for player, row in qbs.items() if row["ranking_eligible"]},
            {"buf-qb1", "lar-qb1"},
        )
        self.assertTrue(all(row["strong_prediction"] == 15.0 for row in qbs.values()))
        self.assertEqual(
            {player: row["qb_depth_rank"] for player, row in qbs.items()},
            {"buf-qb1": 1, "buf-qb2": 2, "lar-qb1": 1, "lar-qb2": 2},
        )
        ranked = {row["gsis_id"]: row for row in prospective.rank_rows(rows)}
        self.assertIsNone(ranked["buf-qb2"]["position_rank"])
        self.assertIsNone(ranked["buf-qb2"]["superflex_rank"])

    def test_verified_inactive_qb1_promotes_qb2_and_no_qb_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values, game_id = self.source_values()
            values["availability"]["rows"].append(
                {"gsis_id": "buf-qb1", "team": "BUF", "status": "INACTIVE"}
            )
            sources = {
                kind: prospective.load_snapshot(
                    self.write_json(root / f"{kind}.json", value), kind
                )
                for kind, value in values.items()
            }
            model = prospective.load_model_config(self.write_json(
                root / "config.json", self.config(), canonical=True
            ))
            rows = prospective.project_game(
                sources, model, game_id, self.LOCKED_AT, lock_mode=True
            )["rows"]
            by_id = {row["gsis_id"]: row for row in rows}
            self.assertEqual(by_id["buf-qb1"]["strong_prediction"], 0.0)
            self.assertFalse(by_id["buf-qb1"]["ranking_eligible"])
            self.assertTrue(by_id["buf-qb2"]["ranking_eligible"])

            values["availability"]["rows"].append(
                {"gsis_id": "buf-qb2", "team": "BUF", "status": "INACTIVE"}
            )
            sources["availability"] = prospective.load_snapshot(
                self.write_json(root / "all-inactive.json", values["availability"]),
                "availability",
            )
            with self.assertRaisesRegex(ValueError, "available QB"):
                prospective.project_game(
                    sources, model, game_id, self.LOCKED_AT, lock_mode=True
                )
```

Run:

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveProjectionTests.test_only_depth_qb1_ranks_while_all_qbs_remain_projected `
  tests.test_pgo_fantasy_prospective.ProspectiveProjectionTests.test_verified_inactive_qb1_promotes_qb2_and_no_qb_blocks -v
```

Expected RED: current code ranks every non-inactive QB and has no `qb_depth_rank` field.

- [ ] **Step 2: Implement the shared selector and projection behavior**

Add after `_depth_ranks()`:

```python
def _qb_starters(players, depth_ranks, inactive):
    teams = {row["team"] for row in players}
    starters = set()
    for team in teams:
        qbs = [
            row for row in players
            if row["team"] == team and row["position"] == "QB"
        ]
        ranks = [depth_ranks.get(row["gsis_id"]) for row in qbs]
        if (
            not qbs
            or any(type(rank) is not int or rank <= 0 for rank in ranks)
            or len(set(ranks)) != len(ranks)
        ):
            raise ValueError("Prospective QB depth ranks are invalid")
        available = [row for row in qbs if row["gsis_id"] not in inactive]
        if not available:
            raise ValueError("Prospective team has no available QB")
        starters.add(min(
            available, key=lambda row: depth_ranks[row["gsis_id"]]
        )["gsis_id"])
    return starters
```

In `project_game()`, immediately after availability is resolved, add:

```python
    depth_ranks = _depth_ranks(sources["depth"], roster, teams)
    eligible_qbs = _qb_starters(roster, depth_ranks, inactive or set())
```

Replace the row fields with:

```python
            "qb_depth_rank": (
                depth_ranks[player["gsis_id"]]
                if player["position"] == "QB" else None
            ),
            "ranking_eligible": (
                not unavailable
                and (
                    player["position"] != "QB"
                    or player["gsis_id"] in eligible_qbs
                )
            ),
```

Do not touch null or strong prediction expressions.

- [ ] **Step 3: Extend and harden the lock row contract**

Insert `"qb_depth_rank"` immediately before `"ranking_eligible"` in `LOCK_PREDICTION_COLUMNS`.

In `_validate_lock_predictions()`, enforce:

```python
        rank = row["qb_depth_rank"]
        if (
            (row["position"] == "QB" and (
                type(rank) is not int or rank <= 0
            ))
            or (row["position"] != "QB" and rank is not None)
        ):
            raise ValueError("Fantasy game lock QB depth rank is invalid")
```

Keep inactive-zero validation. Replace the current ACTIVE-row rule with:

```python
        if (
            row["position"] != "QB"
            and row["availability_status"] == "ACTIVE"
            and not row["ranking_eligible"]
        ):
            raise ValueError("Active fantasy lock row is invalid")
```

After all rows are structurally validated, reconstruct QB selection:

```python
    depth_ranks = {
        row["gsis_id"]: row["qb_depth_rank"]
        for row in rows if row["position"] == "QB"
    }
    inactive = {
        row["gsis_id"] for row in rows
        if row["position"] == "QB" and row["availability_status"] == "INACTIVE"
    }
    eligible_qbs = _qb_starters(rows, depth_ranks, inactive)
    if any(
        row["position"] == "QB"
        and row["ranking_eligible"] != (row["gsis_id"] in eligible_qbs)
        for row in rows
    ):
        raise ValueError("Fantasy game lock QB eligibility is invalid")
```

This is the only verifier exception to the former “every ACTIVE row is eligible” invariant.

Advance the scientific audit identity beside the existing bootstrap constants:

```python
LEAKAGE_AUDIT_CONTRACT = "PGO_FANTASY_PROSPECTIVE_2026_SCIENTIFIC_V2"
LEAKAGE_AUDIT_ITEMS = (
    "target_outcome_boundary", "history_cutoff", "position_mean_initializer",
    "roster_availability", "qb_depth_eligibility", "schedule_result_joins",
    "ranking_primary_pool", "metrics_uncertainty", "epoch_firewall",
)
```

The existing audit fixture builds its inventory from `LEAKAGE_AUDIT_ITEMS`, so
no parallel audit shape is introduced.

- [ ] **Step 4: Replace the single-game weekly fixture with legal 24-team evidence**

Replace `ProspectiveWeekGradeTests.week_evidence()` with a method that accepts `week=1` and builds 12 locks. Use this complete body:

```python
    def week_evidence(self, week=1):
        teams = tuple(sorted(pgo_fantasy.CURRENT_TEAMS)[:24])
        matchups = list(zip(teams[::2], teams[1::2]))
        schedule_rows = [
            {
                "season": 2026,
                "week": week,
                "game_id": f"2026_{week:02d}_{away}_{home}",
                "game_type": "REG",
                "kickoff": self.KICKOFF,
                "away_team": away,
                "home_team": home,
            }
            for away, home in matchups
        ]
        team_game = {
            team: game["game_id"]
            for game in schedule_rows
            for team in (game["away_team"], game["home_team"])
        }
        roster_rows = []
        depth_rows = []
        for team in teams:
            for position, count in (("QB", 1), ("RB", 2), ("WR", 2), ("TE", 1)):
                for index in range(count):
                    gsis_id = f"{team}-{position}-{index:02d}"
                    roster_rows.append({
                        "gsis_id": gsis_id,
                        "player_name": gsis_id,
                        "team": team,
                        "position": position,
                        "status": "ACT",
                    })
                    if position == "QB":
                        depth_rows.append({
                            "gsis_id": gsis_id,
                            "team": team,
                            "position": "QB",
                            "depth_rank": 1,
                        })

        values, _ = self.source_values(history_rows=[])
        values["schedule"] = self.envelope(schedule_rows, teams=teams)
        values["roster"] = self.envelope(roster_rows, teams=teams)
        values["availability"] = self.envelope([], teams=teams)
        values["depth"] = self.depth_envelope(depth_rows, teams=teams)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {
                kind: prospective.load_snapshot(
                    self.write_json(root / f"{kind}.json", value), kind
                )
                for kind, value in values.items()
            }
            model = prospective.load_model_config(self.write_json(
                root / "config.json", self.config(), canonical=True
            ))
            loaded_locks = []
            for game in schedule_rows:
                lock = prospective.build_game_lock(
                    sources, model, game["game_id"], self.LOCKED_AT, "a" * 40
                )
                lock_bytes = prospective.serialize_game_lock(lock).encode("utf-8")
                loaded_locks.append({
                    "lock": lock,
                    "bytes": lock_bytes,
                    "sha256": hashlib.sha256(lock_bytes).hexdigest(),
                })

            missing_id = f"{teams[0]}-WR-00"
            result_rows = [
                {
                    "game_id": team_game[row["team"]],
                    "gsis_id": row["gsis_id"],
                    **self.scoring(receiving_yards=10.0),
                }
                for row in roster_rows if row["gsis_id"] != missing_id
            ]
            results_value = {
                "schema_version": 1,
                "source": "synthetic-official-results",
                "source_as_of": "2026-09-10T00:30:00-04:00",
                "captured_at": "2026-09-10T00:30:00-04:00",
                "teams_processed": list(teams),
                "games": [
                    {
                        "game_id": game["game_id"],
                        "status": "FINAL",
                        "finalized_at": "2026-09-10T00:20:00-04:00",
                    }
                    for game in schedule_rows
                ],
                "rows": result_rows,
            }
            results = prospective.load_results(self.write_json(
                root / "results.json", results_value
            ))
        return loaded_locks, results
```

In `test_week_grade_uses_exact_locks_and_zero_fills_missing_stats`, compute the expected missing ID from the locked rows rather than using `WR-000`:

```python
        missing = next(
            row for row in grade["rows"]
            if row["team"] == sorted(pgo_fantasy.CURRENT_TEAMS)[0]
            and row["position"] == "WR"
            and row["gsis_id"].endswith("-00")
        )
```

Replace `ProspectiveSeasonGradeTests.week_grade()` with:

```python
    def week_grade(self, week, strong_delta=1.0, code_sha="a" * 40):
        locks, results = ProspectiveWeekGradeTests("runTest").week_evidence(week)
        changed_locks = []
        for loaded in locks:
            lock = deepcopy(loaded["lock"])
            lock["code_sha"] = code_sha
            for row in lock["predictions"]:
                row["null_prediction"] += strong_delta
            lock["prediction_integrity_sha256"] = prospective._prediction_hash(
                lock["predictions"]
            )
            lock["artifact_sha256"] = prospective._artifact_hash(lock)
            data = prospective.serialize_game_lock(lock).encode("utf-8")
            changed_locks.append({
                "lock": lock,
                "bytes": data,
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        grade = prospective.grade_week(changed_locks, results)
        self.assertEqual(sum(row["primary_pool"] for row in grade["rows"]), 96)
        self.assertEqual(
            len({
                (row["game_id"], row["gsis_id"])
                for row in grade["rows"] if row["primary_pool"]
            }),
            96,
        )
        return grade
```

This preserves the fixed 24-QB gate instead of weakening it to accommodate a two-team test.

- [ ] **Step 5: Add lock-semantic tamper tests**

Add to `ProspectiveGameLockTests`:

```python
    def test_lock_reconstructs_qb_depth_eligibility(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            lock = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
        by_id = {row["gsis_id"]: row for row in lock["predictions"]}
        self.assertTrue(by_id["buf-qb1"]["ranking_eligible"])
        self.assertFalse(by_id["buf-qb2"]["ranking_eligible"])
        self.assertIsNone(by_id["veteran"]["qb_depth_rank"])

        for label, mutate in (
            ("backup eligible", lambda row: row.update(ranking_eligible=True)),
            ("duplicate rank", lambda row: row.update(qb_depth_rank=1)),
        ):
            with self.subTest(label=label), self.assertRaises(ValueError):
                changed = deepcopy(lock)
                mutate(next(
                    row for row in changed["predictions"]
                    if row["gsis_id"] == "buf-qb2"
                ))
                changed["prediction_integrity_sha256"] = prospective._prediction_hash(
                    changed["predictions"]
                )
                changed["artifact_sha256"] = prospective._artifact_hash(changed)
                prospective.verify_game_lock(changed)
```

If `_prediction_hash()` rejects before the outer verifier, the test still passes only when the semantic error is a clean `ValueError`; do not weaken `_prediction_hash()` to make the forged artifact easier to build.

- [ ] **Step 6: Run Task 2 verification**

Run sequentially:

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveProjectionTests `
  tests.test_pgo_fantasy_prospective.ProspectiveGameLockTests -v
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveWeekGradeTests `
  tests.test_pgo_fantasy_prospective.ProspectiveSeasonGradeTests -v
python -B -W error::ResourceWarning -m unittest tests.test_pgo_fantasy_prospective -v
```

Expected: all tests PASS, weekly primary count remains exactly 96 with 24 unique eligible QBs, inactive QB1 promotes QB2, and point projections retain the frozen v1 math under the v2 eligibility epoch.

- [ ] **Step 7: Commit Task 2**

```powershell
git diff --check
git status --short
git add -- pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git commit -m "feat: rank only active QB depth leaders"
```

Expected: one authorized two-file commit.

---

### Task 3: Close depth evidence, chronology, and CLI regression boundaries

**Files:**
- Modify: `tests/test_pgo_fantasy_prospective.py:166-end`
- Modify only if a new RED exposes a root defect: `pgo_fantasy_prospective.py`

**Interfaces:**
- Proves preview coverage reports depth.
- Proves lock receipts retain the exact loaded depth receipt.
- Proves parsed receipt changes cannot detach from original lock bytes during grading.
- Proves late or aliased depth evidence fails before publication.
- Adds no new production abstraction.

- [ ] **Step 1: Add the depth evidence regression tests**

Add these tests in their matching existing classes:

```python
    def test_preview_reports_depth_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, _ = self.loaded_sources(directory, availability=False)
            preview = prospective.build_preview(sources, model, 1, self.CAPTURED)
        self.assertEqual(preview["source_coverage"]["depth"]["missing"], [])
        self.assertEqual(
            preview["source_coverage"]["depth"]["processed"], ["BUF", "LAR"]
        )
```

```python
    def test_lock_binds_the_exact_depth_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            lock = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
        receipt = next(
            item for item in lock["source_receipts"] if item["kind"] == "depth"
        )
        self.assertEqual(receipt, sources["depth"]["receipt"])
        self.assertTrue(lock["coverage"]["depth"])
```

```python
    def test_grade_rejects_a_rehashed_depth_receipt_detached_from_lock_bytes(self):
        loaded_locks, results = self.week_evidence()
        changed = deepcopy(loaded_locks)
        lock = changed[0]["lock"]
        receipt = next(
            item for item in lock["source_receipts"] if item["kind"] == "depth"
        )
        receipt["sha256"] = "0" * 64
        lock["source_receipts_sha256"] = hashlib.sha256(
            prospective.canonical_json(lock["source_receipts"]).encode("utf-8")
        ).hexdigest()
        lock["artifact_sha256"] = prospective._artifact_hash(lock)
        with self.assertRaisesRegex(ValueError, "bytes are not exact"):
            prospective.grade_week(changed, results)
```

```python
    def test_depth_input_is_protected_and_late_depth_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            original = paths["depth"].read_bytes()
            self.assertEqual(prospective.main([
                "preview", "--schedule", str(paths["schedule"]),
                "--roster", str(paths["roster"]),
                "--depth", str(paths["depth"]),
                "--history", str(paths["history"]),
                "--config", str(paths["config"]),
                "--week", "1", "--as-of", self.CAPTURED,
                "--output", str(paths["depth"]),
            ]), 1)
            self.assertEqual(paths["depth"].read_bytes(), original)

            late = self.depth_envelope(captured="2026-09-09T19:00:00-04:00")
            self.write_json(paths["depth"], late)
            output = paths["root"] / "late-preview.json"
            self.assertEqual(prospective.main([
                "preview", "--schedule", str(paths["schedule"]),
                "--roster", str(paths["roster"]),
                "--depth", str(paths["depth"]),
                "--history", str(paths["history"]),
                "--config", str(paths["config"]),
                "--week", "1", "--as-of", self.CAPTURED,
                "--output", str(output),
            ]), 1)
            self.assertFalse(output.exists())
```

- [ ] **Step 2: Run the new tests and fix only demonstrated root defects**

Run the four exact tests. Expected: PASS if Tasks 1-2 propagated depth correctly. If any test is RED, trace every caller of the failing shared function and apply the smallest root fix in `pgo_fantasy_prospective.py`; do not add a second validator or writer.

- [ ] **Step 3: Run protected and repository-wide verification**

Run sequentially:

```powershell
python -B -W error::ResourceWarning -m unittest tests.test_pgo_fantasy_prospective -v
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy `
  tests.test_pgo_challenger `
  tests.test_pgo_comparison `
  tests.test_pgo_prospective -v
python -B -W error::ResourceWarning -m unittest discover -s tests -v
python -B -m py_compile pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git diff --check
```

Expected: every suite PASS, zero `ResourceWarning`, compilation succeeds, and `git diff --check` is silent.

Verify scope:

```powershell
git diff --name-only 62c149959f93ec652d7a2dd1ee9450fe8e5c772c..HEAD
git status --short
git diff --exit-code 62c149959f93ec652d7a2dd1ee9450fe8e5c772c..HEAD -- `
  data research docs/index.html .github SHOPIFY.md
rg -n "Experimental model — HOLD" docs/index.html
```

Expected: implementation commits contain only the two authorized runtime/test files after excluding this plan/spec documentation; protected diff is silent; the public HOLD label remains present; status is clean.

- [ ] **Step 4: Commit Task 3 tests if they changed**

```powershell
git add -- tests/test_pgo_fantasy_prospective.py pgo_fantasy_prospective.py
git commit -m "test: bind prospective fantasy QB depth evidence"
```

If Step 2 required no change beyond tests, commit only the test file. Do not create an empty commit.

- [ ] **Step 5: Stop at the operational gate**

Report exact commit SHAs, test counts, durations, changed paths, and any retained HOLD/BLOCKED result. Do not normalize a live provider file or create a real v2 preview in this task.

The separately authorized operational follow-on must use a fresh raw depth capture and a new append-only output path. It must freeze a canonical v2 config, recheck all 87-or-current roster QBs, and stop if opening-night definitive inactive coverage is unavailable by the September 9 7:20 PM Eastern T-60 deadline.

---

## Final Review Checklist

- [ ] Exactly one rank-eligible, non-inactive QB exists per required team.
- [ ] Backup QBs remain projected and visible but have no position or Superflex rank.
- [ ] An inactive QB1 is zeroed and QB2 is promoted; no candidate is BLOCKED.
- [ ] RB/WR/TE projections, eligibility, FLEX, and ordering are unchanged.
- [ ] `qb_depth_rank` is exact integer for QB and `None` otherwise.
- [ ] Depth snapshot identity, chronology, row order, types, duplicates, roster join, and coverage fail closed.
- [ ] Preview coverage, lock source receipts, prediction hashes, exact lock bytes, week grades, and season evidence retain the depth identity.
- [ ] v1 and v2 evidence cannot pool.
- [ ] Existing outputs, concurrent writers, and foreign files remain preserved.
- [ ] Full warnings-as-errors verification passes before any completion claim.
- [ ] No protected, public, workflow, store, real-source, push, or deployment action occurred.
