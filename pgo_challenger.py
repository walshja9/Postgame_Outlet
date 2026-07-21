"""Leakage-safe chronological features for the shadow PGO challenger."""

import csv
import io
import math
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import groupby
from zoneinfo import ZoneInfo

import numpy as np

import pgo_model
from pgo_sources import normalize_team, open_csv


FIRST_SEASON = 2013
LAST_SEASON = 2025
QB_PRIOR_DROPBACKS = 200.0
EASTERN = ZoneInfo("America/New_York")
V0_PARAMETERS = pgo_model.Parameters(0.15, 0.5, 2.5, 20.0)
PERFORMANCE_FEATURES = (
    "passing_epa_per_play_for",
    "passing_epa_per_play_against",
    "rushing_epa_per_play_for",
    "rushing_epa_per_play_against",
    "explosive_play_rate_for",
    "explosive_play_prevention_rate",
    "sack_avoidance_rate",
    "sack_creation_rate",
    "giveaway_avoidance_rate",
    "takeaway_rate",
)
QB_FEATURES = (
    "qb_epa_per_dropback",
    "qb_cpoe",
    "qb_sack_avoidance",
    "qb_ball_security",
    "qb_rushing_epa_per_carry",
    "qb_log_dropbacks",
    "qb_experience_prior",
    "qb_draft_prior",
)
HALF_LIFE_GRID = (4, 8, 16)
ALPHA_GRID = (1.0, 10.0, 100.0)
DELTA_GRID = (1.0, 1.5)
OUTER_SEASONS = tuple(range(2018, 2026))
SUBGROUPS = (
    "changed_or_backup_qb",
    "major_availability_loss",
    "head_coach_change",
    "high_roster_turnover",
    "weeks_1_4",
    "weeks_5_18",
)
AUDIT_CHECKS = frozenset(("source", "identity", "leakage", "reproducibility"))


@dataclass(frozen=True)
class FeatureRow:
    game_id: str
    season: int
    week: int
    kickoff: str
    actual_margin: float
    features: dict[str, float | None]
    subgroup_flags: dict[str, bool]


@dataclass(frozen=True)
class Preprocessor:
    feature_names: tuple[str, ...]
    medians: np.ndarray
    scales: np.ndarray
    missing_features: tuple[str, ...]

    def transform(self, rows) -> np.ndarray:
        raw = _feature_matrix(rows, self.feature_names)
        missing = np.isnan(raw)
        filled = np.where(missing, self.medians, raw)
        output = (filled - self.medians) / self.scales
        if self.missing_features:
            indices = [self.feature_names.index(name) for name in self.missing_features]
            output = np.column_stack((output, missing[:, indices]))
        if not np.isfinite(output).all():
            raise ValueError("Preprocessed features must be finite")
        return output


@dataclass(frozen=True)
class ChallengerParameters:
    half_life_games: int
    alpha: float
    delta: float


@dataclass(frozen=True)
class _RatioState:
    numerator: float = 0.0
    denominator: float = 0.0

    def update(self, numerator, denominator, decay):
        aged = _RatioState(self.numerator * decay, self.denominator * decay)
        if numerator is None or denominator is None or denominator <= 0:
            return aged
        return _RatioState(
            aged.numerator + numerator,
            aged.denominator + denominator,
        )

    @property
    def value(self):
        return self.numerator / self.denominator if self.denominator > 0 else None


def availability_probability(report_status, practice_status) -> float:
    report = (report_status or "").strip()
    practice = (practice_status or "").strip()
    reports = {"out": 0.0, "doubtful": 0.25, "questionable": 0.70}
    if report:
        try:
            return reports[report.casefold()]
        except KeyError as error:
            raise ValueError(f"Unknown injury report status: {report}") from error
    practices = {
        "": 1.0,
        "did not participate": 0.70,
        "limited participation": 0.90,
        "full participation": 1.0,
    }
    try:
        return practices[practice.casefold()]
    except KeyError as error:
        raise ValueError(f"Unknown practice status: {practice}") from error


def lineup_views(team, snapshot, state) -> tuple[dict[str, float], dict[str, float]]:
    team = normalize_team(team)
    players = snapshot.get(team, snapshot.get("players", {}))
    base = state.get(team, state) if isinstance(state.get(team), dict) else state
    full = dict(base)
    qbs = [(player_id, player) for player_id, player in players.items()
           if player.get("position", "").strip().upper() == "QB"]
    depth_chart = sorted(qbs, key=lambda item: (-_qb_sort_value(item[1]), item[0]))
    starter = depth_chart[0] if depth_chart else None

    for name in QB_FEATURES:
        full[name] = _qb_feature(starter[1], name) if starter else None
    full["qb_current_minus_full"] = 0.0
    full["offense_availability"] = 0.0
    full["defense_availability"] = 0.0

    current = dict(full)
    if starter:
        for name in QB_FEATURES:
            current[name] = _expected_qb_feature(depth_chart, name)
        full_value = full["qb_epa_per_dropback"]
        current_value = current["qb_epa_per_dropback"]
        if full_value is not None and current_value is not None:
            current["qb_current_minus_full"] = current_value - full_value
        else:
            current["qb_current_minus_full"] = None

    offense = _unavailable_share(players.values(), "offense_snap_share")
    defense = _unavailable_share(players.values(), "defense_snap_share")
    current["offense_availability"] = -offense if offense is not None else None
    current["defense_availability"] = -defense if defense is not None else None
    return full, current


def build_feature_rows(paths, half_life_games) -> list[FeatureRow]:
    rows, _, _ = _walk(paths, half_life_games)
    return rows


