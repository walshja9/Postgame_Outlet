#!/usr/bin/env python3
"""Shadow-only Postgame Outlet team-margin model and backtest gate."""

import csv
import io
import itertools
from collections import defaultdict
from dataclasses import asdict, dataclass


ALIASES = {"OAK": "LV", "SD": "LAC", "STL": "LAR", "LA": "LAR"}
REQUIRED_COLUMNS = {
    "game_id", "season", "game_type", "gameday", "away_team",
    "away_score", "home_team", "home_score", "location",
}
TRAIN_START, TRAIN_END = 2002, 2017
EVAL_START, EVAL_END = 2018, 2025
CURRENT_TEAMS = tuple(sorted(
    "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR "
    "LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split()
))
LEARNING_RATES = (0.10, 0.15, 0.20, 0.25, 0.30)
OFFSEASON_RETENTIONS = (0.50, 0.60, 0.70, 0.80, 0.90)
HOME_FIELDS = (1.5, 2.0, 2.5, 3.0)
MARGIN_CAPS = (20.0, 28.0, 35.0, 1000.0)


@dataclass(frozen=True)
class Game:
    game_id: str
    season: int
    gameday: str
    away: str
    home: str
    margin: float
    neutral: bool


@dataclass(frozen=True, order=True)
class Parameters:
    learning_rate: float
    offseason_retention: float
    home_field: float
    margin_cap: float


@dataclass(frozen=True)
class Prediction:
    game_id: str
    season: int
    actual: float
    predicted: float


def parse_games(text, first_season=1999, last_season=2025):
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
    if missing:
        raise ValueError("Missing game columns: " + ", ".join(sorted(missing)))
    games, seen = [], set()
    for row in reader:
        if row["game_type"] != "REG" or not row["home_score"] or not row["away_score"]:
            continue
        season = int(row["season"])
        if not first_season <= season <= last_season:
            continue
        game_id = row["game_id"]
        if game_id in seen:
            raise ValueError(f"Duplicate completed game: {game_id}")
        seen.add(game_id)
        home = ALIASES.get(row["home_team"], row["home_team"])
        away = ALIASES.get(row["away_team"], row["away_team"])
        if not home or not away or home == away:
            raise ValueError(f"Invalid teams for {game_id}")
        games.append(Game(
            game_id,
            season,
            row["gameday"],
            away,
            home,
            float(row["home_score"]) - float(row["away_score"]),
            row["location"].strip().lower() == "neutral",
        ))
    if not games:
        raise ValueError("No completed regular-season games found")
    return sorted(games, key=lambda game: (game.gameday, game.game_id))


def walk_forward(games, parameters):
    ratings = defaultdict(float)
    predictions = []
    current_season = None
    for game in games:
        if current_season is not None and game.season != current_season:
            seasons = game.season - current_season
            for team in ratings:
                ratings[team] *= parameters.offseason_retention ** seasons
        current_season = game.season
        home_field = 0.0 if game.neutral else parameters.home_field
        predicted = ratings[game.home] - ratings[game.away] + home_field
        predictions.append(Prediction(
            game.game_id, game.season, game.margin, predicted,
        ))
        residual = max(
            -parameters.margin_cap,
            min(parameters.margin_cap, game.margin - predicted),
        )
        change = parameters.learning_rate * residual / 2
        ratings[game.home] += change
        ratings[game.away] -= change
    return predictions, dict(ratings)


def mean_absolute_error(predictions, first_season, last_season):
    errors = [
        abs(value.actual - value.predicted)
        for value in predictions
        if first_season <= value.season <= last_season
    ]
    if not errors:
        raise ValueError("No predictions in requested evaluation window")
    return sum(errors) / len(errors), len(errors)


def select_parameters(games):
    training_games = [game for game in games if game.season <= TRAIN_END]
    candidates = []
    for values in itertools.product(
        LEARNING_RATES, OFFSEASON_RETENTIONS, HOME_FIELDS, MARGIN_CAPS,
    ):
        parameters = Parameters(*values)
        predictions, _ = walk_forward(training_games, parameters)
        score, _ = mean_absolute_error(predictions, TRAIN_START, TRAIN_END)
        candidates.append((score, parameters))
    return min(candidates)[1]


def select_baseline_home_field(games):
    training = [game for game in games if TRAIN_START <= game.season <= TRAIN_END]
    return min(
        (
            sum(abs(game.margin - (0.0 if game.neutral else value)) for game in training)
            / len(training),
            value,
        )
        for value in HOME_FIELDS
    )[1]


def baseline_predictions(games, home_field):
    return [
        Prediction(
            game.game_id,
            game.season,
            game.margin,
            0.0 if game.neutral else home_field,
        )
        for game in games
    ]


def evaluation_metrics(model, baseline):
    aggregate_model, count = mean_absolute_error(model, EVAL_START, EVAL_END)
    aggregate_baseline, _ = mean_absolute_error(baseline, EVAL_START, EVAL_END)
    seasons = []
    for season in range(EVAL_START, EVAL_END + 1):
        model_mae, games = mean_absolute_error(model, season, season)
        baseline_mae, _ = mean_absolute_error(baseline, season, season)
        seasons.append({
            "season": season,
            "games": games,
            "model_mae": round(model_mae, 4),
            "baseline_mae": round(baseline_mae, 4),
            "improvement": round(baseline_mae - model_mae, 4),
        })
    aggregate = {
        "games": count,
        "model_mae": round(aggregate_model, 4),
        "baseline_mae": round(aggregate_baseline, 4),
        "improvement": round(aggregate_baseline - aggregate_model, 4),
    }
    return aggregate, seasons


def gate_checks(aggregate, seasons, team_count):
    return {
        "at_least_2000_holdout_games": aggregate["games"] >= 2000,
        "all_32_current_teams": team_count == 32,
        "aggregate_beats_baseline": (
            aggregate["model_mae"] < aggregate["baseline_mae"]
        ),
        "every_season_beats_baseline": all(
            season["model_mae"] < season["baseline_mae"]
            for season in seasons
        ),
    }


def build_analysis(games):
    parameters = select_parameters(games)
    baseline_home_field = select_baseline_home_field(games)
    model_predictions, ratings = walk_forward(games, parameters)
    baseline = baseline_predictions(games, baseline_home_field)
    aggregate, seasons = evaluation_metrics(model_predictions, baseline)
    shadow = [
        {
            "team": team,
            "rating": round(
                ratings.get(team, 0.0) * parameters.offseason_retention,
                3,
            ),
        }
        for team in CURRENT_TEAMS
        if team in ratings
    ]
    shadow.sort(key=lambda row: (-row["rating"], row["team"]))
    checks = gate_checks(aggregate, seasons, len(shadow))
    report = {
        "format_version": 1,
        "model": "PGO team margin v0",
        "status": "PASS" if all(checks.values()) else "HOLD",
        "scope": {
            "included": "completed regular-season team results",
            "excluded": [
                "Sean McCabe QB/offense/defense ratings",
                "player and unit inputs",
                "market spreads and odds",
            ],
        },
        "windows": {
            "warmup": "1999-2001",
            "training": "2002-2017",
            "evaluation": "2018-2025",
            "ratings": "2026 preseason",
        },
        "parameters": asdict(parameters),
        "baseline": {"home_field": baseline_home_field},
        "aggregate": aggregate,
        "seasons": seasons,
        "checks": checks,
    }
    return report, shadow
