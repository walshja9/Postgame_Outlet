"""Prospective 2026 half-PPR fantasy previews, locks, and grades."""

import csv
import hashlib
import io
import json
import math
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import pgo_challenger
import pgo_fantasy
import pgo_prospective
from pgo_sources import atomic_write_text, normalize_team


SCHEMA_VERSION = 1
SOURCE_KINDS = ("schedule", "roster", "availability", "history")
ENVELOPE_KEYS = frozenset({
    "schema_version", "source", "source_as_of", "captured_at",
    "teams_processed", "rows",
})
SCHEDULE_FIELDS = frozenset({
    "season", "week", "game_id", "game_type", "kickoff",
    "away_team", "home_team",
})
ROSTER_FIELDS = frozenset({
    "gsis_id", "player_name", "team", "position", "status",
})
AVAILABILITY_FIELDS = frozenset({"gsis_id", "team", "status"})
HISTORY_FIELDS = frozenset({
    "season", "week", "game_id", "game_type", "finalized_at",
    "gsis_id", "team", "position",
}) | pgo_fantasy.SCORING_FIELDS
ROW_FIELDS = {
    "schedule": SCHEDULE_FIELDS,
    "roster": ROSTER_FIELDS,
    "availability": AVAILABILITY_FIELDS,
    "history": HISTORY_FIELDS,
}
CONFIG_KEYS = frozenset({
    "schema_version", "model_version", "frozen_at", "trained_through", "scoring",
    "history_games", "half_life_games", "pseudo_games", "position_means",
    "position_mean_evidence_sha256",
})
POSITIONS = ("QB", "RB", "WR", "TE")
LOCK_KIND = "PGO_FANTASY_T60_GAME_LOCK"
PREVIEW_KIND = "PGO_FANTASY_WEEKLY_PREVIEW"
LOCK_KEYS = frozenset({
    "schema_version", "artifact_kind", "status", "publication_status",
    "season", "week", "game_id", "kickoff", "away", "home",
    "decision_time", "locked_at", "teams_processed", "row_count", "coverage",
    "model_version", "config_sha256", "code_sha", "scheduled_week_games",
    "source_receipts", "source_receipts_sha256", "predictions",
    "prediction_integrity_sha256", "artifact_sha256",
})
LOCK_PREDICTION_COLUMNS = (
    "season", "week", "game_id", "gsis_id", "player_name", "team",
    "opponent", "position", "null_prediction", "strong_prediction",
    "history_count", "initialization_reason", "availability_status",
    "ranking_eligible", "config_sha256",
)
SOURCE_RECEIPT_KEYS = frozenset({
    "schema_version", "kind", "source", "source_as_of", "captured_at",
    "teams_processed", "bytes", "sha256", "rows",
})


def canonical_json(value):
    return pgo_prospective._canonical(value)


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError(f"Nonfinite JSON constant: {value}")


