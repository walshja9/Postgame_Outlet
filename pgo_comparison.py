#!/usr/bin/env python3
"""Build a private McCabe-versus-PGO ratings comparison preview."""

import argparse
import csv
import html
import json
import math
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import generate_site
import pgo_challenger
import pgo_model
import snapshot
from release_ratings import atomic_write_text, load_release_rows, rating_total


HERE = Path(__file__).resolve().parent
MCCABE_PATH = HERE / "data" / "ratings.csv"
MODEL_PATH = HERE / "research" / "pgo_v1" / "ratings_2026_preseason.csv"
BACKTEST_PATH = HERE / "research" / "pgo_v1" / "backtest.json"
SNAPSHOTS_PATH = HERE / "data" / "snapshots.json"
PUBLIC_OUTPUT = HERE / "docs" / "index.html"
MCCABE_SNAPSHOT_LABEL = "Preseason 2026"
MODEL_NUMBER_FIELDS = (
    "full_strength_rating",
    "availability_adjustment",
    "current_lineup_rating",
    "headline_rating",
)


def default_preview_path(today=None):
    today = today or datetime.now().astimezone().date()
    return HERE / "output" / "pgo-comparison-preview" / today.isoformat() / "index.html"


def _finite(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"Invalid {label}: {value!r}")
    return number


def load_mccabe_rows(path):
    parsed = []
    for row in load_release_rows(path):
        team = row.get("team", "")
        if team not in generate_site.TEAM:
            raise ValueError(f"Unknown McCabe team: {team!r}")
        components = {
            name: _finite(row.get(name), f"{team} {name}")
            for name in ("qb_value", "off_value", "def_value")
        }
        rating = round(rating_total(components), 1)
        parsed.append({
            "team": team,
            "abbr": generate_site.TEAM[team][0],
            "rating": rating,
        })
    expected = set(pgo_model.CURRENT_TEAMS)
    if len(parsed) != 32 or {row["abbr"] for row in parsed} != expected:
        raise ValueError("McCabe comparison requires exactly the 32 current teams")
    parsed.sort(key=lambda row: -row["rating"])
    for rank, row in enumerate(parsed, 1):
        row["rank"] = rank
    return parsed


def load_mccabe_snapshot(path, rows):
    snaps = snapshot.load_snaps(path)
    if MCCABE_SNAPSHOT_LABEL not in snaps:
        raise ValueError(f"Missing McCabe snapshot: {MCCABE_SNAPSHOT_LABEL}")
    entry = snapshot.normalize_snapshot_entry(snaps[MCCABE_SNAPSHOT_LABEL])
    if not entry["published_at"]:
        raise ValueError("McCabe comparison snapshot has no published_at")
    current = {row["team"]: row["rating"] for row in rows}
    frozen = {
        row["team"]: _finite(row.get("rating"), f"{row.get('team')} rating")
        for row in entry["rows"]
    }
    if frozen != current:
        raise ValueError("Reviewed McCabe ratings do not match the frozen snapshot")
    return {
        "mccabe_edition": MCCABE_SNAPSHOT_LABEL,
        "mccabe_published_at": entry["published_at"],
    }


def validate_receipt(receipt):
    status = receipt.get("status")
    expected_publication = pgo_challenger.PUBLICATION_STATUS.get(status)
    if (
        status not in {"HOLD", "PASS"}
        or receipt.get("publication_status") != expected_publication
    ):
        raise ValueError("PGO model receipt is not eligible for comparison")
    checks = receipt.get("checks")
    if pgo_challenger.classify_release(checks) != status:
        raise ValueError("PGO model receipt status contradicts its checks")
    if not all(checks[name] for name in pgo_challenger.INTEGRITY_GATE_NAMES):
        raise ValueError("PGO model integrity gates did not pass")
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed != receipt.get("failed_checks"):
        raise ValueError("PGO model failed-check receipt is inconsistent")
    return receipt


