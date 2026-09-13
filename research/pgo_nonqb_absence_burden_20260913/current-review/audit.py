"""Replay the pinned current slate for non-QB absence-source readiness.

The legacy role values below are coverage hints only: they omit explicit zero
games and use a maximum-player denominator, so they are not the direct provider
percentages defined by this study's charter. This audit is read-only.
"""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import pgo_offensive_inventory as offensive_inventory
import pgo_season as season
import pgo_sources
from pgo_season_availability import load_availability
from pgo_season_rollover import load_archive
from research.pgo_defender_inventory_20260911 import inventory as defender_inventory
from research.pgo_nonqb_availability_20260909.prepare_roles import role_observations
from research.pgo_opening_night_20260909.identity import source_package


ROOT = REPO / "docs/evidence/season-2026"
EXPECTED_HEAD = "70c54db3de2e4b31dfb4c3b498a7eb0250a84ebb"
IDENTITY_MANIFEST = REPO / (
    "research/pgo_opening_night_20260909/identity/"
    "package-complete-20260909/source-manifest.json"
)
IDENTITY_SHA = "17f1dec348ad4992dbe32c6e5d54461ef8bd858e7e9d1775e37951385c492f2a"


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def file_record(path):
    path = Path(path)
    raw = path.read_bytes()
    try:
        label = path.relative_to(REPO).as_posix()
    except ValueError:
        label = str(path)
    return {"path": label, "bytes": len(raw), "sha256": sha256(raw)}


def legacy_offense_hints():
    paths = source_package.load_sources(IDENTITY_MANIFEST, IDENTITY_SHA)
    collision_path = REPO / (
        "research/pgo_snap_identity_repair_20260909/"
        "source-conflict-inventory.json"
    )
    colliding = json.loads(collision_path.read_bytes())["colliding_gsis"]
    rows = role_observations(
        pgo_sources.open_csv(paths["weekly_rosters", 2025]),
        pgo_sources.open_csv(paths["snap_counts", 2025]),
        colliding,
    )
    values = {
        player_id: statistics.median([row["share"] for row in history[-4:]])
        for (player_id, unit), history in rows.items()
        if unit == "offense"
    }
    return values, {
        "identity_manifest": file_record(IDENTITY_MANIFEST),
        "weekly_rosters_2025": file_record(paths["weekly_rosters", 2025]),
        "snap_counts_2025": file_record(paths["snap_counts", 2025]),
        "collision_inventory": file_record(collision_path),
        "semantic_warning": (
            "Coverage hint only. role_observations keeps positive observations "
            "and divides by a maximum-player unit-snap denominator. It does not "
            "supply direct provider offense_pct values and does not preserve "
            "explicit zero games."
        ),
    }


def documented_observations(player):
    return [
        observation
        for observation in player["observations"]
        if observation.get("status") in {"OUT", "INACTIVE"}
        and str(observation.get("injury") or "").strip()
    ]


def unit_rows(unit, snapshot, teams, offense_hints):
    key = "players" if unit == "offense" else "defenders"
    result = []
    for team in snapshot["teams"]:
        if team["team"] not in teams:
            continue
        for original in team[key]:
            player = dict(original)
            player["team"] = team["team"]
            player["legacy_hint"] = (
                offense_hints.get(player["gsis_id"])
                if unit == "offense"
                else player["prior_role_share"]
            )
            player["documented_observations"] = documented_observations(player)
            result.append(player)
    return result


