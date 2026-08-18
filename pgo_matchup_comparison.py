"""Private PGO matchup preview adapter."""

import argparse
import csv
from datetime import UTC, datetime
from html import escape
import json
import math
from pathlib import Path
import sys

from release_ratings import atomic_write_text
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


def build_matchup_rows(payload, mccabe_ratings, pgo_ratings, hfa, default_hfa):
    """Build comparable, home-relative rows from the shared spread parser."""
    for event in payload.get("events", []):
        try:
            competition = event["competitions"][0]
            teams = {
                competitor["homeAway"]: competitor["team"]["displayName"]
                for competitor in competition["competitors"]
            }
            home, away = teams["home"], teams["away"]
        except (IndexError, KeyError, TypeError) as error:
            raise ValueError("invalid event teams") from error
        if home not in _EXPECTED_TEAMS or away not in _EXPECTED_TEAMS:
            raise ValueError("unknown event team")
        for odds in competition.get("odds") or []:
            if not isinstance(odds, dict):
                raise ValueError("invalid market spread")
            market = odds.get("spread")
            if market is not None and (isinstance(market, bool) or not isinstance(market, (int, float))
                                       or not math.isfinite(market)):
                raise ValueError("invalid market spread")

    def index_games(ratings, label):
        indexed = {}
        for game in spreads.parse_games(payload, ratings, hfa, default_hfa):
            key = (game["date"], game["home"], game["away"])
            if key in indexed:
                raise ValueError(f"duplicate {label} game key")
            indexed[key] = game
        return indexed

    mccabe_games = index_games(mccabe_ratings, "McCabe")
    pgo_games = index_games(pgo_ratings, "PGO")
    if mccabe_games.keys() != pgo_games.keys():
        raise ValueError("unmatched model game keys")

    rows = []
    for key in sorted(mccabe_games):
        mccabe_game, pgo_game = mccabe_games[key], pgo_games[key]
        market = mccabe_game["market"]
        rows.append({
            "date": mccabe_game["date"], "prime": mccabe_game["prime"],
            "home": mccabe_game["home"], "away": mccabe_game["away"],
            "market": market, "details": mccabe_game["details"],
            "mccabe_line": mccabe_game["my_spread"], "pgo_line": pgo_game["my_spread"],
            "mccabe_edge": None if market is None else round(market - mccabe_game["my_spread"], 1),
            "pgo_edge": None if market is None else round(market - pgo_game["my_spread"], 1),
            "mccabe_hfa": mccabe_game["hfa"], "pgo_hfa": pgo_game["hfa"],
        })
    return rows


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


def _captured_utc(captured_at):
    return captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _display_line(home, value):
    return "Unavailable" if value is None else spreads.fmt_spread(home, value)


def _display_edge(value):
    return "Unavailable" if value is None else f"{value:+.1f}"


def render_preview(rows, metadata, *, year, week, captured_at, source_url):
    """Render a self-contained private comparison preview."""
    captured = _captured_utc(captured_at)
    body = []
    for row in rows:
        matchup = f'{row["away"]} @ {row["home"]}' + (" ★" if row["prime"] else "")
        market = row.get("details") or "Unavailable"
        body.append(
            "<tr>"
            f'<td class="left">{escape(matchup)}</td>'
            f"<td>{escape(str(row['date']))}</td>"
            f"<td>{escape(_display_line(row['home'], row['mccabe_line']))}</td>"
            f"<td>{escape(_display_line(row['home'], row['pgo_line']))}</td>"
            f"<td>{escape(market)}</td>"
            f"<td>{escape(_display_edge(row['mccabe_edge']))}</td>"
            f"<td>{escape(_display_edge(row['pgo_edge']))}</td>"
            f'<td>{escape(source_url)}<br><small>{escape(captured)}</small></td>'
            "</tr>"
        )
    failed = ", ".join(metadata.get("failed_checks") or []) or "None"
    return f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">
<title>Private PGO Matchup Preview</title><style>
body{{background:#0e1117;color:#e6edf3;font:15px -apple-system,Segoe UI,Roboto,sans-serif}}.wrap{{max-width:1280px;margin:24px auto;padding:0 16px}}table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #283041}}th,td{{padding:9px 12px;text-align:right;border-bottom:1px solid #283041;vertical-align:top}}th{{background:#11161f;color:#8b949e;font-size:11px;text-transform:uppercase}}.left{{text-align:left}}.sub{{color:#8b949e;font-size:13px}}small{{color:#8b949e}}
</style></head><body><div class=\"wrap\"><h1>Private preview: {escape(str(year))} NFL Week {escape(str(week))}</h1>
<p class=\"sub\">McCabe, PGO, and market numbers are independent matchup lines, not league ranks or a blended rating.</p>
<p class=\"sub\">PGO artifact: {escape(str(metadata['artifact_path']))}<br>As of: {escape(str(metadata['as_of']))}<br>Validation: {escape(str(metadata['display_status']))} ({escape(str(metadata['validation_status']))})<br>HOLD reason: {escape(str(metadata.get('status_reason') or 'None'))}<br>Failed checks: {escape(failed)}<br>ESPN URL: {escape(source_url)}<br>UTC capture: {escape(captured)}</p>
<table><thead><tr><th class=\"left\">Matchup</th><th>Kickoff</th><th>McCabe line</th><th>PGO fair line</th><th>Market</th><th>McCabe edge</th><th>PGO edge</th><th>Market source / capture</th></tr></thead><tbody>{''.join(body)}</tbody></table></div></body></html>"""


def default_preview_path(captured_at):
    date = captured_at.astimezone(UTC).date().isoformat()
    return OUTPUT_ROOT / "pgo-matchup-preview" / date / "index.html"


def write_preview(html, path):
    candidate = Path(path).resolve()
    root = OUTPUT_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("preview output must remain under output/") from error
    atomic_write_text(candidate, html)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write a private PGO matchup preview.")
    parser.add_argument("week", nargs="?", type=int, default=1)
    parser.add_argument("year", nargs="?", type=int, default=2026)
    parser.add_argument("--pgo-ratings", default=PGO_RATINGS_PATH)
    parser.add_argument("--pgo-receipt", default=PGO_RECEIPT_PATH)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        captured_at = datetime.now(UTC)
        payload = spreads.fetch_week(args.week, args.year)
        mccabe_ratings = spreads.load_ratings()
        hfa, default_hfa = spreads.load_hfa()
        pgo_ratings, metadata = load_pgo_ratings(args.pgo_ratings, args.pgo_receipt)
        rows = build_matchup_rows(payload, mccabe_ratings, pgo_ratings, hfa, default_hfa)
        output = Path(args.output) if args.output else default_preview_path(captured_at)
        write_preview(render_preview(
            rows, metadata, year=args.year, week=args.week,
            captured_at=captured_at, source_url=ENDPOINT.format(year=args.year, week=args.week),
        ), output)
    except Exception as error:  # CLI boundary: fetch, validation, and write failures are nonzero.
        print(f"preview failed: {error}", file=sys.stderr)
        return 1
    print(f"wrote private preview: {Path(output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
