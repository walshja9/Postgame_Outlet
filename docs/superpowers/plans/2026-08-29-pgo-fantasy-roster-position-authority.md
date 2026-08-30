# PGO Fantasy Roster Position Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make weekly nflverse roster position the sole platform-neutral fantasy population and position authority, while preserving exact source-byte qualification and separating blocking discrepancies from nonblocking diagnostics.

**Architecture:** Replace the duplicate model/qualification traversals in `pgo_fantasy.py` with one plain-data reconciliation result consumed by both `build_player_games()` and source qualification. Keep source-lock schema 1 and the same 13 inputs, advance only the qualification receipt to schema 2, and reuse the existing standard-library exclusive-write and ownership-safe rollback helpers under new v2 candidate filenames.

**Tech Stack:** Python standard library, existing `pgo_sources` helpers, `unittest`, Git, and PowerShell. No new package, module, service, source, or workflow.

## Global Constraints

- Historical scope is exactly regular seasons 2020 through 2025.
- Source inventory remains exactly one pinned schedule plus six weekly-roster and six player-weekly-stat files.
- Source-lock schema remains exactly `1`; qualification-receipt schema becomes exactly `2`.
- Weekly roster rows are the only population and position authority; eligible raw positions are QB, RB, FB, WR, and TE, with FB mapped to RB.
- Player-stat position is diagnostic metadata only and cannot change population, emitted position, target, ordering, FLEX, or Superflex views.
- Player statistics never add population rows, and display names never join or recover identity.
- Each completed team-week requires at least one relevant stat row joined to one exact eligible `ACT` roster identity before any unmatched eligible roster rows may be treated as verified zero targets.
- Do not add PFF, injury, practice, game-status, inactive, depth-chart, participation, betting, market, display-name identity, paid-source, or platform-specific eligibility inputs.
- Preserve exact UTF-8 source bytes, canonical finite sorted-key JSON, LF-only newlines, terminal newlines, pinned schedule digest validation, and one-read source hashing/parsing.
- Preserve exclusive no-overwrite publication, fixed-claim ownership, interruption cleanup, foreign-writer preservation, and accepted-directory no-overwrite behavior.
- Do not modify or regenerate the August 27 candidate lock or receipt:
  - lock SHA-256 `e2ec765babdc1319e36255e7ee2f69904aab4db2fd0dc9e7c7f5ea80793ce508`;
  - receipt SHA-256 `587aa5cab7d4c385c6a3bade1c942b8100e0823555efd17ea4d6fcb4a5555a4b`.
- Use only the new ignored v2 candidate paths:
  - `output/pgo-fantasy-source-v2-candidate.lock.json`;
  - `output/pgo-fantasy-source-v2-qualification.json`;
  - `output/.pgo-fantasy-source-v2-candidate.claim`.
- The one old-cache check writes only `output/pgo-fantasy-source-v2-development-shadow.json`; it is development evidence, never accepted research evidence.
- Do not run a new remote freeze, acceptance, canonical fantasy backtest, candidate fit, public fantasy board generation, site generation, push, deployment, or commerce work.
- Protect `research/pgo_v1/`, `research/pgo_stability_blend/`, `research/pgo_fantasy/`, `prospective_evidence/`, `docs/index.html`, `.github/workflows/`, and `SHOPIFY.md`.
- Preserve all unrelated untracked paths and use exact `git add -- <paths>` allowlists; never use `git add -A`.
- A `BLOCKED` semantic result is evidence, not an infrastructure failure. Any mismatch in the development-shadow assertions is a hard stop, not permission to change the expected values.

## File map

- Modify `pgo_fantasy.py`: define v2 receipt constants, replace duplicate reconciliation with one roster-authoritative result, validate schema-2 receipts, and point existing freeze/accept behavior at v2 candidate paths.
- Modify `tests/test_pgo_fantasy.py`: prove population/position authority, diagnostic behavior, schema-2 byte binding, and unchanged concurrency/write boundaries with synthetic fixtures.
- Create during execution only, ignored by Git: `output/pgo-fantasy-source-v2-development-shadow.json`.
- Do not create or modify any accepted research, public, workflow, store, or remote artifact.

---

### Task 1: Implement shared roster authority and receipt schema 2

**Files:**
- Modify: `pgo_fantasy.py:23-153`
- Modify: `pgo_fantasy.py:425-890`
- Modify: `pgo_fantasy.py:1406-1478`
- Test: `tests/test_pgo_fantasy.py:207-903`
- Test: `tests/test_pgo_fantasy.py:1342-1550`

**Interfaces:**
- Consumes: `_load_source_rows(paths) -> tuple[dict, list[dict]]`, `_load_schedule(rows) -> tuple[dict, dict]`, `half_ppr(row) -> float`, and exact source rows from the existing 13-source contract.
- Produces: `_reconcile_fantasy_population(source_rows: dict) -> dict` with keys `rows`, `coverage`, `blocking_discrepancies`, and `diagnostics`.
- Produces: `_build_player_games_from_sources(source_rows: dict, source_receipts: list[dict]) -> tuple[list[dict], dict]` and `build_player_games(paths) -> tuple[list[dict], dict]` backed by the same reconciliation result.
- Produces: `qualify_fantasy_sources(paths, source_lock_text) -> dict` with qualification schema 2 and `validate_fantasy_source_qualification(source_lock_text: str, receipt: dict) -> None`.
- Deletes: `_load_rosters`, `_load_stats`, and `_blocked_coverage`; no second population traversal remains.

- [ ] **Step 1: Rewrite the population regressions for roster authority**

In `FantasyPopulationTests`, retain the existing fixture writers and replace the old position-mismatch rejection cases with these tests:

```python
def test_stat_position_is_diagnostic_and_never_changes_model_rows(self):
    schedule, rosters, stats = self._base_rows()
    with tempfile.TemporaryDirectory() as directory:
        baseline_directory = Path(directory) / "baseline"
        changed_directory = Path(directory) / "changed"
        baseline_directory.mkdir()
        changed_directory.mkdir()
        baseline_paths = self._write_sources(
            baseline_directory, schedule, rosters, stats
        )
        baseline_rows, _ = pgo_fantasy.build_player_games(baseline_paths)

        changed_stats = copy.deepcopy(stats)
        changed_stats[2022][0]["position"] = "TE"
        changed_paths = self._write_sources(
            changed_directory, schedule, rosters, changed_stats
        )
        changed_rows, audit = pgo_fantasy.build_player_games(changed_paths)

    self.assertEqual(
        pgo_fantasy.serialize_fantasy_source_json({"rows": changed_rows}),
        pgo_fantasy.serialize_fantasy_source_json({"rows": baseline_rows}),
    )
    self.assertEqual(changed_rows[0]["position"], "QB")
    self.assertEqual(changed_rows[0]["fantasy_points"], 10.0)
    self.assertEqual(
        audit["diagnostics"]["counts"]["stat_position_disagreement"], 1
    )
    self.assertEqual(
        audit["diagnostics"]["fantasy_point_totals"]
        ["stat_position_disagreement"],
        10.0,
    )

def test_act_unmodeled_roster_stat_is_excluded_and_audited(self):
    schedule, rosters, stats = self._base_rows()
    rosters[2022].append(self._row(
        pgo_fantasy.ROSTER_COLUMNS,
        season="2022", week="1", game_type="REG", team="BUF",
        position="LB", status="ACT", full_name="Two Way Player",
        gsis_id="00-LB",
    ))
    stats[2022].append(self._row(
        pgo_fantasy.PLAYER_COLUMNS,
        player_id="00-LB", position="WR", season="2022", week="1",
        season_type="REG", game_id="2022_01_BUF_LAR", team="BUF",
        opponent_team="LAR", receiving_yards="50",
    ))

    with tempfile.TemporaryDirectory() as directory:
        rows, audit = pgo_fantasy.build_player_games(
            self._write_sources(directory, schedule, rosters, stats)
        )

    self.assertEqual({row["gsis_id"] for row in rows}, {"00-QB", "00-FB"})
    self.assertEqual(audit["coverage"]["2022"]["excluded_stats"], 1)
    self.assertEqual(
        audit["diagnostics"]["counts"]["act_unmodeled_roster_stat"], 1
    )
    self.assertEqual(
        audit["diagnostics"]["fantasy_point_totals"]
        ["act_unmodeled_roster_stat"],
        5.0,
    )

def test_noneligible_missing_identity_is_diagnostic_but_eligible_is_blocking(self):
    schedule, rosters, stats = self._base_rows()
    rosters[2022].append(self._row(
        pgo_fantasy.ROSTER_COLUMNS,
        season="2022", week="1", game_type="REG", team="BUF",
        position="LB", status="RES", full_name="Reserve Defender",
        gsis_id="",
    ))
    with tempfile.TemporaryDirectory() as directory:
        paths = self._write_sources(directory, schedule, rosters, stats)
        _, audit = pgo_fantasy.build_player_games(paths)
    self.assertEqual(
        audit["diagnostics"]["counts"]
        ["noneligible_roster_missing_identity"],
        1,
    )

    rosters[2022][-1].update(position="QB", status="ACT")
    with tempfile.TemporaryDirectory() as directory:
        paths = self._write_sources(directory, schedule, rosters, stats)
        with self.assertRaisesRegex(ValueError, "missing_roster_identity"):
            pgo_fantasy.build_player_games(paths)

def test_taysom_like_roster_qb_stat_te_emits_qb_target(self):
    schedule, rosters, stats = self._base_rows()
    stats[2022][0].update(
        position="TE", passing_yards="", rushing_yards="20",
        receptions="2", receiving_yards="30",
    )
    with tempfile.TemporaryDirectory() as directory:
        rows, audit = pgo_fantasy.build_player_games(
            self._write_sources(directory, schedule, rosters, stats)
        )
    quarterback = next(row for row in rows if row["gsis_id"] == "00-QB")
    self.assertEqual(quarterback["position"], "QB")
    self.assertEqual(quarterback["fantasy_points"], 6.0)
    self.assertEqual(
        audit["diagnostics"]["counts"]["stat_position_disagreement"], 1
    )
```

