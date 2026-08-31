# PGO Fantasy Prior-Observed Cohort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and evaluate a roster-independent, prior-eight-week historical
fantasy cohort without fitting a candidate model or creating canonical evidence.

**Architecture:** Reuse the existing `SourceSpec`, one-read CSV loader,
schedule validation, half-PPR scorer, chronological baseline, and primary-pool
code in `pgo_fantasy.py`. Add one seven-source contract and one in-memory cohort
builder; extend the current baseline boundary only enough to validate the new
audit and label its population.

**Tech Stack:** Python standard library, existing `pgo_sources` helpers,
`unittest`, Git, and PowerShell. No new dependency, module, service, CLI,
workflow, or output writer.

## Global Constraints

- Historical seasons are exactly 2020 through 2025; test folds remain 2022,
  2023, 2024, and 2025.
- Evaluation uses completed regular-season weeks 2 through 18.
- Population is exactly `PRIOR_OBSERVED_8_WEEK`.
- A week-`w` player needs a valid stat row in weeks `w-8` through `w-1` of the
  same season. The newest prior row supplies team and position; FB maps to RB.
- Natural identity is `(season, week, gsis_id)`; team/game are context.
- Predict a complete week before any same-week target updates state.
- Week 1 and first appearances are state-only rows with
  `evaluation_eligible: false`; they update later player history after the
  week, but never enter means, pools, predictions, or metrics.
- Prediction rows carry `evaluation_eligible: true`; legacy rows without the
  field retain their existing implicit value of `true`.
- Zero-fill only when the last-known team played.
- Every evaluated week must fill 96 primary slots and capture at least 95% of
  positive half-PPR point mass.
- New reports remain `BASELINE_ONLY`, `DEVELOPMENT_ONLY`, `HOLD`,
  `EXPERIMENTAL`, and `REVIEW_REQUIRED`.
- Keep the 13-source roster qualifier and its old report shape unchanged.
- Do not read PFF, injuries, inactives, depth charts, betting, display-name
  identity, same-week rosters, the real cache, or remote sources.
- Do not write locks, receipts, predictions, research artifacts, site content,
  workflows, store files, pushes, or deployments.
- Protect `research/pgo_v1/`, `research/pgo_stability_blend/`,
  `research/pgo_fantasy/`, `prospective_evidence/`, `docs/index.html`,
  `.github/workflows/`, and `SHOPIFY.md`.
- Preserve unrelated untracked paths; never use `git add -A`.
- Changed-path base is `365712d`. Allowed paths are this plan, the approved
  spec, `pgo_fantasy.py`, and `tests/test_pgo_fantasy.py` only.

## File map

- Modify `pgo_fantasy.py`: seven-source specification, reusable loader,
  chronological cohort/audit, audit validation, and report dispatch.
- Modify `tests/test_pgo_fantasy.py`: synthetic fixture, chronology and failure
  regressions, coverage gates, report metadata, and legacy compatibility.
- Modify the approved spec only to change its status to
  `APPROVED FOR PLANNING`.
- Create no runtime file.

---

### Task 1: Add the seven-source contract and one-read loader option

**Files:**
- Modify: `pgo_fantasy.py:101-121`
- Modify: `pgo_fantasy.py:351-390`
- Test: `tests/test_pgo_fantasy.py:117-205`

**Interfaces:**
- Produces `prior_observed_source_specs() -> tuple[SourceSpec, ...]`.
- Extends `_load_source_rows(paths, source_specs=None) -> tuple[dict, list]`;
  the default retains the exact 13-source behavior.
- Produces test helper `PriorObservedFixture` for Tasks 2 and 3.

- [ ] **Step 1: Add the fixture and RED inventory/one-read tests**

Add after `FantasyContractTests`:

```python
class PriorObservedFixture:
    COUNTS = {"QB": 30, "RB": 42, "WR": 30, "TE": 20}

    @staticmethod
    def _row(columns, **values):
        return {column: values.get(column, "") for column in columns}

    @staticmethod
    def _csv_bytes(columns, rows):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output, fieldnames=columns, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode("utf-8")

    def _source_rows(self, weeks=(1, 2, 3), counts=None):
        counts = self.COUNTS if counts is None else counts
        schedule = []
        stats = {season: [] for season in pgo_fantasy.MODEL_SEASONS}
        for season in pgo_fantasy.MODEL_SEASONS:
            for week in weeks:
                game_id = f"{season}_{week:02d}_BUF_LAR"
                schedule.append(self._row(
                    pgo_fantasy.SCHEDULE_COLUMNS,
                    game_id=game_id, season=str(season), week=str(week),
                    game_type="REG", gameday=f"{season}-09-{week:02d}",
                    gametime="13:00", away_team="BUF", home_team="LAR",
                    away_score="20", home_score="10",
                ))
                for position, count in counts.items():
                    for index in range(count):
                        stats[season].append(self._row(
                            pgo_fantasy.PLAYER_COLUMNS,
                            player_id=f"{position}-{index:02d}",
                            position=position, season=str(season),
                            week=str(week), season_type="REG",
                            game_id=game_id, team="BUF",
                            opponent_team="LAR",
                            receiving_yards=str(10 + index),
                        ))
        return schedule, stats

    def _write_sources(self, directory, schedule, stats):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        schedule_path = root / "schedule.csv"
        schedule_path.write_bytes(self._csv_bytes(
            pgo_fantasy.SCHEDULE_COLUMNS, schedule
        ))
        paths = {("schedule_results", None): schedule_path}
        for season in pgo_fantasy.MODEL_SEASONS:
            path = root / f"stats-{season}.csv.gz"
            path.write_bytes(gzip.compress(
                self._csv_bytes(pgo_fantasy.PLAYER_COLUMNS, stats[season]),
                mtime=0,
            ))
            paths[("player_weekly_stats", season)] = path
        return paths

    @staticmethod
    def _schedule_patch(paths):
        digest = hashlib.sha256(
            Path(paths[("schedule_results", None)]).read_bytes()
        ).hexdigest()
        return patch.object(pgo_sources, "EXPECTED_SOURCE_SHA256", digest)


class PriorObservedSourceContractTests(
    PriorObservedFixture, unittest.TestCase
):
    def test_inventory_is_schedule_plus_six_stats(self):
        specs = pgo_fantasy.prior_observed_source_specs()
        self.assertEqual(len(specs), 7)
        self.assertEqual(
            {(spec.name, spec.season) for spec in specs},
            {("schedule_results", None)} | {
                ("player_weekly_stats", season)
                for season in pgo_fantasy.MODEL_SEASONS
            },
        )

    def test_loader_reads_each_source_once_and_ignores_mapping_order(self):
        schedule, stats = self._source_rows(weeks=(1,))
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, stats)
            original = Path.read_bytes
            reads = []

            def counted(path):
                reads.append(Path(path))
                return original(path)

            with mock.patch.object(Path, "read_bytes", counted):
                first = pgo_fantasy._load_source_rows(
                    paths,
                    source_specs=pgo_fantasy.prior_observed_source_specs(),
                )
            second = pgo_fantasy._load_source_rows(
                dict(reversed(list(paths.items()))),
                source_specs=pgo_fantasy.prior_observed_source_specs(),
            )

        self.assertEqual(len(reads), 7)
        self.assertTrue(all(
            reads.count(Path(path)) == 1 for path in paths.values()
        ))
        self.assertEqual(first, second)
```

