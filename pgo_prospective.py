#!/usr/bin/env python3
"""Freeze pregame PGO predictions for a prospective, shadow-only grade."""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import tempfile
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pgo_challenger
import pgo_model
import pgo_sources
from release_ratings import atomic_write_text


SCHEMA_VERSION = 1
LOCK_STATUS = "LOCKED"
DEFAULT_OUTPUT_DIR = Path("prospective-pgo")
PREDICTION_COLUMNS = (
    "game_id", "season", "week", "kickoff", "home", "away", "game_type",
    "location", "home_rest", "away_rest", "pgo_v0_prediction",
    "challenger_prediction", "challenger_full_strength_prediction",
    "subgroup_flags",
)
BLEND_KIND = "fixed_convex_stability_blend"
BLEND_FORMULA = "0.75*pgo_v0_prediction+0.25*challenger_prediction"
BLEND_WEIGHT = 0.25
BLEND_GRID = tuple(index / 20 for index in range(21))
DEVELOPMENT_SOURCE_SHA256 = "b697b6f8f5eee9ae1efe607272458964a681f99f440a94f86d8edce2ad5a19b7"
DEVELOPMENT_ARTIFACT_SHA256 = "83815b10e621ab97ff664ed3d8006aa53da6107dacaaac5040fc1e447808ae5a"
DEVELOPMENT_GAME_COUNT = 2_127
DEVELOPMENT_SEASONS = tuple(range(2018, 2026))
DEVELOPMENT_COLUMNS = (
    "game_id", "season", "week", "kickoff", "actual_margin",
    "pgo_v0_prediction", "challenger_prediction", "changed_or_backup_qb",
    "major_availability_loss", "head_coach_change", "high_roster_turnover",
    "weeks_1_4", "weeks_5_18", "half_life_games", "alpha", "delta",
)


def _parse_datetime(value):
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid timestamp: {value}") from error
    if result.tzinfo is None:
        raise ValueError(f"Timestamp must include timezone: {value}")
    return result.astimezone(timezone.utc)


def _timestamp(value):
    _parse_datetime(value)
    return value.isoformat() if isinstance(value, datetime) else str(value).strip()


def _finite(value, label):
    try:
        value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Non-finite {label}:") from error
    if not math.isfinite(value):
        raise ValueError(f"Non-finite {label}:")
    return value


def _score_blank(value):
    return value is None or str(value).strip() == ""


def _row_kickoff(row):
    value = row.get("kickoff", "")
    if str(value).strip():
        return _timestamp(value)
    day, time = row.get("gameday", ""), row.get("gametime", "")
    if not str(day).strip():
        raise ValueError("Missing kickoff:")
    try:
        return pgo_challenger._kickoff(day, time).isoformat()
    except ValueError as error:
        raise ValueError(f"Invalid kickoff: {day} {time}") from error