Keep `test_builds_act_population_maps_fullbacks_and_zero_fills_after_audit`, but add:

```python
self.assertEqual(audit["position_authority"], "NFLVERSE_WEEKLY_ROSTER")
self.assertEqual(audit["position_mapping"], {"FB": "RB"})
self.assertEqual(audit["coverage"]["2022"]["excluded_stats"], 0)
self.assertEqual(audit["blocking_discrepancies"]["total"], 0)
```

Remove only the `wrong position` and `ineligible position mismatch` entries from `test_rejects_unmatched_duplicate_or_contradictory_stats`; unmatched identity, duplicate stat identity, wrong team, and wrong week must still raise.

- [ ] **Step 2: Run the population tests to verify RED**

Run:

```powershell
python -B -m unittest tests.test_pgo_fantasy.FantasyPopulationTests -v
```

Expected: FAIL because position disagreements still raise, ACT LB/DB stats still attempt to expand or fail the population, the audit has no diagnostic sections, and eligible/noneligible missing identities are not distinguished.

- [ ] **Step 3: Define the exact v2 finding classes and metadata**

Replace `FANTASY_DISCREPANCY_CLASSES` with these definitions. Leave the three old candidate-path constants unchanged until Task 2 so the central semantic commit remains fully runnable.

```python
FANTASY_POSITION_AUTHORITY = "NFLVERSE_WEEKLY_ROSTER"
FANTASY_POSITION_MAPPING = {"FB": "RB"}
FANTASY_BLOCKING_CLASSES = (
    "incomplete_team_coverage",
    "incomplete_team_week_coverage",
    "incomplete_stat_team_week_coverage",
    "missing_roster_identity",
    "missing_roster_status",
    "duplicate_roster_identity",
    "conflicting_team",
    "missing_stat_identity",
    "duplicate_stat_identity",
    "missing_roster",
    "non_act_roster",
    "schedule_identity",
    "invalid_fantasy_target",
)
FANTASY_DIAGNOSTIC_CLASSES = (
    "stat_position_disagreement",
    "act_unmodeled_roster_stat",
    "noneligible_roster_missing_identity",
)
FANTASY_POINT_DIAGNOSTICS = (
    "stat_position_disagreement",
    "act_unmodeled_roster_stat",
)
FANTASY_BLOCKING_ROW_FIELDS = frozenset({
    "reason", "season", "week", "gsis_id", "game_id", "team",
    "source", "source_row_number",
})
FANTASY_DIAGNOSTIC_ROW_FIELDS = frozenset({
    "reason", "season", "week", "gsis_id", "game_id", "team",
    "roster_status", "raw_roster_position", "fantasy_position",
    "raw_stat_position", "player_name", "source_row_number",
    "fantasy_points",
})
```

Keep `POSITION_MAP` unchanged. It already expresses QB/RB/WR/TE identity mappings and FB-to-RB normalization without a new abstraction.

- [ ] **Step 4: Add deterministic finding constructors and summaries**

Replace `_discrepancy()` and `_discrepancy_key()` with these complete helpers:

```python
def _blocking(
    reason, season, week=0, gsis_id="", game_id="", team="",
    source="", source_row_number=0,
):
    return {
        "reason": reason,
        "season": season,
        "week": week,
        "gsis_id": gsis_id,
        "game_id": game_id,
        "team": team,
        "source": source,
        "source_row_number": source_row_number,
    }


def _diagnostic(
    reason, season, week=0, gsis_id="", game_id="", team="",
    roster_status="", raw_roster_position="", fantasy_position="",
    raw_stat_position="", player_name="", source_row_number=0,
    fantasy_points=0.0,
):
    return {
        "reason": reason,
        "season": season,
        "week": week,
        "gsis_id": gsis_id,
        "game_id": game_id,
        "team": team,
        "roster_status": roster_status,
        "raw_roster_position": raw_roster_position,
        "fantasy_position": fantasy_position,
        "raw_stat_position": raw_stat_position,
        "player_name": player_name,
        "source_row_number": source_row_number,
        "fantasy_points": fantasy_points,
    }


def _finding_key(row):
    return (
        row["reason"], row["season"], row["week"], row["gsis_id"],
        row["game_id"], row["team"], row.get("source", ""),
        row["source_row_number"], row.get("raw_roster_position", ""),
        row.get("raw_stat_position", ""),
    )


def _summarize_findings(rows, classes, point_classes=()):
    unique = {tuple(sorted(row.items())) for row in rows}
    ordered = sorted((dict(items) for items in unique), key=_finding_key)
    summary = {
        "total": len(ordered),
        "counts": {
            reason: sum(row["reason"] == reason for row in ordered)
            for reason in classes
        },
        "by_season": {
            str(season): {
                reason: sum(
                    row["season"] == season and row["reason"] == reason
                    for row in ordered
                )
                for reason in classes
            }
            for season in MODEL_SEASONS
        },
        "rows": ordered,
    }
    if point_classes:
        summary["fantasy_point_totals"] = {
            reason: round(math.fsum(
                row["fantasy_points"]
                for row in ordered
                if row["reason"] == reason
            ), 10)
            for reason in point_classes
        }
    return summary
```

The `source_row_number` is the one-based CSV data-line number including the header, so enumeration starts at `2`. This preserves all 51 noneligible missing-ID source rows rather than collapsing identical natural keys.

- [ ] **Step 5: Implement one roster-authoritative reconciliation result**

Replace `_load_rosters`, `_load_stats`, `_reconcile_fantasy_population`, and `_blocked_coverage` with one `_reconcile_fantasy_population(source_rows)` implementation that follows this exact order:

```python
def _has_admitted_scoring(row):
    return any(_number(row, name) != 0 for name in SCORING_FIELDS)


def _empty_coverage():
    return {
        str(season): {
            "eligible": 0,
            "matched_stats": 0,
            "zero_filled": 0,
            "bye_skipped": 0,
            "excluded_stats": 0,
        }
        for season in MODEL_SEASONS
    }


def _reconcile_fantasy_population(source_rows):
    games, team_weeks = _load_schedule(
        source_rows[("schedule_results", None)]
    )
    coverage = _empty_coverage()
    roster_index = {}
    stat_index = {}
    roster_teams = {season: set() for season in MODEL_SEASONS}
    roster_team_weeks = set()
    relevant_stat_team_weeks = set()
    relevant_roster_keys = set()
    blocking = []
    diagnostics = []

    for source_season in MODEL_SEASONS:
        source = f"weekly_rosters:{source_season}"
        for row_number, row in enumerate(
            source_rows[("weekly_rosters", source_season)], start=2
        ):
            season = _integer(row, "season", "roster")
            if season != source_season:
                raise ValueError(
                    f"Roster source-season mismatch: {source_season} != {season}"
                )
            if (row.get("game_type") or "").strip() != "REG":
                continue
            week = _integer(row, "week", "roster")
            team = normalize_team(row.get("team") or "")
            raw_position = (row.get("position") or "").strip().upper()
            fantasy_position = POSITION_MAP.get(raw_position)
            status = (row.get("status") or "").strip().upper()
            gsis_id = (row.get("gsis_id") or "").strip()
            player_name = (row.get("full_name") or "").strip()
            roster_teams[season].add(team)
            roster_team_weeks.add((season, week, team))

            if fantasy_position is not None and not status:
                blocking.append(_blocking(
                    "missing_roster_status", season, week, gsis_id,
                    team=team, source=source, source_row_number=row_number,
                ))
            eligible = fantasy_position is not None and status == "ACT"
            if not gsis_id:
                if eligible:
                    blocking.append(_blocking(
                        "missing_roster_identity", season, week, team=team,
                        source=source, source_row_number=row_number,
                    ))
                else:
                    diagnostics.append(_diagnostic(
                        "noneligible_roster_missing_identity", season, week,
                        team=team, roster_status=status,
                        raw_roster_position=raw_position,
                        fantasy_position=fantasy_position or "",
                        player_name=player_name,
                        source_row_number=row_number,
                    ))
                continue
            roster_index.setdefault((season, week, gsis_id), []).append({
                "season": season,
                "week": week,
                "gsis_id": gsis_id,
                "team": team,
                "status": status,
                "raw_position": raw_position,
                "fantasy_position": fantasy_position,
                "player_name": player_name,
                "eligible": eligible,
                "source": source,
                "source_row_number": row_number,
            })

    for season in MODEL_SEASONS:
        for team in sorted(set(CURRENT_TEAMS) - roster_teams[season]):
            blocking.append(_blocking(
                "incomplete_team_coverage", season, team=team,
                source=f"weekly_rosters:{season}",
            ))
    for season, week, team in sorted(set(team_weeks) - roster_team_weeks):
        blocking.append(_blocking(
            "incomplete_team_week_coverage", season, week, team=team,
            source=f"weekly_rosters:{season}",
        ))

    for source_season in MODEL_SEASONS:
        source = f"player_weekly_stats:{source_season}"
        for row_number, row in enumerate(
            source_rows[("player_weekly_stats", source_season)], start=2
        ):
            season = _integer(row, "season", "stat")
            if season != source_season:
                raise ValueError(
                    f"Stat source-season mismatch: {source_season} != {season}"
                )
            if (row.get("season_type") or "").strip() != "REG":
                continue
            week = _integer(row, "week", "stat")
            gsis_id = (row.get("player_id") or "").strip()
            raw_position = (row.get("position") or "").strip().upper()
            stat_position = POSITION_MAP.get(raw_position)
            key = (season, week, gsis_id)
            roster_records = roster_index.get(key, []) if gsis_id else []
            try:
                has_scoring = _has_admitted_scoring(row)
                fantasy_points = half_ppr(row)
            except ValueError:
                blocking.append(_blocking(
                    "invalid_fantasy_target", season, week, gsis_id,
                    game_id=(row.get("game_id") or "").strip(),
                    team=normalize_team(row.get("team") or ""),
                    source=source, source_row_number=row_number,
                ))
                continue
            relevant = (
                stat_position is not None
                or has_scoring
                or any(record["eligible"] for record in roster_records)
            )
            if not relevant:
                continue
            if not gsis_id:
                blocking.append(_blocking(
                    "missing_stat_identity", season, week,
                    game_id=(row.get("game_id") or "").strip(),
                    team=normalize_team(row.get("team") or ""),
                    source=source, source_row_number=row_number,
                ))
                continue
            relevant_roster_keys.add(key)
            record = {
                "season": season,
                "week": week,
                "gsis_id": gsis_id,
                "game_id": (row.get("game_id") or "").strip(),
                "team": normalize_team(row.get("team") or ""),
                "opponent": normalize_team(row.get("opponent_team") or ""),
                "raw_position": raw_position,
                "stat_position": stat_position,
                "fantasy_points": fantasy_points,
                "row": row,
                "source": source,
                "source_row_number": row_number,
            }
            stat_index.setdefault(key, []).append(record)

    for key, records in sorted(roster_index.items()):
        relevant = any(record["eligible"] for record in records) or (
            key in relevant_roster_keys
        )
        if not relevant:
            continue
        teams = sorted({record["team"] for record in records})
        if len(records) > 1:
            blocking.append(_blocking(
                "duplicate_roster_identity", *key, team=",".join(teams),
                source=f"weekly_rosters:{key[0]}",
            ))
        if len(teams) > 1:
            blocking.append(_blocking(
                "conflicting_team", *key, team=",".join(teams),
                source=f"weekly_rosters:{key[0]}",
            ))

    matched_stats = {}
    for key, stats in sorted(stat_index.items()):
        if len(stats) > 1:
            blocking.append(_blocking(
                "duplicate_stat_identity", *key,
                game_id=stats[0]["game_id"], team=stats[0]["team"],
                source=f"player_weekly_stats:{key[0]}",
            ))
        rosters = roster_index.get(key, [])
        for stat in stats:
            if not rosters:
                blocking.append(_blocking(
                    "missing_roster", *key, game_id=stat["game_id"],
                    team=stat["team"], source=stat["source"],
                    source_row_number=stat["source_row_number"],
                ))
                continue
            if len(rosters) != 1:
                continue
            roster = rosters[0]
            game = games.get(stat["game_id"])
            expected = team_weeks.get((key[0], key[1], roster["team"]))
            schedule_valid = (
                game is not None
                and game["season"] == key[0]
                and game["week"] == key[1]
                and roster["team"] == stat["team"]
                and expected == (stat["game_id"], stat["opponent"])
            )
            if not schedule_valid:
                blocking.append(_blocking(
                    "schedule_identity", *key, game_id=stat["game_id"],
                    team=stat["team"], source=stat["source"],
                    source_row_number=stat["source_row_number"],
                ))
            if roster["status"] != "ACT":
                blocking.append(_blocking(
                    "non_act_roster", *key, game_id=stat["game_id"],
                    team=roster["team"], source=stat["source"],
                    source_row_number=stat["source_row_number"],
                ))
                continue
            if roster["fantasy_position"] is None:
                diagnostics.append(_diagnostic(
                    "act_unmodeled_roster_stat", *key,
                    game_id=stat["game_id"], team=roster["team"],
                    roster_status=roster["status"],
                    raw_roster_position=roster["raw_position"],
                    raw_stat_position=stat["raw_position"],
                    player_name=roster["player_name"],
                    source_row_number=stat["source_row_number"],
                    fantasy_points=stat["fantasy_points"],
                ))
                coverage[str(key[0])]["excluded_stats"] += 1
                continue
            if stat["raw_position"] and (
                stat["stat_position"] != roster["fantasy_position"]
            ):
                diagnostics.append(_diagnostic(
                    "stat_position_disagreement", *key,
                    game_id=stat["game_id"], team=roster["team"],
                    roster_status=roster["status"],
                    raw_roster_position=roster["raw_position"],
                    fantasy_position=roster["fantasy_position"],
                    raw_stat_position=stat["raw_position"],
                    player_name=roster["player_name"],
                    source_row_number=stat["source_row_number"],
                    fantasy_points=stat["fantasy_points"],
                ))
            if schedule_valid and len(stats) == 1:
                matched_stats[key] = stat
                relevant_stat_team_weeks.add(
                    (key[0], key[1], roster["team"])
                )

    for season, week, team in sorted(
        set(team_weeks) - relevant_stat_team_weeks
    ):
        blocking.append(_blocking(
            "incomplete_stat_team_week_coverage", season, week, team=team,
            source=f"player_weekly_stats:{season}",
        ))

    rows = []
    for key, records in sorted(roster_index.items()):
        if len(records) != 1 or not records[0]["eligible"]:
            continue
        roster = records[0]
        expected = team_weeks.get((key[0], key[1], roster["team"]))
        if expected is None:
            coverage[str(key[0])]["bye_skipped"] += 1
            continue
        coverage[str(key[0])]["eligible"] += 1
        stat = matched_stats.get(key)
        coverage[str(key[0])][
            "matched_stats" if stat is not None else "zero_filled"
        ] += 1
        rows.append({
            "season": key[0],
            "week": key[1],
            "game_id": expected[0],
            "gsis_id": key[2],
            "player_name": roster["player_name"],
            "team": roster["team"],
            "opponent": expected[1],
            "position": roster["fantasy_position"],
            "fantasy_points": (
                0.0 if stat is None else stat["fantasy_points"]
            ),
        })
    rows.sort(key=lambda row: (
        row["season"], row["week"], row["game_id"], row["gsis_id"]
    ))
    return {
        "rows": rows,
        "coverage": coverage,
        "blocking_discrepancies": _summarize_findings(
            blocking, FANTASY_BLOCKING_CLASSES
        ),
        "diagnostics": _summarize_findings(
            diagnostics, FANTASY_DIAGNOSTIC_CLASSES,
            FANTASY_POINT_DIAGNOSTICS,
        ),
    }
```

