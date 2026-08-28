# PGO Fantasy Source Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the exact 13-source fantasy snapshot, audit every 2020-2025 ACT-roster/stat contradiction, and commit a lock-bound qualification receipt only if the real snapshot passes with zero discrepancies.

**Architecture:** Extend the existing `pgo_fantasy.py` module instead of adding a downloader or service. Reuse `pgo_sources.freeze_sources()` and `load_locked_sources()` for raw-byte capture, add a deterministic fantasy lock/receipt contract and strict reconciliation pass, then expose one local CLI with separate freeze and accept actions so research evidence cannot be written before review.

**Tech Stack:** Python standard library, existing `pgo_sources` and `release_ratings` helpers, `unittest`, Git, PowerShell.

## Global Constraints

- Historical scope is exactly regular seasons 2020 through 2025.
- Source inventory is exactly one pinned schedule plus six weekly-roster and six player-weekly-stat files.
- Population eligibility requires an eligible weekly-roster position, stable GSIS ID, and `status == ACT`; player statistics never add population rows.
- Every roster season must contain all exact 32 normalized teams, and every completed scheduled team-week must have roster coverage.
- Any unresolved stat/roster discrepancy produces `BLOCKED`; there is no manual exception allowlist.
- Raw bytes remain ignored under `.cache/pgo_fantasy/`.
- A passing receipt says `artifact_availability: LOCAL_CACHE_ONLY`; no canonical backtest can run until separate immutable-bundle authorization.
- Do not add PFF, injury, practice, inactive, depth-chart, participation, betting, market, or paid-source inputs.
- Do not add a dependency, source module, workflow, public-site change, Shopify change, push, deployment, or publication.
- Preserve all unrelated untracked paths and use exact `git add -- <paths>` allowlists; never use `git add -A`.
- Protect `research/pgo_v1/`, `research/pgo_stability_blend/`, `prospective_evidence/`, `docs/index.html`, and `.github/workflows/`.
- Use UTF-8, LF-only, sorted-key, finite JSON with a terminal newline.
- Existing accepted research paths are no-overwrite.

## File map

- Modify `pgo_fantasy.py`: source-lock contract, reconciliation receipt, freeze/accept CLI, and no-overwrite research promotion.
- Modify `tests/test_pgo_fantasy.py`: synthetic source qualification, byte binding, CLI, and failure-boundary regressions.
- Modify `.gitattributes`: force LF checkout bytes for the two accepted fantasy JSON files.
- Create only after a real `PASS`: `research/pgo_fantasy/sources.lock.json` and `research/pgo_fantasy/source_qualification.json`.

---

### Task 1: Define the fantasy source-lock byte contract

**Files:**
- Modify: `pgo_fantasy.py`
- Modify: `tests/test_pgo_fantasy.py`
- Modify: `.gitattributes`

**Interfaces:**
- Consumes: `fantasy_source_specs()` and a manifest returned by `pgo_sources.freeze_sources()`.
- Produces: `build_fantasy_source_lock(manifest: dict) -> dict`, `serialize_fantasy_source_json(value: dict) -> str`, and `validate_fantasy_source_lock(lock: dict) -> None`.

- [ ] **Step 1: Write the failing lock and LF-contract tests**

Add imports for `subprocess` and `pgo_sources`, then add these tests to
`tests/test_pgo_fantasy.py`:

```python
class FantasySourceLockTests(unittest.TestCase):
    AS_OF = "2026-08-27T12:00:00-04:00"

    @classmethod
    def _manifest(cls):
        return {
            "sources": [
                {
                    "name": spec.name,
                    "season": spec.season,
                    "url": spec.url,
                    "sha256": hashlib.sha256(
                        f"{spec.name}:{spec.season}".encode("utf-8")
                    ).hexdigest(),
                    "bytes": 1,
                    "frozen_at": cls.AS_OF,
                }
                for spec in pgo_fantasy.fantasy_source_specs()
            ]
        }

    def test_builds_exact_deterministic_fantasy_lock(self):
        lock = pgo_fantasy.build_fantasy_source_lock(self._manifest())
        text = pgo_fantasy.serialize_fantasy_source_json(lock)

        self.assertEqual(lock["schema_version"], 1)
        self.assertEqual(lock["scope"], {
            "seasons": [2020, 2021, 2022, 2023, 2024, 2025],
            "game_type": "REG",
            "roster_status": "ACT",
        })
        self.assertEqual(len(lock["sources"]), 13)
        self.assertEqual(text, pgo_fantasy.serialize_fantasy_source_json(
            pgo_fantasy.build_fantasy_source_lock({
                "sources": list(reversed(self._manifest()["sources"]))
            })
        ))
        self.assertNotIn("\r", text)
        self.assertTrue(text.endswith("\n"))
        for entry in lock["sources"]:
            self.assertEqual(set(entry), {
                "name", "season", "url", "sha256", "bytes", "frozen_at",
                "cache_path", "required_columns", "allowed_scope",
            })
            self.assertTrue(entry["cache_path"].startswith(".cache/pgo_fantasy/"))

    def test_rejects_naive_or_inconsistent_capture_time_and_manifest_drift(self):
        cases = []
        naive = self._manifest()
        naive["sources"][0]["frozen_at"] = "2026-08-27T12:00:00"
        cases.append(naive)
        inconsistent = self._manifest()
        inconsistent["sources"][0]["frozen_at"] = "2026-08-27T13:00:00-04:00"
        cases.append(inconsistent)
        missing = self._manifest()
        missing["sources"].pop()
        cases.append(missing)
        changed_url = self._manifest()
        changed_url["sources"][0]["url"] = "https://example.invalid/source.csv"
        cases.append(changed_url)

        for manifest in cases:
            with self.subTest(manifest=manifest):
                with self.assertRaises(ValueError):
                    pgo_fantasy.build_fantasy_source_lock(manifest)

    def test_fantasy_research_json_has_lf_checkout_attribute(self):
        result = subprocess.run(
            [
                "git", "check-attr", "eol", "--",
                "research/pgo_fantasy/sources.lock.json",
                "research/pgo_fantasy/source_qualification.json",
            ],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.splitlines(), [
            "research/pgo_fantasy/sources.lock.json: eol: lf",
            "research/pgo_fantasy/source_qualification.json: eol: lf",
        ])
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```powershell
python -m unittest tests.test_pgo_fantasy.FantasySourceLockTests -v
```

Expected: failures because the three source-lock functions do not exist and the fantasy JSON paths have no LF attribute.

- [ ] **Step 3: Implement the minimal deterministic lock contract**

Add the following constants and functions to `pgo_fantasy.py`. Use exact type checks so `True` and `1.0` cannot satisfy integer schema/byte fields.

```python
from datetime import datetime


FANTASY_CACHE_DIR = Path(".cache/pgo_fantasy")
FANTASY_SCOPE = {
    "seasons": list(MODEL_SEASONS),
    "game_type": "REG",
    "roster_status": "ACT",
}


