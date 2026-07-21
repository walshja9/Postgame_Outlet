#!/usr/bin/env python3
"""Shadow-only Postgame Outlet team-margin model and backtest gate."""

import csv
import io
from collections import defaultdict
from dataclasses import dataclass


ALIASES = {"OAK": "LV", "SD": "LAC", "STL": "LAR", "LA": "LAR"}
REQUIRED_COLUMNS = {
    "game_id", "season", "game_type", "gameday", "away_team",
    "away_score", "home_team", "home_score", "location",
}


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