Do not add a dataclass, adapter, resolver class, player allowlist, or platform overlay. The plain dictionary is the shared boundary needed here.

- [ ] **Step 6: Route the model builder through the shared result**

Replace `_build_player_games_from_sources` with:

```python
def _build_player_games_from_sources(source_rows, source_receipts):
    result = _reconcile_fantasy_population(source_rows)
    blocking = result["blocking_discrepancies"]
    if blocking["total"]:
        reasons = ", ".join(
            reason for reason, count in blocking["counts"].items() if count
        )
        raise ValueError(
            f"Fantasy source qualification has blocking discrepancies: {reasons}"
        )
    if not result["rows"]:
        raise ValueError("Fantasy population contains zero eligible player-games")
    audit = {
        "schema_version": 2,
        "scope": dict(FANTASY_SCOPE),
        "position_authority": FANTASY_POSITION_AUTHORITY,
        "position_mapping": dict(FANTASY_POSITION_MAPPING),
        "sources": source_receipts,
        "coverage": result["coverage"],
        "blocking_discrepancies": blocking,
        "diagnostics": result["diagnostics"],
        "checks": {
            "source_contract": True,
            "schedule_identity": True,
            "roster_identity": True,
            "stat_identity": True,
            "finite_targets": True,
        },
    }
    return result["rows"], audit
```

Keep `build_player_games(paths)` as its existing one-line wrapper around the one loaded byte snapshot.

- [ ] **Step 7: Run the population tests to verify GREEN**

Run:

```powershell
python -B -m unittest tests.test_pgo_fantasy.FantasyPopulationTests -v
```

Expected: exit `0`; every population test ends in `ok`; final line `OK`.

- [ ] **Step 8: Continue directly to the receipt consumer before committing**

Do not commit the intermediate state: the old qualifier still expects the deleted traversal. Continue with the remaining Task 1 steps below so both public consumers route through the shared result in one green commit.

#### Task 1B: Emit and validate qualification receipt schema 2

**Files:**
- Modify: `pgo_fantasy.py:836-983`
- Test: `tests/test_pgo_fantasy.py:562-903`

**Interfaces:**
- Consumes: `_reconcile_fantasy_population(source_rows) -> dict` from the earlier Task 1 steps and source-lock schema-1 canonical text.
- Completes the Task 1 interfaces declared above; diagnostics may be nonzero, but validation requires zero blockers and every PASS check.

- [ ] **Step 1: Add schema-2 receipt and semantic regressions**

Update the clean qualification test to assert this exact top-level contract:

```python
self.assertEqual(receipt["schema_version"], 2)
self.assertEqual(receipt["position_authority"], "NFLVERSE_WEEKLY_ROSTER")
self.assertEqual(receipt["position_mapping"], {"FB": "RB"})
self.assertEqual(receipt["blocking_discrepancies"]["total"], 0)
self.assertEqual(receipt["diagnostics"]["total"], 0)
self.assertEqual(receipt["coverage"]["2022"], {
    "eligible": 2,
    "matched_stats": 2,
    "zero_filled": 0,
    "bye_skipped": 0,
    "excluded_stats": 0,
})
```

Add these focused tests to `FantasySourceQualificationTests`:

```python
def test_schema_one_qualification_receipt_cannot_pass_v2_validation(self):
    with tempfile.TemporaryDirectory() as directory:
        paths = self._qualification_paths(directory)
        with self._fixture_schedule_digest(paths):
            lock_text = self._source_lock_text(paths)
            receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
            receipt["schema_version"] = 1
            with self.assertRaisesRegex(ValueError, "not PASS"):
                pgo_fantasy.validate_fantasy_source_qualification(
                    lock_text, receipt
                )

def test_stat_position_disagreement_is_nonblocking_and_deterministic(self):
    def mutate(schedule, rosters, stats):
        stats[2022][0]["position"] = "TE"

    with tempfile.TemporaryDirectory() as directory:
        paths = self._qualification_paths(directory, mutate)
        with self._fixture_schedule_digest(paths):
            lock_text = self._source_lock_text(paths)
            first = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
            second = pgo_fantasy.qualify_fantasy_sources(
                dict(reversed(list(paths.items()))), lock_text
            )
            pgo_fantasy.validate_fantasy_source_qualification(
                lock_text, first
            )

    self.assertEqual(first, second)
    self.assertEqual(first["qualification_status"], "PASS")
    self.assertEqual(first["blocking_discrepancies"]["total"], 0)
    self.assertEqual(
        first["diagnostics"]["counts"]["stat_position_disagreement"], 1
    )

def test_act_unmodeled_scoring_stat_is_excluded_not_population(self):
    def mutate(schedule, rosters, stats):
        rosters[2022].append(self._row(
            pgo_fantasy.ROSTER_COLUMNS,
            season="2022", week="1", game_type="REG", team="BUF",
            position="DB", status="ACT", full_name="Hybrid Defender",
            gsis_id="HYBRID-DB",
        ))
        stats[2022].append(self._row(
            pgo_fantasy.PLAYER_COLUMNS,
            player_id="HYBRID-DB", position="WR", season="2022", week="1",
            season_type="REG", game_id="2022_01_BUF_LAR", team="BUF",
            opponent_team="LAR", receptions="1", receiving_yards="10",
        ))

    with tempfile.TemporaryDirectory() as directory:
        paths = self._qualification_paths(directory, mutate)
        with self._fixture_schedule_digest(paths):
            lock_text = self._source_lock_text(paths)
            receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
            pgo_fantasy.validate_fantasy_source_qualification(
                lock_text, receipt
            )

    self.assertEqual(receipt["qualification_status"], "PASS")
    self.assertEqual(receipt["coverage"]["2022"]["eligible"], 2)
    self.assertEqual(receipt["coverage"]["2022"]["excluded_stats"], 1)
    self.assertEqual(
        receipt["diagnostics"]["fantasy_point_totals"]
        ["act_unmodeled_roster_stat"],
        1.5,
    )

def test_noneligible_missing_ids_keep_every_source_row(self):
    def mutate(schedule, rosters, stats):
        for name in ("First", "Second"):
            rosters[2022].append(self._row(
                pgo_fantasy.ROSTER_COLUMNS,
                season="2022", week="1", game_type="REG", team="BUF",
                position="LB", status="RES", full_name=name, gsis_id="",
            ))

    with tempfile.TemporaryDirectory() as directory:
        paths = self._qualification_paths(directory, mutate)
        with self._fixture_schedule_digest(paths):
            receipt = pgo_fantasy.qualify_fantasy_sources(
                paths, self._source_lock_text(paths)
            )

    rows = [
        row for row in receipt["diagnostics"]["rows"]
        if row["reason"] == "noneligible_roster_missing_identity"
    ]
    self.assertEqual(len(rows), 2)
    self.assertNotEqual(rows[0]["source_row_number"], rows[1]["source_row_number"])
```