def _reject_nonfinite_numbers(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite JSON number")
    if isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite_numbers(item)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite_numbers(item)


def _matches_frozen_value(value, frozen):
    if type(value) is not type(frozen):
        return False
    if isinstance(value, dict):
        return (
            len(value) == len(frozen)
            and all(
                key in frozen and _matches_frozen_value(item, frozen[key])
                for key, item in value.items()
            )
        )
    if isinstance(value, list):
        return len(value) == len(frozen) and all(
            _matches_frozen_value(item, expected)
            for item, expected in zip(value, frozen)
        )
    return value == frozen


def _decode_json(data, label):
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
        _reject_nonfinite_numbers(value)
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError(f"{label} is invalid JSON") from error


def parse_timestamp(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a timezone-bearing timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be a timezone-bearing timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-bearing timestamp")
    return parsed


def _required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _hex_digest(value, length):
    return (
        isinstance(value, str) and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _validated_teams(values, label):
    if not isinstance(values, list):
        raise ValueError(f"{label} teams_processed is invalid")
    try:
        teams = [normalize_team(value) for value in values]
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"{label} teams_processed is invalid") from error
    if len(teams) != len(set(teams)):
        raise ValueError(f"{label} teams_processed contains duplicates")
    return sorted(teams)


def _row_integer(row, field, kind):
    if type(row[field]) is not int:
        raise ValueError(f"{kind} snapshot {field} is invalid")


def _row_text(row, field, kind):
    row[field] = _required_text(
        row[field], f"{kind} snapshot {field}"
    )


def _row_team(row, field, teams, kind):
    try:
        team = normalize_team(row[field])
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"{kind} snapshot {field} is invalid") from error
    if team not in teams:
        raise ValueError(f"{kind} snapshot {field} is outside teams_processed")
    row[field] = team


def _validate_row(row, kind, teams):
    if kind in {"schedule", "history"}:
        for field in ("season", "week"):
            _row_integer(row, field, kind)
        for field in ("game_id", "game_type"):
            _row_text(row, field, kind)
    if kind == "schedule":
        parse_timestamp(row["kickoff"], f"{kind} snapshot kickoff")
        for field in ("away_team", "home_team"):
            _row_team(row, field, teams, kind)
    elif kind == "roster":
        for field in ("gsis_id", "player_name", "position", "status"):
            _row_text(row, field, kind)
        _row_team(row, "team", teams, kind)
    elif kind == "availability":
        for field in ("gsis_id", "status"):
            _row_text(row, field, kind)
        _row_team(row, "team", teams, kind)
    else:
        parse_timestamp(row["finalized_at"], f"{kind} snapshot finalized_at")
        for field in ("gsis_id", "position"):
            _row_text(row, field, kind)
        _row_team(row, "team", teams, kind)
        for field in pgo_fantasy.SCORING_FIELDS:
            if (
                type(row[field]) not in (int, float)
                or not math.isfinite(row[field])
            ):
                raise ValueError(f"{kind} snapshot {field} is invalid")
        pgo_fantasy.half_ppr(row)


def _snapshot_from_bytes(data, kind):
    if kind not in SOURCE_KINDS:
        raise ValueError(f"Unknown prospective source kind: {kind}")
    value = _decode_json(data, f"{kind} snapshot")
    if not isinstance(value, dict) or set(value) != ENVELOPE_KEYS:
        raise ValueError(f"{kind} snapshot envelope is invalid")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError(f"{kind} snapshot schema is invalid")
    if not isinstance(value["source"], str) or not value["source"].strip():
        raise ValueError(f"{kind} snapshot source is invalid")
    captured = parse_timestamp(value["captured_at"], f"{kind} captured_at")
    if value["source_as_of"] is not None:
        source_as_of = parse_timestamp(
            value["source_as_of"], f"{kind} source_as_of"
        )
        if source_as_of > captured:
            raise ValueError(f"{kind} source_as_of is after capture")
    teams = _validated_teams(value["teams_processed"], kind)
    rows = value["rows"]
    if not isinstance(rows, list):
        raise ValueError(f"{kind} snapshot rows are invalid")
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS[kind]:
            raise ValueError(f"{kind} snapshot row is invalid")
        _validate_row(row, kind, teams)
    snapshot = deepcopy(value)
    snapshot["source"] = value["source"].strip()
    snapshot["teams_processed"] = teams
    loaded = {
        "snapshot": snapshot,
        "receipt": {
            "schema_version": 1,
            "kind": kind,
            "source": snapshot["source"],
            "source_as_of": snapshot["source_as_of"],
            "captured_at": snapshot["captured_at"],
            "teams_processed": teams,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "rows": len(rows),
        },
        "bytes": data,
    }
    return loaded


def load_snapshot(path, kind):
    return _snapshot_from_bytes(Path(path).read_bytes(), kind)


def verify_loaded_snapshot(loaded, kind):
    if not isinstance(loaded, dict) or set(loaded) != {
        "snapshot", "receipt", "bytes",
    } or not isinstance(loaded["bytes"], bytes):
        raise ValueError(f"{kind} loaded source is invalid")
    rebuilt = _snapshot_from_bytes(loaded["bytes"], kind)
    if not _matches_frozen_value(loaded, rebuilt):
        raise ValueError(f"{kind} parsed view does not match frozen bytes")
    return loaded


def serialize_model_config(config):
    return canonical_json(config) + "\n"


def _validate_model_config(config):
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS:
        raise ValueError("Prospective model config is invalid")
    if (
        type(config["schema_version"]) is not int
        or config["schema_version"] != 1
        or config["model_version"] != "pgo_fantasy_2026_baseline_v1"
        or type(config["trained_through"]) is not int
        or config["trained_through"] != 2025
        or config["scoring"] != "PGO_HALF_PPR_V1"
        or type(config["history_games"]) is not int
        or config["history_games"] != 8
        or type(config["half_life_games"]) is not int
        or config["half_life_games"] != 4
        or type(config["pseudo_games"]) is not int
        or config["pseudo_games"] != 4
        or not _hex_digest(config["position_mean_evidence_sha256"], 64)
        or not isinstance(config["position_means"], dict)
        or set(config["position_means"]) != set(POSITIONS)
    ):
        raise ValueError("Prospective model config is invalid")
    parse_timestamp(config["frozen_at"], "model config frozen_at")
    means = {}
    for position in POSITIONS:
        try:
            value = float(config["position_means"][position])
        except (TypeError, ValueError) as error:
            raise ValueError("Prospective model config position mean is invalid") from error
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError("Prospective model config position mean is invalid")
        means[position] = value
    normalized = deepcopy(config)
    normalized["model_version"] = config["model_version"].strip()
    normalized["position_means"] = means
    return normalized


def load_model_config(path):
    path = Path(path)
    data = path.read_bytes()
    config = _validate_model_config(_decode_json(data, "prospective model config"))
    if data != serialize_model_config(config).encode("utf-8"):
        raise ValueError("Prospective model config is not canonical")
    return {
        "config": config,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": data,
    }


def verify_model_config(model):
    if not isinstance(model, dict) or set(model) != {
        "config", "sha256", "bytes",
    } or not isinstance(model["bytes"], bytes):
        raise ValueError("Prospective model config is invalid")
    config = _validate_model_config(
        _decode_json(model["bytes"], "prospective model config")
    )
    if (
        model["bytes"] != serialize_model_config(config).encode("utf-8")
        or not _matches_frozen_value(model["config"], config)
        or model["sha256"] != hashlib.sha256(model["bytes"]).hexdigest()
    ):
        raise ValueError("Prospective model config does not match frozen bytes")
    return model


def _artifact_hash(value):
    payload = deepcopy(value)
    payload.pop("artifact_sha256", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _game_rows(schedule, week=None):
    games = []
    seen = set()
    for row in schedule["snapshot"]["rows"]:
        if (
            type(row["season"]) is not int or row["season"] != 2026
            or type(row["week"]) is not int or not 1 <= row["week"] <= 18
            or row["game_type"] != "REG"
            or not isinstance(row["game_id"], str) or not row["game_id"].strip()
        ):
            raise ValueError("Prospective schedule row is invalid")
        game_id = row["game_id"].strip()
        if game_id in seen:
            raise ValueError(f"Duplicate prospective game: {game_id}")
        seen.add(game_id)
        away = normalize_team(_required_text(row["away_team"], "away team"))
        home = normalize_team(_required_text(row["home_team"], "home team"))
        if away == home:
            raise ValueError("Prospective schedule teams match")
        kickoff = parse_timestamp(row["kickoff"], "scheduled kickoff")
        parsed = {
            "season": 2026, "week": row["week"], "game_id": game_id,
            "kickoff": row["kickoff"], "kickoff_time": kickoff,
            "away": away, "home": home,
        }
        if week is None or row["week"] == week:
            games.append(parsed)
    return sorted(games, key=lambda game: (game["kickoff_time"], game["game_id"]))


def _ensure_captured(source, cutoff, label):
    captured = parse_timestamp(source["receipt"]["captured_at"], f"{label} capture")
    if captured > cutoff:
        raise ValueError(f"{label} source was captured after prediction time")


def _validate_inputs(sources, model, cutoff=None):
    required = {"schedule", "roster", "history"}
    if set(sources) - {"schedule", "roster", "availability", "history"}:
        raise ValueError("Unexpected prospective source")
    if not required <= set(sources):
        raise ValueError("Missing prospective source")
    verify_model_config(model)
    for kind, source in sources.items():
        verify_loaded_snapshot(source, kind)
    if cutoff is None:
        return
    if parse_timestamp(
        model["config"]["frozen_at"], "model config frozen_at"
    ) > cutoff:
        raise ValueError("Prospective model config was frozen after prediction time")
    for kind, source in sources.items():
        _ensure_captured(source, cutoff, kind)


def _roster_rows(roster, teams):
    if not set(teams) <= set(roster["receipt"]["teams_processed"]):
        raise ValueError("Prospective roster coverage is incomplete")
    parsed, seen = [], set()
    for row in roster["snapshot"]["rows"]:
        team = normalize_team(_required_text(row["team"], "roster team"))
        if team not in teams:
            continue
        gsis_id = _required_text(row["gsis_id"], "roster gsis_id")
        name = _required_text(row["player_name"], "roster player_name")
        raw_position = _required_text(
            row["position"], "roster position"
        ).upper()
        if (
            not gsis_id or not name or row["status"] != "ACT"
            or raw_position not in pgo_fantasy.POSITION_MAP
        ):
            raise ValueError("Prospective roster row is invalid")
        if gsis_id in seen:
            raise ValueError(f"Duplicate prospective roster identity: {gsis_id}")
        seen.add(gsis_id)
        parsed.append({
            "gsis_id": gsis_id, "player_name": name, "team": team,
            "position": pgo_fantasy.POSITION_MAP[raw_position],
        })
    if not parsed:
        raise ValueError("Prospective roster contains no modeled players")
    return sorted(parsed, key=lambda row: row["gsis_id"])


def _availability_state(source, teams, lock_mode):
    verified = (
        source is not None
        and set(teams) <= set(source["receipt"]["teams_processed"])
    )
    if lock_mode and not verified:
        raise ValueError("Prospective availability coverage is incomplete")
    if not verified:
        return None
    inactive = set()
    for row in source["snapshot"]["rows"]:
        team = normalize_team(_required_text(row["team"], "availability team"))
        gsis_id = _required_text(row["gsis_id"], "availability gsis_id")
        if not gsis_id or row["status"] != "INACTIVE":
            raise ValueError("Prospective availability row is invalid")
        if team not in teams:
            continue
        if gsis_id in inactive:
            raise ValueError(f"Duplicate inactive identity: {gsis_id}")
        inactive.add(gsis_id)
    return inactive


def _history(history_source, cutoff, current_game):
    by_player, seen = {}, set()
    captured = parse_timestamp(
        history_source["receipt"]["captured_at"], "history capture"
    )
    for row in history_source["snapshot"]["rows"]:
        finalized = parse_timestamp(row["finalized_at"], "history finalized_at")
        gsis_id = _required_text(row["gsis_id"], "history gsis_id")
        game_id = _required_text(row["game_id"], "history game_id")
        normalize_team(_required_text(row["team"], "history team"))
        _required_text(row["position"], "history position")
        key = game_id, gsis_id
        if type(row["season"]) is not int:
            raise ValueError("Prospective history season is invalid")
        if row["season"] < 2025:
            continue
        if (
            row["season"] not in {2025, 2026}
            or type(row["week"]) is not int or not 1 <= row["week"] <= 18
            or row["game_type"] != "REG" or not game_id or not gsis_id
            or finalized > captured or finalized > cutoff
            or game_id == current_game
        ):
            raise ValueError("Prospective history row is invalid")
        if key in seen:
            raise ValueError(f"Duplicate prospective history row: {key}")
        seen.add(key)
        value = pgo_fantasy.half_ppr(row)
        by_player.setdefault(gsis_id, []).append((finalized, game_id, value))
    return {
        player: [item[2] for item in sorted(items)[-8:]]
        for player, items in by_player.items()
    }


def project_game(sources, model, game_id, generated_at, lock_mode):
    generated = parse_timestamp(generated_at, "prediction generated_at")
    _validate_inputs(sources, model)
    games = _game_rows(sources["schedule"])
    matches = [game for game in games if game["game_id"] == game_id]
    if len(matches) != 1:
        raise ValueError("Prospective game identity is invalid")
    game = matches[0]
    decision = game["kickoff_time"] - timedelta(minutes=60)
    if lock_mode and generated > decision:
        raise ValueError("T-60 decision time has passed")
    _validate_inputs(sources, model, min(generated, decision))
    teams = {game["away"], game["home"]}
    roster = _roster_rows(sources["roster"], teams)
    inactive = _availability_state(
        sources.get("availability"), teams, lock_mode
    )
    history = _history(sources["history"], generated, game_id)
    means = model["config"]["position_means"]
    rows = []
    for player in roster:
        values = history.get(player["gsis_id"], [])
        unavailable = inactive is not None and player["gsis_id"] in inactive
        status = (
            "INACTIVE" if unavailable
            else "ACTIVE" if inactive is not None
            else "UNVERIFIED"
        )
        mean = means[player["position"]]
        rows.append({
            "season": 2026, "week": game["week"], "game_id": game_id,
            "gsis_id": player["gsis_id"],
            "player_name": player["player_name"], "team": player["team"],
            "opponent": game["home"] if player["team"] == game["away"] else game["away"],
            "position": player["position"],
            "null_prediction": 0.0 if unavailable else mean,
            "strong_prediction": 0.0 if unavailable else pgo_fantasy.strong_baseline(values, mean),
            "history_count": len(values),
            "initialization_reason": "HISTORY" if values else "TRUE_COLD_START",
            "availability_status": status,
            "ranking_eligible": not unavailable,
            "config_sha256": model["sha256"],
        })
    week_games = [item["game_id"] for item in games if item["week"] == game["week"]]
    return {
        "game": {key: game[key] for key in (
            "season", "week", "game_id", "kickoff", "away", "home"
        )},
        "decision_time": decision.isoformat(),
        "generated_at": generated_at,
        "scheduled_week_games": sorted(week_games),
        "rows": sorted(rows, key=lambda row: row["gsis_id"]),
    }


def rank_rows(rows):
    ranked = [deepcopy(row) for row in rows]
    seen = set()
    for row in ranked:
        key = row["game_id"], row["gsis_id"]
        if key in seen:
            raise ValueError(f"Duplicate ranking row: {key}")
        seen.add(key)
        row.update({"position_rank": None, "flex_rank": None, "superflex_rank": None})

    def assign(field, allowed):
        selected = sorted(
            (
                row for row in ranked
                if row["ranking_eligible"] and row["position"] in allowed
            ),
            key=lambda row: (-row["strong_prediction"], row["gsis_id"]),
        )
        for index, row in enumerate(selected, 1):
            row[field] = index

    for position in POSITIONS:
        assign("position_rank", {position})
    assign("flex_rank", {"RB", "WR", "TE"})
    assign("superflex_rank", set(POSITIONS))
    return sorted(ranked, key=lambda row: (row["game_id"], row["gsis_id"]))


def build_preview(sources, model, week, generated_at):
    if type(week) is not int or not 1 <= week <= 18:
        raise ValueError("Preview week is invalid")
    generated = parse_timestamp(generated_at, "prediction generated_at")
    _validate_inputs(sources, model, generated)
    games = _game_rows(sources["schedule"], week)
    if games:
        _validate_inputs(
            sources, model,
            min(generated, games[0]["kickoff_time"] - timedelta(minutes=60)),
        )
    scheduled_teams = {
        team for game in games for team in (game["away"], game["home"])
    }
    roster_teams = set(sources["roster"]["receipt"]["teams_processed"])
    rows, missing = [], set()
    for game in games:
        teams = {game["away"], game["home"]}
        if not teams <= roster_teams:
            missing.update(teams - roster_teams)
            continue
        rows.extend(project_game(
            sources, model, game["game_id"], generated_at, lock_mode=False
        )["rows"])
    preview = {
        "schema_version": 1,
        "artifact_kind": PREVIEW_KIND,
        "status": "HOLD",
        "publication_status": "EXPERIMENTAL",
        "evidence_mode": "PREVIEW",
        "gradeable": False,
        "season": 2026,
        "week": week,
        "generated_at": generated_at,
        "model_version": model["config"]["model_version"],
        "config_sha256": model["sha256"],
        "teams_processed": sorted(roster_teams),
        "teams_missing": sorted(missing),
        "source_coverage": {
            kind: {
                "processed": sorted(
                    scheduled_teams & set(source["receipt"]["teams_processed"])
                ),
                "missing": sorted(
                    scheduled_teams - set(source["receipt"]["teams_processed"])
                ),
            }
            for kind, source in (
                ("roster", sources["roster"]),
                ("availability", sources.get("availability", {
                    "receipt": {"teams_processed": []},
                })),
            )
        },
        "rows": rank_rows(rows),
    }
    preview["artifact_sha256"] = _artifact_hash(preview)
    return preview


def serialize_preview(preview):
    if preview.get("artifact_sha256") != _artifact_hash(preview):
        raise ValueError("Preview artifact hash is invalid")
    return canonical_json(preview) + "\n"


def _validate_lock_predictions(rows, lock=None):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Fantasy game lock predictions are invalid")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(LOCK_PREDICTION_COLUMNS):
            raise ValueError("Fantasy game lock prediction row is invalid")
        key = row["game_id"], row["gsis_id"]
        values = row["null_prediction"], row["strong_prediction"]
        if (
            not all(isinstance(value, str) and value.strip() for value in (
                row["game_id"], row["gsis_id"], row["player_name"],
                row["team"], row["opponent"], row["position"],
                row["initialization_reason"], row["availability_status"],
                row["config_sha256"],
            ))
            or key in seen
            or type(row["season"]) is not int or row["season"] != 2026
            or type(row["week"]) is not int or not 1 <= row["week"] <= 18
            or row["position"] not in POSITIONS
            or row["initialization_reason"] not in {"HISTORY", "TRUE_COLD_START"}
            or row["availability_status"] not in {"ACTIVE", "INACTIVE"}
            or type(row["ranking_eligible"]) is not bool
            or type(row["history_count"]) is not int
            or not 0 <= row["history_count"] <= 8
            or not all(
                type(value) in {int, float} and math.isfinite(value)
                for value in values
            )
        ):
            raise ValueError("Fantasy game lock prediction row is invalid")
        seen.add(key)
        if row["availability_status"] == "INACTIVE" and (
            values != (0.0, 0.0) or row["ranking_eligible"]
        ):
            raise ValueError("Inactive fantasy lock row is invalid")
        if row["availability_status"] == "ACTIVE" and not row["ranking_eligible"]:
            raise ValueError("Active fantasy lock row is invalid")
        if lock is not None and (
            row["season"] != lock["season"] or row["week"] != lock["week"]
            or row["game_id"] != lock["game_id"]
            or row["team"] not in lock["teams_processed"]
            or row["opponent"] not in lock["teams_processed"]
            or row["team"] == row["opponent"]
            or row["config_sha256"] != lock["config_sha256"]
        ):
            raise ValueError("Fantasy game lock prediction context is invalid")
    if rows != sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"])):
        raise ValueError("Fantasy game lock predictions are not canonical")
    return rows


def _prediction_hash(rows):
    _validate_lock_predictions(rows)
    values = [
        {key: row[key] for key in LOCK_PREDICTION_COLUMNS}
        for row in sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"]))
    ]
    return hashlib.sha256(canonical_json(values).encode("utf-8")).hexdigest()


def build_game_lock(sources, model, game_id, locked_at, code_sha):
    if not _hex_digest(code_sha, 40):
        raise ValueError("Code SHA is invalid")
    projected = project_game(sources, model, game_id, locked_at, lock_mode=True)
    receipts = [deepcopy(sources[kind]["receipt"]) for kind in SOURCE_KINDS]
    lock = {
        "schema_version": 1,
        "artifact_kind": LOCK_KIND,
        "status": "LOCKED",
        "publication_status": "EXPERIMENTAL",
        **projected["game"],
        "decision_time": projected["decision_time"],
        "locked_at": locked_at,
        "model_version": model["config"]["model_version"],
        "config_sha256": model["sha256"],
        "code_sha": code_sha,
        "teams_processed": sorted((
            projected["game"]["away"], projected["game"]["home"]
        )),
        "row_count": len(projected["rows"]),
        "coverage": {"roster": True, "availability": True},
        "scheduled_week_games": projected["scheduled_week_games"],
        "source_receipts": receipts,
        "source_receipts_sha256": hashlib.sha256(
            canonical_json(receipts).encode("utf-8")
        ).hexdigest(),
        "predictions": projected["rows"],
    }
    lock["prediction_integrity_sha256"] = _prediction_hash(lock["predictions"])
    lock["artifact_sha256"] = _artifact_hash(lock)
    return verify_game_lock(lock)


def verify_game_lock(lock):
    if not isinstance(lock, dict) or set(lock) != LOCK_KEYS:
        raise ValueError("Fantasy game lock contract is invalid")
    if (
        type(lock["schema_version"]) is not int or lock["schema_version"] != 1
        or lock["artifact_kind"] != LOCK_KIND or lock["status"] != "LOCKED"
        or lock["publication_status"] != "EXPERIMENTAL"
        or type(lock["season"]) is not int or lock["season"] != 2026
        or type(lock["week"]) is not int or not 1 <= lock["week"] <= 18
        or not isinstance(lock["game_id"], str) or not lock["game_id"].strip()
        or not isinstance(lock["model_version"], str)
        or not lock["model_version"].strip()
        or not _hex_digest(lock["code_sha"], 40)
        or not _hex_digest(lock["config_sha256"], 64)
        or lock["teams_processed"] != sorted((lock["away"], lock["home"]))
        or len(set(lock["teams_processed"])) != 2
        or type(lock["row_count"]) is not int or lock["row_count"] <= 0
        or lock["row_count"] != len(lock["predictions"])
        or lock["coverage"] != {"roster": True, "availability": True}
        or lock["scheduled_week_games"] != sorted(set(lock["scheduled_week_games"]))
        or lock["game_id"] not in lock["scheduled_week_games"]
        or lock["prediction_integrity_sha256"] != _prediction_hash(lock["predictions"])
        or lock["source_receipts_sha256"] != hashlib.sha256(
            canonical_json(lock["source_receipts"]).encode("utf-8")
        ).hexdigest()
        or lock["artifact_sha256"] != _artifact_hash(lock)
    ):
        raise ValueError("Fantasy game lock integrity is invalid")
    if (
        normalize_team(lock["away"]) != lock["away"]
        or normalize_team(lock["home"]) != lock["home"]
    ):
        raise ValueError("Fantasy game lock teams are invalid")
    _validate_lock_predictions(lock["predictions"], lock)
    receipts = lock["source_receipts"]
    if (
        not isinstance(receipts, list)
        or len(receipts) != len(SOURCE_KINDS)
        or any(not isinstance(receipt, dict) for receipt in receipts)
        or [receipt.get("kind") for receipt in receipts] != list(SOURCE_KINDS)
        or any(
            set(receipt) != SOURCE_RECEIPT_KEYS
            or type(receipt["schema_version"]) is not int
            or receipt["schema_version"] != 1
            or not isinstance(receipt["source"], str)
            or not receipt["source"].strip()
            or type(receipt["bytes"]) is not int or receipt["bytes"] <= 0
            or type(receipt["rows"]) is not int or receipt["rows"] < 0
            or not _hex_digest(receipt["sha256"], 64)
            for receipt in receipts
        )
    ):
        raise ValueError("Fantasy game lock source receipts are invalid")
    coverage = {
        receipt["kind"]: set(lock["teams_processed"])
        <= set(receipt["teams_processed"])
        for receipt in receipts
    }
    if not coverage["roster"] or not coverage["availability"]:
        raise ValueError("Fantasy game lock source coverage is invalid")
    kickoff = parse_timestamp(lock["kickoff"], "kickoff")
    decision = parse_timestamp(lock["decision_time"], "decision_time")
    locked = parse_timestamp(lock["locked_at"], "locked_at")
    if decision != kickoff - timedelta(minutes=60) or locked > decision:
        raise ValueError("Fantasy game lock T-60 integrity is invalid")
    for receipt in receipts:
        captured = parse_timestamp(
            receipt["captured_at"], f"{receipt['kind']} captured_at"
        )
        if captured > locked:
            raise ValueError("Fantasy game lock source timing is invalid")
        if receipt["source_as_of"] is not None and parse_timestamp(
            receipt["source_as_of"], f"{receipt['kind']} source_as_of"
        ) > captured:
            raise ValueError("Fantasy game lock source timing is invalid")
    return lock


def serialize_game_lock(lock):
    verify_game_lock(lock)
    return canonical_json(lock) + "\n"


def game_prediction_csv(lock):
    verify_game_lock(lock)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=LOCK_PREDICTION_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for row in lock["predictions"]:
        writer.writerow({key: row[key] for key in LOCK_PREDICTION_COLUMNS})
    return output.getvalue()


def load_game_lock(path):
    data = Path(path).read_bytes()
    lock = _decode_json(data, "fantasy game lock")
    verify_game_lock(lock)
    if data != serialize_game_lock(lock).encode("utf-8"):
        raise ValueError("Fantasy game lock is not canonical")
    return {
        "lock": lock, "bytes": data,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def write_game_lock(output_dir, lock):
    output_dir = Path(output_dir)
    outputs = (
        (output_dir / "fantasy_lock.json", serialize_game_lock(lock)),
        (output_dir / "fantasy_predictions.csv", game_prediction_csv(lock)),
    )
    return pgo_prospective._write_new_outputs(output_dir, outputs)