def summarize_unit(rows):
    documented = [row for row in rows if row["documented_observations"]]
    out = [
        row for row in documented
        if any(obs["status"] == "OUT" for obs in row["documented_observations"])
    ]
    inactive = [
        row for row in documented
        if any(obs["status"] == "INACTIVE" for obs in row["documented_observations"])
        and row not in out
    ]
    raw_inactive = [row for row in rows if "INACTIVE" in row["availability_statuses"]]
    known = [row["legacy_hint"] for row in documented if row["legacy_hint"] is not None]
    return {
        "inventory_rows": len(rows),
        "documented_injury_out": len(out),
        "documented_injury_inactive": len(inactive),
        "raw_inactive_without_documented_injury": sum(
            not row["documented_observations"] for row in raw_inactive
        ),
        "reserve_roster_context": sum(row["roster_status"] == "RES" for row in rows),
        "uncertain_not_confirmed_absent": sum(row["uncertain"] for row in rows),
        "depth_status_counts": dict(sorted(Counter(row["depth_status"] for row in rows).items())),
        "missing_current_role": sum(row["depth_status"] != "LISTED" for row in rows),
        "legacy_positive_only_role_hint_known_all_players": sum(
            row["legacy_hint"] is not None for row in rows
        ),
        "legacy_positive_only_role_hint_missing_all_players": sum(
            row["legacy_hint"] is None for row in rows
        ),
        "legacy_positive_only_role_hint_known_documented_absences": len(known),
        "legacy_positive_only_role_hint_missing_documented_absences": len(documented) - len(known),
        "legacy_positive_only_role_hint_sum_for_diagnostic_only": math.fsum(known),
        "documented_absence_players": [
            {
                "team": row["team"], "gsis_id": row["gsis_id"],
                "name": row["name"], "position": row["position"],
                "depth_status": row["depth_status"],
                "legacy_positive_only_role_hint": row["legacy_hint"],
                "observations": row["documented_observations"],
            }
            for row in documented
        ],
        "missing_legacy_hint_players": [
            {
                "team": row["team"], "gsis_id": row["gsis_id"],
                "name": row["name"], "position": row["position"],
            }
            for row in documented if row["legacy_hint"] is None
        ],
        "direct_provider_percentage_history_computed": False,
        "direct_provider_feature_value": None,
    }


def per_game_rows(games, offense, defense, offense_snapshot, package_games):
    offense_by_team = {team: [] for game in games for team in (game["away"], game["home"])}
    defense_by_team = {team: [] for team in offense_by_team}
    for row in offense:
        offense_by_team[row["team"]].append(row)
    for row in defense:
        defense_by_team[row["team"]].append(row)
    team_context = {team["team"]: team for team in offense_snapshot["teams"]}
    rows = []
    for game in sorted(games, key=lambda item: (item["kickoff"], item["game_id"])):
        teams = [game["away"], game["home"]]
        row = {key: game[key] for key in ("game_id", "away", "home", "kickoff", "lock_at")}
        row["current_availability_archive"] = game["game_id"] in package_games
        row["teams"] = {
            team: {
                "report_status": team_context[team]["report_status"],
                "final_inactives_status": team_context[team]["final_inactives_status"],
            }
            for team in teams
        }
        row["offense"] = summarize_unit(
            [player for team in teams for player in offense_by_team[team]]
        )
        row["defense"] = summarize_unit(
            [player for team in teams for player in defense_by_team[team]]
        )
        rows.append(row)
    return rows


def ascii_name(value):
    replacements = {"\u00e9": "e", "\u2019": "'", "\u2013": "-", "\u2014": "-"}
    return "".join(replacements.get(char, char if ord(char) < 128 else "?") for char in value)