In the existing `test_reports_all_discrepancy_classes_deterministically` mutation, append these rows so every v2 blocker and diagnostic class is exercised:

```python
rosters[season].extend([
    self._row(
        pgo_fantasy.ROSTER_COLUMNS,
        season="2022", week="1", game_type="REG", team="BUF",
        position="QB", status="ACT", full_name="Invalid Target",
        gsis_id="INVALID-TARGET",
    ),
    self._row(
        pgo_fantasy.ROSTER_COLUMNS,
        season="2022", week="1", game_type="REG", team="BUF",
        position="DB", status="ACT", full_name="Hybrid Defender",
        gsis_id="HYBRID-DB",
    ),
    self._row(
        pgo_fantasy.ROSTER_COLUMNS,
        season="2022", week="1", game_type="REG", team="BUF",
        position="LB", status="RES", full_name="Missing Noneligible ID",
        gsis_id="",
    ),
])
stats[season].extend([
    self._row(
        pgo_fantasy.PLAYER_COLUMNS,
        player_id="INVALID-TARGET", position="QB", season="2022",
        week="1", season_type="REG", game_id=game_id, team="BUF",
        opponent_team="LAR", passing_yards="NaN",
    ),
    self._row(
        pgo_fantasy.PLAYER_COLUMNS,
        player_id="HYBRID-DB", position="WR", season="2022", week="1",
        season_type="REG", game_id=game_id, team="BUF",
        opponent_team="LAR", receptions="1", receiving_yards="10",
    ),
])
```

Keep its two differently ordered qualification calls, then replace the old exact v1 row assertions with:

```python
self.assertEqual(first, second)
self.assertEqual(first["qualification_status"], "BLOCKED")
self.assertEqual(
    {row["reason"] for row in first["blocking_discrepancies"]["rows"]},
    set(pgo_fantasy.FANTASY_BLOCKING_CLASSES),
)
self.assertEqual(
    {row["reason"] for row in first["diagnostics"]["rows"]},
    set(pgo_fantasy.FANTASY_DIAGNOSTIC_CLASSES),
)
for name, classes in (
    ("blocking_discrepancies", pgo_fantasy.FANTASY_BLOCKING_CLASSES),
    ("diagnostics", pgo_fantasy.FANTASY_DIAGNOSTIC_CLASSES),
):
    summary = first[name]
    self.assertEqual(summary["rows"], sorted(
        summary["rows"], key=pgo_fantasy._finding_key
    ))
    self.assertEqual(summary["counts"], {
        reason: sum(row["reason"] == reason for row in summary["rows"])
        for reason in classes
    })
    self.assertEqual(summary["by_season"], {
        str(season): {
            reason: sum(
                row["season"] == season and row["reason"] == reason
                for row in summary["rows"]
            )
            for reason in classes
        }
        for season in pgo_fantasy.MODEL_SEASONS
    })
```

Replace `test_unmapped_stat_for_eligible_roster_is_position_contradiction` with:

```python
def test_unmapped_stat_position_is_nonblocking_diagnostic(self):
    def mutate(schedule, rosters, stats):
        stats[2022][0]["position"] = "K"

    with tempfile.TemporaryDirectory() as directory:
        paths = self._qualification_paths(directory, mutate)
        with self._fixture_schedule_digest(paths):
            lock_text = self._source_lock_text(paths)
            receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
            pgo_fantasy.validate_fantasy_source_qualification(
                lock_text, receipt
            )

    self.assertEqual(receipt["qualification_status"], "PASS")
    self.assertEqual(receipt["blocking_discrepancies"]["total"], 0)
    self.assertEqual(
        receipt["diagnostics"]["counts"]["stat_position_disagreement"], 1
    )
    self.assertEqual(receipt["coverage"]["2022"], {
        "eligible": 2,
        "matched_stats": 2,
        "zero_filled": 0,
        "bye_skipped": 0,
        "excluded_stats": 0,
    })
```

For every remaining blocked test, use `blocking_discrepancies` instead of `discrepancies`, add `excluded_stats` to coverage dictionaries, and keep all-postseason, junk-only, missing-team-week, no-roster, non-ACT, duplicate identity, schedule mismatch, source mutation, and exact-lock binding behavior unchanged.

- [ ] **Step 2: Run qualification tests to verify RED**

Run:

```powershell
python -B -m unittest tests.test_pgo_fantasy.FantasySourceQualificationTests -v
```

Expected: FAIL because `qualify_fantasy_sources()` still emits schema 1 with one undifferentiated discrepancy section and its validator rejects every nonzero diagnostic.

- [ ] **Step 3: Build the schema-2 receipt from the shared result**

Replace `qualify_fantasy_sources()` with:

```python
def qualify_fantasy_sources(paths, source_lock_text):
    lock = _load_fantasy_source_lock(source_lock_text)
    source_rows, source_receipts = _load_source_rows(paths)
    locked = {
        (entry["name"], entry["season"]): entry
        for entry in lock["sources"]
    }
    for source in source_receipts:
        entry = locked[(source["name"], source["season"])]
        if (
            source["bytes"] != entry["bytes"]
            or source["sha256"] != entry["sha256"]
        ):
            raise ValueError("Fantasy source bytes do not match the lock")

    result = _reconcile_fantasy_population(source_rows)
    blocking = result["blocking_discrepancies"]
    counts = blocking["counts"]
    checks = {
        "source_contract": True,
        "locked_bytes": True,
        "schedule_identity": counts["schedule_identity"] == 0,
        "team_coverage": all(
            counts[name] == 0 for name in (
                "incomplete_team_coverage",
                "incomplete_team_week_coverage",
            )
        ),
        "roster_identity": all(
            counts[name] == 0 for name in (
                "missing_roster_identity", "missing_roster_status",
                "duplicate_roster_identity", "conflicting_team",
            )
        ),
        "stat_identity": all(
            counts[name] == 0 for name in (
                "missing_stat_identity", "duplicate_stat_identity",
                "missing_roster", "non_act_roster",
            )
        ),
        "stat_team_week_coverage": (
            counts["incomplete_stat_team_week_coverage"] == 0
        ),
        "population_reconciliation": blocking["total"] == 0,
        "finite_targets": counts["invalid_fantasy_target"] == 0,
    }
    return {
        "schema_version": 2,
        "qualification_status": "PASS" if all(checks.values()) else "BLOCKED",
        "artifact_availability": "LOCAL_CACHE_ONLY",
        "source_lock_sha256": hashlib.sha256(
            source_lock_text.encode("utf-8")
        ).hexdigest(),
        "scope": dict(FANTASY_SCOPE),
        "position_authority": FANTASY_POSITION_AUTHORITY,
        "position_mapping": dict(FANTASY_POSITION_MAPPING),
        "source_count": len(source_receipts),
        "sources": source_receipts,
        "checks": checks,
        "coverage": result["coverage"],
        "blocking_discrepancies": blocking,
        "diagnostics": result["diagnostics"],
    }
```

- [ ] **Step 4: Validate counts, rows, point totals, and exact schema**

