"""Private PGO matchup preview adapter."""

import csv
import json
import math
from pathlib import Path

import spreads


HERE = Path(__file__).resolve().parent
OUTPUT_ROOT = HERE / "output"
PGO_RATINGS_PATH = HERE / "research" / "pgo_v1" / "ratings_2026_preseason.csv"
PGO_RECEIPT_PATH = PGO_RATINGS_PATH.with_name("backtest.json")
ENDPOINT = spreads.ENDPOINT

_REQUIRED_COLUMNS = {"team", "headline_rating", "as_of", "validation_status"}
_TEAM_BY_ABBR = {abbreviation: team for team, abbreviation in spreads.ABBR.items()}
_EXPECTED_TEAM_COUNT = 32
_EXPECTED_TEAMS = frozenset(_TEAM_BY_ABBR.values())


def load_pgo_ratings(path, receipt_path=None):
    """Load one validated-or-held PGO ratings artifact without publishing it."""
    artifact_path = Path(path)
    receipt_path = Path(receipt_path) if receipt_path else artifact_path.with_name("backtest.json")
    try:
        with artifact_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
            missing = _REQUIRED_COLUMNS - fields
            if missing:
                raise ValueError(f"{artifact_path}: missing required columns: {', '.join(sorted(missing))}")
            rows = list(reader)
    except (OSError, csv.Error) as error:
        raise ValueError(f"{artifact_path}: cannot read ratings artifact: {error}") from error

    ratings, as_of_values, statuses, reasons = {}, set(), set(), set()
    for row in rows:
        abbreviation = row["team"]
        team = _TEAM_BY_ABBR.get(abbreviation)
        if team is None:
            raise ValueError(f"{artifact_path}: unknown team abbreviation {abbreviation!r}")
        if team in ratings:
            raise ValueError(f"{artifact_path}: duplicate team {abbreviation!r}")
        try:
            rating = float(row["headline_rating"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"{artifact_path}: team {abbreviation!r} has invalid headline_rating") from error
        if not math.isfinite(rating):
            raise ValueError(f"{artifact_path}: team {abbreviation!r} headline_rating must be finite")
        ratings[team] = rating
        as_of_values.add(row["as_of"])
        statuses.add(row["validation_status"])
        if "status_reason" in fields:
            reasons.add(row.get("status_reason", ""))

    if len(ratings) != _EXPECTED_TEAM_COUNT or set(ratings) != _EXPECTED_TEAMS:
        raise ValueError(f"{artifact_path}: requires the expected {_EXPECTED_TEAM_COUNT} current teams, found {len(ratings)}")
    if len(as_of_values) != 1:
        raise ValueError(f"{artifact_path}: inconsistent as_of values")
    if statuses - {"EXPERIMENTAL", "VALIDATED"} or len(statuses) != 1:
        raise ValueError(f"{artifact_path}: invalid validation_status")
    if len(reasons) > 1:
        raise ValueError(f"{artifact_path}: inconsistent status_reason values")
    as_of = as_of_values.pop()
    validation_status = statuses.pop()

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{receipt_path}: cannot read receipt: {error}") from error
    if not isinstance(receipt, dict):
        raise ValueError(f"{receipt_path}: receipt must be an object")
    if receipt.get("as_of") != as_of:
        raise ValueError(f"{receipt_path}: receipt as_of does not match {artifact_path}")
    checks = receipt.get("checks")
    failed_checks = receipt.get("failed_checks")
    if not isinstance(checks, dict) or not checks or not all(isinstance(value, bool) for value in checks.values()):
        raise ValueError(f"{receipt_path}: receipt checks must be a non-empty boolean map")
    if not isinstance(failed_checks, list) or any(not isinstance(name, str) for name in failed_checks):
        raise ValueError(f"{receipt_path}: receipt failed_checks must be a list")
    expected_failed = [name for name, passed in checks.items() if not passed]
    if failed_checks != expected_failed:
        raise ValueError(f"{receipt_path}: receipt failed_checks do not match checks")
    status = receipt.get("status")
    expected_receipt_status = "HOLD" if failed_checks else "PASS"
    if "status" in receipt and status != expected_receipt_status:
        raise ValueError(f"{receipt_path}: receipt status does not match checks")

    return ratings, {
        "artifact_path": str(artifact_path),
        "receipt_path": str(receipt_path),
        "as_of": as_of,
        "validation_status": validation_status,
        "display_status": "VALIDATED" if validation_status == "VALIDATED" and not failed_checks else "HOLD",
        "status_reason": receipt.get("status_reason") or next(iter(reasons), ""),
        "failed_checks": failed_checks,
        "checks": checks,
    }
