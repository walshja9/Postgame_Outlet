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
        or not isinstance(config["model_version"], str)
        or not config["model_version"].strip()
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