Add this helper immediately before `validate_fantasy_source_qualification()`:

```python
def _validate_finding_summary(summary, classes, row_fields, point_classes=()):
    required = {"total", "counts", "by_season", "rows"}
    if point_classes:
        required.add("fantasy_point_totals")
    if not isinstance(summary, dict) or set(summary) != required:
        raise ValueError("Fantasy source qualification is not PASS")
    rows = summary["rows"]
    counts = summary["counts"]
    if (
        type(summary["total"]) is not int
        or not isinstance(rows, list)
        or summary["total"] != len(rows)
        or any(not isinstance(row, dict) or set(row) != row_fields for row in rows)
        or not isinstance(counts, dict)
        or set(counts) != set(classes)
        or any(
            type(value) is not int or value < 0
            for value in counts.values()
        )
    ):
        raise ValueError("Fantasy source qualification is not PASS")
    string_fields = set(row_fields) - {
        "season", "week", "source_row_number", "fantasy_points"
    }
    for row in rows:
        if (
            row["reason"] not in classes
            or type(row["season"]) is not int
            or row["season"] not in MODEL_SEASONS
            or type(row["week"]) is not int
            or row["week"] < 0
            or type(row["source_row_number"]) is not int
            or row["source_row_number"] < 0
            or any(not isinstance(row[name], str) for name in string_fields)
        ):
            raise ValueError("Fantasy source qualification is not PASS")
        if "fantasy_points" in row and (
            isinstance(row["fantasy_points"], bool)
            or not isinstance(row["fantasy_points"], (int, float))
            or not math.isfinite(row["fantasy_points"])
        ):
            raise ValueError("Fantasy source qualification is not PASS")
    if (
        rows != sorted(rows, key=_finding_key)
        or len({tuple(sorted(row.items())) for row in rows}) != len(rows)
        or counts != {
            reason: sum(row["reason"] == reason for row in rows)
            for reason in classes
        }
    ):
        raise ValueError("Fantasy source qualification is not PASS")
    expected_by_season = {
        str(season): {
            reason: sum(
                row["season"] == season and row["reason"] == reason
                for row in rows
            )
            for reason in classes
        }
        for season in MODEL_SEASONS
    }
    if summary["by_season"] != expected_by_season:
        raise ValueError("Fantasy source qualification is not PASS")
    if point_classes:
        point_totals = summary["fantasy_point_totals"]
        expected_points = {
            reason: round(math.fsum(
                row["fantasy_points"]
                for row in rows if row["reason"] == reason
            ), 10)
            for reason in point_classes
        }
        if (
            not isinstance(point_totals, dict)
            or set(point_totals) != set(point_classes)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in point_totals.values()
            )
            or point_totals != expected_points
            or any(not math.isfinite(value) for value in expected_points.values())
        ):
            raise ValueError("Fantasy source qualification is not PASS")
```

Replace the top-level validator field set with:

```python
required = {
    "schema_version", "qualification_status", "artifact_availability",
    "source_lock_sha256", "scope", "position_authority",
    "position_mapping", "source_count", "sources", "checks", "coverage",
    "blocking_discrepancies", "diagnostics",
}
```

Require exact integer schema `2`, exact position metadata, all checks `True`, and zero blocking rows. Validate the two summaries with the field constants defined earlier in Task 1:

```python
_validate_finding_summary(
    receipt["blocking_discrepancies"],
    FANTASY_BLOCKING_CLASSES,
    FANTASY_BLOCKING_ROW_FIELDS,
)
_validate_finding_summary(
    receipt["diagnostics"],
    FANTASY_DIAGNOSTIC_CLASSES,
    FANTASY_DIAGNOSTIC_ROW_FIELDS,
    FANTASY_POINT_DIAGNOSTICS,
)
if receipt["blocking_discrepancies"]["total"] != 0:
    raise ValueError("Fantasy source qualification is not PASS")
```

For each season, require coverage keys exactly:

```python
{
    "eligible", "matched_stats", "zero_filled", "bye_skipped",
    "excluded_stats",
}
```

Require every value to be a nonnegative exact integer, require `matched_stats + zero_filled == eligible`, and require `excluded_stats` to equal that season's `act_unmodeled_roster_stat` diagnostic count. Keep the existing source-count, source-order, byte-count, SHA-256, lock-hash, canonical-finite-JSON, and PASS-only checks unchanged.

- [ ] **Step 5: Advance the internal source audit with the same diagnostics**

`build_player_games()` now returns additional provenance, so update `_validate_source_audit()` rather than stripping that information before the baseline boundary. Require exact schema `2`, the exact top-level keys emitted by `_build_player_games_from_sources`, exact position metadata, an empty validated blocker summary, a validated diagnostic summary, and the five-field coverage contract.

Replace the initial contract check in `_validate_source_audit()` with:

```python
if (
    not isinstance(source_audit, dict)
    or set(source_audit) != {
        "schema_version", "scope", "position_authority",
        "position_mapping", "sources", "coverage",
        "blocking_discrepancies", "diagnostics", "checks",
    }
    or type(source_audit.get("schema_version")) is not int
    or source_audit["schema_version"] != 2
    or source_audit.get("scope") != FANTASY_SCOPE
    or source_audit.get("position_authority") != FANTASY_POSITION_AUTHORITY
    or source_audit.get("position_mapping") != FANTASY_POSITION_MAPPING
    or source_audit.get("checks") != {
        name: True for name in AUDIT_CHECKS
    }
):
    raise ValueError("Source audit contract is invalid")
_validate_finding_summary(
    source_audit["blocking_discrepancies"],
    FANTASY_BLOCKING_CLASSES,
    FANTASY_BLOCKING_ROW_FIELDS,
)
_validate_finding_summary(
    source_audit["diagnostics"],
    FANTASY_DIAGNOSTIC_CLASSES,
    FANTASY_DIAGNOSTIC_ROW_FIELDS,
    FANTASY_POINT_DIAGNOSTICS,
)
if source_audit["blocking_discrepancies"]["total"] != 0:
    raise ValueError("Source audit contract is invalid")
```

Change its coverage field set to:

```python
fields = {
    "eligible", "matched_stats", "zero_filled", "bye_skipped",
    "excluded_stats",
}
```

Keep the existing nonnegative exact-integer and `matched_stats + zero_filled == eligible` checks, then require each season's `excluded_stats` to equal the same season's `act_unmodeled_roster_stat` diagnostic count.

Update `FantasyBaselineTests._audit()` to emit schema `2`, position metadata, `excluded_stats: 0`, and empty summaries made with the production summary helper:

```python
"schema_version": 2,
"position_authority": pgo_fantasy.FANTASY_POSITION_AUTHORITY,
"position_mapping": dict(pgo_fantasy.FANTASY_POSITION_MAPPING),
"blocking_discrepancies": pgo_fantasy._summarize_findings(
    [], pgo_fantasy.FANTASY_BLOCKING_CLASSES
),
"diagnostics": pgo_fantasy._summarize_findings(
    [],
    pgo_fantasy.FANTASY_DIAGNOSTIC_CLASSES,
    pgo_fantasy.FANTASY_POINT_DIAGNOSTICS,
),
```

Add `"excluded_stats": 0` to every season's fixture coverage. Change the deliberately incomplete audit in `test_backtest_rejects_incomplete_or_mismatched_source_audit` to `{"schema_version": 2, "checks": {"source_contract": True}}`; the expected rejection remains unchanged.

- [ ] **Step 6: Run qualification, population, and baseline-contract tests to verify GREEN**

Run:

```powershell
python -B -m unittest `
  tests.test_pgo_fantasy.FantasyPopulationTests `
  tests.test_pgo_fantasy.FantasySourceQualificationTests `
  tests.test_pgo_fantasy.FantasyBaselineTests `
  tests.test_pgo_fantasy.FantasyReceiptTests -v
```

Expected: exit `0`; final line `OK`.

- [ ] **Step 7: Commit the shared semantics and schema 2 together**

Run:

