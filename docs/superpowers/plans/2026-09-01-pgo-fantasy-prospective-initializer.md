# PGO Fantasy 2026 Prospective Initializer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic local preview, T-60 player-game lock, weekly grade, and full-season gate for the existing PGO half-PPR strong baseline.

**Architecture:** Add one focused `pgo_fantasy_prospective.py` module that consumes normalized frozen local JSON snapshots and imports existing scoring, baseline, pool-selection, canonical-JSON, bootstrap, and exclusive-write primitives. Keep previews timestamped and ungradeable with append-only output paths, keep evidence packages immutable, and bind every grade to exact lock and result bytes without modifying the historical fantasy or team-model pipelines.

**Tech Stack:** Python standard library, existing NumPy-backed `pgo_challenger.paired_block_bootstrap`, existing PGO modules, `unittest`, Git, and PowerShell. No new dependency, provider SDK, database, service, workflow, or web framework.

## Global Constraints

- Implementation base is `f1d7edfdd3a5a521377b680eb4e0d1bee17345ab`.
- Use an isolated Git worktree created at execution time; never implement directly in the primary checkout.
- Allowed implementation paths are `pgo_fantasy_prospective.py`, `tests/test_pgo_fantasy_prospective.py`, this plan, and the approved design specification only.
- The row grain is one player-game keyed by `(season, week, game_id, gsis_id)`.
- Competition is exactly the 2026 NFL regular season; preseason, postseason, kickers, and team defenses are excluded.
- Decision time is `T = scheduled kickoff - 60 minutes` for each game. Lock creation and every admitted source capture must be no later than `T`.
- The target remains the existing PGO half-PPR formula in `pgo_fantasy.half_ppr`.
- Current team, opponent, position, and eligibility come only from the frozen pregame roster snapshot. FB maps to RB.
- Player history uses at most eight completed regular-season games from 2025 and 2026, with a four-game half-life and four frozen position-mean pseudo-games through the existing `pgo_fantasy.strong_baseline`.
- A player with no legal history receives the frozen position mean and `TRUE_COLD_START`.
- The frozen config embeds exact canonical strict-UTF-8 bytes and SHA-256 for
  one `ACCEPTED` position-mean receipt. That receipt must declare the fixed
  2020-2025 stats-only regular-season player-game population, half-PPR scoring,
  finite QB/RB/WR/TE means equal to config means, legal freeze chronology, and
  nonempty upstream provenance. Locks retain the config and receipt bytes;
  weekly and season epochs retain the receipt hash.
- Verified inactive players lock at `0.0` and are not ranking eligible. Unverified availability may appear only in preview and blocks a T-60 lock.
- A game lock requires complete roster and availability coverage for both participating teams and stable GSIS identity for every normalized fantasy row.
- A weekly primary pool is exactly 24 QB, 24 RB, 24 WR, 12 TE, and 12 remaining RB/WR/TE FLEX rows selected by the existing `pgo_fantasy.select_primary_pool`.
- Primary metric is player-game-weighted MAE. The full-season gate uses seed `20260901`, 10,000 paired week-block resamples, at least 1% pooled MAE improvement, a positive lower 95% bound, and a strict majority of weekly wins.
- No scientific PASS before all 18 regular-season weeks are present and the
  canonical prospective leakage audit is `CLEAN`. The audit binds the exact
  scientific contract/version, model/config/code/position-mean epoch, all
  supplied weekly-grade/result/lock/source receipt identities, fixed reviewed
  feature/lineage outcomes, provider-vintage disposition, and nonempty
  findings/remediation; those bindings are reconstructed from embedded grades.
- Preview output paths are append-only/no-overwrite. A rerun requires a new
  path; any existing target fails closed with its bytes preserved. Locks,
  weekly grades, season grades, and BLOCKED diagnostics also use no-overwrite
  publication.
- All accepted JSON uses strict UTF-8, compact canonical JSON, finite values, sorted keys, and one LF terminator.
- A `BLOCKED` diagnostic must resolve path-disjoint in both ancestor and
  descendant directions (including aliases) from frozen input directories and
  artifact output/package directories; otherwise it fails closed with exit 2.
- Do not fetch remote data or read the real nflverse cache, `prospective_evidence/`, or accepted research directories during implementation verification. All focused tests use synthetic temporary files.
- Do not alter `pgo_fantasy.py`, `pgo_prospective.py`, `pgo_challenger.py`, `pgo_sources.py`, `research/`, `data/`, `docs/index.html`, `.github/workflows/`, `SHOPIFY.md`, or store/theme files.
- Do not rewrite the July team-model lock, historical snapshots, McCabe comparison, or public `Experimental model — HOLD` label.
- Do not push, deploy, publish, capture opening-night sources, or run a real T-60 lock in this plan.
- Preserve unrelated untracked paths and never use `git add -A`.

## File Map

- Create `pgo_fantasy_prospective.py`: normalized source/config validation, projection and ranking construction, preview serialization, immutable game lock, weekly and season grading, safe output publication, and CLI.
- Create `tests/test_pgo_fantasy_prospective.py`: synthetic source fixture plus source, projection, ranking, lock, grading, versioning, CLI, chronology, determinism, and failure-boundary tests.
- Modify `docs/superpowers/specs/2026-09-01-pgo-fantasy-prospective-initializer-design.md`: retain the already-applied `APPROVED FOR PLANNING` status only.
- Create no runtime source, cache, evidence, site, workflow, or store artifact.

---

### Task 1: Add the frozen JSON and model-config trust boundary

**Files:**
- Create: `pgo_fantasy_prospective.py`
- Create: `tests/test_pgo_fantasy_prospective.py`

**Interfaces:**
- Produces `parse_timestamp(value: str, label: str) -> datetime`.
- Produces `load_snapshot(path: Path, kind: str) -> dict` with exact keys `snapshot`, `receipt`, and immutable `bytes`.
- Produces `verify_loaded_snapshot(loaded: dict, kind: str) -> dict` so later callers cannot use a mutated parsed view that no longer matches the frozen bytes.
- Produces `serialize_model_config(config: dict) -> str`.
- Produces `load_model_config(path: Path) -> dict` with exact keys `config`, `sha256`, and immutable `bytes`, plus `verify_model_config(model: dict) -> dict`.
- Produces `verify_position_mean_evidence(receipt: dict) -> dict` and validates
  the exact receipt bytes embedded in the model config before preview or lock.
- Produces test fixture `ProspectiveFantasyFixture` for Tasks 2-6.

- [ ] **Step 1: Create the fixture and RED trust-boundary tests**

Create `tests/test_pgo_fantasy_prospective.py` with these imports and helpers:

```python
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pgo_fantasy
import pgo_fantasy_prospective as prospective


class ProspectiveFantasyFixture:
    CAPTURED = "2026-09-09T18:50:00-04:00"
    KICKOFF = "2026-09-09T20:20:00-04:00"
    LOCKED_AT = "2026-09-09T19:20:00-04:00"

    @staticmethod
    def scoring(**values):
        return {
            field: values.get(field, 0.0)
            for field in pgo_fantasy.SCORING_FIELDS
        }

    def envelope(self, rows, teams=("BUF", "LAR"), captured=None):
        return {
            "schema_version": 1,
            "source": "synthetic-official-source",
            "source_as_of": captured or self.CAPTURED,
            "captured_at": captured or self.CAPTURED,
            "teams_processed": list(teams),
            "rows": rows,
        }

    def position_mean_evidence(self):
        receipt = {
            "schema_version": 1,
            "artifact_kind": "PGO_FANTASY_POSITION_MEAN_EVIDENCE",
            "status": "ACCEPTED",
            "contract_version": "PGO_FANTASY_POSITION_MEANS_2020_2025_V1",
            "source_as_of": "2026-08-31T12:00:00-04:00",
            "captured_at": "2026-08-31T12:00:00-04:00",
            "frozen_at": "2026-09-01T11:00:00-04:00",
            "seasons": [2020, 2021, 2022, 2023, 2024, 2025],
            "population": "QUALIFIED_STATS_ONLY_REGULAR_SEASON_PLAYER_GAMES",
            "scoring": "PGO_HALF_PPR_V1",
            "position_means": {"QB": 15.0, "RB": 8.0, "WR": 7.0, "TE": 5.0},
            "upstream_provenance": [{
                "source": "synthetic-qualified-stats",
                "source_as_of": "2026-08-31T12:00:00-04:00",
                "captured_at": "2026-08-31T12:00:00-04:00",
                "sha256": "e" * 64,
            }],
        }
        receipt["artifact_sha256"] = prospective._artifact_hash(receipt)
        return receipt

    def config(self):
        receipt = self.position_mean_evidence()
        receipt_bytes = prospective.canonical_json(receipt) + "\n"
        return {
            "schema_version": 1,
            "model_version": "pgo_fantasy_2026_baseline_v1",
            "frozen_at": "2026-09-01T12:00:00-04:00",
            "trained_through": 2025,
            "scoring": "PGO_HALF_PPR_V1",
            "history_games": 8,
            "half_life_games": 4,
            "pseudo_games": 4,
            "position_mean_evidence_sha256": hashlib.sha256(
                receipt_bytes.encode("utf-8")
            ).hexdigest(),
            "position_mean_evidence_bytes": receipt_bytes,
            "position_means": {
                "QB": 15.0, "RB": 8.0, "WR": 7.0, "TE": 5.0,
            },
        }

    def source_values(self, *, availability=True, history_rows=None):
        game_id = "2026_01_BUF_LAR"
        schedule = self.envelope([{
            "season": 2026, "week": 1, "game_id": game_id,
            "game_type": "REG", "kickoff": self.KICKOFF,
            "away_team": "BUF", "home_team": "LAR",
        }])
        roster = self.envelope([
            {"gsis_id": "veteran", "player_name": "Veteran",
             "team": "BUF", "position": "WR", "status": "ACT"},
            {"gsis_id": "rookie", "player_name": "Rookie",
             "team": "LAR", "position": "WR", "status": "ACT"},
            {"gsis_id": "inactive", "player_name": "Inactive",
             "team": "BUF", "position": "RB", "status": "ACT"},
        ])
        inactive = self.envelope([
            {"gsis_id": "inactive", "team": "BUF", "status": "INACTIVE"},
        ])
        default_history = [{
            "season": 2025, "week": 18, "game_id": "2025_18_BUF_NYJ",
            "game_type": "REG", "finalized_at": "2026-01-04T19:00:00-05:00",
            "gsis_id": "veteran", "team": "BUF", "position": "WR",
            **self.scoring(receiving_yards=100.0),
        }]
        values = {
            "schedule": schedule,
            "roster": roster,
            "history": self.envelope(
                default_history if history_rows is None else history_rows
            ),
        }
        if availability:
            values["availability"] = inactive
        return values, game_id

    def loaded_sources(self, directory, *, availability=True, history_rows=None):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        values, game_id = self.source_values(
            availability=availability, history_rows=history_rows
        )
        loaded = {}
        for kind, value in values.items():
            path = self.write_json(root / f"{kind}.json", value)
            loaded[kind] = prospective.load_snapshot(path, kind)
        config_path = self.write_json(
            root / "config.json", self.config(), canonical=True
        )
        return loaded, prospective.load_model_config(config_path), game_id

    def command_fixture(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        values, game_id = self.source_values()
        paths = {"root": root, "game_id": game_id}
        for kind, value in values.items():
            paths[kind] = self.write_json(root / f"{kind}.json", value)
        paths["config"] = self.write_json(
            root / "config.json", self.config(), canonical=True
        )
        return paths

    @staticmethod
    def write_json(path, value, *, canonical=False):
        text = (
            prospective.canonical_json(value) + "\n"
            if canonical
            else json.dumps(value, ensure_ascii=False) + "\n"
        )
        Path(path).write_text(text, encoding="utf-8", newline="")
        return Path(path)


class ProspectiveSourceBoundaryTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def test_snapshot_reads_one_byte_sequence_and_receipts_exact_bytes(self):
        rows = [{
            "season": 2026, "week": 1, "game_id": "2026_01_BUF_LAR",
            "game_type": "REG", "kickoff": self.KICKOFF,
            "away_team": "BUF", "home_team": "LAR",
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(
                Path(directory) / "schedule.json", self.envelope(rows)
            )
            expected = path.read_bytes()
            original = Path.read_bytes
            reads = []

            def counted(target):
                reads.append(Path(target))
                return original(target)

            with patch.object(Path, "read_bytes", counted):
                loaded = prospective.load_snapshot(path, "schedule")

        self.assertEqual(reads, [path])
        self.assertEqual(loaded["snapshot"]["rows"], rows)
        self.assertEqual(loaded["receipt"]["bytes"], len(expected))
        self.assertEqual(loaded["bytes"], expected)
        self.assertEqual(
            loaded["receipt"]["sha256"], hashlib.sha256(expected).hexdigest()
        )

    def test_loaded_views_cannot_drift_from_their_frozen_bytes(self):
        rows = [{
            "season": 2026, "week": 1, "game_id": "2026_01_BUF_LAR",
            "game_type": "REG", "kickoff": self.KICKOFF,
            "away_team": "BUF", "home_team": "LAR",
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(
                Path(directory) / "schedule.json", self.envelope(rows)
            )
            loaded = prospective.load_snapshot(path, "schedule")
            loaded["snapshot"]["rows"][0]["kickoff"] = (
                "2026-09-10T20:20:00-04:00"
            )
            with self.assertRaisesRegex(ValueError, "frozen bytes"):
                prospective.verify_loaded_snapshot(loaded, "schedule")

            config_path = self.write_json(
                Path(directory) / "config.json", self.config(), canonical=True
            )
            model = prospective.load_model_config(config_path)
            model["config"]["history_games"] = 7
            with self.assertRaisesRegex(ValueError, "frozen bytes"):
                prospective.verify_model_config(model)

    def test_snapshot_rejects_duplicate_json_nonfinite_and_naive_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text(
                '{"schema_version":1,"schema_version":1}\n',
                encoding="utf-8", newline="",
            )
            nonfinite = root / "nonfinite.json"
            nonfinite.write_text(
                '{"schema_version":1,"value":NaN}\n',
                encoding="utf-8", newline="",
            )
            naive = self.envelope([], captured="2026-09-09T18:50:00")
            naive_path = self.write_json(root / "naive.json", naive)
            for path in (duplicate, nonfinite, naive_path):
                with self.subTest(path=path.name):
                    with self.assertRaises(ValueError):
                        prospective.load_snapshot(path, "schedule")

    def test_model_config_requires_exact_canonical_frozen_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = self.write_json(
                root / "config.json", self.config(), canonical=True
            )
            loaded = prospective.load_model_config(canonical)
            self.assertEqual(loaded["config"], self.config())
            self.assertEqual(
                loaded["sha256"], hashlib.sha256(canonical.read_bytes()).hexdigest()
            )
            changed = self.config()
            changed["history_games"] = 7
            changed_path = self.write_json(
                root / "changed.json", changed, canonical=True
            )
            with self.assertRaisesRegex(ValueError, "model config"):
                prospective.load_model_config(changed_path)
```

