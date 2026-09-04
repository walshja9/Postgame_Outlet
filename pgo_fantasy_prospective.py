"""Prospective 2026 half-PPR fantasy previews, locks, and grades."""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import pgo_challenger
import pgo_fantasy
import pgo_prospective
from pgo_sources import atomic_write_text, normalize_team


SCHEMA_VERSION = 1
SOURCE_KINDS = ("schedule", "roster", "availability", "history", "depth")
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
DEPTH_FIELDS = frozenset({"gsis_id", "team", "position", "depth_rank"})
HISTORY_FIELDS = frozenset({
    "season", "week", "game_id", "game_type", "finalized_at",
    "gsis_id", "team", "position",
}) | pgo_fantasy.SCORING_FIELDS
ROW_FIELDS = {
    "schedule": SCHEDULE_FIELDS,
    "roster": ROSTER_FIELDS,
    "availability": AVAILABILITY_FIELDS,
    "history": HISTORY_FIELDS,
    "depth": DEPTH_FIELDS,
}
CONFIG_KEYS = frozenset({
    "schema_version", "model_version", "frozen_at", "trained_through", "scoring",
    "history_games", "half_life_games", "pseudo_games", "position_means",
    "position_mean_evidence_sha256", "position_mean_evidence_bytes",
})
POSITIONS = ("QB", "RB", "WR", "TE")
POSITION_MEAN_EVIDENCE_KIND = "PGO_FANTASY_POSITION_MEAN_EVIDENCE"
POSITION_MEAN_EVIDENCE_CONTRACT = "PGO_FANTASY_POSITION_MEANS_2020_2025_V1"
POSITION_MEAN_EVIDENCE_KEYS = frozenset({
    "schema_version", "artifact_kind", "status", "contract_version",
    "source_as_of", "captured_at", "frozen_at", "seasons", "population",
    "scoring", "position_means", "upstream_provenance", "artifact_sha256",
})
POSITION_MEAN_PROVENANCE_KEYS = frozenset({
    "source", "source_as_of", "captured_at", "sha256",
})
POSITION_MEAN_POPULATION = "QUALIFIED_STATS_ONLY_REGULAR_SEASON_PLAYER_GAMES"
LOCK_KIND = "PGO_FANTASY_T60_GAME_LOCK"
PREVIEW_KIND = "PGO_FANTASY_WEEKLY_PREVIEW"
LOCK_KEYS = frozenset({
    "schema_version", "artifact_kind", "status", "publication_status",
    "season", "week", "game_id", "kickoff", "away", "home",
    "decision_time", "locked_at", "teams_processed", "row_count", "coverage",
    "model_version", "config_sha256", "config_bytes", "code_sha",
    "position_mean_evidence_sha256", "position_mean_evidence_bytes",
    "scheduled_week_games",
    "source_receipts", "source_receipts_sha256", "predictions",
    "prediction_integrity_sha256", "artifact_sha256",
})
LOCK_PREDICTION_COLUMNS = (
    "season", "week", "game_id", "gsis_id", "player_name", "team",
    "opponent", "position", "null_prediction", "strong_prediction",
    "history_count", "initialization_reason", "availability_status",
    "qb_depth_rank", "ranking_eligible", "config_sha256",
)
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
SOURCE_RECEIPT_KEYS = frozenset({
    "schema_version", "kind", "source", "source_as_of", "captured_at",
    "teams_processed", "bytes", "sha256", "rows",
})
RESULT_ENVELOPE_KEYS = frozenset({
    "schema_version", "source", "source_as_of", "captured_at",
    "teams_processed", "games", "rows",
})
RESULT_GAME_FIELDS = frozenset({"game_id", "status", "finalized_at"})
RESULT_ROW_FIELDS = frozenset({"game_id", "gsis_id"}) | pgo_fantasy.SCORING_FIELDS
RESULT_RECEIPT_KEYS = frozenset({
    "schema_version", "source", "source_as_of", "captured_at",
    "teams_processed", "games", "rows", "bytes", "sha256",
})
WEEK_GRADE_KEYS = frozenset({
    "schema_version", "artifact_kind", "status", "publication_status",
    "season", "week", "model_version", "config_sha256", "code_sha",
    "position_mean_evidence_sha256",
    "lock_sha256", "lock_bytes", "result_receipt", "result_bytes",
    "checks", "metrics", "rows", "artifact_sha256",
})
WEEK_ROW_FIELDS = frozenset(LOCK_PREDICTION_COLUMNS) | {
    "position_rank", "flex_rank", "superflex_rank", "fantasy_points",
    "primary_pool", "null_absolute_error", "strong_absolute_error",
    "improvement",
}


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