def load_model_rows(path, receipt):
    expected_label = pgo_challenger.PUBLICATION_STATUS[receipt["status"]]
    expected_reason = (
        "All historical gates passed"
        if receipt["status"] == "PASS"
        else "Historical HOLD: " + ", ".join(receipt["failed_checks"])
    )
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != pgo_challenger.RATING_COLUMNS:
            raise ValueError("PGO ratings schema does not match the release contract")
        rows = list(reader)
    if len(rows) != 32 or {row["team"] for row in rows} != set(pgo_model.CURRENT_TEAMS):
        raise ValueError("PGO comparison requires exactly the 32 current teams")
    if {row["validation_status"] for row in rows} != {expected_label}:
        raise ValueError("PGO ratings label contradicts the receipt")
    if {row["status_reason"] for row in rows} != {expected_reason}:
        raise ValueError("PGO ratings reason contradicts the receipt")
    if {row["as_of"] for row in rows} != {str(receipt["as_of"])}:
        raise ValueError("PGO ratings as-of time contradicts the receipt")

    parsed = []
    for row in rows:
        item = dict(row)
        try:
            item["rank"] = int(row["rank"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid PGO rank for {row['team']}") from error
        for name in MODEL_NUMBER_FIELDS:
            item[name] = _finite(row.get(name), f"{row['team']} {name}")
        if not math.isclose(
            item["full_strength_rating"] + item["availability_adjustment"],
            item["current_lineup_rating"],
            abs_tol=1e-6,
        ):
            raise ValueError(f"PGO rating algebra failed for {row['team']}")
        if item["headline_view"] not in {"full_strength", "current_lineup"}:
            raise ValueError(f"Invalid PGO headline view for {row['team']}")
        expected_headline = item[
            "full_strength_rating"
            if item["headline_view"] == "full_strength"
            else "current_lineup_rating"
        ]
        if not math.isclose(item["headline_rating"], expected_headline, abs_tol=1e-6):
            raise ValueError(f"PGO headline rating failed for {row['team']}")
        parsed.append(item)
    if sorted(row["rank"] for row in parsed) != list(range(1, 33)):
        raise ValueError("PGO full-strength ranks must be 1 through 32")
    return parsed


def build_comparison_rows(mccabe_rows, model_rows):
    mccabe_by_abbr = {row["abbr"]: row for row in mccabe_rows}
    model_by_abbr = {row["team"]: row for row in model_rows}
    if set(mccabe_by_abbr) != set(model_by_abbr):
        raise ValueError("McCabe and PGO team sets do not match")
    current_ranks = {
        row["team"]: rank
        for rank, row in enumerate(
            sorted(
                model_rows,
                key=lambda row: (-row["current_lineup_rating"], row["team"]),
            ),
            1,
        )
    }
    output = []
    for mccabe in sorted(mccabe_rows, key=lambda row: row["rank"]):
        model = model_by_abbr[mccabe["abbr"]]
        current_rank = current_ranks[model["team"]]
        headline_rank = (
            model["rank"]
            if model["headline_view"] == "full_strength"
            else current_rank
        )
        output.append({
            "team": mccabe["team"],
            "abbr": mccabe["abbr"],
            "mccabe_rank": mccabe["rank"],
            "mccabe_rating": mccabe["rating"],
            "full_strength_rank": model["rank"],
            "full_strength_rating": model["full_strength_rating"],
            "availability_adjustment": model["availability_adjustment"],
            "current_lineup_rank": current_rank,
            "current_lineup_rating": model["current_lineup_rating"],
            "rank_disagreement": headline_rank - mccabe["rank"],
            "rating_disagreement": model["headline_rating"] - mccabe["rating"],
        })
    return output


def load_comparison_rows(
    mccabe_path,
    model_path,
    backtest_path,
    snapshots_path=SNAPSHOTS_PATH,
    require_immutable=False,
):
    receipt = validate_receipt(
        json.loads(Path(backtest_path).read_text(encoding="utf-8"))
    )
    mccabe_rows = load_mccabe_rows(mccabe_path)
    receipt = {
        **receipt,
        **load_mccabe_snapshot(snapshots_path, mccabe_rows),
    }
    if require_immutable:
        receipt["receipt_ref"] = require_immutable_artifacts(
            backtest_path, model_path
        )
    return build_comparison_rows(
        mccabe_rows,
        load_model_rows(model_path, receipt),
    ), receipt


def immutable_git_ref(path):
    try:
        relative = Path(path).resolve().relative_to(HERE.resolve()).as_posix()
        subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", relative],
            cwd=HERE,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", relative],
            cwd=HERE,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        raise ValueError(
            "PGO publication artifact must be committed and unmodified"
        ) from error
    receipt_ref = result.stdout.strip()
    if len(receipt_ref) != 40 or any(
        character not in "0123456789abcdef" for character in receipt_ref.lower()
    ):
        raise ValueError("PGO receipt has no immutable Git commit reference")
    return receipt_ref


def require_immutable_artifacts(backtest_path, model_path):
    receipt_ref = immutable_git_ref(backtest_path)
    ratings_ref = immutable_git_ref(model_path)
    if receipt_ref != ratings_ref:
        raise ValueError(
            "PGO receipt and ratings artifact must be from the same Git commit"
        )
    return receipt_ref


MODEL_CSS = """
#panel-comparison .model-status {
  display:inline-block; margin:0 0 12px; padding:6px 10px;
  border:1px solid var(--orange); border-radius:999px;
  color:var(--ink); font-weight:700;
}
#panel-comparison .comparison-summary { color:var(--mut); max-width:78ch; }
#panel-comparison .comparison-table th:first-child,
#panel-comparison .comparison-table td:first-child { text-align:left; }
#panel-comparison .comparison-table thead th:first-child,
#panel-comparison .comparison-table tbody th:first-child {
  position:sticky; left:0; z-index:1;
}
#panel-comparison .comparison-table thead th:first-child {
  background:var(--ink);
}
#panel-comparison .comparison-table tbody th:first-child {
  background:var(--panel); color:var(--ink);
}
#panel-comparison .comparison-links { margin-top:16px; }
@media (max-width:680px) {
  #panel-comparison .comparison-table { font-size:12px; }
  #panel-comparison .comparison-table th,
  #panel-comparison .comparison-table td { padding:8px 7px; }
}
"""


def _signed(value):
    return f"{value:+.1f}"


def render_comparison_panel(rows, receipt):
    rows = sorted(
        rows,
        key=lambda row: (row["full_strength_rank"], row["team"]),
    )
    receipt_ref = receipt.get("receipt_ref")
    receipt_link = (
        f'<a href="https://github.com/walshja9/Postgame_Outlet/blob/'
        f'{html.escape(str(receipt_ref), quote=True)}'
        '/research/pgo_v1/backtest.json" target="_blank" '
        'rel="noopener noreferrer">Backtest receipt</a>'
        if receipt_ref
        else "<span>Backtest receipt available on publish</span>"
    )
    interval = receipt["aggregate_interval"]
    metrics = receipt["metrics"]
    label = (
        "Validated model \N{EM DASH} PASS"
        if receipt["status"] == "PASS"
        else "Experimental model \N{EM DASH} HOLD"
    )
    reason = (
        "All historical gates passed"
        if not receipt["failed_checks"]
        else "Hold reason: " + ", ".join(
            name.replace("_", " ") for name in receipt["failed_checks"]
        )
    )
    body = "\n".join(
        "<tr>"
        f'<th scope="row" data-sort="{html.escape(row["team"].casefold())}">'
        f'{html.escape(row["team"])}</th>'
        f'<td data-sort="{row["full_strength_rank"]}">{row["full_strength_rank"]}</td>'
        f'<td data-sort="{row["full_strength_rating"]}">{_signed(row["full_strength_rating"])}</td>'
        f'<td data-sort="{row["availability_adjustment"]}">{_signed(row["availability_adjustment"])}</td>'
        f'<td data-sort="{row["current_lineup_rank"]}">{row["current_lineup_rank"]}</td>'
        f'<td data-sort="{row["current_lineup_rating"]}">{_signed(row["current_lineup_rating"])}</td>'
        f'<td data-sort="{row["mccabe_rank"]}">{row["mccabe_rank"]}</td>'
        f'<td data-sort="{row["mccabe_rating"]}">{_signed(row["mccabe_rating"])}</td>'
        f'<td data-sort="{row["rank_disagreement"]}">{row["rank_disagreement"]:+d}</td>'
        f'<td data-sort="{row["rating_disagreement"]}">{_signed(row["rating_disagreement"])}</td>'
        "</tr>"
        for row in rows
    )
    summary = (
        f'Backtest: v1 MAE {metrics["challenger"]["mae"]:.3f} vs '
        f'v0 {metrics["pgo_v0"]["mae"]:.3f}; improvement '
        f'{interval["mean"]:+.3f}, 95% CI '
        f'{interval["lower"]:+.3f} to {interval["upper"]:+.3f}.'
    )
    return f"""
  <section class="panel active" id="panel-comparison" role="tabpanel"
    aria-labelledby="tab-comparison">
    <div class="model-status">{html.escape(label)}</div>
    <h2>PGO v1 Power Ratings</h2>
    <p>Postgame Outlet's independent statistical rating, compared with McCabe's human rating and never blended.</p>
    <p class="comparison-summary">{html.escape(summary)}<br>
      McCabe {html.escape(receipt["mccabe_edition"])} locked
      {html.escape(receipt["mccabe_published_at"])}.<br>
      PGO {html.escape(receipt["version"])} as of
      {html.escape(str(receipt["as_of"]))}. {html.escape(reason)}.</p>
    <p class="visually-hidden comparison-sort-status" role="status" aria-live="polite"></p>
    <div class="table-shell">
      <table class="comparison-table">
        <caption class="visually-hidden">All 32 NFL teams comparing McCabe and PGO ratings</caption>
        <thead><tr>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="0">Team</button></th>
          <th scope="col" aria-sort="ascending"><button type="button" class="sort-button" data-column="1">PGO full #</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="2">PGO full</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="3">Avail.</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="4">PGO today #</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="5">PGO today</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="6">McCabe #</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="7">McCabe</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="8">Rank gap</button></th>
          <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-column="9">Rating gap</button></th>
        </tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
    <p class="legend">Positive rank gap means PGO ranks the team lower.
      Positive rating gap means PGO rates the team higher.</p>
    <p class="comparison-links">
      {receipt_link}
      &middot;
      <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/docs/superpowers/specs/2026-07-21-independent-forward-looking-pgo-model-design.md" target="_blank" rel="noopener noreferrer">Methodology and release rules</a>
    </p>
  </section>
"""


COMPARISON_TAB = """
    <button type="button" class="tab active" id="tab-comparison" role="tab"
      aria-selected="true" aria-controls="panel-comparison" tabindex="0"
      data-panel="comparison">PGO Model</button>
"""


COMPARISON_SCRIPT = """
<script>
  (() => {
    const panel = document.querySelector('#panel-comparison');
    const body = panel && panel.querySelector('.comparison-table tbody');
    const status = panel && panel.querySelector('.comparison-sort-status');
    const buttons = panel ? [...panel.querySelectorAll('.comparison-table .sort-button')] : [];
    if (!body || !status || buttons.length === 0) return;

    let activeColumn = 1;
    let ascending = true;

    function value(row, index) {
      const raw = row.children[index].dataset.sort;
      const numeric = index !== 0;
      return numeric ? Number(raw) : raw;
    }

    buttons.forEach(button => {
      button.addEventListener('click', () => {
        const column = Number(button.dataset.column);
        ascending = column === activeColumn ? !ascending : true;
        activeColumn = column;
        [...body.rows].sort((a, b) => {
          const left = value(a, column);
          const right = value(b, column);
          const order = typeof left === 'number'
            ? left - right
            : left.localeCompare(right);
          const directed = ascending ? order : -order;
          return directed || a.children[0].dataset.sort.localeCompare(
            b.children[0].dataset.sort
          );
        }).forEach(row => body.appendChild(row));
        buttons.forEach(candidate => {
          candidate.closest('th').setAttribute('aria-sort', 'none');
        });
        button.closest('th').setAttribute(
          'aria-sort', ascending ? 'ascending' : 'descending'
        );
        status.textContent = button.textContent.trim() + ' sorted '
          + (ascending ? 'ascending' : 'descending');
      });
    });
  })();
</script>
"""


def inject_comparison(base_html, panel_html):
    rating_tab = (
        '    <button type="button" class="tab active" id="tab-ratings"'
    )
    rating_panel = (
        '  <section class="panel active" id="panel-ratings"'
    )
    fixed_replacements = (
        (
            '<meta name="description" content="Sean McCabe’s',
            '<meta name="description" content="Postgame Outlet’s independent PGO v1',
        ),
        (
            '<div class="updated">By Sean McCabe &middot;',
            '<div class="updated">By Postgame Outlet Model &middot;',
        ),
        (
            'aria-selected="true" aria-controls="panel-ratings" tabindex="0"',
            'aria-selected="false" aria-controls="panel-ratings" tabindex="-1"',
        ),
        (
            'data-panel="ratings">Power Ratings</button>',
            'data-panel="ratings">McCabe Ratings</button>',
        ),
        (">QB Ratings</button>", ">McCabe QBs</button>"),
        (">Methodology</button>", ">McCabe Method</button>"),
    )
    markers = (
        "</style>",
        "</body>",
        rating_tab,
        rating_panel,
        *(old for old, _new in fixed_replacements),
    )
    if any(base_html.count(marker) != 1 for marker in markers):
        raise ValueError("Base ratings template markers changed")
    output = base_html.replace(
        "</style>", MODEL_CSS + '\n</style>\n<link rel="icon" href="data:,">', 1
    )
    for old, new in fixed_replacements:
        output = output.replace(old, new, 1)
    output = output.replace(
        rating_tab,
        COMPARISON_TAB
        + '    <button type="button" class="tab" id="tab-ratings"',
        1,
    )
    output = output.replace(
        rating_panel,
        panel_html
        + '\n  <section class="panel" id="panel-ratings" hidden',
        1,
    )
    output = output.replace("</body>", COMPARISON_SCRIPT + "\n</body>", 1)
    return output


def extract_comparison_panel(existing_html):
    start_marker = '<section class="panel active" id="panel-comparison"'
    start = existing_html.find(start_marker)
    if start < 0:
        raise ValueError(
            "Existing public board has no PGO comparison panel; publish an approved PGO release first"
        )
    end_marker = "</section>"
    end = existing_html.find(end_marker, start)
    if end < 0:
        raise ValueError("Existing PGO comparison panel is incomplete")
    return existing_html[start:end + len(end_marker)]


def mccabe_source_timestamp(path):
    try:
        relative = Path(path).resolve().relative_to(HERE.resolve()).as_posix()
        history = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=HERE,
            check=True,
            capture_output=True,
            text=True,
        )
        if history.stdout.strip().lower() == "true":
            raise ValueError(
                "Current McCabe source timestamp requires full Git history"
            )
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", relative],
            cwd=HERE,
            check=True,
            capture_output=True,
            text=True,
        )
    except ValueError:
        raise
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Could not determine the current McCabe source timestamp") from error
    timestamp = result.stdout.strip()
    if not timestamp:
        raise ValueError("Current McCabe source has no Git timestamp")
    return timestamp


