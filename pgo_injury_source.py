#!/usr/bin/env python3
"""Import a frozen official NFL availability ledger into the PGO overlay."""

import argparse
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pgo_challenger
import pgo_model
import pgo_sources
from release_ratings import atomic_write_text


SNAPSHOT_SCHEMA_VERSION = 2
STATUS_BLANKS = frozenset(("", "-", "n/a", "na"))
SOURCE_KINDS = frozenset((
    "formal_injury_report",
    "preseason_availability_list",
    "reserve_list",
    "official_news",
    "no_formal_report",
))


def _text(value):
    return "" if value is None else str(value).strip()


def _status(value):
    value = _text(value)
    return "" if value.casefold() in STATUS_BLANKS else value


def _https_url(value):
    value = _text(value)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Injury source URLs must use HTTPS")
    return value


def _parse_timestamp(value, label):
    value = _text(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Invalid {label}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} requires a timezone")
    return parsed.astimezone(timezone.utc)


def load_snapshot(path):
    path = Path(path)
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, TypeError, ValueError) as error:
        raise ValueError("Invalid injury source snapshot JSON") from error
    if not isinstance(data, dict):
        raise ValueError("Injury source snapshot must be an object")

    source = _text(data.get("source"))
    source_as_of = _text(data.get("source_as_of"))
    if not source or not source_as_of:
        raise ValueError("Injury source snapshot metadata is incomplete")
    capture_time = _parse_timestamp(source_as_of, "source_as_of timestamp")

    team_sources_raw = data.get("team_sources")
    if not isinstance(team_sources_raw, list):
        raise ValueError("Injury source snapshot team_sources must be a list")
    team_sources = {}
    for raw_source in team_sources_raw:
        if not isinstance(raw_source, dict):
            raise ValueError("Injury source team records must be objects")
        team_raw = _text(raw_source.get("team"))
        try:
            team = pgo_sources.normalize_team(team_raw)
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("Invalid injury source team coverage") from error
        if team_raw != team or team not in pgo_model.CURRENT_TEAMS:
            raise ValueError("Injury source teams must use canonical abbreviations")
        if team in team_sources:
            raise ValueError(f"Duplicate injury source team: {team}")
        source_kind = _text(raw_source.get("source_kind"))
        if source_kind not in SOURCE_KINDS:
            raise ValueError(f"Unknown injury source kind: {source_kind}")
        source_url = _https_url(raw_source.get("source_url"))
        published_at = _text(raw_source.get("source_published_at"))
        if published_at:
            published_time = _parse_timestamp(
                published_at, "source publication timestamp"
            )
            if published_time > capture_time:
                raise ValueError("Injury source publication is later than snapshot")
        coverage_note = _text(raw_source.get("coverage_note"))
        if not coverage_note:
            raise ValueError("Injury source coverage note is required")
        team_sources[team] = {
            "team": team,
            "source_url": source_url,
            "source_kind": source_kind,
            "source_published_at": published_at,
            "target_game": _text(raw_source.get("target_game")),
            "coverage_note": coverage_note,
        }
    if (
        len(team_sources) != len(pgo_model.CURRENT_TEAMS)
        or set(team_sources) != set(pgo_model.CURRENT_TEAMS)
    ):
        raise ValueError("Injury source snapshot must contain exactly 32 teams")

    players_raw = data.get("players", [])
    if not isinstance(players_raw, list):
        raise ValueError("Injury source snapshot players must be a list")
    players = []
    seen = set()
    for raw_player in players_raw:
        if not isinstance(raw_player, dict):
            raise ValueError("Injury source player rows must be objects")
        team_raw = _text(raw_player.get("team"))
        try:
            team = pgo_sources.normalize_team(team_raw)
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("Invalid injury source player team") from error
        if team_raw != team or team not in team_sources:
            raise ValueError("Invalid injury source player team")
        gsis_id = _text(raw_player.get("gsis_id"))
        player = _text(raw_player.get("player"))
        position = _text(raw_player.get("position"))
        if not gsis_id or not player or not position:
            raise ValueError("Injury source player identity is incomplete")
        key = (team, gsis_id)
        if key in seen:
            raise ValueError(f"Duplicate injury player: {team} {gsis_id}")
        seen.add(key)

        source_record = team_sources[team]
        source_url = _https_url(raw_player.get("source_url"))
        if source_url != source_record["source_url"]:
            raise ValueError(f"Player source URL does not match team source: {team}")
        if source_record["source_kind"] == "no_formal_report":
            raise ValueError("A no_formal_report source cannot list players")

        practice_status = _status(raw_player.get("practice_status"))
        game_status = _status(raw_player.get("game_status"))
        availability_text = _text(raw_player.get("availability_text"))
        if source_record["source_kind"] == "formal_injury_report":
            if not practice_status and game_status.casefold() in ("", "note"):
                raise ValueError("Formal injury rows require a practice or game status")
            pgo_challenger.availability_probability(game_status, practice_status)
        elif not availability_text:
            raise ValueError("Editorial availability rows require source language")

        players.append({
            "team": team,
            "gsis_id": gsis_id,
            "player": player,
            "position": position,
            "source_url": source_url,
            "source_kind": source_record["source_kind"],
            "injury": _text(raw_player.get("injury")),
            "practice_status": practice_status,
            "game_status": game_status,
            "availability_text": availability_text,
        })

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source": source,
        "source_as_of": source_as_of,
        "team_sources": [
            team_sources[team] for team in pgo_model.CURRENT_TEAMS
        ],
        "teams_processed": list(pgo_model.CURRENT_TEAMS),
        "players": sorted(players, key=lambda row: (row["team"], row["gsis_id"])),
        "raw_source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def build_overlay(snapshot):
    rows = []
    exclusions = []
    for player in snapshot["players"]:
        if player["source_kind"] != "formal_injury_report":
            exclusions.append({
                "team": player["team"],
                "gsis_id": player["gsis_id"],
                "player": player["player"],
                "source_kind": player["source_kind"],
                "source_url": player["source_url"],
                "reason": f"{player['source_kind']} is editorial-only",
            })
            continue
        probability = pgo_challenger.availability_probability(
            player["game_status"], player["practice_status"]
        )
        status_note = (
            f"Official injury report: {player['injury'] or 'not listed'}; "
            f"practice={player['practice_status'] or 'not listed'}; "
            f"game={player['game_status'] or 'not listed'}; "
            f"source={player['source_url']}"
        )
        rows.append({
            "team": player["team"],
            "gsis_id": player["gsis_id"],
            "player": player["player"],
            "availability_probability": f"{probability:.2f}",
            "offense_snap_share_low": "",
            "offense_snap_share_base": "",
            "offense_snap_share_high": "",
            "defense_snap_share_low": "",
            "defense_snap_share_base": "",
            "defense_snap_share_high": "",
            "source_as_of": snapshot["source_as_of"],
            "source_note": status_note,
            "role_note": "",
        })
    return rows, exclusions