def _normalize_row(row):
    game_id = str(row.get("game_id", "")).strip()
    if not game_id:
        raise ValueError("Missing game ID:")
    try:
        season, week = int(row["season"]), int(row["week"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid season/week: {game_id}") from error
    home_raw = row.get("home_team", row.get("home", ""))
    away_raw = row.get("away_team", row.get("away", ""))
    try:
        home, away = pgo_sources.normalize_team(home_raw), pgo_sources.normalize_team(away_raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid teams: {game_id}") from error
    if home == away:
        raise ValueError(f"Invalid teams: {game_id}")
    game_type = str(row.get("game_type", "REG")).strip().upper()
    if not game_type:
        raise ValueError(f"Missing game type: {game_id}")
    kickoff = _row_kickoff(row)
    def rest(name):
        try:
            value = float(row[name])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid {name}: {game_id}") from error
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid {name}: {game_id}")
        return int(value) if value.is_integer() else value
    location = str(row.get("location", "")).strip()
    if not location:
        raise ValueError(f"Missing venue: {game_id}")
    return {
        "game_id": game_id,
        "season": season,
        "week": week,
        "game_type": game_type,
        "kickoff": kickoff,
        "home_team": home,
        "away_team": away,
        "home_score": "" if row.get("home_score") is None else str(row.get("home_score")).strip(),
        "away_score": "" if row.get("away_score") is None else str(row.get("away_score")).strip(),
        "location": location,
        "home_rest": rest("home_rest"),
        "away_rest": rest("away_rest"),
        "home_coach": str(row.get("home_coach", "") or "").strip(),
        "away_coach": str(row.get("away_coach", "") or "").strip(),
    }


def load_schedule_snapshot(path):
    """Load and hash a caller-frozen schedule snapshot without fetching it."""
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames:
            raise ValueError("Schedule snapshot has no header")
        rows = [_normalize_row(row) for row in reader]
    except UnicodeDecodeError as error:
        raise ValueError("Schedule snapshot is not UTF-8 CSV") from error
    if not rows:
        raise ValueError("Schedule snapshot has no rows")
    seen = set()
    for row in rows:
        if row["game_id"] in seen:
            raise ValueError(f"Duplicate game ID: {row['game_id']}")
        seen.add(row["game_id"])
    return {"rows": rows, "sha256": hashlib.sha256(raw).hexdigest()}


def load_development_predictions(path):
    """Load the fixed historical blend-development source without changing it."""
    raw = Path(path).read_bytes()
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    except UnicodeDecodeError as error:
        raise ValueError("Development predictions are not UTF-8 CSV") from error
    if reader.fieldnames != list(DEVELOPMENT_COLUMNS):
        raise ValueError("Development predictions header mismatch")
    rows, seen = [], set()
    boolean_names = {
        "changed_or_backup_qb", "major_availability_loss", "head_coach_change",
        "high_roster_turnover", "weeks_1_4", "weeks_5_18",
    }
    integer_names = {"season", "week", "half_life_games"}
    numeric_names = {
        "actual_margin", "pgo_v0_prediction", "challenger_prediction", "alpha", "delta",
    }
    for raw_row in reader:
        if None in raw_row:
            raise ValueError("Development predictions row has extra columns")
        game_id = str(raw_row.get("game_id", "")).strip()
        if not game_id:
            raise ValueError("Development prediction game ID is missing")
        if game_id in seen:
            raise ValueError(f"Duplicate development game ID: {game_id}")
        seen.add(game_id)
        row = {"game_id": game_id, "kickoff": _timestamp(raw_row.get("kickoff", ""))}
        try:
            row.update({name: int(raw_row[name]) for name in integer_names})
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid development integer: {game_id}") from error
        row.update({name: _finite(raw_row.get(name), name) for name in numeric_names})
        for name in boolean_names:
            if raw_row.get(name) not in {"true", "false"}:
                raise ValueError(f"Invalid development boolean: {game_id}")
            row[name] = raw_row[name] == "true"
        rows.append(row)
    if not rows:
        raise ValueError("Development predictions have no rows")
    return {"rows": rows, "sha256": hashlib.sha256(raw).hexdigest()}


def _source_revisions_before_kickoff(model_state, game_id, kickoff):
    for revision in model_state.get("source_revisions", ()):
        if revision.get("game_id") not in (None, game_id):
            continue
        available = revision.get("available_at", revision.get("revised_at", ""))
        if available and _parse_datetime(available) > _parse_datetime(kickoff):
            raise ValueError(f"Post-kickoff source revision: {game_id}")


def _strict_flags(flags, game_id):
    if not isinstance(flags, dict):
        raise ValueError(f"Invalid subgroup flags: {game_id}")
    if any(type(value) is not bool for value in flags.values()):
        raise ValueError(f"Invalid subgroup flags: {game_id}")
    return {str(key): value for key, value in sorted(flags.items())}


def lock_games(schedule_snapshot, model_state, as_of):
    """Validate a pregame boundary and produce an immutable lock payload."""
    boundary = _parse_datetime(as_of)
    if not isinstance(model_state, dict):
        raise ValueError("Model state missing:")
    source_lock_sha256 = str(model_state.get("source_lock_sha256", "")).strip()
    if not source_lock_sha256:
        raise ValueError("Source lock hash missing:")
    if not isinstance(schedule_snapshot, dict) or not schedule_snapshot.get("sha256"):
        raise ValueError("Schedule snapshot hash missing:")
    rows = schedule_snapshot.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Schedule snapshot rows missing:")
    seen = set()
    predictions = model_state.get("predictions", {}) if isinstance(model_state, dict) else {}
    if not isinstance(predictions, dict):
        raise ValueError("Model predictions missing:")
    games = []
    for raw in rows:
        row = _normalize_row(raw)
        game_id = row["game_id"]
        if game_id in seen:
            raise ValueError(f"Duplicate game ID: {game_id}")
        seen.add(game_id)
        if row["game_type"] != "REG":
            continue
        if row["season"] != 2026:
            continue
        home_final, away_final = (
            not _score_blank(row["home_score"]), not _score_blank(row["away_score"])
        )
        if home_final and away_final and _parse_datetime(row["kickoff"]) <= boundary:
            continue
        if home_final or away_final:
            raise ValueError(f"Final score present: {game_id}")
        if _parse_datetime(row["kickoff"]) <= boundary:
            raise ValueError(f"Kickoff is not after lock boundary: {game_id}")
        _source_revisions_before_kickoff(model_state, game_id, row["kickoff"])
        prediction = predictions.get(game_id)
        if not isinstance(prediction, dict):
            raise ValueError(f"Missing prediction: {game_id}")
        try:
            values = {
                name: _finite(prediction.get(name), name)
                for name in (
                    "pgo_v0_prediction", "challenger_prediction",
                    "challenger_full_strength_prediction",
                )
            }
        except ValueError as error:
            raise ValueError("Non-finite prediction:") from error
        flags = prediction.get("subgroup_flags", {})
        games.append({
            "game_id": game_id,
            "season": row["season"],
            "week": row["week"],
            "kickoff": row["kickoff"],
            "home": row["home_team"],
            "away": row["away_team"],
            "game_type": row["game_type"],
            "location": row["location"],
            "home_rest": row["home_rest"],
            "away_rest": row["away_rest"],
            **values,
            "subgroup_flags": _strict_flags(flags, game_id),
        })
    games.sort(key=lambda row: (row["kickoff"], row["game_id"]))
    if not games:
        raise ValueError("No unplayed 2026 regular-season games after lock boundary")
    source_hashes = deepcopy(model_state.get("source_hashes", {}))
    body = {
        "schema_version": SCHEMA_VERSION,
        "as_of": _timestamp(as_of),
        "status": LOCK_STATUS,
        "schedule_snapshot_sha256": str(schedule_snapshot["sha256"]),
        "source_lock_sha256": source_lock_sha256,
        "source_hashes": source_hashes,
        "model_state": {
            key: deepcopy(value)
            for key, value in model_state.items()
            if key not in {"predictions", "source_revisions"}
        },
        "games": games,
    }
    body["prediction_integrity_sha256"] = _prediction_integrity_hash(games)
    body["artifact_sha256"] = _artifact_hash(body)
    return body


def _json_value(value):
    if hasattr(value, "item"):
        return _json_value(value.item())
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Lock values must be finite")
    return value


def _canonical(value):
    return json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def _artifact_hash(lock):
    payload = deepcopy(lock)
    payload.pop("artifact_sha256", None)
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _prediction_integrity_hash(games, include_candidate=False):
    keys = (
        "game_id", "pgo_v0_prediction", "challenger_prediction",
        "challenger_full_strength_prediction", "subgroup_flags",
    )
    if include_candidate:
        keys += ("candidate_prediction",)
    return hashlib.sha256(_canonical([
        {key: game[key] for key in keys}
        for game in games
    ]).encode("utf-8")).hexdigest()


def serialize_lock(lock):
    return _canonical(lock) + "\n"


def _prediction_csv(lock):
    columns = PREDICTION_COLUMNS
    if (
        lock.get("schema_version") == 2
        and isinstance(lock.get("candidate"), dict)
        and lock["candidate"].get("kind") == BLEND_KIND
    ):
        columns += ("candidate_prediction",)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for game in lock["games"]:
        row = dict(game)
        row["subgroup_flags"] = json.dumps(
            row["subgroup_flags"], sort_keys=True, separators=(",", ":")
        )
        writer.writerow({name: row.get(name, "") for name in columns})
    return output.getvalue()


def write_lock(output_dir, lock):
    output_dir = Path(output_dir)
    lock_path = output_dir / "prospective_lock.json"
    atomic_write_text(lock_path, serialize_lock(lock))
    atomic_write_text(output_dir / "prospective_predictions.csv", _prediction_csv(lock))
    return lock_path


GRADE_RESULT_COLUMNS = (
    "game_id", "season", "week", "kickoff", "home", "away", "game_type",
    "location", "home_rest", "away_rest", "pgo_v0_prediction",
    "challenger_prediction", "challenger_full_strength_prediction",
    "subgroup_flags", "home_score", "away_score", "finalized_at",
    "actual_margin", "pgo_v0_absolute_error", "challenger_absolute_error",
    "improvement",
)


def _verify_schema_one_lock(lock):
    if not isinstance(lock, dict) or lock.get("status") != LOCK_STATUS:
        raise ValueError("Lock status is not LOCKED:")
    games = lock.get("games")
    if not isinstance(games, list) or not games:
        raise ValueError("Lock games are missing:")
    seen = set()
    for game in games:
        if not isinstance(game, dict):
            raise ValueError("Invalid locked game:")
        game_id = str(game.get("game_id", "")).strip()
        if not game_id or game_id in seen:
            raise ValueError(f"Duplicate locked game: {game_id}")
        seen.add(game_id)
        if game.get("game_type") != "REG":
            raise ValueError(f"Locked game is not regular season: {game_id}")
        for name in ("home", "away", "kickoff", "location"):
            if not str(game.get(name, "")).strip():
                raise ValueError(f"Locked game metadata missing: {game_id}")
        for name in ("pgo_v0_prediction", "challenger_prediction",
                     "challenger_full_strength_prediction"):
            _finite(game.get(name), f"locked {name}")
        _strict_flags(game.get("subgroup_flags", {}), game_id)
    prediction_hash = str(lock.get("prediction_integrity_sha256", "")).strip()
    if prediction_hash and _prediction_integrity_hash(games) != prediction_hash:
        raise ValueError("Locked prediction integrity:")
    artifact_hash = str(lock.get("artifact_sha256", "")).strip()
    if not artifact_hash or _artifact_hash(lock) != artifact_hash:
        raise ValueError("Lock artifact hash mismatch:")
    return games


def _base_lock_from_derived(derived_lock):
    base = deepcopy(derived_lock)
    for name in (
        "candidate", "base_lock_artifact_sha256",
        "base_prediction_integrity_sha256",
    ):
        base.pop(name, None)
    base["schema_version"] = SCHEMA_VERSION
    for game in base.get("games", []):
        if isinstance(game, dict):
            game.pop("candidate_prediction", None)
    base["prediction_integrity_sha256"] = derived_lock.get(
        "base_prediction_integrity_sha256", ""
    )
    base["artifact_sha256"] = derived_lock.get("base_lock_artifact_sha256", "")
    return base


def _verify_lock(lock):
    if not isinstance(lock, dict):
        raise ValueError("Lock status is not LOCKED:")
    schema_version = lock.get("schema_version")
    if schema_version == SCHEMA_VERSION:
        if (
            any(name in lock for name in (
                "candidate", "base_lock_artifact_sha256",
                "base_prediction_integrity_sha256",
            ))
            or any("candidate_prediction" in game for game in lock.get("games", []) if isinstance(game, dict))
        ):
            raise ValueError("Schema-1 lock has candidate fields:")
        return _verify_schema_one_lock(lock)
    if schema_version != 2:
        raise ValueError("Lock schema mismatch:")
    candidate = lock.get("candidate")
    expected_candidate = {
        "kind": BLEND_KIND,
        "pgo_v0_weight": 0.75,
        "pgo_v1_weight": BLEND_WEIGHT,
        "formula": BLEND_FORMULA,
    }
    if not isinstance(candidate, dict) or set(candidate) != {
        *expected_candidate, "as_of", "development_receipt_sha256",
    } or any(candidate.get(name) != value for name, value in expected_candidate.items()):
        raise ValueError("Derived candidate mismatch:")
    try:
        candidate_as_of = _timestamp(candidate["as_of"])
    except (KeyError, ValueError) as error:
        raise ValueError("Derived candidate timestamp:") from error
    receipt_hash = candidate.get("development_receipt_sha256", "")
    if not _is_sha256(receipt_hash):
        raise ValueError("Derived development receipt hash:")
    base = _base_lock_from_derived(lock)
    _verify_lock(base)
    if lock.get("base_lock_artifact_sha256") != base["artifact_sha256"]:
        raise ValueError("Derived base artifact hash:")
    if lock.get("base_prediction_integrity_sha256") != base["prediction_integrity_sha256"]:
        raise ValueError("Derived base prediction hash:")
    games = lock["games"]
    for game in games:
        if _parse_datetime(candidate_as_of) >= _parse_datetime(game["kickoff"]):
            raise ValueError("Candidate timestamp is not before kickoff:")
        try:
            prediction = _finite(game["candidate_prediction"], "candidate prediction")
        except (KeyError, ValueError) as error:
            raise ValueError("Derived candidate prediction:") from error
        if prediction != _blend_prediction(
            game["pgo_v0_prediction"], game["challenger_prediction"]
        ):
            raise ValueError("Derived candidate prediction:")
    if lock.get("prediction_integrity_sha256") != _prediction_integrity_hash(
        games, include_candidate=True
    ):
        raise ValueError("Derived prediction integrity:")
    if not _is_sha256(lock.get("artifact_sha256", "")) or _artifact_hash(lock) != lock["artifact_sha256"]:
        raise ValueError("Lock artifact hash mismatch:")
    return games


def derive_stability_blend(base_lock, development_receipt, development_file_sha256, as_of):
    _verify_lock(base_lock)
    _verify_development_receipt(development_receipt)
    receipt_bytes = (_canonical(development_receipt) + "\n").encode("utf-8")
    if development_file_sha256 != hashlib.sha256(receipt_bytes).hexdigest():
        raise ValueError("Development receipt file hash mismatch")
    candidate_as_of = _timestamp(as_of)
    derived = deepcopy(base_lock)
    derived["schema_version"] = 2
    derived["base_lock_artifact_sha256"] = base_lock["artifact_sha256"]
    derived["base_prediction_integrity_sha256"] = base_lock["prediction_integrity_sha256"]
    derived["candidate"] = {
        "kind": BLEND_KIND,
        "as_of": candidate_as_of,
        "pgo_v0_weight": 0.75,
        "pgo_v1_weight": BLEND_WEIGHT,
        "formula": BLEND_FORMULA,
        "development_receipt_sha256": development_file_sha256,
    }
    for game in derived["games"]:
        game["candidate_prediction"] = _blend_prediction(
            game["pgo_v0_prediction"], game["challenger_prediction"]
        )
    derived["prediction_integrity_sha256"] = _prediction_integrity_hash(
        derived["games"], include_candidate=True
    )
    derived["artifact_sha256"] = _artifact_hash(derived)
    _verify_lock(derived)
    return derived


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def build_prospective_attestation(
    base_lock, base_lock_bytes, base_prediction_bytes, derived_lock,
    derived_lock_bytes, derived_prediction_bytes, development_receipt_bytes,
):
    _verify_lock(base_lock)
    _verify_lock(derived_lock)
    if (
        base_lock_bytes != serialize_lock(base_lock).encode("utf-8")
        or hashlib.sha256(development_receipt_bytes).hexdigest()
        != derived_lock["candidate"]["development_receipt_sha256"]
        or _base_lock_from_derived(derived_lock) != base_lock
        or base_prediction_bytes != _prediction_csv(base_lock).encode("utf-8")
        or derived_lock_bytes != serialize_lock(derived_lock).encode("utf-8")
        or derived_prediction_bytes != _prediction_csv(derived_lock).encode("utf-8")
    ):
        raise ValueError("Attestation input bytes mismatch")
    attestation = {
        "schema_version": SCHEMA_VERSION,
        "status": LOCK_STATUS,
        "candidate": {
            "kind": BLEND_KIND,
            "as_of": derived_lock["candidate"]["as_of"],
        },
        "earliest_kickoff": min(
            base_lock["games"], key=lambda game: _parse_datetime(game["kickoff"])
        )["kickoff"],
        "development_receipt_file_sha256": hashlib.sha256(
            development_receipt_bytes
        ).hexdigest(),
        "base": {
            "lock_artifact_sha256": base_lock["artifact_sha256"],
            "lock_file_sha256": hashlib.sha256(base_lock_bytes).hexdigest(),
            "prediction_integrity_sha256": base_lock["prediction_integrity_sha256"],
            "predictions_file_sha256": hashlib.sha256(base_prediction_bytes).hexdigest(),
        },
        "derived": {
            "lock_artifact_sha256": derived_lock["artifact_sha256"],
            "lock_file_sha256": hashlib.sha256(derived_lock_bytes).hexdigest(),
            "prediction_integrity_sha256": derived_lock["prediction_integrity_sha256"],
            "predictions_file_sha256": hashlib.sha256(derived_prediction_bytes).hexdigest(),
        },
    }
    attestation["artifact_sha256"] = _artifact_hash(attestation)
    return _verify_prospective_attestation(attestation)


def _verify_prospective_attestation(attestation):
    expected_keys = {
        "schema_version", "status", "candidate", "earliest_kickoff",
        "development_receipt_file_sha256", "base", "derived", "artifact_sha256",
    }
    if not isinstance(attestation, dict) or set(attestation) != expected_keys:
        raise ValueError("Attestation schema mismatch")
    candidate = attestation["candidate"]
    if (
        attestation["schema_version"] != SCHEMA_VERSION
        or attestation["status"] != LOCK_STATUS
        or not isinstance(candidate, dict)
        or set(candidate) != {"kind", "as_of"}
        or candidate["kind"] != BLEND_KIND
    ):
        raise ValueError("Attestation status mismatch")
    try:
        candidate_as_of = _parse_datetime(candidate["as_of"])
        earliest_kickoff = _parse_datetime(attestation["earliest_kickoff"])
    except ValueError as error:
        raise ValueError("Attestation timestamp mismatch") from error
    if candidate_as_of >= earliest_kickoff:
        raise ValueError("Attestation candidate timestamp:")
    for name in ("development_receipt_file_sha256", "artifact_sha256"):
        if not _is_sha256(attestation[name]):
            raise ValueError("Attestation hash mismatch")
    for name in ("base", "derived"):
        section = attestation[name]
        if not isinstance(section, dict) or set(section) != {
            "lock_artifact_sha256", "lock_file_sha256",
            "prediction_integrity_sha256", "predictions_file_sha256",
        } or not all(_is_sha256(value) for value in section.values()):
            raise ValueError("Attestation hash mismatch")
    if _artifact_hash(attestation) != attestation["artifact_sha256"]:
        raise ValueError("Attestation artifact hash mismatch")
    return attestation


def _verify_grade_attestation(lock, lock_bytes, attestation):
    _verify_prospective_attestation(attestation)
    if not isinstance(lock_bytes, bytes):
        raise ValueError("Grade attestation lock bytes mismatch")
    base = _base_lock_from_derived(lock)
    base_lock_bytes = serialize_lock(base).encode("utf-8")
    base_prediction_bytes = _prediction_csv(base).encode("utf-8")
    derived_lock_bytes = serialize_lock(lock).encode("utf-8")
    derived_prediction_bytes = _prediction_csv(lock).encode("utf-8")
    expected_base = {
        "lock_artifact_sha256": base["artifact_sha256"],
        "lock_file_sha256": hashlib.sha256(base_lock_bytes).hexdigest(),
        "prediction_integrity_sha256": base["prediction_integrity_sha256"],
        "predictions_file_sha256": hashlib.sha256(base_prediction_bytes).hexdigest(),
    }
    expected_derived = {
        "lock_artifact_sha256": lock["artifact_sha256"],
        "lock_file_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "prediction_integrity_sha256": lock["prediction_integrity_sha256"],
        "predictions_file_sha256": hashlib.sha256(derived_prediction_bytes).hexdigest(),
    }
    if (
        lock_bytes != derived_lock_bytes
        or attestation["candidate"] != {
            "kind": lock["candidate"]["kind"],
            "as_of": lock["candidate"]["as_of"],
        }
        or attestation["development_receipt_file_sha256"]
        != lock["candidate"]["development_receipt_sha256"]
        or attestation["earliest_kickoff"] != min(
            lock["games"], key=lambda game: _parse_datetime(game["kickoff"])
        )["kickoff"]
        or attestation["base"] != expected_base
        or attestation["derived"] != expected_derived
    ):
        raise ValueError("Grade attestation mismatch")
    return attestation


def _normalize_result(result):
    if not isinstance(result, dict):
        raise ValueError("Invalid result row:")
    game_id = str(result.get("game_id", "")).strip()
    if not game_id:
        raise ValueError("Missing result game ID:")
    if not str(result.get("kickoff", "")).strip():
        raise ValueError(f"Missing result kickoff: {game_id}")
    if not str(result.get("game_type", "")).strip():
        raise ValueError(f"Missing result game type: {game_id}")
    try:
        home = pgo_sources.normalize_team(
            result.get("home_team", result.get("home", ""))
        )
        away = pgo_sources.normalize_team(
            result.get("away_team", result.get("away", ""))
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid result teams: {game_id}") from error
    finalized_at = str(result.get("finalized_at", "") or "").strip()
    if not finalized_at:
        raise ValueError(f"Result not finalized: {game_id}")
    try:
        finalized_at = _timestamp(finalized_at)
    except ValueError as error:
        raise ValueError(f"Result not finalized: {game_id}") from error
    scores = {}
    for name in ("home_score", "away_score"):
        value = result.get(name)
        try:
            value = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Result not finalized: {game_id}") from error
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Result not finalized: {game_id}")
        scores[name] = int(value) if value.is_integer() else value
    normalized = {
        "game_id": game_id,
        "home_team": home,
        "away_team": away,
        "home_score": scores["home_score"],
        "away_score": scores["away_score"],
        "finalized_at": finalized_at,
    }
    for name in ("season", "week"):
        if str(result.get(name, "")).strip():
            try:
                normalized[name] = int(result[name])
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid result {name}: {game_id}") from error
    normalized["kickoff"] = _timestamp(result["kickoff"])
    normalized["game_type"] = str(result["game_type"]).strip().upper()
    return normalized


def _result_hash(rows):
    return hashlib.sha256(_canonical(rows).encode("utf-8")).hexdigest()


def grade_locked_games(lock, results, *, attestation=None, lock_bytes=None):
    """Validate finalized results and grade the immutable prospective lock."""
    games = _verify_lock(lock)
    candidate_grade = (
        lock.get("schema_version") == 2
        and isinstance(lock.get("candidate"), dict)
        and lock["candidate"].get("kind") == BLEND_KIND
    )
    if candidate_grade:
        _verify_grade_attestation(lock, lock_bytes, attestation)
    if not isinstance(results, list):
        raise ValueError("Results must be a list:")
    locked_by_id = {game["game_id"]: game for game in games}
    result_by_id = {}
    normalized_results = []
    for raw in results:
        if isinstance(raw, dict) and candidate_grade and str(raw.get("status", "")).strip().upper() in {
            "CANCELLED", "CANCELED", "FORFEIT", "FORFEITED", "POSTPONED",
        }:
            raise ValueError(f"Candidate result status: {raw.get('game_id', '')}")
        result = _normalize_result(raw)
        game_id = result["game_id"]
        if game_id in result_by_id:
            raise ValueError(f"Duplicate result: {game_id}")
        if game_id not in locked_by_id:
            raise ValueError(f"Unexpected result: {game_id}")
        locked = locked_by_id[game_id]
        if result["home_team"] != locked["home"]:
            raise ValueError(f"locked home team: {game_id}")
        if result["away_team"] != locked["away"]:
            raise ValueError(f"locked away team: {game_id}")
        if _parse_datetime(result["kickoff"]) != _parse_datetime(locked["kickoff"]):
            raise ValueError(f"locked kickoff: {game_id}")
        if result["game_type"] != locked["game_type"]:
            raise ValueError(f"locked game type: {game_id}")
        for name in ("season", "week"):
            if name in result and result[name] != locked[name]:
                raise ValueError(f"locked {name}: {game_id}")
        result_by_id[game_id] = result
        normalized_results.append(result)
    missing = sorted(set(locked_by_id) - set(result_by_id))
    if missing:
        raise ValueError(f"Missing locked result: {missing[0]}")
    normalized_results.sort(key=lambda row: row["game_id"])

    rows = []
    for locked in sorted(games, key=lambda game: (game["kickoff"], game["game_id"])):
        result = result_by_id[locked["game_id"]]
        actual = float(result["home_score"] - result["away_score"])
        row = {
            **locked,
            "home_score": result["home_score"],
            "away_score": result["away_score"],
            "finalized_at": result["finalized_at"],
            "actual_margin": actual,
        }
        row["pgo_v0_absolute_error"] = abs(actual - row["pgo_v0_prediction"])
        row["challenger_absolute_error"] = abs(actual - row["challenger_prediction"])
        row["improvement"] = row["pgo_v0_absolute_error"] - row["challenger_absolute_error"]
        if candidate_grade:
            row["candidate_absolute_error"] = abs(actual - row["candidate_prediction"])
            row["candidate_improvement_vs_pgo_v0"] = (
                row["pgo_v0_absolute_error"] - row["candidate_absolute_error"]
            )
            row["candidate_improvement_vs_challenger"] = (
                row["challenger_absolute_error"] - row["candidate_absolute_error"]
            )
        row.update(row["subgroup_flags"])
        rows.append(row)

    if candidate_grade:
        pgo_v0 = pgo_challenger.metric_summary(rows, "pgo_v0_prediction")
        challenger = pgo_challenger.metric_summary(rows, "challenger_prediction")
        candidate = pgo_challenger.metric_summary(rows, "candidate_prediction")
        comparison = _comparison_rows(rows, "pgo_v0_prediction", "candidate_prediction")
        improvement = pgo_challenger.paired_block_bootstrap(
            comparison, samples=10_000, seed=20260721
        )
        subgroups = pgo_challenger.subgroup_results(comparison)
        candidate_vs_challenger = pgo_challenger.paired_block_bootstrap(
            _comparison_rows(rows, "challenger_prediction", "candidate_prediction"),
            samples=10_000, seed=20260721,
        )
        checks = {
            "lock_artifact_integrity": True,
            "result_integrity": True,
            "counts_match": len(rows) == len(games),
            "candidate_mae_lower": candidate["mae"] < pgo_v0["mae"],
            "aggregate_improvement_ci_positive": improvement["lower"] > 0.0,
            "no_sufficient_subgroup_regression": pgo_challenger._subgroup_gate_passes(subgroups),
        }
        integrity = ("lock_artifact_integrity", "result_integrity", "counts_match")
        status = (
            "BLOCKED" if not all(checks[name] for name in integrity)
            else "PASS" if all(checks.values()) else "HOLD"
        )
        feature_state = lock.get("model_state", {}).get("challenger", {})
        return {
            "schema_version": 2,
            "candidate": deepcopy(lock["candidate"]),
            "status": status,
            "publication_status": {"PASS": "VALIDATED", "HOLD": "EXPERIMENTAL", "BLOCKED": "BLOCKED"}[status],
            "as_of": lock.get("as_of"),
            "lock_sha256": lock["artifact_sha256"],
            "results_sha256": _result_hash(normalized_results),
            "schedule_snapshot_sha256": lock.get("schedule_snapshot_sha256"),
            "source_lock_sha256": lock.get("source_lock_sha256"),
            "source_hashes": deepcopy(lock.get("source_hashes", {})),
            "feature_manifest": {
                "features": list(feature_state.get("feature_names", [])),
                "missingness_flags": list(feature_state.get("missing_features", [])),
            },
            "counts": {"locked_games": len(games), "graded_games": len(rows)},
            "metrics": {
                "pgo_v0": pgo_v0, "challenger": challenger, "candidate": candidate,
                "pgo_v0_mae": pgo_v0["mae"], "challenger_mae": challenger["mae"],
                "candidate_mae": candidate["mae"],
            },
            "bootstrap": improvement,
            "aggregate_interval": improvement,
            "candidate_vs_challenger_interval": candidate_vs_challenger,
            "subgroup_results": subgroups,
            "checks": checks,
            "failed_checks": sorted(name for name, passed in checks.items() if not passed),
            "rows": rows,
        }

    pgo_v0 = pgo_challenger.metric_summary(rows, "pgo_v0_prediction")
    challenger = pgo_challenger.metric_summary(rows, "challenger_prediction")
    improvement = pgo_challenger.paired_block_bootstrap(
        rows, samples=10_000, seed=20260721
    )
    subgroups = pgo_challenger.subgroup_results(rows)
    checks = {
        "lock_artifact_integrity": True,
        "result_integrity": True,
        "counts_match": len(rows) == len(games),
        "challenger_mae_lower": challenger["mae"] < pgo_v0["mae"],
        "aggregate_improvement_ci_positive": improvement["lower"] > 0.0,
        "no_sufficient_subgroup_regression": pgo_challenger._subgroup_gate_passes(subgroups),
    }
    integrity = ("lock_artifact_integrity", "result_integrity", "counts_match")
    status = (
        "BLOCKED" if not all(checks[name] for name in integrity)
        else "PASS" if all(checks.values()) else "HOLD"
    )
    feature_state = lock.get("model_state", {}).get("challenger", {})
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "publication_status": {"PASS": "VALIDATED", "HOLD": "EXPERIMENTAL", "BLOCKED": "BLOCKED"}[status],
        "as_of": lock.get("as_of"),
        "lock_sha256": lock["artifact_sha256"],
        "results_sha256": _result_hash(normalized_results),
        "schedule_snapshot_sha256": lock.get("schedule_snapshot_sha256"),
        "source_lock_sha256": lock.get("source_lock_sha256"),
        "source_hashes": deepcopy(lock.get("source_hashes", {})),
        "feature_manifest": {
            "features": list(feature_state.get("feature_names", [])),
            "missingness_flags": list(feature_state.get("missing_features", [])),
        },
        "counts": {"locked_games": len(games), "graded_games": len(rows)},
        "metrics": {
            "pgo_v0": pgo_v0, "challenger": challenger,
            "pgo_v0_mae": pgo_v0["mae"], "challenger_mae": challenger["mae"],
        },
        "bootstrap": improvement,
        "aggregate_interval": improvement,
        "subgroup_results": subgroups,
        "checks": checks,
        "failed_checks": sorted(name for name, passed in checks.items() if not passed),
        "rows": rows,
    }
    return receipt


def serialize_grade(receipt, rows):
    receipt_text = _canonical(receipt) + "\n"
    output = io.StringIO(newline="")
    columns = GRADE_RESULT_COLUMNS
    if (
        receipt.get("schema_version") == 2
        and isinstance(receipt.get("candidate"), dict)
        and receipt["candidate"].get("kind") == BLEND_KIND
    ):
        columns += (
            "candidate_absolute_error", "candidate_improvement_vs_pgo_v0",
            "candidate_improvement_vs_challenger",
        )
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        item = dict(row)
        item["subgroup_flags"] = json.dumps(
            {name: bool(row.get(name)) for name in pgo_challenger.SUBGROUPS},
            sort_keys=True, separators=(",", ":"),
        )
        writer.writerow({name: item.get(name, "") for name in columns})
    return receipt_text, output.getvalue()


def write_grade(output_dir, receipt, rows):
    output_dir = Path(output_dir)
    receipt_text, results_text = serialize_grade(receipt, rows)
    receipt_path = output_dir / "prospective_receipt.json"
    atomic_write_text(receipt_path, receipt_text)
    atomic_write_text(output_dir / "prospective_results.csv", results_text)
    return receipt_path


def _blend_prediction(pgo_v0, challenger, weight=BLEND_WEIGHT):
    return (1.0 - weight) * float(pgo_v0) + weight * float(challenger)


def _comparison_rows(rows, incumbent_key, candidate_key):
    return [
        {
            **row,
            "pgo_v0_prediction": row[incumbent_key],
            "challenger_prediction": row[candidate_key],
        }
        for row in rows
    ]


def _season_results(incumbent, candidate):
    incumbent_by_season = {row["season"]: row for row in incumbent["seasons"]}
    return [
        {
            "season": row["season"],
            "pgo_v0_mae": incumbent_by_season[row["season"]]["mae"],
            "candidate_mae": row["mae"],
            "improvement": incumbent_by_season[row["season"]]["mae"] - row["mae"],
        }
        for row in candidate["seasons"]
    ]


def _grid_result(rows, incumbent, weight):
    candidate_rows = [
        {**row, "candidate_prediction": _blend_prediction(
            row["pgo_v0_prediction"], row["challenger_prediction"], weight
        )}
        for row in rows
    ]
    candidate = pgo_challenger.metric_summary(candidate_rows, "candidate_prediction")
    return {
        "pgo_v1_weight": weight,
        "metrics": {
            "pgo_v0_mae": incumbent["mae"],
            "candidate_mae": candidate["mae"],
            "improvement": incumbent["mae"] - candidate["mae"],
        },
        "season_results": _season_results(incumbent, candidate),
        "rows": candidate_rows,
    }


def _selection_from_grid(grid_results):
    eligible = [
        row for row in grid_results
        if row["pgo_v1_weight"] > 0.0
        and all(item["improvement"] > 0.0 for item in row["season_results"])
    ]
    if not eligible:
        raise ValueError("No development blend improves every season")
    selected = max(eligible, key=lambda row: row["pgo_v1_weight"])
    regressing = next((
        row["pgo_v1_weight"] for row in grid_results
        if row["pgo_v1_weight"] > selected["pgo_v1_weight"]
        and any(item["improvement"] <= 0.0 for item in row["season_results"])
    ), None)
    if regressing is None:
        raise ValueError("Development grid has no regressing weight")
    return selected, regressing


def develop_stability_blend(source):
    if not isinstance(source, dict) or source.get("sha256") != DEVELOPMENT_SOURCE_SHA256:
        raise ValueError("Development source hash mismatch")
    rows = source.get("rows")
    if not isinstance(rows, list) or len(rows) != DEVELOPMENT_GAME_COUNT:
        raise ValueError("Development source game count mismatch")
    if tuple(sorted({row.get("season") for row in rows})) != DEVELOPMENT_SEASONS:
        raise ValueError("Development source seasons mismatch")
    incumbent = pgo_challenger.metric_summary(rows, "pgo_v0_prediction")
    grid = [_grid_result(rows, incumbent, weight) for weight in BLEND_GRID]
    selected, first_regressing = _selection_from_grid(grid)
    comparison = _comparison_rows(
        selected.pop("rows"), "pgo_v0_prediction", "candidate_prediction"
    )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "status": "DEVELOPMENT_ONLY",
        "candidate": {
            "kind": BLEND_KIND,
            "formula": BLEND_FORMULA,
            "pgo_v1_weight": BLEND_WEIGHT,
        },
        "source_sha256": source["sha256"],
        "counts": {"games": len(rows), "seasons": len(DEVELOPMENT_SEASONS)},
        "seasons": list(DEVELOPMENT_SEASONS),
        "selection": {
            "selected_pgo_v1_weight": selected["pgo_v1_weight"],
            "first_regressing_weight": first_regressing,
        },
        "metrics": deepcopy(selected["metrics"]),
        "aggregate_interval": pgo_challenger.paired_block_bootstrap(
            comparison, samples=10_000, seed=20260721
        ),
        "season_results": deepcopy(selected["season_results"]),
        "grid_results": [{key: value for key, value in row.items() if key != "rows"} for row in grid],
    }
    receipt["artifact_sha256"] = _artifact_hash(receipt)
    return receipt


def _verify_development_receipt(receipt):
    expected_keys = {
        "schema_version", "status", "candidate", "source_sha256", "counts", "seasons",
        "selection", "metrics", "aggregate_interval", "season_results", "grid_results",
        "artifact_sha256",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        raise ValueError("Development receipt schema mismatch")
    if receipt["schema_version"] != SCHEMA_VERSION or receipt["status"] != "DEVELOPMENT_ONLY":
        raise ValueError("Development receipt status mismatch")
    if receipt["candidate"] != {
        "kind": BLEND_KIND, "formula": BLEND_FORMULA, "pgo_v1_weight": BLEND_WEIGHT,
    }:
        raise ValueError("Development receipt candidate mismatch")
    if receipt["source_sha256"] != DEVELOPMENT_SOURCE_SHA256:
        raise ValueError("Development receipt source mismatch")
    if receipt["counts"] != {"games": DEVELOPMENT_GAME_COUNT, "seasons": len(DEVELOPMENT_SEASONS)}:
        raise ValueError("Development receipt counts mismatch")
    if receipt["seasons"] != list(DEVELOPMENT_SEASONS):
        raise ValueError("Development receipt seasons mismatch")
    grid = receipt["grid_results"]
    if not isinstance(grid, list) or [row.get("pgo_v1_weight") for row in grid] != list(BLEND_GRID):
        raise ValueError("Development receipt grid mismatch")
    try:
        selected, first_regressing = _selection_from_grid(grid)
        finite_values = [
            *receipt["metrics"].values(), *receipt["aggregate_interval"].values(),
            *(value for row in receipt["season_results"] for value in row.values() if row is not None),
            *(item for row in grid for item in row["metrics"].values()),
            *(value for row in grid for item in row["season_results"] for value in item.values()),
        ]
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Development receipt metrics mismatch") from error
    if not all(math.isfinite(float(value)) for value in finite_values):
        raise ValueError("Development receipt metrics must be finite")
    if receipt["selection"] != {
        "selected_pgo_v1_weight": selected["pgo_v1_weight"],
        "first_regressing_weight": first_regressing,
    }:
        raise ValueError("Development receipt selection mismatch")
    if receipt["metrics"] != selected["metrics"] or receipt["season_results"] != selected["season_results"]:
        raise ValueError("Development receipt selected metrics mismatch")
    if receipt["selection"]["selected_pgo_v1_weight"] != BLEND_WEIGHT:
        raise ValueError("Development receipt blend weight mismatch")
    if (
        receipt.get("artifact_sha256") != DEVELOPMENT_ARTIFACT_SHA256
        or _artifact_hash(receipt) != receipt["artifact_sha256"]
    ):
        raise ValueError("Development receipt artifact hash mismatch")
    return receipt


def write_development_receipt(path, receipt):
    _verify_development_receipt(receipt)
    path = Path(path)
    atomic_write_text(path, _canonical(receipt) + "\n")
    return path


def _load_results(path):
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("Results CSV has no header")
            return list(reader)
    except (OSError, csv.Error) as error:
        raise ValueError(f"Unable to read results CSV: {path}") from error


def _blocked_receipt(lock, results_path, error):
    lock = lock if isinstance(lock, dict) else {}
    try:
        results_hash = hashlib.sha256(Path(results_path).read_bytes()).hexdigest()
    except OSError:
        results_hash = ""
    checks = {
        "lock_artifact_integrity": False,
        "result_integrity": False,
        "counts_match": False,
        "challenger_mae_lower": False,
        "aggregate_improvement_ci_positive": False,
        "no_sufficient_subgroup_regression": False,
    }
    if (
        lock.get("schema_version") == 2
        and isinstance(lock.get("candidate"), dict)
        and lock["candidate"].get("kind") == BLEND_KIND
    ):
        checks.pop("challenger_mae_lower")
        checks["candidate_mae_lower"] = False
        return {
            "schema_version": 2,
            "candidate": deepcopy(lock["candidate"]),
            "status": "BLOCKED",
            "publication_status": "BLOCKED",
            "as_of": lock.get("as_of"),
            "lock_sha256": lock.get("artifact_sha256", ""),
            "results_sha256": results_hash,
            "schedule_snapshot_sha256": lock.get("schedule_snapshot_sha256"),
            "source_lock_sha256": lock.get("source_lock_sha256"),
            "source_hashes": deepcopy(lock.get("source_hashes", {})),
            "feature_manifest": {},
            "counts": {"locked_games": len(lock.get("games", [])) if isinstance(lock.get("games"), list) else 0, "graded_games": 0},
            "metrics": {},
            "bootstrap": {},
            "aggregate_interval": {},
            "candidate_vs_challenger_interval": {},
            "subgroup_results": {},
            "checks": checks,
            "failed_checks": sorted(checks),
            "error": str(error),
            "rows": [],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "BLOCKED",
        "publication_status": "BLOCKED",
        "as_of": lock.get("as_of"),
        "lock_sha256": lock.get("artifact_sha256", ""),
        "results_sha256": results_hash,
        "schedule_snapshot_sha256": lock.get("schedule_snapshot_sha256"),
        "source_lock_sha256": lock.get("source_lock_sha256"),
        "source_hashes": deepcopy(lock.get("source_hashes", {})),
        "feature_manifest": {},
        "counts": {"locked_games": len(lock.get("games", [])) if isinstance(lock.get("games"), list) else 0, "graded_games": 0},
        "metrics": {},
        "bootstrap": {},
        "aggregate_interval": {},
        "subgroup_results": {},
        "checks": checks,
        "failed_checks": sorted(checks),
        "error": str(error),
        "rows": [],
    }


def _snapshot_states_with_schedule(paths, schedule_rows, as_of, half_life, context, inputs):
    as_of_dt = pgo_challenger._parse_datetime(as_of)
    as_of_year = as_of_dt.astimezone(pgo_challenger.EASTERN).year
    available_periods, completed_current_teams = set(), set()
    for game in pgo_challenger._load_games(paths):
        if game["kickoff_dt"] < as_of_dt:
            available_periods.update({
                (game["season"], game["week"], game["home"]),
                (game["season"], game["week"], game["away"]),
            })
            if game["season"] == as_of_year:
                completed_current_teams.update((game["home"], game["away"]))
    scheduled_coaches = {}
    for row in schedule_rows:
        if row["game_type"] != "REG" or row["season"] != as_of_year:
            continue
        kickoff = pgo_challenger._parse_datetime(row["kickoff"])
        for team, coach in (
            (row["home_team"], row.get("home_coach", "")),
            (row["away_team"], row.get("away_coach", "")),
        ):
            candidate = (kickoff, row["game_id"], coach)
            if team not in scheduled_coaches or candidate < scheduled_coaches[team]:
                scheduled_coaches[team] = candidate
    periods = {}
    for season, week, team in inputs["rosters"]:
        key = (season, week, team)
        available = key in available_periods or (
            key in inputs["current_roster_periods"] and season == as_of_year
        )
        if available and (team not in periods or (season, week) > periods[team]):
            periods[team] = (season, week)
    states, metadata = {}, {}
    for team in sorted(context["seen_teams"] | set(periods)):
        season, week = periods.get(team, (as_of_year, 0))
        coach = context["coaches"].get(team, "")
        if team not in completed_current_teams and team in scheduled_coaches:
            coach = scheduled_coaches[team][2]
        full, current, team_metadata = pgo_challenger._team_views(
            team, season, week, coach, as_of_dt, context, inputs
        )
        states[team] = (full, current)
        metadata[team] = team_metadata
    return states, metadata


def _prospective_turnover_flags(historical_rows, historical_metadata, future_rows, future_metadata):
    del historical_rows, historical_metadata
    flags, _ = pgo_challenger._frozen_turnover_flags(
        list(future_rows), future_metadata
    )
    return {row.game_id: flags[row.game_id] for row in future_rows}


def fit_model_state(paths, as_of, schedule_rows):
    """Fit the existing challenger state and return serializable model inputs."""
    parameters = pgo_challenger.select_parameters(paths, pgo_challenger.OUTER_SEASONS)
    historical_rows, historical_context, _ = pgo_challenger._walk(
        paths, parameters.half_life_games
    )
    training = [row for row in historical_rows if row.season <= pgo_challenger.LAST_SEASON]
    if not training:
        raise ValueError("Final training rows must not be empty")
    feature_names = tuple(sorted(training[0].features))
    preprocessor = pgo_challenger.fit_preprocessor(training, feature_names)
    coefficients = pgo_challenger.fit_huber_ridge(
        preprocessor.transform(training),
        [row.actual_margin for row in training],
        parameters.alpha, parameters.delta,
    )
    _, context, inputs = pgo_challenger._walk(
        paths, parameters.half_life_games,
        as_of=pgo_challenger._parse_datetime(as_of),
    )
    snapshot_states, snapshot_metadata = _snapshot_states_with_schedule(
        paths, schedule_rows, as_of, parameters.half_life_games, context, inputs
    )
    v0_parameters, v0_ratings = _fit_v0_state(paths)
    boundary = pgo_challenger._parse_datetime(as_of)
    predictions, future_rows, future_metadata = {}, [], {}
    for row in schedule_rows:
        if row["season"] != 2026 or row["game_type"] != "REG":
            continue
        if not (
            _score_blank(row.get("home_score"))
            and _score_blank(row.get("away_score"))
            and pgo_challenger._parse_datetime(row["kickoff"]) > boundary
        ):
            continue
        home_state = snapshot_states.get(row["home_team"])
        away_state = snapshot_states.get(row["away_team"])
        if not home_state or not away_state:
            raise ValueError(f"Missing snapshot state: {row['game_id']}")
        game = {
            "home": row["home_team"], "away": row["away_team"],
            "neutral": row["location"].strip().lower() == "neutral",
            "home_rest": row["home_rest"], "away_rest": row["away_rest"],
        }
        home_full, home_current = home_state
        away_full, away_current = away_state
        def model_prediction(features):
            feature_row = pgo_challenger.FeatureRow(
                row["game_id"], row["season"], row["week"], row["kickoff"],
                0.0, features, {},
            )
            return float(pgo_challenger.predict(
                preprocessor.transform([feature_row]), coefficients
            )[0])
        current_prediction = model_prediction(
            pgo_challenger._matchup_features(home_current, away_current, game)
        )
        full_prediction = model_prediction(
            pgo_challenger._matchup_features(home_full, away_full, game)
        )
        home_full_prediction = model_prediction(
            pgo_challenger._matchup_features(home_full, away_current, game)
        )
        away_full_prediction = model_prediction(
            pgo_challenger._matchup_features(home_current, away_full, game)
        )
        home_coach, away_coach = row.get("home_coach", ""), row.get("away_coach", "")
        head_coach_change = any(
            coach and context["coaches"].get(team) and coach != context["coaches"].get(team)
            for team, coach in (
                (row["home_team"], home_coach), (row["away_team"], away_coach)
            )
        )
        home_qb = home_current.get("qb_current_minus_full")
        away_qb = away_current.get("qb_current_minus_full")
        home_starter = snapshot_metadata[row["home_team"]].get("starter")
        away_starter = snapshot_metadata[row["away_team"]].get("starter")
        prior_starter = context.get("prior_starter", {})
        starter_changed = any(
            starter is not None
            and prior_starter.get(team) is not None
            and starter != prior_starter.get(team)
            for team, starter in (
                (row["home_team"], home_starter), (row["away_team"], away_starter)
            )
        )
        future_rows.append(pgo_challenger.FeatureRow(
            row["game_id"], row["season"], row["week"], row["kickoff"],
            0.0, {}, {},
        ))
        future_metadata[row["game_id"]] = {
            "home_team": row["home_team"], "away_team": row["away_team"],
            "home_returning_snap_share": snapshot_metadata[row["home_team"]].get("returning_snap_share"),
            "away_returning_snap_share": snapshot_metadata[row["away_team"]].get("returning_snap_share"),
        }
        predictions[row["game_id"]] = {
            "pgo_v0_prediction": float(
                v0_ratings.get(row["home_team"], 0.0)
                - v0_ratings.get(row["away_team"], 0.0)
                + (0.0 if game["neutral"] else v0_parameters.home_field)
            ),
            "challenger_prediction": current_prediction,
            "challenger_full_strength_prediction": full_prediction,
            "subgroup_flags": {
                "changed_or_backup_qb": bool(
                    starter_changed
                    or
                    (home_qb is not None and home_qb < -1e-12)
                    or (away_qb is not None and away_qb < -1e-12)
                ),
                "major_availability_loss": bool(
                    current_prediction - home_full_prediction <= -1.5
                    or away_full_prediction - current_prediction <= -1.5
                ),
                "head_coach_change": bool(head_coach_change),
                "weeks_1_4": row["week"] <= 4,
                "weeks_5_18": 5 <= row["week"] <= 18,
            },
        }
    turnover_flags = _prospective_turnover_flags(
        historical_rows, historical_context["evaluation_metadata"],
        future_rows, future_metadata,
    )
    for game_id, flag in turnover_flags.items():
        predictions[game_id]["subgroup_flags"]["high_roster_turnover"] = bool(flag)
    return {
        "source_hashes": {},
        "challenger": {
            "parameters": asdict(parameters),
            "feature_names": list(preprocessor.feature_names),
            "missing_features": list(preprocessor.missing_features),
            "medians": preprocessor.medians.tolist(),
            "scales": preprocessor.scales.tolist(),
            "coefficients": coefficients.tolist(),
        },
        "pgo_v0": {
            "parameters": asdict(v0_parameters),
            "ratings": dict(v0_ratings),
        },
        "predictions": predictions,
    }


def _fit_v0_state(paths):
    """Fit the existing v0 benchmark from the frozen completed schedule."""
    schedule_path = paths.get(("schedule_results", None))
    if schedule_path is None:
        raise ValueError("Locked schedule source is missing")
    games = []
    for row in pgo_sources.open_csv(schedule_path):
        if row.get("game_type") != "REG" or not row.get("home_score") or not row.get("away_score"):
            continue
        season = int(row["season"])
        if season > pgo_model.EVAL_END:
            continue
        home = pgo_model.ALIASES.get(row["home_team"], row["home_team"])
        away = pgo_model.ALIASES.get(row["away_team"], row["away_team"])
        games.append(pgo_model.Game(
            row["game_id"], season, row["gameday"], away, home,
            float(row["home_score"]) - float(row["away_score"]),
            row.get("location", "").strip().lower() == "neutral",
        ))
    if not games:
        raise ValueError("No completed schedule rows for v0 fit")
    games.sort(key=lambda game: (game.gameday, game.game_id))
    parameters = pgo_model.select_parameters(games)
    _, ratings = pgo_model.walk_forward(games, parameters)
    latest_season = max(game.season for game in games)
    gap = 2026 - latest_season
    if gap > 0:
        ratings = {
            team: value * parameters.offseason_retention ** gap
            for team, value in ratings.items()
        }
    return parameters, ratings


def _cli_lock(args):
    schedule = load_schedule_snapshot(args.schedule_snapshot)
    manifest = json.loads(Path(args.lock_path).read_text(encoding="utf-8"))
    paths = pgo_sources.load_locked_sources(args.lock_path, args.cache_dir)
    audit = pgo_challenger._source_preflight(paths, manifest, args.as_of)
    state = fit_model_state(paths, args.as_of, schedule["rows"])
    state["source_lock_sha256"] = hashlib.sha256(
        Path(args.lock_path).read_bytes()
    ).hexdigest()
    state["source_hashes"] = audit["source_hashes"]
    lock = lock_games(schedule, state, args.as_of)
    write_lock(args.output_dir, lock)
    return 0


def _cli_grade(args):
    lock = {}
    try:
        lock_bytes = Path(args.lock_file).read_bytes()
        parsed_lock = json.loads(lock_bytes)
        if not isinstance(parsed_lock, dict):
            raise ValueError("Lock must be a JSON object")
        _canonical(parsed_lock)
        lock = parsed_lock
        attestation = None
        if lock.get("schema_version") == 2:
            attestation_file = getattr(args, "attestation_file", None)
            if attestation_file is None:
                raise ValueError("Grade attestation required")
            attestation = json.loads(Path(attestation_file).read_bytes())
        receipt = grade_locked_games(
            lock,
            _load_results(args.results_path),
            attestation=attestation,
            lock_bytes=lock_bytes,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        receipt = _blocked_receipt(lock, args.results_path, error)
    write_grade(args.output_dir, receipt, receipt["rows"])
    return 0 if receipt["status"] == "PASS" else 1


def _cli_develop_blend(args):
    write_development_receipt(
        args.output, develop_stability_blend(load_development_predictions(args.predictions))
    )
    return 0


def _detach_output(target, expected_state):
    quarantine = None
    try:
        descriptor, name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".rollback",
        )
        os.close(descriptor)
        quarantine = Path(name)
        os.replace(target, quarantine)
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
    except BaseException:
        return
    if not is_owned:
        try:
            os.link(quarantine, target)
        except BaseException:
            return
    try:
        quarantine.unlink()
    except BaseException:
        pass


def _write_new_outputs(output_dir, outputs):
    staged = []
    owned = {}
    owns_output_dir = False
    success = False
    failure = None
    try:
        output_dir.mkdir(parents=True)
        owns_output_dir = True
        outputs[-1][0].parent.mkdir(parents=True, exist_ok=True)
        for target, content in outputs:
            descriptor, name = tempfile.mkstemp(
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".pending",
            )
            os.close(descriptor)
            staged_path = Path(name)
            staged.append(staged_path)
            atomic_write_text(staged_path, content)
        for (target, _), staged_path in zip(outputs, staged):
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
            _detach_output(target, state)
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
    if isinstance(failure, (KeyboardInterrupt, SystemExit)):
        raise failure
    return success


def _cli_derive_blend(args):
    output_paths = (
        args.output_dir / "prospective_lock.json",
        args.output_dir / "prospective_predictions.csv",
        args.attestation_output,
    )
    try:
        resolved_output_dir = args.output_dir.resolve()
        resolved_outputs = tuple(path.resolve() for path in output_paths)
    except OSError:
        return 1
    if (
        args.output_dir.exists()
        or args.output_dir.is_symlink()
        or any(path.exists() or path.is_symlink() for path in output_paths)
        or len(set(resolved_outputs)) != len(resolved_outputs)
        or resolved_outputs[-1].is_relative_to(resolved_output_dir)
        or resolved_output_dir.is_relative_to(resolved_outputs[-1])
    ):
        return 1
    try:
        base_lock_bytes = args.base_lock.read_bytes()
        base_prediction_bytes = args.base_predictions.read_bytes()
        development_receipt_bytes = args.development_receipt.read_bytes()
        base_lock = json.loads(base_lock_bytes)
        development_receipt = json.loads(development_receipt_bytes)
        _verify_lock(base_lock)
        if base_prediction_bytes != _prediction_csv(base_lock).encode("utf-8"):
            raise ValueError("Base prediction bytes mismatch")
        derived = derive_stability_blend(
            base_lock, development_receipt,
            hashlib.sha256(development_receipt_bytes).hexdigest(), args.as_of,
        )
        derived_lock_bytes = serialize_lock(derived).encode("utf-8")
        derived_prediction_bytes = _prediction_csv(derived).encode("utf-8")
        attestation = build_prospective_attestation(
            base_lock, base_lock_bytes, base_prediction_bytes, derived,
            derived_lock_bytes, derived_prediction_bytes, development_receipt_bytes,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return 1
    outputs = (
        (output_paths[0], derived_lock_bytes.decode("utf-8")),
        (output_paths[1], derived_prediction_bytes.decode("utf-8")),
        (output_paths[2], _canonical(attestation) + "\n"),
    )
    return 0 if _write_new_outputs(args.output_dir, outputs) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    lock = subparsers.add_parser("lock")
    lock.add_argument("--as-of", required=True)
    lock.add_argument("--lock-path", type=Path, required=True)
    lock.add_argument("--cache-dir", type=Path, required=True)
    lock.add_argument("--schedule-snapshot", type=Path, required=True)
    lock.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    grade = subparsers.add_parser("grade")
    grade.add_argument("--lock-file", type=Path, required=True)
    grade.add_argument("--results-path", type=Path, required=True)
    grade.add_argument("--attestation-file", type=Path)
    grade.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    develop = subparsers.add_parser("develop-blend")
    develop.add_argument("--predictions", type=Path, required=True)
    develop.add_argument("--output", type=Path, required=True)
    derive = subparsers.add_parser("derive-blend")
    derive.add_argument("--base-lock", type=Path, required=True)
    derive.add_argument("--base-predictions", type=Path, required=True)
    derive.add_argument("--development-receipt", type=Path, required=True)
    derive.add_argument("--as-of", required=True)
    derive.add_argument("--output-dir", type=Path, required=True)
    derive.add_argument("--attestation-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "lock":
        return _cli_lock(args)
    elif args.command == "grade":
        return _cli_grade(args)
    elif args.command == "develop-blend":
        return _cli_develop_blend(args)
    elif args.command == "derive-blend":
        return _cli_derive_blend(args)


if __name__ == "__main__":
    raise SystemExit(main())