def _cell_sort_value(cell, label):
    match = re.search(r'data-sort="([^"]+)"', cell)
    if not match:
        raise ValueError(f"Existing PGO comparison cell has no sort value: {label}")
    try:
        return float(match.group(1))
    except ValueError as error:
        raise ValueError(
            f"Existing PGO comparison cell has an invalid sort value: {label}"
        ) from error


def _replace_comparison_cell(cell, sort_value, display):
    cell = re.sub(
        r'data-sort="[^"]+"',
        f'data-sort="{html.escape(str(sort_value), quote=True)}"',
        cell,
        count=1,
    )
    return re.sub(r">[^<>]*</td>\Z", f">{display}</td>", cell, count=1)


def _refresh_comparison_metadata(panel_html, source_timestamp):
    old_pattern = re.compile(
        r"McCabe (?P<edition>[^<\r\n]+?) locked\s+"
        r"(?P<published>\d{4}-\d{2}-\d{2}T[^\s<]+)\.<br>"
    )
    current_pattern = re.compile(
        r"Current McCabe ratings from data/ratings\.csv as of\s+"
        r"(?P<source>\d{4}-\d{2}-\d{2}T[^\s<]+)\.\s+"
        r"Historical (?P<edition>[^<\r\n]+?) snapshot locked\s+"
        r"(?P<published>\d{4}-\d{2}-\d{2}T[^\s<]+)\.<br>"
    )
    match = old_pattern.search(panel_html) or current_pattern.search(panel_html)
    if not match:
        raise ValueError("Existing PGO comparison panel has no McCabe metadata")
    edition = match.group("edition")
    published = match.group("published")
    replacement = (
        "Current McCabe ratings from data/ratings.csv as of\n"
        f"      {html.escape(source_timestamp)}. Historical {html.escape(edition)} "
        "snapshot locked\n"
        f"      {html.escape(published)}.<br>"
    )
    return panel_html[:match.start()] + replacement + panel_html[match.end():]