def _parse_frozen_at(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("frozen_at must be a timezone-bearing timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("frozen_at must be a timezone-bearing timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("frozen_at must be a timezone-bearing timestamp")
    return value.strip()


def _cache_name(url, digest):
    suffix = ".csv.gz" if url.lower().endswith(".csv.gz") else ".csv"
    return (FANTASY_CACHE_DIR / f"{digest}{suffix}").as_posix()


def _allowed_scope(spec):
    return {
        "seasons": list(MODEL_SEASONS) if spec.season is None else [spec.season],
        "game_type_field": (
            "season_type" if spec.name == "player_weekly_stats" else "game_type"
        ),
        "game_type_value": "REG",
        "completed_only": spec.name == "schedule_results",
    }


def build_fantasy_source_lock(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"sources"}:
        raise ValueError("Fantasy source manifest is invalid")
    specs = {
        (spec.name, spec.season): spec for spec in fantasy_source_specs()
    }
    entries = manifest["sources"]
    if not isinstance(entries, list):
        raise ValueError("Fantasy source inventory is invalid")
    received = {}
    frozen_values = set()
    required = {"name", "season", "url", "sha256", "bytes", "frozen_at"}
    for source in entries:
        if not isinstance(source, dict) or set(source) != required:
            raise ValueError("Fantasy source entry is invalid")
        name = source["name"]
        season = source["season"]
        if (
            not isinstance(name, str)
            or (season is not None and type(season) is not int)
        ):
            raise ValueError("Fantasy source entry is invalid")
        key = (name, season)
        digest = source["sha256"]
        if (
            key in received
            or key not in specs
            or source["url"] != specs[key].url
            or type(source["bytes"]) is not int
            or source["bytes"] <= 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("Fantasy source entry is invalid")
        frozen = _parse_frozen_at(source["frozen_at"])
        frozen_values.add(frozen)
        received[key] = {
            **source,
            "frozen_at": frozen,
            "cache_path": _cache_name(source["url"], digest),
            "required_columns": list(specs[key].required_columns),
            "allowed_scope": _allowed_scope(specs[key]),
        }
    if set(received) != set(specs) or len(frozen_values) != 1:
        raise ValueError("Fantasy source inventory is incomplete or inconsistent")
    return {
        "schema_version": 1,
        "scope": dict(FANTASY_SCOPE),
        "sources": [received[key] for key in sorted(received, key=_source_key_sort)],
    }


def validate_fantasy_source_lock(lock):
    if not isinstance(lock, dict) or set(lock) != {
        "schema_version", "scope", "sources"
    }:
        raise ValueError("Fantasy source lock is invalid")
    if type(lock["schema_version"]) is not int or lock["schema_version"] != 1:
        raise ValueError("Fantasy source lock schema is invalid")
    if not isinstance(lock["sources"], list):
        raise ValueError("Fantasy source lock sources are invalid")
    try:
        raw_manifest = {
            "sources": [
                {
                    name: entry[name]
                    for name in (
                        "name", "season", "url", "sha256", "bytes", "frozen_at"
                    )
                }
                for entry in lock["sources"]
            ]
        }
    except (KeyError, TypeError) as error:
        raise ValueError("Fantasy source lock sources are invalid") from error
    if lock != build_fantasy_source_lock(raw_manifest):
        raise ValueError("Fantasy source lock contract is invalid")


def serialize_fantasy_source_json(value):
    try:
        return json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise ValueError("Fantasy source evidence must contain finite JSON") from error
```

Append this exact rule to `.gitattributes`:

```gitattributes
research/pgo_fantasy/*.json text eol=lf
```

- [ ] **Step 4: Run GREEN checks**

Run:

```powershell
python -m unittest tests.test_pgo_fantasy.FantasySourceLockTests -v
python -m unittest tests.test_pgo_fantasy -v
git diff --check
```

Expected: all source-lock and existing fantasy tests pass; the diff check is clean.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- .gitattributes pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: define fantasy source qualification contract"
```

Expected staged paths: exactly the three listed files.

---

### Task 2: Reconcile every roster/stat contradiction

**Files:**
- Modify: `pgo_fantasy.py`
- Modify: `tests/test_pgo_fantasy.py`

**Interfaces:**
- Consumes: locked paths from `pgo_sources.load_locked_sources()` and exact serialized bytes from Task 1.
- Produces: `qualify_fantasy_sources(paths: dict, source_lock_text: str) -> dict` and `validate_fantasy_source_qualification(source_lock_text: str, receipt: dict) -> None`.

- [ ] **Step 1: Add a complete synthetic qualification fixture**

Add `CURRENT_TEAMS` to the existing `pgo_model` import in `pgo_fantasy.py`. In `tests/test_pgo_fantasy.py`, add this helper class below `FantasyPopulationTests`:

```python
class FantasyQualificationFixture:
    _row = staticmethod(FantasyPopulationTests._row)

    def _write_sources(self, directory, schedule, rosters, stats):
        return FantasyPopulationTests()._write_sources(
            directory, schedule, rosters, stats
        )

    def _qualification_rows(self):
        schedule = []
        rosters = {season: [] for season in pgo_fantasy.MODEL_SEASONS}
        stats = {season: [] for season in pgo_fantasy.MODEL_SEASONS}
        for season in pgo_fantasy.MODEL_SEASONS:
            game_id = f"{season}_01_BUF_LAR"
            schedule.append(self._row(
                pgo_fantasy.SCHEDULE_COLUMNS,
                game_id=game_id,
                season=str(season),
                week="1",
                game_type="REG",
                gameday=f"{season}-09-08",
                gametime="20:20",
                away_team="BUF",
                home_team="LAR",
                away_score="21",
                home_score="17",
            ))
            for team in pgo_fantasy.CURRENT_TEAMS:
                rosters[season].append(self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season=str(season),
                    week="99",
                    game_type="REG",
                    team=team,
                    position="K",
                    status="ACT",
                    full_name=f"Coverage {team}",
                    gsis_id=f"K-{season}-{team}",
                ))
            for team, opponent, player in (
                ("BUF", "LAR", "BUF-QB"),
                ("LAR", "BUF", "LAR-QB"),
            ):
                rosters[season].append(self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season=str(season),
                    week="1",
                    game_type="REG",
                    team=team,
                    position="QB",
                    status="ACT",
                    full_name=player,
                    gsis_id=f"{player}-{season}",
                ))
                stats[season].append(self._row(
                    pgo_fantasy.PLAYER_COLUMNS,
                    player_id=f"{player}-{season}",
                    position="QB",
                    season=str(season),
                    week="1",
                    season_type="REG",
                    game_id=game_id,
                    team=team,
                    opponent_team=opponent,
                    passing_yards="200",
                ))
        return schedule, rosters, stats

    def _qualification_paths(self, directory, mutate=None):
        Path(directory).mkdir(parents=True, exist_ok=True)
        schedule, rosters, stats = self._qualification_rows()
        if mutate is not None:
            mutate(schedule, rosters, stats)
        return self._write_sources(directory, schedule, rosters, stats)

    @staticmethod
    def _source_lock_text(paths):
        manifest = {"sources": []}
        for spec in pgo_fantasy.fantasy_source_specs():
            data = Path(paths[(spec.name, spec.season)]).read_bytes()
            manifest["sources"].append({
                "name": spec.name,
                "season": spec.season,
                "url": spec.url,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "frozen_at": FantasySourceLockTests.AS_OF,
            })
        return pgo_fantasy.serialize_fantasy_source_json(
            pgo_fantasy.build_fantasy_source_lock(manifest)
        )
```

- [ ] **Step 2: Write failing PASS, multi-discrepancy, and byte-binding tests**

Add:

```python
class FantasySourceQualificationTests(
    FantasyQualificationFixture, unittest.TestCase
):
    def test_clean_sources_pass_without_stat_driven_population_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory)
            lock_text = self._source_lock_text(paths)

            receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)

        self.assertEqual(receipt["qualification_status"], "PASS")
        self.assertEqual(receipt["artifact_availability"], "LOCAL_CACHE_ONLY")
        self.assertEqual(receipt["source_count"], 13)
        self.assertEqual(len(receipt["sources"]), 13)
        self.assertTrue(all(receipt["checks"].values()))
        self.assertEqual(receipt["discrepancies"]["total"], 0)
        self.assertTrue(all(
            count == 0
            for count in receipt["discrepancies"]["counts"].values()
        ))
        self.assertEqual(receipt["coverage"]["2022"]["eligible"], 2)
        pgo_fantasy.validate_fantasy_source_qualification(lock_text, receipt)

    def test_reports_all_discrepancy_classes_deterministically(self):
        def mutate(schedule, rosters, stats):
            season = 2022
            game_id = f"{season}_01_BUF_LAR"
            schedule.append(self._row(
                pgo_fantasy.SCHEDULE_COLUMNS,
                game_id="2022_02_ARI_ATL", season="2022", week="2",
                game_type="REG", gameday="2022-09-18", gametime="13:00",
                away_team="ARI", home_team="ATL", away_score="10",
                home_score="17",
            ))
            rosters[season] = [
                row for row in rosters[season]
                if not (row["team"] == "ARI" and row["position"] == "K")
            ]
            rosters[season].extend([
                self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="BUF",
                    position="WR", status="INA", full_name="Non ACT",
                    gsis_id="NON-ACT",
                ),
                self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="BUF",
                    position="WR", status="ACT", full_name="Position Conflict",
                    gsis_id="POS-CONFLICT",
                ),
                self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="BUF",
                    position="WR", status="ACT", full_name="Duplicate",
                    gsis_id="DUP-ROSTER",
                ),
                self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="LAR",
                    position="WR", status="ACT", full_name="Duplicate",
                    gsis_id="DUP-ROSTER",
                ),
                self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="BUF",
                    position="WR", status="", full_name="Missing Status",
                    gsis_id="MISSING-STATUS",
                ),
                self._row(
                    pgo_fantasy.ROSTER_COLUMNS,
                    season="2022", week="1", game_type="REG", team="BUF",
                    position="WR", status="ACT", full_name="Missing ID",
                    gsis_id="",
                ),
            ])
            stats[season].extend([
                self._row(
                    pgo_fantasy.PLAYER_COLUMNS,
                    player_id="NO-ROSTER", position="WR", season="2022",
                    week="1", season_type="REG", game_id=game_id,
                    team="BUF", opponent_team="LAR", receiving_yards="40",
                ),
                self._row(
                    pgo_fantasy.PLAYER_COLUMNS,
                    player_id="NON-ACT", position="WR", season="2022",
                    week="1", season_type="REG", game_id=game_id,
                    team="BUF", opponent_team="LAR", receiving_yards="40",
                ),
                self._row(
                    pgo_fantasy.PLAYER_COLUMNS,
                    player_id="POS-CONFLICT", position="RB", season="2022",
                    week="1", season_type="REG", game_id=game_id,
                    team="BUF", opponent_team="LAR", rushing_yards="40",
                ),
                self._row(
                    pgo_fantasy.PLAYER_COLUMNS,
                    player_id="BAD-SCHEDULE", position="WR", season="2022",
                    week="1", season_type="REG", game_id=game_id,
                    team="BUF", opponent_team="BUF", receiving_yards="40",
                ),
                self._row(
                    pgo_fantasy.PLAYER_COLUMNS,
                    player_id="", position="WR", season="2022", week="1",
                    season_type="REG", game_id=game_id, team="BUF",
                    opponent_team="LAR", receiving_yards="40",
                ),
            ])
            rosters[season].append(self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022", week="1", game_type="REG", team="BUF",
                position="WR", status="ACT", full_name="Bad Schedule",
                gsis_id="BAD-SCHEDULE",
            ))
            stats[season].append(copy.deepcopy(stats[season][-2]))

        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory, mutate)
            lock_text = self._source_lock_text(paths)
            first = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
            second = pgo_fantasy.qualify_fantasy_sources(
                dict(reversed(list(paths.items()))), lock_text
            )

        self.assertEqual(first, second)
        self.assertEqual(first["qualification_status"], "BLOCKED")
        reasons = {
            row["reason"] for row in first["discrepancies"]["rows"]
        }
        self.assertTrue({
            "incomplete_team_coverage", "missing_roster_identity",
            "incomplete_team_week_coverage",
            "missing_roster_status", "duplicate_roster_identity",
            "conflicting_team", "missing_stat_identity",
            "duplicate_stat_identity", "missing_roster", "non_act_roster",
            "schedule_identity", "position_contradiction",
        }.issubset(reasons))
        with self.assertRaisesRegex(ValueError, "PASS"):
            pgo_fantasy.validate_fantasy_source_qualification(lock_text, first)

    def test_receipt_is_bound_to_exact_lock_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._qualification_paths(directory)
            lock_text = self._source_lock_text(paths)
            receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
        changed_lock = lock_text.replace(
            FantasySourceLockTests.AS_OF,
            "2026-08-27T12:00:01-04:00",
        )
        with self.assertRaisesRegex(ValueError, "hash"):
            pgo_fantasy.validate_fantasy_source_qualification(
                changed_lock, receipt
            )
```

- [ ] **Step 3: Run the tests to verify RED**

Run:

```powershell
python -m unittest tests.test_pgo_fantasy.FantasySourceQualificationTests -v
```

Expected: failures because qualification and receipt validation do not exist.

- [ ] **Step 4: Implement strict reconciliation without changing the model population**

Add these discrepancy names and a single audit path in `pgo_fantasy.py`:

```python
FANTASY_DISCREPANCY_CLASSES = (
    "incomplete_team_coverage",
    "incomplete_team_week_coverage",
    "missing_roster_identity",
    "missing_roster_status",
    "duplicate_roster_identity",
    "conflicting_team",
    "missing_stat_identity",
    "duplicate_stat_identity",
    "missing_roster",
    "non_act_roster",
    "schedule_identity",
    "position_contradiction",
)


def _discrepancy(reason, season, week=0, gsis_id="", game_id="", team=""):
    return {
        "reason": reason,
        "season": season,
        "week": week,
        "gsis_id": gsis_id,
        "game_id": game_id,
        "team": team,
    }


def _discrepancy_key(row):
    return (
        row["reason"], row["season"], row["week"], row["gsis_id"],
        row["game_id"], row["team"],
    )
```

Implement `_reconcile_fantasy_population(source_rows, games, team_weeks)` with two indexes keyed by `(season, week, gsis_id)`. It must:

```python
def _reconcile_fantasy_population(source_rows, games, team_weeks):
    roster_index = {}
    stat_index = {}
    roster_teams = {season: set() for season in MODEL_SEASONS}
    roster_team_weeks = set()
    discrepancies = []

    for source_season in MODEL_SEASONS:
        for row in source_rows[("weekly_rosters", source_season)]:
            season = _integer(row, "season", "roster")
            if season != source_season:
                raise ValueError(
                    f"Roster source-season mismatch: {source_season} != {season}"
                )
            if (row.get("game_type") or "").strip() != "REG":
                continue
            team = normalize_team(row.get("team") or "")
            week = _integer(row, "week", "roster")
            roster_teams[season].add(team)
            roster_team_weeks.add((season, week, team))
            position = POSITION_MAP.get((row.get("position") or "").strip().upper())
            if position is None:
                continue
            gsis_id = (row.get("gsis_id") or "").strip()
            status = (row.get("status") or "").strip().upper()
            if not gsis_id:
                discrepancies.append(_discrepancy(
                    "missing_roster_identity", season, week, team=team
                ))
                continue
            if not status:
                discrepancies.append(_discrepancy(
                    "missing_roster_status", season, week, gsis_id, team=team
                ))
            record = {
                "season": season,
                "week": week,
                "gsis_id": gsis_id,
                "team": team,
                "position": position,
                "status": status,
            }
            roster_index.setdefault((season, week, gsis_id), []).append(record)

    for season in MODEL_SEASONS:
        for team in sorted(set(CURRENT_TEAMS) - roster_teams[season]):
            discrepancies.append(_discrepancy(
                "incomplete_team_coverage", season, team=team
            ))
    for season, week, team in sorted(set(team_weeks) - roster_team_weeks):
        discrepancies.append(_discrepancy(
            "incomplete_team_week_coverage", season, week, team=team
        ))

    for key, records in sorted(roster_index.items()):
        teams = sorted({record["team"] for record in records})
        if len(records) > 1:
            discrepancies.append(_discrepancy(
                "duplicate_roster_identity", *key, team=",".join(teams)
            ))
        if len(teams) > 1:
            discrepancies.append(_discrepancy(
                "conflicting_team", *key, team=",".join(teams)
            ))

    for source_season in MODEL_SEASONS:
        for row in source_rows[("player_weekly_stats", source_season)]:
            season = _integer(row, "season", "stat")
            if season != source_season:
                raise ValueError(
                    f"Stat source-season mismatch: {source_season} != {season}"
                )
            if (row.get("season_type") or "").strip() != "REG":
                continue
            position = POSITION_MAP.get((row.get("position") or "").strip().upper())
            if position is None:
                continue
            week = _integer(row, "week", "stat")
            gsis_id = (row.get("player_id") or "").strip()
            game_id = (row.get("game_id") or "").strip()
            team = normalize_team(row.get("team") or "")
            opponent = normalize_team(row.get("opponent_team") or "")
            if not gsis_id:
                discrepancies.append(_discrepancy(
                    "missing_stat_identity", season, week, game_id=game_id,
                    team=team,
                ))
                continue
            record = {
                "season": season,
                "week": week,
                "gsis_id": gsis_id,
                "game_id": game_id,
                "team": team,
                "opponent": opponent,
                "position": position,
            }
            stat_index.setdefault((season, week, gsis_id), []).append(record)
            game = games.get(game_id)
            if (
                game is None
                or game["season"] != season
                or game["week"] != week
                or {team, opponent} != {game["away"], game["home"]}
                or team == opponent
            ):
                discrepancies.append(_discrepancy(
                    "schedule_identity", season, week, gsis_id, game_id, team
                ))

    for key, records in sorted(stat_index.items()):
        if len(records) > 1:
            discrepancies.append(_discrepancy(
                "duplicate_stat_identity", *key,
                game_id=records[0]["game_id"], team=records[0]["team"],
            ))
        rosters = roster_index.get(key, [])
        for stat in records:
            if not rosters:
                discrepancies.append(_discrepancy(
                    "missing_roster", *key, game_id=stat["game_id"],
                    team=stat["team"],
                ))
                continue
            if len(rosters) != 1:
                continue
            roster = rosters[0]
            if roster["status"] != "ACT":
                discrepancies.append(_discrepancy(
                    "non_act_roster", *key, game_id=stat["game_id"],
                    team=roster["team"],
                ))
            if roster["position"] != stat["position"]:
                discrepancies.append(_discrepancy(
                    "position_contradiction", *key, game_id=stat["game_id"],
                    team=roster["team"],
                ))
            expected = team_weeks.get((key[0], key[1], roster["team"]))
            if (
                roster["team"] != stat["team"]
                or expected != (stat["game_id"], stat["opponent"])
            ):
                discrepancies.append(_discrepancy(
                    "schedule_identity", *key, game_id=stat["game_id"],
                    team=stat["team"],
                ))

    rows = sorted(
        {tuple(sorted(row.items())) for row in discrepancies},
        key=lambda items: _discrepancy_key(dict(items)),
    )
    rows = [dict(items) for items in rows]
    counts = {
        reason: sum(row["reason"] == reason for row in rows)
        for reason in FANTASY_DISCREPANCY_CLASSES
    }
    by_season = {
        str(season): {
            reason: sum(
                row["season"] == season and row["reason"] == reason
                for row in rows
            )
            for reason in FANTASY_DISCREPANCY_CLASSES
        }
        for season in MODEL_SEASONS
    }
    return {"total": len(rows), "counts": counts, "by_season": by_season, "rows": rows}
```

After reconciliation, call `build_player_games(paths)` only when `total == 0`; this preserves its existing fail-closed behavior and produces authoritative coverage. For blocked diagnostics, compute roster eligibility, matched-stat, zero-fill, and bye counts from the same indexes without adding stat-only keys. Build the receipt with exact lock-byte binding:

```python
def qualify_fantasy_sources(paths, source_lock_text):
    try:
        lock = json.loads(source_lock_text)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("Fantasy source lock is invalid JSON") from error
    validate_fantasy_source_lock(lock)
    source_rows, source_receipts = _load_source_rows(paths)
    locked = {
        (entry["name"], entry["season"]): entry for entry in lock["sources"]
    }
    for source in source_receipts:
        entry = locked[(source["name"], source["season"])]
        if source["bytes"] != entry["bytes"] or source["sha256"] != entry["sha256"]:
            raise ValueError("Fantasy source bytes do not match the lock")
    games, team_weeks = _load_schedule(source_rows[("schedule_results", None)])
    discrepancies = _reconcile_fantasy_population(
        source_rows, games, team_weeks
    )
    if discrepancies["total"] == 0:
        _, model_audit = build_player_games(paths)
        coverage = model_audit["coverage"]
    else:
        coverage = _blocked_coverage(source_rows, team_weeks)
    checks = {
        "source_contract": True,
        "locked_bytes": True,
        "schedule_identity": discrepancies["counts"]["schedule_identity"] == 0,
        "team_coverage": all(
            discrepancies["counts"][name] == 0
            for name in (
                "incomplete_team_coverage", "incomplete_team_week_coverage",
            )
        ),
        "roster_identity": all(
            discrepancies["counts"][name] == 0
            for name in (
                "missing_roster_identity", "missing_roster_status",
                "duplicate_roster_identity", "conflicting_team",
            )
        ),
        "stat_identity": all(
            discrepancies["counts"][name] == 0
            for name in ("missing_stat_identity", "duplicate_stat_identity")
        ),
        "population_reconciliation": discrepancies["total"] == 0,
        "finite_targets": discrepancies["total"] == 0,
    }
    return {
        "schema_version": 1,
        "qualification_status": (
            "PASS" if all(checks.values()) else "BLOCKED"
        ),
        "artifact_availability": "LOCAL_CACHE_ONLY",
        "source_lock_sha256": hashlib.sha256(
            source_lock_text.encode("utf-8")
        ).hexdigest(),
        "scope": dict(FANTASY_SCOPE),
        "source_count": len(source_receipts),
        "sources": source_receipts,
        "checks": checks,
        "coverage": coverage,
        "discrepancies": discrepancies,
    }
```

Implement `_blocked_coverage()` as the roster-only counterpart of
`_load_rosters`. It never unions a stat key into `eligible`:

```python
def _blocked_coverage(source_rows, team_weeks):
    coverage = {
        str(season): {
            "eligible": 0,
            "matched_stats": 0,
            "zero_filled": 0,
            "bye_skipped": 0,
        }
        for season in MODEL_SEASONS
    }
    stat_index = {}
    for source_season in MODEL_SEASONS:
        for row in source_rows[("player_weekly_stats", source_season)]:
            if (row.get("season_type") or "").strip() != "REG":
                continue
            position = POSITION_MAP.get(
                (row.get("position") or "").strip().upper()
            )
            gsis_id = (row.get("player_id") or "").strip()
            if position is None or not gsis_id:
                continue
            season = _integer(row, "season", "stat")
            week = _integer(row, "week", "stat")
            stat_index.setdefault((season, week, gsis_id), []).append({
                "game_id": (row.get("game_id") or "").strip(),
                "team": normalize_team(row.get("team") or ""),
                "opponent": normalize_team(row.get("opponent_team") or ""),
                "position": position,
            })

    for source_season in MODEL_SEASONS:
        for row in source_rows[("weekly_rosters", source_season)]:
            if (row.get("game_type") or "").strip() != "REG":
                continue
            position = POSITION_MAP.get(
                (row.get("position") or "").strip().upper()
            )
            status = (row.get("status") or "").strip().upper()
            gsis_id = (row.get("gsis_id") or "").strip()
            if position is None or status != "ACT" or not gsis_id:
                continue
            season = _integer(row, "season", "roster")
            week = _integer(row, "week", "roster")
            team = normalize_team(row.get("team") or "")
            expected = team_weeks.get((season, week, team))
            values = coverage[str(season)]
            if expected is None:
                values["bye_skipped"] += 1
                continue
            values["eligible"] += 1
            candidates = stat_index.get((season, week, gsis_id), [])
            matched = (
                len(candidates) == 1
                and candidates[0]["game_id"] == expected[0]
                and candidates[0]["team"] == team
                and candidates[0]["opponent"] == expected[1]
                and candidates[0]["position"] == position
            )
            values["matched_stats" if matched else "zero_filled"] += 1
    return coverage
```

Validate the exact receipt schema, `PASS`, all-true checks, zero discrepancy counts/rows, finite canonical JSON, and exact lock SHA-256:

```python
def validate_fantasy_source_qualification(source_lock_text, receipt):
    required = {
        "schema_version", "qualification_status", "artifact_availability",
        "source_lock_sha256", "scope", "source_count", "sources", "checks",
        "coverage", "discrepancies",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ValueError("Fantasy source qualification receipt is invalid")
    try:
        lock = json.loads(source_lock_text)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("Fantasy source lock is invalid JSON") from error
    validate_fantasy_source_lock(lock)
    expected_hash = hashlib.sha256(source_lock_text.encode("utf-8")).hexdigest()
    if receipt["source_lock_sha256"] != expected_hash:
        raise ValueError("Fantasy source qualification lock hash changed")
    expected_checks = {
        "source_contract", "locked_bytes", "schedule_identity",
        "team_coverage", "roster_identity", "stat_identity",
        "population_reconciliation", "finite_targets",
    }
    discrepancies = receipt.get("discrepancies")
    coverage = receipt.get("coverage")
    if (
        type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or receipt["qualification_status"] != "PASS"
        or receipt["artifact_availability"] != "LOCAL_CACHE_ONLY"
        or receipt["scope"] != FANTASY_SCOPE
        or type(receipt["source_count"]) is not int
        or receipt["source_count"] != 13
        or not isinstance(receipt["sources"], list)
        or len(receipt["sources"]) != 13
        or not isinstance(receipt["checks"], dict)
        or set(receipt["checks"]) != expected_checks
        or not all(value is True for value in receipt["checks"].values())
        or not isinstance(discrepancies, dict)
        or set(discrepancies) != {"total", "counts", "by_season", "rows"}
        or type(discrepancies["total"]) is not int
        or discrepancies["total"] != 0
        or discrepancies["rows"] != []
        or not isinstance(discrepancies["counts"], dict)
        or set(discrepancies["counts"]) != set(FANTASY_DISCREPANCY_CLASSES)
        or any(type(value) is not int or value != 0
               for value in discrepancies["counts"].values())
        or not isinstance(discrepancies["by_season"], dict)
        or set(discrepancies["by_season"]) != {
            str(season) for season in MODEL_SEASONS
        }
        or not isinstance(coverage, dict)
        or set(coverage) != {str(season) for season in MODEL_SEASONS}
    ):
        raise ValueError("Fantasy source qualification is not PASS")
    locked = {
        (entry["name"], entry["season"]): entry for entry in lock["sources"]
    }
    received = set()
    received_order = []
    for source in receipt["sources"]:
        if not isinstance(source, dict) or set(source) != {
            "name", "season", "bytes", "sha256", "rows"
        }:
            raise ValueError("Fantasy source qualification is not PASS")
        key = (source["name"], source["season"])
        if (
            key in received
            or key not in locked
            or type(source["bytes"]) is not int
            or source["bytes"] != locked[key]["bytes"]
            or source["sha256"] != locked[key]["sha256"]
            or type(source["rows"]) is not int
            or source["rows"] <= 0
        ):
            raise ValueError("Fantasy source qualification is not PASS")
        received.add(key)
        received_order.append(key)
    if (
        received != set(locked)
        or received_order != sorted(received_order, key=_source_key_sort)
    ):
        raise ValueError("Fantasy source qualification is not PASS")
    for season in MODEL_SEASONS:
        season_discrepancies = discrepancies["by_season"][str(season)]
        values = coverage[str(season)]
        if (
            not isinstance(season_discrepancies, dict)
            or set(season_discrepancies) != set(FANTASY_DISCREPANCY_CLASSES)
            or any(type(value) is not int or value != 0
                   for value in season_discrepancies.values())
            or not isinstance(values, dict)
            or set(values) != {
                "eligible", "matched_stats", "zero_filled", "bye_skipped"
            }
            or any(type(value) is not int or value < 0 for value in values.values())
            or values["matched_stats"] + values["zero_filled"]
            != values["eligible"]
        ):
            raise ValueError("Fantasy source qualification is not PASS")
    serialize_fantasy_source_json(receipt)
```

- [ ] **Step 5: Run GREEN and unchanged-model checks**

Run:

```powershell
python -m unittest tests.test_pgo_fantasy.FantasySourceQualificationTests -v
python -m unittest tests.test_pgo_fantasy.FantasyPopulationTests -v
python -m unittest tests.test_pgo_fantasy.FantasyBaselineTests -v
python -m unittest tests.test_pgo_fantasy.FantasyReceiptTests -v
git diff --check
```

Expected: all tests pass; the existing unmatched-stat test still raises instead of expanding the model population.

- [ ] **Step 6: Commit Task 2**

```powershell
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: reconcile fantasy source population"
```

Expected staged paths: exactly `pgo_fantasy.py` and `tests/test_pgo_fantasy.py`.

---

### Task 3: Add freeze, diagnostic, and no-overwrite acceptance commands

**Files:**
- Modify: `pgo_fantasy.py`
- Modify: `tests/test_pgo_fantasy.py`

**Interfaces:**
- Consumes: Task 1 lock bytes, Task 2 qualification receipt, and the fixed local paths below.
- Produces: `main(argv: list[str] | None = None) -> int`, where freeze returns `0` for `PASS`, `1` for `BLOCKED`, and `2` for operational failure; accept returns `0` only after exact offline requalification and no-overwrite directory publication.

- [ ] **Step 1: Write failing CLI and write-boundary tests**

Add these exact imports, then add a payload helper that turns the complete
fixture into the URL-keyed bytes expected by `freeze_sources()`:

```python
import gzip
import io
import os
from contextlib import redirect_stderr
from unittest.mock import patch
```

Add:

```python
class FantasySourceCommandTests(FantasyQualificationFixture, unittest.TestCase):
    AS_OF = FantasySourceLockTests.AS_OF

    def _payloads(self, root, mutate=None):
        paths = self._qualification_paths(root / "fixtures", mutate)
        payloads = {}
        for spec in pgo_fantasy.fantasy_source_specs():
            data = paths[(spec.name, spec.season)].read_bytes()
            if spec.url.lower().endswith(".csv.gz"):
                data = gzip.compress(data, mtime=0)
            payloads[spec.url] = data
        return payloads

    def _run_in_root(self, root, argv, payloads=None):
        original = pgo_sources.freeze_sources

        def freeze(specs, cache_dir, lock_path, frozen_at):
            return original(
                specs, cache_dir, lock_path, frozen_at,
                fetch=payloads.__getitem__,
            )

        previous = Path.cwd()
        os.chdir(root)
        try:
            if payloads is None:
                return pgo_fantasy.main(argv)
            schedule = next(
                spec for spec in pgo_fantasy.fantasy_source_specs()
                if spec.name == "schedule_results"
            )
            digest = hashlib.sha256(payloads[schedule.url]).hexdigest()
            with (
                patch.object(pgo_sources, "EXPECTED_SOURCE_SHA256", digest),
                patch.object(pgo_sources, "freeze_sources", side_effect=freeze),
            ):
                return pgo_fantasy.main(argv)
        finally:
            os.chdir(previous)

    def test_freeze_writes_local_pass_but_not_research(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            code = self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            )
            receipt = json.loads((
                root / "output/pgo-fantasy-source-qualification.json"
            ).read_text(encoding="utf-8"))
            lock_text = (
                root / "output/pgo-fantasy-source-candidate.lock.json"
            ).read_text(encoding="utf-8")

            self.assertEqual(code, 0)
            self.assertEqual(receipt["qualification_status"], "PASS")
            pgo_fantasy.validate_fantasy_source_qualification(lock_text, receipt)
            self.assertFalse((root / "research/pgo_fantasy").exists())

    def test_blocked_freeze_writes_diagnostic_but_not_research(self):
        def unmatched(schedule, rosters, stats):
            stats[2022].append({
                **stats[2022][0],
                "player_id": "NO-ROSTER",
                "position": "WR",
            })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root, unmatched)
            code = self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            )
            receipt = json.loads((
                root / "output/pgo-fantasy-source-qualification.json"
            ).read_text(encoding="utf-8"))

            self.assertEqual(code, 1)
            self.assertEqual(receipt["qualification_status"], "BLOCKED")
            self.assertGreater(receipt["discrepancies"]["total"], 0)
            self.assertFalse((root / "research/pgo_fantasy").exists())

    def test_accept_requalifies_offline_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            self.assertEqual(self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            ), 0)
            with patch.object(pgo_sources, "freeze_sources") as freeze:
                self.assertEqual(self._run_in_root(
                    root, ["--accept-qualified"]
                ), 0)
                freeze.assert_not_called()
            accepted = root / "research/pgo_fantasy"
            self.assertEqual(
                sorted(path.name for path in accepted.iterdir()),
                ["source_qualification.json", "sources.lock.json"],
            )
            before = {
                path.name: path.read_bytes() for path in accepted.iterdir()
            }
            error = io.StringIO()
            with redirect_stderr(error):
                second = self._run_in_root(root, ["--accept-qualified"])
            self.assertEqual(second, 2)
            self.assertEqual(before, {
                path.name: path.read_bytes() for path in accepted.iterdir()
            })

    def test_preflight_rejects_bad_time_or_existing_candidate_before_fetch(self):
        for argv, existing in (
            (["--freeze-sources", "--frozen-at", "not-a-time"], False),
            (["--freeze-sources", "--frozen-at", self.AS_OF], True),
        ):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if existing:
                    path = root / "output/pgo-fantasy-source-candidate.lock.json"
                    path.parent.mkdir(parents=True)
                    path.write_text("existing\n", encoding="utf-8")
                previous = Path.cwd()
                os.chdir(root)
                try:
                    with patch.object(pgo_sources, "freeze_sources") as freeze:
                        code = pgo_fantasy.main(argv)
                    self.assertEqual(code, 2)
                    freeze.assert_not_called()
                finally:
                    os.chdir(previous)

    def test_operational_freeze_failure_writes_blocked_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                with patch.object(
                    pgo_sources, "freeze_sources", side_effect=OSError("offline")
                ):
                    code = pgo_fantasy.main([
                        "--freeze-sources", "--frozen-at", self.AS_OF,
                    ])
            finally:
                os.chdir(previous)
            receipt = json.loads((
                root / "output/pgo-fantasy-source-qualification.json"
            ).read_text(encoding="utf-8"))
            self.assertEqual(code, 2)
            self.assertEqual(receipt["qualification_status"], "BLOCKED")
            self.assertEqual(receipt["error"], "OSError: offline")
            self.assertFalse((root / "research/pgo_fantasy").exists())

    def test_accept_write_failure_leaves_no_partial_research_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = self._payloads(root)
            self.assertEqual(self._run_in_root(
                root,
                ["--freeze-sources", "--frozen-at", self.AS_OF],
                payloads,
            ), 0)
            original = pgo_fantasy.atomic_write_text
            calls = 0

            def fail_second(path, text):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("second write failed")
                return original(path, text)

            previous = Path.cwd()
            os.chdir(root)
            try:
                with patch.object(
                    pgo_fantasy, "atomic_write_text", side_effect=fail_second
                ):
                    code = pgo_fantasy.main(["--accept-qualified"])
            finally:
                os.chdir(previous)
            self.assertEqual(code, 2)
            self.assertFalse((root / "research/pgo_fantasy").exists())
            self.assertEqual(list((root / "research").iterdir()), [])
```

- [ ] **Step 2: Run CLI tests to verify RED**

Run:

```powershell
python -m unittest tests.test_pgo_fantasy.FantasySourceCommandTests -v
```

Expected: failures because the command interface and acceptance writer do not exist.

- [ ] **Step 3: Implement the fixed local command boundary**

Add standard-library imports `argparse`, `os`, `sys`, and `tempfile`; import `pgo_sources` and `atomic_write_text`. Define fixed paths:

```python
FANTASY_CANDIDATE_LOCK = Path(
    "output/pgo-fantasy-source-candidate.lock.json"
)
FANTASY_QUALIFICATION_OUTPUT = Path(
    "output/pgo-fantasy-source-qualification.json"
)
FANTASY_ACCEPTED_DIR = Path("research/pgo_fantasy")
```

Freeze to a temporary lock, enrich it, reload the exact cache, qualify, and then write only ignored candidate outputs:

```python
def _freeze_and_qualify(frozen_at):
    _parse_frozen_at(frozen_at)
    for path in (FANTASY_CANDIDATE_LOCK, FANTASY_QUALIFICATION_OUTPUT):
        if path.exists():
            raise ValueError(f"Refusing to replace existing candidate output: {path}")
    if FANTASY_ACCEPTED_DIR.exists():
        raise ValueError("Accepted fantasy source evidence already exists")
    FANTASY_CANDIDATE_LOCK.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=FANTASY_CANDIDATE_LOCK.parent,
        prefix=".pgo-fantasy-source-",
        suffix=".pending",
    )
    os.close(descriptor)
    staged = Path(name)
    staged.unlink()
    try:
        manifest = pgo_sources.freeze_sources(
            fantasy_source_specs(), FANTASY_CACHE_DIR, staged, frozen_at
        )
        lock = build_fantasy_source_lock(manifest)
        lock_text = serialize_fantasy_source_json(lock)
        staged.write_text(lock_text, encoding="utf-8", newline="")
        paths = pgo_sources.load_locked_sources(staged, FANTASY_CACHE_DIR)
        receipt = qualify_fantasy_sources(paths, lock_text)
        atomic_write_text(FANTASY_CANDIDATE_LOCK, lock_text)
        atomic_write_text(
            FANTASY_QUALIFICATION_OUTPUT,
            serialize_fantasy_source_json(receipt),
        )
        return receipt
    finally:
        staged.unlink(missing_ok=True)
```

Accept only an exact `PASS`, re-read every cached hash, recompute the receipt
offline, and reserve the accepted directory with one exclusive `mkdir`. Clean
up the two exact owned files on any `BaseException` so an interrupted write
cannot leave a partial accepted directory:

```python
def _accept_qualified_sources():
    lock_text = FANTASY_CANDIDATE_LOCK.read_text(encoding="utf-8")
    receipt_text = FANTASY_QUALIFICATION_OUTPUT.read_text(encoding="utf-8")
    lock = json.loads(lock_text)
    receipt = json.loads(receipt_text)
    validate_fantasy_source_lock(lock)
    validate_fantasy_source_qualification(lock_text, receipt)
    paths = pgo_sources.load_locked_sources(
        FANTASY_CANDIDATE_LOCK, FANTASY_CACHE_DIR
    )
    recomputed = qualify_fantasy_sources(paths, lock_text)
    if serialize_fantasy_source_json(recomputed) != receipt_text:
        raise ValueError("Fantasy source qualification does not reproduce")
    if FANTASY_ACCEPTED_DIR.exists():
        raise ValueError("Accepted fantasy source evidence already exists")
    FANTASY_ACCEPTED_DIR.parent.mkdir(parents=True, exist_ok=True)
    FANTASY_ACCEPTED_DIR.mkdir()
    try:
        atomic_write_text(
            FANTASY_ACCEPTED_DIR / "sources.lock.json", lock_text
        )
        atomic_write_text(
            FANTASY_ACCEPTED_DIR / "source_qualification.json", receipt_text
        )
    except BaseException:
        for name in ("sources.lock.json", "source_qualification.json"):
            (FANTASY_ACCEPTED_DIR / name).unlink(missing_ok=True)
        FANTASY_ACCEPTED_DIR.rmdir()
        raise
```

Add parsing and return codes:

```python
def parse_qualification_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--freeze-sources", action="store_true")
    action.add_argument("--accept-qualified", action="store_true")
    parser.add_argument("--frozen-at")
    return parser.parse_args(argv)


def _operational_blocked_receipt(error):
    return {
        "schema_version": 1,
        "qualification_status": "BLOCKED",
        "artifact_availability": "LOCAL_CACHE_ONLY",
        "error": f"{type(error).__name__}: {error}",
    }


def main(argv=None):
    args = parse_qualification_args(argv)
    try:
        if args.freeze_sources:
            if args.frozen_at is None:
                raise ValueError("--frozen-at is required with --freeze-sources")
            receipt = _freeze_and_qualify(args.frozen_at)
            status = receipt["qualification_status"]
            print(f"{status}: PGO fantasy source qualification")
            return 0 if status == "PASS" else 1
        if args.frozen_at is not None:
            raise ValueError("--frozen-at is valid only with --freeze-sources")
        _accept_qualified_sources()
        print("PASS: accepted PGO fantasy source qualification")
        return 0
    except (
        AttributeError, csv.Error, json.JSONDecodeError, KeyError, OSError,
        OverflowError, TypeError, UnicodeError, ValueError,
    ) as error:
        if (
            args.freeze_sources
            and not FANTASY_CANDIDATE_LOCK.exists()
            and not FANTASY_QUALIFICATION_OUTPUT.exists()
        ):
            try:
                FANTASY_QUALIFICATION_OUTPUT.parent.mkdir(
                    parents=True, exist_ok=True
                )
                atomic_write_text(
                    FANTASY_QUALIFICATION_OUTPUT,
                    serialize_fantasy_source_json(
                        _operational_blocked_receipt(error)
                    ),
                )
            except OSError:
                pass
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

Do not catch `KeyboardInterrupt` or `SystemExit`. The staged accepted directory cleanup runs under `finally`, while an already published directory is never treated as staging.

- [ ] **Step 4: Run CLI GREEN and failure-boundary checks**

Run:

```powershell
python -m unittest tests.test_pgo_fantasy.FantasySourceCommandTests -v
python -m unittest tests.test_pgo_fantasy -v
python -m py_compile pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --check
```

Expected: all commands pass; blocked and operational failures create no research directory; accept is offline and no-overwrite.

- [ ] **Step 5: Commit Task 3**

```powershell
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: qualify frozen fantasy sources"
```

Expected staged paths: exactly `pgo_fantasy.py` and `tests/test_pgo_fantasy.py`.

---

### Task 4: Freeze and gate the real nflverse snapshot

**Files:**
- Read/write ignored: `.cache/pgo_fantasy/`
- Read/write ignored: `output/pgo-fantasy-source-candidate.lock.json`
- Read/write ignored: `output/pgo-fantasy-source-qualification.json`
- Create only on `PASS`: `research/pgo_fantasy/sources.lock.json`
- Create only on `PASS`: `research/pgo_fantasy/source_qualification.json`

**Interfaces:**
- Consumes: the Task 3 CLI and current bytes at the 13 declared canonical URLs.
- Produces: either a local `BLOCKED` diagnostic and hard stop, or the two committed `LOCAL_CACHE_ONLY` research artifacts.

- [ ] **Step 1: Preflight the checkout and protected paths**

Run:

```powershell
git status --short --branch
git rev-parse HEAD
if (Test-Path research/pgo_fantasy) { throw 'research/pgo_fantasy already exists' }
if (Test-Path output/pgo-fantasy-source-candidate.lock.json) { throw 'candidate lock already exists' }
if (Test-Path output/pgo-fantasy-source-qualification.json) { throw 'candidate receipt already exists' }
git diff --exit-code dec6ef1 -- research/pgo_v1 research/pgo_stability_blend docs/index.html .github/workflows
```

Expected: branch `main`; only the known unrelated untracked paths are present; accepted/candidate fantasy paths do not exist; protected diff is empty.

- [ ] **Step 2: Capture one timestamp and freeze once**

Run:

```powershell
$fantasyFrozenAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
python pgo_fantasy.py --freeze-sources --frozen-at $fantasyFrozenAt
$fantasyFreezeExit = $LASTEXITCODE
if ($fantasyFreezeExit -notin 0,1) { throw "Source qualification failed operationally: $fantasyFreezeExit" }
$fantasyFrozenAt
```

Expected: exit `0` with `PASS` or exit `1` with `BLOCKED`. The timestamp has an explicit UTC offset. Never rerun merely to seek different source bytes.

- [ ] **Step 3: Inspect and independently recompute the candidate evidence**

Run:

```powershell
@'
import hashlib
import json
from pathlib import Path

lock_path = Path("output/pgo-fantasy-source-candidate.lock.json")
receipt_path = Path("output/pgo-fantasy-source-qualification.json")
lock_bytes = lock_path.read_bytes()
lock = json.loads(lock_bytes)
receipt = json.loads(receipt_path.read_bytes())
assert lock["schema_version"] == 1
assert len(lock["sources"]) == 13
assert receipt["source_lock_sha256"] == hashlib.sha256(lock_bytes).hexdigest()
assert receipt["artifact_availability"] == "LOCAL_CACHE_ONLY"
assert all(entry["frozen_at"] == lock["sources"][0]["frozen_at"] for entry in lock["sources"])
print(receipt["qualification_status"])
print(json.dumps(receipt["discrepancies"], indent=2, sort_keys=True))
'@ | python -
```

Expected: the lock has 13 sources, the receipt binds the exact lock bytes, and the complete discrepancy inventory prints.

- [ ] **Step 4: Enforce the PASS/BLOCKED stop**

If `$fantasyFreezeExit -eq 1` or the receipt status is `BLOCKED`, stop this plan here:

```powershell
git status --short
git diff --exit-code dec6ef1 -- research/pgo_v1 research/pgo_stability_blend docs/index.html .github/workflows
```

Expected: no `research/pgo_fantasy/` directory, no staged cache/output files, and no protected diff. Report the exact sorted discrepancy classes and identities. Do not create an exception allowlist, alter ACT semantics, run the backtest, or commit a source lock.

If and only if the receipt is `PASS`, continue:

```powershell
python pgo_fantasy.py --accept-qualified
if ($LASTEXITCODE -ne 0) { throw 'Accepted-source publication failed' }
```

Expected: `research/pgo_fantasy/` appears with exactly the two approved files, copied from the revalidated local candidate without another network fetch.

- [ ] **Step 5: Verify and commit passing research evidence**

Run only after `PASS`:

```powershell
@'
import hashlib
import json
from pathlib import Path

root = Path("research/pgo_fantasy")
assert sorted(path.name for path in root.iterdir()) == [
    "source_qualification.json", "sources.lock.json"
]
lock_bytes = (root / "sources.lock.json").read_bytes()
receipt = json.loads((root / "source_qualification.json").read_bytes())
assert b"\r" not in lock_bytes
assert b"\r" not in (root / "source_qualification.json").read_bytes()
assert receipt["qualification_status"] == "PASS"
assert receipt["artifact_availability"] == "LOCAL_CACHE_ONLY"
assert receipt["source_lock_sha256"] == hashlib.sha256(lock_bytes).hexdigest()
assert receipt["discrepancies"]["total"] == 0
assert not any(receipt["discrepancies"]["counts"].values())
assert all(receipt["checks"].values())
print(hashlib.sha256(lock_bytes).hexdigest())
'@ | python -
git add -- research/pgo_fantasy/sources.lock.json research/pgo_fantasy/source_qualification.json
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 2) { throw "Unexpected staged paths: $($staged -join ', ')" }
git diff --cached --check
git commit -m "data: lock qualified fantasy sources"
```

Expected: both files validate, contain LF only, and are committed together with no other staged path.

---

### Task 5: Run the final stability and scope gate

**Files:**
- Verify only: `.gitattributes`
- Verify only: `pgo_fantasy.py`
- Verify only: `tests/test_pgo_fantasy.py`
- Verify only after real `PASS`: `research/pgo_fantasy/sources.lock.json`
- Verify only after real `PASS`: `research/pgo_fantasy/source_qualification.json`

**Interfaces:**
- Consumes: all completed implementation commits and, when available, the accepted evidence pair.
- Produces: a verified completion report or an evidence-backed `BLOCKED` report.

- [ ] **Step 1: Run focused and full tests with warnings elevated**

Run:

```powershell
python -m unittest tests.test_pgo_fantasy -v
python -W error::ResourceWarning -m unittest discover -s tests -p "test_*.py"
```

Expected: every focused and repository test passes.

- [ ] **Step 2: Run compilation, whitespace, and prohibited-input checks**

Run:

```powershell
python -m py_compile pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --check dec6ef1...HEAD
rg -n -i "pff|injur|practice|inactive|depth.?chart|participation|betting|market" pgo_fantasy.py tests/test_pgo_fantasy.py
```

Expected: compilation and diff check pass. The text scan finds only explicit prohibited-input assertions or documentation, never a source/feature field or runtime dependency.

- [ ] **Step 3: Verify protected artifacts and exact tracked scope**

Run:

```powershell
git diff --exit-code dec6ef1 -- research/pgo_v1 research/pgo_stability_blend docs/index.html .github/workflows
$changed = @(git diff --name-only dec6ef1...HEAD)
$allowed = @(
  '.gitattributes',
  'docs/superpowers/plans/2026-08-27-pgo-fantasy-source-qualification.md',
  'pgo_fantasy.py',
  'tests/test_pgo_fantasy.py',
  'research/pgo_fantasy/sources.lock.json',
  'research/pgo_fantasy/source_qualification.json'
)
$unexpected = @($changed | Where-Object { $_ -notin $allowed })
if ($unexpected.Count -ne 0) { throw "Unexpected tracked paths: $($unexpected -join ', ')" }
git status --short --branch
```

Expected: protected diff empty. Changed tracked paths are a subset of the allowlist: the two research paths are absent on `BLOCKED` and both present on `PASS`. Status contains only the known unrelated untracked paths plus ignored cache/output evidence.

- [ ] **Step 4: Give the truthful final result**

On real `PASS`, report:

- exact implementation and evidence commit SHAs;
- focused and full test counts;
- source capture time, 13-source count, lock SHA-256, per-season coverage, and zero discrepancy counts;
- `LOCAL_CACHE_ONLY`, with canonical backtest and public output still unauthorized;
- no push or deployment performed.

On real `BLOCKED`, report:

- implementation commit SHAs and passing verification counts;
- source capture time and candidate lock hash;
- exact discrepancy classes, counts, and sorted identities from the local receipt;
- confirmation that no accepted research artifact, backtest, site change, push, or deployment occurred;
- the next decision required to replace or revise the source contract, without weakening it automatically.