- [ ] **Step 2: Run RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedSourceContractTests -v
```

Expected: ERROR for the missing function and loader parameter.

- [ ] **Step 3: Add the minimal production code**

Add after `fantasy_source_specs`:

```python
def prior_observed_source_specs() -> tuple[SourceSpec, ...]:
    return tuple(
        spec for spec in fantasy_source_specs()
        if spec.name != "weekly_rosters"
    )
```

Change only `_load_source_rows` initialization:

```python
def _load_source_rows(paths, source_specs=None):
    source_specs = (
        fantasy_source_specs()
        if source_specs is None
        else tuple(source_specs)
    )
    specs = {(spec.name, spec.season): spec for spec in source_specs}
```

Leave its remaining one-read parse/hash/receipt logic unchanged.

- [ ] **Step 4: Run GREEN and legacy contract tests**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedSourceContractTests `
  tests.test_pgo_fantasy.FantasyContractTests `
  tests.test_pgo_fantasy.FantasyPopulationTests `
  tests.test_pgo_fantasy.FantasySourceQualificationTests -v
```

Expected: `OK`; legacy inventory remains 13 sources.

- [ ] **Step 5: Commit Task 1**

```powershell
python -B -m py_compile pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --check
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: add prior-observed source contract"
```

Expected: exactly the two code/test paths are committed.

---
### Task 2: Construct and audit the chronological cohort

**Files:**
- Modify: `pgo_fantasy.py:20-175`
- Modify: `pgo_fantasy.py:393-630`
- Test: `tests/test_pgo_fantasy.py` after
  `PriorObservedSourceContractTests`

**Interfaces:**
- Produces `build_prior_observed_games(paths) -> tuple[list[dict], dict]`.
- Produces `_build_prior_observed_from_sources(source_rows,
  source_receipts) -> tuple[list[dict], dict]`.
- Audit keys are exactly `schema_version`, `population`, `scope`,
  `position_authority`, `position_mapping`, `sources`, `coverage`,
  `diagnostics`, and `checks`.

- [ ] **Step 1: Add RED chronology, identity, and diagnostic tests**

Create `PriorObservedCohortTests(PriorObservedFixture, unittest.TestCase)`.
Its helper must call only temporary sources:

```python
class PriorObservedCohortTests(PriorObservedFixture, unittest.TestCase):
    def _build(self, directory, schedule, stats):
        paths = self._write_sources(directory, schedule, stats)
        with self._schedule_patch(paths):
            return pgo_fantasy.build_prior_observed_games(paths)

    def test_prior_state_zero_fill_and_fullback_mapping(self):
        schedule, stats = self._source_rows(
            counts={"QB": 1, "FB": 1, "WR": 1, "TE": 1}
        )
        stats[2022] = [
            row for row in stats[2022]
            if not (row["week"] == "2" and row["player_id"] == "QB-00")
        ]
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._build(directory, schedule, stats)

        self.assertTrue(any(row["week"] == 1 for row in rows))
        self.assertTrue(all(
            not row["evaluation_eligible"]
            for row in rows if row["week"] == 1
        ))
        keyed = {
            (row["season"], row["week"], row["gsis_id"]): row
            for row in rows
        }
        self.assertEqual(keyed[(2022, 2, "QB-00")]["fantasy_points"], 0.0)
        self.assertEqual(keyed[(2022, 2, "FB-00")]["position"], "RB")
        week = next(
            row for row in audit["coverage"]
            if (row["season"], row["week"]) == (2022, 2)
        )
        self.assertEqual(
            (week["eligible"], week["matched_stats"], week["zero_filled"]),
            (4, 3, 1),
        )
        self.assertEqual(week["state_only"], 0)

    def test_first_appearance_enters_next_week(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        for week in (2, 3):
            source = next(
                row for row in stats[2022] if row["week"] == str(week)
            )
            stats[2022].append({**source, "player_id": "NEW-QB"})
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._build(directory, schedule, stats)

        self.assertEqual(
            [(row["season"], row["week"]) for row in rows
             if row["gsis_id"] == "NEW-QB"
             and row["evaluation_eligible"]],
            [(2022, 3)],
        )
        self.assertIn(
            (2022, 2, False),
            {(row["season"], row["week"], row["evaluation_eligible"])
             for row in rows if row["gsis_id"] == "NEW-QB"},
        )
        self.assertIn(
            ("cold_start", 2022, 2, "NEW-QB"),
            {(row["reason"], row["season"], row["week"], row["gsis_id"])
             for row in audit["diagnostics"]},
        )

    def test_future_rows_do_not_change_week_two(self):
        schedule, stats = self._source_rows(counts={"QB": 2})
        with tempfile.TemporaryDirectory() as first_directory:
            first, _ = self._build(first_directory, schedule, stats)
        changed = copy.deepcopy(stats)
        changed[2022] = [
            row for row in changed[2022] if row["week"] != "3"
        ]
        with tempfile.TemporaryDirectory() as second_directory:
            second, _ = self._build(second_directory, schedule, changed)

        select = lambda rows: [
            row for row in rows
            if (row["season"], row["week"]) == (2022, 2)
        ]
        self.assertEqual(select(first), select(second))

    def test_roster_bytes_and_path_mapping_order_have_no_influence(self):
        schedule, stats = self._source_rows(counts={"QB": 2})
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, stats)
            unrelated_roster = Path(directory) / "weekly-roster.csv"
            unrelated_roster.write_bytes(b"status,gsis_id\nACT,OLD\n")
            with self._schedule_patch(paths):
                first = pgo_fantasy.build_prior_observed_games(paths)
            unrelated_roster.write_bytes(b"status,gsis_id\nACT,CHANGED\n")
            reversed_paths = dict(reversed(list(paths.items())))
            with self._schedule_patch(reversed_paths):
                second = pgo_fantasy.build_prior_observed_games(reversed_paths)
        self.assertEqual(first, second)

    def test_most_recent_prior_position_controls_next_week(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        week_two = next(row for row in stats[2022]
                        if row["week"] == "2" and row["player_id"] == "QB-00")
        week_two["position"] = "TE"
        with tempfile.TemporaryDirectory() as directory:
            rows, _ = self._build(directory, schedule, stats)
        keyed = {(row["season"], row["week"], row["gsis_id"]): row
                 for row in rows}
        self.assertEqual(keyed[(2022, 2, "QB-00")]["position"], "QB")
        self.assertEqual(keyed[(2022, 3, "QB-00")]["position"], "TE")

    def test_unsupported_position_is_diagnostic_only(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        source = next(row for row in stats[2022] if row["week"] == "2")
        stats[2022].append({
            **source, "player_id": "K-00", "position": "K"
        })
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._build(directory, schedule, stats)

        self.assertNotIn("K-00", {row["gsis_id"] for row in rows})
        self.assertIn(
            ("unsupported_position", "K-00"),
            {(row["reason"], row["gsis_id"])
             for row in audit["diagnostics"]},
        )

    def test_invalid_relevant_stats_fail_closed(self):
        mutations = (
            lambda row: row.update(player_id=""),
            lambda row: row.update(team="ATL"),
            lambda row: row.update(receiving_yards="NaN"),
        )
        for mutate in mutations:
            schedule, stats = self._source_rows(counts={"QB": 1})
            mutate(next(row for row in stats[2022] if row["week"] == "2"))
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    self._build(directory, schedule, stats)

    def test_duplicate_player_week_fails_closed(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        target = next(row for row in stats[2022] if row["week"] == "2")
        stats[2022].append(copy.deepcopy(target))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Duplicate prior-observed"):
                self._build(directory, schedule, stats)

    def test_unpinned_schedule_fails_closed(self):
        schedule, stats = self._source_rows(counts={"QB": 1})
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_sources(directory, schedule, stats)
            with patch.object(
                pgo_sources, "EXPECTED_SOURCE_SHA256", "0" * 64
            ):
                with self.assertRaisesRegex(ValueError, "pinned SHA-256"):
                    pgo_fantasy.build_prior_observed_games(paths)
```

Add the transition and expiry tests with complete schedule identities:

```python
def test_team_transition_keeps_prior_game_context(self):
    schedule, stats = self._source_rows(counts={"QB": 1})
    schedule.append(self._row(
        pgo_fantasy.SCHEDULE_COLUMNS,
        game_id="2022_02_ATL_CAR", season="2022", week="2",
        game_type="REG", gameday="2022-09-02", gametime="13:00",
        away_team="ATL", home_team="CAR",
        away_score="20", home_score="10",
    ))
    moved = next(row for row in stats[2022]
                 if row["week"] == "2" and row["player_id"] == "QB-00")
    moved.update(
        game_id="2022_02_ATL_CAR", team="ATL", opponent_team="CAR"
    )
    with tempfile.TemporaryDirectory() as directory:
        rows, audit = self._build(directory, schedule, stats)
    prediction = next(row for row in rows
                      if (row["season"], row["week"], row["gsis_id"])
                      == (2022, 2, "QB-00"))
    self.assertEqual(
        (prediction["game_id"], prediction["team"], prediction["opponent"]),
        ("2022_02_BUF_LAR", "BUF", "LAR"),
    )
    self.assertGreater(prediction["fantasy_points"], 0.0)
    self.assertIn(
        ("team_transition", "QB-00", "BUF", "ATL"),
        {(row["reason"], row["gsis_id"], row["last_known_team"], row["team"])
         for row in audit["diagnostics"]},
    )

def test_bye_transition_and_recency_expiry_are_unpredicted(self):
    schedule, stats = self._source_rows(
        weeks=tuple(range(1, 11)), counts={"QB": 1}
    )
    schedule.extend((
        self._row(
            pgo_fantasy.SCHEDULE_COLUMNS,
            game_id="2022_01_NYJ_MIA", season="2022", week="1",
            game_type="REG", gameday="2022-09-01", gametime="13:00",
            away_team="NYJ", home_team="MIA",
            away_score="20", home_score="10",
        ),
        self._row(
            pgo_fantasy.SCHEDULE_COLUMNS,
            game_id="2022_02_ATL_CAR", season="2022", week="2",
            game_type="REG", gameday="2022-09-02", gametime="13:00",
            away_team="ATL", home_team="CAR",
            away_score="20", home_score="10",
        ),
    ))
    week_one = next(row for row in stats[2022] if row["week"] == "1")
    week_two = next(row for row in stats[2022] if row["week"] == "2")
    week_ten = next(row for row in stats[2022] if row["week"] == "10")
    stats[2022].extend((
        {**week_one, "player_id": "BYE-QB", "game_id": "2022_01_NYJ_MIA",
         "team": "NYJ", "opponent_team": "MIA"},
        {**week_two, "player_id": "BYE-QB", "game_id": "2022_02_ATL_CAR",
         "team": "ATL", "opponent_team": "CAR"},
        {**week_one, "player_id": "EXPIRED-QB"},
        {**week_ten, "player_id": "EXPIRED-QB"},
    ))
    with tempfile.TemporaryDirectory() as directory:
        rows, audit = self._build(directory, schedule, stats)
    keys = {(row["season"], row["week"], row["gsis_id"]) for row in rows}
    self.assertIn((2022, 2, "BYE-QB"), keys)
    self.assertIn((2022, 10, "EXPIRED-QB"), keys)
    self.assertFalse(next(row["evaluation_eligible"] for row in rows
                          if (row["season"], row["week"], row["gsis_id"])
                          == (2022, 2, "BYE-QB")))
    self.assertFalse(next(row["evaluation_eligible"] for row in rows
                          if (row["season"], row["week"], row["gsis_id"])
                          == (2022, 10, "EXPIRED-QB")))
    reasons = {(row["reason"], row["gsis_id"], row["week"])
               for row in audit["diagnostics"]}
    self.assertIn(("bye_transition", "BYE-QB", 2), reasons)
    self.assertIn(("recency_expired", "EXPIRED-QB", 10), reasons)
```

- [ ] **Step 2: Run RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedCohortTests -v
```

Expected: ERROR for missing `build_prior_observed_games`.

- [ ] **Step 3: Add exact metadata and deterministic diagnostic helpers**

```python
PRIOR_OBSERVED_POPULATION = "PRIOR_OBSERVED_8_WEEK"
PRIOR_OBSERVED_POSITION_AUTHORITY = "MOST_RECENT_PRIOR_PLAYER_STAT"
PRIOR_OBSERVED_SCOPE = {
    "seasons": list(MODEL_SEASONS),
    "game_type": "REG",
    "history_weeks": 8,
    "evaluation_weeks": [2, 18],
}
PRIOR_OBSERVED_CHECKS = (
    "source_contract", "schedule_identity", "stat_identity",
    "chronology", "finite_targets", "point_coverage",
)
PRIOR_OBSERVED_DIAGNOSTIC_CLASSES = (
    "cold_start", "team_transition", "bye_transition",
    "recency_expired", "unsupported_position",
)


def _prior_observed_diagnostic(reason, row, last_known_team=""):
    if reason not in PRIOR_OBSERVED_DIAGNOSTIC_CLASSES:
        raise ValueError(f"Unknown prior-observed diagnostic: {reason}")
    return {
        "reason": reason,
        "season": row["season"],
        "week": row["week"],
        "game_id": row["game_id"],
        "gsis_id": row["gsis_id"],
        "team": row["team"],
        "last_known_team": last_known_team,
        "raw_position": row["raw_position"],
        "fantasy_points": row["fantasy_points"],
    }


def _prior_observed_diagnostic_key(row):
    return (
        row["season"], row["week"], row["reason"], row["gsis_id"],
        row["team"], row["game_id"],
    )
```

- [ ] **Step 4: Parse valid regular-season stat rows**

Implement `_load_prior_observed_stats(source_rows, team_weeks)` with this exact
order:

```python
def _load_prior_observed_stats(source_rows, team_weeks):
    by_week, diagnostics, seen = {}, [], set()
    for source_season in MODEL_SEASONS:
        for row in source_rows[("player_weekly_stats", source_season)]:
            season = _integer(row, "season", "prior-observed stat")
            if season != source_season:
                raise ValueError("Prior-observed stat source-season mismatch")
            if (row.get("season_type") or "").strip() != "REG":
                continue
            week = _integer(row, "week", "prior-observed stat")
            game_id = (row.get("game_id") or "").strip()
            gsis_id = (row.get("player_id") or "").strip()
            team = normalize_team(row.get("team") or "")
            opponent = normalize_team(row.get("opponent_team") or "")
            raw_position = (row.get("position") or "").strip().upper()
            fantasy_points = half_ppr(row)
            if (
                week < 1 or week > 18
                or team_weeks.get((season, week, team))
                != (game_id, opponent)
            ):
                raise ValueError("Prior-observed stat schedule identity is invalid")
            parsed = {
                "season": season, "week": week, "game_id": game_id,
                "gsis_id": gsis_id, "player_name": "", "team": team,
                "opponent": opponent,
                "position": POSITION_MAP.get(raw_position),
                "raw_position": raw_position,
                "fantasy_points": fantasy_points,
            }
            if parsed["position"] is None:
                diagnostics.append(_prior_observed_diagnostic(
                    "unsupported_position", parsed
                ))
                continue
            if not gsis_id:
                raise ValueError("Missing prior-observed stat identity")
            key = season, week, gsis_id
            if key in seen:
                raise ValueError(f"Duplicate prior-observed player-week: {key}")
            seen.add(key)
            by_week.setdefault((season, week), []).append(parsed)
    for rows in by_week.values():
        rows.sort(key=lambda row: (row["gsis_id"], row["game_id"]))
    diagnostics.sort(key=_prior_observed_diagnostic_key)
    return by_week, diagnostics
```

- [ ] **Step 5: Build complete weeks before updating histories**

Implement `_build_prior_observed_from_sources` using this loop. Keep the audit
in memory and sort both rows and diagnostics:

```python
def _build_prior_observed_from_sources(source_rows, source_receipts):
    _, team_weeks = _load_schedule(source_rows[("schedule_results", None)])
    stats_by_week, diagnostics = _load_prior_observed_stats(
        source_rows, team_weeks
    )
    output_rows, coverage = [], []
    for season in MODEL_SEASONS:
        history = {}
        weeks = sorted({week for item_season, week, _ in team_weeks
                        if item_season == season})
        if not weeks:
            raise ValueError("Prior-observed schedule is missing a model season")
        for week in weeks:
            current_rows = stats_by_week.get((season, week), [])
            current = {row["gsis_id"]: row for row in current_rows}
            predicted = set()
            if week >= 2:
                for gsis_id in sorted(history):
                    prior = [row for row in history[gsis_id]
                             if week - 8 <= row["week"] < week]
                    if not prior:
                        continue
                    last = prior[-1]
                    scheduled = team_weeks.get((season, week, last["team"]))
                    if scheduled is None:
                        continue
                    game_id, opponent = scheduled
                    target = current.get(gsis_id)
                    output_rows.append({
                        "season": season, "week": week, "game_id": game_id,
                        "gsis_id": gsis_id, "player_name": last["player_name"],
                        "team": last["team"], "opponent": opponent,
                        "position": last["position"],
                        "fantasy_points": 0.0 if target is None
                        else target["fantasy_points"],
                        "evaluation_eligible": True,
                    })
                    predicted.add(gsis_id)
                    if target is not None and target["team"] != last["team"]:
                        diagnostics.append(_prior_observed_diagnostic(
                            "team_transition", target, last["team"]
                        ))
            for row in current_rows:
                if row["gsis_id"] in predicted:
                    continue
                prior = history.get(row["gsis_id"], [])
                if not prior:
                    reason, last_team = "cold_start", ""
                elif week - prior[-1]["week"] > 8:
                    reason, last_team = "recency_expired", prior[-1]["team"]
                elif team_weeks.get((season, week, prior[-1]["team"])) is None:
                    reason, last_team = "bye_transition", prior[-1]["team"]
                else:
                    raise ValueError("Prior-observed chronology omitted a player")
                diagnostics.append(_prior_observed_diagnostic(
                    reason, row, last_team
                ))
                output_rows.append({
                    "season": season, "week": week,
                    "game_id": row["game_id"], "gsis_id": row["gsis_id"],
                    "player_name": row["player_name"], "team": row["team"],
                    "opponent": row["opponent"], "position": row["position"],
                    "fantasy_points": row["fantasy_points"],
                    "evaluation_eligible": False,
                })
            total = sum(max(row["fantasy_points"], 0.0)
                        for row in current_rows)
            captured = sum(max(current[player]["fantasy_points"], 0.0)
                           for player in predicted if player in current)
            matched = len(predicted & set(current))
            coverage.append({
                "season": season, "week": week,
                "eligible": len(predicted), "matched_stats": matched,
                "zero_filled": len(predicted) - matched,
                "state_only": len(current_rows) - matched,
                "positive_points_captured": captured,
                "positive_points_total": total,
                "positive_point_coverage": captured / total
                if total > 0.0 else 0.0,
            })
            for row in current_rows:
                history.setdefault(row["gsis_id"], []).append(row)
```

Finish the function exactly as follows:

```python
    coverage.sort(key=lambda row: (row["season"], row["week"]))
    diagnostics.sort(key=_prior_observed_diagnostic_key)
    test_rows = [
        row for row in coverage
        if row["season"] in TEST_SEASONS and row["week"] >= 2
    ]
    point_coverage = (
        all(any(row["season"] == season for row in test_rows)
            for season in TEST_SEASONS)
        and all(row["positive_points_total"] > 0.0
                and row["positive_point_coverage"] >= 0.95
                for row in test_rows)
    )
    audit = {
        "schema_version": 1,
        "population": PRIOR_OBSERVED_POPULATION,
        "scope": dict(PRIOR_OBSERVED_SCOPE),
        "position_authority": PRIOR_OBSERVED_POSITION_AUTHORITY,
        "position_mapping": dict(FANTASY_POSITION_MAPPING),
        "sources": source_receipts,
        "coverage": coverage,
        "diagnostics": diagnostics,
        "checks": {name: True for name in PRIOR_OBSERVED_CHECKS},
    }
    audit["checks"]["point_coverage"] = point_coverage
    return sorted(output_rows, key=_row_key), audit


def build_prior_observed_games(paths) -> tuple[list[dict], dict]:
    source_rows, receipts = _load_source_rows(
        paths, source_specs=prior_observed_source_specs()
    )
    schedule = next(row for row in receipts
                    if (row["name"], row["season"])
                    == ("schedule_results", None))
    if schedule["sha256"] != pgo_sources.EXPECTED_SOURCE_SHA256:
        raise ValueError("Prior-observed schedule does not match pinned SHA-256")
    return _build_prior_observed_from_sources(source_rows, receipts)
```

- [ ] **Step 6: Run GREEN and legacy reconciliation tests**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedSourceContractTests `
  tests.test_pgo_fantasy.PriorObservedCohortTests `
  tests.test_pgo_fantasy.FantasyPopulationTests `
  tests.test_pgo_fantasy.FantasySourceQualificationTests -v
```

Expected: `OK`; no roster-qualification expectation changes.

- [ ] **Step 7: Commit Task 2**

```powershell
python -B -m py_compile pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --check
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: build prior-observed fantasy cohort"
```

Expected: exactly the two code/test paths are committed.

---

### Task 3: Validate the cohort and reuse the baseline evaluator

**Files:**
- Modify: `pgo_fantasy.py:1203-1341`
- Test: `tests/test_pgo_fantasy.py` before `FantasyReceiptTests`

**Interfaces:**
- Produces `_validate_prior_observed_audit(source_audit, rows) -> None`.
- Produces `_validate_baseline_source_audit(source_audit, rows) -> str`.
- Keeps `backtest_baselines(rows, source_audit)` signature unchanged.

- [ ] **Step 1: Add RED report and gate tests**

```python
class PriorObservedBaselineTests(PriorObservedFixture, unittest.TestCase):
    def _cohort(self, directory, schedule=None, stats=None, counts=None):
        if schedule is None or stats is None:
            schedule, stats = self._source_rows(counts=counts)
        paths = self._write_sources(directory, schedule, stats)
        with self._schedule_patch(paths):
            return pgo_fantasy.build_prior_observed_games(paths)

    def test_report_is_development_hold_with_96_weekly_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._cohort(directory)
            report, predictions = pgo_fantasy.backtest_baselines(rows, audit)
        self.assertEqual(report["population"], "PRIOR_OBSERVED_8_WEEK")
        self.assertEqual(report["stage"], "BASELINE_ONLY")
        self.assertEqual(report["evidence_role"], "DEVELOPMENT_ONLY")
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["publication_status"], "EXPERIMENTAL")
        self.assertEqual(report["leakage_status"], "REVIEW_REQUIRED")
        self.assertFalse(any(row["week"] == 1 for row in predictions))
        for season in pgo_fantasy.TEST_SEASONS:
            for week in (2, 3):
                weekly = [row for row in predictions
                          if (row["season"], row["week"]) == (season, week)]
                self.assertEqual(sum(row["primary_pool"] for row in weekly), 96)

    def test_same_week_target_does_not_change_same_week_prediction(self):
        schedule, stats = self._source_rows()
        with tempfile.TemporaryDirectory() as first_directory:
            rows, audit = self._cohort(first_directory, schedule, stats)
            _, first = pgo_fantasy.backtest_baselines(rows, audit)
        changed = copy.deepcopy(stats)
        target = next(row for row in changed[2022]
                      if row["week"] == "2" and row["player_id"] == "RB-00")
        target["receiving_yards"] = "10000"
        with tempfile.TemporaryDirectory() as second_directory:
            rows, audit = self._cohort(second_directory, schedule, changed)
            _, second = pgo_fantasy.backtest_baselines(rows, audit)
        before = {(row["season"], row["week"], row["gsis_id"]): row
                  for row in first}
        after = {(row["season"], row["week"], row["gsis_id"]): row
                 for row in second}
        for key in before:
            if key[:2] == (2022, 2):
                self.assertEqual(
                    (before[key]["null_prediction"],
                     before[key]["strong_prediction"],
                     before[key]["primary_pool"]),
                    (after[key]["null_prediction"],
                     after[key]["strong_prediction"],
                     after[key]["primary_pool"]),
                )
        self.assertNotEqual(
            before[(2022, 3, "RB-00")]["strong_prediction"],
            after[(2022, 3, "RB-00")]["strong_prediction"],
        )

    def test_week_one_state_seeds_week_two_without_being_predicted(self):
        schedule, stats = self._source_rows()
        with tempfile.TemporaryDirectory() as first_directory:
            rows, audit = self._cohort(first_directory, schedule, stats)
            _, first = pgo_fantasy.backtest_baselines(rows, audit)
        changed = copy.deepcopy(stats)
        target = next(row for row in changed[2022]
                      if row["week"] == "1" and row["player_id"] == "RB-00")
        target["receiving_yards"] = "10000"
        with tempfile.TemporaryDirectory() as second_directory:
            rows, audit = self._cohort(second_directory, schedule, changed)
            _, second = pgo_fantasy.backtest_baselines(rows, audit)
        before = next(row for row in first
                      if (row["season"], row["week"], row["gsis_id"])
                      == (2022, 2, "RB-00"))
        after = next(row for row in second
                     if (row["season"], row["week"], row["gsis_id"])
                     == (2022, 2, "RB-00"))
        self.assertNotEqual(
            before["strong_prediction"], after["strong_prediction"]
        )
        self.assertEqual(before["null_prediction"], after["null_prediction"])
        self.assertFalse(any(row["week"] == 1 for row in first + second))

    def test_point_coverage_and_primary_pool_fail_closed(self):
        schedule, stats = self._source_rows()
        source = next(row for row in stats[2022]
                      if row["week"] == "2" and row["player_id"] == "QB-00")
        stats[2022].append({
            **source, "player_id": "COLD-STAR",
            "receiving_yards": "100000",
        })
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._cohort(directory, schedule, stats)
        self.assertFalse(audit["checks"]["point_coverage"])
        with self.assertRaisesRegex(ValueError, "point coverage"):
            pgo_fantasy.backtest_baselines(rows, audit)

        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._cohort(
                directory,
                counts={"QB": 23, "RB": 42, "WR": 30, "TE": 20},
            )
        with self.assertRaisesRegex(ValueError, "Insufficient primary-pool QB"):
            pgo_fantasy.backtest_baselines(rows, audit)

    def test_audit_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            rows, audit = self._cohort(directory)
        cases = []
        missing_source = copy.deepcopy(audit)
        missing_source["sources"].pop()
        cases.append(missing_source)
        changed_count = copy.deepcopy(audit)
        changed_count["coverage"][0]["eligible"] += 1
        cases.append(changed_count)
        nonfinite = copy.deepcopy(audit)
        nonfinite["coverage"][0]["positive_points_total"] = math.nan
        cases.append(nonfinite)
        reordered = copy.deepcopy(audit)
        reordered["diagnostics"] = list(reversed(reordered["diagnostics"]))
        cases.append(reordered)
        for changed in cases:
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    pgo_fantasy.backtest_baselines(rows, changed)

    def test_legacy_roster_report_shape_is_unchanged(self):
        report, _ = pgo_fantasy.backtest_baselines(
            FantasyBaselineTests()._model_rows(),
            FantasyBaselineTests._audit(),
        )
        self.assertEqual(set(report), {
            "schema_version", "model", "stage", "status",
            "publication_status", "status_reason", "scoring", "population",
            "source_audit_sha256", "folds", "pooled",
        })
```

- [ ] **Step 2: Run RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedBaselineTests -v
```

Expected: prior-observed audits fail the existing schema-2 roster validator.

- [ ] **Step 3: Extract shared receipt validation**

Move the existing receipt loop from `_validate_source_audit` into this helper;
call it from the old validator with `fantasy_source_specs()`:

```python
def _validate_audit_sources(sources, source_specs):
    expected = {(spec.name, spec.season) for spec in source_specs}
    if not isinstance(sources, list):
        raise ValueError("Source audit sources are invalid")
    received = set()
    for receipt in sources:
        if not isinstance(receipt, dict) or set(receipt) != {
            "name", "season", "bytes", "sha256", "rows",
        }:
            raise ValueError("Source audit receipt is invalid")
        key = receipt["name"], receipt["season"]
        digest = receipt["sha256"]
        if (
            key in received or key not in expected
            or type(receipt["bytes"]) is not int or receipt["bytes"] <= 0
            or type(receipt["rows"]) is not int or receipt["rows"] <= 0
            or not isinstance(digest, str) or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("Source audit receipt is invalid")
        received.add(key)
    order = [(row["name"], row["season"]) for row in sources]
    if received != expected or order != sorted(order, key=_source_key_sort):
        raise ValueError("Source audit inventory is incomplete")
```

- [ ] **Step 4: Add strict prior-observed audit validation**

Define exact row fields and validate shape, order, counts, finiteness, ratio,
population binding, and the 95% gate:

```python
PRIOR_OBSERVED_COVERAGE_FIELDS = frozenset({
    "season", "week", "eligible", "matched_stats", "zero_filled",
    "state_only",
    "positive_points_captured", "positive_points_total",
    "positive_point_coverage",
})
PRIOR_OBSERVED_DIAGNOSTIC_FIELDS = frozenset({
    "reason", "season", "week", "game_id", "gsis_id", "team",
    "last_known_team", "raw_position", "fantasy_points",
})


def _validate_prior_observed_audit(audit, rows):
    if (
        not isinstance(audit, dict)
        or set(audit) != {
            "schema_version", "population", "scope", "position_authority",
            "position_mapping", "sources", "coverage", "diagnostics", "checks",
        }
        or type(audit["schema_version"]) is not int
        or audit["schema_version"] != 1
        or audit["population"] != PRIOR_OBSERVED_POPULATION
        or audit["scope"] != PRIOR_OBSERVED_SCOPE
        or audit["position_authority"] != PRIOR_OBSERVED_POSITION_AUTHORITY
        or audit["position_mapping"] != FANTASY_POSITION_MAPPING
    ):
        raise ValueError("Prior-observed source audit is invalid")
    _validate_audit_sources(audit["sources"], prior_observed_source_specs())

    coverage = audit["coverage"]
    if not isinstance(coverage, list) or coverage != sorted(
        coverage, key=lambda row: (row["season"], row["week"])
    ):
        raise ValueError("Prior-observed coverage is invalid")
    seen, row_counts, eligible_counts = set(), {}, {}
    for row in rows:
        key = row["season"], row["week"]
        if not isinstance(row.get("evaluation_eligible"), bool):
            raise ValueError("Prior-observed evaluation marker is invalid")
        row_counts[key] = row_counts.get(key, 0) + 1
        if row["evaluation_eligible"]:
            eligible_counts[key] = eligible_counts.get(key, 0) + 1
    for item in coverage:
        if not isinstance(item, dict) or set(item) != PRIOR_OBSERVED_COVERAGE_FIELDS:
            raise ValueError("Prior-observed coverage is invalid")
        key = item["season"], item["week"]
        numbers = (
            item["positive_points_captured"], item["positive_points_total"],
            item["positive_point_coverage"],
        )
        if (
            key in seen or item["season"] not in MODEL_SEASONS
            or type(item["week"]) is not int or not 1 <= item["week"] <= 18
            or any(type(item[name]) is not int or item[name] < 0
                   for name in (
                       "eligible", "matched_stats", "zero_filled", "state_only"
                   ))
            or item["matched_stats"] + item["zero_filled"] != item["eligible"]
            or row_counts.get(key, 0) != item["eligible"] + item["state_only"]
            or eligible_counts.get(key, 0) != item["eligible"]
            or any(isinstance(value, bool)
                   or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in numbers)
            or not 0.0 <= item["positive_points_captured"]
            <= item["positive_points_total"]
        ):
            raise ValueError("Prior-observed coverage is invalid")
        expected = (item["positive_points_captured"]
                    / item["positive_points_total"]
                    if item["positive_points_total"] > 0.0 else 0.0)
        if not math.isclose(
            item["positive_point_coverage"], expected,
            rel_tol=0.0, abs_tol=1e-12,
        ):
            raise ValueError("Prior-observed coverage is invalid")
        seen.add(key)
    if set(row_counts) - seen:
        raise ValueError("Prior-observed population changed")

    diagnostics = audit["diagnostics"]
    if not isinstance(diagnostics, list) or diagnostics != sorted(
        diagnostics, key=_prior_observed_diagnostic_key
    ) or len({_canonical_json_bytes(row) for row in diagnostics}) != len(
        diagnostics
    ):
        raise ValueError("Prior-observed diagnostics are invalid")
    for row in diagnostics:
        if (
            not isinstance(row, dict)
            or set(row) != PRIOR_OBSERVED_DIAGNOSTIC_FIELDS
            or row["reason"] not in PRIOR_OBSERVED_DIAGNOSTIC_CLASSES
            or type(row["season"]) is not int
            or row["season"] not in MODEL_SEASONS
            or type(row["week"]) is not int
            or not 1 <= row["week"] <= 18
            or any(not isinstance(row[name], str) for name in (
                "reason", "game_id", "gsis_id", "team",
                "last_known_team", "raw_position",
            ))
            or not isinstance(row["fantasy_points"], (int, float))
            or isinstance(row["fantasy_points"], bool)
            or not math.isfinite(row["fantasy_points"])
        ):
            raise ValueError("Prior-observed diagnostics are invalid")

    point_ok = (
        all(any(item["season"] == season for item in coverage)
            for season in TEST_SEASONS)
        and all(item["positive_points_total"] > 0.0
                and item["positive_point_coverage"] >= 0.95
                for item in coverage
                if item["season"] in TEST_SEASONS and item["week"] >= 2)
    )
    expected_checks = {name: True for name in PRIOR_OBSERVED_CHECKS}
    expected_checks["point_coverage"] = point_ok
    if audit["checks"] != expected_checks or not point_ok:
        raise ValueError("Prior-observed point coverage is blocked")
```

- [ ] **Step 5: Separate state updates from evaluation rows**

In `_validated_baseline_rows`, read the optional marker with a legacy default
and reject non-booleans:

```python
evaluation_eligible = source.get("evaluation_eligible", True)
if not isinstance(evaluation_eligible, bool):
    raise ValueError("Invalid baseline evaluation marker")
```

Keep the source dictionary unchanged when the field is absent. Replace
`_predict_fold` with the same baseline math and this state/evaluation split:

```python
def _is_evaluation_row(row):
    return row.get("evaluation_eligible", True)


def _predict_fold(rows, test_season):
    training = [row for row in rows if row["season"] < test_season]
    position_sums = {position: 0.0 for position in ("QB", "RB", "WR", "TE")}
    position_counts = {position: 0 for position in position_sums}
    histories = {}
    for row in training:
        if _is_evaluation_row(row):
            position_sums[row["position"]] += row["fantasy_points"]
            position_counts[row["position"]] += 1
        histories.setdefault(row["gsis_id"], []).append(row["fantasy_points"])
    if any(count == 0 for count in position_counts.values()):
        raise ValueError(f"Training positions are incomplete for {test_season}")
    null_means = {
        position: position_sums[position] / position_counts[position]
        for position in position_sums
    }
    test_weeks = {}
    for row in rows:
        if row["season"] == test_season:
            test_weeks.setdefault(row["week"], []).append(row)
    if not any(_is_evaluation_row(row)
               for weekly in test_weeks.values() for row in weekly):
        raise ValueError(f"Test season contains zero evaluation rows: {test_season}")

    predictions = []
    for week in sorted(test_weeks):
        weekly_rows = sorted(test_weeks[week], key=_row_key)
        evaluation_rows = [row for row in weekly_rows
                           if _is_evaluation_row(row)]
        week_predictions = []
        for row in evaluation_rows:
            position = row["position"]
            live_mean = position_sums[position] / position_counts[position]
            week_predictions.append({
                **row,
                "null_prediction": null_means[position],
                "strong_prediction": strong_baseline(
                    histories.get(row["gsis_id"], []), live_mean
                ),
            })
        if week_predictions:
            primary = select_primary_pool(week_predictions)
            for prediction in week_predictions:
                prediction["primary_pool"] = (
                    _natural_key(prediction) in primary
                )
            predictions.extend(week_predictions)

        # State-only and evaluated outcomes both become history only now.
        for row in weekly_rows:
            histories.setdefault(row["gsis_id"], []).append(
                row["fantasy_points"]
            )
            if _is_evaluation_row(row):
                position_sums[row["position"]] += row["fantasy_points"]
                position_counts[row["position"]] += 1
    return predictions
```

This preserves the old path because every legacy row is implicitly eligible.

- [ ] **Step 6: Dispatch the audit and label only the new report**

```python
def _validate_baseline_source_audit(audit, rows):
    if isinstance(audit, dict) and audit.get("population") == PRIOR_OBSERVED_POPULATION:
        _validate_prior_observed_audit(audit, rows)
        return PRIOR_OBSERVED_POPULATION
    _validate_source_audit(audit)
    _validate_audit_population(audit, rows)
    return "WEEKLY_ROSTER_ACT_QB_RB_FB_WR_TE"
```

At the start of `backtest_baselines`, canonicalize the audit, validate rows,
then call the dispatcher. Replace the hard-coded report population with its
return value. Build the existing report unchanged, then add only:

```python
if population == PRIOR_OBSERVED_POPULATION:
    report.update({
        "evidence_role": "DEVELOPMENT_ONLY",
        "leakage_status": "REVIEW_REQUIRED",
    })
```

Keep the fold loop, baseline formulas, metrics, serializers, and legacy report
keys unchanged.

- [ ] **Step 7: Run GREEN**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedBaselineTests `
  tests.test_pgo_fantasy.FantasyBaselineTests `
  tests.test_pgo_fantasy.FantasyReceiptTests -v
python -B -W error::ResourceWarning -m unittest tests.test_pgo_fantasy -v
```

Expected: `OK`; the new coverage gate raises before report creation and the
legacy report has no new keys.

- [ ] **Step 8: Commit Task 3**

```powershell
python -B -m py_compile pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --check
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git commit -m "feat: evaluate prior-observed fantasy baseline"
```

Expected: exactly the two code/test paths are committed.

---

### Task 4: Run final stability and scope gates

**Files:**
- Verify only: `pgo_fantasy.py`
- Verify only: `tests/test_pgo_fantasy.py`
- Verify only: protected model, research, public, workflow, and store paths

**Interfaces:**
- Consumes the three implementation commits.
- Produces no runtime artifact or model result.

- [ ] **Step 1: Run focused old and new fantasy verification**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.PriorObservedSourceContractTests `
  tests.test_pgo_fantasy.PriorObservedCohortTests `
  tests.test_pgo_fantasy.PriorObservedBaselineTests `
  tests.test_pgo_fantasy.FantasyPopulationTests `
  tests.test_pgo_fantasy.FantasySourceQualificationTests `
  tests.test_pgo_fantasy.FantasyBaselineTests `
  tests.test_pgo_fantasy.FantasyReceiptTests -v
```

Expected: `OK` without `ResourceWarning`.

- [ ] **Step 2: Run the complete repository gate**

```powershell
python -B -W error::ResourceWarning -m unittest discover -s tests -v
python -B -m py_compile pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --check 365712d..HEAD
```

Expected: the full suite reports `OK`; compilation and diff checks exit zero.

- [ ] **Step 3: Verify the changed-path allowlist**

```powershell
$allowed = @(
  'docs/superpowers/plans/2026-08-31-pgo-fantasy-prior-observed-cohort.md',
  'docs/superpowers/specs/2026-08-31-pgo-fantasy-prior-observed-cohort-design.md',
  'pgo_fantasy.py',
  'tests/test_pgo_fantasy.py'
) | Sort-Object
$changed = @(git diff --name-only 365712d..HEAD) | Sort-Object
$difference = @(Compare-Object $allowed $changed)
if ($difference.Count -ne 0) {
  $difference | Format-Table -AutoSize
  throw 'Changed-path allowlist mismatch'
}
```

Expected: no comparison output. Never expand the allowlist to an evidence,
public, workflow, or store path.

- [ ] **Step 4: Verify protected paths and the public HOLD label**

```powershell
git diff --exit-code 365712d..HEAD -- `
  research/pgo_v1 `
  research/pgo_stability_blend `
  research/pgo_fantasy `
  prospective_evidence `
  docs/index.html `
  .github/workflows `
  SHOPIFY.md
rg -F "Experimental model — HOLD" docs/index.html
```

Expected: protected diff is empty and the HOLD label is found.

- [ ] **Step 5: Perform the manual trust-boundary review**

```powershell
git diff 365712d..HEAD -- pgo_fantasy.py tests/test_pgo_fantasy.py
rg -n "prior_observed|PRIOR_OBSERVED|current_rows|history|point_coverage" `
  pgo_fantasy.py tests/test_pgo_fantasy.py
```

Confirm with direct code and test evidence:

- each source is read once and those same bytes are parsed and hashed;
- the new inventory has no weekly-roster source;
- membership and context are fixed before current-week targets join;
- histories update only after the entire week's rows are built;
- Week 1 and other state-only rows update player histories but never position
  means, pools, predictions, or metrics;
- transition targets join by GSIS while prior-known context stays frozen;
- zero-fill requires a scheduled last-known team;
- every test-week coverage ratio is recomputed and at least 95%;
- every test week fills all 96 primary slots;
- the old qualifier and roster baseline retain their contracts; and
- no path fetches, writes evidence, fits a candidate, publishes, pushes, or
  deploys.

Any failed conclusion requires one focused RED regression, the smallest shared
boundary fix, and complete reruns of Tasks 3 and 4.

- [ ] **Step 6: Record the local-only final state**

```powershell
git status --short --branch
git log -5 --oneline --decorate
```

Expected: implementation commits are local, `origin/main` is untouched, and
only the previously preserved unrelated untracked paths remain. Do not invoke
the new builder on any real cache or downloaded nflverse file.

## Completion boundary

Completion means the synthetic cohort and baseline report pass chronology,
coverage, compatibility, and protected-scope gates. It does not establish
provider-vintage cleanliness, predictive improvement, canonical backtest
validity, or publication readiness.

The next possible action is a separately approved read-only real-cache shadow.
Candidate fitting stays gated until that shadow demonstrates usable 96-player
and 95% point coverage without changing the contract after viewing results.