def build_snapshot_states(paths, as_of, half_life_games) -> dict[str, tuple[dict, dict]]:
    as_of_dt = _parse_datetime(as_of)
    as_of_year = as_of_dt.astimezone(EASTERN).year
    _, context, inputs = _walk(paths, half_life_games, as_of=as_of_dt)
    available_periods = set()
    for game in _load_games(paths):
        if game["kickoff_dt"] < as_of_dt:
            available_periods.update({
                (game["season"], game["week"], game["home"]),
                (game["season"], game["week"], game["away"]),
            })
    periods = {}
    for season, week, team in inputs["rosters"]:
        key = (season, week, team)
        available = key in available_periods or (
            key in inputs["current_roster_periods"] and season == as_of_year
        )
        if available and (team not in periods or (season, week) > periods[team]):
            periods[team] = (season, week)
    teams = sorted(context["seen_teams"] | set(periods))
    states = {}
    for team in teams:
        season, week = periods.get(team, (as_of_year, 0))
        coach = context["coaches"].get(team, "")
        full, current, _ = _team_views(
            team, season, week, coach, as_of_dt, context, inputs
        )
        states[team] = (full, current)
    return states


def fit_preprocessor(rows, feature_names) -> Preprocessor:
    if not rows:
        raise ValueError("Training rows must not be empty")
    feature_names = tuple(feature_names)
    raw = _feature_matrix(rows, feature_names)
    medians = np.array([
        np.median(column[~np.isnan(column)])
        if np.any(~np.isnan(column)) else np.nan
        for column in raw.T
    ])
    if not np.isfinite(medians).all():
        raise ValueError("Training features must contain a finite value")
    filled = np.where(np.isnan(raw), medians, raw)
    scales = filled.std(axis=0)
    scales[scales == 0.0] = 1.0
    if not np.isfinite(scales).all():
        raise ValueError("Training feature scales must be finite")
    missing_features = tuple(
        name for index, name in enumerate(feature_names)
        if np.isnan(raw[:, index]).any()
    )
    return Preprocessor(feature_names, medians, scales, missing_features)


def fit_huber_ridge(x, y, alpha, delta, max_iter=50, tolerance=1e-8) -> np.ndarray:
    x, y = _model_inputs(x, y)
    if not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("alpha must be positive and finite")
    if not np.isfinite(delta) or delta <= 0:
        raise ValueError("delta must be positive and finite")
    if not isinstance(max_iter, int) or max_iter <= 0:
        raise ValueError("max_iter must be a positive integer")
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be positive and finite")
    design = np.column_stack((np.ones(len(x)), x))
    coefficients = _ridge_solution(design, y, alpha, np.ones(len(x)))
    for _ in range(max_iter):
        residuals = y - design @ coefficients
        scale = 1.4826 * np.median(
            np.abs(residuals - np.median(residuals))
        )
        if scale <= np.finfo(float).eps:
            return coefficients
        absolute = np.abs(residuals)
        weights = np.ones(len(x))
        nonzero = absolute > 0.0
        weights[nonzero] = np.minimum(
            1.0, delta * scale / absolute[nonzero]
        )
        updated = _ridge_solution(design, y, alpha, weights)
        if np.max(np.abs(updated - coefficients)) < tolerance:
            return updated
        coefficients = updated
    return coefficients