def _refresh_comparison_panel(panel_html, mccabe_rows, source_timestamp):
    mccabe_by_team = {row["team"].casefold(): row for row in mccabe_rows}
    seen = set()
    row_pattern = re.compile(r"<tr\b[^>]*>.*?</tr>", re.DOTALL)
    cell_pattern = re.compile(r"<td\b[^>]*>.*?</td>", re.DOTALL)
    team_pattern = re.compile(r'<th\b[^>]*data-sort="([^"]+)"', re.DOTALL)

    def refresh_row(match):
        row_html = match.group(0)
        team_match = team_pattern.search(row_html)
        if not team_match:
            return row_html
        team_key = html.unescape(team_match.group(1)).casefold()
        if team_key not in mccabe_by_team:
            raise ValueError(f"Existing PGO comparison has unknown team: {team_key}")
        cells = cell_pattern.findall(row_html)
        if len(cells) != 9:
            raise ValueError(f"Existing PGO comparison row is incomplete: {team_key}")

        old_rank = int(_cell_sort_value(cells[5], f"{team_key} McCabe rank"))
        old_rating = _cell_sort_value(cells[6], f"{team_key} McCabe rating")
        headline_rank = old_rank + int(
            _cell_sort_value(cells[7], f"{team_key} rank gap")
        )
        headline_rating = old_rating + _cell_sort_value(
            cells[8], f"{team_key} rating gap"
        )
        current = mccabe_by_team[team_key]
        updates = {
            5: (current["rank"], str(current["rank"])),
            6: (current["rating"], _signed(current["rating"])),
            7: (
                headline_rank - current["rank"],
                f"{headline_rank - current['rank']:+d}",
            ),
            8: (
                headline_rating - current["rating"],
                _signed(headline_rating - current["rating"]),
            ),
        }

        cell_index = 0

        def replace_cell(cell_match):
            nonlocal cell_index
            current_index = cell_index
            cell_index += 1
            if current_index not in updates:
                return cell_match.group(0)
            sort_value, display = updates[current_index]
            return _replace_comparison_cell(
                cell_match.group(0), sort_value, display
            )

        seen.add(team_key)
        return cell_pattern.sub(replace_cell, row_html)

    refreshed = row_pattern.sub(refresh_row, panel_html)
    if seen != set(mccabe_by_team):
        missing = sorted(set(mccabe_by_team) - seen)
        raise ValueError(f"Existing PGO comparison is missing teams: {missing}")
    return _refresh_comparison_metadata(refreshed, source_timestamp)