def _valid_depth_source_identity(source, source_as_of):
    if not isinstance(source, str) or source_as_of is None:
        return False
    identity, marker, digest = source.rpartition("|sha256:")
    return (
        identity.strip()
        and marker == "|sha256:"
        and source.count("|sha256:") == 1
        and _hex_digest(digest, 64)
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
    if kind == "depth":
        if (
            not _valid_depth_source_identity(
                value["source"], value["source_as_of"]
            )
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


def _position_means(values, label):
    if not isinstance(values, dict) or set(values) != set(POSITIONS):
        raise ValueError(f"{label} position means are invalid")
    means = {}
    for position in POSITIONS:
        raw = values[position]
        if type(raw) not in {int, float}:
            raise ValueError(f"{label} position mean is invalid")
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} position mean is invalid") from error
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{label} position mean is invalid")
        means[position] = value
    return means


def verify_position_mean_evidence(receipt):
    if not isinstance(receipt, dict) or set(receipt) != POSITION_MEAN_EVIDENCE_KEYS:
        raise ValueError("Position mean evidence is invalid")
    if (
        type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or receipt["artifact_kind"] != POSITION_MEAN_EVIDENCE_KIND
        or receipt["status"] != "ACCEPTED"
        or receipt["contract_version"] != POSITION_MEAN_EVIDENCE_CONTRACT
        or receipt["seasons"] != list(range(2020, 2026))
        or receipt["population"] != POSITION_MEAN_POPULATION
        or receipt["scoring"] != "PGO_HALF_PPR_V1"
        or not _hex_digest(receipt["artifact_sha256"], 64)
    ):
        raise ValueError("Position mean evidence is invalid")
    source_as_of = parse_timestamp(
        receipt["source_as_of"], "position mean evidence source_as_of"
    )
    captured_at = parse_timestamp(
        receipt["captured_at"], "position mean evidence captured_at"
    )
    frozen_at = parse_timestamp(
        receipt["frozen_at"], "position mean evidence frozen_at"
    )
    if source_as_of > captured_at or captured_at > frozen_at:
        raise ValueError("Position mean evidence chronology is invalid")
    means = _position_means(receipt["position_means"], "Position mean evidence")
    provenance = receipt["upstream_provenance"]
    if not isinstance(provenance, list) or not provenance:
        raise ValueError("Position mean evidence provenance is invalid")
    normalized_provenance = []
    for item in provenance:
        if not isinstance(item, dict) or set(item) != POSITION_MEAN_PROVENANCE_KEYS:
            raise ValueError("Position mean evidence provenance is invalid")
        item_source_as_of = parse_timestamp(
            item["source_as_of"], "position mean provenance source_as_of"
        )
        item_captured_at = parse_timestamp(
            item["captured_at"], "position mean provenance captured_at"
        )
        if (
            item_source_as_of > item_captured_at
            or item_captured_at > frozen_at
            or not _hex_digest(item["sha256"], 64)
        ):
            raise ValueError("Position mean evidence provenance is invalid")
        normalized_provenance.append({
            "source": _required_text(
                item["source"], "position mean provenance source"
            ),
            "source_as_of": item["source_as_of"],
            "captured_at": item["captured_at"],
            "sha256": item["sha256"],
        })
    if normalized_provenance != sorted(
        normalized_provenance,
        key=lambda item: (
            item["source"], item["source_as_of"], item["captured_at"], item["sha256"],
        ),
    ):
        raise ValueError("Position mean evidence provenance is not canonical")
    normalized = deepcopy(receipt)
    normalized["position_means"] = means
    normalized["upstream_provenance"] = normalized_provenance
    if normalized["artifact_sha256"] != _artifact_hash(normalized):
        raise ValueError("Position mean evidence integrity is invalid")
    return normalized


def serialize_position_mean_evidence(receipt):
    return canonical_json(verify_position_mean_evidence(receipt)) + "\n"


def _position_mean_evidence_from_bytes(data):
    receipt = verify_position_mean_evidence(
        _decode_json(data, "position mean evidence")
    )
    if data != serialize_position_mean_evidence(receipt).encode("utf-8"):
        raise ValueError("Position mean evidence is not canonical")
    return receipt


def _validate_model_config(config):
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS:
        raise ValueError("Prospective model config is invalid")
    if (
        type(config["schema_version"]) is not int
        or config["schema_version"] != 1
        or config["model_version"] != "pgo_fantasy_2026_baseline_v2"
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
        or not isinstance(config["position_mean_evidence_bytes"], str)
    ):
        raise ValueError("Prospective model config is invalid")
    frozen_at = parse_timestamp(config["frozen_at"], "model config frozen_at")
    means = _position_means(config["position_means"], "Prospective model config")
    try:
        receipt_bytes = config["position_mean_evidence_bytes"].encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("Prospective model config position mean evidence is invalid") from error
    receipt = _position_mean_evidence_from_bytes(receipt_bytes)
    if (
        hashlib.sha256(receipt_bytes).hexdigest()
        != config["position_mean_evidence_sha256"]
        or not _matches_frozen_value(receipt["position_means"], means)
        or receipt["scoring"] != config["scoring"]
        or parse_timestamp(
            receipt["frozen_at"], "position mean evidence frozen_at"
        ) > frozen_at
    ):
        raise ValueError("Prospective model config position mean evidence is invalid")
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


def _validate_inputs(sources, model, cutoff=None, depth_cutoff=None):
    required = {"schedule", "roster", "history", "depth"}
    if set(sources) - set(SOURCE_KINDS):
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
        _ensure_captured(
            source,
            depth_cutoff if kind == "depth" and depth_cutoff is not None else cutoff,
            kind,
        )


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


def _availability_state(source, roster, teams, lock_mode):
    verified = (
        source is not None
        and set(teams) <= set(source["receipt"]["teams_processed"])
    )
    if lock_mode and not verified:
        raise ValueError("Prospective availability coverage is incomplete")
    if not verified:
        return None
    roster_teams = {row["gsis_id"]: row["team"] for row in roster}
    inactive = set()
    for row in source["snapshot"]["rows"]:
        team = normalize_team(_required_text(row["team"], "availability team"))
        gsis_id = _required_text(row["gsis_id"], "availability gsis_id")
        if not gsis_id or row["status"] != "INACTIVE":
            raise ValueError("Prospective availability row is invalid")
        if gsis_id in roster_teams and roster_teams[gsis_id] != team:
            raise ValueError("Prospective availability identity contradicts roster")
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
    _validate_inputs(
        sources, model, min(generated, decision),
        depth_cutoff=generated if not lock_mode else None,
    )
    teams = {game["away"], game["home"]}
    roster = _roster_rows(sources["roster"], teams)
    inactive = _availability_state(
        sources.get("availability"), roster, teams, lock_mode
    )
    depth_ranks = _depth_ranks(sources["depth"], roster, teams)
    eligible_qbs = _qb_starters(roster, depth_ranks, inactive or set())
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
            depth_cutoff=generated,
        )
    scheduled_teams = {
        team for game in games for team in (game["away"], game["home"])
    }
    roster_teams = set(sources["roster"]["receipt"]["teams_processed"])
    depth_teams = set(sources["depth"]["receipt"]["teams_processed"])
    if not scheduled_teams <= roster_teams:
        raise ValueError("Prospective preview roster coverage is incomplete")
    if not scheduled_teams <= depth_teams:
        raise ValueError("Prospective preview depth coverage is incomplete")
    rows = []
    for game in games:
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
        "teams_missing": [],
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
                ("depth", sources["depth"]),
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


def _write_preview(output, text):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pgo_fantasy._exclusive_write_text(output, text)


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
        rank = row["qb_depth_rank"]
        if (
            (row["position"] == "QB" and (
                type(rank) is not int or rank <= 0
            ))
            or (row["position"] != "QB" and rank is not None)
        ):
            raise ValueError("Fantasy game lock QB depth rank is invalid")
        if (
            row["position"] != "QB"
            and row["availability_status"] == "ACTIVE"
            and not row["ranking_eligible"]
        ):
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
    if lock is not None and {
        row["team"] for row in rows
    } != set(lock["teams_processed"]):
        raise ValueError("Fantasy game lock prediction context is invalid")
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
        "config_bytes": model["bytes"].decode("utf-8"),
        "code_sha": code_sha,
        "position_mean_evidence_sha256": model["config"]["position_mean_evidence_sha256"],
        "position_mean_evidence_bytes": model["config"]["position_mean_evidence_bytes"],
        "teams_processed": sorted((
            projected["game"]["away"], projected["game"]["home"]
        )),
        "row_count": len(projected["rows"]),
        "coverage": {"roster": True, "availability": True, "depth": True},
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
        or not _hex_digest(lock["position_mean_evidence_sha256"], 64)
        or not isinstance(lock["config_bytes"], str)
        or not isinstance(lock["position_mean_evidence_bytes"], str)
        or lock["teams_processed"] != sorted((lock["away"], lock["home"]))
        or len(set(lock["teams_processed"])) != 2
        or type(lock["row_count"]) is not int or lock["row_count"] <= 0
        or lock["row_count"] != len(lock["predictions"])
        or lock["coverage"] != {"roster": True, "availability": True, "depth": True}
        or lock["scheduled_week_games"] != sorted(set(lock["scheduled_week_games"]))
        or lock["game_id"] not in lock["scheduled_week_games"]
        or lock["prediction_integrity_sha256"] != _prediction_hash(lock["predictions"])
        or lock["source_receipts_sha256"] != hashlib.sha256(
            canonical_json(lock["source_receipts"]).encode("utf-8")
        ).hexdigest()
        or lock["artifact_sha256"] != _artifact_hash(lock)
    ):
        raise ValueError("Fantasy game lock integrity is invalid")
    try:
        config_data = lock["config_bytes"].encode("utf-8")
        evidence_data = lock["position_mean_evidence_bytes"].encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("Fantasy game lock config evidence is invalid") from error
    config = _validate_model_config(
        _decode_json(config_data, "prospective model config")
    )
    evidence = _position_mean_evidence_from_bytes(evidence_data)
    if (
        config_data != serialize_model_config(config).encode("utf-8")
        or hashlib.sha256(config_data).hexdigest() != lock["config_sha256"]
        or config["model_version"] != lock["model_version"]
        or config["position_mean_evidence_sha256"]
        != lock["position_mean_evidence_sha256"]
        or config["position_mean_evidence_bytes"]
        != lock["position_mean_evidence_bytes"]
        or hashlib.sha256(evidence_data).hexdigest()
        != lock["position_mean_evidence_sha256"]
        or not _matches_frozen_value(
            evidence["position_means"], config["position_means"]
        )
    ):
        raise ValueError("Fantasy game lock config evidence is invalid")
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
    depth_receipt = next(
        receipt for receipt in receipts if receipt["kind"] == "depth"
    )
    if not _valid_depth_source_identity(
        depth_receipt["source"], depth_receipt["source_as_of"]
    ):
        raise ValueError("Fantasy game lock source receipts are invalid")
    try:
        receipt_teams = {
            receipt["kind"]: _validated_teams(
                receipt["teams_processed"], f"{receipt['kind']} receipt"
            )
            for receipt in receipts
        }
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("Fantasy game lock source receipts are invalid") from error
    if any(receipt["teams_processed"] != receipt_teams[receipt["kind"]]
           for receipt in receipts):
        raise ValueError("Fantasy game lock source receipts are invalid")
    coverage = {
        kind: set(lock["teams_processed"]) <= set(teams)
        for kind, teams in receipt_teams.items()
    }
    if not all(coverage[kind] for kind in ("roster", "availability", "depth")):
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