def markdown(result):
    lines = [
        "# Current prospective readiness review", "",
        f"Audit status: **{result['status']}**.", "",
        "The pinned current archive replays successfully, but it cannot yet produce the charter's new confirmed-absence feature. The direct provider `offense_pct` and `defense_pct` history, including explicit zero games, was not built or calculated in this audit. No coefficient was fit and no source or current-state file was changed.",
        "", "## Current evidence", "",
        f"- HEAD: `{result['repo_head']}`",
        f"- Current pointer: `{result['custody']['pointer']['path']}`; checked `{result['custody']['state_checked_at']}`; pointer unchanged during replay: `{str(result['custody']['current_unchanged']).lower()}`.",
        f"- Slate: {result['slate']['issued_games']} issued games, {result['slate']['verified_finals']} finals, and {result['slate']['future_games']} future games. Offensive and defensive postgame usage each have {result['slate']['usage_joined_games']} joined games; {result['slate']['pending_games']} games remain pending.",
        f"- Availability: {result['availability']['archived_current_games']}/{result['availability']['future_games']} future games and {result['availability']['teams_with_current_archive']}/{result['availability']['future_teams']} teams have the current archive. Missing: {', '.join(result['availability']['teams_without_current_archive'])} ({', '.join(result['availability']['games_without_current_archive'])}).",
        f"- Team report statuses: {result['availability']['team_report_status_counts']}. Final inactive statuses: {result['availability']['final_inactives_status_counts']}.",
        f"- Documented injury OUT: offense {result['units']['offense']['documented_injury_out']}, defense {result['units']['defense']['documented_injury_out']}. Documented injury INACTIVE: offense {result['units']['offense']['documented_injury_inactive']}, defense {result['units']['defense']['documented_injury_inactive']}.",
        "", "## Legacy coverage hints", "",
        "These are diagnostics from the old `role_observations` path. They keep positive observations and use a maximum-player denominator. They are not direct provider percentages, they do not preserve explicit zero games, and their sums are not values of the proposed feature.",
        "",
        f"- Offense: {result['units']['offense']['legacy_positive_only_role_hint_known_all_players']}/{result['units']['offense']['inventory_rows']} current players and {result['units']['offense']['legacy_positive_only_role_hint_known_documented_absences']}/{result['units']['offense']['documented_injury_out'] + result['units']['offense']['documented_injury_inactive']} documented absences have a legacy hint.",
        f"- Defense: {result['units']['defense']['legacy_positive_only_role_hint_known_all_players']}/{result['units']['defense']['inventory_rows']} current players and {result['units']['defense']['legacy_positive_only_role_hint_known_documented_absences']}/{result['units']['defense']['documented_injury_out'] + result['units']['defense']['documented_injury_inactive']} documented absences have a legacy hint.",
        "- Missing documented-absence legacy hints: " + "; ".join(
            f"{row['team']} {ascii_name(row['name'])} ({row['position']})"
            for unit in ("offense", "defense")
            for row in result["units"][unit]["missing_legacy_hint_players"]
        ) + ".",
        "", "## Per-game report and absence counts", "",
        "| Game | Reports (away/home) | Final inactive lists | Off OUT/INA | Def OUT/INA | Legacy hints all O;D (known/missing) | Documented absences (known/missing) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for game in result["per_game"]:
        away, home = game["away"], game["home"]
        reports = f"{away} {game['teams'][away]['report_status']}; {home} {game['teams'][home]['report_status']}"
        inactives = f"{away} {game['teams'][away]['final_inactives_status']}; {home} {game['teams'][home]['final_inactives_status']}"
        offense, defense = game["offense"], game["defense"]
        known = sum(unit["legacy_positive_only_role_hint_known_documented_absences"] for unit in (offense, defense))
        missing = sum(unit["legacy_positive_only_role_hint_missing_documented_absences"] for unit in (offense, defense))
        missing_names = [
            f"{item['team']} {ascii_name(item['name'])}"
            for unit in (offense, defense)
            for item in unit["missing_legacy_hint_players"]
        ]
        all_hints = "; ".join(
            f"{unit_name} {unit['legacy_positive_only_role_hint_known_all_players']}/{unit['legacy_positive_only_role_hint_missing_all_players']}"
            for unit_name, unit in (("O", offense), ("D", defense))
        )
        hint = f"{known}/{missing}" + (f" ({'; '.join(missing_names)})" if missing_names else "")
        lines.append(
            f"| `{game['game_id']}` | {reports} | {inactives} | {offense['documented_injury_out']}/{offense['documented_injury_inactive']} | {defense['documented_injury_out']}/{defense['documented_injury_inactive']} | {all_hints} | {hint} |"
        )
    lines.extend([
        "", "The legacy columns report known/missing coverage. The last column applies only to documented absences and names any missing player. Both are coverage warnings, not feature calculations.",
        "", "## Charter gaps", "",
    ])
    lines.extend(f"- {reason}" for reason in result["decision"]["blocking_gaps"])
    lines.extend([
        "", "The current evidence therefore supports collector and source-gap review only. The study remains source-admission blocked and has no admissible numerical feature values or training rows.", "",
    ])
    return "\n".join(lines)


def main(output, report):
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if head != EXPECTED_HEAD:
        raise ValueError(f"Unexpected HEAD: {head}")
    pointer_raw = (ROOT / "current.json").read_bytes()
    pointer = json.loads(pointer_raw)
    state, manifest = load_archive(ROOT, pointer)
    if state != season.load_current(ROOT):
        raise ValueError("Current loader and pinned archive differ")
    manifest_path = ROOT / pointer["path"] / "manifest.json"
    state_name = next(iter(manifest["files"]))
    state_path = ROOT / pointer["path"] / state_name
    offense_snapshot, offense_roster = offensive_inventory.load_inventory(ROOT, pointer)
    defense_snapshot, defense_roster = defender_inventory.load_inventory(ROOT, pointer)
    if offense_snapshot["inventory_version"] != 2 or defense_snapshot["inventory_version"] != 2:
        raise ValueError("Current inventories are not both version 2")
    if {row["game_id"] for row in offense_snapshot["games"]} != {row["game_id"] for row in defense_snapshot["games"]}:
        raise ValueError("Offensive and defensive future games differ")

    current_games = [game for week in state["weeks"] for game in week["games"]]
    final_ids = {row["game_id"] for row in state["results"]}
    future_games = [game for game in current_games if game["game_id"] not in final_ids]
    expected_games = [
        {key: game[key] for key in ("game_id", "season", "week", "game_type", "home", "away", "kickoff", "lock_at")}
        for game in future_games
    ]
    if offense_snapshot["games"] != expected_games:
        raise ValueError("Offensive prospective games differ from current future games")
    future_ids = {game["game_id"] for game in future_games}
    future_teams = {team for game in future_games for team in (game["home"], game["away"])}
    state_games = {game["game_id"]: game for game in current_games}

    availability_refs = sorted({state_games[key].get("availability", {}).get("source_archive") for key in future_ids} - {None})
    packages = [load_availability(ROOT / ref) for ref in availability_refs]
    package_games = {key for package in packages for key in package["games"]}
    archive_teams = {
        team for game_id in package_games
        for team in (state_games[game_id]["home"], state_games[game_id]["away"])
    }
    source_pins, seen = [], set()
    for snapshot in (offense_snapshot, defense_snapshot):
        for ref in snapshot["sources"]:
            key = (ref["path"], ref["sha256"])
            if key in seen:
                continue
            seen.add(key)
            path = REPO / ref["path"] if ref["path"].startswith("docs/") else ROOT / ref["path"]
            actual = file_record(path)
            if actual["sha256"] != ref["sha256"] or ("bytes" in ref and actual["bytes"] != ref["bytes"]):
                raise ValueError("Inventory source pin differs")
            source_pins.append({"ref": ref, "actual": actual})

    starter_rows = []
    for game in current_games:
        for row in game.get("starter_announcements") or []:
            source_ref = row["source"]
            raw = (ROOT / source_ref["path"]).read_bytes()
            if sha256(raw) != source_ref["sha256"] or len(raw) != source_ref["bytes"]:
                raise ValueError("Starter source bytes differ")
            starter_rows.append({
                "game_id": game["game_id"], "team": row["team"],
                "gsis_id": row["gsis_id"], "full_name": row["full_name"],
                "source": source_ref,
            })

    offense_hints, history_sources = legacy_offense_hints()
    offense = unit_rows("offense", offense_snapshot, future_teams, offense_hints)
    defense = unit_rows("defense", defense_snapshot, future_teams, offense_hints)
    units = {"offense": summarize_unit(offense), "defense": summarize_unit(defense)}
    units["offense"]["usage_identity_status_counts"] = dict(sorted(Counter(
        player["usage_identity"]["status"] for player in offense
    ).items()))
    marked = [player for player in defense if player["confirmed_unavailable"]]
    units["defense"]["saved_confirmed_unavailable_count"] = len(marked)
    units["defense"]["saved_confirmed_unavailable_roster_statuses"] = dict(sorted(Counter(
        player["roster_status"] for player in marked
    ).items()))
    units["defense"]["saved_field_semantic_warning"] = (
        "confirmed_unavailable includes reserve-roster context and is not the charter's documented injury OUT/INACTIVE population."
    )
    per_game = per_game_rows(future_games, offense, defense, offense_snapshot, package_games)
    report_statuses = Counter(team["report_status"] for team in offense_snapshot["teams"] if team["team"] in future_teams)
    inactive_statuses = Counter(team["final_inactives_status"] for team in offense_snapshot["teams"] if team["team"] in future_teams)
    availability_sources = [source for package in packages for source in package["sources"]]
    offense_usage, defense_usage = state["offensive_usage"], state["injury_usage"]
    usage_joined = min(
        offense_usage["metrics"]["joined"], defense_usage["metrics"]["joined"]
    )
    pending = max(offense_usage["pending_games"], defense_usage["pending_games"])
    first_lock = min(season.utc(game["lock_at"]) for game in future_games)

    result = {
        "status": "BLOCKED_DIRECT_PROVIDER_HISTORY_NOT_ADMITTED",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_head": head,
        "custody": {
            "current": file_record(ROOT / "current.json"), "pointer": pointer,
            "manifest": file_record(manifest_path), "manifest_created_at": manifest["created_at"],
            "state": file_record(state_path), "state_checked_at": state["checked_at"],
            "source_pins": source_pins, "current_unchanged": None,
        },
        "replay": {
            "offensive_inventory": {"status": "PASS", "version": offense_snapshot["inventory_version"], "games": len(offense_snapshot["games"]), "teams": len(offense_snapshot["teams"]), "roster_rows": len(offense_roster)},
            "defensive_inventory": {"status": "PASS", "version": defense_snapshot["inventory_version"], "games": len(defense_snapshot["games"]), "teams": len(defense_snapshot["teams"]), "roster_rows": len(defense_roster)},
        },
        "timeline": {
            "first_future_kickoff": min(game["kickoff"] for game in future_games),
            "first_future_lock": first_lock.isoformat(),
            "state_check_to_first_lock_seconds": (first_lock - season.utc(state["checked_at"])).total_seconds(),
            "durable_to_first_lock_seconds": (first_lock - season.utc(manifest["created_at"])).total_seconds(),
            "offensive_generated_at": offense_snapshot["generated_at"],
            "defensive_generated_at": defense_snapshot["generated_at"],
            "depth_snapshot_at_counts": dict(sorted(Counter(team["depth_snapshot_at"] for team in offense_snapshot["teams"] if team["team"] in future_teams).items())),
        },
        "slate": {
            "issued_games": len(current_games), "verified_finals": len(state["results"]),
            "final_game_ids": sorted(final_ids), "future_games": len(future_games),
            "future_teams": len(future_teams), "usage_joined_games": usage_joined,
            "pending_games": pending, "offensive_usage": offense_usage,
            "defensive_usage": defense_usage,
        },
        "availability": {
            "future_games": len(future_games), "archived_current_games": len(package_games),
            "games_without_current_archive": sorted(future_ids - package_games),
            "future_teams": len(future_teams), "teams_with_current_archive": len(archive_teams),
            "teams_without_current_archive": sorted(future_teams - archive_teams),
            "team_report_status_counts": dict(sorted(report_statuses.items())),
            "final_inactives_status_counts": dict(sorted(inactive_statuses.items())),
            "archive_checked_at": sorted({package["checked_at"] for package in packages}),
            "source_kind_counts": dict(sorted(Counter(source["kind"] for source in availability_sources).items())),
            "http_status_counts": dict(sorted(Counter(str(source["status"]) for source in availability_sources).items())),
            "source_started_at_min": min(source["started_at"] for source in availability_sources),
            "source_captured_at_max": max(source["captured_at"] for source in availability_sources),
            "starter_announcements": starter_rows,
        },
        "legacy_history_sources": history_sources, "units": units, "per_game": per_game,
        "decision": {
            "direct_provider_feature_values_computed": False,
            "admissible_numerical_rows": 0,
            "blocking_gaps": [
                "The direct provider offense_pct and defense_pct history required by the charter has not been built or replayed, so explicit zero games and the required denominator are unverified.",
                "DEN and KC have no current versioned availability archive for 2026_01_DEN_KC; report completeness is 26 of 28 future teams.",
                "All 28 future-team final-inactive statuses are UNKNOWN; documented game-day inactive absences are not yet observed.",
                "The 14 prospective games have no final targets or postgame usage joins. The two existing finals predate eligible inventories.",
                "The legacy positive-only role path lacks hints for NO TE Oscar Delp and PHI TE Eli Stowers. This is a coverage warning only and does not establish whether direct provider history exists.",
                "The saved defensive confirmed_unavailable population mixes 121 reserve-roster rows with 13 documented OUT rows and cannot define the charter population.",
                "Historical injury timing, identity, completeness, and source-vintage gates remain unadmitted; no historical substitution or fitting is allowed.",
                "The prospective minimums of 200 games, 12 weeks, all 32 teams, 50 nonzero observations per unit difference, and a rank-two feature matrix are unmet.",
            ],
        },
    }
    result["custody"]["current_unchanged"] = (ROOT / "current.json").read_bytes() == pointer_raw
    if not result["custody"]["current_unchanged"]:
        raise ValueError("Current pointer changed during audit")
    output, report = Path(output), Path(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.resolve() != Path(__file__).resolve().parent or report.parent.resolve() != output.parent.resolve():
        raise ValueError("Outputs must be written beside this audit script")
    with output.open("x", encoding="ascii", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False, ensure_ascii=True)
        handle.write("\n")
    with report.open("x", encoding="ascii", newline="\n") as handle:
        handle.write(markdown(result))
    print(json.dumps({
        "status": result["status"], "future_games": len(future_games),
        "report_coverage": f"{len(archive_teams)}/{len(future_teams)}",
        "offense_out": units["offense"]["documented_injury_out"],
        "defense_out": units["defense"]["documented_injury_out"],
        "documented_inactive": units["offense"]["documented_injury_inactive"] + units["defense"]["documented_injury_inactive"],
        "admissible_numerical_rows": 0,
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    main(**vars(parser.parse_args()))
