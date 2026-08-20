#!/usr/bin/env python3
"""Freeze pregame PGO predictions for a prospective, shadow-only grade."""

import argparse
import csv
import hashlib
import io
import json
import math
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


def serialize_lock(lock):
    return _canonical(lock) + "\n"


def _prediction_csv(lock):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PREDICTION_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for game in lock["games"]:
        row = dict(game)
        row["subgroup_flags"] = json.dumps(
            row["subgroup_flags"], sort_keys=True, separators=(",", ":")
        )
        writer.writerow({name: row.get(name, "") for name in PREDICTION_COLUMNS})
    return output.getvalue()


def write_lock(output_dir, lock):
    output_dir = Path(output_dir)
    lock_path = output_dir / "prospective_lock.json"
    atomic_write_text(lock_path, serialize_lock(lock))
    atomic_write_text(output_dir / "prospective_predictions.csv", _prediction_csv(lock))
    return lock_path


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    lock = subparsers.add_parser("lock")
    lock.add_argument("--as-of", required=True)
    lock.add_argument("--lock-path", type=Path, required=True)
    lock.add_argument("--cache-dir", type=Path, required=True)
    lock.add_argument("--schedule-snapshot", type=Path, required=True)
    lock.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    if args.command == "lock":
        _cli_lock(args)
    return 0


if __name__ == "__main__":
    main()