def _write_guarded_game_lock(output_dir, outputs, publication_guard):
    staged, owned = [], {}
    owns_output_dir = success = False
    failure = None
    try:
        output_dir.mkdir(parents=True)
        owns_output_dir = True
        for target, content in outputs:
            descriptor, name = tempfile.mkstemp(
                dir=target.parent, prefix=f".{target.name}.", suffix=".pending"
            )
            os.close(descriptor)
            staged_path = Path(name)
            staged.append(staged_path)
            atomic_write_text(staged_path, content)
        for (target, _), staged_path in zip(outputs, staged):
            publication_guard()
            state = staged_path.stat(follow_symlinks=False)
            owned[target] = state
            os.link(staged_path, target)
        if any(
            not os.path.samestat(target.stat(follow_symlinks=False), state)
            for target, state in owned.items()
        ):
            raise OSError("Output reservation ownership changed")
        success = True
    except BaseException as error:
        failure = error
        for target, state in owned.items():
            pgo_prospective._detach_output(target, state)
    finally:
        for staged_path in staged:
            try:
                staged_path.unlink(missing_ok=True)
            except BaseException:
                pass
        if owns_output_dir and not success:
            try:
                output_dir.rmdir()
            except BaseException:
                pass
    if isinstance(failure, (KeyboardInterrupt, SystemExit, ValueError)):
        raise failure
    return success


def write_game_lock(output_dir, lock, publication_guard=None):
    output_dir = Path(output_dir)
    outputs = (
        (output_dir / "fantasy_lock.json", serialize_game_lock(lock)),
        (output_dir / "fantasy_predictions.csv", game_prediction_csv(lock)),
    )
    if publication_guard is not None:
        return _write_guarded_game_lock(output_dir, outputs, publication_guard)
    return pgo_prospective._write_new_outputs(output_dir, outputs)