- [ ] **Step 2: Run the focused test and capture RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveSourceBoundaryTests -v
```

Expected: ERROR because `pgo_fantasy_prospective` does not exist.

- [ ] **Step 3: Implement strict JSON, timestamps, source receipts, and config validation**

Create `pgo_fantasy_prospective.py` with this initial boundary:

```python
"""Prospective 2026 half-PPR fantasy previews, locks, and grades."""

import csv
import hashlib
import io
import json
import math
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import pgo_challenger
import pgo_fantasy
import pgo_prospective
from pgo_sources import atomic_write_text, normalize_team


SCHEMA_VERSION = 1
SOURCE_KINDS = ("schedule", "roster", "availability", "history")
ENVELOPE_KEYS = frozenset({
    "schema_version", "source", "source_as_of", "captured_at",
    "teams_processed", "rows",
})
SCHEDULE_FIELDS = frozenset({
    "season", "week", "game_id", "game_type", "kickoff",
    "away_team", "home_team",
})
ROSTER_FIELDS = frozenset({
    "gsis_id", "player_name", "team", "position", "status",
})
AVAILABILITY_FIELDS = frozenset({"gsis_id", "team", "status"})
HISTORY_FIELDS = frozenset({
    "season", "week", "game_id", "game_type", "finalized_at",
    "gsis_id", "team", "position",
}) | pgo_fantasy.SCORING_FIELDS
ROW_FIELDS = {
    "schedule": SCHEDULE_FIELDS,
    "roster": ROSTER_FIELDS,
    "availability": AVAILABILITY_FIELDS,
    "history": HISTORY_FIELDS,
}
CONFIG_KEYS = frozenset({
    "schema_version", "model_version", "frozen_at", "trained_through", "scoring",
    "history_games", "half_life_games", "pseudo_games", "position_means",
    "position_mean_evidence_sha256", "position_mean_evidence_bytes",
})
POSITIONS = ("QB", "RB", "WR", "TE")


def canonical_json(value):
    return pgo_prospective._canonical(value)


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError(f"Nonfinite JSON constant: {value}")


def _decode_json(data, label):
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError(f"{label} is invalid JSON") from error


