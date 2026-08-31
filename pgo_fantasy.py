"""Independent half-PPR fantasy baselines built from frozen nflverse files."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from pgo_model import CURRENT_TEAMS, SOURCE_URL
import pgo_sources
from pgo_sources import SourceSpec, atomic_write_text, normalize_team


MODEL_SEASONS = tuple(range(2020, 2026))
TEST_SEASONS = (2022, 2023, 2024, 2025)
POSITION_MAP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE"}

SCHEDULE_COLUMNS = (
    "game_id",
    "season",
    "week",
    "game_type",
    "gameday",
    "gametime",
    "away_team",
    "home_team",
    "away_score",
    "home_score",
)
ROSTER_COLUMNS = (
    "season",
    "week",
    "game_type",
    "team",
    "position",
    "status",
    "full_name",
    "gsis_id",
)
SCORING_FIELDS = frozenset({
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "passing_2pt_conversions",
    "rushing_yards",
    "rushing_tds",
    "rushing_2pt_conversions",
    "receptions",
    "receiving_yards",
    "receiving_tds",
    "receiving_2pt_conversions",
    "special_teams_tds",
    "fumbles_lost_total",
})
PLAYER_COLUMNS = (
    "player_id",
    "position",
    "season",
    "week",
    "season_type",
    "game_id",
    "team",
    "opponent_team",
    *sorted(SCORING_FIELDS),
)
TWO_POINT_FIELDS = (
    "passing_2pt_conversions",
    "rushing_2pt_conversions",
    "receiving_2pt_conversions",
)
PREDICTION_COLUMNS = (
    "season",
    "week",
    "game_id",
    "gsis_id",
    "player_name",
    "team",
    "opponent",
    "position",
    "fantasy_points",
    "null_prediction",
    "strong_prediction",
    "primary_pool",
)
AUDIT_CHECKS = frozenset({
    "source_contract",
    "schedule_identity",
    "roster_identity",
    "stat_identity",
    "finite_targets",
})


def fantasy_source_specs() -> tuple[SourceSpec, ...]:
    specs = [SourceSpec("schedule_results", None, SOURCE_URL, SCHEDULE_COLUMNS)]
    for season in MODEL_SEASONS:
        specs.extend((
            SourceSpec(
                "weekly_rosters",
                season,
                "https://github.com/nflverse/nflverse-data/releases/download/"
                f"weekly_rosters/roster_weekly_{season}.csv",
                ROSTER_COLUMNS,
            ),
            SourceSpec(
                "player_weekly_stats",
                season,
                "https://github.com/nflverse/nflverse-data/releases/download/"
                f"stats_player/stats_player_week_{season}.csv.gz",
                PLAYER_COLUMNS,
            ),
        ))
    return tuple(specs)


def prior_observed_source_specs() -> tuple[SourceSpec, ...]:
    return tuple(
        spec for spec in fantasy_source_specs()
        if spec.name != "weekly_rosters"
    )


FANTASY_CACHE_DIR = Path(".cache/pgo_fantasy")
FANTASY_CANDIDATE_LOCK = Path(
    "output/pgo-fantasy-source-v2-candidate.lock.json"
)
FANTASY_QUALIFICATION_OUTPUT = Path(
    "output/pgo-fantasy-source-v2-qualification.json"
)
FANTASY_CANDIDATE_CLAIM = Path(
    "output/.pgo-fantasy-source-v2-candidate.claim"
)
FANTASY_ACCEPTED_DIR = Path("research/pgo_fantasy")
FANTASY_SCOPE = {
    "seasons": list(MODEL_SEASONS),
    "game_type": "REG",
    "roster_status": "ACT",
}
FANTASY_POSITION_AUTHORITY = "NFLVERSE_WEEKLY_ROSTER"
FANTASY_POSITION_MAPPING = {"FB": "RB"}
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
    "stat_position_disagreement", "act_unmodeled_roster_stat",
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
    specs = {(spec.name, spec.season): spec for spec in fantasy_source_specs()}
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
        if not isinstance(name, str) or (season is not None and type(season) is not int):
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
        if (
            key == ("schedule_results", None)
            and digest != pgo_sources.EXPECTED_SOURCE_SHA256
        ):
            raise ValueError("schedule_results does not match pinned SHA-256")
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
    if not isinstance(lock, dict) or set(lock) != {"schema_version", "scope", "sources"}:
        raise ValueError("Fantasy source lock is invalid")
    if type(lock["schema_version"]) is not int or lock["schema_version"] != 1:
        raise ValueError("Fantasy source lock schema is invalid")
    if not isinstance(lock["sources"], list):
        raise ValueError("Fantasy source lock sources are invalid")
    try:
        raw_manifest = {
            "sources": [
                {name: entry[name] for name in (
                    "name", "season", "url", "sha256", "bytes", "frozen_at"
                )}
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
            value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise ValueError("Fantasy source evidence must contain finite JSON") from error


def _reject_duplicate_json_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Fantasy source lock contains duplicate JSON key")
        value[key] = item
    return value


def _load_fantasy_source_lock(source_lock_text):
    try:
        lock = json.loads(
            source_lock_text,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (TypeError, ValueError) as error:
        if "duplicate JSON key" in str(error):
            raise
        raise ValueError("Fantasy source lock is invalid JSON") from error
    validate_fantasy_source_lock(lock)
    if serialize_fantasy_source_json(lock) != source_lock_text:
        raise ValueError("Fantasy source lock serialization is not canonical")
    return lock


def _number(row, name):
    raw = row.get(name, "")
    try:
        value = 0.0 if raw in (None, "") else float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {name}: {raw!r}") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def half_ppr(row) -> float:
    score = (
        0.04 * _number(row, "passing_yards")
        + 4 * _number(row, "passing_tds")
        - 2 * _number(row, "passing_interceptions")
        + 0.1 * _number(row, "rushing_yards")
        + 0.1 * _number(row, "receiving_yards")
        + 6 * (_number(row, "rushing_tds") + _number(row, "receiving_tds"))
        + 0.5 * _number(row, "receptions")
        - 2 * _number(row, "fumbles_lost_total")
        + 2 * sum(_number(row, name) for name in TWO_POINT_FIELDS)
        + 6 * _number(row, "special_teams_tds")
    )
    if not math.isfinite(score):
        raise ValueError("Fantasy score must be finite")
    return score


def _source_label(key):
    name, season = key
    return name if season is None else f"{name}:{season}"


def _source_key_sort(key):
    return key[0], -1 if key[1] is None else key[1]


def _load_source_rows(paths, source_specs=None):
    source_specs = (
        fantasy_source_specs()
        if source_specs is None
        else tuple(source_specs)
    )
    specs = {(spec.name, spec.season): spec for spec in source_specs}
    received = set(paths)
    missing = sorted(set(specs) - received, key=_source_key_sort)
    if missing:
        raise ValueError(f"Missing source: {_source_label(missing[0])}")
    unexpected = sorted(received - set(specs), key=_source_key_sort)
    if unexpected:
        raise ValueError(f"Unexpected source: {_source_label(unexpected[0])}")

    source_rows = {}
    receipts = []
    for key, spec in specs.items():
        path = Path(paths[key])
        data = path.read_bytes()
        try:
            raw = gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"{_source_label(key)} is not readable CSV") from error
        if not rows:
            raise ValueError(f"{_source_label(key)} contains zero data rows")
        missing_columns = [
            column for column in spec.required_columns if column not in rows[0]
        ]
        if missing_columns:
            raise ValueError(
                f"{_source_label(key)} missing required columns: "
                + ", ".join(missing_columns)
            )
        source_rows[key] = rows
        receipts.append({
            "name": key[0],
            "season": key[1],
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "rows": len(rows),
        })
    receipts.sort(key=lambda row: _source_key_sort((row["name"], row["season"])))
    return source_rows, receipts


def _integer(row, name, label):
    raw = (row.get(name) or "").strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"Invalid {label} {name}: {raw!r}") from error
    return value


def _load_schedule(rows):
    games = {}
    team_weeks = {}
    for row in rows:
        season = _integer(row, "season", "schedule")
        if season not in MODEL_SEASONS or (row.get("game_type") or "").strip() != "REG":
            continue
        if (row.get("away_score") or "").strip() == "" or (
            row.get("home_score") or ""
        ).strip() == "":
            continue
        for name in ("away_score", "home_score"):
            score = _number(row, name)
            if score < 0:
                raise ValueError(f"Invalid schedule {name}: {score}")
        week = _integer(row, "week", "schedule")
        game_id = (row.get("game_id") or "").strip()
        if not game_id:
            raise ValueError("Missing schedule game_id")
        away = normalize_team(row.get("away_team") or "")
        home = normalize_team(row.get("home_team") or "")
        if away == home:
            raise ValueError(f"Schedule teams match for {game_id}")
        if game_id in games:
            raise ValueError(f"Duplicate schedule game_id: {game_id}")
        game = {
            "season": season,
            "week": week,
            "game_id": game_id,
            "away": away,
            "home": home,
        }
        games[game_id] = game
        for team, opponent in ((away, home), (home, away)):
            key = (season, week, team)
            if key in team_weeks:
                raise ValueError(f"Duplicate schedule team-week: {key}")
            team_weeks[key] = (game_id, opponent)
    if not games:
        raise ValueError("Schedule contains zero completed regular-season games")
    return games, team_weeks


def build_player_games(paths) -> tuple[list[dict], dict]:
    return _build_player_games_from_sources(*_load_source_rows(paths))


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
            if not gsis_id:
                raise ValueError("Missing prior-observed stat identity")
            key = season, week, gsis_id
            if key in seen:
                raise ValueError(f"Duplicate prior-observed player-week: {key}")
            seen.add(key)
            if parsed["position"] is None:
                diagnostics.append(_prior_observed_diagnostic(
                    "unsupported_position", parsed
                ))
                continue
            by_week.setdefault((season, week), []).append(parsed)
    for rows in by_week.values():
        rows.sort(key=lambda row: (row["gsis_id"], row["game_id"]))
    diagnostics.sort(key=_prior_observed_diagnostic_key)
    return by_week, diagnostics


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


def _blocking(reason, season, week=0, gsis_id="", game_id="", team="",
              source="", source_row_number=0):
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


def _diagnostic(reason, season, week=0, gsis_id="", game_id="", team="",
                roster_status="", raw_roster_position="", fantasy_position="",
                raw_stat_position="", player_name="", source_row_number=0,
                fantasy_points=0.0):
    return {
        "reason": reason, "season": season, "week": week, "gsis_id": gsis_id,
        "game_id": game_id, "team": team, "roster_status": roster_status,
        "raw_roster_position": raw_roster_position,
        "fantasy_position": fantasy_position,
        "raw_stat_position": raw_stat_position, "player_name": player_name,
        "source_row_number": source_row_number, "fantasy_points": fantasy_points,
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
    result = {
        "total": len(ordered),
        "counts": {reason: sum(row["reason"] == reason for row in ordered)
                   for reason in classes},
        "by_season": {str(season): {
            reason: sum(row["season"] == season and row["reason"] == reason
                        for row in ordered) for reason in classes}
            for season in MODEL_SEASONS},
        "rows": ordered,
    }
    if point_classes:
        result["fantasy_point_totals"] = {
            reason: round(math.fsum(row["fantasy_points"] for row in ordered
                                    if row["reason"] == reason), 10)
            for reason in point_classes}
    return result


def _has_admitted_scoring(row):
    return any(_number(row, name) != 0 for name in SCORING_FIELDS)


def _empty_coverage():
    return {str(season): {"eligible": 0, "matched_stats": 0,
                          "zero_filled": 0, "bye_skipped": 0,
                          "excluded_stats": 0}
            for season in MODEL_SEASONS}


def _reconcile_fantasy_population(source_rows):
    games, team_weeks = _load_schedule(source_rows[("schedule_results", None)])
    coverage, roster_index, stat_index = _empty_coverage(), {}, {}
    roster_teams = {season: set() for season in MODEL_SEASONS}
    roster_team_weeks, relevant_stat_team_weeks = set(), set()
    relevant_roster_keys, blocking, diagnostics = set(), [], []
    for source_season in MODEL_SEASONS:
        source = f"weekly_rosters:{source_season}"
        for row_number, row in enumerate(source_rows[("weekly_rosters", source_season)], 2):
            season = _integer(row, "season", "roster")
            if season != source_season:
                raise ValueError(f"Roster source-season mismatch: {source_season} != {season}")
            if (row.get("game_type") or "").strip() != "REG": continue
            week, team = _integer(row, "week", "roster"), normalize_team(row.get("team") or "")
            raw_position = (row.get("position") or "").strip().upper()
            fantasy_position = POSITION_MAP.get(raw_position)
            status, gsis_id = (row.get("status") or "").strip().upper(), (row.get("gsis_id") or "").strip()
            player_name = (row.get("full_name") or "").strip()
            roster_teams[season].add(team); roster_team_weeks.add((season, week, team))
            if fantasy_position is not None and not status:
                blocking.append(_blocking("missing_roster_status", season, week, gsis_id, team=team, source=source, source_row_number=row_number))
            eligible = fantasy_position is not None and status == "ACT"
            if not gsis_id:
                if eligible:
                    blocking.append(_blocking("missing_roster_identity", season, week, team=team, source=source, source_row_number=row_number))
                else:
                    diagnostics.append(_diagnostic("noneligible_roster_missing_identity", season, week, team=team, roster_status=status, raw_roster_position=raw_position, fantasy_position=fantasy_position or "", player_name=player_name, source_row_number=row_number))
                continue
            roster_index.setdefault((season, week, gsis_id), []).append({
                "season": season, "week": week, "gsis_id": gsis_id, "team": team,
                "status": status, "raw_position": raw_position,
                "fantasy_position": fantasy_position, "player_name": player_name,
                "eligible": eligible, "source": source, "source_row_number": row_number})
    for season in MODEL_SEASONS:
        for team in sorted(set(CURRENT_TEAMS) - roster_teams[season]):
            blocking.append(_blocking("incomplete_team_coverage", season, team=team, source=f"weekly_rosters:{season}"))
    for season, week, team in sorted(set(team_weeks) - roster_team_weeks):
        blocking.append(_blocking("incomplete_team_week_coverage", season, week, team=team, source=f"weekly_rosters:{season}"))
    for source_season in MODEL_SEASONS:
        source = f"player_weekly_stats:{source_season}"
        for row_number, row in enumerate(source_rows[("player_weekly_stats", source_season)], 2):
            season = _integer(row, "season", "stat")
            if season != source_season:
                raise ValueError(f"Stat source-season mismatch: {source_season} != {season}")
            if (row.get("season_type") or "").strip() != "REG": continue
            week, gsis_id = _integer(row, "week", "stat"), (row.get("player_id") or "").strip()
            raw_position = (row.get("position") or "").strip().upper()
            stat_position, key = POSITION_MAP.get(raw_position), (season, week, gsis_id)
            roster_records = roster_index.get(key, []) if gsis_id else []
            try:
                has_scoring, fantasy_points = _has_admitted_scoring(row), half_ppr(row)
            except ValueError:
                blocking.append(_blocking("invalid_fantasy_target", season, week, gsis_id, game_id=(row.get("game_id") or "").strip(), team=normalize_team(row.get("team") or ""), source=source, source_row_number=row_number)); continue
            if not (stat_position is not None or has_scoring or any(record["eligible"] for record in roster_records)): continue
            if not gsis_id:
                blocking.append(_blocking("missing_stat_identity", season, week, game_id=(row.get("game_id") or "").strip(), team=normalize_team(row.get("team") or ""), source=source, source_row_number=row_number)); continue
            relevant_roster_keys.add(key)
            stat_index.setdefault(key, []).append({"season": season, "week": week, "gsis_id": gsis_id, "game_id": (row.get("game_id") or "").strip(), "team": normalize_team(row.get("team") or ""), "opponent": normalize_team(row.get("opponent_team") or ""), "raw_position": raw_position, "stat_position": stat_position, "fantasy_points": fantasy_points, "source": source, "source_row_number": row_number})
    for key, records in sorted(roster_index.items()):
        if not (any(record["eligible"] for record in records) or key in relevant_roster_keys): continue
        teams = sorted({record["team"] for record in records})
        if len(records) > 1: blocking.append(_blocking("duplicate_roster_identity", *key, team=",".join(teams), source=f"weekly_rosters:{key[0]}"))
        if len(teams) > 1: blocking.append(_blocking("conflicting_team", *key, team=",".join(teams), source=f"weekly_rosters:{key[0]}"))
    matched_stats = {}
    for key, stats in sorted(stat_index.items()):
        if len(stats) > 1: blocking.append(_blocking("duplicate_stat_identity", *key, game_id=stats[0]["game_id"], team=stats[0]["team"], source=f"player_weekly_stats:{key[0]}"))
        rosters = roster_index.get(key, [])
        for stat in stats:
            if not rosters:
                blocking.append(_blocking("missing_roster", *key, game_id=stat["game_id"], team=stat["team"], source=stat["source"], source_row_number=stat["source_row_number"])); continue
            if len(rosters) != 1: continue
            roster, game = rosters[0], games.get(stat["game_id"])
            expected = team_weeks.get((key[0], key[1], roster["team"]))
            schedule_valid = game is not None and game["season"] == key[0] and game["week"] == key[1] and roster["team"] == stat["team"] and expected == (stat["game_id"], stat["opponent"])
            if not schedule_valid: blocking.append(_blocking("schedule_identity", *key, game_id=stat["game_id"], team=stat["team"], source=stat["source"], source_row_number=stat["source_row_number"]))
            if roster["status"] != "ACT":
                blocking.append(_blocking("non_act_roster", *key, game_id=stat["game_id"], team=roster["team"], source=stat["source"], source_row_number=stat["source_row_number"])); continue
            if roster["fantasy_position"] is None:
                diagnostics.append(_diagnostic("act_unmodeled_roster_stat", *key, game_id=stat["game_id"], team=roster["team"], roster_status=roster["status"], raw_roster_position=roster["raw_position"], raw_stat_position=stat["raw_position"], player_name=roster["player_name"], source_row_number=stat["source_row_number"], fantasy_points=stat["fantasy_points"])); coverage[str(key[0])]["excluded_stats"] += 1; continue
            if stat["raw_position"] and stat["stat_position"] != roster["fantasy_position"]:
                diagnostics.append(_diagnostic("stat_position_disagreement", *key, game_id=stat["game_id"], team=roster["team"], roster_status=roster["status"], raw_roster_position=roster["raw_position"], fantasy_position=roster["fantasy_position"], raw_stat_position=stat["raw_position"], player_name=roster["player_name"], source_row_number=stat["source_row_number"], fantasy_points=stat["fantasy_points"]))
            if schedule_valid and len(stats) == 1:
                matched_stats[key] = stat; relevant_stat_team_weeks.add((key[0], key[1], roster["team"]))
    for season, week, team in sorted(set(team_weeks) - relevant_stat_team_weeks):
        blocking.append(_blocking("incomplete_stat_team_week_coverage", season, week, team=team, source=f"player_weekly_stats:{season}"))
    rows = []
    for key, records in sorted(roster_index.items()):
        if len(records) != 1 or not records[0]["eligible"]: continue
        roster, expected = records[0], team_weeks.get((key[0], key[1], records[0]["team"]))
        if expected is None: coverage[str(key[0])]["bye_skipped"] += 1; continue
        coverage[str(key[0])]["eligible"] += 1
        stat = matched_stats.get(key); coverage[str(key[0])]["matched_stats" if stat else "zero_filled"] += 1
        rows.append({"season": key[0], "week": key[1], "game_id": expected[0], "gsis_id": key[2], "player_name": roster["player_name"], "team": roster["team"], "opponent": expected[1], "position": roster["fantasy_position"], "fantasy_points": 0.0 if stat is None else stat["fantasy_points"]})
    rows.sort(key=lambda row: (row["season"], row["week"], row["game_id"], row["gsis_id"]))
    return {"rows": rows, "coverage": coverage,
            "blocking_discrepancies": _summarize_findings(blocking, FANTASY_BLOCKING_CLASSES),
            "diagnostics": _summarize_findings(diagnostics, FANTASY_DIAGNOSTIC_CLASSES, FANTASY_POINT_DIAGNOSTICS)}


def _build_player_games_from_sources(source_rows, source_receipts):
    result = _reconcile_fantasy_population(source_rows)
    blocking = result["blocking_discrepancies"]
    if blocking["total"]:
        reasons = ", ".join(reason for reason, count in blocking["counts"].items() if count)
        raise ValueError(f"Fantasy source qualification has blocking discrepancies: {reasons}")
    if not result["rows"]: raise ValueError("Fantasy population contains zero eligible player-games")
    return result["rows"], {"schema_version": 2, "scope": dict(FANTASY_SCOPE),
        "position_authority": FANTASY_POSITION_AUTHORITY, "position_mapping": dict(FANTASY_POSITION_MAPPING),
        "sources": source_receipts, "coverage": result["coverage"], "blocking_discrepancies": blocking,
        "diagnostics": result["diagnostics"], "checks": {name: True for name in AUDIT_CHECKS}}


def qualify_fantasy_sources(paths, source_lock_text):
    lock = _load_fantasy_source_lock(source_lock_text)
    source_rows, source_receipts = _load_source_rows(paths)
    locked = {(entry["name"], entry["season"]): entry for entry in lock["sources"]}
    for source in source_receipts:
        entry = locked[(source["name"], source["season"])]
        if source["bytes"] != entry["bytes"] or source["sha256"] != entry["sha256"]:
            raise ValueError("Fantasy source bytes do not match the lock")
    result = _reconcile_fantasy_population(source_rows)
    blocking = result["blocking_discrepancies"]
    counts = blocking["counts"]
    checks = {
        "source_contract": True,
        "locked_bytes": True,
        "schedule_identity": counts["schedule_identity"] == 0,
        "team_coverage": all(
            counts[name] == 0
            for name in ("incomplete_team_coverage", "incomplete_team_week_coverage")
        ),
        "roster_identity": all(
            counts[name] == 0
            for name in (
                "missing_roster_identity", "missing_roster_status",
                "duplicate_roster_identity", "conflicting_team",
            )
        ),
        "stat_identity": all(
            counts[name] == 0 for name in (
                "missing_stat_identity", "duplicate_stat_identity", "missing_roster", "non_act_roster")
        ),
        "stat_team_week_coverage": counts["incomplete_stat_team_week_coverage"] == 0,
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


def _validate_finding_summary(summary, classes, row_fields, point_classes=()):
    required = {"total", "counts", "by_season", "rows"}
    if point_classes: required.add("fantasy_point_totals")
    if not isinstance(summary, dict) or set(summary) != required:
        raise ValueError("Fantasy source qualification is not PASS")
    rows, counts = summary["rows"], summary["counts"]
    if (type(summary["total"]) is not int or not isinstance(rows, list) or
        summary["total"] != len(rows) or
        any(not isinstance(row, dict) or set(row) != row_fields for row in rows) or
        not isinstance(counts, dict) or set(counts) != set(classes) or
        any(type(value) is not int or value < 0 for value in counts.values())):
        raise ValueError("Fantasy source qualification is not PASS")
    strings = set(row_fields) - {"season", "week", "source_row_number", "fantasy_points"}
    for row in rows:
        if (row["reason"] not in classes or type(row["season"]) is not int or
            row["season"] not in MODEL_SEASONS or type(row["week"]) is not int or row["week"] < 0 or
            type(row["source_row_number"]) is not int or row["source_row_number"] < 0 or
            any(not isinstance(row[name], str) for name in strings) or
            ("fantasy_points" in row and (isinstance(row["fantasy_points"], bool) or not isinstance(row["fantasy_points"], (int, float)) or not math.isfinite(row["fantasy_points"])) )):
            raise ValueError("Fantasy source qualification is not PASS")
    expected_counts = {reason: sum(row["reason"] == reason for row in rows) for reason in classes}
    expected_seasons = {str(season): {reason: sum(row["season"] == season and row["reason"] == reason for row in rows) for reason in classes} for season in MODEL_SEASONS}
    if rows != sorted(rows, key=_finding_key) or len({tuple(sorted(row.items())) for row in rows}) != len(rows) or counts != expected_counts or summary["by_season"] != expected_seasons:
        raise ValueError("Fantasy source qualification is not PASS")
    if point_classes:
        expected = {reason: round(math.fsum(row["fantasy_points"] for row in rows if row["reason"] == reason), 10) for reason in point_classes}
        values = summary["fantasy_point_totals"]
        if not isinstance(values, dict) or set(values) != set(point_classes) or values != expected or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values.values()):
            raise ValueError("Fantasy source qualification is not PASS")


def validate_fantasy_source_qualification(source_lock_text, receipt):
    required = {
        "schema_version", "qualification_status", "artifact_availability",
        "source_lock_sha256", "scope", "position_authority", "position_mapping",
        "source_count", "sources", "checks", "coverage", "blocking_discrepancies", "diagnostics",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ValueError("Fantasy source qualification receipt is invalid")
    lock = _load_fantasy_source_lock(source_lock_text)
    expected_hash = hashlib.sha256(source_lock_text.encode("utf-8")).hexdigest()
    if receipt["source_lock_sha256"] != expected_hash:
        raise ValueError("Fantasy source qualification lock hash changed")
    expected_checks = {
        "source_contract", "locked_bytes", "schedule_identity", "team_coverage",
        "roster_identity", "stat_identity", "stat_team_week_coverage",
        "population_reconciliation", "finite_targets",
    }
    coverage = receipt.get("coverage")
    if (
        type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 2
        or receipt["qualification_status"] != "PASS"
        or receipt["artifact_availability"] != "LOCAL_CACHE_ONLY"
        or receipt["scope"] != FANTASY_SCOPE
        or receipt["position_authority"] != FANTASY_POSITION_AUTHORITY
        or receipt["position_mapping"] != FANTASY_POSITION_MAPPING
        or type(receipt["source_count"]) is not int
        or receipt["source_count"] != 13
        or not isinstance(receipt["sources"], list)
        or len(receipt["sources"]) != 13
        or not isinstance(receipt["checks"], dict)
        or set(receipt["checks"]) != expected_checks
        or not all(value is True for value in receipt["checks"].values())
        or not isinstance(coverage, dict)
        or set(coverage) != {str(season) for season in MODEL_SEASONS}
    ):
        raise ValueError("Fantasy source qualification is not PASS")
    _validate_finding_summary(receipt["blocking_discrepancies"], FANTASY_BLOCKING_CLASSES, FANTASY_BLOCKING_ROW_FIELDS)
    _validate_finding_summary(receipt["diagnostics"], FANTASY_DIAGNOSTIC_CLASSES, FANTASY_DIAGNOSTIC_ROW_FIELDS, FANTASY_POINT_DIAGNOSTICS)
    if receipt["blocking_discrepancies"]["total"]:
        raise ValueError("Fantasy source qualification is not PASS")
    locked = {(entry["name"], entry["season"]): entry for entry in lock["sources"]}
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
        values = coverage[str(season)]
        if (
            not isinstance(values, dict)
            or set(values) != {
                "eligible", "matched_stats", "zero_filled", "bye_skipped", "excluded_stats"
            }
            or any(type(value) is not int or value < 0 for value in values.values())
            or values["matched_stats"] + values["zero_filled"] != values["eligible"]
            or values["excluded_stats"] != receipt["diagnostics"]["by_season"][str(season)]["act_unmodeled_roster_stat"]
        ):
            raise ValueError("Fantasy source qualification is not PASS")
    serialize_fantasy_source_json(receipt)


def _unlink_owned(path, expected_state, content=None):
    path = Path(path)
    quarantine = None
    try:
        descriptor, name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".rollback",
        )
        os.close(descriptor)
        quarantine = Path(name)
        os.replace(path, quarantine)
    except BaseException:
        if quarantine is not None:
            try:
                quarantine.unlink()
            except BaseException:
                pass
        return
    try:
        is_owned = os.path.samestat(
            quarantine.stat(follow_symlinks=False), expected_state
        )
        if content is not None:
            is_owned = is_owned and quarantine.read_bytes() == content
    except BaseException:
        return
    if not is_owned:
        try:
            os.link(quarantine, path)
        except BaseException:
            return
    try:
        quarantine.unlink()
    except BaseException:
        pass


def _exclusive_write_text(path, text):
    path = Path(path)
    content = text.encode("utf-8")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    state = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        _unlink_owned(path, state)
        raise
    return state, content


def _refuse_existing_candidate_outputs():
    for path in (FANTASY_CANDIDATE_LOCK, FANTASY_QUALIFICATION_OUTPUT):
        if path.exists():
            raise ValueError(f"Refusing to replace existing candidate output: {path}")
    if FANTASY_ACCEPTED_DIR.exists():
        raise ValueError("Accepted fantasy source evidence already exists")


def _freeze_and_qualify(frozen_at):
    _parse_frozen_at(frozen_at)
    _refuse_existing_candidate_outputs()
    FANTASY_CANDIDATE_LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        claim = _exclusive_write_text(
            FANTASY_CANDIDATE_CLAIM, os.urandom(16).hex()
        )
    except FileExistsError as error:
        raise ValueError("Fantasy source candidate freeze already in progress") from error
    staged = None
    candidate = None
    qualification = None
    try:
        _refuse_existing_candidate_outputs()
        descriptor, name = tempfile.mkstemp(
            dir=FANTASY_CANDIDATE_LOCK.parent,
            prefix=".pgo-fantasy-source-v2-",
            suffix=".pending",
        )
        os.close(descriptor)
        staged = Path(name)
        staged.unlink()
        manifest = pgo_sources.freeze_sources(
            fantasy_source_specs(), FANTASY_CACHE_DIR, staged, frozen_at
        )
        lock = build_fantasy_source_lock(manifest)
        lock_text = serialize_fantasy_source_json(lock)
        staged.write_text(lock_text, encoding="utf-8", newline="")
        paths = pgo_sources.load_locked_sources(staged, FANTASY_CACHE_DIR)
        receipt = qualify_fantasy_sources(paths, lock_text)
        candidate = _exclusive_write_text(FANTASY_CANDIDATE_LOCK, lock_text)
        qualification = _exclusive_write_text(
            FANTASY_QUALIFICATION_OUTPUT,
            serialize_fantasy_source_json(receipt),
        )
        return receipt
    except BaseException:
        if candidate is not None:
            _unlink_owned(FANTASY_CANDIDATE_LOCK, *candidate)
        if qualification is not None:
            _unlink_owned(FANTASY_QUALIFICATION_OUTPUT, *qualification)
        raise
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
        _unlink_owned(FANTASY_CANDIDATE_CLAIM, *claim)


def _accept_qualified_sources():
    lock_text = FANTASY_CANDIDATE_LOCK.read_bytes().decode("utf-8")
    receipt_text = FANTASY_QUALIFICATION_OUTPUT.read_bytes().decode("utf-8")
    lock = _load_fantasy_source_lock(lock_text)
    receipt = json.loads(receipt_text)
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


def parse_qualification_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--freeze-sources", action="store_true")
    action.add_argument("--accept-qualified", action="store_true")
    parser.add_argument("--frozen-at")
    return parser.parse_args(argv)


def _operational_blocked_receipt(error):
    return {
        "schema_version": 2,
        "qualification_status": "BLOCKED",
        "artifact_availability": "LOCAL_CACHE_ONLY",
        "error": f"{type(error).__name__}: {error}",
    }


def main(argv: list[str] | None = None) -> int:
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
            and not FANTASY_CANDIDATE_CLAIM.exists()
        ):
            try:
                FANTASY_QUALIFICATION_OUTPUT.parent.mkdir(
                    parents=True, exist_ok=True
                )
                _exclusive_write_text(
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


def strong_baseline(history, position_mean) -> float:
    position_mean = float(position_mean)
    values = [float(value) for value in history[-8:]]
    if not math.isfinite(position_mean) or not all(
        math.isfinite(value) for value in values
    ):
        raise ValueError("Strong-baseline inputs must be finite")
    recent = list(reversed(values))
    if not recent:
        return position_mean
    weights = [2 ** (-index / 4) for index in range(len(recent))]
    prediction = (
        sum(value * weight for value, weight in zip(recent, weights))
        + 4 * position_mean
    ) / (sum(weights) + 4)
    if not math.isfinite(prediction):
        raise ValueError("Strong-baseline prediction must be finite")
    return prediction


def _row_key(row):
    return row["season"], row["week"], row["game_id"], row["gsis_id"]


def _natural_key(row):
    return row["game_id"], row["gsis_id"]


def select_primary_pool(rows) -> set[tuple[str, str]]:
    ordered = []
    seen = set()
    for row in rows:
        key = _natural_key(row)
        if key in seen:
            raise ValueError(f"Duplicate primary-pool row: {key}")
        seen.add(key)
        try:
            prediction = float(row["strong_prediction"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid strong prediction for {key}") from error
        if not math.isfinite(prediction):
            raise ValueError(f"Strong prediction must be finite for {key}")
        position = row.get("position")
        if position not in {"QB", "RB", "WR", "TE"}:
            raise ValueError(f"Invalid fantasy position for {key}: {position!r}")
        ordered.append((row, prediction))

    selected = set()
    for position, limit in (("QB", 24), ("RB", 24), ("WR", 24), ("TE", 12)):
        candidates = sorted(
            (
                (row, prediction)
                for row, prediction in ordered
                if row["position"] == position
            ),
            key=lambda item: (-item[1], item[0]["gsis_id"]),
        )
        if len(candidates) < limit:
            raise ValueError(f"Insufficient primary-pool {position} rows")
        selected.update(_natural_key(row) for row, _ in candidates[:limit])

    flex = sorted(
        (
            (row, prediction)
            for row, prediction in ordered
            if row["position"] in {"RB", "WR", "TE"}
            and _natural_key(row) not in selected
        ),
        key=lambda item: (-item[1], item[0]["gsis_id"]),
    )
    if len(flex) < 12:
        raise ValueError("Insufficient primary-pool FLEX rows")
    selected.update(_natural_key(row) for row, _ in flex[:12])
    return selected


def _validated_baseline_rows(rows):
    validated = []
    seen = set()
    player_weeks = set()
    for source in rows:
        try:
            season = source["season"]
            week = source["week"]
            game_id = source["game_id"].strip()
            gsis_id = source["gsis_id"].strip()
            position = source["position"]
            target = float(source["fantasy_points"])
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid baseline player-game row") from error
        if (
            isinstance(season, bool)
            or not isinstance(season, int)
            or season not in MODEL_SEASONS
            or isinstance(week, bool)
            or not isinstance(week, int)
            or week < 1
            or not game_id
            or not gsis_id
            or position not in {"QB", "RB", "WR", "TE"}
            or not math.isfinite(target)
        ):
            raise ValueError("Invalid baseline player-game row")
        key = (game_id, gsis_id)
        if key in seen:
            raise ValueError(f"Duplicate baseline player-game row: {key}")
        seen.add(key)
        player_week = (season, week, gsis_id)
        if player_week in player_weeks:
            raise ValueError(f"Duplicate baseline player-week: {player_week}")
        player_weeks.add(player_week)
        validated.append({**source, "fantasy_points": target})
    if {row["season"] for row in validated} != set(MODEL_SEASONS):
        raise ValueError("Baseline rows must cover every model season")
    return sorted(validated, key=_row_key)


def _predict_fold(rows, test_season):
    training = [row for row in rows if row["season"] < test_season]
    position_sums = {position: 0.0 for position in ("QB", "RB", "WR", "TE")}
    position_counts = {position: 0 for position in position_sums}
    histories = {}
    for row in training:
        position = row["position"]
        target = row["fantasy_points"]
        position_sums[position] += target
        position_counts[position] += 1
        histories.setdefault(row["gsis_id"], []).append(target)
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
    if not test_weeks:
        raise ValueError(f"Test season contains zero rows: {test_season}")

    predictions = []
    for week in sorted(test_weeks):
        week_predictions = []
        for row in sorted(test_weeks[week], key=_row_key):
            position = row["position"]
            live_mean = position_sums[position] / position_counts[position]
            week_predictions.append({
                **row,
                "null_prediction": null_means[position],
                "strong_prediction": strong_baseline(
                    histories.get(row["gsis_id"], []), live_mean
                ),
            })
        primary = select_primary_pool(week_predictions)
        for prediction in week_predictions:
            prediction["primary_pool"] = _natural_key(prediction) in primary
        predictions.extend(week_predictions)

        # Every outcome in the week is hidden until all predictions are complete.
        for row in sorted(test_weeks[week], key=_row_key):
            target = row["fantasy_points"]
            histories.setdefault(row["gsis_id"], []).append(target)
            position_sums[row["position"]] += target
            position_counts[row["position"]] += 1
    return predictions


def _metric_block(rows):
    if not rows:
        raise ValueError("Metric slice contains zero rows")
    null_mae = sum(
        abs(row["fantasy_points"] - row["null_prediction"]) for row in rows
    ) / len(rows)
    strong_mae = sum(
        abs(row["fantasy_points"] - row["strong_prediction"]) for row in rows
    ) / len(rows)
    values = (null_mae, strong_mae, null_mae - strong_mae)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Baseline metrics must be finite")
    return {
        "count": len(rows),
        "null_mae": null_mae,
        "strong_mae": strong_mae,
        "strong_vs_null_mae_improvement": null_mae - strong_mae,
    }


def _evaluation_metrics(rows):
    primary = [row for row in rows if row["primary_pool"]]
    return {
        "all_eligible": _metric_block(rows),
        "primary": _metric_block(primary),
        "primary_by_position": {
            position: _metric_block(
                [row for row in primary if row["position"] == position]
            )
            for position in ("QB", "RB", "WR", "TE")
        },
    }


def _canonical_json_bytes(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("Value is not finite canonical JSON") from error


def _validate_source_audit(source_audit):
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

    expected_sources = {
        (spec.name, spec.season) for spec in fantasy_source_specs()
    }
    sources = source_audit.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Source audit sources are invalid")
    received_sources = set()
    for receipt in sources:
        if not isinstance(receipt, dict) or set(receipt) != {
            "name",
            "season",
            "bytes",
            "sha256",
            "rows",
        }:
            raise ValueError("Source audit receipt is invalid")
        key = (receipt["name"], receipt["season"])
        digest = receipt["sha256"]
        if (
            key in received_sources
            or key not in expected_sources
            or type(receipt["bytes"]) is not int
            or receipt["bytes"] <= 0
            or type(receipt["rows"]) is not int
            or receipt["rows"] <= 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("Source audit receipt is invalid")
        received_sources.add(key)
    if received_sources != expected_sources:
        raise ValueError("Source audit inventory is incomplete")

    coverage = source_audit.get("coverage")
    if not isinstance(coverage, dict) or set(coverage) != {
        str(season) for season in MODEL_SEASONS
    }:
        raise ValueError("Source audit coverage is invalid")
    fields = {
        "eligible", "matched_stats", "zero_filled", "bye_skipped",
        "excluded_stats",
    }
    for season in MODEL_SEASONS:
        values = coverage[str(season)]
        if (
            not isinstance(values, dict)
            or set(values) != fields
            or any(type(values[field]) is not int or values[field] < 0 for field in fields)
            or values["matched_stats"] + values["zero_filled"]
            != values["eligible"]
            or values["excluded_stats"] != source_audit["diagnostics"]
            ["by_season"][str(season)]["act_unmodeled_roster_stat"]
        ):
            raise ValueError("Source audit coverage is invalid")


def _validate_audit_population(source_audit, rows):
    for season in MODEL_SEASONS:
        count = sum(row["season"] == season for row in rows)
        if source_audit["coverage"][str(season)]["eligible"] != count:
            raise ValueError("Source audit population does not match baseline rows")


def backtest_baselines(rows, source_audit) -> tuple[dict, list[dict]]:
    _validate_source_audit(source_audit)
    audit_sha256 = hashlib.sha256(_canonical_json_bytes(source_audit)).hexdigest()
    validated = _validated_baseline_rows(rows)
    _validate_audit_population(source_audit, validated)
    predictions = []
    folds = []
    for test_season in TEST_SEASONS:
        fold_predictions = _predict_fold(validated, test_season)
        predictions.extend(fold_predictions)
        folds.append({
            "test_season": test_season,
            "train_seasons": list(range(MODEL_SEASONS[0], test_season)),
            **_evaluation_metrics(fold_predictions),
        })
    predictions.sort(key=_row_key)
    return ({
        "schema_version": 1,
        "model": "pgo_fantasy_baselines_v1",
        "stage": "BASELINE_ONLY",
        "status": "HOLD",
        "publication_status": "EXPERIMENTAL",
        "status_reason": "No candidate is evaluated in the baseline-only slice",
        "scoring": "HALF_PPR",
        "population": "WEEKLY_ROSTER_ACT_QB_RB_FB_WR_TE",
        "source_audit_sha256": audit_sha256,
        "folds": folds,
        "pooled": _evaluation_metrics(predictions),
    }, predictions)


def serialize_baseline_report(report) -> str:
    try:
        return json.dumps(
            report,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise ValueError("Baseline report must contain finite JSON values") from error


def serialize_baseline_predictions(rows) -> str:
    try:
        ordered = sorted(list(rows), key=_row_key)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Invalid baseline prediction row") from error
    if not ordered:
        raise ValueError("Baseline predictions contain zero rows")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=PREDICTION_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    seen = set()
    for source in ordered:
        try:
            season = source["season"]
            week = source["week"]
            game_id = source["game_id"]
            gsis_id = source["gsis_id"]
            position = source["position"]
            primary = source["primary_pool"]
            numbers = {
                name: float(source[name])
                for name in (
                    "fantasy_points",
                    "null_prediction",
                    "strong_prediction",
                )
            }
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid baseline prediction row") from error
        key = (game_id, gsis_id)
        if (
            isinstance(season, bool)
            or not isinstance(season, int)
            or isinstance(week, bool)
            or not isinstance(week, int)
            or not isinstance(game_id, str)
            or not game_id
            or not isinstance(gsis_id, str)
            or not gsis_id
            or position not in {"QB", "RB", "WR", "TE"}
            or not isinstance(primary, bool)
            or not all(math.isfinite(value) for value in numbers.values())
        ):
            raise ValueError(f"Prediction values must be finite and valid for {key}")
        if key in seen:
            raise ValueError(f"Duplicate baseline prediction row: {key}")
        seen.add(key)
        writer.writerow({
            "season": season,
            "week": week,
            "game_id": game_id,
            "gsis_id": gsis_id,
            "player_name": source.get("player_name", ""),
            "team": source.get("team", ""),
            "opponent": source.get("opponent", ""),
            "position": position,
            **numbers,
            "primary_pool": str(primary).lower(),
        })
    return output.getvalue()