def _results_from_bytes(data):
    value = _decode_json(data, "fantasy results")
    if not isinstance(value, dict) or set(value) != RESULT_ENVELOPE_KEYS:
        raise ValueError("Fantasy result envelope is invalid")
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not isinstance(value["source"], str)
        or not value["source"].strip()
    ):
        raise ValueError("Fantasy result schema is invalid")
    captured = parse_timestamp(value["captured_at"], "result captured_at")
    if value["source_as_of"] is not None and parse_timestamp(
        value["source_as_of"], "result source_as_of"
    ) > captured:
        raise ValueError("Fantasy result source_as_of is after capture")
    teams = _validated_teams(value["teams_processed"], "results")
    games, seen_games = [], set()
    if not isinstance(value["games"], list):
        raise ValueError("Fantasy final game rows are invalid")
    for game in value["games"]:
        if not isinstance(game, dict) or set(game) != RESULT_GAME_FIELDS:
            raise ValueError("Fantasy final game row is invalid")
        game_id = _required_text(game["game_id"], "result game_id")
        if game_id in seen_games or game["status"] != "FINAL":
            raise ValueError("Fantasy final game row is invalid")
        if parse_timestamp(game["finalized_at"], "game finalized_at") > captured:
            raise ValueError("Fantasy final game is after result capture")
        seen_games.add(game_id)
        games.append(deepcopy(game))
    if not isinstance(value["rows"], list):
        raise ValueError("Fantasy result player rows are invalid")
    rows, seen_rows = [], set()
    for row in value["rows"]:
        if not isinstance(row, dict) or set(row) != RESULT_ROW_FIELDS:
            raise ValueError("Fantasy result player row is invalid")
        key = (
            _required_text(row["game_id"], "result game_id"),
            _required_text(row["gsis_id"], "result gsis_id"),
        )
        if key in seen_rows or key[0] not in seen_games or not all(
            type(row[field]) in {int, float} and math.isfinite(row[field])
            for field in pgo_fantasy.SCORING_FIELDS
        ):
            raise ValueError("Fantasy result player row is invalid")
        pgo_fantasy.half_ppr(row)
        seen_rows.add(key)
        rows.append(deepcopy(row))
    snapshot = deepcopy(value)
    snapshot["source"] = value["source"].strip()
    snapshot["teams_processed"] = teams
    snapshot["games"] = sorted(games, key=lambda game: game["game_id"])
    snapshot["rows"] = sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"]))
    return {
        "snapshot": snapshot,
        "receipt": {
            "schema_version": 1,
            "source": snapshot["source"], "source_as_of": value["source_as_of"],
            "captured_at": value["captured_at"], "teams_processed": teams,
            "games": len(games), "rows": len(rows), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        "bytes": data,
    }


def load_results(path):
    return _results_from_bytes(Path(path).read_bytes())


def verify_loaded_results(loaded):
    if not isinstance(loaded, dict) or set(loaded) != {
        "snapshot", "receipt", "bytes",
    } or not isinstance(loaded["bytes"], bytes):
        raise ValueError("Loaded fantasy results are invalid")
    if not _matches_frozen_value(loaded, _results_from_bytes(loaded["bytes"])):
        raise ValueError("Parsed fantasy results do not match frozen bytes")
    return loaded


def _verify_result_receipt(receipt):
    if not isinstance(receipt, dict) or set(receipt) != RESULT_RECEIPT_KEYS:
        raise ValueError("Weekly fantasy result receipt is invalid")
    if (
        type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or not isinstance(receipt["source"], str)
        or not receipt["source"].strip()
        or type(receipt["games"]) is not int or receipt["games"] < 0
        or type(receipt["rows"]) is not int or receipt["rows"] < 0
        or type(receipt["bytes"]) is not int or receipt["bytes"] <= 0
        or not _hex_digest(receipt["sha256"], 64)
    ):
        raise ValueError("Weekly fantasy result receipt is invalid")
    captured = parse_timestamp(receipt["captured_at"], "result receipt captured_at")
    if receipt["source_as_of"] is not None and parse_timestamp(
        receipt["source_as_of"], "result receipt source_as_of"
    ) > captured:
        raise ValueError("Weekly fantasy result receipt is invalid")
    teams = _validated_teams(receipt["teams_processed"], "result receipt")
    if receipt["teams_processed"] != teams:
        raise ValueError("Weekly fantasy result receipt is invalid")
    return receipt


def _mae(rows, prediction):
    return math.fsum(
        abs(row["fantasy_points"] - row[prediction]) for row in rows
    ) / len(rows)


def _grade_week(loaded_locks, loaded_results):
    if not isinstance(loaded_locks, list) or not loaded_locks:
        raise ValueError("Weekly fantasy locks are missing")
    verify_loaded_results(loaded_results)
    locks, loaded_hashes = [], []
    for loaded in loaded_locks:
        if not isinstance(loaded, dict) or set(loaded) != {"lock", "bytes", "sha256"}:
            raise ValueError("Loaded fantasy game lock is invalid")
        lock = verify_game_lock(loaded["lock"])
        if not isinstance(loaded["bytes"], bytes) or (
            loaded["bytes"] != serialize_game_lock(lock).encode("utf-8")
        ):
            raise ValueError("Fantasy game lock bytes are not exact")
        if loaded["sha256"] != hashlib.sha256(loaded["bytes"]).hexdigest():
            raise ValueError("Fantasy game lock hash is invalid")
        locks.append(lock)
        loaded_hashes.append(loaded["sha256"])
    first = locks[0]
    common = (
        first["season"], first["week"], first["model_version"],
        first["config_sha256"], first["code_sha"],
        first["position_mean_evidence_sha256"],
    )
    if any(
        (
            lock["season"], lock["week"], lock["model_version"],
            lock["config_sha256"], lock["code_sha"],
            lock["position_mean_evidence_sha256"],
        )
        != common for lock in locks
    ):
        raise ValueError("Weekly fantasy locks do not share one model epoch")
    expected_games = set(first["scheduled_week_games"])
    if any(set(lock["scheduled_week_games"]) != expected_games for lock in locks):
        raise ValueError("Weekly fantasy schedule manifests disagree")
    if {lock["game_id"] for lock in locks} != expected_games or len(locks) != len(expected_games):
        raise ValueError("Weekly fantasy lock coverage is incomplete")
    expected_teams = {team for lock in locks for team in lock["teams_processed"]}
    if not expected_teams <= set(loaded_results["receipt"]["teams_processed"]):
        raise ValueError("Weekly fantasy result team coverage is incomplete")
    final_games = {
        game["game_id"]: game for game in loaded_results["snapshot"]["games"]
    }
    if set(final_games) != expected_games:
        raise ValueError("Weekly fantasy final game coverage is incomplete")
    if any(
        parse_timestamp(
            final_games[lock["game_id"]]["finalized_at"], "game finalized_at"
        ) <= parse_timestamp(lock["kickoff"], "kickoff")
        for lock in locks
    ):
        raise ValueError("Weekly fantasy result finalized_at is not after kickoff")
    predictions = rank_rows([
        row for lock in locks for row in lock["predictions"]
    ])
    prediction_keys = {(row["game_id"], row["gsis_id"]) for row in predictions}
    result_rows = {
        (row["game_id"], row["gsis_id"]): row
        for row in loaded_results["snapshot"]["rows"]
    }
    if not set(result_rows) <= prediction_keys:
        raise ValueError("Fantasy result identity is not in the locked population")
    primary = pgo_fantasy.select_primary_pool([
        row for row in predictions if row["ranking_eligible"]
    ])
    if len(primary) != 96:
        raise ValueError("Weekly fantasy primary pool is not 96 rows")
    rows = []
    for prediction in predictions:
        key = prediction["game_id"], prediction["gsis_id"]
        actual = pgo_fantasy.half_ppr(result_rows[key]) if key in result_rows else 0.0
        rows.append({
            **prediction,
            "fantasy_points": actual,
            "primary_pool": key in primary,
            "null_absolute_error": abs(actual - prediction["null_prediction"]),
            "strong_absolute_error": abs(actual - prediction["strong_prediction"]),
            "improvement": (
                abs(actual - prediction["null_prediction"])
                - abs(actual - prediction["strong_prediction"])
            ),
        })
    selected = [row for row in rows if row["primary_pool"]]
    null_mae = _mae(selected, "null_prediction")
    strong_mae = _mae(selected, "strong_prediction")
    grade = {
        "schema_version": 1,
        "artifact_kind": "PGO_FANTASY_WEEK_GRADE",
        "status": "HOLD",
        "publication_status": "EXPERIMENTAL",
        "season": first["season"], "week": first["week"],
        "model_version": first["model_version"],
        "config_sha256": first["config_sha256"], "code_sha": first["code_sha"],
        "position_mean_evidence_sha256": first["position_mean_evidence_sha256"],
        "lock_sha256": sorted(loaded_hashes),
        "lock_bytes": [data.decode("utf-8") for _, data in sorted(
            zip(loaded_hashes, (loaded["bytes"] for loaded in loaded_locks))
        )],
        "result_receipt": loaded_results["receipt"],
        "result_bytes": loaded_results["bytes"].decode("utf-8"),
        "checks": {
            "complete_game_locks": True,
            "complete_game_results": True,
            "primary_pool_96": True,
            "exact_lock_binding": True,
        },
        "metrics": {"primary": {
            "count": 96, "null_mae": null_mae, "strong_mae": strong_mae,
            "improvement": null_mae - strong_mae,
            "relative_improvement": (
                (null_mae - strong_mae) / null_mae if null_mae > 0.0 else 0.0
            ),
            "strong_win": strong_mae < null_mae,
        }},
        "rows": sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"])),
    }
    grade["artifact_sha256"] = _artifact_hash(grade)
    return grade


def _grade_evidence(grade):
    lock_bytes = grade["lock_bytes"]
    if not isinstance(lock_bytes, list) or len(lock_bytes) != len(grade["lock_sha256"]):
        raise ValueError("Weekly fantasy grade evidence is invalid")
    locks = []
    for text, sha256 in zip(lock_bytes, grade["lock_sha256"]):
        if not isinstance(text, str):
            raise ValueError("Weekly fantasy grade evidence is invalid")
        try:
            data = text.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError("Weekly fantasy grade evidence is invalid") from error
        lock = _decode_json(data, "fantasy game lock")
        verify_game_lock(lock)
        if data != serialize_game_lock(lock).encode("utf-8") or (
            hashlib.sha256(data).hexdigest() != sha256
        ):
            raise ValueError("Weekly fantasy grade evidence binding is invalid")
        locks.append({"lock": lock, "bytes": data, "sha256": sha256})
    if not isinstance(grade["result_bytes"], str):
        raise ValueError("Weekly fantasy grade evidence is invalid")
    try:
        result_data = grade["result_bytes"].encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("Weekly fantasy grade evidence is invalid") from error
    results = _results_from_bytes(result_data)
    if not _matches_frozen_value(results["receipt"], grade["result_receipt"]):
        raise ValueError("Weekly fantasy result receipt binding is invalid")
    return locks, results


def grade_week(loaded_locks, loaded_results):
    return verify_week_grade(_grade_week(loaded_locks, loaded_results))


def verify_week_grade(grade):
    if not isinstance(grade, dict) or set(grade) != WEEK_GRADE_KEYS:
        raise ValueError("Weekly fantasy grade contract is invalid")
    if (
        type(grade["schema_version"]) is not int
        or grade["schema_version"] != 1
        or grade["artifact_kind"] != "PGO_FANTASY_WEEK_GRADE"
        or grade["status"] != "HOLD"
        or grade["publication_status"] != "EXPERIMENTAL"
        or type(grade["season"]) is not int or grade["season"] != 2026
        or type(grade["week"]) is not int or not 1 <= grade["week"] <= 18
        or not isinstance(grade["model_version"], str)
        or not grade["model_version"].strip()
        or not _hex_digest(grade["config_sha256"], 64)
        or not _hex_digest(grade["code_sha"], 40)
        or not _hex_digest(grade["position_mean_evidence_sha256"], 64)
        or not isinstance(grade["lock_sha256"], list)
        or grade["lock_sha256"] != sorted(set(grade["lock_sha256"]))
        or not grade["lock_sha256"]
        or not all(_hex_digest(value, 64) for value in grade["lock_sha256"])
        or grade["checks"] != {
            "complete_game_locks": True,
            "complete_game_results": True,
            "primary_pool_96": True,
            "exact_lock_binding": True,
        }
    ):
        raise ValueError("Weekly fantasy grade metadata is invalid")
    if (
        not isinstance(grade["checks"], dict)
        or set(grade["checks"]) != {
            "complete_game_locks", "complete_game_results", "primary_pool_96",
            "exact_lock_binding",
        }
        or any(type(value) is not bool or value is not True
               for value in grade["checks"].values())
    ):
        raise ValueError("Weekly fantasy grade metadata is invalid")
    _verify_result_receipt(grade["result_receipt"])
    rows = grade["rows"]
    if (
        not isinstance(rows, list) or not rows
        or rows != sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"]))
        or any(not isinstance(row, dict) or set(row) != WEEK_ROW_FIELDS for row in rows)
    ):
        raise ValueError("Weekly fantasy grade rows are invalid")
    base_rows = [{field: row[field] for field in LOCK_PREDICTION_COLUMNS} for row in rows]
    _validate_lock_predictions(base_rows)
    reranked = {
        (row["game_id"], row["gsis_id"]): row for row in rank_rows(base_rows)
    }
    primary = pgo_fantasy.select_primary_pool([
        row for row in base_rows if row["ranking_eligible"]
    ])
    if len(primary) != 96:
        raise ValueError("Weekly fantasy grade primary pool is invalid")
    for row in rows:
        key = row["game_id"], row["gsis_id"]
        actual = row["fantasy_points"]
        if (
            row["season"] != 2026 or row["week"] != grade["week"]
            or row["config_sha256"] != grade["config_sha256"]
            or type(row["primary_pool"]) is not bool
            or row["primary_pool"] != (key in primary)
            or type(actual) not in {int, float} or not math.isfinite(actual)
            or any(
                value is not None and type(value) is not int
                for value in (row["position_rank"], row["flex_rank"], row["superflex_rank"])
            )
            or any(
                type(row[field]) not in {int, float} or not math.isfinite(row[field])
                for field in ("null_absolute_error", "strong_absolute_error", "improvement")
            )
            or any(row[field] != reranked[key][field] for field in (
                "position_rank", "flex_rank", "superflex_rank"
            ))
            or row["null_absolute_error"] != abs(actual - row["null_prediction"])
            or row["strong_absolute_error"] != abs(actual - row["strong_prediction"])
            or row["improvement"] != (
                row["null_absolute_error"] - row["strong_absolute_error"]
            )
        ):
            raise ValueError("Weekly fantasy grade row binding is invalid")
    selected = [row for row in rows if row["primary_pool"]]
    null_mae = _mae(selected, "null_prediction")
    strong_mae = _mae(selected, "strong_prediction")
    expected_metrics = {"primary": {
        "count": 96,
        "null_mae": null_mae,
        "strong_mae": strong_mae,
        "improvement": null_mae - strong_mae,
        "relative_improvement": (
            (null_mae - strong_mae) / null_mae if null_mae > 0.0 else 0.0
        ),
        "strong_win": strong_mae < null_mae,
    }}
    metrics = grade["metrics"]
    primary_metrics = metrics.get("primary") if isinstance(metrics, dict) else None
    if (
        not isinstance(primary_metrics, dict)
        or set(metrics) != {"primary"}
        or set(primary_metrics) != set(expected_metrics["primary"])
        or type(primary_metrics["count"]) is not int
        or any(
            type(primary_metrics[field]) not in {int, float}
            or not math.isfinite(primary_metrics[field])
            for field in ("null_mae", "strong_mae", "improvement", "relative_improvement")
        )
        or type(primary_metrics["strong_win"]) is not bool
        or metrics != expected_metrics
    ):
        raise ValueError("Weekly fantasy grade metrics are invalid")
    if grade["artifact_sha256"] != _artifact_hash(grade):
        raise ValueError("Weekly fantasy grade integrity is invalid")
    locks, results = _grade_evidence(grade)
    if not _matches_frozen_value(grade, _grade_week(locks, results)):
        raise ValueError("Weekly fantasy grade evidence binding is invalid")
    return grade


def serialize_week_grade(grade):
    verify_week_grade(grade)
    return canonical_json(grade) + "\n"


def write_week_grade(output_dir, grade):
    output_dir = Path(output_dir)
    return pgo_prospective._write_new_outputs(output_dir, (
        (output_dir / "fantasy_week_grade.json", serialize_week_grade(grade)),
    ))


BOOTSTRAP_SEED = 20260901
BOOTSTRAP_SAMPLES = 10_000
LEAKAGE_AUDIT_KIND = "PGO_FANTASY_PROSPECTIVE_LEAKAGE_AUDIT"
LEAKAGE_AUDIT_CONTRACT = "PGO_FANTASY_PROSPECTIVE_2026_SCIENTIFIC_V2"
LEAKAGE_AUDIT_ITEMS = (
    "target_outcome_boundary", "history_cutoff", "position_mean_initializer",
    "roster_availability", "qb_depth_eligibility", "schedule_result_joins", "ranking_primary_pool",
    "metrics_uncertainty", "epoch_firewall",
)
LEAKAGE_AUDIT_KEYS = frozenset({
    "schema_version", "artifact_kind", "status", "verdict", "audited_at",
    "scientific_contract", "model_version", "config_sha256", "code_sha",
    "position_mean_evidence_sha256", "weekly_evidence", "feature_inventory",
    "provider_vintage_disposition", "findings", "remediation", "artifact_sha256",
})
LEAKAGE_AUDIT_WEEK_KEYS = frozenset({
    "week", "week_grade_sha256", "lock_sha256", "result_receipt_sha256",
    "source_receipts",
})
LEAKAGE_AUDIT_SOURCE_KEYS = frozenset({
    "lock_sha256", "source_receipts_sha256",
})
LEAKAGE_AUDIT_ITEM_KEYS = frozenset({"item", "outcome", "evidence"})
SEASON_GRADE_KEYS = frozenset({
    "schema_version", "artifact_kind", "status", "publication_status",
    "season", "model_version", "config_sha256", "code_sha",
    "position_mean_evidence_sha256", "checks",
    "metrics", "bootstrap", "leakage_audit_sha256",
    "leakage_audit_verdict", "leakage_audit_audited_at",
    "latest_result_captured_at", "weeks",
    "week_grade_sha256", "week_grade_bytes", "leakage_audit_bytes",
    "rejected_week_grade_bytes", "diagnostics", "artifact_sha256",
})
SEASON_CHECK_KEYS = frozenset({
    "season_complete", "common_model_epoch", "weekly_primary_pools",
    "relative_improvement_at_least_1pct", "bootstrap_lower_positive",
    "strict_majority_weekly_wins", "leakage_audit_clean",
    "leakage_audit_after_results", "leakage_audit_binding",
    "artifact_integrity",
})
SEASON_METRIC_KEYS = frozenset({
    "primary_count", "null_mae", "strong_mae", "relative_improvement",
    "weekly_wins",
})
SEASON_BOOTSTRAP_KEYS = frozenset({
    "mean", "lower", "upper", "samples", "seed",
})


def load_week_grade(path):
    data = Path(path).read_bytes()
    grade = verify_week_grade(_decode_json(data, "weekly fantasy grade"))
    if data != serialize_week_grade(grade).encode("utf-8"):
        raise ValueError("Weekly fantasy grade is not canonical")
    return grade


def verify_leakage_audit(audit):
    if (
        not isinstance(audit, dict) or set(audit) != LEAKAGE_AUDIT_KEYS
        or type(audit["schema_version"]) is not int
        or audit["schema_version"] != 1
        or audit["artifact_kind"] != LEAKAGE_AUDIT_KIND
        or audit["status"] != "COMPLETE"
        or audit["verdict"] not in {"CLEAN", "REVIEW REQUIRED", "NOT CLEAN"}
        or audit["scientific_contract"] != LEAKAGE_AUDIT_CONTRACT
        or not isinstance(audit["model_version"], str)
        or not audit["model_version"].strip()
        or not _hex_digest(audit["config_sha256"], 64)
        or not _hex_digest(audit["code_sha"], 40)
        or not _hex_digest(audit["position_mean_evidence_sha256"], 64)
        or audit["provider_vintage_disposition"] not in {
            "CLEAN", "REVIEW REQUIRED", "NOT CLEAN",
        }
        or not _hex_digest(audit["artifact_sha256"], 64)
    ):
        raise ValueError("Prospective leakage audit is invalid")
    parse_timestamp(audit["audited_at"], "leakage audited_at")
    evidence = audit["weekly_evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Prospective leakage audit evidence is invalid")
    weeks = []
    for item in evidence:
        if (
            not isinstance(item, dict) or set(item) != LEAKAGE_AUDIT_WEEK_KEYS
            or type(item["week"]) is not int or not 1 <= item["week"] <= 18
            or not _hex_digest(item["week_grade_sha256"], 64)
            or not isinstance(item["lock_sha256"], list)
            or item["lock_sha256"] != sorted(set(item["lock_sha256"]))
            or not item["lock_sha256"]
            or not all(_hex_digest(value, 64) for value in item["lock_sha256"])
            or not _hex_digest(item["result_receipt_sha256"], 64)
            or not isinstance(item["source_receipts"], list)
        ):
            raise ValueError("Prospective leakage audit evidence is invalid")
        sources = item["source_receipts"]
        if (
            len(sources) != len(item["lock_sha256"])
            or any(
                not isinstance(source, dict)
                or set(source) != LEAKAGE_AUDIT_SOURCE_KEYS
                or not _hex_digest(source["lock_sha256"], 64)
                or not _hex_digest(source["source_receipts_sha256"], 64)
                for source in sources
            )
            or [source["lock_sha256"] for source in sources]
            != item["lock_sha256"]
        ):
            raise ValueError("Prospective leakage audit evidence is invalid")
        weeks.append(item["week"])
    if weeks != sorted(set(weeks)):
        raise ValueError("Prospective leakage audit evidence is not canonical")
    inventory = audit["feature_inventory"]
    if (
        not isinstance(inventory, list) or len(inventory) != len(LEAKAGE_AUDIT_ITEMS)
        or any(
            not isinstance(item, dict) or set(item) != LEAKAGE_AUDIT_ITEM_KEYS
            or item["outcome"] not in {"PASS", "REVIEW REQUIRED", "NOT CLEAN"}
            or not isinstance(item["evidence"], str) or not item["evidence"].strip()
            for item in inventory
        )
        or [item["item"] for item in inventory] != list(LEAKAGE_AUDIT_ITEMS)
    ):
        raise ValueError("Prospective leakage audit inventory is invalid")
    for field in ("findings", "remediation"):
        if (
            not isinstance(audit[field], list) or not audit[field]
            or not all(isinstance(item, str) and item.strip() for item in audit[field])
        ):
            raise ValueError("Prospective leakage audit record is invalid")
    if audit["verdict"] == "CLEAN" and (
        audit["provider_vintage_disposition"] != "CLEAN"
        or any(item["outcome"] != "PASS" for item in inventory)
    ):
        raise ValueError("Prospective leakage audit clean verdict is invalid")
    if audit["artifact_sha256"] != _artifact_hash(audit):
        raise ValueError("Prospective leakage audit integrity is invalid")
    return audit


def load_leakage_audit(path):
    data = Path(path).read_bytes()
    audit = verify_leakage_audit(
        _decode_json(data, "prospective leakage audit")
    )
    if data != (canonical_json(audit) + "\n").encode("utf-8"):
        raise ValueError("Prospective leakage audit is not canonical")
    return audit


def _audit_weekly_evidence(grades):
    evidence = []
    for grade in sorted(grades, key=lambda grade: grade["week"]):
        locks, _ = _grade_evidence(grade)
        evidence.append({
            "week": grade["week"],
            "week_grade_sha256": grade["artifact_sha256"],
            "lock_sha256": grade["lock_sha256"],
            "result_receipt_sha256": grade["result_receipt"]["sha256"],
            "source_receipts": [{
                "lock_sha256": loaded["sha256"],
                "source_receipts_sha256": (
                    loaded["lock"]["source_receipts_sha256"]
                ),
            } for loaded in locks],
        })
    return evidence


def _audit_matches_grades(audit, grades):
    epochs = {
        (
            grade["model_version"], grade["config_sha256"], grade["code_sha"],
            grade["position_mean_evidence_sha256"],
        )
        for grade in grades
    }
    if not grades or len(epochs) != 1:
        return False
    model_version, config_sha256, code_sha, position_mean_evidence_sha256 = (
        next(iter(epochs))
    )
    return all((
        audit["model_version"] == model_version,
        audit["config_sha256"] == config_sha256,
        audit["code_sha"] == code_sha,
        audit["position_mean_evidence_sha256"] == position_mean_evidence_sha256,
        _matches_frozen_value(
            audit["weekly_evidence"], _audit_weekly_evidence(grades)
        ),
    ))


def _bootstrap_rows(rows):
    return [{
        "season": row["season"], "week": row["week"],
        "actual_margin": row["fantasy_points"],
        "pgo_v0_prediction": row["null_prediction"],
        "challenger_prediction": row["strong_prediction"],
    } for row in rows]


def _season_status(checks):
    complete = checks["season_complete"]
    blocked = (
        not checks["artifact_integrity"]
        or not checks["common_model_epoch"]
        or (complete and not all((
            checks["weekly_primary_pools"], checks["leakage_audit_clean"],
            checks["leakage_audit_after_results"], checks["leakage_audit_binding"],
        )))
    )
    statistical = all((
        complete, checks["weekly_primary_pools"],
        checks["relative_improvement_at_least_1pct"],
        checks["bootstrap_lower_positive"],
        checks["strict_majority_weekly_wins"],
        checks["leakage_audit_clean"], checks["leakage_audit_after_results"],
        checks["leakage_audit_binding"],
        checks["artifact_integrity"], checks["common_model_epoch"],
    ))
    return "BLOCKED" if blocked else "PASS" if statistical else "HOLD"


def _rank_values(values):
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        rank = (start + 1 + end) / 2.0
        for index, _ in ordered[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def _spearman(rows):
    if len(rows) < 2:
        return None
    actual = _rank_values([row["fantasy_points"] for row in rows])
    strong = _rank_values([row["strong_prediction"] for row in rows])
    actual_mean = math.fsum(actual) / len(actual)
    strong_mean = math.fsum(strong) / len(strong)
    numerator = math.fsum((x - actual_mean) * (y - strong_mean)
                         for x, y in zip(actual, strong))
    denominator = math.sqrt(
        math.fsum((x - actual_mean) ** 2 for x in actual)
        * math.fsum((y - strong_mean) ** 2 for y in strong)
    )
    return None if denominator == 0.0 else numerator / denominator


def _diagnostics(rows, grades, input_count):
    def summary(values):
        if not values:
            return {"count": 0, "null_mae": None, "strong_mae": None,
                    "null_rmse": None, "strong_rmse": None,
                    "null_bias": None, "strong_bias": None}
        def rmse(field):
            return math.sqrt(math.fsum(
                (row[field] - row["fantasy_points"]) ** 2 for row in values
            ) / len(values))
        def bias(field):
            return math.fsum(
                row[field] - row["fantasy_points"] for row in values
            ) / len(values)
        return {"count": len(values), "null_mae": _mae(values, "null_prediction"),
                "strong_mae": _mae(values, "strong_prediction"),
                "null_rmse": rmse("null_prediction"),
                "strong_rmse": rmse("strong_prediction"),
                "null_bias": bias("null_prediction"), "strong_bias": bias("strong_prediction")}
    weekly = [{"week": grade["week"], "strong_spearman": _spearman([
        row for row in grade["rows"] if row["primary_pool"]
    ])} for grade in grades]
    return {
        "primary": summary(rows),
        "by_position": {position: summary([
            row for row in rows if row["position"] == position
        ]) for position in POSITIONS},
        "true_cold_start_primary": summary([
            row for row in rows if row["initialization_reason"] == "TRUE_COLD_START"
        ]),
        "weekly_strong_spearman": weekly,
        "availability_counts": {
            "active": sum(row["availability_status"] == "ACTIVE" for grade in grades for row in grade["rows"]),
            "inactive": sum(row["availability_status"] == "INACTIVE" for grade in grades for row in grade["rows"]),
        },
        "largest_strong_misses": [{
            "game_id": row["game_id"], "gsis_id": row["gsis_id"],
            "fantasy_points": row["fantasy_points"],
            "strong_prediction": row["strong_prediction"],
            "strong_absolute_error": row["strong_absolute_error"],
        } for row in sorted(
            (row for grade in grades for row in grade["rows"]),
            key=lambda row: (-row["strong_absolute_error"], row["game_id"], row["gsis_id"]),
        )[:10]],
        "coverage": {"provided_week_grades": input_count,
                     "valid_week_grades": len(grades),
                     "missing_weeks": len(set(range(1, 19)) - {grade["week"] for grade in grades}),
                     "blocked_weeks": input_count - len(grades)},
    }


def _build_season_grade(week_grades, leakage_audit):
    verify_leakage_audit(leakage_audit)
    valid_grades, rejected, integrity = [], [], isinstance(week_grades, list)
    for grade in week_grades if integrity else ():
        try:
            valid_grades.append(verify_week_grade(grade))
        except (TypeError, ValueError):
            integrity = False
            try:
                text = canonical_json(grade) + "\n"
                if _decode_json(text.encode("utf-8"), "rejected weekly grade") != grade:
                    raise ValueError("Rejected weekly grade is not canonical")
            except (TypeError, ValueError, UnicodeEncodeError) as error:
                raise ValueError("Rejected weekly grade is not finite JSON") from error
            rejected.append(text)
    valid_grades.sort(key=lambda grade: grade["week"])
    rejected.sort()
    epochs = {
        (
            grade["model_version"], grade["config_sha256"], grade["code_sha"],
            grade["position_mean_evidence_sha256"],
        )
        for grade in valid_grades
    }
    weeks = [grade["week"] for grade in valid_grades]
    if len(weeks) != len(set(weeks)):
        integrity = False
    complete = len(valid_grades) == 18 and set(weeks) == set(range(1, 19))
    common_epoch = len(epochs) == 1
    weekly_primary_pools = bool(valid_grades) and all(
        grade["metrics"]["primary"]["count"] == 96
        and sum(row["primary_pool"] for row in grade["rows"]) == 96
        and len({(row["game_id"], row["gsis_id"]) for row in grade["rows"]
                 if row["primary_pool"]}) == 96
        for grade in valid_grades
    )
    rows = [
        row for grade in valid_grades for row in grade["rows"]
        if row["primary_pool"] is True
    ]
    if not rows:
        integrity = False
    null_mae = _mae(rows, "null_prediction") if rows else None
    strong_mae = _mae(rows, "strong_prediction") if rows else None
    relative = (
        (null_mae - strong_mae) / null_mae
        if null_mae is not None and null_mae > 0.0 else 0.0
    )
    bootstrap = pgo_challenger.paired_block_bootstrap(
        _bootstrap_rows(rows), BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED
    ) if rows else None
    weekly_wins = sum(
        grade["metrics"]["primary"]["strong_win"] for grade in valid_grades
    )
    result_times = [
        (parse_timestamp(grade["result_receipt"]["captured_at"], "result capture"),
         grade["result_receipt"]["captured_at"])
        for grade in valid_grades
    ]
    latest_result = max(result_times)[1] if result_times else None
    audited_at = leakage_audit["audited_at"]
    audit_after_results = bool(
        result_times and parse_timestamp(audited_at, "leakage audited_at")
        >= max(result_times)[0]
    )
    audit_binding = _audit_matches_grades(leakage_audit, valid_grades)
    checks = {
        "season_complete": complete,
        "common_model_epoch": common_epoch,
        "weekly_primary_pools": weekly_primary_pools,
        "relative_improvement_at_least_1pct": relative >= 0.01,
        "bootstrap_lower_positive": bool(
            bootstrap is not None and bootstrap["lower"] > 0.0
        ),
        "strict_majority_weekly_wins": weekly_wins > 9,
        "leakage_audit_clean": (
            leakage_audit["verdict"] == "CLEAN" and audit_binding
        ),
        "leakage_audit_after_results": audit_after_results,
        "leakage_audit_binding": audit_binding,
        "artifact_integrity": integrity,
    }
    status = _season_status(checks)
    model_version, config_sha256, code_sha, position_mean_evidence_sha256 = (
        next(iter(epochs)) if common_epoch else (None, None, None, None)
    )
    grade = {
        "schema_version": 1,
        "artifact_kind": "PGO_FANTASY_2026_SEASON_GRADE",
        "status": status,
        "publication_status": {
            "PASS": "VALIDATED", "HOLD": "EXPERIMENTAL", "BLOCKED": "BLOCKED",
        }[status],
        "season": 2026,
        "model_version": model_version,
        "config_sha256": config_sha256,
        "code_sha": code_sha,
        "position_mean_evidence_sha256": position_mean_evidence_sha256,
        "checks": checks,
        "metrics": {
            "primary_count": len(rows), "null_mae": null_mae,
            "strong_mae": strong_mae, "relative_improvement": relative,
            "weekly_wins": weekly_wins,
        },
        "bootstrap": bootstrap,
        "leakage_audit_sha256": leakage_audit["artifact_sha256"],
        "leakage_audit_verdict": leakage_audit["verdict"],
        "leakage_audit_audited_at": audited_at,
        "latest_result_captured_at": latest_result,
        "weeks": sorted(set(weeks)),
        "week_grade_sha256": sorted(
            grade["artifact_sha256"] for grade in valid_grades
        ),
        "week_grade_bytes": [serialize_week_grade(grade) for grade in valid_grades],
        "rejected_week_grade_bytes": rejected,
        "leakage_audit_bytes": canonical_json(leakage_audit) + "\n",
        "diagnostics": _diagnostics(
            rows, valid_grades, len(valid_grades) + len(rejected)
        ),
    }
    grade["artifact_sha256"] = _artifact_hash(grade)
    return grade


def grade_season(week_grades, leakage_audit):
    verify_leakage_audit(leakage_audit)
    return verify_season_grade(_build_season_grade(week_grades, leakage_audit))


def verify_season_grade(grade):
    if not isinstance(grade, dict) or set(grade) != SEASON_GRADE_KEYS:
        raise ValueError("Season fantasy grade contract is invalid")
    if (
        type(grade["schema_version"]) is not int
        or grade["schema_version"] != 1
        or grade["artifact_kind"] != "PGO_FANTASY_2026_SEASON_GRADE"
        or grade["status"] not in {"PASS", "HOLD", "BLOCKED"}
        or grade["publication_status"] != {
            "PASS": "VALIDATED", "HOLD": "EXPERIMENTAL", "BLOCKED": "BLOCKED",
        }[grade["status"]]
        or type(grade["season"]) is not int or grade["season"] != 2026
        or not isinstance(grade["checks"], dict)
        or set(grade["checks"]) != SEASON_CHECK_KEYS
        or any(type(value) is not bool for value in grade["checks"].values())
        or not _hex_digest(grade["leakage_audit_sha256"], 64)
        or (
            grade["checks"]["common_model_epoch"]
            and not _hex_digest(grade["position_mean_evidence_sha256"], 64)
        )
        or (
            not grade["checks"]["common_model_epoch"]
            and grade["position_mean_evidence_sha256"] is not None
        )
        or grade["leakage_audit_verdict"] not in {
            "CLEAN", "REVIEW REQUIRED", "NOT CLEAN",
        }
        or not isinstance(grade["week_grade_bytes"], list)
        or not isinstance(grade["rejected_week_grade_bytes"], list)
        or not all(isinstance(text, str) for text in (
            grade["week_grade_bytes"] + grade["rejected_week_grade_bytes"]
        ))
        or not isinstance(grade["leakage_audit_bytes"], str)
        or not _hex_digest(grade["artifact_sha256"], 64)
    ):
        raise ValueError("Season fantasy grade metadata is invalid")
    try:
        grade_bytes = [text.encode("utf-8") for text in grade["week_grade_bytes"]]
        rejected_bytes = [text.encode("utf-8")
                          for text in grade["rejected_week_grade_bytes"]]
        audit_bytes = grade["leakage_audit_bytes"].encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("Season fantasy grade evidence is invalid") from error
    grades = [verify_week_grade(_decode_json(data, "weekly fantasy grade"))
              for data in grade_bytes]
    if any(data != serialize_week_grade(item).encode("utf-8")
           for data, item in zip(grade_bytes, grades)):
        raise ValueError("Season fantasy grade evidence is not canonical")
    rejected = []
    for data in rejected_bytes:
        item = _decode_json(data, "rejected weekly fantasy grade")
        if data != (canonical_json(item) + "\n").encode("utf-8"):
            raise ValueError("Season fantasy grade evidence is not canonical")
        try:
            verify_week_grade(item)
        except (TypeError, ValueError):
            rejected.append(item)
        else:
            raise ValueError("Rejected weekly fantasy grade now verifies")
    audit = verify_leakage_audit(_decode_json(audit_bytes, "prospective leakage audit"))
    if audit_bytes != (canonical_json(audit) + "\n").encode("utf-8"):
        raise ValueError("Season fantasy grade evidence is not canonical")
    expected = _build_season_grade(grades + rejected, audit)
    if not _matches_frozen_value(grade, expected):
        raise ValueError("Season fantasy grade evidence binding is invalid")
    return grade


def serialize_season_grade(grade):
    verify_season_grade(grade)
    return canonical_json(grade) + "\n"


def write_season_grade(output_dir, grade):
    output_dir = Path(output_dir)
    return pgo_prospective._write_new_outputs(output_dir, (
        (output_dir / "fantasy_season_grade.json", serialize_season_grade(grade)),
    ))


CODE_PATHS = (
    "pgo_fantasy_prospective.py", "pgo_fantasy.py", "pgo_prospective.py",
    "pgo_challenger.py", "pgo_sources.py", "pgo_model.py", "release_ratings.py",
)


def _now():
    return datetime.now().astimezone()


def _current_code_sha():
    root = Path(__file__).resolve().parent
    try:
        head = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        status = subprocess.run(
            (
                "git", "status", "--porcelain=v1", "--untracked-files=all",
                "--", *CODE_PATHS,
            ),
            cwd=root, check=True, capture_output=True, text=True,
        ).stdout
        if not _hex_digest(head, 40):
            raise ValueError("Current code SHA is invalid")
        if status.strip():
            raise ValueError("Prospective fantasy runtime code is not clean")
        tracked = subprocess.run(
            ("git", "ls-files", "--error-unmatch", "--", *CODE_PATHS),
            cwd=root, check=True, capture_output=True, text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("Unable to determine prospective fantasy runtime identity") from error
    if set(tracked) != set(CODE_PATHS):
        raise ValueError("Prospective fantasy runtime code is not fully tracked")
    return head


def _same_path(first, second):
    return Path(first).resolve(strict=False) == Path(second).resolve(strict=False)


def _require_distinct(path, protected, label):
    if any(_same_path(path, item) for item in protected):
        raise ValueError(f"{label} aliases frozen evidence")


def _require_disjoint(path, protected, label):
    resolved = Path(path).resolve(strict=False)
    if any(
        resolved == Path(item).resolve(strict=False)
        or resolved in Path(item).resolve(strict=False).parents
        or Path(item).resolve(strict=False) in resolved.parents
        for item in protected
    ):
        raise ValueError(f"{label} overlaps frozen evidence")


def _common_sources(args, availability_required):
    sources = {
        "schedule": load_snapshot(args.schedule, "schedule"),
        "roster": load_snapshot(args.roster, "roster"),
        "depth": load_snapshot(args.depth, "depth"),
        "history": load_snapshot(args.history, "history"),
    }
    if getattr(args, "availability", None) is not None:
        sources["availability"] = load_snapshot(
            args.availability, "availability"
        )
    if availability_required and "availability" not in sources:
        raise ValueError("Availability source is required")
    return sources, load_model_config(args.config)


def _blocked(mode, error):
    receipt = {
        "schema_version": 1,
        "artifact_kind": "PGO_FANTASY_BLOCKED_DIAGNOSTIC",
        "status": "BLOCKED",
        "publication_status": "BLOCKED",
        "mode": mode,
        "error_type": type(error).__name__,
        "error": str(error),
    }
    receipt["artifact_sha256"] = _artifact_hash(receipt)
    return canonical_json(receipt) + "\n"


def _write_blocked(path, mode, error, protected=()):
    _require_disjoint(path, protected, "Diagnostic output")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pgo_fantasy._exclusive_write_text(path, _blocked(mode, error))


def _runtime_matches(code_shas):
    values = set(code_shas)
    if len(values) != 1 or not _hex_digest(next(iter(values), ""), 40):
        raise ValueError("Frozen evidence does not share one runtime code epoch")
    if _current_code_sha() != next(iter(values)):
        raise ValueError("Current runtime code does not match the frozen evidence epoch")


def _parser():
    parser = argparse.ArgumentParser(
        description="Build and grade local PGO fantasy prospective evidence"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def sources(command, availability=False):
        command.add_argument("--schedule", type=Path, required=True)
        command.add_argument("--roster", type=Path, required=True)
        command.add_argument("--depth", type=Path, required=True)
        command.add_argument("--history", type=Path, required=True)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--availability", type=Path, required=availability)

    preview = commands.add_parser("preview")
    sources(preview)
    preview.add_argument("--week", type=int, required=True)
    preview.add_argument("--as-of", required=True)
    preview.add_argument("--output", type=Path, required=True)

    lock = commands.add_parser("lock")
    sources(lock, availability=True)
    lock.add_argument("--game-id", required=True)
    lock.add_argument("--output-dir", type=Path, required=True)
    lock.add_argument("--diagnostic-output", type=Path, required=True)

    week = commands.add_parser("grade-week")
    week.add_argument("--lock", type=Path, action="append", required=True)
    week.add_argument("--results", type=Path, required=True)
    week.add_argument("--output-dir", type=Path, required=True)
    week.add_argument("--diagnostic-output", type=Path, required=True)

    season = commands.add_parser("grade-season")
    season.add_argument("--week-grade", type=Path, action="append", required=True)
    season.add_argument("--leakage-audit", type=Path, required=True)
    season.add_argument("--output-dir", type=Path, required=True)
    season.add_argument("--diagnostic-output", type=Path, required=True)
    return parser


def _inputs(args):
    if args.command in {"preview", "lock"}:
        return (args.schedule, args.roster, args.depth, args.history, args.config,
                *(() if args.availability is None else (args.availability,)))
    if args.command == "grade-week":
        return (*args.lock, args.results)
    return (*args.week_grade, args.leakage_audit)


def _outputs(args):
    if args.command == "preview":
        return (args.output,)
    if args.command == "lock":
        return (args.output_dir / "fantasy_lock.json",
                args.output_dir / "fantasy_predictions.csv")
    if args.command == "grade-week":
        return (args.output_dir / "fantasy_week_grade.json",)
    return (args.output_dir / "fantasy_season_grade.json",)


def _diagnostic_protected(args, inputs, outputs):
    packages = () if args.command == "preview" else (args.output_dir,)
    return (*inputs, *(Path(path).parent for path in inputs), *outputs, *packages)


def _lock_publication_guard(lock):
    if _now() > parse_timestamp(lock["decision_time"], "decision time"):
        raise ValueError("Fantasy game lock T-60 window has closed")


def main(argv=None):
    args = _parser().parse_args(argv)
    inputs, outputs = _inputs(args), _outputs(args)
    try:
        for output in outputs:
            _require_distinct(output, inputs, "Artifact output")
        if args.command == "preview":
            sources, model = _common_sources(args, False)
            preview = build_preview(sources, model, args.week, args.as_of)
            _write_preview(args.output, serialize_preview(preview))
            return 0
        if args.command == "lock":
            sources, model = _common_sources(args, True)
            code_sha = _current_code_sha()
            locked_at = _now().isoformat()
            lock = build_game_lock(sources, model, args.game_id, locked_at, code_sha)
            _lock_publication_guard(lock)
            if not write_game_lock(
                args.output_dir, lock, lambda: _lock_publication_guard(lock)
            ):
                raise ValueError("Fantasy game lock output already exists")
            return 0
        if args.command == "grade-week":
            locks = [load_game_lock(path) for path in args.lock]
            _runtime_matches(loaded["lock"].get("code_sha") for loaded in locks)
            grade = grade_week(locks, load_results(args.results))
            if not write_week_grade(args.output_dir, grade):
                raise ValueError("Fantasy week grade output already exists")
            return 1
        grades = [load_week_grade(path) for path in args.week_grade]
        _runtime_matches(grade.get("code_sha") for grade in grades)
        grade = grade_season(grades, load_leakage_audit(args.leakage_audit))
        if not write_season_grade(args.output_dir, grade):
            raise ValueError("Fantasy season grade output already exists")
        return 0 if grade["status"] == "PASS" else 1
    except (OSError, TypeError, ValueError, json.JSONDecodeError,
            subprocess.SubprocessError) as error:
        diagnostic = getattr(args, "diagnostic_output", None)
        if diagnostic is None:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        try:
            _write_blocked(
                diagnostic, args.command, error,
                _diagnostic_protected(args, inputs, outputs),
            )
        except (OSError, TypeError, ValueError):
            return 2
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