def parse_timestamp(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a timezone-bearing timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be a timezone-bearing timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-bearing timestamp")
    return parsed


def _required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _hex_digest(value, length):
    return (
        isinstance(value, str) and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _validated_teams(values, label):
    if not isinstance(values, list):
        raise ValueError(f"{label} teams_processed is invalid")
    try:
        teams = [normalize_team(value) for value in values]
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"{label} teams_processed is invalid") from error
    if len(teams) != len(set(teams)):
        raise ValueError(f"{label} teams_processed contains duplicates")
    return sorted(teams)


def _snapshot_from_bytes(data, kind):
    if kind not in SOURCE_KINDS:
        raise ValueError(f"Unknown prospective source kind: {kind}")
    value = _decode_json(data, f"{kind} snapshot")
    if not isinstance(value, dict) or set(value) != ENVELOPE_KEYS:
        raise ValueError(f"{kind} snapshot envelope is invalid")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError(f"{kind} snapshot schema is invalid")
    if not isinstance(value["source"], str) or not value["source"].strip():
        raise ValueError(f"{kind} snapshot source is invalid")
    captured = parse_timestamp(value["captured_at"], f"{kind} captured_at")
    if value["source_as_of"] is not None:
        source_as_of = parse_timestamp(
            value["source_as_of"], f"{kind} source_as_of"
        )
        if source_as_of > captured:
            raise ValueError(f"{kind} source_as_of is after capture")
    teams = _validated_teams(value["teams_processed"], kind)
    rows = value["rows"]
    if not isinstance(rows, list):
        raise ValueError(f"{kind} snapshot rows are invalid")
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS[kind]:
            raise ValueError(f"{kind} snapshot row is invalid")
    snapshot = deepcopy(value)
    snapshot["source"] = value["source"].strip()
    snapshot["teams_processed"] = teams
    loaded = {
        "snapshot": snapshot,
        "receipt": {
            "schema_version": 1,
            "kind": kind,
            "source": snapshot["source"],
            "source_as_of": snapshot["source_as_of"],
            "captured_at": snapshot["captured_at"],
            "teams_processed": teams,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "rows": len(rows),
        },
        "bytes": data,
    }
    return loaded


def load_snapshot(path, kind):
    return _snapshot_from_bytes(Path(path).read_bytes(), kind)


def verify_loaded_snapshot(loaded, kind):
    if not isinstance(loaded, dict) or set(loaded) != {
        "snapshot", "receipt", "bytes",
    } or not isinstance(loaded["bytes"], bytes):
        raise ValueError(f"{kind} loaded source is invalid")
    rebuilt = _snapshot_from_bytes(loaded["bytes"], kind)
    if loaded != rebuilt:
        raise ValueError(f"{kind} parsed view does not match frozen bytes")
    return loaded


def serialize_model_config(config):
    return canonical_json(config) + "\n"


def _validate_model_config(config):
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS:
        raise ValueError("Prospective model config is invalid")
    if (
        type(config["schema_version"]) is not int
        or config["schema_version"] != 1
        or not isinstance(config["model_version"], str)
        or not config["model_version"].strip()
        or type(config["trained_through"]) is not int
        or config["trained_through"] != 2025
        or config["scoring"] != "PGO_HALF_PPR_V1"
        or type(config["history_games"]) is not int
        or config["history_games"] != 8
        or type(config["half_life_games"]) is not int
        or config["half_life_games"] != 4
        or type(config["pseudo_games"]) is not int
        or config["pseudo_games"] != 4
        or not _hex_digest(config["position_mean_evidence_sha256"], 64)
        or not isinstance(config["position_mean_evidence_bytes"], str)
        or not isinstance(config["position_means"], dict)
        or set(config["position_means"]) != set(POSITIONS)
    ):
        raise ValueError("Prospective model config is invalid")
    frozen_at = parse_timestamp(config["frozen_at"], "model config frozen_at")
    evidence_bytes = config["position_mean_evidence_bytes"].encode("utf-8")
    evidence = _position_mean_evidence_from_bytes(evidence_bytes)
    if (
        hashlib.sha256(evidence_bytes).hexdigest()
        != config["position_mean_evidence_sha256"]
        or parse_timestamp(evidence["frozen_at"], "position evidence frozen_at")
        > frozen_at
    ):
        raise ValueError("Prospective model config position evidence is invalid")
    means = {}
    for position in POSITIONS:
        try:
            value = float(config["position_means"][position])
        except (TypeError, ValueError) as error:
            raise ValueError("Prospective model config position mean is invalid") from error
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError("Prospective model config position mean is invalid")
        means[position] = value
    if evidence["position_means"] != means:
        raise ValueError("Prospective model config position evidence is invalid")
    normalized = deepcopy(config)
    normalized["model_version"] = config["model_version"].strip()
    normalized["position_means"] = means
    return normalized


def load_model_config(path):
    path = Path(path)
    data = path.read_bytes()
    config = _validate_model_config(_decode_json(data, "prospective model config"))
    if data != serialize_model_config(config).encode("utf-8"):
        raise ValueError("Prospective model config is not canonical")
    return {
        "config": config,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": data,
    }


def verify_model_config(model):
    if not isinstance(model, dict) or set(model) != {
        "config", "sha256", "bytes",
    } or not isinstance(model["bytes"], bytes):
        raise ValueError("Prospective model config is invalid")
    config = _validate_model_config(
        _decode_json(model["bytes"], "prospective model config")
    )
    if (
        model["bytes"] != serialize_model_config(config).encode("utf-8")
        or model["config"] != config
        or model["sha256"] != hashlib.sha256(model["bytes"]).hexdigest()
    ):
        raise ValueError("Prospective model config does not match frozen bytes")
    return model
```

- [ ] **Step 4: Run Task 1 GREEN and the protected fantasy contract tests**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveSourceBoundaryTests -v
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy.FantasyContractTests `
  tests.test_pgo_fantasy.FantasyBaselineTests -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git commit -m "feat: validate prospective fantasy inputs"
```

---

### Task 2: Build time-safe projections and weekly preview rankings

**Files:**
- Modify: `pgo_fantasy_prospective.py`
- Modify: `tests/test_pgo_fantasy_prospective.py`

**Interfaces:**
- Consumes Task 1 loaded sources and model config.
- Produces `project_game(sources: dict, model: dict, game_id: str, generated_at: str, lock_mode: bool) -> dict`.
- Produces `rank_rows(rows: list[dict]) -> list[dict]`.
- Produces `build_preview(sources: dict, model: dict, week: int, generated_at: str) -> dict`.
- Produces `serialize_preview(preview: dict) -> str`.

- [ ] **Step 1: Add RED chronology, cold-start, availability, and ranking tests**

Append this class to the focused test file. The shared fixture already creates the one-game normalized sources used here and by later tasks.

```python
class ProspectiveProjectionTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def test_projection_uses_history_cold_start_and_verified_inactive(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            result = prospective.project_game(
                sources, model, game_id, self.LOCKED_AT, lock_mode=True
            )
        rows = {row["gsis_id"]: row for row in result["rows"]}
        self.assertGreater(rows["veteran"]["strong_prediction"], 7.0)
        self.assertEqual(rows["veteran"]["history_count"], 1)
        self.assertEqual(rows["veteran"]["initialization_reason"], "HISTORY")
        self.assertEqual(rows["rookie"]["strong_prediction"], 7.0)
        self.assertEqual(
            rows["rookie"]["initialization_reason"], "TRUE_COLD_START"
        )
        self.assertEqual(rows["inactive"]["strong_prediction"], 0.0)
        self.assertFalse(rows["inactive"]["ranking_eligible"])

    def test_preview_keeps_unverified_players_but_lock_rejects_them(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(
                directory, availability=False
            )
            preview = prospective.project_game(
                sources, model, game_id, self.CAPTURED, lock_mode=False
            )
            self.assertTrue(all(
                row["availability_status"] == "UNVERIFIED"
                for row in preview["rows"]
            ))
            with self.assertRaisesRegex(ValueError, "availability"):
                prospective.project_game(
                    sources, model, game_id, self.LOCKED_AT, lock_mode=True
                )

    def test_future_or_current_game_history_cannot_change_projection(self):
        future = [{
            "season": 2026, "week": 1, "game_id": "2026_01_BUF_LAR",
            "game_type": "REG", "finalized_at": "2026-09-09T23:59:00-04:00",
            "gsis_id": "veteran", "team": "BUF", "position": "WR",
            **self.scoring(receiving_yards=999.0),
        }]
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(
                directory, history_rows=future
            )
            with self.assertRaisesRegex(ValueError, "history"):
                prospective.project_game(
                    sources, model, game_id, self.LOCKED_AT, lock_mode=True
                )

    def test_preview_rejects_any_supplied_source_captured_after_preview_time(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            sources["availability"]["snapshot"]["captured_at"] = (
                "2026-09-09T19:00:00-04:00"
            )
            sources["availability"]["bytes"] = json.dumps(
                sources["availability"]["snapshot"], ensure_ascii=False
            ).encode("utf-8") + b"\n"
            sources["availability"] = prospective.load_snapshot(
                self.write_json(
                    Path(directory) / "late-availability.json",
                    sources["availability"]["snapshot"],
                ),
                "availability",
            )
            with self.assertRaisesRegex(ValueError, "captured after"):
                prospective.project_game(
                    sources, model, game_id, self.CAPTURED, lock_mode=False
                )

    def test_projection_rejects_model_config_frozen_after_prediction_time(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, _, game_id = self.loaded_sources(directory)
            config = self.config()
            config["frozen_at"] = "2026-09-09T19:00:00-04:00"
            model = prospective.load_model_config(self.write_json(
                Path(directory) / "future-config.json", config, canonical=True
            ))
            with self.assertRaisesRegex(ValueError, "frozen after"):
                prospective.project_game(
                    sources, model, game_id, self.CAPTURED, lock_mode=False
                )

    def test_history_is_eight_games_and_current_roster_context_wins(self):
        history = [{
            "season": 2024, "week": 18, "game_id": "old",
            "game_type": "REG", "finalized_at": "2025-01-05T19:00:00-05:00",
            "gsis_id": "veteran", "team": "NYJ", "position": "RB",
            **self.scoring(receiving_yards=999.0),
        }]
        history.extend({
            "season": 2025, "week": week, "game_id": f"2025_{week:02d}",
            "game_type": "REG",
            "finalized_at": f"2025-{9 + week // 4:02d}-{1 + week:02d}T19:00:00-04:00",
            "gsis_id": "veteran", "team": "LAR", "position": "RB",
            **self.scoring(receiving_yards=10.0 * week),
        } for week in range(1, 10))
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(
                directory, history_rows=history
            )
            row = next(item for item in prospective.project_game(
                sources, model, game_id, self.LOCKED_AT, lock_mode=True
            )["rows"] if item["gsis_id"] == "veteran")
        self.assertEqual(row["history_count"], 8)
        self.assertEqual(row["team"], "BUF")
        self.assertEqual(row["position"], "WR")
        self.assertEqual(row["opponent"], "LAR")
        self.assertAlmostEqual(
            row["strong_prediction"],
            pgo_fantasy.strong_baseline(list(range(2, 10)), 7.0),
        )

    def test_fb_maps_to_rb_but_unsupported_or_duplicate_roster_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values, game_id = self.source_values()
            values["roster"]["rows"][2]["position"] = "FB"
            loaded = {
                kind: prospective.load_snapshot(
                    self.write_json(root / f"{kind}.json", value), kind
                )
                for kind, value in values.items()
            }
            model = prospective.load_model_config(self.write_json(
                root / "config.json", self.config(), canonical=True
            ))
            rows = prospective.project_game(
                loaded, model, game_id, self.LOCKED_AT, lock_mode=True
            )["rows"]
            self.assertEqual(
                next(row for row in rows if row["gsis_id"] == "inactive")["position"],
                "RB",
            )

            for change in ("unsupported", "duplicate"):
                broken = json.loads(json.dumps(values["roster"]))
                if change == "unsupported":
                    broken["rows"][0]["position"] = "K"
                else:
                    broken["rows"][1]["gsis_id"] = broken["rows"][0]["gsis_id"]
                loaded["roster"] = prospective.load_snapshot(
                    self.write_json(root / f"{change}.json", broken), "roster"
                )
                with self.subTest(change=change):
                    with self.assertRaises(ValueError):
                        prospective.project_game(
                            loaded, model, game_id, self.LOCKED_AT, lock_mode=True
                        )

    def test_ranking_is_deterministic_and_uses_gsis_id_for_ties(self):
        rows = [
            {"game_id": "g", "gsis_id": "b", "position": "WR",
             "strong_prediction": 10.0, "ranking_eligible": True},
            {"game_id": "g", "gsis_id": "a", "position": "WR",
             "strong_prediction": 10.0, "ranking_eligible": True},
            {"game_id": "g", "gsis_id": "q", "position": "QB",
             "strong_prediction": 20.0, "ranking_eligible": True},
        ]
        ranked = prospective.rank_rows(list(reversed(rows)))
        by_id = {row["gsis_id"]: row for row in ranked}
        self.assertEqual(by_id["a"]["position_rank"], 1)
        self.assertEqual(by_id["b"]["position_rank"], 2)
        self.assertEqual(by_id["a"]["flex_rank"], 1)
        self.assertEqual(by_id["q"]["superflex_rank"], 1)

    def test_preview_is_explicitly_ungradeable_and_reports_source_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, _ = self.loaded_sources(
                directory, availability=False
            )
            preview = prospective.build_preview(
                sources, model, 1, self.CAPTURED
            )
        self.assertEqual(preview["evidence_mode"], "PREVIEW")
        self.assertFalse(preview["gradeable"])
        self.assertEqual(
            preview["source_coverage"]["availability"]["missing"],
            ["BUF", "LAR"],
        )
```

- [ ] **Step 2: Run Task 2 RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveProjectionTests -v
```

Expected: ERROR for missing projection and ranking functions.

- [ ] **Step 3: Implement game selection, chronology, availability, history, and projection**

Append these constants and functions. Keep every validation branch fail-closed; normalized roster snapshots contain only modeled ACT rows.

```python
LOCK_KIND = "PGO_FANTASY_T60_GAME_LOCK"
PREVIEW_KIND = "PGO_FANTASY_WEEKLY_PREVIEW"


def _artifact_hash(value):
    payload = deepcopy(value)
    payload.pop("artifact_sha256", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _game_rows(schedule, week=None):
    games = []
    seen = set()
    for row in schedule["snapshot"]["rows"]:
        if (
            type(row["season"]) is not int or row["season"] != 2026
            or type(row["week"]) is not int or not 1 <= row["week"] <= 18
            or row["game_type"] != "REG"
            or not isinstance(row["game_id"], str) or not row["game_id"].strip()
        ):
            raise ValueError("Prospective schedule row is invalid")
        game_id = row["game_id"].strip()
        if game_id in seen:
            raise ValueError(f"Duplicate prospective game: {game_id}")
        seen.add(game_id)
        away = normalize_team(_required_text(row["away_team"], "away team"))
        home = normalize_team(_required_text(row["home_team"], "home team"))
        if away == home:
            raise ValueError("Prospective schedule teams match")
        kickoff = parse_timestamp(row["kickoff"], "scheduled kickoff")
        parsed = {
            "season": 2026, "week": row["week"], "game_id": game_id,
            "kickoff": row["kickoff"], "kickoff_time": kickoff,
            "away": away, "home": home,
        }
        if week is None or row["week"] == week:
            games.append(parsed)
    return sorted(games, key=lambda game: (game["kickoff_time"], game["game_id"]))


def _ensure_captured(source, cutoff, label):
    captured = parse_timestamp(source["receipt"]["captured_at"], f"{label} capture")
    if captured > cutoff:
        raise ValueError(f"{label} source was captured after prediction time")


def _roster_rows(roster, teams):
    if not set(teams) <= set(roster["receipt"]["teams_processed"]):
        raise ValueError("Prospective roster coverage is incomplete")
    parsed, seen = [], set()
    for row in roster["snapshot"]["rows"]:
        team = normalize_team(_required_text(row["team"], "roster team"))
        if team not in teams:
            continue
        gsis_id = _required_text(row["gsis_id"], "roster gsis_id")
        name = _required_text(row["player_name"], "roster player_name")
        raw_position = _required_text(
            row["position"], "roster position"
        ).upper()
        if (
            not gsis_id or not name or row["status"] != "ACT"
            or raw_position not in pgo_fantasy.POSITION_MAP
        ):
            raise ValueError("Prospective roster row is invalid")
        if gsis_id in seen:
            raise ValueError(f"Duplicate prospective roster identity: {gsis_id}")
        seen.add(gsis_id)
        parsed.append({
            "gsis_id": gsis_id, "player_name": name, "team": team,
            "position": pgo_fantasy.POSITION_MAP[raw_position],
        })
    if not parsed:
        raise ValueError("Prospective roster contains no modeled players")
    return sorted(parsed, key=lambda row: row["gsis_id"])


def _availability_state(source, teams, lock_mode):
    verified = (
        source is not None
        and set(teams) <= set(source["receipt"]["teams_processed"])
    )
    if lock_mode and not verified:
        raise ValueError("Prospective availability coverage is incomplete")
    if not verified:
        return None
    inactive = set()
    for row in source["snapshot"]["rows"]:
        team = normalize_team(_required_text(row["team"], "availability team"))
        gsis_id = _required_text(row["gsis_id"], "availability gsis_id")
        if not gsis_id or row["status"] != "INACTIVE":
            raise ValueError("Prospective availability row is invalid")
        if team not in teams:
            continue
        if gsis_id in inactive:
            raise ValueError(f"Duplicate inactive identity: {gsis_id}")
        inactive.add(gsis_id)
    return inactive


def _history(history_source, cutoff, current_game):
    by_player, seen = {}, set()
    captured = parse_timestamp(
        history_source["receipt"]["captured_at"], "history capture"
    )
    for row in history_source["snapshot"]["rows"]:
        finalized = parse_timestamp(row["finalized_at"], "history finalized_at")
        gsis_id = _required_text(row["gsis_id"], "history gsis_id")
        game_id = _required_text(row["game_id"], "history game_id")
        normalize_team(_required_text(row["team"], "history team"))
        _required_text(row["position"], "history position")
        key = game_id, gsis_id
        if type(row["season"]) is not int:
            raise ValueError("Prospective history season is invalid")
        if row["season"] < 2025:
            continue
        if (
            row["season"] not in {2025, 2026}
            or type(row["week"]) is not int or not 1 <= row["week"] <= 18
            or row["game_type"] != "REG" or not game_id or not gsis_id
            or finalized > captured or finalized > cutoff
            or game_id == current_game
        ):
            raise ValueError("Prospective history row is invalid")
        if key in seen:
            raise ValueError(f"Duplicate prospective history row: {key}")
        seen.add(key)
        value = pgo_fantasy.half_ppr(row)
        by_player.setdefault(gsis_id, []).append((finalized, game_id, value))
    return {
        player: [item[2] for item in sorted(items)[-8:]]
        for player, items in by_player.items()
    }


def project_game(sources, model, game_id, generated_at, lock_mode):
    required = {"schedule", "roster", "history"}
    if set(sources) - {"schedule", "roster", "availability", "history"}:
        raise ValueError("Unexpected prospective source")
    if not required <= set(sources):
        raise ValueError("Missing prospective source")
    verify_model_config(model)
    for kind, source in sources.items():
        verify_loaded_snapshot(source, kind)
    generated = parse_timestamp(generated_at, "prediction generated_at")
    if parse_timestamp(
        model["config"]["frozen_at"], "model config frozen_at"
    ) > generated:
        raise ValueError("Prospective model config was frozen after prediction time")
    games = _game_rows(sources["schedule"])
    matches = [game for game in games if game["game_id"] == game_id]
    if len(matches) != 1:
        raise ValueError("Prospective game identity is invalid")
    game = matches[0]
    decision = game["kickoff_time"] - timedelta(minutes=60)
    if lock_mode and generated > decision:
        raise ValueError("T-60 decision time has passed")
    for kind in sources:
        _ensure_captured(sources[kind], generated, kind)
    teams = {game["away"], game["home"]}
    roster = _roster_rows(sources["roster"], teams)
    inactive = _availability_state(
        sources.get("availability"), teams, lock_mode
    )
    history = _history(sources["history"], generated, game_id)
    means = model["config"]["position_means"]
    rows = []
    for player in roster:
        values = history.get(player["gsis_id"], [])
        unavailable = inactive is not None and player["gsis_id"] in inactive
        status = (
            "INACTIVE" if unavailable
            else "ACTIVE" if inactive is not None
            else "UNVERIFIED"
        )
        mean = means[player["position"]]
        rows.append({
            "season": 2026, "week": game["week"], "game_id": game_id,
            "gsis_id": player["gsis_id"],
            "player_name": player["player_name"], "team": player["team"],
            "opponent": game["home"] if player["team"] == game["away"] else game["away"],
            "position": player["position"],
            "null_prediction": 0.0 if unavailable else mean,
            "strong_prediction": 0.0 if unavailable else pgo_fantasy.strong_baseline(values, mean),
            "history_count": len(values),
            "initialization_reason": "HISTORY" if values else "TRUE_COLD_START",
            "availability_status": status,
            "ranking_eligible": not unavailable,
            "config_sha256": model["sha256"],
        })
    week_games = [item["game_id"] for item in games if item["week"] == game["week"]]
    return {
        "game": {key: game[key] for key in (
            "season", "week", "game_id", "kickoff", "away", "home"
        )},
        "decision_time": decision.isoformat(),
        "generated_at": generated_at,
        "scheduled_week_games": sorted(week_games),
        "rows": sorted(rows, key=lambda row: row["gsis_id"]),
    }
```

- [ ] **Step 4: Implement deterministic ranking and preview assembly**

```python
def rank_rows(rows):
    ranked = [deepcopy(row) for row in rows]
    seen = set()
    for row in ranked:
        key = row["game_id"], row["gsis_id"]
        if key in seen:
            raise ValueError(f"Duplicate ranking row: {key}")
        seen.add(key)
        row.update({"position_rank": None, "flex_rank": None, "superflex_rank": None})

    def assign(field, allowed):
        selected = sorted(
            (
                row for row in ranked
                if row["ranking_eligible"] and row["position"] in allowed
            ),
            key=lambda row: (-row["strong_prediction"], row["gsis_id"]),
        )
        for index, row in enumerate(selected, 1):
            row[field] = index

    for position in POSITIONS:
        assign("position_rank", {position})
    assign("flex_rank", {"RB", "WR", "TE"})
    assign("superflex_rank", set(POSITIONS))
    return sorted(ranked, key=lambda row: (row["game_id"], row["gsis_id"]))


def build_preview(sources, model, week, generated_at):
    if type(week) is not int or not 1 <= week <= 18:
        raise ValueError("Preview week is invalid")
    games = _game_rows(sources["schedule"], week)
    scheduled_teams = {
        team for game in games for team in (game["away"], game["home"])
    }
    roster_teams = set(sources["roster"]["receipt"]["teams_processed"])
    rows, missing = [], set()
    for game in games:
        teams = {game["away"], game["home"]}
        if not teams <= roster_teams:
            missing.update(teams - roster_teams)
            continue
        rows.extend(project_game(
            sources, model, game["game_id"], generated_at, lock_mode=False
        )["rows"])
    preview = {
        "schema_version": 1,
        "artifact_kind": PREVIEW_KIND,
        "status": "HOLD",
        "publication_status": "EXPERIMENTAL",
        "evidence_mode": "PREVIEW",
        "gradeable": False,
        "season": 2026,
        "week": week,
        "generated_at": generated_at,
        "model_version": model["config"]["model_version"],
        "config_sha256": model["sha256"],
        "teams_processed": sorted(roster_teams),
        "teams_missing": sorted(missing),
        "source_coverage": {
            kind: {
                "processed": sorted(
                    scheduled_teams & set(source["receipt"]["teams_processed"])
                ),
                "missing": sorted(
                    scheduled_teams - set(source["receipt"]["teams_processed"])
                ),
            }
            for kind, source in (
                ("roster", sources["roster"]),
                ("availability", sources.get("availability", {
                    "receipt": {"teams_processed": []},
                })),
            )
        },
        "rows": rank_rows(rows),
    }
    preview["artifact_sha256"] = _artifact_hash(preview)
    return preview


def serialize_preview(preview):
    if preview.get("artifact_sha256") != _artifact_hash(preview):
        raise ValueError("Preview artifact hash is invalid")
    return canonical_json(preview) + "\n"
```

- [ ] **Step 5: Run Task 2 GREEN and all focused tests so far**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveProjectionTests -v
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective -v
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add -- pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git commit -m "feat: build prospective fantasy previews"
```

---

### Task 3: Create immutable per-game T-60 lock packages

**Files:**
- Modify: `pgo_fantasy_prospective.py`
- Modify: `tests/test_pgo_fantasy_prospective.py`

**Interfaces:**
- Consumes Task 2 `project_game`.
- Produces `build_game_lock(sources, model, game_id, locked_at, code_sha) -> dict`.
- Produces `verify_game_lock(lock: dict) -> dict`.
- Produces `serialize_game_lock(lock: dict) -> str` and `game_prediction_csv(lock: dict) -> str`.
- Produces `load_game_lock(path: Path) -> dict` with keys `lock`, `bytes`, and `sha256`.
- Produces `write_game_lock(output_dir: Path, lock: dict) -> bool`.

- [ ] **Step 1: Add RED lock integrity, time, no-overwrite, and postponement tests**

Append `ProspectiveGameLockTests`; it reuses `loaded_sources` from the shared fixture.

```python
class ProspectiveGameLockTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def test_lock_is_canonical_deterministic_and_bound_to_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            first = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            second = prospective.build_game_lock(
                dict(reversed(list(sources.items()))), model, game_id,
                self.LOCKED_AT, "a" * 40,
            )
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "LOCKED")
        self.assertEqual(
            prospective.serialize_game_lock(first),
            prospective.serialize_game_lock(second),
        )
        changed = json.loads(prospective.serialize_game_lock(first))
        next(
            row for row in changed["predictions"]
            if row["availability_status"] == "ACTIVE"
        )["strong_prediction"] += 1.0
        with self.assertRaisesRegex(ValueError, "integrity"):
            prospective.verify_game_lock(changed)

    def test_after_t_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            with self.assertRaisesRegex(ValueError, "T-60"):
                prospective.build_game_lock(
                    sources, model, game_id,
                    "2026-09-09T19:20:01-04:00", "a" * 40,
                )

    def test_lock_rejects_mutated_source_view_and_incomplete_team_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, model, game_id = self.loaded_sources(directory)
            sources["schedule"]["snapshot"]["rows"][0]["home_team"] = "SF"
            with self.assertRaisesRegex(ValueError, "frozen bytes"):
                prospective.build_game_lock(
                    sources, model, game_id, self.LOCKED_AT, "a" * 40
                )

            sources, model, game_id = self.loaded_sources(
                Path(directory) / "coverage"
            )
            incomplete = json.loads(json.dumps(
                sources["availability"]["snapshot"]
            ))
            incomplete["teams_processed"] = ["BUF"]
            sources["availability"] = prospective.load_snapshot(
                self.write_json(
                    Path(directory) / "incomplete.json", incomplete
                ),
                "availability",
            )
            with self.assertRaisesRegex(ValueError, "coverage"):
                prospective.build_game_lock(
                    sources, model, game_id, self.LOCKED_AT, "a" * 40
                )

    def test_lock_writer_never_overwrites_existing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, game_id = self.loaded_sources(root / "inputs")
            lock = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            output = root / "lock"
            self.assertTrue(prospective.write_game_lock(output, lock))
            first = (output / "fantasy_lock.json").read_bytes()
            self.assertFalse(prospective.write_game_lock(output, lock))
            self.assertEqual((output / "fantasy_lock.json").read_bytes(), first)

    def test_rescheduled_lock_does_not_rewrite_old_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, model, game_id = self.loaded_sources(root / "inputs")
            old = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            old_dir = root / "old"
            self.assertTrue(prospective.write_game_lock(old_dir, old))
            original = (old_dir / "fantasy_lock.json").read_bytes()
            rescheduled = json.loads(json.dumps(
                sources["schedule"]["snapshot"]
            ))
            rescheduled["rows"][0]["kickoff"] = (
                "2026-09-10T20:20:00-04:00"
            )
            sources["schedule"] = prospective.load_snapshot(
                self.write_json(root / "rescheduled.json", rescheduled),
                "schedule",
            )
            new = prospective.build_game_lock(
                sources, model, game_id,
                "2026-09-10T19:20:00-04:00", "a" * 40,
            )
            self.assertTrue(prospective.write_game_lock(root / "new", new))
            self.assertEqual((old_dir / "fantasy_lock.json").read_bytes(), original)
            self.assertNotEqual(old["artifact_sha256"], new["artifact_sha256"])
```

- [ ] **Step 2: Run Task 3 RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveGameLockTests -v
```

Expected: ERROR for missing lock functions.

- [ ] **Step 3: Implement lock hashes, serialization, strict reload, and safe package publication**

```python
LOCK_KEYS = frozenset({
    "schema_version", "artifact_kind", "status", "publication_status",
    "season", "week", "game_id", "kickoff", "away", "home",
    "decision_time", "locked_at", "teams_processed", "row_count", "coverage",
    "model_version", "config_sha256", "code_sha", "scheduled_week_games",
    "source_receipts", "source_receipts_sha256", "predictions",
    "prediction_integrity_sha256", "artifact_sha256",
})
LOCK_PREDICTION_COLUMNS = (
    "season", "week", "game_id", "gsis_id", "player_name", "team",
    "opponent", "position", "null_prediction", "strong_prediction",
    "history_count", "initialization_reason", "availability_status",
    "ranking_eligible", "config_sha256",
)
SOURCE_RECEIPT_KEYS = frozenset({
    "schema_version", "kind", "source", "source_as_of", "captured_at",
    "teams_processed", "bytes", "sha256", "rows",
})


def _validate_lock_predictions(rows, lock=None):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Fantasy game lock predictions are invalid")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(LOCK_PREDICTION_COLUMNS):
            raise ValueError("Fantasy game lock prediction row is invalid")
        key = row["game_id"], row["gsis_id"]
        values = (row["null_prediction"], row["strong_prediction"])
        if (
            not all(isinstance(value, str) and value.strip() for value in (
                row["game_id"], row["gsis_id"], row["player_name"],
                row["team"], row["opponent"], row["position"],
                row["initialization_reason"], row["availability_status"],
                row["config_sha256"],
            ))
            or key in seen
            or type(row["season"]) is not int or row["season"] != 2026
            or type(row["week"]) is not int or not 1 <= row["week"] <= 18
            or row["position"] not in POSITIONS
            or row["initialization_reason"] not in {"HISTORY", "TRUE_COLD_START"}
            or row["availability_status"] not in {"ACTIVE", "INACTIVE"}
            or type(row["ranking_eligible"]) is not bool
            or type(row["history_count"]) is not int
            or not 0 <= row["history_count"] <= 8
            or not all(type(value) in {int, float} and math.isfinite(value) for value in values)
        ):
            raise ValueError("Fantasy game lock prediction row is invalid")
        seen.add(key)
        if row["availability_status"] == "INACTIVE" and (
            values != (0.0, 0.0) or row["ranking_eligible"]
        ):
            raise ValueError("Inactive fantasy lock row is invalid")
        if row["availability_status"] == "ACTIVE" and not row["ranking_eligible"]:
            raise ValueError("Active fantasy lock row is invalid")
        if lock is not None and (
            row["season"] != lock["season"] or row["week"] != lock["week"]
            or row["game_id"] != lock["game_id"]
            or row["team"] not in lock["teams_processed"]
            or row["opponent"] not in lock["teams_processed"]
            or row["team"] == row["opponent"]
            or row["config_sha256"] != lock["config_sha256"]
        ):
            raise ValueError("Fantasy game lock prediction context is invalid")
    if rows != sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"])):
        raise ValueError("Fantasy game lock predictions are not canonical")
    return rows


def _prediction_hash(rows):
    _validate_lock_predictions(rows)
    values = [
        {key: row[key] for key in LOCK_PREDICTION_COLUMNS}
        for row in sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"]))
    ]
    return hashlib.sha256(canonical_json(values).encode("utf-8")).hexdigest()


def build_game_lock(sources, model, game_id, locked_at, code_sha):
    if (
        not isinstance(code_sha, str) or len(code_sha) != 40
        or any(character not in "0123456789abcdef" for character in code_sha)
    ):
        raise ValueError("Code SHA is invalid")
    projected = project_game(
        sources, model, game_id, locked_at, lock_mode=True
    )
    receipts = [deepcopy(sources[kind]["receipt"]) for kind in SOURCE_KINDS]
    lock = {
        "schema_version": 1,
        "artifact_kind": LOCK_KIND,
        "status": "LOCKED",
        "publication_status": "EXPERIMENTAL",
        **projected["game"],
        "decision_time": projected["decision_time"],
        "locked_at": locked_at,
        "model_version": model["config"]["model_version"],
        "config_sha256": model["sha256"],
        "code_sha": code_sha,
        "teams_processed": sorted((projected["game"]["away"], projected["game"]["home"])),
        "row_count": len(projected["rows"]),
        "coverage": {"roster": True, "availability": True},
        "scheduled_week_games": projected["scheduled_week_games"],
        "source_receipts": receipts,
        "source_receipts_sha256": hashlib.sha256(
            canonical_json(receipts).encode("utf-8")
        ).hexdigest(),
        "predictions": projected["rows"],
    }
    lock["prediction_integrity_sha256"] = _prediction_hash(lock["predictions"])
    lock["artifact_sha256"] = _artifact_hash(lock)
    return verify_game_lock(lock)


def verify_game_lock(lock):
    if not isinstance(lock, dict) or set(lock) != LOCK_KEYS:
        raise ValueError("Fantasy game lock contract is invalid")
    if (
        type(lock["schema_version"]) is not int or lock["schema_version"] != 1
        or lock["artifact_kind"] != LOCK_KIND or lock["status"] != "LOCKED"
        or lock["publication_status"] != "EXPERIMENTAL"
        or type(lock["season"]) is not int or lock["season"] != 2026
        or type(lock["week"]) is not int or not 1 <= lock["week"] <= 18
        or not isinstance(lock["game_id"], str) or not lock["game_id"].strip()
        or not isinstance(lock["model_version"], str)
        or not lock["model_version"].strip()
        or not _hex_digest(lock["code_sha"], 40)
        or not _hex_digest(lock["config_sha256"], 64)
        or lock["teams_processed"] != sorted((lock["away"], lock["home"]))
        or len(set(lock["teams_processed"])) != 2
        or type(lock["row_count"]) is not int or lock["row_count"] <= 0
        or lock["row_count"] != len(lock["predictions"])
        or lock["coverage"] != {"roster": True, "availability": True}
        or lock["scheduled_week_games"] != sorted(set(lock["scheduled_week_games"]))
        or lock["game_id"] not in lock["scheduled_week_games"]
        or lock["prediction_integrity_sha256"] != _prediction_hash(lock["predictions"])
        or lock["source_receipts_sha256"] != hashlib.sha256(
            canonical_json(lock["source_receipts"]).encode("utf-8")
        ).hexdigest()
        or lock["artifact_sha256"] != _artifact_hash(lock)
    ):
        raise ValueError("Fantasy game lock integrity is invalid")
    if (
        normalize_team(lock["away"]) != lock["away"]
        or normalize_team(lock["home"]) != lock["home"]
    ):
        raise ValueError("Fantasy game lock teams are invalid")
    _validate_lock_predictions(lock["predictions"], lock)
    if (
        not isinstance(lock["source_receipts"], list)
        or [receipt.get("kind") for receipt in lock["source_receipts"]]
        != list(SOURCE_KINDS)
        or any(
            not isinstance(receipt, dict) or set(receipt) != SOURCE_RECEIPT_KEYS
            or type(receipt["schema_version"]) is not int
            or receipt["schema_version"] != 1
            or not isinstance(receipt["source"], str)
            or not receipt["source"].strip()
            or type(receipt["bytes"]) is not int or receipt["bytes"] <= 0
            or type(receipt["rows"]) is not int or receipt["rows"] < 0
            or not _hex_digest(receipt["sha256"], 64)
            for receipt in lock["source_receipts"]
        )
    ):
        raise ValueError("Fantasy game lock source receipts are invalid")
    coverage = {
        receipt["kind"]: set(lock["teams_processed"])
        <= set(receipt["teams_processed"])
        for receipt in lock["source_receipts"]
    }
    if not coverage["roster"] or not coverage["availability"]:
        raise ValueError("Fantasy game lock source coverage is invalid")
    kickoff = parse_timestamp(lock["kickoff"], "kickoff")
    decision = parse_timestamp(lock["decision_time"], "decision_time")
    locked = parse_timestamp(lock["locked_at"], "locked_at")
    if decision != kickoff - timedelta(minutes=60) or locked > decision:
        raise ValueError("Fantasy game lock T-60 integrity is invalid")
    for receipt in lock["source_receipts"]:
        captured = parse_timestamp(
            receipt["captured_at"], f"{receipt['kind']} captured_at"
        )
        if captured > locked:
            raise ValueError("Fantasy game lock source timing is invalid")
        if receipt["source_as_of"] is not None and parse_timestamp(
            receipt["source_as_of"], f"{receipt['kind']} source_as_of"
        ) > captured:
            raise ValueError("Fantasy game lock source timing is invalid")
    return lock


def serialize_game_lock(lock):
    verify_game_lock(lock)
    return canonical_json(lock) + "\n"


def game_prediction_csv(lock):
    verify_game_lock(lock)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=LOCK_PREDICTION_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for row in lock["predictions"]:
        writer.writerow({key: row[key] for key in LOCK_PREDICTION_COLUMNS})
    return output.getvalue()


def load_game_lock(path):
    data = Path(path).read_bytes()
    lock = _decode_json(data, "fantasy game lock")
    verify_game_lock(lock)
    if data != serialize_game_lock(lock).encode("utf-8"):
        raise ValueError("Fantasy game lock is not canonical")
    return {
        "lock": lock, "bytes": data,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def write_game_lock(output_dir, lock):
    output_dir = Path(output_dir)
    outputs = (
        (output_dir / "fantasy_lock.json", serialize_game_lock(lock)),
        (output_dir / "fantasy_predictions.csv", game_prediction_csv(lock)),
    )
    return pgo_prospective._write_new_outputs(output_dir, outputs)
```

- [ ] **Step 4: Run Task 3 GREEN plus the shared writer adversarial suite**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveGameLockTests -v
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_prospective.ProspectiveArtifactSafetyTests `
  tests.test_pgo_prospective.ProspectiveBlendLockTests -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add -- pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git commit -m "feat: lock prospective fantasy projections"
```

---

### Task 4: Grade exact weekly locks against finalized results

**Files:**
- Modify: `pgo_fantasy_prospective.py`
- Modify: `tests/test_pgo_fantasy_prospective.py`

**Interfaces:**
- Produces `load_results(path: Path) -> dict` with exact keys `snapshot`, `receipt`, and immutable `bytes`, plus `verify_loaded_results(loaded: dict) -> dict`.
- Produces `grade_week(loaded_locks: list[dict], loaded_results: dict) -> dict`.
- Produces `serialize_week_grade(grade: dict) -> str`.
- Produces `write_week_grade(output_dir: Path, grade: dict) -> bool`.

- [ ] **Step 1: Add RED exact-binding, zero-fill, pool, and tamper tests**

The helper below builds one synthetic final game with 30 QB, 40 RB, 40 WR, and 20 TE active locked rows. Deterministic IDs and projections make the existing pool selector fill exactly 96 slots without real evidence.

```python
class ProspectiveWeekGradeTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def load_result_value(self, value):
        with tempfile.TemporaryDirectory() as directory:
            return prospective.load_results(self.write_json(
                Path(directory) / "results.json", value
            ))

    def week_evidence(self):
        positions = (("QB", 30), ("RB", 40), ("WR", 40), ("TE", 20))
        roster_rows = [
            {
                "gsis_id": f"{position}-{index:03d}",
                "player_name": f"{position} {index:03d}",
                "team": "BUF" if index % 2 == 0 else "LAR",
                "position": position,
                "status": "ACT",
            }
            for position, count in positions for index in range(count)
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values, game_id = self.source_values(history_rows=[])
            values["roster"] = self.envelope(roster_rows)
            values["availability"] = self.envelope([])
            sources = {
                kind: prospective.load_snapshot(
                    self.write_json(root / f"{kind}.json", value), kind
                )
                for kind, value in values.items()
            }
            model = prospective.load_model_config(self.write_json(
                root / "config.json", self.config(), canonical=True
            ))
            lock = prospective.build_game_lock(
                sources, model, game_id, self.LOCKED_AT, "a" * 40
            )
            lock_bytes = prospective.serialize_game_lock(lock).encode("utf-8")
            loaded_locks = [{
                "lock": lock,
                "bytes": lock_bytes,
                "sha256": hashlib.sha256(lock_bytes).hexdigest(),
            }]
            result_rows = [{
                "game_id": game_id,
                "gsis_id": row["gsis_id"],
                **self.scoring(receiving_yards=10.0),
            } for row in roster_rows if row["gsis_id"] != "WR-000"]
            results_value = {
                "schema_version": 1,
                "source": "synthetic-official-results",
                "source_as_of": "2026-09-10T00:30:00-04:00",
                "captured_at": "2026-09-10T00:30:00-04:00",
                "teams_processed": ["BUF", "LAR"],
                "games": [{
                    "game_id": game_id,
                    "status": "FINAL",
                    "finalized_at": "2026-09-10T00:20:00-04:00",
                }],
                "rows": result_rows,
            }
            results = prospective.load_results(self.write_json(
                root / "results.json", results_value
            ))
        return loaded_locks, results

    def test_week_grade_uses_exact_locks_and_zero_fills_missing_stats(self):
        loaded_locks, results = self.week_evidence()
        grade = prospective.grade_week(loaded_locks, results)
        self.assertEqual(grade["status"], "HOLD")
        self.assertEqual(grade["publication_status"], "EXPERIMENTAL")
        self.assertEqual(grade["metrics"]["primary"]["count"], 96)
        missing = next(row for row in grade["rows"] if row["gsis_id"] == "WR-000")
        self.assertEqual(missing["fantasy_points"], 0.0)
        self.assertTrue(grade["checks"]["complete_game_results"])

    def test_week_grade_rejects_missing_final_game_or_extra_modeled_identity(self):
        loaded_locks, results = self.week_evidence()
        missing_value = json.loads(json.dumps(results["snapshot"]))
        missing_value["games"] = []
        missing_value["rows"] = []
        missing = self.load_result_value(missing_value)
        with self.assertRaisesRegex(ValueError, "final game"):
            prospective.grade_week(loaded_locks, missing)
        extra_value = json.loads(json.dumps(results["snapshot"]))
        extra_value["rows"].append({
            "game_id": loaded_locks[0]["lock"]["game_id"],
            "gsis_id": "not-locked",
            **self.scoring(receiving_yards=1.0),
        })
        extra = self.load_result_value(extra_value)
        with self.assertRaisesRegex(ValueError, "result identity"):
            prospective.grade_week(loaded_locks, extra)

    def test_week_grade_rejects_rehashed_or_noncanonical_lock(self):
        loaded_locks, results = self.week_evidence()
        changed = dict(loaded_locks[0])
        changed["lock"] = json.loads(prospective.serialize_game_lock(
            loaded_locks[0]["lock"]
        ))
        changed["lock"]["predictions"][0]["strong_prediction"] += 5.0
        with self.assertRaisesRegex(ValueError, "integrity"):
            prospective.grade_week([changed, *loaded_locks[1:]], results)

    def test_weekly_ranks_and_primary_pool_do_not_depend_on_results(self):
        loaded_locks, results = self.week_evidence()
        first = prospective.grade_week(loaded_locks, results)
        changed_value = json.loads(json.dumps(results["snapshot"]))
        for index, row in enumerate(changed_value["rows"]):
            row.update(self.scoring(receiving_yards=float(index * 100)))
        second = prospective.grade_week(
            loaded_locks, self.load_result_value(changed_value)
        )
        def selections(grade):
            return {
                (row["game_id"], row["gsis_id"], row["position_rank"],
                 row["flex_rank"], row["superflex_rank"])
                for row in grade["rows"] if row["primary_pool"]
            }
        self.assertEqual(selections(first), selections(second))
```

- [ ] **Step 2: Run Task 4 RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveWeekGradeTests -v
```

Expected: ERROR for missing results and grade functions.

- [ ] **Step 3: Implement finalized-result loading and exact weekly grading**

```python
RESULT_ENVELOPE_KEYS = frozenset({
    "schema_version", "source", "source_as_of", "captured_at",
    "teams_processed", "games", "rows",
})
RESULT_GAME_FIELDS = frozenset({"game_id", "status", "finalized_at"})
RESULT_ROW_FIELDS = frozenset({"game_id", "gsis_id"}) | pgo_fantasy.SCORING_FIELDS
RESULT_RECEIPT_KEYS = frozenset({
    "schema_version", "source", "source_as_of", "captured_at",
    "teams_processed", "games", "rows", "bytes", "sha256",
})
WEEK_GRADE_KEYS = frozenset({
    "schema_version", "artifact_kind", "status", "publication_status",
    "season", "week", "model_version", "config_sha256", "lock_sha256",
    "result_receipt", "checks", "metrics", "rows", "artifact_sha256",
})
WEEK_ROW_FIELDS = frozenset(LOCK_PREDICTION_COLUMNS) | {
    "position_rank", "flex_rank", "superflex_rank", "fantasy_points",
    "primary_pool", "null_absolute_error", "strong_absolute_error",
    "improvement",
}


def _results_from_bytes(data):
    value = _decode_json(data, "fantasy results")
    if not isinstance(value, dict) or set(value) != RESULT_ENVELOPE_KEYS:
        raise ValueError("Fantasy result envelope is invalid")
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not isinstance(value["source"], str)
        or not value["source"].strip()
    ):
        raise ValueError("Fantasy result schema is invalid")
    captured = parse_timestamp(value["captured_at"], "result captured_at")
    if value["source_as_of"] is not None:
        if parse_timestamp(value["source_as_of"], "result source_as_of") > captured:
            raise ValueError("Fantasy result source_as_of is after capture")
    teams = _validated_teams(value["teams_processed"], "results")
    games, seen_games = [], set()
    for game in value["games"]:
        if not isinstance(game, dict) or set(game) != RESULT_GAME_FIELDS:
            raise ValueError("Fantasy final game row is invalid")
        game_id = _required_text(game["game_id"], "result game_id")
        if not game_id or game_id in seen_games or game["status"] != "FINAL":
            raise ValueError("Fantasy final game row is invalid")
        if parse_timestamp(game["finalized_at"], "game finalized_at") > captured:
            raise ValueError("Fantasy final game is after result capture")
        seen_games.add(game_id)
        games.append(deepcopy(game))
    rows, seen_rows = [], set()
    for row in value["rows"]:
        if not isinstance(row, dict) or set(row) != RESULT_ROW_FIELDS:
            raise ValueError("Fantasy result player row is invalid")
        key = (
            _required_text(row["game_id"], "result game_id"),
            _required_text(row["gsis_id"], "result gsis_id"),
        )
        if not all(key) or key in seen_rows or key[0] not in seen_games:
            raise ValueError("Fantasy result identity is invalid")
        seen_rows.add(key)
        rows.append(deepcopy(row))
    snapshot = deepcopy(value)
    snapshot["teams_processed"] = teams
    snapshot["games"] = sorted(games, key=lambda game: game["game_id"])
    snapshot["rows"] = sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"]))
    return {
        "snapshot": snapshot,
        "receipt": {
            "schema_version": 1,
            "source": value["source"], "source_as_of": value["source_as_of"],
            "captured_at": value["captured_at"], "teams_processed": teams,
            "games": len(games), "rows": len(rows), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        "bytes": data,
    }


def load_results(path):
    return _results_from_bytes(Path(path).read_bytes())


def verify_loaded_results(loaded):
    if not isinstance(loaded, dict) or set(loaded) != {
        "snapshot", "receipt", "bytes",
    } or not isinstance(loaded["bytes"], bytes):
        raise ValueError("Loaded fantasy results are invalid")
    if loaded != _results_from_bytes(loaded["bytes"]):
        raise ValueError("Parsed fantasy results do not match frozen bytes")
    return loaded


def _mae(rows, prediction):
    return math.fsum(
        abs(row["fantasy_points"] - row[prediction]) for row in rows
    ) / len(rows)


def grade_week(loaded_locks, loaded_results):
    if not isinstance(loaded_locks, list) or not loaded_locks:
        raise ValueError("Weekly fantasy locks are missing")
    verify_loaded_results(loaded_results)
    locks = []
    for loaded in loaded_locks:
        lock = verify_game_lock(loaded["lock"])
        if loaded["bytes"] != serialize_game_lock(lock).encode("utf-8"):
            raise ValueError("Fantasy game lock bytes are not exact")
        if loaded["sha256"] != hashlib.sha256(loaded["bytes"]).hexdigest():
            raise ValueError("Fantasy game lock hash is invalid")
        locks.append(lock)
    first = locks[0]
    common = (first["season"], first["week"], first["model_version"], first["config_sha256"])
    if any(
        (lock["season"], lock["week"], lock["model_version"], lock["config_sha256"]) != common
        for lock in locks
    ):
        raise ValueError("Weekly fantasy locks do not share one model epoch")
    expected_games = set(first["scheduled_week_games"])
    if any(set(lock["scheduled_week_games"]) != expected_games for lock in locks):
        raise ValueError("Weekly fantasy schedule manifests disagree")
    if {lock["game_id"] for lock in locks} != expected_games:
        raise ValueError("Weekly fantasy lock coverage is incomplete")
    expected_teams = {
        team for lock in locks for team in lock["teams_processed"]
    }
    if not expected_teams <= set(loaded_results["receipt"]["teams_processed"]):
        raise ValueError("Weekly fantasy result team coverage is incomplete")
    final_games = {game["game_id"] for game in loaded_results["snapshot"]["games"]}
    if not expected_games <= final_games:
        raise ValueError("Weekly fantasy final game coverage is incomplete")
    predictions = rank_rows([
        row for lock in locks for row in lock["predictions"]
    ])
    prediction_keys = {(row["game_id"], row["gsis_id"]) for row in predictions}
    result_rows = {
        (row["game_id"], row["gsis_id"]): row
        for row in loaded_results["snapshot"]["rows"]
        if row["game_id"] in expected_games
    }
    if not set(result_rows) <= prediction_keys:
        raise ValueError("Fantasy result identity is not in the locked population")
    primary = pgo_fantasy.select_primary_pool([
        row for row in predictions if row["ranking_eligible"]
    ])
    if len(primary) != 96:
        raise ValueError("Weekly fantasy primary pool is not 96 rows")
    rows = []
    for prediction in predictions:
        key = prediction["game_id"], prediction["gsis_id"]
        actual = pgo_fantasy.half_ppr(result_rows[key]) if key in result_rows else 0.0
        rows.append({
            **prediction,
            "fantasy_points": actual,
            "primary_pool": key in primary,
            "null_absolute_error": abs(actual - prediction["null_prediction"]),
            "strong_absolute_error": abs(actual - prediction["strong_prediction"]),
            "improvement": (
                abs(actual - prediction["null_prediction"])
                - abs(actual - prediction["strong_prediction"])
            ),
        })
    selected = [row for row in rows if row["primary_pool"]]
    null_mae = _mae(selected, "null_prediction")
    strong_mae = _mae(selected, "strong_prediction")
    grade = {
        "schema_version": 1,
        "artifact_kind": "PGO_FANTASY_WEEK_GRADE",
        "status": "HOLD",
        "publication_status": "EXPERIMENTAL",
        "season": first["season"], "week": first["week"],
        "model_version": first["model_version"],
        "config_sha256": first["config_sha256"],
        "lock_sha256": sorted(loaded["sha256"] for loaded in loaded_locks),
        "result_receipt": loaded_results["receipt"],
        "checks": {
            "complete_game_locks": True,
            "complete_game_results": True,
            "primary_pool_96": True,
            "exact_lock_binding": True,
        },
        "metrics": {"primary": {
            "count": 96, "null_mae": null_mae, "strong_mae": strong_mae,
            "improvement": null_mae - strong_mae,
            "relative_improvement": (
                (null_mae - strong_mae) / null_mae if null_mae > 0.0 else 0.0
            ),
            "strong_win": strong_mae < null_mae,
        }},
        "rows": sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"])),
    }
    grade["artifact_sha256"] = _artifact_hash(grade)
    return verify_week_grade(grade)


def verify_week_grade(grade):
    if not isinstance(grade, dict) or set(grade) != WEEK_GRADE_KEYS:
        raise ValueError("Weekly fantasy grade contract is invalid")
    if (
        type(grade["schema_version"]) is not int
        or grade["schema_version"] != 1
        or grade["artifact_kind"] != "PGO_FANTASY_WEEK_GRADE"
        or grade["status"] != "HOLD"
        or grade["publication_status"] != "EXPERIMENTAL"
        or grade["season"] != 2026
        or type(grade["week"]) is not int
        or not 1 <= grade["week"] <= 18
        or not isinstance(grade["model_version"], str)
        or not grade["model_version"].strip()
        or not _hex_digest(grade["config_sha256"], 64)
        or not isinstance(grade["lock_sha256"], list)
        or grade["lock_sha256"] != sorted(set(grade["lock_sha256"]))
        or not grade["lock_sha256"]
        or not all(_hex_digest(value, 64) for value in grade["lock_sha256"])
        or not isinstance(grade["result_receipt"], dict)
        or set(grade["result_receipt"]) != RESULT_RECEIPT_KEYS
        or grade["result_receipt"]["schema_version"] != 1
        or not _hex_digest(grade["result_receipt"].get("sha256"), 64)
        or grade["checks"] != {
            "complete_game_locks": True,
            "complete_game_results": True,
            "primary_pool_96": True,
            "exact_lock_binding": True,
        }
    ):
        raise ValueError("Weekly fantasy grade metadata is invalid")
    rows = grade["rows"]
    if (
        not isinstance(rows, list) or not rows
        or rows != sorted(rows, key=lambda row: (row["game_id"], row["gsis_id"]))
        or any(not isinstance(row, dict) or set(row) != WEEK_ROW_FIELDS for row in rows)
    ):
        raise ValueError("Weekly fantasy grade rows are invalid")
    base_rows = [
        {field: row[field] for field in LOCK_PREDICTION_COLUMNS}
        for row in rows
    ]
    _validate_lock_predictions(base_rows)
    reranked = {
        (row["game_id"], row["gsis_id"]): row
        for row in rank_rows(base_rows)
    }
    primary = pgo_fantasy.select_primary_pool([
        row for row in base_rows if row["ranking_eligible"]
    ])
    if len(primary) != 96:
        raise ValueError("Weekly fantasy grade primary pool is invalid")
    for row in rows:
        key = row["game_id"], row["gsis_id"]
        actual = row["fantasy_points"]
        if (
            row["season"] != 2026 or row["week"] != grade["week"]
            or row["config_sha256"] != grade["config_sha256"]
            or type(row["primary_pool"]) is not bool
            or row["primary_pool"] != (key in primary)
            or type(actual) not in {int, float} or not math.isfinite(actual)
            or any(
                row[field] != reranked[key][field]
                for field in ("position_rank", "flex_rank", "superflex_rank")
            )
            or row["null_absolute_error"]
            != abs(actual - row["null_prediction"])
            or row["strong_absolute_error"]
            != abs(actual - row["strong_prediction"])
            or row["improvement"]
            != row["null_absolute_error"] - row["strong_absolute_error"]
        ):
            raise ValueError("Weekly fantasy grade row binding is invalid")
    selected = [row for row in rows if row["primary_pool"]]
    null_mae = _mae(selected, "null_prediction")
    strong_mae = _mae(selected, "strong_prediction")
    expected_metrics = {"primary": {
        "count": 96,
        "null_mae": null_mae,
        "strong_mae": strong_mae,
        "improvement": null_mae - strong_mae,
        "relative_improvement": (
            (null_mae - strong_mae) / null_mae if null_mae > 0.0 else 0.0
        ),
        "strong_win": strong_mae < null_mae,
    }}
    if grade["metrics"] != expected_metrics:
        raise ValueError("Weekly fantasy grade metrics are invalid")
    if grade["artifact_sha256"] != _artifact_hash(grade):
        raise ValueError("Weekly fantasy grade integrity is invalid")
    return grade


def serialize_week_grade(grade):
    verify_week_grade(grade)
    return canonical_json(grade) + "\n"


def write_week_grade(output_dir, grade):
    output_dir = Path(output_dir)
    return pgo_prospective._write_new_outputs(output_dir, (
        (output_dir / "fantasy_week_grade.json", serialize_week_grade(grade)),
    ))
```

- [ ] **Step 4: Run Task 4 GREEN and regression suites**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveWeekGradeTests -v
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective `
  tests.test_pgo_fantasy.FantasyBaselineTests `
  tests.test_pgo_prospective.ProspectiveGradeTests -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add -- pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git commit -m "feat: grade prospective fantasy weeks"
```

---

### Task 5: Aggregate the locked full-season promotion gate

**Files:**
- Modify: `pgo_fantasy_prospective.py`
- Modify: `tests/test_pgo_fantasy_prospective.py`

**Interfaces:**
- Produces `load_week_grade(path: Path) -> dict`.
- Produces `load_leakage_audit(path: Path) -> dict`.
- Produces `grade_season(week_grades: list[dict], leakage_audit: dict) -> dict`.
- Produces `serialize_season_grade(grade: dict) -> str` and `write_season_grade(output_dir, grade) -> bool`.

- [ ] **Step 1: Add RED incomplete, PASS, HOLD, BLOCKED, and version-mixing tests**

The exact helpers below build canonical 96-row weekly grades in memory. PASS fixtures make the null one point worse; HOLD fixtures make the two baselines identical. They never read real evidence.

```python
class ProspectiveSeasonGradeTests(unittest.TestCase):
    def audit(self, weeks, verdict="CLEAN"):
        model_version, config_sha256, code_sha, position_mean_sha256 = epoch(weeks)
        audit = {
            "schema_version": 1,
            "artifact_kind": "PGO_FANTASY_PROSPECTIVE_LEAKAGE_AUDIT",
            "status": "COMPLETE",
            "verdict": verdict,
            "audited_at": "2027-01-11T12:00:00-05:00",
            "scientific_contract": "PGO_FANTASY_PROSPECTIVE_2026_SCIENTIFIC_V1",
            "model_version": model_version,
            "config_sha256": config_sha256,
            "code_sha": code_sha,
            "position_mean_evidence_sha256": position_mean_sha256,
            "weekly_evidence": audit_weekly_evidence(weeks),
            "feature_inventory": reviewed_inventory_with_outcomes(),
            "provider_vintage_disposition": "CLEAN",
            "findings": ["completed review record"],
            "remediation": ["completed remediation record"],
        }
        audit["artifact_sha256"] = prospective._artifact_hash(audit)
        return audit

    @staticmethod
    def week_grade(week, strong_delta):
        game_id = f"2026_{week:02d}_BUF_LAR"
        positions = (("QB", 24), ("RB", 30), ("WR", 30), ("TE", 12))
        predictions = prospective.rank_rows([{
            "season": 2026,
            "week": week,
            "game_id": game_id,
            "gsis_id": f"{position}-{index:03d}",
            "player_name": f"{position} {index:03d}",
            "team": "BUF" if index % 2 == 0 else "LAR",
            "opponent": "LAR" if index % 2 == 0 else "BUF",
            "position": position,
            "null_prediction": 10.0 + strong_delta,
            "strong_prediction": 10.0,
            "history_count": 0,
            "initialization_reason": "TRUE_COLD_START",
            "availability_status": "ACTIVE",
            "ranking_eligible": True,
            "config_sha256": "c" * 64,
        } for position, count in positions for index in range(count)])
        primary = pgo_fantasy.select_primary_pool(predictions)
        rows = []
        for prediction in predictions:
            key = prediction["game_id"], prediction["gsis_id"]
            actual = 10.0
            rows.append({
                **prediction,
                "fantasy_points": actual,
                "primary_pool": key in primary,
                "null_absolute_error": abs(actual - prediction["null_prediction"]),
                "strong_absolute_error": abs(actual - prediction["strong_prediction"]),
                "improvement": abs(actual - prediction["null_prediction"])
                - abs(actual - prediction["strong_prediction"]),
            })
        null_mae = abs(float(strong_delta))
        grade = {
            "schema_version": 1,
            "artifact_kind": "PGO_FANTASY_WEEK_GRADE",
            "status": "HOLD",
            "publication_status": "EXPERIMENTAL",
            "season": 2026,
            "week": week,
            "model_version": "pgo_fantasy_2026_baseline_v1",
            "config_sha256": "c" * 64,
            "lock_sha256": [hashlib.sha256(
                f"lock-{week}".encode("ascii")
            ).hexdigest()],
            "result_receipt": {
                "schema_version": 1,
                "source": "synthetic-official-results",
                "source_as_of": "2027-01-11T00:00:00-05:00",
                "captured_at": "2027-01-11T00:00:00-05:00",
                "teams_processed": ["BUF", "LAR"],
                "games": 1,
                "rows": 96,
                "bytes": 1,
                "sha256": hashlib.sha256(
                    f"results-{week}".encode("ascii")
                ).hexdigest(),
            },
            "checks": {
                "complete_game_locks": True,
                "complete_game_results": True,
                "primary_pool_96": True,
                "exact_lock_binding": True,
            },
            "metrics": {"primary": {
                "count": 96,
                "null_mae": null_mae,
                "strong_mae": 0.0,
                "improvement": null_mae,
                "relative_improvement": 1.0 if null_mae > 0.0 else 0.0,
                "strong_win": null_mae > 0.0,
            }},
            "rows": rows,
        }
        grade["artifact_sha256"] = prospective._artifact_hash(grade)
        return prospective.verify_week_grade(grade)

    def test_incomplete_season_cannot_pass(self):
        weeks = [self.week_grade(week, strong_delta=1.0) for week in range(1, 18)]
        receipt = prospective.grade_season(weeks, self.audit(weeks, "CLEAN"))
        self.assertEqual(receipt["status"], "HOLD")
        self.assertFalse(receipt["checks"]["season_complete"])

    def test_complete_clear_improvement_passes_locked_gate(self):
        weeks = [self.week_grade(week, strong_delta=1.0) for week in range(1, 19)]
        receipt = prospective.grade_season(weeks, self.audit(weeks, "CLEAN"))
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["publication_status"], "VALIDATED")
        self.assertEqual(receipt["bootstrap"]["seed"], 20260901)
        self.assertEqual(receipt["bootstrap"]["samples"], 10_000)
        self.assertGreater(receipt["bootstrap"]["lower"], 0.0)

    def test_statistical_shortfall_holds_and_unclean_audit_blocks(self):
        weeks = [self.week_grade(week, strong_delta=0.0) for week in range(1, 19)]
        hold = prospective.grade_season(weeks, self.audit(weeks, "CLEAN"))
        self.assertEqual(hold["status"], "HOLD")
        blocked = prospective.grade_season(
            weeks, self.audit(weeks, "REVIEW REQUIRED")
        )
        self.assertEqual(blocked["status"], "BLOCKED")

    def test_mixed_model_versions_are_blocked(self):
        weeks = [self.week_grade(week, strong_delta=1.0) for week in range(1, 19)]
        weeks[-1]["model_version"] = "different"
        weeks[-1]["artifact_sha256"] = prospective._artifact_hash(weeks[-1])
        receipt = prospective.grade_season(weeks, self.audit(weeks, "CLEAN"))
        self.assertEqual(receipt["status"], "BLOCKED")

    def test_rehashed_incomplete_weekly_pool_cannot_pass(self):
        weeks = [self.week_grade(week, strong_delta=1.0) for week in range(1, 19)]
        weeks[-1]["rows"].pop()
        weeks[-1]["artifact_sha256"] = prospective._artifact_hash(weeks[-1])
        receipt = prospective.grade_season(weeks, self.audit(weeks, "CLEAN"))
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["checks"]["artifact_integrity"])
```

- [ ] **Step 2: Run Task 5 RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveSeasonGradeTests -v
```

Expected: ERROR for missing season-grade functions.

- [ ] **Step 3: Implement strict grade/audit loading and the full-season gate**

```python
BOOTSTRAP_SEED = 20260901
BOOTSTRAP_SAMPLES = 10_000
LEAKAGE_AUDIT_KEYS = frozenset({
    "schema_version", "artifact_kind", "status", "verdict", "audited_at",
    "scientific_contract", "model_version", "config_sha256", "code_sha",
    "position_mean_evidence_sha256", "weekly_evidence", "feature_inventory",
    "provider_vintage_disposition", "findings", "remediation", "artifact_sha256",
})


def load_week_grade(path):
    data = Path(path).read_bytes()
    grade = _decode_json(data, "weekly fantasy grade")
    verify_week_grade(grade)
    if data != serialize_week_grade(grade).encode("utf-8"):
        raise ValueError("Weekly fantasy grade is not canonical")
    return grade


def verify_leakage_audit(audit):
    if (
        not isinstance(audit, dict) or set(audit) != LEAKAGE_AUDIT_KEYS
        or type(audit["schema_version"]) is not int
        or audit["schema_version"] != 1
        or audit["artifact_kind"] != "PGO_FANTASY_PROSPECTIVE_LEAKAGE_AUDIT"
        or audit["status"] != "COMPLETE"
        or audit["verdict"] not in {"CLEAN", "REVIEW REQUIRED", "NOT CLEAN"}
        or audit["scientific_contract"] != "PGO_FANTASY_PROSPECTIVE_2026_SCIENTIFIC_V1"
    ):
        raise ValueError("Prospective leakage audit is invalid")
    parse_timestamp(audit["audited_at"], "leakage audited_at")
    # Require canonical, nonempty weekly evidence (week grade, result, lock,
    # source-receipt identities), the exact reviewed inventory, provider
    # disposition, and nonempty findings/remediation. CLEAN requires every
    # item and provider disposition to be CLEAN/PASS.
    if audit["artifact_sha256"] != _artifact_hash(audit):
        raise ValueError("Prospective leakage audit integrity is invalid")
    return audit


def load_leakage_audit(path):
    data = Path(path).read_bytes()
    audit = verify_leakage_audit(
        _decode_json(data, "prospective leakage audit")
    )
    if data != (canonical_json(audit) + "\n").encode("utf-8"):
        raise ValueError("Prospective leakage audit is not canonical")
    return audit


def _bootstrap_rows(rows):
    return [{
        "season": row["season"], "week": row["week"],
        "actual_margin": row["fantasy_points"],
        "pgo_v0_prediction": row["null_prediction"],
        "challenger_prediction": row["strong_prediction"],
    } for row in rows]


def grade_season(week_grades, leakage_audit):
    verify_leakage_audit(leakage_audit)
    valid_grades = []
    integrity = True
    for grade in week_grades:
        try:
            verify_week_grade(grade)
        except (TypeError, ValueError):
            integrity = False
            continue
        valid_grades.append(grade)
    versions = {
        (
            grade.get("model_version"), grade.get("config_sha256"),
            grade.get("code_sha"), grade.get("position_mean_evidence_sha256"),
        )
        for grade in valid_grades
    }
    weeks = {grade.get("week") for grade in valid_grades}
    complete = weeks == set(range(1, 19)) and len(valid_grades) == 18
    common_epoch = len(versions) == 1
    audit_binding = _audit_matches_grades(leakage_audit, valid_grades)
    audit_clean = leakage_audit["verdict"] == "CLEAN" and audit_binding
    weekly_primary_pools = (
        len(valid_grades) == len(week_grades)
        and all(
            grade["metrics"]["primary"]["count"] == 96
            and sum(row["primary_pool"] for row in grade["rows"]) == 96
            for grade in valid_grades
        )
    )
    rows = [
        row for grade in valid_grades for row in grade.get("rows", [])
        if row.get("primary_pool") is True
    ]
    if not rows:
        integrity = False
    null_mae = _mae(rows, "null_prediction") if rows else None
    strong_mae = _mae(rows, "strong_prediction") if rows else None
    relative = (
        (null_mae - strong_mae) / null_mae
        if rows and null_mae > 0.0 else 0.0
    )
    bootstrap = (
        pgo_challenger.paired_block_bootstrap(
            _bootstrap_rows(rows), BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED
        ) if rows else None
    )
    weekly_wins = sum(
        grade["metrics"]["primary"]["strong_win"]
        for grade in valid_grades
    )
    statistical = bool(
        complete and weekly_primary_pools
        and relative >= 0.01 and bootstrap is not None
        and bootstrap["lower"] > 0.0 and weekly_wins > 9 and audit_clean
    )
    blocked = (
        not integrity or not common_epoch
        or (complete and (not audit_clean or not weekly_primary_pools))
    )
    status = "BLOCKED" if blocked else "PASS" if statistical else "HOLD"
    model_version, config_sha256, code_sha, position_mean_evidence_sha256 = (
        next(iter(versions)) if len(versions) == 1 else (None, None, None, None)
    )
    receipt = {
        "schema_version": 1,
        "artifact_kind": "PGO_FANTASY_2026_SEASON_GRADE",
        "status": status,
        "publication_status": {
            "PASS": "VALIDATED", "HOLD": "EXPERIMENTAL", "BLOCKED": "BLOCKED",
        }[status],
        "season": 2026,
        "model_version": model_version,
        "config_sha256": config_sha256,
        "code_sha": code_sha,
        "position_mean_evidence_sha256": position_mean_evidence_sha256,
        "checks": {
            "season_complete": complete,
            "common_model_epoch": common_epoch,
            "weekly_primary_pools": weekly_primary_pools,
            "relative_improvement_at_least_1pct": relative >= 0.01,
            "bootstrap_lower_positive": bool(
                bootstrap is not None and bootstrap["lower"] > 0.0
            ),
            "strict_majority_weekly_wins": weekly_wins > 9,
            "leakage_audit_clean": audit_clean,
            "leakage_audit_binding": audit_binding,
            "artifact_integrity": integrity,
        },
        "metrics": {
            "primary_count": len(rows), "null_mae": null_mae,
            "strong_mae": strong_mae, "relative_improvement": relative,
            "weekly_wins": weekly_wins,
        },
        "bootstrap": bootstrap,
        "leakage_audit_sha256": leakage_audit.get("artifact_sha256"),
        "week_grade_sha256": sorted(
            grade["artifact_sha256"] for grade in valid_grades
        ),
    }
    receipt["artifact_sha256"] = _artifact_hash(receipt)
    return receipt


def serialize_season_grade(grade):
    if grade.get("artifact_sha256") != _artifact_hash(grade):
        raise ValueError("Season fantasy grade integrity is invalid")
    return canonical_json(grade) + "\n"


def write_season_grade(output_dir, grade):
    output_dir = Path(output_dir)
    return pgo_prospective._write_new_outputs(output_dir, (
        (output_dir / "fantasy_season_grade.json", serialize_season_grade(grade)),
    ))
```

- [ ] **Step 4: Run Task 5 GREEN twice to prove deterministic bootstrap output**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveSeasonGradeTests -v
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveSeasonGradeTests -v
```

Expected: both runs pass with identical serialized season receipt assertions.

- [ ] **Step 5: Commit Task 5**

```powershell
git add -- pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git commit -m "feat: gate prospective fantasy season"
```

---

### Task 6: Add the single CLI, BLOCKED diagnostics, and final verification

**Files:**
- Modify: `pgo_fantasy_prospective.py`
- Modify: `tests/test_pgo_fantasy_prospective.py`

**Interfaces:**
- Produces `main(argv: list[str] | None = None) -> int`.
- Commands are `preview`, `lock`, `grade-week`, and `grade-season`.
- Preview success returns 0. Lock success returns 0. PASS season grade returns 0. Weekly HOLD, incomplete/statistical HOLD, and BLOCKED return 1. An unwritable diagnostic returns 2.

- [ ] **Step 1: Add RED CLI end-to-end and failure-boundary tests**

```python
class ProspectiveFantasyCommandTests(
    ProspectiveFantasyFixture, unittest.TestCase
):
    def test_preview_and_lock_use_only_supplied_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            preview = paths["root"] / "preview.json"
            with (
                patch("urllib.request.urlopen") as remote,
                patch.object(
                    prospective, "_now",
                    return_value=prospective.parse_timestamp(
                        self.LOCKED_AT, "test clock"
                    ),
                ),
                patch.object(
                    prospective, "_current_code_sha", return_value="a" * 40
                ),
            ):
                self.assertEqual(prospective.main([
                    "preview", "--schedule", str(paths["schedule"]),
                    "--roster", str(paths["roster"]),
                    "--history", str(paths["history"]),
                    "--config", str(paths["config"]),
                    "--week", "1", "--as-of", self.CAPTURED,
                    "--output", str(preview),
                ]), 0)
                self.assertEqual(prospective.main([
                    "lock", "--schedule", str(paths["schedule"]),
                    "--roster", str(paths["roster"]),
                    "--availability", str(paths["availability"]),
                    "--history", str(paths["history"]),
                    "--config", str(paths["config"]),
                    "--game-id", "2026_01_BUF_LAR",
                    "--output-dir", str(paths["root"] / "lock"),
                    "--diagnostic-output", str(paths["root"] / "lock-blocked.json"),
                ]), 0)
            remote.assert_not_called()
            self.assertTrue(preview.is_file())
            self.assertTrue((paths["root"] / "lock" / "fantasy_lock.json").is_file())

    def test_after_t_lock_writes_only_exclusive_blocked_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.command_fixture(Path(directory))
            output = paths["root"] / "late-lock"
            diagnostic = paths["root"] / "late-blocked.json"
            command = [
                "lock", "--schedule", str(paths["schedule"]),
                "--roster", str(paths["roster"]),
                "--availability", str(paths["availability"]),
                "--history", str(paths["history"]),
                "--config", str(paths["config"]),
                "--game-id", "2026_01_BUF_LAR",
                "--output-dir", str(output),
                "--diagnostic-output", str(diagnostic),
            ]
            with (
                patch.object(
                    prospective, "_now",
                    return_value=prospective.parse_timestamp(
                        "2026-09-09T19:21:00-04:00", "test clock"
                    ),
                ),
                patch.object(
                    prospective, "_current_code_sha", return_value="a" * 40
                ),
            ):
                result = prospective.main(command)
            self.assertEqual(result, 1)
            self.assertFalse(output.exists())
            self.assertEqual(json.loads(diagnostic.read_text())["status"], "BLOCKED")
            first = diagnostic.read_bytes()
            with (
                patch.object(
                    prospective, "_now",
                    return_value=prospective.parse_timestamp(
                        "2026-09-09T19:21:00-04:00", "test clock"
                    ),
                ),
                patch.object(
                    prospective, "_current_code_sha", return_value="a" * 40
                ),
            ):
                self.assertEqual(prospective.main(command), 2)
            self.assertEqual(diagnostic.read_bytes(), first)

    def test_grade_commands_route_hold_and_pass_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(prospective, "load_game_lock", return_value={}),
                patch.object(prospective, "load_results", return_value={}),
                patch.object(
                    prospective, "grade_week", return_value={"status": "HOLD"}
                ),
                patch.object(prospective, "write_week_grade", return_value=True),
            ):
                self.assertEqual(prospective.main([
                    "grade-week", "--lock", str(root / "lock.json"),
                    "--results", str(root / "results.json"),
                    "--output-dir", str(root / "week"),
                    "--diagnostic-output", str(root / "week-blocked.json"),
                ]), 1)
            with (
                patch.object(prospective, "load_week_grade", return_value={}),
                patch.object(prospective, "load_leakage_audit", return_value={}),
                patch.object(
                    prospective, "grade_season", return_value={"status": "PASS"}
                ),
                patch.object(prospective, "write_season_grade", return_value=True),
            ):
                self.assertEqual(prospective.main([
                    "grade-season", "--week-grade", str(root / "week.json"),
                    "--leakage-audit", str(root / "audit.json"),
                    "--output-dir", str(root / "season"),
                    "--diagnostic-output", str(root / "season-blocked.json"),
                ]), 0)

    def test_code_sha_requires_a_clean_tracked_runtime(self):
        head = prospective.subprocess.CompletedProcess(
            (), 0, stdout="a" * 40 + "\n", stderr=""
        )
        clean = prospective.subprocess.CompletedProcess(
            (), 0, stdout="", stderr=""
        )
        dirty = prospective.subprocess.CompletedProcess(
            (), 0, stdout=" M pgo_fantasy.py\n", stderr=""
        )
        with patch.object(
            prospective.subprocess, "run", side_effect=(head, clean)
        ):
            self.assertEqual(prospective._current_code_sha(), "a" * 40)
        with patch.object(
            prospective.subprocess, "run", side_effect=(head, dirty)
        ):
            with self.assertRaisesRegex(ValueError, "not clean"):
                prospective._current_code_sha()

    def test_cli_help_lists_only_four_local_operations(self):
        with self.assertRaises(SystemExit) as caught:
            prospective.main(["--help"])
        self.assertEqual(caught.exception.code, 0)
```

- [ ] **Step 2: Run Task 6 RED**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveFantasyCommandTests -v
```

Expected: ERROR for the missing CLI.

- [ ] **Step 3: Add argparse, explicit local-path loading, and exclusive diagnostics**

Add `argparse` to imports, then append the following command boundary after all model functions:

```python
import argparse
import subprocess


CODE_PATHS = (
    "pgo_fantasy_prospective.py", "pgo_fantasy.py", "pgo_prospective.py",
    "pgo_challenger.py", "pgo_sources.py", "pgo_model.py", "release_ratings.py",
)


def _now():
    return datetime.now().astimezone()


def _current_code_sha():
    root = Path(__file__).resolve().parent
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if not _hex_digest(head, 40):
        raise ValueError("Current code SHA is invalid")
    status = subprocess.run(
        (
            "git", "status", "--porcelain=v1", "--untracked-files=all",
            "--", *CODE_PATHS,
        ),
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    if status.strip():
        raise ValueError("Prospective fantasy runtime code is not clean")
    return head


def _common_sources(args, availability_required):
    sources = {
        "schedule": load_snapshot(args.schedule, "schedule"),
        "roster": load_snapshot(args.roster, "roster"),
        "history": load_snapshot(args.history, "history"),
    }
    if args.availability is not None:
        sources["availability"] = load_snapshot(
            args.availability, "availability"
        )
    if availability_required and "availability" not in sources:
        raise ValueError("Availability source is required")
    return sources, load_model_config(args.config)


def _blocked(mode, error):
    receipt = {
        "schema_version": 1,
        "artifact_kind": "PGO_FANTASY_BLOCKED_DIAGNOSTIC",
        "status": "BLOCKED",
        "publication_status": "BLOCKED",
        "mode": mode,
        "error_type": type(error).__name__,
        "error": str(error),
    }
    receipt["artifact_sha256"] = _artifact_hash(receipt)
    return canonical_json(receipt) + "\n"


def _require_disjoint(path, protected, label):
    resolved = Path(path).resolve(strict=False)
    if any(
        resolved == Path(item).resolve(strict=False)
        or resolved in Path(item).resolve(strict=False).parents
        or Path(item).resolve(strict=False) in resolved.parents
        for item in protected
    ):
        raise ValueError(f"{label} overlaps frozen evidence")


def _write_blocked(path, mode, error, protected=()):
    _require_disjoint(path, protected, "Diagnostic output")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pgo_fantasy._exclusive_write_text(path, _blocked(mode, error))


def _parser():
    parser = argparse.ArgumentParser(
        description="Build and grade local PGO fantasy prospective evidence"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def sources(command, availability=False):
        command.add_argument("--schedule", type=Path, required=True)
        command.add_argument("--roster", type=Path, required=True)
        command.add_argument("--history", type=Path, required=True)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument(
            "--availability", type=Path, required=availability
        )

    preview = commands.add_parser("preview")
    sources(preview)
    preview.add_argument("--week", type=int, required=True)
    preview.add_argument("--as-of", required=True)
    preview.add_argument("--output", type=Path, required=True)

    lock = commands.add_parser("lock")
    sources(lock, availability=True)
    lock.add_argument("--game-id", required=True)
    lock.add_argument("--output-dir", type=Path, required=True)
    lock.add_argument("--diagnostic-output", type=Path, required=True)

    week = commands.add_parser("grade-week")
    week.add_argument("--lock", type=Path, action="append", required=True)
    week.add_argument("--results", type=Path, required=True)
    week.add_argument("--output-dir", type=Path, required=True)
    week.add_argument("--diagnostic-output", type=Path, required=True)

    season = commands.add_parser("grade-season")
    season.add_argument(
        "--week-grade", type=Path, action="append", required=True
    )
    season.add_argument("--leakage-audit", type=Path, required=True)
    season.add_argument("--output-dir", type=Path, required=True)
    season.add_argument("--diagnostic-output", type=Path, required=True)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    inputs, outputs = _inputs(args), _outputs(args)
    try:
        if args.command == "preview":
            sources, model = _common_sources(args, False)
            preview = build_preview(sources, model, args.week, args.as_of)
            _write_preview(args.output, serialize_preview(preview))
            return 0
        if args.command == "lock":
            sources, model = _common_sources(args, True)
            locked_at = _now().isoformat()
            lock = build_game_lock(
                sources, model, args.game_id, locked_at, _current_code_sha()
            )
            if not write_game_lock(args.output_dir, lock):
                raise ValueError("Fantasy game lock output already exists")
            return 0
        if args.command == "grade-week":
            grade = grade_week(
                [load_game_lock(path) for path in args.lock],
                load_results(args.results),
            )
            if not write_week_grade(args.output_dir, grade):
                raise ValueError("Fantasy week grade output already exists")
            return 1
        grades = [load_week_grade(path) for path in args.week_grade]
        grade = grade_season(grades, load_leakage_audit(args.leakage_audit))
        if not write_season_grade(args.output_dir, grade):
            raise ValueError("Fantasy season grade output already exists")
        return 0 if grade["status"] == "PASS" else 1
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        diagnostic = getattr(args, "diagnostic_output", None)
        if diagnostic is None:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        try:
            _write_blocked(
                diagnostic, args.command, error,
                _diagnostic_protected(args, inputs, outputs),
            )
        except (OSError, TypeError, ValueError):
            return 2
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused CLI and full prospective fantasy tests**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective.ProspectiveFantasyCommandTests -v
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy_prospective -v
```

Expected: all focused tests pass.

- [ ] **Step 5: Run protected regression suites**

```powershell
python -B -W error::ResourceWarning -m unittest `
  tests.test_pgo_fantasy `
  tests.test_pgo_prospective `
  tests.test_pgo_challenger `
  tests.test_pgo_comparison -v
```

Expected: all protected suites pass with zero `ResourceWarning`.

- [ ] **Step 6: Run the complete repository gate**

```powershell
python -B -W error::ResourceWarning -m unittest discover -s tests -v
python -m py_compile pgo_fantasy_prospective.py `
  tests/test_pgo_fantasy_prospective.py
git diff --check
```

Expected: the full suite, compilation, and diff check pass.

- [ ] **Step 7: Verify protected scope and prohibited inputs**

```powershell
git diff --name-only f1d7edfdd3a5a521377b680eb4e0d1bee17345ab -- `
  research data prospective_evidence docs/index.html .github/workflows SHOPIFY.md
rg -n "PFF|urllib|requests|http://|https://|prospective_evidence|research/" `
  pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git status --short
```

Expected:

- protected diff output is empty;
- prohibited-input scan finds only the test's mocked `urllib.request.urlopen` assertion and no runtime fetch or protected-path read;
- tracked changes are limited to the two runtime/test files plus the approved plan/spec documentation;
- unrelated untracked paths are unchanged.

- [ ] **Step 8: Commit Task 6**

```powershell
git add -- pgo_fantasy_prospective.py tests/test_pgo_fantasy_prospective.py
git commit -m "feat: add prospective fantasy commands"
```

- [ ] **Step 9: Perform independent implementation and scientific reviews**

Require two review passes before integration:

1. correctness/trust-boundary review of source-byte binding, T-60 timing, identities, canonical serialization, exclusive writes, exact grading, and version isolation; and
2. scientific/leakage review of the target, history cutoff, frozen position means, common 96-row pool, week-block uncertainty, PASS/HOLD/BLOCKED logic, and full-season firewall.

Any Critical or Important finding returns to the owning task with a focused RED regression, minimal shared-boundary fix, focused GREEN, protected suites, and full repository rerun.

## Execution Stop

Successful implementation completes only the synthetic/local evidence machinery. Stop before:

- reading or freezing real 2026 roster, inactive, schedule, history, or result files;
- computing or accepting the real frozen position means;
- creating an opening-night preview or T-60 lock;
- modifying public HTML, site generation, workflows, Shopify, navigation, or store content;
- pushing, deploying, or publishing; or
- changing any existing HOLD, historical, or team-model artifact.

Those are separate source-execution and release decisions after this implementation is reviewed and integrated.
