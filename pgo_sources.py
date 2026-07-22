"""Pinned source inventory and offline validation for the PGO challenger."""

import csv
import gzip
import hashlib
import json
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pgo_model import (
    ALIASES,
    CURRENT_TEAMS,
    EXPECTED_SOURCE_SHA256,
    SOURCE_URL,
)
from release_ratings import atomic_write_text


FIRST_MODEL_SEASON = 2013
LAST_HISTORY_SEASON = 2025
LICENSE_URL = "https://github.com/nflverse/nflverse-data/blob/master/LICENSE.md"
ALIASES = {
    **ALIASES,
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
    "SL": "LAR",
}

SCHEDULE_COLUMNS = (
    "game_id", "season", "week", "game_type", "gameday", "gametime",
    "away_team", "home_team", "away_score", "home_score", "location",
    "away_rest", "home_rest", "away_coach", "home_coach",
)
TEAM_COLUMNS = (
    "season", "week", "team", "game_id", "opponent_team", "attempts",
    "carries", "passing_epa", "rushing_epa", "sacks_suffered",
    "passing_interceptions", "fumbles_lost_total", "passing_20", "rushing_20",
)
PLAYER_COLUMNS = (
    "player_id", "position", "season", "week", "team", "attempts",
    "passing_epa", "passing_cpoe", "sacks_suffered", "passing_interceptions",
    "sack_fumbles_lost", "carries", "rushing_epa",
)
ROSTER_COLUMNS = (
    "season", "week", "team", "position", "full_name", "gsis_id", "pfr_id",
    "smart_id", "years_exp", "draft_number",
)
INJURY_COLUMNS = (
    "season", "week", "team", "gsis_id", "position", "report_status",
    "practice_status",
)
SNAP_COLUMNS = (
    "season", "week", "team", "player", "pfr_player_id", "position",
    "offense_snaps", "defense_snaps",
)
NOT_ADMITTED = (
    "coordinator identities",
    "team success rate",
    "special-teams EPA",
    "travel distance",
    "paid sources",
    "market data",
    "subjective scheme labels",
    "manual player grades",
)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    season: int | None
    url: str
    required_columns: tuple[str, ...]


def source_specs() -> tuple[SourceSpec, ...]:
    specs = [SourceSpec("schedule_results", None, SOURCE_URL, SCHEDULE_COLUMNS)]
    seasonal = (
        (
            "team_weekly_stats",
            "https://github.com/nflverse/nflverse-data/releases/download/"
            "stats_team/stats_team_week_{season}.csv.gz",
            TEAM_COLUMNS,
        ),
        (
            "player_weekly_stats",
            "https://github.com/nflverse/nflverse-data/releases/download/"
            "stats_player/stats_player_week_{season}.csv.gz",
            PLAYER_COLUMNS,
        ),
        (
            "weekly_rosters",
            "https://github.com/nflverse/nflverse-data/releases/download/"
            "weekly_rosters/roster_weekly_{season}.csv",
            ROSTER_COLUMNS,
        ),
        (
            "injury_reports",
            "https://github.com/nflverse/nflverse-data/releases/download/"
            "injuries/injuries_{season}.csv",
            INJURY_COLUMNS,
        ),
        (
            "snap_counts",
            "https://github.com/nflverse/nflverse-data/releases/download/"
            "snap_counts/snap_counts_{season}.csv",
            SNAP_COLUMNS,
        ),
    )
    for name, url, columns in seasonal:
        specs.extend(
            SourceSpec(name, season, url.format(season=season), columns)
            for season in range(FIRST_MODEL_SEASON, LAST_HISTORY_SEASON + 1)
        )
    specs.append(SourceSpec(
        "current_roster",
        2026,
        "https://github.com/nflverse/nflverse-data/releases/download/"
        "rosters/roster_2026.csv.gz",
        ROSTER_COLUMNS,
    ))
    return tuple(specs)


