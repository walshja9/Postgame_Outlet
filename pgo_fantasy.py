"""Independent half-PPR fantasy baselines built from frozen nflverse files."""

import csv
import hashlib
import io
import json
import math
from pathlib import Path

from pgo_model import SOURCE_URL
from pgo_sources import SourceSpec, normalize_team, open_csv


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


def _load_source_rows(paths):
    specs = {(spec.name, spec.season): spec for spec in fantasy_source_specs()}
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
        rows = list(open_csv(path))
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


def _load_rosters(source_rows, team_weeks, coverage):
    rosters = {}
    player_weeks = set()
    for source_season in MODEL_SEASONS:
        for row in source_rows[("weekly_rosters", source_season)]:
            season = _integer(row, "season", "roster")
            if season != source_season:
                raise ValueError(
                    f"Roster source-season mismatch: {source_season} != {season}"
                )
            if (row.get("game_type") or "").strip() != "REG":
                continue
            raw_position = (row.get("position") or "").strip().upper()
            position = POSITION_MAP.get(raw_position)
            if position is None:
                continue
            week = _integer(row, "week", "roster")
            status = (row.get("status") or "").strip().upper()
            if not status:
                raise ValueError("Missing roster status")
            gsis_id = (row.get("gsis_id") or "").strip()
            if not gsis_id:
                raise ValueError("Missing roster GSIS ID")
            team = normalize_team(row.get("team") or "")
            player_week = (season, week, gsis_id)
            if player_week in player_weeks:
                raise ValueError(f"Duplicate eligible roster identity: {player_week}")
            player_weeks.add(player_week)
            if status != "ACT":
                continue
            schedule_key = (season, week, team)
            if schedule_key not in team_weeks:
                coverage[str(season)]["bye_skipped"] += 1
                continue
            game_id, opponent = team_weeks[schedule_key]
            natural_key = (game_id, gsis_id)
            if natural_key in rosters:
                raise ValueError(f"Duplicate fantasy natural key: {natural_key}")
            rosters[natural_key] = {
                "season": season,
                "week": week,
                "game_id": game_id,
                "gsis_id": gsis_id,
                "player_name": (row.get("full_name") or "").strip(),
                "team": team,
                "opponent": opponent,
                "position": position,
            }
            coverage[str(season)]["eligible"] += 1
    return rosters


def _load_stats(source_rows, games, rosters):
    stats = {}
    for source_season in MODEL_SEASONS:
        for row in source_rows[("player_weekly_stats", source_season)]:
            season = _integer(row, "season", "stat")
            if season != source_season:
                raise ValueError(
                    f"Stat source-season mismatch: {source_season} != {season}"
                )
            if (row.get("season_type") or "").strip() != "REG":
                continue
            raw_position = (row.get("position") or "").strip().upper()
            gsis_id = (row.get("player_id") or "").strip()
            game_id = (row.get("game_id") or "").strip()
            natural_key = (game_id, gsis_id)
            if raw_position not in POSITION_MAP and natural_key not in rosters:
                continue
            if not gsis_id:
                raise ValueError("Missing stat GSIS ID")
            game = games.get(game_id)
            week = _integer(row, "week", "stat")
            if game is None or game["season"] != season or game["week"] != week:
                raise ValueError(f"Stat schedule identity mismatch: {(game_id, gsis_id)}")
            team = normalize_team(row.get("team") or "")
            opponent = normalize_team(row.get("opponent_team") or "")
            valid_matchup = (
                (team == game["away"] and opponent == game["home"])
                or (team == game["home"] and opponent == game["away"])
            )
            if not valid_matchup:
                raise ValueError(f"Stat team/opponent mismatch: {(game_id, gsis_id)}")
            if natural_key in stats:
                raise ValueError(f"Duplicate eligible stat identity: {natural_key}")
            stats[natural_key] = row
    return stats


def build_player_games(paths) -> tuple[list[dict], dict]:
    source_rows, source_receipts = _load_source_rows(paths)
    games, team_weeks = _load_schedule(source_rows[("schedule_results", None)])
    coverage = {
        str(season): {
            "eligible": 0,
            "matched_stats": 0,
            "zero_filled": 0,
            "bye_skipped": 0,
        }
        for season in MODEL_SEASONS
    }
    rosters = _load_rosters(source_rows, team_weeks, coverage)
    stats = _load_stats(source_rows, games, rosters)
    unmatched = sorted(set(stats) - set(rosters))
    if unmatched:
        raise ValueError(f"Eligible stat row outside ACT roster population: {unmatched[0]}")

    rows = []
    for key, roster in sorted(rosters.items()):
        stat = stats.get(key)
        if stat is not None:
            if (
                normalize_team(stat["team"]) != roster["team"]
                or normalize_team(stat["opponent_team"]) != roster["opponent"]
            ):
                raise ValueError(f"Stat team/opponent mismatch: {key}")
            if POSITION_MAP.get(stat["position"].strip().upper()) != roster["position"]:
                raise ValueError(f"Position mismatch for {key}")
        target = 0.0 if stat is None else half_ppr(stat)
        coverage[str(roster["season"])][
            "zero_filled" if stat is None else "matched_stats"
        ] += 1
        rows.append({**roster, "fantasy_points": target})
    rows.sort(
        key=lambda row: (
            row["season"],
            row["week"],
            row["game_id"],
            row["gsis_id"],
        )
    )
    if not rows:
        raise ValueError("Fantasy population contains zero eligible player-games")
    audit = {
        "schema_version": 1,
        "scope": {
            "seasons": list(MODEL_SEASONS),
            "game_type": "REG",
            "roster_status": "ACT",
        },
        "sources": source_receipts,
        "coverage": coverage,
        "checks": {
            "source_contract": True,
            "schedule_identity": True,
            "roster_identity": True,
            "stat_identity": True,
            "finite_targets": True,
        },
    }
    return rows, audit


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


def backtest_baselines(rows, source_audit) -> tuple[dict, list[dict]]:
    if (
        not isinstance(source_audit, dict)
        or not isinstance(source_audit.get("checks"), dict)
        or not source_audit["checks"]
        or any(value is not True for value in source_audit["checks"].values())
    ):
        raise ValueError("Source audit is incomplete")
    audit_sha256 = hashlib.sha256(_canonical_json_bytes(source_audit)).hexdigest()
    validated = _validated_baseline_rows(rows)
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
