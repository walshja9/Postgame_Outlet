# PGO Fantasy Week 1 Site Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private, site-faithful 2026 Week 1 fantasy rankings tab from the qualified frozen preview without creating any route that can publish it.

**Architecture:** Add one fail-closed Week 1 preview loader beside the existing prospective serializer, then pass its validated object into the existing comparison-page renderer through an opt-in private CLI argument. For that opt-in path, read the tracked combined `docs/index.html` as a frozen, read-only site shell and inject only the fantasy tab into a private copy; this avoids rebuilding or changing the existing PGO/McCabe panels. The renderer emits static escaped rows plus minimal inline CSS and JavaScript, and the browser filters and sorts those rows without fetching data.

**Tech Stack:** Python 3 standard library, existing PGO modules, static HTML/CSS/JavaScript, unittest, Git, PowerShell, and Playwright CLI for local browser verification. No new dependency, service, framework, endpoint, database, or workflow.

## Global Constraints

- Approved design base is commit `57a4dd6f786ad27599afb641c6d92651ecb18f82` on branch `codex/pgo-fantasy-week1-site-preview` in `D:\CodexWorktrees\Postgame_Outlet-fantasy-qb-depth-eligibility`.
- The authoritative design is `docs/superpowers/specs/2026-09-03-pgo-fantasy-week-1-site-preview-design.md`.
- The qualified input is `D:\Claude Context\Postgame_Outlet\prospective_evidence\fantasy-2026-week-01\operational-v2-2026-09-03-134700\preview-week-1-v2-2026-09-03-135256.json`.
- The qualified input file SHA-256 is exactly `65b90d8860044613e9acce45cf644b62dbbc3bf22ffae25c309fe19a111548a2`.
- The embedded artifact SHA-256 is exactly `0f26a03dc1cd760455d1107c17a33632e8ef0716e28c737fc22ddfabe93210aa`.
- The config SHA-256 is exactly `5b93ca84421579d9e979c71df89a55762456d16a13d76f52a8bcf445b48e6bff`.
- Model identity is exactly `pgo_fantasy_2026_baseline_v2`; evidence state is exactly `PREVIEW`, `HOLD`, `EXPERIMENTAL`, and non-gradeable.
- The source has 502 rows and 447 ranking-eligible rows: 32 QB, 113 RB, 182 WR, and 120 TE.
- Default view is SUPERFLEX. Additional views are QB, RB, WR, TE, and FLEX.
- Default columns are selected-view rank, player, position, team, opponent, and projected points.
- Expanded columns are position rank, FLEX rank, SUPERFLEX rank, baseline projection, model delta, history count, initialization reason, and availability status.
- Stable player IDs and row-level config hashes never appear in the table.
- All source text is escaped. The generated page contains all required data and makes no browser-side JSON request.
- The private HTML destination must resolve beneath `output/`; the input and output paths must not resolve to the same file.
- `--fantasy-preview` must fail before loading input or generating HTML when combined with `--publish` or `--refresh-mccabe`.
- Without `--fantasy-preview`, existing preview, publish, refresh, workflow, and generated-byte behavior stays unchanged.
- `docs/index.html` starts and ends with SHA-256 `5094ad484807bacb8ce5dddf19cff38798ed86a07c1501d1bcbf09f84dd932fe`.
- Do not change `generate_site.py`, `tests/test_public_board_workflow.py`, `.github/workflows/`, `docs/index.html`, the qualified JSON, Shopify, GitHub Pages, or any remote state.
- All automated tests use synthetic temporary inputs. They do not read `prospective_evidence/` or use the network.
- Generated review HTML and Playwright artifacts remain ignored beneath `output/` and are never committed.
- Never use `git add -A`; stage only the files named by the current task.

## File Map

- Modify `pgo_fantasy_prospective.py`: declare the exact preview contract and add `verify_week1_preview()` plus `load_week1_preview()`.
- Modify `tests/test_pgo_fantasy_prospective.py`: build a portable 32-team synthetic preview and test canonicality, metadata, coverage, rows, eligibility, and ranks.
- Modify `pgo_comparison.py`: render the fantasy panel, add its local CSS/JavaScript, inject it into the tracked combined page without rebuilding existing panels, and gate CLI loading to private output.
- Modify `tests/test_pgo_comparison.py`: test reader markup, escaping, interactions, legacy-byte preservation, argument rejection, fail-before-generation behavior, and private write wiring.
- Create no runtime module, data fixture, workflow, public page, or package.

---

### Task 1: Add the strict Week 1 preview trust boundary

**Files:**

- Modify: `pgo_fantasy_prospective.py:65-83, 813-907`
- Modify: `tests/test_pgo_fantasy_prospective.py:15-186, after ProspectiveProjectionTests`

**Interfaces:**

- Produces `PREVIEW_KEYS: frozenset[str]`.
- Produces `PREVIEW_COVERAGE_KINDS = ("roster", "availability", "depth")`.
- Produces `PREVIEW_COVERAGE_KEYS = frozenset({"processed", "missing"})`.
- Produces `PREVIEW_ROW_FIELDS: frozenset[str]`.
- Produces `verify_week1_preview(preview: dict) -> dict`.
- Produces `load_week1_preview(path: str | Path) -> dict`.
- Later tasks consume only `load_week1_preview()`; no renderer parses JSON itself.

- [ ] **Step 1: Add a complete synthetic Week 1 artifact fixture**

Add these methods to `ProspectiveFantasyFixture` after `write_json()`:

~~~python
    def week1_site_preview(self):
        teams = list(pgo_fantasy.CURRENT_TEAMS)
        config_sha256 = "a" * 64
        matchups = {}
        rows = []

        for index in range(0, len(teams), 2):
            away, home = teams[index:index + 2]
            away_id = "LA" if away == "LAR" else away
            home_id = "LA" if home == "LAR" else home
            game_id = f"2026_01_{away_id}_{home_id}"
            matchups[away] = (game_id, home)
            matchups[home] = (game_id, away)

        def add_row(
            gsis_id,
            player_name,
            team,
            position,
            strong_prediction,
            *,
            history_count=1,
            qb_depth_rank=None,
            ranking_eligible=True,
        ):
            game_id, opponent = matchups[team]
            rows.append({
                "season": 2026,
                "week": 1,
                "game_id": game_id,
                "gsis_id": gsis_id,
                "player_name": player_name,
                "team": team,
                "opponent": opponent,
                "position": position,
                "null_prediction": strong_prediction - 1.0,
                "strong_prediction": strong_prediction,
                "history_count": history_count,
                "initialization_reason": (
                    "HISTORY" if history_count else "TRUE_COLD_START"
                ),
                "availability_status": "UNVERIFIED",
                "qb_depth_rank": qb_depth_rank,
                "ranking_eligible": ranking_eligible,
                "config_sha256": config_sha256,
            })

        for index, team in enumerate(teams):
            add_row(
                f"qb1-{team.lower()}",
                f"{team} QB1",
                team,
                "QB",
                40.0 - index,
                qb_depth_rank=1,
            )

        add_row(
            f"qb2-{teams[0].lower()}",
            f"{teams[0]} QB2",
            teams[0],
            "QB",
            50.0,
            qb_depth_rank=2,
            ranking_eligible=False,
        )
        add_row("rb-1", "Synthetic RB", teams[0], "RB", 12.0)
        add_row("wr-1", "Synthetic WR", teams[1], "WR", 11.0)
        add_row(
            "te-1",
            "Synthetic TE",
            teams[2],
            "TE",
            10.0,
            history_count=0,
        )

        preview = {
            "schema_version": 1,
            "artifact_kind": "PGO_FANTASY_WEEKLY_PREVIEW",
            "status": "HOLD",
            "publication_status": "EXPERIMENTAL",
            "evidence_mode": "PREVIEW",
            "gradeable": False,
            "season": 2026,
            "week": 1,
            "generated_at": "2026-09-03T13:52:56-04:00",
            "model_version": "pgo_fantasy_2026_baseline_v2",
            "config_sha256": config_sha256,
            "teams_processed": list(teams),
            "teams_missing": [],
            "source_coverage": {
                "roster": {"processed": list(teams), "missing": []},
                "availability": {"processed": [], "missing": list(teams)},
                "depth": {"processed": list(teams), "missing": []},
            },
            "rows": prospective.rank_rows(rows),
        }
        preview["artifact_sha256"] = prospective._artifact_hash(preview)
        return preview

    @staticmethod
    def rehash_preview(preview):
        preview["artifact_sha256"] = prospective._artifact_hash(preview)
        return preview
~~~

- [ ] **Step 2: Add RED tests for valid bytes and JSON decoding**

Add this new class immediately before `ProspectiveGameLockTests`:

~~~python
class ProspectiveWeek1PreviewLoadTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def test_week1_preview_loader_accepts_canonical_artifact(self):
        preview = self.week1_site_preview()
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(
                Path(directory) / "preview.json",
                preview,
                canonical=True,
            )
            loaded = prospective.load_week1_preview(path)

        self.assertEqual(loaded, preview)

    def test_week1_preview_loader_rejects_invalid_and_noncanonical_json(self):
        preview = self.week1_site_preview()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_bytes(b'{"week":1,"week":1}\n')
            nonfinite = root / "nonfinite.json"
            nonfinite.write_bytes(b'{"value":NaN}\n')
            pretty = root / "pretty.json"
            pretty.write_text(
                json.dumps(preview, indent=2) + "\n",
                encoding="utf-8",
                newline="",
            )

            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                prospective.load_week1_preview(duplicate)
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                prospective.load_week1_preview(nonfinite)
            with self.assertRaisesRegex(ValueError, "not canonical"):
                prospective.load_week1_preview(pretty)