def _coverage(snapshot, overlay_rows, exclusions):
    source_counts = {team: 0 for team in pgo_model.CURRENT_TEAMS}
    overlay_counts = {team: 0 for team in pgo_model.CURRENT_TEAMS}
    excluded_counts = {team: 0 for team in pgo_model.CURRENT_TEAMS}
    for player in snapshot["players"]:
        source_counts[player["team"]] += 1
    for row in overlay_rows:
        overlay_counts[row["team"]] += 1
    for row in exclusions:
        excluded_counts[row["team"]] += 1
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source": snapshot["source"],
        "source_as_of": snapshot["source_as_of"],
        "raw_source_sha256": snapshot["raw_source_sha256"],
        "team_sources": snapshot["team_sources"],
        "teams_processed": list(pgo_model.CURRENT_TEAMS),
        "teams_with_source_players": [
            team for team in pgo_model.CURRENT_TEAMS if source_counts[team]
        ],
        "teams_with_overlay_players": [
            team for team in pgo_model.CURRENT_TEAMS if overlay_counts[team]
        ],
        "team_source_player_counts": source_counts,
        "team_row_counts": overlay_counts,
        "team_excluded_counts": excluded_counts,
        "source_player_count": len(snapshot["players"]),
        "player_row_count": len(overlay_rows),
        "excluded_player_count": len(exclusions),
        "overlay_player_keys": [
            {"team": row["team"], "gsis_id": row["gsis_id"]}
            for row in overlay_rows
        ],
        "exclusions": exclusions,
    }


def _csv_text(rows):
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(
        handle,
        fieldnames=pgo_challenger.AVAILABILITY_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()


def import_snapshot(source_path, overlay_path, coverage_path):
    snapshot = load_snapshot(source_path)
    rows, exclusions = build_overlay(snapshot)
    coverage = _coverage(snapshot, rows, exclusions)
    atomic_write_text(overlay_path, _csv_text(rows))
    atomic_write_text(
        coverage_path,
        json.dumps(coverage, indent=2, sort_keys=True) + "\n",
    )
    return {
        "source_player_count": coverage["source_player_count"],
        "overlay_row_count": len(rows),
        "excluded_player_count": coverage["excluded_player_count"],
        "teams_processed": coverage["teams_processed"],
        "teams_with_overlay_players": coverage["teams_with_overlay_players"],
        "raw_source_sha256": coverage["raw_source_sha256"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument("--coverage", required=True, type=Path)
    args = parser.parse_args(argv)
    import_snapshot(args.input, args.overlay, args.coverage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
