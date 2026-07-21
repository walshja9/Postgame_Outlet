"""Leakage-safe chronological features for the shadow PGO challenger."""

import math
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import groupby
from zoneinfo import ZoneInfo

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
    available_periods = set(inputs["current_roster_periods"])
    for game in _load_games(paths):
        if game["kickoff_dt"] <= as_of_dt:
            available_periods.update({
                (game["season"], game["week"], game["home"]),
                (game["season"], game["week"], game["away"]),
            })
    periods = {}
    for season, week, team in inputs["rosters"]:
        available = season < as_of_year or (season, week, team) in available_periods
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
            features = _difference(home[1], away[1])
            features["home_field"] = 0.0 if game["neutral"] else 1.0
            features["rest_difference"] = _rest_difference(
                game["home_rest"], game["away_rest"]
            )
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