~~~

- [ ] **Step 3: Add RED coverage for metadata, source coverage, rows, ranks, and hash**

Append these methods to `ProspectiveWeek1PreviewLoadTests`:

~~~python
    def test_week1_preview_loader_rejects_metadata_and_coverage_drift(self):
        cases = (
            ("missing-field", lambda value: value.pop("generated_at")),
            ("extra-field", lambda value: value.update(extra=True)),
            ("schema", lambda value: value.update(schema_version=2)),
            ("kind", lambda value: value.update(artifact_kind="OTHER")),
            ("season", lambda value: value.update(season=2025)),
            ("week", lambda value: value.update(week=2)),
            ("model", lambda value: value.update(model_version="other")),
            ("evidence", lambda value: value.update(evidence_mode="LOCK")),
            ("status", lambda value: value.update(status="PASS")),
            (
                "publication",
                lambda value: value.update(publication_status="VALIDATED"),
            ),
            ("gradeable", lambda value: value.update(gradeable=True)),
            (
                "timestamp",
                lambda value: value.update(generated_at="2026-09-03"),
            ),
            ("teams", lambda value: value["teams_processed"].pop()),
            (
                "depth-coverage",
                lambda value: value["source_coverage"]["depth"].update(
                    processed=value["teams_processed"][1:],
                    missing=[value["teams_processed"][0]],
                ),
            ),
            (
                "availability-coverage",
                lambda value: value["source_coverage"]["availability"].update(
                    processed=[value["teams_processed"][0]],
                    missing=value["teams_processed"][1:],
                ),
            ),
            (
                "coverage-key",
                lambda value: value["source_coverage"].update(extra={}),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for label, mutate in cases:
                with self.subTest(label=label):
                    changed = deepcopy(self.week1_site_preview())
                    mutate(changed)
                    self.rehash_preview(changed)
                    path = self.write_json(
                        root / f"{label}.json",
                        changed,
                        canonical=True,
                    )
                    with self.assertRaises(ValueError):
                        prospective.load_week1_preview(path)

            corrupt = self.week1_site_preview()
            corrupt["artifact_sha256"] = "0" * 64
            corrupt_path = self.write_json(
                root / "corrupt-hash.json",
                corrupt,
                canonical=True,
            )
            with self.assertRaisesRegex(ValueError, "metadata"):
                prospective.load_week1_preview(corrupt_path)

    def test_week1_preview_loader_rejects_row_and_rank_drift(self):
        def first_row(value, predicate):
            return next(row for row in value["rows"] if predicate(row))

        cases = (
            (
                "missing-row-field",
                lambda value: value["rows"][0].pop("player_name"),
            ),
            (
                "extra-row-field",
                lambda value: value["rows"][0].update(extra=True),
            ),
            (
                "boolean-history",
                lambda value: value["rows"][0].update(history_count=True),
            ),
            (
                "negative-history",
                lambda value: value["rows"][0].update(history_count=-1),
            ),
            (
                "initialization",
                lambda value: value["rows"][0].update(
                    initialization_reason="TRUE_COLD_START"
                ),
            ),
            (
                "blank-player",
                lambda value: value["rows"][0].update(player_name=" "),
            ),
            (
                "unknown-team",
                lambda value: value["rows"][0].update(team="XXX"),
            ),
            (
                "same-opponent",
                lambda value: value["rows"][0].update(
                    opponent=value["rows"][0]["team"]
                ),
            ),
            ("game-id", lambda value: value["rows"][0].update(game_id="bad")),
            ("position", lambda value: value["rows"][0].update(position="K")),
            (
                "availability",
                lambda value: value["rows"][0].update(
                    availability_status="ACTIVE"
                ),
            ),
            (
                "row-config",
                lambda value: value["rows"][0].update(
                    config_sha256="b" * 64
                ),
            ),
            (
                "non-qb-depth",
                lambda value: first_row(
                    value, lambda row: row["position"] == "RB"
                ).update(qb_depth_rank=1),
            ),
            (
                "backup-eligible",
                lambda value: first_row(
                    value,
                    lambda row: (
                        row["position"] == "QB"
                        and row["qb_depth_rank"] == 2
                    ),
                ).update(ranking_eligible=True),
            ),
            (
                "missing-rank",
                lambda value: first_row(
                    value, lambda row: row["ranking_eligible"]
                ).update(superflex_rank=None),
            ),
            (
                "duplicate-rank",
                lambda value: value["rows"][1].update(
                    superflex_rank=value["rows"][0]["superflex_rank"]
                ),
            ),
            (
                "duplicate-row",
                lambda value: value["rows"].append(
                    deepcopy(value["rows"][0])
                ),
            ),
            ("row-order", lambda value: value["rows"].reverse()),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for label, mutate in cases:
                with self.subTest(label=label):
                    changed = deepcopy(self.week1_site_preview())
                    mutate(changed)
                    self.rehash_preview(changed)
                    path = self.write_json(
                        root / f"{label}.json",
                        changed,
                        canonical=True,
                    )
                    with self.assertRaises(ValueError):
                        prospective.load_week1_preview(path)
~~~


- [ ] **Step 4: Run the complete loader class to verify RED**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveWeek1PreviewLoadTests -v
~~~

Expected: every test errors because `pgo_fantasy_prospective` has no `load_week1_preview`.

- [ ] **Step 5: Add the exact preview constants**

Immediately after `LOCK_PREDICTION_COLUMNS`, add:

~~~python
PREVIEW_KEYS = frozenset({
    "schema_version", "artifact_kind", "artifact_sha256", "config_sha256",
    "evidence_mode", "generated_at", "gradeable", "model_version",
    "publication_status", "rows", "season", "source_coverage", "status",
    "teams_missing", "teams_processed", "week",
})
PREVIEW_COVERAGE_KINDS = ("roster", "availability", "depth")
PREVIEW_COVERAGE_KEYS = frozenset({"processed", "missing"})
PREVIEW_ROW_FIELDS = frozenset(LOCK_PREDICTION_COLUMNS) | {
    "position_rank", "flex_rank", "superflex_rank",
}
~~~

- [ ] **Step 6: Implement the fail-closed verifier and canonical loader**

Insert these functions immediately after `serialize_preview()`:

~~~python
def verify_week1_preview(preview):
    teams = list(pgo_fantasy.CURRENT_TEAMS)
    if not isinstance(preview, dict) or set(preview) != PREVIEW_KEYS:
        raise ValueError("Fantasy Week 1 preview contract is invalid")
    if (
        type(preview["schema_version"]) is not int
        or preview["schema_version"] != 1
        or preview["artifact_kind"] != PREVIEW_KIND
        or preview["status"] != "HOLD"
        or preview["publication_status"] != "EXPERIMENTAL"
        or preview["evidence_mode"] != "PREVIEW"
        or preview["gradeable"] is not False
        or type(preview["season"]) is not int
        or preview["season"] != 2026
        or type(preview["week"]) is not int
        or preview["week"] != 1
        or preview["model_version"] != "pgo_fantasy_2026_baseline_v2"
        or not _hex_digest(preview["config_sha256"], 64)
        or not _hex_digest(preview["artifact_sha256"], 64)
        or preview["artifact_sha256"] != _artifact_hash(preview)
        or preview["teams_processed"] != teams
        or preview["teams_missing"] != []
    ):
        raise ValueError("Fantasy Week 1 preview metadata is invalid")
    parse_timestamp(preview["generated_at"], "fantasy preview generated_at")

    expected_coverage = {
        "roster": {"processed": teams, "missing": []},
        "availability": {"processed": [], "missing": teams},
        "depth": {"processed": teams, "missing": []},
    }
    coverage = preview["source_coverage"]
    if (
        not isinstance(coverage, dict)
        or set(coverage) != set(PREVIEW_COVERAGE_KINDS)
        or any(
            not isinstance(coverage[kind], dict)
            or set(coverage[kind]) != PREVIEW_COVERAGE_KEYS
            for kind in PREVIEW_COVERAGE_KINDS
        )
        or coverage != expected_coverage
    ):
        raise ValueError("Fantasy Week 1 preview source coverage is invalid")

    rows = preview["rows"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("Fantasy Week 1 preview rows are invalid")

    seen = set()
    qb_depth_keys = set()
    eligible_qb_teams = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != PREVIEW_ROW_FIELDS:
            raise ValueError("Fantasy Week 1 preview row contract is invalid")

        for field in ("game_id", "gsis_id", "player_name"):
            if _required_text(row[field], f"fantasy preview {field}") != row[field]:
                raise ValueError(f"Fantasy Week 1 preview {field} is invalid")
        game_parts = row["game_id"].split("_")
        try:
            team = normalize_team(row["team"])
            opponent = normalize_team(row["opponent"])
            game_teams = {
                normalize_team(value) for value in game_parts[2:]
            }
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("Fantasy Week 1 preview teams are invalid") from error

        if (
            team != row["team"]
            or opponent != row["opponent"]
            or team == opponent
            or len(game_parts) != 4
            or game_parts[:2] != ["2026", "01"]
            or game_teams != {team, opponent}
            or type(row["season"]) is not int
            or row["season"] != 2026
            or type(row["week"]) is not int
            or row["week"] != 1
            or row["position"] not in POSITIONS
            or row["availability_status"] != "UNVERIFIED"
            or row["config_sha256"] != preview["config_sha256"]
            or type(row["ranking_eligible"]) is not bool
            or type(row["history_count"]) is not int
            or row["history_count"] < 0
            or row["initialization_reason"] != (
                "HISTORY" if row["history_count"] else "TRUE_COLD_START"
            )
        ):
            raise ValueError("Fantasy Week 1 preview row context is invalid")

        for field in ("null_prediction", "strong_prediction"):
            if type(row[field]) not in (int, float) or not math.isfinite(row[field]):
                raise ValueError(
                    f"Fantasy Week 1 preview {field} is invalid"
                )

        if row["position"] == "QB":
            if (
                type(row["qb_depth_rank"]) is not int
                or row["qb_depth_rank"] <= 0
            ):
                raise ValueError("Fantasy Week 1 QB depth rank is invalid")
            depth_key = row["team"], row["qb_depth_rank"]
            if depth_key in qb_depth_keys:
                raise ValueError("Fantasy Week 1 QB depth rank is duplicated")
            qb_depth_keys.add(depth_key)
        elif row["qb_depth_rank"] is not None:
            raise ValueError("Fantasy Week 1 non-QB depth rank is invalid")

        expected_eligible = (
            row["position"] != "QB" or row["qb_depth_rank"] == 1
        )
        if row["ranking_eligible"] is not expected_eligible:
            raise ValueError("Fantasy Week 1 ranking eligibility is invalid")

        expected_ranks = {
            "position_rank": expected_eligible,
            "flex_rank": expected_eligible and row["position"] != "QB",
            "superflex_rank": expected_eligible,
        }
        for field, required in expected_ranks.items():
            value = row[field]
            if required and (type(value) is not int or value <= 0):
                raise ValueError(f"Fantasy Week 1 {field} is invalid")
            if not required and value is not None:
                raise ValueError(f"Fantasy Week 1 {field} is invalid")

        key = row["season"], row["week"], row["game_id"], row["gsis_id"]
        if key in seen:
            raise ValueError(f"Duplicate Fantasy Week 1 preview row: {key}")
        seen.add(key)
        if row["position"] == "QB" and row["ranking_eligible"]:
            eligible_qb_teams.append(row["team"])

    if (
        len(eligible_qb_teams) != 32
        or set(eligible_qb_teams) != set(teams)
    ):
        raise ValueError(
            "Fantasy Week 1 preview requires one eligible QB per team"
        )
    if rows != rank_rows(rows):
        raise ValueError("Fantasy Week 1 preview ranks or row order are invalid")
    return preview


def load_week1_preview(path):
    data = Path(path).read_bytes()
    preview = verify_week1_preview(
        _decode_json(data, "Fantasy Week 1 preview")
    )
    if data != serialize_preview(preview).encode("utf-8"):
        raise ValueError("Fantasy Week 1 preview is not canonical")
    return preview
~~~

- [ ] **Step 7: Run the core loader tests to verify GREEN**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveWeek1PreviewLoadTests.test_week1_preview_loader_accepts_canonical_artifact `
  tests.test_pgo_fantasy_prospective.ProspectiveWeek1PreviewLoadTests.test_week1_preview_loader_rejects_invalid_and_noncanonical_json -v
~~~

Expected: `Ran 2 tests` and `OK`.

- [ ] **Step 8: Run the expanded loader class**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveWeek1PreviewLoadTests -v
~~~

Expected: every test in `ProspectiveWeek1PreviewLoadTests` passes and the final line is `OK`.

- [ ] **Step 9: Run the complete prospective suite**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective -v
~~~

Expected: every prospective test passes and the final line is `OK`.

- [ ] **Step 10: Commit the loader boundary**

Run:

~~~powershell
git diff --check
git status --short
git add -- pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git diff --cached --check
git commit -m "feat: validate Week 1 fantasy previews"
~~~

Expected: one commit containing only the prospective module and its test file.

---

### Task 2: Render and inject the private fantasy panel

**Files:**

- Modify: `pgo_comparison.py:4-20, 271-504`
- Modify: `tests/test_pgo_comparison.py:1-57, 178-273`

**Interfaces:**

- Produces `FANTASY_CSS: str`, `FANTASY_TAB: str`, and `FANTASY_SCRIPT: str`.
- Produces `render_fantasy_panel(preview: dict) -> str`.
- Produces `inject_fantasy_preview(existing_html: str, panel_html: str) -> str`.
- Leaves `inject_comparison(base_html: str, panel_html: str) -> str` unchanged and byte-identical.
- `inject_fantasy_preview()` uses the already combined tracked page as its source, selects the fantasy tab and panel, and leaves PGO/McCabe content available but hidden.

- [ ] **Step 1: Add the renderer fixture and RED markup tests**

Add `import hashlib` at the top of `tests/test_pgo_comparison.py`. Add this helper after `_held_receipt()` inside `ComparisonTests`:

~~~python
    @staticmethod
    def _fantasy_preview():
        config_sha256 = "a" * 64

        def row(
            gsis_id,
            player_name,
            position,
            team,
            opponent,
            strong_prediction,
            position_rank,
            flex_rank,
            superflex_rank,
            *,
            qb_depth_rank=None,
            ranking_eligible=True,
            history_count=1,
        ):
            return {
                "season": 2026,
                "week": 1,
                "game_id": "2026_01_BUF_LAR",
                "gsis_id": gsis_id,
                "player_name": player_name,
                "team": team,
                "opponent": opponent,
                "position": position,
                "null_prediction": strong_prediction - 1.0,
                "strong_prediction": strong_prediction,
                "history_count": history_count,
                "initialization_reason": (
                    "HISTORY" if history_count else "TRUE_COLD_START"
                ),
                "availability_status": "UNVERIFIED",
                "qb_depth_rank": qb_depth_rank,
                "ranking_eligible": ranking_eligible,
                "config_sha256": config_sha256,
                "position_rank": position_rank,
                "flex_rank": flex_rank,
                "superflex_rank": superflex_rank,
            }

        return {
            "schema_version": 1,
            "artifact_kind": "PGO_FANTASY_WEEKLY_PREVIEW",
            "artifact_sha256": "b" * 64,
            "config_sha256": config_sha256,
            "evidence_mode": "PREVIEW",
            "generated_at": "2026-09-03T13:52:56-04:00",
            "gradeable": False,
            "model_version": "pgo_fantasy_2026_baseline_v2",
            "publication_status": "EXPERIMENTAL",
            "season": 2026,
            "source_coverage": {
                "roster": {"processed": ["BUF", "LAR"], "missing": []},
                "availability": {
                    "processed": [],
                    "missing": ["BUF", "LAR"],
                },
                "depth": {"processed": ["BUF", "LAR"], "missing": []},
            },
            "status": "HOLD",
            "teams_missing": [],
            "teams_processed": ["BUF", "LAR"],
            "week": 1,
            "rows": [
                row(
                    "qb-buf",
                    "Buffalo QB",
                    "QB",
                    "BUF",
                    "LAR",
                    20.0,
                    1,
                    None,
                    1,
                    qb_depth_rank=1,
                ),
                row(
                    "qb-buf-backup",
                    "Buffalo Backup",
                    "QB",
                    "BUF",
                    "LAR",
                    19.0,
                    None,
                    None,
                    None,
                    qb_depth_rank=2,
                    ranking_eligible=False,
                ),
                row(
                    "rb-lar",
                    "Los Angeles RB",
                    "RB",
                    "LAR",
                    "BUF",
                    15.0,
                    1,
                    1,
                    2,
                ),
                row(
                    "wr-buf",
                    "Rookie <script>alert(1)</script>",
                    "WR",
                    "BUF",
                    "LAR",
                    14.0,
                    1,
                    2,
                    3,
                    history_count=0,
                ),
                row(
                    "te-lar",
                    "Los Angeles TE",
                    "TE",
                    "LAR",
                    "BUF",
                    10.0,
                    1,
                    3,
                    4,
                ),
            ],
        }
~~~

Add these tests to `ComparisonTests`:

~~~python
    def test_fantasy_panel_is_reader_first_and_excludes_ineligible_rows(self):
        panel = pgo_comparison.render_fantasy_panel(
            self._fantasy_preview()
        )

        self.assertEqual(panel.count('class="fantasy-row"'), 4)
        self.assertNotIn("Buffalo Backup", panel)
        self.assertEqual(panel.count('class="fantasy-view-button"'), 6)
        self.assertIn(
            'data-view="SUPERFLEX" aria-pressed="true"',
            panel,
        )
        self.assertIn('id="fantasy-player-search"', panel)
        self.assertIn('id="fantasy-team"', panel)
        self.assertIn('id="fantasy-columns"', panel)
        for label in ("SF#", "Player", "Pos", "Team", "Opp.", "Proj."):
            self.assertIn(f">{label}</button>", panel)
        for label in (
            "Pos #",
            "FLEX #",
            "SF #",
            "Baseline",
            "Delta",
            "History",
            "Init",
            "Availability",
        ):
            self.assertIn(f">{label}</button>", panel)
        self.assertIn("PREVIEW / HOLD", panel)
        self.assertIn("pre-lock half-PPR", panel)
        self.assertIn("not gradeable", panel)
        self.assertIn("Player availability is unverified", panel)
        self.assertIn('role="status" aria-live="polite"', panel)
        self.assertIn("2026-09-03T13:52:56-04:00", panel)
        self.assertIn("pgo_fantasy_2026_baseline_v2", panel)
        self.assertIn("b" * 64, panel)
        self.assertIn("a" * 64, panel)
        self.assertNotIn("qb-buf", panel)

    def test_fantasy_panel_escapes_source_text(self):
        panel = pgo_comparison.render_fantasy_panel(
            self._fantasy_preview()
        )

        self.assertIn(
            "Rookie &lt;script&gt;alert(1)&lt;/script&gt;",
            panel,
        )
        self.assertNotIn("<script>alert(1)</script>", panel)

    def test_fantasy_assets_cover_filters_sorting_columns_and_mobile(self):
        self.assertIn("dataset.view", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("fantasy-player-search", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("fantasy-team", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("fantasy-columns", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("aria-sort", pgo_comparison.FANTASY_SCRIPT)
        self.assertNotIn("fetch(", pgo_comparison.FANTASY_SCRIPT)
        self.assertIn("@media (max-width:480px)", pgo_comparison.FANTASY_CSS)
        self.assertIn(
            "#panel-fantasy.show-technical .fantasy-technical",
            pgo_comparison.FANTASY_CSS,
        )

    def test_fantasy_injection_selects_new_tab_and_preserves_other_panels(self):
        comparison = pgo_comparison.render_comparison_panel(
            [], self._held_receipt()
        )
        fantasy = pgo_comparison.render_fantasy_panel(
            self._fantasy_preview()
        )

        existing = pgo_comparison.inject_comparison(
            self._base_html(), comparison
        )
        output = pgo_comparison.inject_fantasy_preview(
            existing, fantasy
        )

        self.assertLess(
            output.index('id="tab-comparison"'),
            output.index('id="tab-fantasy"'),
        )
        self.assertLess(
            output.index('id="tab-fantasy"'),
            output.index('id="tab-ratings"'),
        )
        self.assertIn(
            'class="tab active" id="tab-fantasy"',
            output,
        )
        self.assertIn(
            'aria-selected="true" aria-controls="panel-fantasy"',
            output,
        )
        self.assertIn(
            'class="tab" id="tab-comparison"',
            output,
        )
        self.assertIn(
            'aria-selected="false" aria-controls="panel-comparison"',
            output,
        )
        self.assertIn(
            'class="panel" id="panel-comparison"',
            output,
        )
        self.assertIn(
            'aria-labelledby="tab-comparison" hidden>',
            output,
        )
        self.assertIn(
            'class="panel active" id="panel-fantasy"',
            output,
        )
        self.assertIn('id="panel-ratings" hidden', output)
        self.assertIn("McCabe Ratings</button>", output)
        self.assertIn("McCabe QBs</button>", output)
        self.assertIn("McCabe Method</button>", output)
        self.assertEqual(output.count(pgo_comparison.FANTASY_SCRIPT), 1)
        with self.assertRaisesRegex(ValueError, "already has"):
            pgo_comparison.inject_fantasy_preview(output, fantasy)

    def test_injection_without_fantasy_remains_byte_identical(self):
        output = pgo_comparison.inject_comparison(
            self._base_html(),
            '<section id="panel-comparison">Rows</section>',
        )
        digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        self.assertEqual(
            digest,
            "6da6eac6d26cf88ecd3679f0706f430c4352d128af7d2eb039fd3c920f8bc50f",
        )
~~~

- [ ] **Step 2: Run the renderer tests to verify RED**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_panel_is_reader_first_and_excludes_ineligible_rows `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_panel_escapes_source_text `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_assets_cover_filters_sorting_columns_and_mobile `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_injection_selects_new_tab_and_preserves_other_panels `
  tests.test_pgo_comparison.ComparisonTests.test_injection_without_fantasy_remains_byte_identical -v
~~~

Expected: four tests error because the fantasy renderer/assets and `inject_fantasy_preview()` do not exist; the legacy byte test passes.

- [ ] **Step 3: Add the panel CSS and complete static renderer**

Add this constant immediately after `MODEL_CSS`:

~~~python
FANTASY_CSS = """
#panel-fantasy .fantasy-status {
  display:inline-block; margin:0 0 10px; padding:6px 10px;
  border:1px solid var(--orange); border-radius:999px;
  color:var(--ink); font-weight:700;
}
#panel-fantasy .fantasy-warning {
  max-width:78ch; margin:0 0 16px; color:var(--mut);
}
#panel-fantasy .fantasy-controls {
  display:flex; flex-wrap:wrap; gap:10px 14px; align-items:end;
  margin:16px 0 10px;
}
#panel-fantasy .fantasy-field {
  display:grid; gap:4px; color:var(--mut); font-size:12px; font-weight:600;
}
#panel-fantasy .fantasy-field input[type="search"],
#panel-fantasy .fantasy-field select {
  min-height:38px; border:1px solid var(--border); border-radius:8px;
  background:var(--panel); color:var(--ink); font:inherit; padding:7px 9px;
}
#panel-fantasy .fantasy-view-buttons {
  display:flex; flex-wrap:wrap; gap:7px; margin:0 0 12px;
}
#panel-fantasy .fantasy-view-button {
  border:1px solid var(--border); border-radius:999px; background:var(--panel);
  color:var(--ink); cursor:pointer; font:inherit; font-size:12px;
  font-weight:700; padding:7px 11px;
}
#panel-fantasy .fantasy-view-button[aria-pressed="true"] {
  border-color:var(--orange); background:var(--orange); color:#1e2a3c;
}
#panel-fantasy .fantasy-result-count {
  margin:8px 0; color:var(--mut); font-size:13px;
}
#panel-fantasy .fantasy-table th:nth-child(2),
#panel-fantasy .fantasy-table td:nth-child(2) { text-align:left; }
#panel-fantasy .fantasy-player {
  text-align:left; white-space:normal; overflow-wrap:anywhere;
}
#panel-fantasy .fantasy-technical { display:none; }
#panel-fantasy.show-technical .fantasy-technical { display:table-cell; }
#panel-fantasy.show-technical .fantasy-table { min-width:1080px; }
#panel-fantasy .fantasy-details {
  margin-top:16px; color:var(--mut); font-size:12px;
}
#panel-fantasy .fantasy-details summary {
  color:var(--ink); cursor:pointer; font-weight:700;
}
#panel-fantasy .fantasy-details code { overflow-wrap:anywhere; }
@media (max-width:480px) {
  #panel-fantasy .fantasy-controls { display:grid; grid-template-columns:1fr 1fr; }
  #panel-fantasy .fantasy-field:first-child { grid-column:1 / -1; }
  #panel-fantasy:not(.show-technical) .fantasy-table {
    table-layout:fixed; font-size:11px;
  }
  #panel-fantasy:not(.show-technical) .fantasy-table th,
  #panel-fantasy:not(.show-technical) .fantasy-table td { padding:6px 3px; }
  #panel-fantasy:not(.show-technical) .fantasy-table th:nth-child(1) { width:9%; }
  #panel-fantasy:not(.show-technical) .fantasy-table th:nth-child(2) { width:34%; }
  #panel-fantasy:not(.show-technical) .fantasy-table th:nth-child(3) { width:10%; }
  #panel-fantasy:not(.show-technical) .fantasy-table th:nth-child(4) { width:12%; }
  #panel-fantasy:not(.show-technical) .fantasy-table th:nth-child(5) { width:12%; }
  #panel-fantasy:not(.show-technical) .fantasy-table th:nth-child(6) { width:23%; }
}
"""
~~~

Add these functions immediately before `render_comparison_panel()`:

~~~python
def _optional_rank(value):
    return ("", "&mdash;") if value is None else (str(value), str(value))


def render_fantasy_panel(preview):
    eligible = sorted(
        (
            row for row in preview["rows"]
            if row["ranking_eligible"]
        ),
        key=lambda row: row["superflex_rank"],
    )
    if not eligible:
        raise ValueError("Fantasy Week 1 preview has no eligible rows")

    teams = sorted({row["team"] for row in eligible})
    options = "\n".join(
        f'<option value="{html.escape(team, quote=True)}">'
        f"{html.escape(team)}</option>"
        for team in teams
    )
    body = []
    for row in eligible:
        position_sort, position_text = _optional_rank(row["position_rank"])
        flex_sort, flex_text = _optional_rank(row["flex_rank"])
        superflex_sort, superflex_text = _optional_rank(
            row["superflex_rank"]
        )
        player = html.escape(row["player_name"])
        player_sort = html.escape(row["player_name"].lower(), quote=True)
        position = html.escape(row["position"], quote=True)
        team = html.escape(row["team"], quote=True)
        opponent = html.escape(row["opponent"], quote=True)
        initialization = html.escape(row["initialization_reason"])
        availability = html.escape(row["availability_status"])
        delta = row["strong_prediction"] - row["null_prediction"]
        body.append(
            f'<tr class="fantasy-row" data-position="{position}" '
            f'data-team="{team}" data-player="{player_sort}" '
            f'data-position-rank="{position_sort}" '
            f'data-flex-rank="{flex_sort}" '
            f'data-superflex-rank="{superflex_sort}">'
            f'<td class="fantasy-rank" data-sort="{superflex_sort}">'
            f"{superflex_text}</td>"
            f'<th scope="row" class="fantasy-player" data-sort="{player_sort}">'
            f"{player}</th>"
            f'<td data-sort="{position}">{position}</td>'
            f'<td data-sort="{team}">{team}</td>'
            f'<td data-sort="{opponent}">{opponent}</td>'
            f'<td data-sort="{row["strong_prediction"]}">'
            f'{row["strong_prediction"]:.1f}</td>'
            f'<td class="fantasy-technical" data-sort="{position_sort}">'
            f"{position_text}</td>"
            f'<td class="fantasy-technical" data-sort="{flex_sort}">'
            f"{flex_text}</td>"
            f'<td class="fantasy-technical" data-sort="{superflex_sort}">'
            f"{superflex_text}</td>"
            f'<td class="fantasy-technical" data-sort="{row["null_prediction"]}">'
            f'{row["null_prediction"]:.1f}</td>'
            f'<td class="fantasy-technical" data-sort="{delta}">'
            f"{delta:+.1f}</td>"
            f'<td class="fantasy-technical" data-sort="{row["history_count"]}">'
            f'{row["history_count"]}</td>'
            f'<td class="fantasy-technical" '
            f'data-sort="{html.escape(row["initialization_reason"].lower(), quote=True)}">'
            f"{initialization}</td>"
            f'<td class="fantasy-technical" '
            f'data-sort="{html.escape(row["availability_status"].lower(), quote=True)}">'
            f"{availability}</td>"
            "</tr>"
        )

    generated = html.escape(preview["generated_at"], quote=True)
    model = html.escape(preview["model_version"])
    artifact_sha = html.escape(preview["artifact_sha256"])
    config_sha = html.escape(preview["config_sha256"])
    coverage = preview["source_coverage"]
    total = len(preview["rows"])
    visible = len(eligible)
    return f"""
  <section class="panel active" id="panel-fantasy" role="tabpanel"
    aria-labelledby="tab-fantasy">
    <div class="fantasy-status">PREVIEW / HOLD</div>
    <h2>2026 Week 1 Fantasy Rankings</h2>
    <p class="fantasy-warning">These are pre-lock half-PPR projections.
      Player availability is unverified, rankings may change before lock,
      and this artifact is not gradeable. Generated
      <time datetime="{generated}">{generated}</time>.</p>
    <div class="fantasy-view-buttons" role="group"
      aria-label="Fantasy ranking view">
      <button type="button" class="fantasy-view-button"
        data-view="SUPERFLEX" aria-pressed="true"
        aria-controls="fantasy-table">SUPERFLEX</button>
      <button type="button" class="fantasy-view-button"
        data-view="QB" aria-pressed="false"
        aria-controls="fantasy-table">QB</button>
      <button type="button" class="fantasy-view-button"
        data-view="RB" aria-pressed="false"
        aria-controls="fantasy-table">RB</button>
      <button type="button" class="fantasy-view-button"
        data-view="WR" aria-pressed="false"
        aria-controls="fantasy-table">WR</button>
      <button type="button" class="fantasy-view-button"
        data-view="TE" aria-pressed="false"
        aria-controls="fantasy-table">TE</button>
      <button type="button" class="fantasy-view-button"
        data-view="FLEX" aria-pressed="false"
        aria-controls="fantasy-table">FLEX</button>
    </div>
    <div class="fantasy-controls">
      <label class="fantasy-field" for="fantasy-player-search">
        Player
        <input id="fantasy-player-search" type="search"
          autocomplete="off" placeholder="Search player">
      </label>
      <label class="fantasy-field" for="fantasy-team">
        Team
        <select id="fantasy-team">
          <option value="">All teams</option>
          {options}
        </select>
      </label>
      <label class="fantasy-field" for="fantasy-columns">
        Columns
        <span><input id="fantasy-columns" type="checkbox">
          Show all columns</span>
      </label>
    </div>
    <p class="fantasy-result-count" id="fantasy-result-count"
      role="status" aria-live="polite">{visible} players shown</p>
    <p class="visually-hidden fantasy-sort-status"
      role="status" aria-live="polite"></p>
    <div class="table-shell">
      <table class="fantasy-table" id="fantasy-table">
        <caption class="visually-hidden">
          Eligible 2026 Week 1 half-PPR fantasy projections
        </caption>
        <thead><tr>
          <th scope="col" aria-sort="ascending">
            <button type="button" class="sort-button fantasy-sort"
              data-column="0" data-kind="number">SF#</button></th>
          <th scope="col" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="1" data-kind="text">Player</button></th>
          <th scope="col" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="2" data-kind="text">Pos</button></th>
          <th scope="col" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="3" data-kind="text">Team</button></th>
          <th scope="col" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="4" data-kind="text">Opp.</button></th>
          <th scope="col" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="5" data-kind="number">Proj.</button></th>
          <th scope="col" class="fantasy-technical" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="6" data-kind="number">Pos #</button></th>
          <th scope="col" class="fantasy-technical" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="7" data-kind="number">FLEX #</button></th>
          <th scope="col" class="fantasy-technical" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="8" data-kind="number">SF #</button></th>
          <th scope="col" class="fantasy-technical" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="9" data-kind="number">Baseline</button></th>
          <th scope="col" class="fantasy-technical" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="10" data-kind="number">Delta</button></th>
          <th scope="col" class="fantasy-technical" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="11" data-kind="number">History</button></th>
          <th scope="col" class="fantasy-technical" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="12" data-kind="text">Init</button></th>
          <th scope="col" class="fantasy-technical" aria-sort="none">
            <button type="button" class="sort-button fantasy-sort"
              data-column="13" data-kind="text">Availability</button></th>
        </tr></thead>
        <tbody id="fantasy-rows">{"".join(body)}</tbody>
      </table>
    </div>
    <details class="fantasy-details">
      <summary>Preview details</summary>
      <p>Model <code>{model}</code>; generated
        <time datetime="{generated}">{generated}</time>.<br>
        Artifact SHA-256 <code>{artifact_sha}</code>.<br>
        Config SHA-256 <code>{config_sha}</code>.<br>
        Rows: {total} total, {visible} ranking-eligible.<br>
        Coverage: roster {len(coverage["roster"]["processed"])}/32;
        depth {len(coverage["depth"]["processed"])}/32;
        availability {len(coverage["availability"]["processed"])}/32.
        Status: PREVIEW / HOLD, EXPERIMENTAL, non-gradeable.
        Availability remains unverified.</p>
    </details>
  </section>
"""
~~~

- [ ] **Step 4: Run the static renderer tests**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_panel_is_reader_first_and_excludes_ineligible_rows `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_panel_escapes_source_text -v
~~~

Expected: `Ran 2 tests` and `OK`.

- [ ] **Step 5: Add the tab and client-side interaction script**

Add this constant after `COMPARISON_TAB`:

~~~python
FANTASY_TAB = """
    <button type="button" class="tab active" id="tab-fantasy" role="tab"
      aria-selected="true" aria-controls="panel-fantasy" tabindex="0"
      data-panel="fantasy">Fantasy Week 1</button>
"""
~~~

Add this constant after `COMPARISON_SCRIPT`:

~~~python
FANTASY_SCRIPT = """
<script>
  (() => {
    const panel = document.querySelector('#panel-fantasy');
    const body = panel && panel.querySelector('#fantasy-rows');
    const viewButtons = panel
      ? [...panel.querySelectorAll('.fantasy-view-button')]
      : [];
    const sortButtons = panel
      ? [...panel.querySelectorAll('.fantasy-sort')]
      : [];
    const search = panel && panel.querySelector('#fantasy-player-search');
    const team = panel && panel.querySelector('#fantasy-team');
    const columns = panel && panel.querySelector('#fantasy-columns');
    const count = panel && panel.querySelector('#fantasy-result-count');
    const sortStatus = panel && panel.querySelector('.fantasy-sort-status');
    const rankButton = panel
      && panel.querySelector('.fantasy-sort[data-column="0"]');
    if (
      !body || viewButtons.length !== 6 || sortButtons.length !== 14
      || !search || !team || !columns || !count || !sortStatus || !rankButton
    ) return;

    const rows = [...body.rows];
    const views = {
      SUPERFLEX: {rank: 'superflexRank', label: 'SF#'},
      QB: {rank: 'positionRank', label: 'QB#'},
      RB: {rank: 'positionRank', label: 'RB#'},
      WR: {rank: 'positionRank', label: 'WR#'},
      TE: {rank: 'positionRank', label: 'TE#'},
      FLEX: {rank: 'flexRank', label: 'FLEX#'}
    };
    let activeView = 'SUPERFLEX';
    let activeColumn = 0;
    let ascending = true;

    function sortValue(row, column, numeric) {
      const raw = row.children[column].dataset.sort;
      if (numeric) return raw === '' ? null : Number(raw);
      return raw;
    }

    function sortRows(column, nextAscending, announce) {
      const button = sortButtons.find(
        candidate => Number(candidate.dataset.column) === column
      );
      const numeric = button.dataset.kind === 'number';
      activeColumn = column;
      ascending = nextAscending;
      rows.sort((leftRow, rightRow) => {
        const left = sortValue(leftRow, column, numeric);
        const right = sortValue(rightRow, column, numeric);
        if (left === null && right !== null) return 1;
        if (right === null && left !== null) return -1;
        let order = 0;
        if (left !== null && right !== null) {
          order = numeric
            ? left - right
            : left.localeCompare(right);
        }
        const directed = ascending ? order : -order;
        return directed || leftRow.dataset.player.localeCompare(
          rightRow.dataset.player
        );
      }).forEach(row => body.appendChild(row));
      sortButtons.forEach(candidate => {
        candidate.closest('th').setAttribute('aria-sort', 'none');
      });
      button.closest('th').setAttribute(
        'aria-sort', ascending ? 'ascending' : 'descending'
      );
      if (announce) {
        sortStatus.textContent = button.textContent.trim() + ' sorted '
          + (ascending ? 'ascending' : 'descending');
      }
    }

    function applyFilters(resetRank) {
      const view = views[activeView];
      rankButton.textContent = view.label;
      const query = search.value.trim().toLowerCase();
      let visible = 0;
      rows.forEach(row => {
        const rank = row.dataset[view.rank];
        row.children[0].textContent = rank;
        row.children[0].dataset.sort = rank;
        const positionMatch = activeView === 'SUPERFLEX'
          || (activeView === 'FLEX' && row.dataset.position !== 'QB')
          || row.dataset.position === activeView;
        const playerMatch = !query || row.dataset.player.includes(query);
        const teamMatch = !team.value || row.dataset.team === team.value;
        row.hidden = !(positionMatch && playerMatch && teamMatch);
        if (!row.hidden) visible += 1;
      });
      if (resetRank) sortRows(0, true, false);
      count.textContent = visible + (visible === 1 ? ' player shown' : ' players shown');
    }

    viewButtons.forEach(button => {
      button.addEventListener('click', () => {
        activeView = button.dataset.view;
        viewButtons.forEach(candidate => {
          candidate.setAttribute(
            'aria-pressed', String(candidate === button)
          );
        });
        applyFilters(true);
      });
    });
    sortButtons.forEach(button => {
      button.addEventListener('click', () => {
        const column = Number(button.dataset.column);
        const nextAscending = column === activeColumn ? !ascending : true;
        sortRows(column, nextAscending, true);
      });
    });
    search.addEventListener('input', () => applyFilters(false));
    team.addEventListener('change', () => applyFilters(false));
    columns.addEventListener('change', () => {
      panel.classList.toggle('show-technical', columns.checked);
    });
    applyFilters(true);
  })();
</script>
"""
~~~

- [ ] **Step 6: Add fail-closed injection into the frozen combined page**

Add this function immediately after `inject_comparison()`. Do not edit `inject_comparison()`, `refresh_mccabe_page()`, or their existing constants:

~~~python
def inject_fantasy_preview(existing_html, panel_html):
    if (
        'id="tab-fantasy"' in existing_html
        or 'id="panel-fantasy"' in existing_html
    ):
        raise ValueError("Existing ratings page already has a fantasy preview")

    comparison_panel = extract_comparison_panel(existing_html)
    panel_class = '<section class="panel active" id="panel-comparison"'
    panel_label = 'aria-labelledby="tab-comparison">'
    markers = ("</style>", "</body>", COMPARISON_TAB, comparison_panel)
    if (
        any(existing_html.count(marker) != 1 for marker in markers)
        or comparison_panel.count(panel_class) != 1
        or comparison_panel.count(panel_label) != 1
        or panel_html.count('id="panel-fantasy"') != 1
    ):
        raise ValueError("Fantasy preview page markers changed")

    inactive_tab = (
        COMPARISON_TAB
        .replace('class="tab active"', 'class="tab"', 1)
        .replace('aria-selected="true"', 'aria-selected="false"', 1)
        .replace('tabindex="0"', 'tabindex="-1"', 1)
    )
    inactive_panel = (
        comparison_panel
        .replace(panel_class, '<section class="panel" id="panel-comparison"', 1)
        .replace(panel_label, 'aria-labelledby="tab-comparison" hidden>', 1)
    )
    output = existing_html.replace("</style>", FANTASY_CSS + "\n</style>", 1)
    output = output.replace(COMPARISON_TAB, inactive_tab + FANTASY_TAB, 1)
    output = output.replace(
        comparison_panel, inactive_panel + "\n" + panel_html, 1
    )
    output = output.replace("</body>", FANTASY_SCRIPT + "\n</body>", 1)
    return output
~~~

- [ ] **Step 7: Run all five renderer tests**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_panel_is_reader_first_and_excludes_ineligible_rows `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_panel_escapes_source_text `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_assets_cover_filters_sorting_columns_and_mobile `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_injection_selects_new_tab_and_preserves_other_panels `
  tests.test_pgo_comparison.ComparisonTests.test_injection_without_fantasy_remains_byte_identical -v
~~~

Expected: `Ran 5 tests` and `OK`. The pinned legacy digest must remain exactly `6da6eac6d26cf88ecd3679f0706f430c4352d128af7d2eb039fd3c920f8bc50f`.

- [ ] **Step 8: Run the full comparison suite**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest tests.test_pgo_comparison -v
~~~

Expected: every comparison test passes and the final line is `OK`.

- [ ] **Step 9: Commit the renderer**

Run:

~~~powershell
git diff --check
git status --short
git add -- pgo_comparison.py tests/test_pgo_comparison.py
git diff --cached --check
git commit -m "feat: render private Week 1 fantasy tab"
~~~

Expected: one commit containing only the comparison renderer and its test file.

---

### Task 3: Gate and wire the private CLI path

**Files:**

- Modify: `pgo_comparison.py:15-20, 673-731`
- Modify: `tests/test_pgo_comparison.py:162-177, 364-385`

**Interfaces:**

- Adds `--fantasy-preview PATH` to `parse_args()`.
- `main()` resolves and validates the private destination before loading the preview.
- `main()` rejects public-mode combinations and input/output aliasing before calling `load_week1_preview()`.
- `main()` validates the preview before reading the tracked site shell.
- Successful private generation reads `PUBLIC_OUTPUT`, calls `render_fantasy_panel(preview)`, then calls `inject_fantasy_preview()`.
- The fantasy branch never calls `generate_site` or `load_comparison_rows()`; without `--fantasy-preview`, the existing branch remains unchanged.

- [ ] **Step 1: Add RED tests for publication guards and write ordering**

Add these tests to `ComparisonTests`:

~~~python
    def test_fantasy_cli_rejects_public_modes_before_loading(self):
        for public_flag in ("--publish", "--refresh-mccabe"):
            with (
                self.subTest(public_flag=public_flag),
                patch.object(
                    pgo_comparison.fantasy_prospective,
                    "load_week1_preview",
                ) as load,
                patch.object(
                    pgo_comparison.generate_site,
                    "load_config",
                ) as load_config,
                patch.object(pgo_comparison, "atomic_write_text") as write,
            ):
                errors = io.StringIO()
                with redirect_stderr(errors):
                    code = pgo_comparison.main([
                        "--fantasy-preview",
                        "frozen.json",
                        public_flag,
                    ])

                self.assertEqual(code, 1)
                self.assertIn("private-only", errors.getvalue())
                load.assert_not_called()
                load_config.assert_not_called()
                write.assert_not_called()

    def test_fantasy_cli_rejects_input_output_alias_before_loading(self):
        same = Path("output") / "same.json"
        with (
            patch.object(
                pgo_comparison.fantasy_prospective,
                "load_week1_preview",
            ) as load,
            patch.object(
                pgo_comparison.generate_site,
                "load_config",
            ) as load_config,
            patch.object(pgo_comparison, "atomic_write_text") as write,
        ):
            errors = io.StringIO()
            with redirect_stderr(errors):
                code = pgo_comparison.main([
                    "--fantasy-preview",
                    str(same),
                    "--output",
                    str(same),
                ])

        self.assertEqual(code, 1)
        self.assertIn("different files", errors.getvalue())
        load.assert_not_called()
        load_config.assert_not_called()
        write.assert_not_called()

    def test_fantasy_cli_validates_before_reading_site_shell(self):
        with (
            patch.object(
                pgo_comparison.fantasy_prospective,
                "load_week1_preview",
                side_effect=ValueError("invalid frozen preview"),
            ) as load,
            patch.object(Path, "read_text") as read,
            patch.object(
                pgo_comparison.generate_site,
                "load_config",
            ) as load_config,
            patch.object(pgo_comparison, "atomic_write_text") as write,
        ):
            errors = io.StringIO()
            with redirect_stderr(errors):
                code = pgo_comparison.main([
                    "--fantasy-preview",
                    "frozen.json",
                    "--output",
                    "output/fantasy/index.html",
                ])

        self.assertEqual(code, 1)
        self.assertIn("invalid frozen preview", errors.getvalue())
        load.assert_called_once()
        read.assert_not_called()
        load_config.assert_not_called()
        write.assert_not_called()

    def test_fantasy_cli_writes_only_private_output(self):
        fantasy = self._fantasy_preview()
        comparison = pgo_comparison.render_comparison_panel(
            [], self._held_receipt()
        )
        existing = pgo_comparison.inject_comparison(
            self._base_html(), comparison
        )

        with tempfile.TemporaryDirectory() as temp:
            public = Path(temp) / "index.html"
            public.write_text(existing, encoding="utf-8")
            with (
                patch.object(
                    pgo_comparison.fantasy_prospective,
                    "load_week1_preview",
                    return_value=fantasy,
                ) as load,
                patch.object(pgo_comparison, "PUBLIC_OUTPUT", public),
                patch.object(
                    pgo_comparison.generate_site,
                    "load_config",
                ) as load_config,
                patch.object(
                    pgo_comparison,
                    "load_comparison_rows",
                ) as load_comparison,
                patch.object(pgo_comparison, "atomic_write_text") as write,
            ):
                code = pgo_comparison.main([
                    "--fantasy-preview",
                    "frozen.json",
                    "--output",
                    "output/fantasy/index.html",
                ])

        self.assertEqual(code, 0)
        load.assert_called_once_with(Path("frozen.json").resolve())
        load_config.assert_not_called()
        load_comparison.assert_not_called()
        write.assert_called_once()
        target, rendered = write.call_args.args
        self.assertEqual(
            target,
            Path("output/fantasy/index.html").resolve(),
        )
        self.assertIn('id="tab-fantasy"', rendered)
        self.assertIn('id="panel-fantasy"', rendered)
        self.assertIn("Rookie &lt;script&gt;", rendered)
        self.assertIn("McCabe Ratings</button>", rendered)
~~~

- [ ] **Step 2: Run the four CLI tests to verify RED**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_cli_rejects_public_modes_before_loading `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_cli_rejects_input_output_alias_before_loading `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_cli_validates_before_reading_site_shell `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_cli_writes_only_private_output -v
~~~

Expected: the tests fail because `--fantasy-preview` and `fantasy_prospective` are not wired into `pgo_comparison.py`.

- [ ] **Step 3: Add the shared-loader import and CLI argument**

Add this import beside the other PGO imports:

~~~python
import pgo_fantasy_prospective as fantasy_prospective
~~~

Add this argument after the mutually exclusive destination arguments in `parse_args()`:

~~~python
    parser.add_argument(
        "--fantasy-preview",
        type=Path,
        help="add a validated Week 1 fantasy tab to private output only",
    )
~~~

- [ ] **Step 4: Replace `main()` with validation-before-shell wiring**

Use:

~~~python
def main(argv=None):
    args = parse_args(argv)
    try:
        if args.fantasy_preview is not None and (
            args.publish or args.refresh_mccabe
        ):
            raise ValueError(
                "--fantasy-preview is private-only and cannot be combined "
                "with --publish or --refresh-mccabe"
            )

        output = (
            PUBLIC_OUTPUT if (args.publish or args.refresh_mccabe) else args.output
        ).resolve()
        preview_root = (HERE / "output").resolve()
        if not (args.publish or args.refresh_mccabe) and preview_root not in output.parents:
            raise ValueError("Comparison output must stay under output/")

        fantasy_preview = None
        comparison_rows = receipt = None
        if args.fantasy_preview is not None:
            fantasy_path = args.fantasy_preview.resolve()
            if fantasy_path == output:
                raise ValueError(
                    "Fantasy preview input and HTML output must be different files"
                )
            fantasy_preview = fantasy_prospective.load_week1_preview(
                fantasy_path
            )
            preview = inject_fantasy_preview(
                PUBLIC_OUTPUT.read_text(encoding="utf-8"),
                render_fantasy_panel(fantasy_preview),
            )
        else:
            config = generate_site.load_config()
            site_rows = generate_site.load_teams(generate_site.load_prior())
            team_ratings = {row["team"]: row["rating"] for row in site_rows}
            generate_site.build_html.qb_data = generate_site.load_qbs(
                team_ratings
            )
            base_html = generate_site.build_html(site_rows, config)
            if args.refresh_mccabe:
                preview = refresh_mccabe_page(
                    base_html, PUBLIC_OUTPUT.read_text(encoding="utf-8")
                )
            else:
                comparison_rows, receipt = load_comparison_rows(
                    MCCABE_PATH,
                    MODEL_PATH,
                    BACKTEST_PATH,
                    require_immutable=args.publish,
                )
                preview = inject_comparison(
                    base_html,
                    render_comparison_panel(comparison_rows, receipt),
                )
        atomic_write_text(output, preview)
    except (csv.Error, KeyError, OSError, TypeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Wrote {output}")
    if receipt:
        print(f"  {len(comparison_rows)} teams | {receipt['publication_status']}")
    else:
        print("  Preserved the existing approved PGO panel")
    if fantasy_preview is not None:
        eligible = sum(
            row["ranking_eligible"] for row in fantasy_preview["rows"]
        )
        print(f"  {eligible} fantasy players | PREVIEW / HOLD")
    return 0
~~~

- [ ] **Step 5: Run the CLI tests to verify GREEN**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_cli_rejects_public_modes_before_loading `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_cli_rejects_input_output_alias_before_loading `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_cli_validates_before_reading_site_shell `
  tests.test_pgo_comparison.ComparisonTests.test_fantasy_cli_writes_only_private_output -v
~~~

Expected: `Ran 4 tests` and `OK`.

- [ ] **Step 6: Run comparison and public-workflow regressions**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_comparison `
  tests.test_public_board_workflow -v
~~~

Expected: all comparison and public-workflow tests pass. The workflow tests still find only `python pgo_comparison.py --refresh-mccabe`, and the tracked public page still contains the existing PGO panel.

- [ ] **Step 7: Prove legacy generation code and the public page stayed unchanged**

Run:

~~~powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_comparison.ComparisonTests.test_injection_without_fantasy_remains_byte_identical -v
$publicHash = (Get-FileHash -Algorithm SHA256 -LiteralPath docs\index.html).Hash.ToLowerInvariant()
if ($publicHash -ne "5094ad484807bacb8ce5dddf19cff38798ed86a07c1501d1bcbf09f84dd932fe") {
  throw "Public page changed: $publicHash"
}
git diff --exit-code -- docs/index.html
~~~

Expected: the golden legacy injection test passes, the public hash is exact, and Git reports no public-page diff. Do not substitute a default-generator smoke run: the fantasy path must reuse the frozen combined page rather than recompute either existing model panel.

- [ ] **Step 8: Commit the guarded CLI path**

Run:

~~~powershell
git diff --check
git status --short
git add -- pgo_comparison.py tests/test_pgo_comparison.py
git diff --cached --check
git commit -m "feat: gate fantasy preview to private output"
~~~

Expected: one commit containing only the comparison renderer and its test file.

---

### Task 4: Generate and verify the site-faithful local artifact

**Files:**

- Read only: `D:\Claude Context\Postgame_Outlet\prospective_evidence\fantasy-2026-week-01\operational-v2-2026-09-03-134700\preview-week-1-v2-2026-09-03-135256.json`
- Generate ignored artifact: `output/fantasy-week1-site-preview/$runStamp/index.html`
- Generate no tracked file

**Interfaces:**

- Consumes the exact frozen source and the completed `pgo_comparison.py --fantasy-preview` path.
- Produces one self-contained local HTML artifact and a recorded absolute path for user review.
- Produces verification evidence only; it does not create another source commit.

- [ ] **Step 1: Confirm the implementation diff is contained**

Keep this PowerShell session open through Step 9. Run:

~~~powershell
$designBase = "57a4dd6f786ad27599afb641c6d92651ecb18f82"
$allowed = @(
  "docs/superpowers/plans/2026-09-03-pgo-fantasy-week-1-site-preview.md"
  "pgo_fantasy_prospective.py"
  "tests/test_pgo_fantasy_prospective.py"
  "pgo_comparison.py"
  "tests/test_pgo_comparison.py"
)
$changed = @(git diff --name-only "$designBase..HEAD")
$unexpected = @(Compare-Object ($allowed | Sort-Object) ($changed | Sort-Object))
if ($unexpected.Count) { throw "Unexpected implementation path: $unexpected" }
if (git status --porcelain=v1) { throw "Worktree is not clean" }
$publicBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath docs\index.html).Hash.ToLowerInvariant()
if ($publicBefore -ne "5094ad484807bacb8ce5dddf19cff38798ed86a07c1501d1bcbf09f84dd932fe") {
  throw "Tracked public page changed before verification: $publicBefore"
}
git log --oneline "$designBase..HEAD"
~~~

Expected: only the plan and four approved implementation/test files appear; the worktree is clean; the public-page hash matches.

- [ ] **Step 2: Run syntax, focused, workflow, and full-suite verification**

Run each command separately and stop at the first nonzero exit:

~~~powershell
python -B -m py_compile pgo_fantasy_prospective.py pgo_comparison.py
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveWeek1PreviewLoadTests `
  tests.test_pgo_comparison.ComparisonTests `
  tests.test_public_board_workflow -v
python -B -W error::ResourceWarning -m unittest discover -s tests -v
git diff "$designBase..HEAD" --check
~~~

Expected: compilation exits 0; focused and full suites end in `OK` with zero failures or errors; the diff check prints nothing and exits 0.

- [ ] **Step 3: Verify the frozen source before reading it**

Run:

~~~powershell
$source = "D:\Claude Context\Postgame_Outlet\prospective_evidence\fantasy-2026-week-01\operational-v2-2026-09-03-134700\preview-week-1-v2-2026-09-03-135256.json"
$expectedSourceHash = "65b90d8860044613e9acce45cf644b62dbbc3bf22ffae25c309fe19a111548a2"
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
if ($sourceHash -ne $expectedSourceHash) {
  throw "Qualified source SHA-256 mismatch: $sourceHash"
}
$sourceHash
~~~

Expected: exactly `65b90d8860044613e9acce45cf644b62dbbc3bf22ffae25c309fe19a111548a2`.

- [ ] **Step 4: Generate one fresh private artifact**

In the same PowerShell session, run:

~~~powershell
$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reviewRoot = Join-Path (Get-Location) "output\fantasy-week1-site-preview\$runStamp"
$reviewOutput = Join-Path $reviewRoot "index.html"
if (Test-Path -LiteralPath $reviewOutput) {
  throw "Review output already exists: $reviewOutput"
}
python pgo_comparison.py --fantasy-preview $source --output $reviewOutput
if ($LASTEXITCODE -ne 0) { throw "Private fantasy render failed" }
$reviewOutput
~~~

Expected: the first line echoes the exact resolved `$reviewOutput` path after `Wrote`; the remaining evidence is:

~~~text
  Preserved the existing approved PGO panel
  447 fantasy players | PREVIEW / HOLD
~~~

The resolved `$reviewOutput` is the artifact handed to the user. Do not copy it to `docs/` or stage it.

- [ ] **Step 5: Machine-check the rendered artifact and public-page hash**

Run:

~~~powershell
$rendered = Get-Content -LiteralPath $reviewOutput -Raw -Encoding utf8
$counts = [ordered]@{
  all = ([regex]::Matches($rendered, 'class="fantasy-row"')).Count
  QB = ([regex]::Matches($rendered, 'class="fantasy-row" data-position="QB"')).Count
  RB = ([regex]::Matches($rendered, 'class="fantasy-row" data-position="RB"')).Count
  WR = ([regex]::Matches($rendered, 'class="fantasy-row" data-position="WR"')).Count
  TE = ([regex]::Matches($rendered, 'class="fantasy-row" data-position="TE"')).Count
}
$expectedCounts = [ordered]@{all=447; QB=32; RB=113; WR=182; TE=120}
foreach ($name in $expectedCounts.Keys) {
  if ($counts[$name] -ne $expectedCounts[$name]) {
    throw "Rendered $name count is $($counts[$name]); expected $($expectedCounts[$name])"
  }
}
foreach ($required in @(
  'class="tab active" id="tab-fantasy"'
  'PREVIEW / HOLD'
  'pre-lock half-PPR'
  'Player availability is unverified'
  'not gradeable'
  'pgo_fantasy_2026_baseline_v2'
  '0f26a03dc1cd760455d1107c17a33632e8ef0716e28c737fc22ddfabe93210aa'
  '5b93ca84421579d9e979c71df89a55762456d16a13d76f52a8bcf445b48e6bff'
)) {
  if (-not $rendered.Contains($required)) {
    throw "Rendered artifact is missing: $required"
  }
}
if ($rendered.Contains("fetch(")) {
  throw "Rendered artifact contains a browser-side fetch"
}
$publicAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath docs\index.html).Hash.ToLowerInvariant()
if ($publicAfter -ne $publicBefore) {
  throw "Tracked public page changed: $publicAfter"
}
if (git status --porcelain=v1) { throw "Tracked worktree changed during rendering" }
$counts
$publicAfter
git check-ignore -v $reviewOutput
~~~

Expected: counts are exactly 447/32/113/182/120; all required disclosure text and hashes exist; no `fetch(` exists; the public hash is unchanged; Git reports the review artifact is ignored by the `output/` rule.

- [ ] **Step 6: Start a loopback-only local server**

Run:

~~~powershell
$port = 8765
if (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue) {
  throw "Port $port is already in use"
}
$server = Start-Process -FilePath python `
  -ArgumentList @("-m", "http.server", "$port", "--bind", "127.0.0.1", "--directory", $reviewRoot) `
  -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1
$response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/index.html"
if ($response.StatusCode -ne 200) { throw "Local preview server failed" }
"Server PID $($server.Id) returned HTTP $($response.StatusCode)"
~~~

Expected: one hidden Python process serves only `127.0.0.1:8765` and returns HTTP 200.

- [ ] **Step 7: Exercise desktop behavior in a real browser**

The Playwright wrapper depends on `npx`. Verify it and open an isolated headed session:

~~~powershell
if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
  throw "Node.js/npm is required for the Playwright wrapper"
}
$gitBash = "C:\Program Files\Git\bin\bash.exe"
$playwrightCli = "/c/Users/Alex/.codex/skills/playwright/scripts/playwright_cli.sh"
& $gitBash $playwrightCli --session pgo-fantasy-week1 open "http://127.0.0.1:8765/index.html" --headed
& $gitBash $playwrightCli --session pgo-fantasy-week1 resize 1440 1000
& $gitBash $playwrightCli --session pgo-fantasy-week1 snapshot
~~~

Expected snapshot: `Fantasy Week 1` is the selected top-level tab; `PREVIEW / HOLD` and all four limitation statements are visible; SUPERFLEX is pressed; the count is 447; default columns are SF#, Player, Pos, Team, Opp., and Proj.

Use DOM-backed checks for exact counts and state:

~~~powershell
$env:PGO_EVAL = 'document.querySelector("#tab-fantasy").getAttribute("aria-selected")'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-result-count").textContent.trim()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("[data-view=QB]").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelectorAll(".fantasy-row:not([hidden])").length'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("[data-view=RB]").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelectorAll(".fantasy-row:not([hidden])").length'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("[data-view=WR]").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelectorAll(".fantasy-row:not([hidden])").length'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("[data-view=TE]").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelectorAll(".fantasy-row:not([hidden])").length'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("[data-view=FLEX]").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelectorAll(".fantasy-row:not([hidden])").length'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("[data-view=SUPERFLEX]").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelectorAll(".fantasy-row:not([hidden])").length'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
~~~

Expected read values, in order: `true`, `447 players shown`, `32`, `113`, `182`, `120`, `415`, and `447`. Mutation calls may also print `undefined`.

Exercise search and team filtering:

~~~powershell
$env:PGO_EVAL = 'document.querySelector("#fantasy-player-search").value="Trevor\u0020Lawrence"'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-player-search").dispatchEvent(new/**/Event("input"))'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-result-count").textContent.trim()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-player-search").value=""'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-player-search").dispatchEvent(new/**/Event("input"))'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-team").value="JAX"'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-team").dispatchEvent(new/**/Event("change"))'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelectorAll(".fantasy-row:not([hidden])").length'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-team").value=""'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-team").dispatchEvent(new/**/Event("change"))'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-result-count").textContent.trim()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
~~~

Expected read values: `1 player shown`, `14`, and `447 players shown`. Mutation calls may also print their assigned value, `true`, or `undefined`.

Exercise projection sorting, expanded columns, and top-level keyboard navigation:

~~~powershell
$env:PGO_EVAL = 'document.querySelector(".fantasy-sort[data-column=''5'']").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector(".fantasy-row:not([hidden])\u0020.fantasy-player").textContent.trim()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-columns").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'getComputedStyle(document.querySelector(".fantasy-technical")).display'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#tab-fantasy").focus()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
& $gitBash $playwrightCli --session pgo-fantasy-week1 press ArrowRight
$env:PGO_EVAL = 'document.querySelector("#tab-ratings").getAttribute("aria-selected")'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
& $gitBash $playwrightCli --session pgo-fantasy-week1 press ArrowLeft
$env:PGO_EVAL = 'document.querySelector("#tab-fantasy").getAttribute("aria-selected")'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
~~~

Expected read values: `Trevor Lawrence`; a display value other than `none`; `true` for McCabe Ratings after ArrowRight; and `true` for Fantasy Week 1 after ArrowLeft. Mutation calls may also print `undefined`. Visually confirm focus indicators remain visible.

- [ ] **Step 8: Exercise mobile layout and close local processes**

Run:

~~~powershell
$env:PGO_EVAL = 'document.querySelector("#fantasy-columns").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
& $gitBash $playwrightCli --session pgo-fantasy-week1 resize 390 844
& $gitBash $playwrightCli --session pgo-fantasy-week1 snapshot
$env:PGO_EVAL = 'document.documentElement.scrollWidth===document.documentElement.clientWidth'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#panel-fantasy\u0020.fantasy-table").scrollWidth<=document.querySelector("#panel-fantasy\u0020.table-shell").clientWidth'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#fantasy-columns").click()'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.documentElement.scrollWidth===document.documentElement.clientWidth'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
$env:PGO_EVAL = 'document.querySelector("#panel-fantasy\u0020.fantasy-table").scrollWidth>document.querySelector("#panel-fantasy\u0020.table-shell").clientWidth'
& $gitBash -lc '"$1" --session pgo-fantasy-week1 eval "$PGO_EVAL"' _ $playwrightCli
& $gitBash $playwrightCli --session pgo-fantasy-week1 requests --static
& $gitBash $playwrightCli --session pgo-fantasy-week1 close
Stop-Process -Id $server.Id
~~~

Expected: the compact view produces no page or table overflow at 390 pixels; expanded columns stay inside a horizontally scrollable table shell while the page itself still does not overflow. Network output may contain the document and Google Fonts, but must contain no JSON path, evidence path, API call, or rankings fetch. Only the exact local server process started in Step 6 is stopped.

- [ ] **Step 9: Record the final local handoff and stop**

Run:

~~~powershell
$publicFinal = (Get-FileHash -Algorithm SHA256 -LiteralPath docs\index.html).Hash.ToLowerInvariant()
$status = @(git status --porcelain=v1)
if ($publicFinal -ne "5094ad484807bacb8ce5dddf19cff38798ed86a07c1501d1bcbf09f84dd932fe") {
  throw "Public page changed: $publicFinal"
}
if ($status.Count) { throw "Worktree is not clean: $status" }
[pscustomobject]@{
  ReviewArtifact = $reviewOutput
  SourceSha256 = $sourceHash
  PublicPageSha256 = $publicFinal
  GitHead = (git rev-parse HEAD).Trim()
  Worktree = "clean"
  Published = $false
} | Format-List
~~~

Expected: the exact review-artifact path is recorded, the source and public hashes match, the worktree is clean, and `Published` is `False`. Hand the local artifact to the user for visual approval. Do not add a publish flag, update `docs/index.html`, push, deploy, or touch Shopify.

---

## Final Review Checklist

- [ ] The implementation changed only the plan, two runtime files, and their two existing test files.
- [ ] `load_week1_preview()` rejects malformed JSON, non-canonical bytes, contract drift, incomplete coverage, row drift, rank drift, and an invalid embedded hash.
- [ ] The qualified source file SHA-256 was independently verified before generation.
- [ ] Only ranking-eligible rows render; the exact real counts are 447 total, 32 QB, 113 RB, 182 WR, and 120 TE.
- [ ] SUPERFLEX is selected first; QB/RB/WR/TE/FLEX membership and view-specific ranks are correct.
- [ ] Default and expanded columns match the approved design.
- [ ] Search, team filter, sorting, dynamic count, and column toggle work in the real browser.
- [ ] Source text is escaped; stable IDs and row-level config hashes are absent from the table; no browser-side data fetch exists.
- [ ] PREVIEW/HOLD, half-PPR, unverified availability, possible pre-lock change, EXPERIMENTAL status, and non-gradeable state are explicit.
- [ ] Tabs, labels, focus, selected state, live regions, sortable-header state, and 390-pixel behavior pass browser inspection.
- [ ] Omitting `--fantasy-preview` preserves legacy injection bytes and existing CLI/workflow behavior.
- [ ] `--fantasy-preview` fails closed with `--publish`, `--refresh-mccabe`, an external output destination, or an input/output alias.
- [ ] Focused tests, public-workflow tests, the complete suite, compilation, and diff checks all pass.
- [ ] `docs/index.html` remains SHA-256 `5094ad484807bacb8ce5dddf19cff38798ed86a07c1501d1bcbf09f84dd932fe`.
- [ ] The final artifact exists only beneath ignored `output/` and no push, deployment, Pages change, or Shopify change occurred.
