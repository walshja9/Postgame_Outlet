"""Independent half-PPR fantasy baselines built from frozen nflverse files."""

import math

from pgo_model import SOURCE_URL
from pgo_sources import SourceSpec


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