def predict(x, coefficients) -> np.ndarray:
    try:
        x = np.asarray(x, dtype=float)
        coefficients = np.asarray(coefficients, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("Model inputs must be numeric") from error
    if x.ndim != 2 or coefficients.ndim != 1 or len(coefficients) != x.shape[1] + 1:
        raise ValueError("Model input shapes do not align")
    if not np.isfinite(x).all() or not np.isfinite(coefficients).all():
        raise ValueError("Model inputs must be finite")
    output = np.column_stack((np.ones(len(x)), x)) @ coefficients
    if not np.isfinite(output).all():
        raise ValueError("Predictions must be finite")
    return output


def select_parameters(paths, validation_seasons) -> ChallengerParameters:
    seasons = tuple(sorted(set(validation_seasons)))
    if not seasons:
        raise ValueError("validation_seasons must not be empty")
    errors = {
        ChallengerParameters(half_life, alpha, delta): []
        for half_life in HALF_LIFE_GRID
        for alpha in ALPHA_GRID
        for delta in DELTA_GRID
    }
    for half_life in HALF_LIFE_GRID:
        rows = build_feature_rows(paths, half_life)
        eligible_rows = [row for row in rows if row.season <= seasons[-1]]
        if not eligible_rows:
            raise ValueError("Feature rows must not be empty")
        feature_names = tuple(sorted(eligible_rows[0].features))
        if any(
            tuple(sorted(row.features)) != feature_names for row in eligible_rows
        ):
            raise ValueError("Feature row shapes do not align")
        for season in seasons:
            training = [row for row in eligible_rows if row.season < season]
            validation = [row for row in eligible_rows if row.season == season]
            if len({row.season for row in training}) < 3:
                raise ValueError(
                    "Each validation fold requires three earlier training seasons"
                )
            if not validation:
                raise ValueError(f"No feature rows for validation season {season}")
            preprocessor = fit_preprocessor(training, feature_names)
            x_train = preprocessor.transform(training)
            x_validation = preprocessor.transform(validation)
            y_train = np.array([row.actual_margin for row in training], dtype=float)
            y_validation = np.array(
                [row.actual_margin for row in validation], dtype=float
            )
            if not np.isfinite(y_validation).all():
                raise ValueError("Validation targets must be finite")
            for alpha in ALPHA_GRID:
                for delta in DELTA_GRID:
                    parameters = ChallengerParameters(half_life, alpha, delta)
                    coefficients = fit_huber_ridge(
                        x_train, y_train, alpha, delta
                    )
                    validation_predictions = predict(x_validation, coefficients)
                    with np.errstate(over="ignore", invalid="ignore"):
                        absolute_errors = np.abs(
                            y_validation - validation_predictions
                        )
                    if not np.isfinite(absolute_errors).all():
                        raise ValueError("Prediction errors must be finite")
                    errors[parameters].extend(absolute_errors)
    return min(
        errors,
        key=lambda parameters: (
            float(np.mean(errors[parameters])),
            parameters.half_life_games,
            parameters.alpha,
            parameters.delta,
        ),
    )


def rolling_predictions(paths) -> tuple[list[dict], dict]:
    incumbent = _incumbent_predictions(paths)
    challenger = []
    for season in OUTER_SEASONS:
        parameters = select_parameters(paths, range(2016, season))
        rows, context, _ = _walk(paths, parameters.half_life_games)
        training = [row for row in rows if row.season < season]
        validation = [row for row in rows if row.season == season]
        if not training or not validation:
            raise ValueError(f"Missing challenger fold rows for {season}")
        feature_names = tuple(sorted(training[0].features))
        if any(tuple(sorted(row.features)) != feature_names for row in training + validation):
            raise ValueError("Feature row shapes do not align")
        preprocessor = fit_preprocessor(training, feature_names)
        coefficients = fit_huber_ridge(
            preprocessor.transform(training),
            np.array([row.actual_margin for row in training], dtype=float),
            parameters.alpha,
            parameters.delta,
        )
        predictions = predict(preprocessor.transform(validation), coefficients)
        metadata = context.get("evaluation_metadata", {})
        try:
            fold_metadata = [metadata[row.game_id] for row in validation]
        except KeyError as error:
            raise ValueError(f"Missing evaluation metadata: {error.args[0]}") from error
        home_full = [
            _feature_row(row, value["home_full_features"])
            for row, value in zip(validation, fold_metadata)
        ]
        away_full = [
            _feature_row(row, value["away_full_features"])
            for row, value in zip(validation, fold_metadata)
        ]
        home_full_predictions = predict(
            preprocessor.transform(home_full), coefficients
        )
        away_full_predictions = predict(
            preprocessor.transform(away_full), coefficients
        )
        turnover_flags, _ = _frozen_turnover_flags(validation, metadata)
        for row, predicted, home_prediction, away_prediction, value in zip(
            validation,
            predictions,
            home_full_predictions,
            away_full_predictions,
            fold_metadata,
        ):
            flags = dict(row.subgroup_flags)
            flags["major_availability_loss"] = (
                predicted - home_prediction <= -1.5
                or away_prediction - predicted <= -1.5
            )
            flags["high_roster_turnover"] = turnover_flags[row.game_id]
            challenger.append({
                "game_id": row.game_id,
                "season": row.season,
                "week": row.week,
                "kickoff": row.kickoff,
                "actual_margin": row.actual_margin,
                "challenger_prediction": float(predicted),
                **flags,
                "half_life_games": parameters.half_life_games,
                "alpha": parameters.alpha,
                "delta": parameters.delta,
            })

    incumbent_by_id = _unique_predictions(incumbent, "incumbent")
    challenger_by_id = _unique_predictions(challenger, "challenger")
    if incumbent_by_id.keys() != challenger_by_id.keys():
        missing = sorted(challenger_by_id.keys() - incumbent_by_id.keys())
        extra = sorted(incumbent_by_id.keys() - challenger_by_id.keys())
        details = []
        if missing:
            details.append("missing incumbent: " + ", ".join(missing))
        if extra:
            details.append("extra incumbent: " + ", ".join(extra))
        raise ValueError("Prediction game IDs do not match (" + "; ".join(details) + ")")
    for row in challenger:
        incumbent_row = incumbent_by_id[row["game_id"]]
        if incumbent_row.actual != row["actual_margin"]:
            raise ValueError(f"Actual margin mismatch: {row['game_id']}")
        row["pgo_v0_prediction"] = float(incumbent_row.predicted)

    evaluation = {
        "paired_game_ids": True,
        "pgo_v0": metric_summary(challenger, "pgo_v0_prediction"),
        "challenger": metric_summary(challenger, "challenger_prediction"),
        "improvement": paired_block_bootstrap(challenger),
        "subgroups": subgroup_results(challenger),
    }
    return challenger, evaluation


def _frozen_turnover_flags(rows, metadata):
    first_share, teams_by_game = {}, {}
    for row in sorted(rows, key=lambda value: (value.kickoff, value.game_id)):
        try:
            value = metadata[row.game_id]
            teams = (
                (value["home_team"], value["home_returning_snap_share"]),
                (value["away_team"], value["away_returning_snap_share"]),
            )
        except KeyError as error:
            raise ValueError(f"Missing turnover metadata: {error.args[0]}") from error
        teams_by_game[row.game_id] = tuple(team for team, _ in teams)
        for team, share in teams:
            if team in first_share:
                continue
            if share is not None:
                share = float(share)
                if not math.isfinite(share):
                    raise ValueError("Returning snap shares must be finite")
            first_share[team] = share
    shares = [share for share in first_share.values() if share is not None]
    quartile = float(np.percentile(shares, 25)) if shares else None
    return {
        game_id: (
            quartile is not None
            and any(
                first_share.get(team) is not None
                and first_share[team] <= quartile
                for team in teams
            )
        )
        for game_id, teams in teams_by_game.items()
    }, quartile


def metric_summary(rows, prediction_key) -> dict:
    actual, predicted = _prediction_values(rows, prediction_key)
    summary = _basic_metrics(actual, predicted)
    summary["seasons"] = [
        {
            "season": season,
            **_basic_metrics(
                *zip(*[
                    (float(row["actual_margin"]), float(row[prediction_key]))
                    for row in rows
                    if row["season"] == season
                ])
            ),
        }
        for season in sorted({row["season"] for row in rows})
    ]
    bands = (
        ("<-7", lambda value: value < -7.0),
        ("-7:-3", lambda value: -7.0 <= value < -3.0),
        ("-3:3", lambda value: -3.0 <= value <= 3.0),
        ("3:7", lambda value: 3.0 < value <= 7.0),
        (">7", lambda value: value > 7.0),
    )
    calibration = []
    for label, contains in bands:
        selected = [
            row for row in rows if contains(float(row["challenger_prediction"]))
        ]
        calibration.append({
            "band": label,
            "count": len(selected),
            "mean_prediction": (
                float(np.mean([row[prediction_key] for row in selected]))
                if selected else None
            ),
            "mean_actual_margin": (
                float(np.mean([row["actual_margin"] for row in selected]))
                if selected else None
            ),
        })
    summary["calibration_bands"] = calibration
    return summary


def paired_block_bootstrap(rows, samples=10_000, seed=20260721) -> dict:
    if not isinstance(samples, int) or samples <= 0:
        raise ValueError("samples must be a positive integer")
    improvements = defaultdict(list)
    for row in rows:
        try:
            actual = float(row["actual_margin"])
            incumbent = float(row["pgo_v0_prediction"])
            challenger = float(row["challenger_prediction"])
            season, week = int(row["season"]), int(row["week"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Bootstrap rows are invalid") from error
        values = (actual, incumbent, challenger)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Bootstrap values must be finite")
        improvements[(season, week)].append(
            abs(actual - incumbent) - abs(actual - challenger)
        )
    if not improvements:
        raise ValueError("Bootstrap rows must not be empty")
    blocks = [np.asarray(improvements[key], dtype=float) for key in sorted(improvements)]
    block_sums = np.asarray([block.sum() for block in blocks])
    block_counts = np.asarray([len(block) for block in blocks])
    draws = np.random.default_rng(seed).integers(
        0, len(blocks), size=(samples, len(blocks))
    )
    distribution = block_sums[draws].sum(axis=1) / block_counts[draws].sum(axis=1)
    return {
        "mean": float(sum(map(sum, blocks)) / sum(map(len, blocks))),
        "lower": float(np.percentile(distribution, 2.5)),
        "upper": float(np.percentile(distribution, 97.5)),
        "samples": samples,
        "seed": seed,
    }


def subgroup_results(rows) -> dict:
    results = {}
    for name in SUBGROUPS:
        selected = [row for row in rows if row.get(name) is True]
        if len(selected) < 100:
            results[name] = {
                "status": "INSUFFICIENT_EVIDENCE",
                "count": len(selected),
            }
            continue
        incumbent = metric_summary(selected, "pgo_v0_prediction")
        challenger = metric_summary(selected, "challenger_prediction")
        interval = paired_block_bootstrap(selected)
        results[name] = {
            "status": "SUFFICIENT_EVIDENCE",
            "count": len(selected),
            "pgo_v0_mae": incumbent["mae"],
            "challenger_mae": challenger["mae"],
            "improvement": incumbent["mae"] - challenger["mae"],
            "lower": interval["lower"],
            "upper": interval["upper"],
        }
    return results


def gate_checks(audit, evaluation, ratings_count, deterministic) -> dict[str, bool]:
    audit_checks = audit.get("checks", audit) if isinstance(audit, dict) else {}
    subgroups = evaluation.get("subgroups", {})
    mae_passes, bootstrap_passes = _aggregate_gate_checks(evaluation)
    return {
        "audit_checks_pass": AUDIT_CHECKS <= set(audit_checks) and all(
            value is True for value in audit_checks.values()
        ),
        "all_32_current_teams": ratings_count == 32,
        "paired_game_ids": evaluation.get("paired_game_ids") is True,
        "challenger_mae_lower": mae_passes,
        "aggregate_improvement_ci_positive": bootstrap_passes,
        "no_sufficient_subgroup_regression": _subgroup_gate_passes(subgroups),
        "deterministic": deterministic is True,
    }


def _aggregate_gate_checks(evaluation):
    try:
        incumbent = evaluation["pgo_v0"]
        challenger = evaluation["challenger"]
        incumbent_count = incumbent["count"]
        challenger_count = challenger["count"]
        incumbent_mae = incumbent["mae"]
        challenger_mae = challenger["mae"]
        valid_counts = all(
            not isinstance(value, bool)
            and isinstance(value, (int, np.integer))
            and value > 0
            for value in (incumbent_count, challenger_count)
        ) and incumbent_count == challenger_count
        valid_maes = all(
            not isinstance(value, bool)
            and isinstance(value, (int, float, np.integer, np.floating))
            and math.isfinite(value)
            and value >= 0.0
            for value in (incumbent_mae, challenger_mae)
        )
        mae_passes = (
            valid_counts and valid_maes and challenger_mae < incumbent_mae
        )
    except (KeyError, TypeError):
        mae_passes = False

    try:
        improvement = evaluation["improvement"]
        mean, lower, upper = (
            improvement[name] for name in ("mean", "lower", "upper")
        )
        valid_interval = all(
            not isinstance(value, bool)
            and isinstance(value, (int, float, np.integer, np.floating))
            and math.isfinite(value)
            for value in (mean, lower, upper)
        )
        bootstrap_passes = (
            valid_interval
            and lower <= mean <= upper
            and not isinstance(improvement["samples"], bool)
            and isinstance(improvement["samples"], (int, np.integer))
            and improvement["samples"] == 10_000
            and not isinstance(improvement["seed"], bool)
            and isinstance(improvement["seed"], (int, np.integer))
            and improvement["seed"] == 20260721
            and lower > 0.0
        )
    except (KeyError, TypeError):
        bootstrap_passes = False
    return mae_passes, bootstrap_passes


def _subgroup_gate_passes(subgroups):
    if set(subgroups) != set(SUBGROUPS):
        return False
    for result in subgroups.values():
        count = result.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return False
        status = result.get("status")
        if status == "INSUFFICIENT_EVIDENCE":
            if count >= 100:
                return False
            continue
        if status != "SUFFICIENT_EVIDENCE" or count < 100:
            return False
        try:
            incumbent, challenger, improvement, lower, upper = (
                float(result[name])
                for name in (
                    "pgo_v0_mae",
                    "challenger_mae",
                    "improvement",
                    "lower",
                    "upper",
                )
            )
        except (KeyError, TypeError, ValueError):
            return False
        values = (incumbent, challenger, improvement, lower, upper)
        if not all(math.isfinite(value) for value in values):
            return False
        if lower > upper or not math.isclose(
            improvement,
            incumbent - challenger,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            return False
        if upper < 0.0:
            return False
    return True


def _incumbent_predictions(paths):
    schedule = list(open_csv(paths[("schedule_results", None)]))
    if not schedule:
        raise ValueError("Schedule source must not be empty")
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=tuple(schedule[0]))
    writer.writeheader()
    writer.writerows(schedule)
    games = pgo_model.parse_games(text.getvalue())
    parameters = pgo_model.select_parameters(games)
    predictions, _ = pgo_model.walk_forward(games, parameters)
    return [value for value in predictions if value.season in OUTER_SEASONS]


def _unique_predictions(rows, label):
    by_id = {}
    for row in rows:
        game_id = row.game_id if hasattr(row, "game_id") else row["game_id"]
        if game_id in by_id:
            raise ValueError(f"Duplicate {label} prediction: {game_id}")
        by_id[game_id] = row
    return by_id


def _feature_row(row, features):
    return FeatureRow(
        row.game_id,
        row.season,
        row.week,
        row.kickoff,
        row.actual_margin,
        features,
        row.subgroup_flags,
    )


def _prediction_values(rows, prediction_key):
    if not rows:
        raise ValueError("Metric rows must not be empty")
    try:
        actual = np.asarray([row["actual_margin"] for row in rows], dtype=float)
        predicted = np.asarray([row[prediction_key] for row in rows], dtype=float)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Metric rows are invalid") from error
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Metric values must be finite")
    return actual, predicted


def _basic_metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    errors = actual - predicted
    absolute = np.abs(errors)
    return {
        "count": len(errors),
        "mae": float(np.mean(absolute)),
        "median_absolute_error": float(np.median(absolute)),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "miss_rate_above_14": float(np.mean(absolute > 14.0)),
        "miss_rate_above_21": float(np.mean(absolute > 21.0)),
        "mean_signed_error_home": float(np.mean(errors)),
        "mean_signed_error_away": float(-np.mean(errors)),
    }


def _feature_matrix(rows, feature_names) -> np.ndarray:
    matrix = np.empty((len(rows), len(feature_names)), dtype=float)
    for row_index, row in enumerate(rows):
        for column_index, name in enumerate(feature_names):
            try:
                value = row.features[name]
            except (AttributeError, KeyError) as error:
                raise ValueError("Feature row shapes do not align") from error
            if value is None:
                matrix[row_index, column_index] = np.nan
                continue
            try:
                value = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Feature {name} must be numeric") from error
            if not math.isfinite(value):
                raise ValueError(f"Feature {name} must be finite")
            matrix[row_index, column_index] = value
    return matrix


def _model_inputs(x, y):
    try:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("Model inputs must be numeric") from error
    if x.ndim != 2 or y.ndim != 1 or len(x) != len(y):
        raise ValueError("Model input shapes do not align")
    if not len(x):
        raise ValueError("Training rows must not be empty")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Model inputs must be finite")
    return x, y


def _ridge_solution(design, y, alpha, weights):
    penalty = np.diag([0.0] + [alpha] * (design.shape[1] - 1))
    coefficients = np.linalg.solve(
        design.T @ (design * weights[:, None]) + penalty,
        design.T @ (weights * y),
    )
    if not np.isfinite(coefficients).all():
        raise ValueError("Model coefficients must be finite")
    return coefficients


def _walk(paths, half_life_games, as_of=None):
    if not isinstance(half_life_games, (int, float)) or half_life_games <= 0:
        raise ValueError("half_life_games must be positive")
    decay = 0.5 ** (1.0 / half_life_games)
    inputs = _load_inputs(paths)
    games = _load_games(paths)
    if as_of is not None:
        games = [game for game in games if game["kickoff_dt"] < as_of]
    context = {
        "ratios": defaultdict(dict),
        "ratings": defaultdict(float),
        "qb_history": defaultdict(lambda: defaultdict(float)),
        "qb_population": defaultdict(float),
        "snap_history": defaultdict(lambda: {
            "offense": deque(maxlen=4), "defense": deque(maxlen=4),
        }),
        "last_team": {},
        "coaches": {},
        "coach_games": defaultdict(int),
        "prior_starter": {},
        "seen_teams": set(),
        "evaluation_metadata": {},
        "season": None,
    }
    output = []
    for _, grouped in groupby(games, key=lambda game: game["kickoff_dt"]):
        batch = list(grouped)
        season = batch[0]["season"]
        if context["season"] is not None and season != context["season"]:
            gap = season - context["season"]
            for team in context["ratings"]:
                context["ratings"][team] *= V0_PARAMETERS.offseason_retention ** gap
        context["season"] = season
        prepared = []
        for game in batch:
            home = _team_views(
                game["home"], game["season"], game["week"],
                game["home_coach"], game["kickoff_dt"], context, inputs,
            )
            away = _team_views(
                game["away"], game["season"], game["week"],
                game["away_coach"], game["kickoff_dt"], context, inputs,
            )
            features = _matchup_features(home[1], away[1], game)
            context["evaluation_metadata"][game["game_id"]] = {
                "home_full_features": _matchup_features(home[0], away[1], game),
                "away_full_features": _matchup_features(home[1], away[0], game),
                "home_team": game["home"],
                "away_team": game["away"],
                "home_returning_snap_share": home[2]["returning_snap_share"],
                "away_returning_snap_share": away[2]["returning_snap_share"],
            }
            starter_changed = any(
                metadata["starter"] is not None
                and team in context["prior_starter"]
                and metadata["starter"] != context["prior_starter"][team]
                for team, metadata in ((game["home"], home[2]), (game["away"], away[2]))
            )
            availability_changed = any(
                view[1]["qb_current_minus_full"] is not None
                and view[1]["qb_current_minus_full"] < -1e-12
                for view in (home, away)
            )
            output.append(FeatureRow(
                game["game_id"], game["season"], game["week"],
                game["kickoff"], game["margin"], features,
                {
                    "changed_or_backup_qb": starter_changed or availability_changed,
                    "head_coach_change": home[2]["coach_changed"] or away[2]["coach_changed"],
                    "weeks_1_4": game["week"] <= 4,
                    "weeks_5_18": 5 <= game["week"] <= 18,
                },
            ))
            prepared.append((game, home[2], away[2]))
        for game, home_metadata, away_metadata in prepared:
            _update_after_game(game, home_metadata, away_metadata, context, inputs, decay)
    return output, context, inputs


def _team_views(team, season, week, coach, kickoff, context, inputs):
    roster_rows = inputs["rosters"].get((season, week, team), ())
    players, metadata = _players_for_team(
        team, season, week, kickoff, roster_rows, context, inputs
    )
    base = {"pgo_v0": context["ratings"].get(team, 0.0)}
    for name in PERFORMANCE_FEATURES:
        base[name] = context["ratios"].get(team, {}).get(name, _RatioState()).value

    offense_total = sum(
        player["offense_snap_share"] for player in players.values()
        if player["offense_snap_share"] is not None
    )
    defense_total = sum(
        player["defense_snap_share"] for player in players.values()
        if player["defense_snap_share"] is not None
    )
    base["returning_offense_snap_share"] = _roster_share(
        players, context["last_team"], team, "offense_snap_share", offense_total, False
    )
    base["returning_defense_snap_share"] = _roster_share(
        players, context["last_team"], team, "defense_snap_share", defense_total, False
    )
    combined = offense_total + defense_total
    base["incoming_prior_snap_share"] = _roster_share(
        players, context["last_team"], team, None, combined, True
    )
    base["rookie_draft_capital"] = sum(
        player["qb_draft_prior"]
        for player in players.values()
        if player["years_exp"] == 0
    ) / max(1, len(players))
    previous_coach = context["coaches"].get(team)
    base["head_coach_continuity"] = (
        None if previous_coach is None else float(previous_coach == coach)
    )
    base["head_coach_tenure"] = math.log1p(
        context["coach_games"].get((team, coach), 0)
    )
    metadata.update({
        "coach": coach,
        "coach_changed": previous_coach is not None and previous_coach != coach,
        "roster": players,
        "returning_snap_share": _roster_share(
            players, context["last_team"], team, None, combined, False
        ),
    })
    full, current = lineup_views(team, {team: players}, base)
    metadata["starter"] = _best_qb([
        (player_id, player) for player_id, player in players.items()
        if player["position"] == "QB"
    ])
    metadata["starter"] = metadata["starter"][0] if metadata["starter"] else None
    return full, current, metadata


def _players_for_team(team, season, week, kickoff, roster_rows, context, inputs):
    players, gsis_ids, pfr_ids = {}, {}, {}
    for row in roster_rows:
        gsis_id = row.get("gsis_id", "").strip()
        pfr_id = row.get("pfr_id", "").strip()
        player_id = gsis_id or (f"pfr:{pfr_id}" if pfr_id else "")
        if not player_id:
            continue
        if player_id in players:
            raise ValueError(f"Duplicate roster player: {season} week {week} {team} {player_id}")
        if gsis_id:
            gsis_ids[gsis_id] = player_id
        if pfr_id:
            pfr_ids[pfr_id] = player_id
        history = context["snap_history"].get(player_id)
        offense = statistics.median(history["offense"]) if history and history["offense"] else None
        defense = statistics.median(history["defense"]) if history and history["defense"] else None
        probability = 1.0
        injury = inputs["injuries"].get((season, week, team, gsis_id)) if gsis_id else None
        if injury:
            modified = injury.get("date_modified", "").strip()
            if modified and _parse_datetime(modified) > kickoff:
                raise ValueError(f"Injury revision after kickoff: {season} week {week} {team} {gsis_id}")
            probability = availability_probability(
                injury.get("report_status"), injury.get("practice_status")
            )
        years_exp = int(float(row.get("years_exp") or 0))
        draft_number = _number(row, "draft_number")
        qb = _qb_features(player_id, years_exp, draft_number, context)
        players[player_id] = {
            "position": row.get("position", "").strip().upper(),
            "probability": probability,
            "offense_snap_share": offense,
            "defense_snap_share": defense,
            "years_exp": years_exp,
            **qb,
        }
    return players, {"gsis_ids": gsis_ids, "pfr_ids": pfr_ids}


def _qb_features(player_id, years_exp, draft_number, context):
    history = context["qb_history"].get(player_id, {})
    population = context["qb_population"]
    sample = history.get("dropbacks", 0.0)
    values = {
        "qb_epa_per_dropback": _shrunk(
            history, population, "passing_epa", "passing_epa_plays", sample
        ),
        "qb_cpoe": _shrunk(history, population, "cpoe_sum", "cpoe_plays", sample),
        "qb_sack_avoidance": _shrunk(
            history, population, "sack_free_dropbacks", "sack_dropbacks", sample
        ),
        "qb_ball_security": _shrunk(
            history, population, "secure_dropbacks", "security_dropbacks", sample
        ),
        "qb_rushing_epa_per_carry": _shrunk(
            history, population, "rushing_epa", "carries", sample
        ),
        "qb_log_dropbacks": math.log1p(sample),
        "qb_experience_prior": math.log1p(max(0, years_exp)),
        "qb_draft_prior": 1.0 / math.sqrt(draft_number) if draft_number and draft_number > 0 else 0.0,
    }
    values["qb_value"] = values["qb_epa_per_dropback"] or 0.0
    return values


def _shrunk(history, population, numerator, denominator, sample):
    population_denominator = population.get(denominator, 0.0)
    if population_denominator <= 0:
        return None
    mean = population.get(numerator, 0.0) / population_denominator
    player_denominator = history.get(denominator, 0.0)
    if player_denominator <= 0:
        return mean
    player = history.get(numerator, 0.0) / player_denominator
    weight = sample / (sample + QB_PRIOR_DROPBACKS)
    return weight * player + (1.0 - weight) * mean


def _update_after_game(game, home, away, context, inputs, decay):
    for team, opponent, metadata in (
        (game["home"], game["away"], home),
        (game["away"], game["home"], away),
    ):
        own = inputs["team_rows"].get((game["season"], game["week"], team))
        other = inputs["team_rows"].get((game["season"], game["week"], opponent))
        _validate_team_row(own, game, opponent)
        for name, (numerator, denominator) in _observations(own, other).items():
            previous = context["ratios"][team].get(name, _RatioState())
            context["ratios"][team][name] = previous.update(numerator, denominator, decay)
        completed_starter, completed_dropbacks = None, 0.0
        for row in inputs["players"].get((game["season"], game["week"], team), ()):
            if row.get("position", "").strip().upper() != "QB":
                continue
            raw_id = row.get("player_id", "").strip()
            player_id = metadata["gsis_ids"].get(raw_id, raw_id)
            dropbacks = _sum(row, "attempts", "sacks_suffered")
            if dropbacks is None:
                dropbacks = _number(row, "attempts") or 0.0
            if dropbacks > completed_dropbacks or (
                dropbacks == completed_dropbacks and completed_starter is not None
                and player_id < completed_starter
            ):
                completed_starter, completed_dropbacks = player_id, dropbacks
            _accumulate_qb(row, context["qb_history"][player_id])
            _accumulate_qb(row, context["qb_population"])
        snap_rows = inputs["snaps"].get((game["season"], game["week"], team), ())
        offense_total = max((_number(row, "offense_snaps") or 0.0 for row in snap_rows), default=0.0)
        defense_total = max((_number(row, "defense_snaps") or 0.0 for row in snap_rows), default=0.0)
        snap_shares = {}
        for row in snap_rows:
            pfr_id = row.get("pfr_player_id", "").strip()
            player_id = metadata["pfr_ids"].get(pfr_id)
            if not player_id:
                continue
            offense = _number(row, "offense_snaps")
            defense = _number(row, "defense_snaps")
            snap_shares[player_id] = (
                offense / offense_total if offense is not None and offense_total > 0 else offense,
                defense / defense_total if defense is not None and defense_total > 0 else defense,
            )
        for player_id in metadata["roster"]:
            offense, defense = snap_shares.get(player_id, (0.0, 0.0))
            if offense is not None:
                context["snap_history"][player_id]["offense"].append(offense)
            if defense is not None:
                context["snap_history"][player_id]["defense"].append(defense)
            context["last_team"][player_id] = team
        coach = metadata["coach"]
        if context["coaches"].get(team) != coach:
            context["coach_games"][(team, coach)] = 0
        context["coach_games"][(team, coach)] += 1
        context["coaches"][team] = coach
        if completed_starter:
            context["prior_starter"][team] = completed_starter
        context["seen_teams"].add(team)

    predicted = (
        context["ratings"][game["home"]] - context["ratings"][game["away"]]
        + (0.0 if game["neutral"] else V0_PARAMETERS.home_field)
    )
    residual = max(
        -V0_PARAMETERS.margin_cap,
        min(V0_PARAMETERS.margin_cap, game["margin"] - predicted),
    )
    change = V0_PARAMETERS.learning_rate * residual / 2.0
    context["ratings"][game["home"]] += change
    context["ratings"][game["away"]] -= change


def _observations(own, opponent):
    if not own:
        return {name: (None, None) for name in PERFORMANCE_FEATURES}
    own_db = _sum(own, "attempts", "sacks_suffered")
    own_plays = _sum_value(own_db, _number(own, "carries"))
    own_explosive = _sum(own, "passing_20", "rushing_20")
    own_giveaways = _sum(own, "passing_interceptions", "fumbles_lost_total")
    opponent_db = _sum(opponent, "attempts", "sacks_suffered") if opponent else None
    opponent_plays = _sum_value(opponent_db, _number(opponent, "carries")) if opponent else None
    opponent_explosive = _sum(opponent, "passing_20", "rushing_20") if opponent else None
    opponent_giveaways = _sum(opponent, "passing_interceptions", "fumbles_lost_total") if opponent else None
    return {
        "passing_epa_per_play_for": (_number(own, "passing_epa"), own_db),
        "passing_epa_per_play_against": (
            -_number(opponent, "passing_epa") if opponent and _number(opponent, "passing_epa") is not None else None,
            opponent_db,
        ),
        "rushing_epa_per_play_for": (_number(own, "rushing_epa"), _number(own, "carries")),
        "rushing_epa_per_play_against": (
            -_number(opponent, "rushing_epa") if opponent and _number(opponent, "rushing_epa") is not None else None,
            _number(opponent, "carries") if opponent else None,
        ),
        "explosive_play_rate_for": (own_explosive, own_plays),
        "explosive_play_prevention_rate": (
            _subtract(opponent_plays, opponent_explosive), opponent_plays
        ),
        "sack_avoidance_rate": (
            _subtract(own_db, _number(own, "sacks_suffered")), own_db
        ),
        "sack_creation_rate": (
            _number(opponent, "sacks_suffered") if opponent else None, opponent_db
        ),
        "giveaway_avoidance_rate": (_subtract(own_plays, own_giveaways), own_plays),
        "takeaway_rate": (opponent_giveaways, opponent_plays),
    }


def _accumulate_qb(row, target):
    attempts = _number(row, "attempts")
    sacks = _number(row, "sacks_suffered")
    dropbacks = _sum_value(attempts, sacks)
    passing_epa = _number(row, "passing_epa")
    if passing_epa is not None and dropbacks is not None:
        target["passing_epa"] += passing_epa
        target["passing_epa_plays"] += dropbacks
    cpoe = _number(row, "passing_cpoe")
    if cpoe is not None and attempts is not None:
        target["cpoe_sum"] += cpoe * attempts
        target["cpoe_plays"] += attempts
    if dropbacks is not None:
        target["dropbacks"] += dropbacks
        if sacks is not None:
            target["sack_free_dropbacks"] += dropbacks - sacks
            target["sack_dropbacks"] += dropbacks
        interceptions = _number(row, "passing_interceptions")
        fumbles = _number(row, "sack_fumbles_lost")
        turnovers = _sum_value(interceptions, fumbles)
        if turnovers is not None:
            target["secure_dropbacks"] += dropbacks - turnovers
            target["security_dropbacks"] += dropbacks
    carries = _number(row, "carries")
    rushing_epa = _number(row, "rushing_epa")
    if carries is not None and rushing_epa is not None:
        target["carries"] += carries
        target["rushing_epa"] += rushing_epa


def _load_inputs(paths):
    inputs = {
        "team_rows": {}, "players": defaultdict(list),
        "rosters": defaultdict(list), "injuries": {}, "snaps": defaultdict(list),
        "current_roster_periods": set(),
    }
    for (name, source_season), path in paths.items():
        if name not in {
            "team_weekly_stats", "player_weekly_stats", "weekly_rosters",
            "current_roster", "injury_reports", "snap_counts",
        }:
            continue
        for original in open_csv(path):
            row = dict(original)
            season = int(row.get("season") or source_season)
            week = int(float(row.get("week") or 0))
            team = normalize_team(row["team"])
            row["team"] = team
            key = (season, week, team)
            if name == "team_weekly_stats":
                if key in inputs["team_rows"]:
                    raise ValueError(f"Duplicate team row: {season} week {week} {team}")
                inputs["team_rows"][key] = row
            elif name == "player_weekly_stats":
                inputs["players"][key].append(row)
            elif name in {"weekly_rosters", "current_roster"}:
                inputs["rosters"][key].append(row)
                if name == "current_roster":
                    inputs["current_roster_periods"].add(key)
            elif name == "injury_reports":
                injury_key = (*key, row.get("gsis_id", "").strip())
                if injury_key in inputs["injuries"]:
                    raise ValueError(f"Duplicate injury row: {season} week {week} {team}")
                inputs["injuries"][injury_key] = row
            elif name == "snap_counts":
                inputs["snaps"][key].append(row)
    return inputs


def _load_games(paths):
    try:
        path = paths[("schedule_results", None)]
    except KeyError as error:
        raise ValueError("Missing schedule_results source") from error
    games, seen = [], set()
    for row in open_csv(path):
        if row.get("game_type") != "REG":
            continue
        season = int(row["season"])
        if not FIRST_SEASON <= season <= LAST_SEASON:
            continue
        game_id = row["game_id"].strip()
        if game_id in seen:
            raise ValueError(f"Duplicate game: {game_id}")
        seen.add(game_id)
        if not row.get("home_score", "").strip() or not row.get("away_score", "").strip():
            continue
        home, away = normalize_team(row["home_team"]), normalize_team(row["away_team"])
        if home == away:
            raise ValueError(f"Invalid teams for {game_id}")
        kickoff_dt = _kickoff(row.get("gameday", ""), row.get("gametime", ""))
        games.append({
            "game_id": game_id,
            "season": season,
            "week": int(float(row["week"])),
            "kickoff_dt": kickoff_dt,
            "kickoff": kickoff_dt.astimezone(EASTERN).isoformat(timespec="minutes"),
            "home": home,
            "away": away,
            "margin": float(row["home_score"]) - float(row["away_score"]),
            "neutral": row.get("location", "").strip().casefold() == "neutral",
            "home_rest": _number(row, "home_rest"),
            "away_rest": _number(row, "away_rest"),
            "home_coach": row.get("home_coach", "").strip(),
            "away_coach": row.get("away_coach", "").strip(),
        })
    return sorted(games, key=lambda game: (game["kickoff_dt"], game["game_id"]))


def _validate_team_row(row, game, opponent):
    if not row:
        return
    if row.get("game_id", "").strip() != game["game_id"]:
        raise ValueError(f"Team row game mismatch: {game['game_id']}")
    if normalize_team(row["opponent_team"]) != opponent:
        raise ValueError(f"Team row opponent mismatch: {game['game_id']}")


def _best_qb(qbs):
    if not qbs:
        return None
    return min(qbs, key=lambda item: (-_qb_sort_value(item[1]), item[0]))


def _qb_sort_value(player):
    value = player.get("qb_value", player.get("qb_epa_per_dropback"))
    return float(value) if value is not None else -math.inf


def _qb_feature(player, name):
    if name == "qb_epa_per_dropback":
        return player.get(name, player.get("qb_value"))
    return player.get(name)


def _probability(player):
    value = float(player.get("probability", 1.0))
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"Availability probability outside [0, 1]: {value}")
    return value


def _expected_qb_feature(depth_chart, name):
    total, remaining = 0.0, 1.0
    for _, player in depth_chart:
        weight = remaining * _probability(player)
        value = _qb_feature(player, name)
        if weight and value is None:
            return None
        if value is not None:
            total += weight * value
        remaining -= weight
    return None if remaining > 1e-12 else total


def _unavailable_share(players, name):
    total = 0.0
    for player in players:
        missing = 1.0 - _probability(player)
        if not missing:
            continue
        share = player.get(name)
        if share is None:
            return None
        total += float(share) * missing
    return total


def _roster_share(players, last_team, team, name, denominator, incoming):
    if denominator <= 0:
        return None
    numerator = 0.0
    for player_id, player in players.items():
        previous = last_team.get(player_id)
        selected = previous is not None and previous != team if incoming else previous == team
        if not selected:
            continue
        numerator += (
            (player["offense_snap_share"] or 0.0) + (player["defense_snap_share"] or 0.0)
            if name is None else (player[name] or 0.0)
        )
    return numerator / denominator


def _difference(home, away):
    if home.keys() != away.keys():
        raise ValueError("Home and away feature states do not align")
    return {
        name: home[name] - away[name]
        if home[name] is not None and away[name] is not None else None
        for name in home
    }


def _matchup_features(home, away, game):
    features = _difference(home, away)
    features["home_field"] = 0.0 if game["neutral"] else 1.0
    features["rest_difference"] = _rest_difference(
        game["home_rest"], game["away_rest"]
    )
    return features


def _rest_difference(home, away):
    if home is None or away is None:
        return None
    return max(-7.0, min(7.0, home - away)) / 7.0


def _number(row, key):
    if not row:
        return None
    value = row.get(key, "")
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid numeric {key}: {value}") from error


def _sum(row, *keys):
    values = [_number(row, key) for key in keys]
    return sum(values) if all(value is not None for value in values) else None


def _sum_value(first, second):
    return first + second if first is not None and second is not None else None


def _subtract(first, second):
    return first - second if first is not None and second is not None else None


def _kickoff(day, time):
    day, time = day.strip(), time.strip()
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %I:%M %p"):
        try:
            local = datetime.strptime(f"{day} {time or '00:00'}", pattern)
            return local.replace(tzinfo=EASTERN).astimezone(timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"Invalid kickoff: {day} {time}")


def _parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=EASTERN)
    return parsed.astimezone(timezone.utc)