```powershell
git diff --check
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --cached --name-only
git commit -m "feat: use roster authority for fantasy qualification"
```

Expected staged paths before commit, exactly:

```text
pgo_fantasy.py
tests/test_pgo_fantasy.py
```

---

### Task 2: Preserve the v2 freeze and acceptance trust boundary

**Files:**
- Modify: `pgo_fantasy.py:986-1183`
- Test: `tests/test_pgo_fantasy.py:904-1340`

**Interfaces:**
- Consumes: the existing `_exclusive_write_text`, `_unlink_owned`, `_freeze_and_qualify`, `_accept_qualified_sources`, and `main` control flow.
- Produces: the same CLI flags and exit codes under v2 candidate filenames: `--freeze-sources` returns `0` PASS, `1` semantic BLOCKED, `2` operational failure; `--accept-qualified` remains offline and no-overwrite.
- Preserves: source-lock schema 1, raw-byte canonical validation, candidate claim behavior, and accepted paths under `research/pgo_fantasy/`.

- [ ] **Step 1: Update command tests to the v2 paths and add legacy isolation**

Replace every hard-coded old output path in `FantasySourceCommandTests` with the corresponding constant or v2 filename. Then add:

```python
def test_v2_freeze_never_reads_or_writes_august_27_candidate_paths(self):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        old_lock = root / "output/pgo-fantasy-source-candidate.lock.json"
        old_receipt = root / "output/pgo-fantasy-source-qualification.json"
        old_lock.parent.mkdir(parents=True)
        old_lock.write_bytes(b"immutable old lock\n")
        old_receipt.write_bytes(b"immutable old receipt\n")
        payloads = self._payloads(root)

        code = self._run_in_root(
            root,
            ["--freeze-sources", "--frozen-at", self.AS_OF],
            payloads,
        )

        self.assertEqual(code, 0)
        self.assertEqual(old_lock.read_bytes(), b"immutable old lock\n")
        self.assertEqual(old_receipt.read_bytes(), b"immutable old receipt\n")
        self.assertTrue((root / pgo_fantasy.FANTASY_CANDIDATE_LOCK).exists())
        self.assertTrue((
            root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
        ).exists())

def test_accept_rejects_schema_one_receipt_without_fetch_or_research(self):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        payloads = self._payloads(root)
        self.assertEqual(self._run_in_root(
            root,
            ["--freeze-sources", "--frozen-at", self.AS_OF],
            payloads,
        ), 0)
        receipt_path = root / pgo_fantasy.FANTASY_QUALIFICATION_OUTPUT
        receipt = json.loads(receipt_path.read_bytes().decode("utf-8"))
        receipt["schema_version"] = 1
        receipt_path.write_bytes(
            pgo_fantasy.serialize_fantasy_source_json(receipt).encode("utf-8")
        )

        schedule = next(
            spec for spec in pgo_fantasy.fantasy_source_specs()
            if spec.name == "schedule_results"
        )
        digest = hashlib.sha256(payloads[schedule.url]).hexdigest()
        previous = Path.cwd()
        os.chdir(root)
        try:
            with patch.object(
                pgo_sources, "EXPECTED_SOURCE_SHA256", digest
            ), patch.object(
                pgo_sources, "freeze_sources"
            ) as freeze, redirect_stderr(io.StringIO()):
                code = pgo_fantasy.main(["--accept-qualified"])
        finally:
            os.chdir(previous)

        self.assertEqual(code, 2)
        freeze.assert_not_called()
        self.assertFalse((root / "research/pgo_fantasy").exists())
```

Update operational diagnostic expectations to schema version `2` and the v2 qualification path. Keep every existing CRLF, duplicate-key, noncanonical lock, pinned-digest, source mutation, concurrent claim, interloper preservation, write failure, interruption cleanup, and accepted-directory rollback test.

- [ ] **Step 2: Run command tests to verify RED**

Run:

```powershell
python -B -m unittest tests.test_pgo_fantasy.FantasySourceCommandTests -v
```

Expected: FAIL until all command-path assertions use the new v2 constants and the operational receipt declares schema 2.

- [ ] **Step 3: Make the minimal CLI changes**

Keep the existing CLI flags, claim algorithm, exclusive writer, ownership-aware cleanup, and accepted directory unchanged. First replace only the three candidate-path constants:

```python
FANTASY_CANDIDATE_LOCK = Path(
    "output/pgo-fantasy-source-v2-candidate.lock.json"
)
FANTASY_QUALIFICATION_OUTPUT = Path(
    "output/pgo-fantasy-source-v2-qualification.json"
)
FANTASY_CANDIDATE_CLAIM = Path(
    "output/.pgo-fantasy-source-v2-candidate.claim"
)
```

Then make only these remaining production changes:

```python
def _operational_blocked_receipt(error):
    return {
        "schema_version": 2,
        "qualification_status": "BLOCKED",
        "artifact_availability": "LOCAL_CACHE_ONLY",
        "error": f"{type(error).__name__}: {error}",
    }
```

Change the temporary pending-file prefix to make v2 residue identifiable:

```python
prefix=".pgo-fantasy-source-v2-"
```

Do not change `_accept_qualified_sources()` beyond consuming the v2 constants defined immediately above. Its raw `read_bytes().decode("utf-8")`, strict lock load, offline cache requalification, exact serialized receipt comparison, accepted-directory preflight, and rollback already implement the approved boundary.

- [ ] **Step 4: Run all fantasy tests and adversarial command tests**

Run:

```powershell
python -B -W error::ResourceWarning -m unittest tests.test_pgo_fantasy -v
```

Expected: exit `0`; all fantasy tests end in `ok`; final line `OK`.

- [ ] **Step 5: Commit the v2 write boundary**

Run:

```powershell
git diff --check
git add -- pgo_fantasy.py tests/test_pgo_fantasy.py
git diff --cached --name-only
git commit -m "fix: isolate fantasy qualification v2 outputs"
```

Expected staged paths before commit, exactly:

```text
pgo_fantasy.py
tests/test_pgo_fantasy.py
```

---

### Task 3: Run the one permitted August 27 development shadow

**Files:**
- Read only: `D:\CodexWorktrees\Postgame_Outlet-fantasy-source-qualification\output\pgo-fantasy-source-candidate.lock.json`
- Read only: `D:\CodexWorktrees\Postgame_Outlet-fantasy-source-qualification\output\pgo-fantasy-source-qualification.json`
- Read only: `D:\CodexWorktrees\Postgame_Outlet-fantasy-source-qualification\.cache\pgo_fantasy\`
- Create ignored: `output/pgo-fantasy-source-v2-development-shadow.json`

**Interfaces:**
- Consumes: the exact old schema-1 source lock and 13 cached files; it does not consume the old BLOCKED qualification receipt as authority.
- Produces: one ignored schema-2 qualification receipt at the development-shadow path after every expected inventory assertion passes.
- Does not produce: a v2 candidate pair, accepted research evidence, backtest, model fit, public artifact, push, or deployment.

- [ ] **Step 1: Prove the immutable inputs and empty outputs before reading the cache**

Run from `D:\Claude Context\Postgame_Outlet`:

```powershell
$oldRoot = 'D:\CodexWorktrees\Postgame_Outlet-fantasy-source-qualification'
Get-FileHash -Algorithm SHA256 -LiteralPath `
  "$oldRoot\output\pgo-fantasy-source-candidate.lock.json", `
  "$oldRoot\output\pgo-fantasy-source-qualification.json"
Test-Path -LiteralPath 'output\pgo-fantasy-source-v2-development-shadow.json'
Test-Path -LiteralPath 'research\pgo_fantasy'
```

Expected hashes, in order:

```text
E2EC765BABDC1319E36255E7EE2F69904AAB4DB2FD0DC9E7C7F5EA80793CE508
587AA5CAB7D4C385C6A3BADE1C942B8100E0823555EFD17EA4D6FCB4A5555A4B
```

Expected final two values: `False`, `False`. Stop if a hash differs or either path exists.

- [ ] **Step 2: Execute exactly one local-cache shadow invocation**

Run this command once. Do not retry if it raises or an assertion fails.

```powershell
@'
import hashlib
from pathlib import Path