def refresh_mccabe_page(base_html, existing_html, mccabe_path=MCCABE_PATH):
    mccabe_rows = load_mccabe_rows(mccabe_path)
    panel = _refresh_comparison_panel(
        extract_comparison_panel(existing_html),
        mccabe_rows,
        mccabe_source_timestamp(mccabe_path),
    )
    return inject_comparison(base_html, panel)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--output", type=Path, default=default_preview_path()
    )
    destination.add_argument(
        "--publish",
        action="store_true",
        help="write the reviewed combined page to docs/index.html",
    )
    destination.add_argument(
        "--refresh-mccabe",
        action="store_true",
        help="update the McCabe board while preserving the approved PGO panel",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        output = (
            PUBLIC_OUTPUT if (args.publish or args.refresh_mccabe) else args.output
        ).resolve()
        preview_root = (HERE / "output").resolve()
        if not (args.publish or args.refresh_mccabe) and preview_root not in output.parents:
            raise ValueError("Comparison output must stay under output/")
        config = generate_site.load_config()
        site_rows = generate_site.load_teams(generate_site.load_prior())
        team_ratings = {row["team"]: row["rating"] for row in site_rows}
        generate_site.build_html.qb_data = generate_site.load_qbs(team_ratings)
        base_html = generate_site.build_html(site_rows, config)
        if args.refresh_mccabe:
            preview = refresh_mccabe_page(
                base_html, PUBLIC_OUTPUT.read_text(encoding="utf-8")
            )
            comparison_rows = receipt = None
        else:
            comparison_rows, receipt = load_comparison_rows(
                MCCABE_PATH,
                MODEL_PATH,
                BACKTEST_PATH,
                require_immutable=args.publish,
            )
            preview = inject_comparison(
                base_html,
                render_comparison_panel(comparison_rows, receipt),
            )
        atomic_write_text(output, preview)
    except (csv.Error, KeyError, OSError, TypeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    if receipt:
        print(f"  {len(comparison_rows)} teams | {receipt['publication_status']}")
    else:
        print("  Preserved the existing approved PGO panel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