def fetch_url(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        return response.read()


def freeze_sources(
    specs, cache_dir, lock_path, frozen_at, fetch=fetch_url,
) -> dict:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    seen = set()
    for spec in specs:
        key = (spec.name, spec.season)
        if key in seen:
            raise ValueError(f"Duplicate logical source: {_label(*key)}")
        seen.add(key)
        data = fetch(spec.url)
        if not isinstance(data, bytes):
            raise TypeError(f"Fetcher returned non-bytes for {_label(*key)}")
        digest = hashlib.sha256(data).hexdigest()
        if key == ("schedule_results", None) and digest != EXPECTED_SOURCE_SHA256:
            raise ValueError("schedule_results does not match pinned SHA-256")
        cache_path = cache_dir / f"{digest}{_csv_extension(spec.url)}"
        cache_path.write_bytes(data)
        entries.append({
            "name": spec.name,
            "season": spec.season,
            "url": spec.url,
            "sha256": digest,
            "bytes": len(data),
            "frozen_at": frozen_at,
        })
    entries.sort(key=lambda entry: (entry["name"], entry["season"] or -1))
    manifest = {"sources": entries}
    atomic_write_text(lock_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def load_locked_sources(lock_path, cache_dir) -> dict[tuple[str, int | None], Path]:
    manifest = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    paths = {}
    for entry in manifest.get("sources", ()):
        key = (entry["name"], entry["season"])
        label = _label(*key)
        if key in paths:
            raise ValueError(f"Duplicate locked source: {label}")
        path = Path(cache_dir, f"{entry['sha256']}{_csv_extension(entry['url'])}")
        try:
            data = path.read_bytes()
        except FileNotFoundError as error:
            raise ValueError(f"Locked source {label} is missing") from error
        if len(data) != entry["bytes"]:
            raise ValueError(f"Locked source {label} byte count changed")
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Locked source {label} hash changed")
        paths[key] = path
    return paths


def open_csv(path) -> Iterator[dict[str, str]]:
    with _open_text(path) as handle:
        yield from csv.DictReader(handle)


def normalize_team(team: str) -> str:
    original = team.strip().upper()
    normalized = ALIASES.get(original, original)
    if normalized not in CURRENT_TEAMS:
        raise ValueError(f"Unknown team abbreviation: {original}")
    return normalized


def validate_source_audit(paths) -> dict:
    expected = {(spec.name, spec.season): spec for spec in source_specs()}
    missing_sources = sorted(
        set(expected) - set(paths), key=lambda key: (key[0], key[1] or -1)
    )
    if missing_sources:
        raise ValueError(f"Missing source: {_label(*missing_sources[0])}")
    unexpected = sorted(
        set(paths) - set(expected), key=lambda key: (key[0], key[1] or -1)
    )
    if unexpected:
        raise ValueError(f"Unexpected source: {_label(*unexpected[0])}")

    records = []
    teams = set()
    for key, spec in expected.items():
        with _open_text(paths[key]) as handle:
            reader = csv.DictReader(handle)
            columns = tuple(reader.fieldnames or ())
            missing_columns = [
                column for column in spec.required_columns if column not in columns
            ]
            if missing_columns:
                raise ValueError(
                    f"{_label(*key)} missing required columns: "
                    + ", ".join(missing_columns)
                )
            rows = 0
            team_columns = tuple(
                column
                for column in ("team", "opponent_team", "home_team", "away_team")
                if column in columns
            )
            for row in reader:
                rows += 1
                for column in team_columns:
                    if row[column].strip():
                        teams.add(normalize_team(row[column]))
            if rows == 0:
                raise ValueError(f"{_label(*key)} contains zero data rows")
        records.append({
            "name": spec.name,
            "season": spec.season,
            "url": spec.url,
            "rows": rows,
            "columns": list(columns),
        })

    return {
        "earliest_modeling_season": FIRST_MODEL_SEASON,
        "sources": records,
        "teams": sorted(teams),
        "aliases": dict(sorted(ALIASES.items())),
        "attribution": {
            "provider": "nflverse-data",
            "license": "CC BY 4.0",
            "license_url": LICENSE_URL,
        },
        "schedule_provenance": {
            "url": SOURCE_URL,
            "sha256": EXPECTED_SOURCE_SHA256,
        },
        "not_admitted": list(NOT_ADMITTED),
    }


def _csv_extension(url: str) -> str:
    return ".csv.gz" if url.lower().endswith(".csv.gz") else ".csv"


def _open_text(path):
    path = Path(path)
    if path.name.lower().endswith(".gz"):
        return gzip.open(path, mode="rt", encoding="utf-8-sig", newline="")
    return open(path, mode="r", encoding="utf-8-sig", newline="")


def _label(name, season) -> str:
    return f"{name} {season}" if season is not None else name