import pgo_fantasy
import pgo_sources

old_root = Path(r"D:\CodexWorktrees\Postgame_Outlet-fantasy-source-qualification")
lock_path = old_root / "output/pgo-fantasy-source-candidate.lock.json"
cache_dir = old_root / ".cache/pgo_fantasy"
shadow_path = Path("output/pgo-fantasy-source-v2-development-shadow.json")
lock_bytes = lock_path.read_bytes()
assert hashlib.sha256(lock_bytes).hexdigest() == (
    "e2ec765babdc1319e36255e7ee2f69904aab4db2fd0dc9e7c7f5ea80793ce508"
)
lock_text = lock_bytes.decode("utf-8")
paths = pgo_sources.load_locked_sources(lock_path, cache_dir)
assert len(paths) == 13
receipt = pgo_fantasy.qualify_fantasy_sources(paths, lock_text)
assert receipt["schema_version"] == 2
assert receipt["qualification_status"] == "PASS"
assert receipt["blocking_discrepancies"]["total"] == 0
assert receipt["diagnostics"]["counts"] == {
    "stat_position_disagreement": 312,
    "act_unmodeled_roster_stat": 45,
    "noneligible_roster_missing_identity": 51,
}
assert receipt["diagnostics"]["fantasy_point_totals"] == {
    "stat_position_disagreement": 895.14,
    "act_unmodeled_roster_stat": 24.5,
}
coverage = receipt["coverage"]
assert sum(row["eligible"] for row in coverage.values()) == 44908
assert sum(row["matched_stats"] for row in coverage.values()) == 35519
assert sum(row["zero_filled"] for row in coverage.values()) == 9389
assert sum(row["excluded_stats"] for row in coverage.values()) == 45
assert not Path("research/pgo_fantasy").exists()
shadow_path.parent.mkdir(parents=True, exist_ok=True)
pgo_fantasy._exclusive_write_text(
    shadow_path,
    pgo_fantasy.serialize_fantasy_source_json(receipt),
)
print(hashlib.sha256(shadow_path.read_bytes()).hexdigest())
'@ | python -B -
```

Expected: exit `0` and exactly one SHA-256 line for the new shadow file. The exact shadow hash is recorded in the execution report; it is not predeclared because it is derived from the implementation under review.

- [ ] **Step 3: Recheck immutability and evidence separation**

Run:

```powershell
$oldRoot = 'D:\CodexWorktrees\Postgame_Outlet-fantasy-source-qualification'
Get-FileHash -Algorithm SHA256 -LiteralPath `
  "$oldRoot\output\pgo-fantasy-source-candidate.lock.json", `
  "$oldRoot\output\pgo-fantasy-source-qualification.json"
Test-Path -LiteralPath 'output\pgo-fantasy-source-v2-candidate.lock.json'
Test-Path -LiteralPath 'output\pgo-fantasy-source-v2-qualification.json'
Test-Path -LiteralPath 'research\pgo_fantasy'
git status --short
```

Expected: the two old hashes are unchanged; all three `Test-Path` results are `False`; the ignored development shadow does not appear in Git status; no commit is made for this task.

---

### Task 4: Run repository, leakage, and protected-scope gates

**Files:**
- Verify only: entire repository
- Modify: none

**Interfaces:**
- Consumes: the two implementation commits and the ignored development shadow.
- Produces: an evidence-backed review decision only; no source, model, public, remote, or deployment mutation.

- [ ] **Step 1: Run focused and complete test gates**

Run one uninterrupted process for each command:

```powershell
python -B -W error::ResourceWarning -m unittest tests.test_pgo_fantasy -v
python -B -W error::ResourceWarning -m unittest discover -s tests -v
python -B -m py_compile pgo_fantasy.py tests\test_pgo_fantasy.py
git diff --check
```

Expected: every command exits `0`; each unittest run ends with `OK`; compilation and `git diff --check` print nothing.

- [ ] **Step 2: Run the explicit leakage review**

Invoke the `leakage-audit` skill and audit the implementation at the player-game grain and weekly pregame decision boundary. Confirm from code and tests that:

```text
population source = same-week weekly roster only
position source = same-week weekly roster only
target source = same-game player stats only
stat position affects diagnostics only
display name affects diagnostics only
stat-only identities never create model rows
zero filling requires relevant-stat team-week coverage
```

Run these mechanical checks:

```powershell
rg -n "player_name|full_name|raw_stat_position|stat_position|fantasy_position" pgo_fantasy.py
rg -n -i "pff|injury|practice|inactive|depth.?chart|participation|betting|market" pgo_fantasy.py
python -B -m unittest `
  tests.test_pgo_fantasy.FantasyPopulationTests.test_stat_position_is_diagnostic_and_never_changes_model_rows `
  tests.test_pgo_fantasy.FantasySourceQualificationTests.test_unmodeled_nonroster_stats_do_not_satisfy_team_week_coverage -v
```

Expected: the first search shows names and stat positions only in emitted metadata/diagnostics and roster positions in model rows; the prohibited-input search has no matches; both regressions pass. Stop on any target, temporal, join, preprocessing, or split-leakage finding.

- [ ] **Step 3: Prove exact implementation scope**

Because Tasks 1-2 create exactly two commits, run:

```powershell
$changed = @(git diff --name-only HEAD~2..HEAD)
$allowed = @('pgo_fantasy.py', 'tests/test_pgo_fantasy.py')
Compare-Object -ReferenceObject $allowed -DifferenceObject $changed
git diff --exit-code HEAD~2..HEAD -- `
  research/pgo_v1 `
  research/pgo_stability_blend `
  research/pgo_fantasy `
  prospective_evidence `
  docs/index.html `
  .github/workflows `
  SHOPIFY.md
git show --check --oneline HEAD~1 HEAD
```

Expected: `Compare-Object`, protected-path diff, and `git show --check` report no differences/errors beyond the two one-line commit headers from the final command.

- [ ] **Step 4: Prove the old evidence and public HOLD remain unchanged**

Run:

```powershell
$oldRoot = 'D:\CodexWorktrees\Postgame_Outlet-fantasy-source-qualification'
Get-FileHash -Algorithm SHA256 -LiteralPath `
  "$oldRoot\output\pgo-fantasy-source-candidate.lock.json", `
  "$oldRoot\output\pgo-fantasy-source-qualification.json"
Select-String -LiteralPath 'docs\index.html' -Pattern 'Experimental model . HOLD'
git status --short --branch
```

Expected: the old hashes remain exactly `E2EC765B...E508` and `587AA5CA...5A4B`; the public page still contains the HOLD label; status contains only the pre-existing unrelated untracked paths and no tracked modification.

- [ ] **Step 5: Perform an independent correctness review before handoff**

Review the complete `HEAD~2..HEAD` diff and the shadow receipt against every section of `docs/superpowers/specs/2026-08-29-pgo-fantasy-roster-position-authority-design.md`. The review must explicitly attempt to falsify:

- roster-only population and position authority;
- stat-position model-row invariance;
- completeness and deterministic order of blocker/diagnostic rows;
- schema-1 lock plus schema-2 receipt binding;
- old-candidate isolation;
- no-overwrite and rollback behavior under races/interruption;
- absence of names, outcomes, or stat position in population selection;
- the exact 312/45/51 diagnostic and 44,908/35,519/9,389 coverage inventory; and
- every protected-path and release boundary.

Expected decision: `PASS` only with no unresolved Critical or Important finding. A finding or shadow mismatch stops the slice for diagnosis; it does not authorize a refreeze, acceptance, backtest, publication, push, or deployment.

## Execution stop

After Task 4, report the two code commit SHAs, focused/full test results, development-shadow hash and exact counts, old immutable hashes, leakage decision, protected-scope result, and Git status. Stop and request a separate decision before any new remote v2 freeze. Even a clean schema-2 development shadow does not authorize source acceptance or model execution.
