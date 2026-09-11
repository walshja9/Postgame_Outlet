#!/usr/bin/env python3
"""Render the frozen 2026 PGO Forecast Lab without fetching or grading."""

import argparse
import csv
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import generate_site
import pgo_comparison
import pgo_current_board
from pgo_challenger import PERFORMANCE_FEATURES, QB_FEATURES, _rest_difference
import pgo_forecast_snapshot
import pgo_forecast_weekly
import pgo_prospective
from release_ratings import atomic_write_text


FORECAST_DISPLAY_SCRIPT = """<script>
let weeklyLockTimer;
function updateWeeklyLocks() {
  clearTimeout(weeklyLockTimer);
  const now = Date.now();
  let next = now + 60000;
  document.querySelectorAll('[data-weekly-cutoff]').forEach(node => {
    const cutoff = Date.parse(node.dataset.weeklyCutoff);
    node.textContent = now >= cutoff ? 'Locked' : 'Draft';
    if (cutoff > now) next = Math.min(next, cutoff);
  });
  document.querySelectorAll('[data-freshness-at]').forEach(node => {
    const checked = Date.parse(node.dataset.freshnessAt);
    const minutes = Number(node.dataset.freshnessMinutes);
    const locked = now >= Date.parse(node.dataset.freshnessUntil);
    const valid = Number.isFinite(checked) && minutes > 0;
    const overdue = valid && !locked && now - checked > minutes * 60000;
    node.textContent = !valid ? 'Check time unavailable' : checked > now ? 'Check time ahead of this clock' : locked ? (node.dataset.freshnessEndedLabel || 'Updates closed at lock') : overdue ? 'Update overdue' : 'Recently checked';
    node.dataset.overdue = String(overdue);
  });
  if (document.querySelector('[data-weekly-cutoff],[data-freshness-at]')) weeklyLockTimer = setTimeout(updateWeeklyLocks, Math.max(1, next - now));
}
updateWeeklyLocks();
function openFragment(hash) {
  const target = document.getElementById(hash.slice(1));
  if (!target) return;
  const panel = target.closest('[role="tabpanel"]');
  if (panel && panel.hidden) {
    const tab = document.getElementById(panel.getAttribute('aria-labelledby'));
    if (tab) tab.click();
  }
  for (let node = target; node; node = node.parentElement) {
    if (node.tagName === 'DETAILS') node.open = true;
  }
  target.scrollIntoView();
}
document.addEventListener('click', event => {
  const link = event.target.closest('a[href^="#"]');
  if (link) openFragment(link.hash);
});
window.addEventListener('hashchange', () => openFragment(location.hash));
document.addEventListener('DOMContentLoaded', () => openFragment(location.hash), {once:true});
openFragment(location.hash);
let seasonRefreshPending = false;
setInterval(async () => {
  const selector = '#pgo-season[data-season-checked-at]';
  const current = document.querySelector(selector);
  if (seasonRefreshPending || !current || document.hidden) return;
  const panel = current.closest('[role="tabpanel"]');
  if (panel && panel.hidden) return;
  seasonRefreshPending = true;
  try {
    const response = await fetch('evidence/season-2026/current.json', {cache:'no-store'});
    if (!response.ok) return;
    const latest = await response.json();
    const advertised = Date.parse(latest.checked_at);
    const displayed = Date.parse(current.dataset.seasonCheckedAt);
    if (!Number.isFinite(advertised) || !Number.isFinite(displayed) || advertised <= displayed) return;
    const page = await fetch(location.href, {cache:'no-store'});
    if (!page.ok || new URL(page.url).origin !== location.origin) return;
    const parsed = new DOMParser().parseFromString(await page.text(), 'text/html');
    const sections = parsed.querySelectorAll('#pgo-season');
    if (sections.length !== 1) return;
    const next = sections[0];
    const checked = Date.parse(next.dataset.seasonCheckedAt);
    if (!Number.isFinite(checked) || checked < advertised || checked <= Date.parse(current.dataset.seasonCheckedAt)) return;
    // This fragment is generated same-origin HTML, never a script delivery path.
    if (next.querySelector('script,style,iframe,object,embed,frame,frameset,base,link,meta,template')) return;
    for (const node of [next, ...next.querySelectorAll('*')]) {
      for (const attribute of Array.from(node.attributes || [])) {
        const name = attribute.name.toLowerCase();
        const value = attribute.value.replace(/[\\s\\u0000-\\u001f]/g, '').toLowerCase();
        if (name.startsWith('on') || name === 'srcdoc' || value.startsWith('javascript:') || value.startsWith('vbscript:')) return;
      }
    }
    if (document.hidden || (panel && panel.hidden) || document.querySelector(selector) !== current) return;
    const oldKeys = new Map(), newKeys = new Map();
    for (const [section, keys] of [[current, oldKeys], [next, newKeys]]) {
      for (const node of section.querySelectorAll('[data-view-key]')) {
        const key = node.dataset.viewKey;
        if (!key || keys.has(key)) return;
        keys.set(key, node);
      }
    }
    // Capture immediately before replacement so interactions during fetch win.
    const active = document.activeElement;
    const owner = current.contains(active) ? active.closest('[data-view-key]') : null;
    const focusPath = [];
    if (owner) {
      for (let node = active; node !== owner; node = node.parentElement) {
        focusPath.unshift(Array.from(node.parentElement.children).indexOf(node));
      }
    }
    const scrolls = [];
    for (const [key, old] of oldKeys) {
      const node = newKeys.get(key);
      if (!node || node.tagName !== old.tagName || node.type !== old.type) continue;
      if (old.tagName === 'DETAILS') node.open = old.open;
      if (old.tagName === 'INPUT' && old.type === 'checkbox') node.checked = old.checked;
      scrolls.push([node, old.scrollLeft, old.scrollTop]);
    }
    const newOwner = owner ? newKeys.get(owner.dataset.viewKey) : null;
    let focus = newOwner && newOwner.tagName === owner.tagName && newOwner.type === owner.type ? newOwner : null;
    for (const index of focusPath) focus = focus && focus.children[index];
    if (focus && (focus.tagName !== active.tagName || focus.type !== active.type || focus.getAttribute('href') !== active.getAttribute('href'))) focus = null;
    if (!focus && newOwner && newOwner.tagName === 'DETAILS') focus = newOwner.querySelector('summary');
    const x = window.scrollX, y = window.scrollY;
    current.replaceWith(next);
    // Detached elements have no layout and cannot retain nonzero scroll offsets.
    for (const [node, left, top] of scrolls) { node.scrollLeft = left; node.scrollTop = top; }
    if (focus) focus.focus({preventScroll:true});
    window.scrollTo(x, y);
    updateWeeklyLocks();
  } catch (_) { /* Keep the last verified page when a network check fails. */ }
  finally { seasonRefreshPending = false; }
}, 60000);
</script>"""

HERE = Path(__file__).resolve().parent
ARCHIVE_DIR = HERE / "docs" / "evidence" / "forecast-lab-2026"
LOCK_PATH = ARCHIVE_DIR / "prospective_lock.json"
PREDICTIONS_PATH = ARCHIVE_DIR / "prospective_predictions.csv"
ATTESTATION_PATH = HERE / "research" / "pgo_stability_blend" / "prospective_attestation.json"
CAPTURE_ROOT = ARCHIVE_DIR / "results"
SNAPSHOT_DIR = ARCHIVE_DIR / "september-07"
CORRECTED_DIR = ARCHIVE_DIR / "september-08-corrected"
WEEKLY_DIR = ARCHIVE_DIR / "weekly"
OUTPUT_PATH = HERE / "docs" / "forecast-lab.html"
SENSITIVITY_DIR = HERE / "research" / "pgo_opponent_adjustment" / "run-20260907"
SENSITIVITY_MANIFEST_SHA256 = "0e2fd095579fdd33a6ab1c728eeeb07c373779cdb32da6c8d14ce48b08de5998"
SENSITIVITY_ARMS = tuple(f"{arm}__offseason_{carry}"
    for arm in ("raw", "team_epa", "team_qb_epa") for carry in ("unchanged", "0.5"))
STRENGTH_STUDY_DIR = HERE / "research" / "pgo_current_strength" / "run-20260908"
STRENGTH_STUDY_MANIFEST_SHA256 = "6682197b16fcc0974fef19e6c704ef238d4d2a30ba0db066e3e86a6bad35ee4a"
STRENGTH_STUDY_ARMS = ("raw", "starter", "starter_recency", "starter_recency_roster")
ATTESTATION_COMMIT = "8aae9438d251c645509d3df15a31bb86d50059b9"
ATTESTED_AT = "2026-08-26T16:07:24-04:00"
EXPECTED_ATTESTATION_SHA256 = "b89fe9c50f6c9d351aecc1820c573625ef11dd17bca1650ce3327abc8e3fadcd"
EXPECTED_SNAPSHOT_MANIFEST_SHA256 = "43bdeee73a2d3301eedbcecc7d291dc9ebe68cf196860e7217326570e4fe2f42"
RESULT_COLUMNS = (
    "game_id", "season", "week", "kickoff", "game_type", "home_team",
    "away_team", "home_score", "away_score", "finalized_at",
)
_RESULT_REQUIRED = {
    "game_id", "kickoff", "game_type", "home_team", "away_team",
    "home_score", "away_score", "finalized_at",
}
_CAPTURE_KEYS = {
    "schema_version", "kind", "captured_at", "source_url", "results_file",
    "results_file_sha256", "rows",
}
_CAPTURE_NAME = re.compile(r"^\d{8}T\d{6}Z$")


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _utc(value):
    return pgo_prospective._parse_datetime(value).astimezone(UTC)


def _capture_name(value):
    return _utc(value).strftime("%Y%m%dT%H%M%SZ")


def _current_utc():
    return datetime.now(UTC)


def _https_url(value):
    parsed = urlparse(str(value).strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Result provenance requires an HTTPS source URL")
    return parsed.geturl()


def load_archive(lock_path, csv_path, attestation_path):
    """Verify the exact derived lock and its review CSV against the attestation."""
    try:
        lock_bytes = Path(lock_path).read_bytes()
        prediction_bytes = Path(csv_path).read_bytes()
        attestation_bytes = Path(attestation_path).read_bytes()
        if _sha256(attestation_bytes) != EXPECTED_ATTESTATION_SHA256:
            raise ValueError("published attestation hash mismatch")
        attestation = json.loads(attestation_bytes)
        lock = json.loads(lock_bytes)
        pgo_prospective._verify_lock(lock)
        pgo_prospective._verify_grade_attestation(lock, lock_bytes, attestation)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"Forecast archive verification failed: {error}") from error
    expected = attestation["derived"]["predictions_file_sha256"]
    if _sha256(prediction_bytes) != expected:
        raise ValueError("Forecast prediction CSV hash mismatch")
    if prediction_bytes != pgo_prospective._prediction_csv(lock).encode("utf-8"):
        raise ValueError("Forecast prediction CSV does not match the lock")
    if len(lock["games"]) != 272:
        raise ValueError("Forecast archive must contain exactly 272 games")
    return lock


def _load_snapshot(directory):
    directory = Path(directory)
    is_default = directory.absolute() == SNAPSHOT_DIR.absolute()
    if not directory.exists() and not directory.is_symlink():
        if is_default and EXPECTED_SNAPSHOT_MANIFEST_SHA256:
            raise ValueError("The pinned default snapshot is missing")
        return None
    if is_default and EXPECTED_SNAPSHOT_MANIFEST_SHA256:
        try:
            manifest = (directory / "manifest.json").read_bytes()
        except OSError as error:
            raise ValueError("The pinned default snapshot manifest is missing") from error
        if _sha256(manifest) != EXPECTED_SNAPSHOT_MANIFEST_SHA256:
            raise ValueError("The pinned default snapshot manifest hash changed")
    return pgo_forecast_snapshot.load_snapshot(directory)


def _parse_results(raw, label):
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        fieldnames = reader.fieldnames or ()
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError("duplicate result CSV columns")
        fields = set(fieldnames)
        if not _RESULT_REQUIRED <= fields or fields - set(RESULT_COLUMNS):
            raise ValueError("result CSV columns are invalid")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError("result CSV field count mismatch")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} is not UTF-8") from error
    except csv.Error as error:
        raise ValueError(f"{label} is not valid CSV") from error
    if not rows:
        raise ValueError(f"{label} has no result rows")
    return rows


def _accepted_results(raw, lock, captured_at, label):
    locked = {game["game_id"]: game for game in lock.get("games", ())}
    accepted = []
    seen = set()
    capture_time = _utc(captured_at)
    for row in _parse_results(raw, label):
        normalized = pgo_prospective._normalize_result(row)
        game_id = normalized["game_id"]
        if game_id in seen:
            raise ValueError(f"duplicate result in capture: {game_id}")
        seen.add(game_id)
        game = locked.get(game_id)
        if game is None:
            raise ValueError(f"unexpected result: {game_id}")
        for field, actual, expected in (
            ("home team", normalized["home_team"], game["home"]),
            ("away team", normalized["away_team"], game["away"]),
            ("kickoff", _utc(normalized["kickoff"]), _utc(game["kickoff"])),
            ("game type", normalized["game_type"], game["game_type"]),
        ):
            if actual != expected:
                raise ValueError(f"locked {field} mismatch: {game_id}")
        for field in ("season", "week"):
            if field in normalized and normalized[field] != game[field]:
                raise ValueError(f"locked {field} mismatch: {game_id}")
        if any(not isinstance(normalized[field], int) for field in ("home_score", "away_score")):
            raise ValueError(f"Result requires nonnegative integer scores: {game_id}")
        finalized = _utc(normalized["finalized_at"])
        if finalized <= _utc(game["kickoff"]):
            raise ValueError(f"Result finalized before kickoff: {game_id}")
        if finalized > capture_time:
            raise ValueError(f"Result finalized after capture: {game_id}")
        normalized.update({
            "season": game["season"],
            "week": game["week"],
            "actual_margin": normalized["home_score"] - normalized["away_score"],
        })
        accepted.append(normalized)
    return accepted


def load_results(capture_root, lock):
    """Load immutable incremental result transcriptions, rejecting corrections."""
    root = Path(capture_root)
    if not root.exists():
        return [], []
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Result capture root must be a real directory")
    accepted = {}
    provenance = []
    for directory in sorted(root.iterdir(), key=lambda path: path.name):
        if directory.is_symlink() or not directory.is_dir() or not _CAPTURE_NAME.fullmatch(directory.name):
            raise ValueError(f"Invalid result capture directory: {directory.name}")
        metadata_path = directory / "capture.json"
        results_path = directory / "results.csv"
        if metadata_path.is_symlink() or results_path.is_symlink():
            raise ValueError(f"Invalid result capture path: {directory.name}")
        if set(path.name for path in directory.iterdir()) != {"capture.json", "results.csv"}:
            raise ValueError(f"Invalid result capture contents: {directory.name}")
        try:
            metadata = json.loads(metadata_path.read_bytes())
            raw = results_path.read_bytes()
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid result capture: {directory.name}") from error
        if not isinstance(metadata, dict) or set(metadata) != _CAPTURE_KEYS:
            raise ValueError(f"Invalid result capture metadata: {directory.name}")
        if (
            metadata["schema_version"] != 1
            or metadata["kind"] != "pgo_forecast_lab_result_transcription"
            or metadata["results_file"] != "results.csv"
            or isinstance(metadata["rows"], bool)
            or not isinstance(metadata["rows"], int)
            or metadata["rows"] <= 0
        ):
            raise ValueError(f"Invalid result capture metadata: {directory.name}")
        if _capture_name(metadata["captured_at"]) != directory.name:
            raise ValueError(f"Result capture timestamp mismatch: {directory.name}")
        metadata["source_url"] = _https_url(metadata["source_url"])
        if _sha256(raw) != metadata["results_file_sha256"]:
            raise ValueError(f"Result capture hash mismatch: {directory.name}")
        rows = _accepted_results(raw, lock, metadata["captured_at"], directory.name)
        if len(rows) != metadata["rows"]:
            raise ValueError(f"Result capture row count mismatch: {directory.name}")
        for row in rows:
            if row["game_id"] in accepted:
                raise ValueError(f"duplicate result across captures: {row['game_id']}")
            accepted[row["game_id"]] = row
        provenance.append(metadata)
    if root.absolute() in {CAPTURE_ROOT.absolute(), (SNAPSHOT_DIR / 'results').absolute(), (WEEKLY_DIR / 'results').absolute()}:
        from pgo_season import load_current
        season = load_current()
        if season:
            known = {g['game_id'] for g in lock.get('games', ())}
            for result in season['results']:
                if result['game_id'] not in known:
                    continue
                selected = {k: result[k] for k in RESULT_COLUMNS}
                text = io.StringIO(newline='')
                writer = csv.DictWriter(text, fieldnames=RESULT_COLUMNS, lineterminator='\n')
                writer.writeheader(); writer.writerow(selected)
                checked = _accepted_results(text.getvalue().encode(), lock, season['checked_at'], 'automatic season results')[0]
                previous = accepted.get(checked['game_id'])
                if previous and any(previous[k] != checked[k] for k in ('home_score', 'away_score', 'actual_margin')):
                    raise ValueError('Automatic result conflicts with archived transcription')
                if not previous:
                    accepted[checked['game_id']] = checked
                    provenance.append({'captured_at': result['finalized_at'], 'rows': 1,
                                       'source_url': result['source']['url']})
    order = {game["game_id"]: index for index, game in enumerate(lock.get("games", ()))}
    return sorted(accepted.values(), key=lambda row: order[row["game_id"]]), provenance


def record_results(results_path, source_url, capture_root, lock):
    """Archive one reviewed, incremental UTF-8 result transcription once."""
    source_url = _https_url(source_url)
    capture_time = _current_utc().astimezone(UTC)
    name = _capture_name(capture_time)
    destination = Path(capture_root) / name
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Result capture already exists: {name}")
    try:
        raw = Path(results_path).read_bytes()
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Reviewed result CSV is not UTF-8") from error
    except OSError as error:
        raise ValueError(f"Cannot read reviewed result CSV: {error}") from error
    if text.encode("utf-8") != raw:
        raise ValueError("Reviewed result CSV does not round-trip as UTF-8")
    rows = _accepted_results(raw, lock, capture_time, str(results_path))
    existing, _ = load_results(capture_root, lock)
    duplicate = {row["game_id"] for row in rows} & {row["game_id"] for row in existing}
    if duplicate:
        raise ValueError(f"Result already captured: {sorted(duplicate)[0]}")
    captured_text = capture_time.isoformat().replace("+00:00", "Z")
    metadata = {
        "schema_version": 1,
        "kind": "pgo_forecast_lab_result_transcription",
        "captured_at": captured_text,
        "source_url": source_url,
        "results_file": "results.csv",
        "results_file_sha256": _sha256(raw),
        "rows": len(rows),
    }
    outputs = (
        (destination / "results.csv", text),
        (destination / "capture.json", pgo_prospective._canonical(metadata) + "\n"),
    )
    if not pgo_prospective._write_new_outputs(destination, outputs):
        raise ValueError("Result capture could not reserve new output paths")
    return destination


def _validate_output_path(output, protected_paths, protected_roots):
    output = Path(output).resolve()
    if output.suffix.lower() != ".html":
        raise ValueError("Forecast Lab output must be an HTML file")
    protected = {Path(path).resolve() for path in protected_paths if path is not None}
    if output in protected:
        raise ValueError("Forecast Lab output conflicts with a protected input")
    for root in protected_roots:
        root = Path(root).resolve()
        if output == root or root in output.parents:
            raise ValueError("Forecast Lab output cannot be inside immutable evidence")
    return output


def _summary(values, actuals, *, winner=False):
    errors = [actual - predicted for actual, predicted in zip(actuals, values)]
    result = {
        "count": len(errors),
        "mae": math.fsum(abs(error) for error in errors) / len(errors) if errors else None,
        "rmse": math.sqrt(math.fsum(error * error for error in errors) / len(errors)) if errors else None,
    }
    if winner:
        decisions = [
            (actual, predicted) for actual, predicted in zip(actuals, values)
            if actual != 0 and predicted != 0
        ]
        correct = sum((actual > 0) == (predicted > 0) for actual, predicted in decisions)
        result["winner"] = {
            "correct": correct,
            "denominator": len(decisions),
            "accuracy": correct / len(decisions) if decisions else None,
        }
    return result


def interim_metrics(lock, results):
    """Calculate descriptive subset metrics without invoking the canonical grader."""
    games = {game["game_id"]: game for game in lock.get("games", ())}
    actuals = [float(row["actual_margin"]) for row in results]
    predictions = {
        "blend": [float(games[row["game_id"]]["candidate_prediction"]) for row in results],
        "pgo_v0": [float(games[row["game_id"]]["pgo_v0_prediction"]) for row in results],
        "zero": [0.0 for _row in results],
        "venue": [
            2.5 if games[row["game_id"]]["location"] == "Home" else 0.0
            for row in results
        ],
    }
    return {
        name: _summary(values, actuals, winner=name in {"blend", "pgo_v0"})
        for name, values in predictions.items()
    }


def _target_summary(predicted, actual):
    errors = [observed - estimate for observed, estimate in zip(actual, predicted)]
    return {
        "count": len(errors),
        "mae": math.fsum(abs(error) for error in errors) / len(errors) if errors else None,
        "rmse": math.sqrt(math.fsum(error * error for error in errors) / len(errors)) if errors else None,
        "bias": math.fsum(errors) / len(errors) if errors else None,
    }


def snapshot_interim_metrics(snapshot, results):
    """Describe finalized results for the separately issued September snapshot."""
    games = {game["game_id"]: game for game in snapshot.get("games", ())}
    selected = []
    for result in results:
        game = games.get(result["game_id"])
        if game is None:
            raise ValueError(f'Unexpected September snapshot result: {result["game_id"]}')
        selected.append((game, result))
    predicted_margins = [float(game["margin"]) for game, _result in selected]
    actual_margins = [float(result["actual_margin"]) for _game, result in selected]
    predicted_totals = [float(game["total"]) for game, _result in selected]
    actual_totals = [
        float(result["home_score"] + result["away_score"])
        for _game, result in selected
    ]
    predicted_scores = [
        score for game, _result in selected
        for score in (float(game["home_points"]), float(game["away_points"]))
    ]
    actual_scores = [
        float(score) for _game, result in selected
        for score in (result["home_score"], result["away_score"])
    ]
    venue_margins = [
        2.5 if game["location"] == "Home" else 0.0
        for game, _result in selected
    ]
    league_totals = [float(game.get("league_mean_total", snapshot["league_mean_total"]))
                     for game, _result in selected]
    league_scores = [score for venue, total in zip(venue_margins, league_totals)
                     for score in ((total + venue) / 2, (total - venue) / 2)]
    unavailable = {"total": None, "score": None}
    metrics = {
        "count": len(selected),
        "margin": _target_summary(predicted_margins, actual_margins),
        "total": _target_summary(predicted_totals, actual_totals),
        "score": _target_summary(predicted_scores, actual_scores),
        "winner": _summary(predicted_margins, actual_margins, winner=True)["winner"],
        "ties": {
            "actual": actual_margins.count(0.0),
            "forecast": predicted_margins.count(0.0),
        },
        "baselines": {
            "pgo_v0": {
                "margin": _target_summary(
                    [float(game["pgo_v0_margin"]) for game, _result in selected],
                    actual_margins,
                ), **unavailable,
            },
            "legacy": {
                "margin": _target_summary(
                    [float(game["legacy_margin"]) for game, _result in selected],
                    actual_margins,
                ), **unavailable,
            },
            "zero": {
                "margin": _target_summary([0.0 for _item in selected], actual_margins),
                **unavailable,
            },
            "league_mean_venue": {
                "margin": _target_summary(venue_margins, actual_margins),
                "total": _target_summary(league_totals, actual_totals),
                "score": _target_summary(league_scores, actual_scores),
            },
        },
    }
    if selected and all("incumbent_margin" in game for game, _result in selected):
        metrics["baselines"]["incumbent"] = {
            "margin": _target_summary(
                [float(game["incumbent_margin"]) for game, _result in selected], actual_margins),
            **unavailable,
        }
    return metrics


def _shared_css():
    template = generate_site.TEMPLATE
    if template.count("<style>") != 1 or template.count("</style>") != 1:
        raise ValueError("Shared board style markers are missing or ambiguous")
    return template.split("<style>", 1)[1].split("</style>", 1)[0]


def _signed(value):
    return f"{float(value):+.1f}"


def _display_time(value, zone_label):
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    clock = moment.strftime("%I:%M %p").lstrip("0")
    return f"{moment.strftime('%B')} {moment.day}, {moment.year} at {clock} {zone_label}"


def _kickoff_time(value):
    source = str(value)
    display = _display_time(_utc(source), "UTC")
    return f'<time datetime="{html.escape(source, quote=True)}">{display}</time>'


def _snapshot_kickoff_time(value):
    source = str(value)
    moment = _utc(source).astimezone(ZoneInfo("America/New_York"))
    display = _display_time(moment, moment.tzname())
    return f'<time datetime="{html.escape(source, quote=True)}">{display}</time>'


def _projected_score(value):
    return str(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _spread(game):
    margin = float(game["margin"])
    if margin == 0:
        return 'No projected edge'
    favorite = html.escape(game['home'] if margin > 0 else game['away'])
    gap = 'less than 0.1 point' if abs(margin) < 0.1 else f'{abs(margin):.1f} points'
    return f'{favorite} by {gap}'


def _edition_name(edition):
    return {'pgo-corrected-week1-2026-09-08': 'PGO Corrected — Sep 8',
            'pgo-postseason-week1-2026-09-09': 'PGO postseason — Sep 9',
            'pgo-active-roster-2026-09-07': 'September 7 preseason'}.get(edition, edition)


def _snapshot_metric_cards(metrics, label="September snapshot", *, incumbent_label="September 7 incumbent margin"):
    if metrics["count"] == 0:
        return f'<p class="empty">No finalized {html.escape(label)} results recorded yet.</p>'
    cards = []
    technical_rows = []
    for name, label in (
        ("margin", "Winning margin"),
        ("total", "Combined points"),
        ("score", "Each team’s score"),
    ):
        item = metrics[name]
        cards.append(
            f'<article class="metric"><h3>{label}</h3>'
            f'<div>Average miss <strong>{item["mae"]:.3f} points</strong></div>'
            f'<small>{item["count"]} predictions scored</small></article>'
        )
        technical_rows.append(f'<tr><th scope="row">{label}</th><td>{item["count"]}</td>'
                              f'<td>{item["mae"]:.3f}</td><td>{item["rmse"]:.3f}</td>'
                              f'<td>{item["bias"]:+.3f}</td></tr>')
    winner = metrics["winner"]
    accuracy = "Unavailable" if winner["accuracy"] is None else f'{winner["accuracy"]:.1%}'
    cards.append(
        '<article class="metric"><h3>Winner accuracy</h3>'
        f'<div><strong>{accuracy}</strong></div>'
        f'<small>{winner["correct"]}/{winner["denominator"]}; '
        f'{metrics["ties"]["actual"]} actual ties and '
        f'{metrics["ties"]["forecast"]} predictions with no winner excluded</small></article>'
    )
    baselines = metrics["baselines"]
    baseline_rows = []
    for key, label in (
        ("pgo_v0", "PGO v0 margin"),
        ("legacy", "Original archive margin"),
        ("incumbent", incumbent_label),
        ("zero", "Zero margin"),
        ("league_mean_venue", "League mean + venue"),
    ):
        if key not in baselines:
            continue
        item = baselines[key]
        values = [
            "Unavailable" if item[target] is None else f'{item[target]["mae"]:.3f}'
            for target in ("margin", "total", "score")
        ]
        baseline_rows.append(
            f'<tr><th scope="row">{label}</th>'
            + "".join(f"<td>{value}</td>" for value in values) + "</tr>"
        )
    return (
        '<div class="metric-grid">' + "".join(cards) + "</div>"
        '<details class="technical-details"><summary>Technical scoring details and comparisons</summary>'
        '<p>MAE is the average size of the miss. RMSE gives larger misses more weight. Bias is the signed average error.</p>'
        '<div class="table-shell"><table><thead><tr><th>Target</th><th>Values</th>'
        '<th>MAE</th><th>RMSE</th><th>Bias</th></tr></thead>'
        f'<tbody>{"".join(technical_rows)}</tbody></table></div>'
        '<h3>Same-game diagnostic baselines</h3>'
        f'<p>Every row uses the same {metrics["count"]} finalized games. '
        'PGO v0 and the original archive have no frozen total or score forecasts.</p>'
        '<div class="table-shell"><table><thead><tr><th>Baseline</th>'
        '<th>Margin MAE</th><th>Total MAE</th><th>Team-score MAE</th></tr></thead>'
        f'<tbody>{"".join(baseline_rows)}</tbody></table></div></details>'
    )


def _forecast_reason(game, corrected=None):
    """Explain saved arithmetic; only a matching verified source may supply drivers."""
    home, away = (html.escape(game[key]) for key in ('home', 'away'))
    margin, total = float(game['margin']), float(game['total'])
    arithmetic = (
        '<p><strong>Saved score calculation:</strong> split the combined-points estimate '
        'in half, then give half the projected lead to the favored team and subtract it '
        'from the other team. Home = (combined points + home-team lead) / 2; '
        'away = (combined points - home-team lead) / 2.</p>'
        f'<p>Combined points {total:.2f}; home-team lead {margin:+.2f}; '
        f'{home} {float(game["home_points"]):.2f}, {away} {float(game["away_points"]):.2f}. '
        'Numbers here are rounded for reading; the saved calculation uses full precision.</p>'
    )
    drivers = ''
    source = next((row for row in (corrected or {}).get('games', [])
                   if row['game_id'] == game['game_id']), None)
    bindings = (('source_edition', 'edition'), ('source_generated_at', 'generated_at'),
                ('source_manifest_sha256', '_manifest_sha256'))
    fields = ('game_id', 'season', 'week', 'game_type', 'home', 'away', 'kickoff',
              'location', 'home_rest', 'away_rest', 'margin', 'total', 'home_points', 'away_points')
    matches = (source is not None and all(game.get(left) and game[left] == corrected.get(right)
               for left, right in bindings) and all(key in game and key in source
               and game[key] == source[key] for key in fields))
    if matches:
        teams = {row['team']: row for row in corrected['teams']}
        fit = corrected['fit']
        pp = fit['preprocessor']
        def coefficient(name):
            index = pp['feature_names'].index(name)
            return fit['coefficients'][index + 1] / pp['scales'][index]
        gap = teams[game['home']]['rating'] - teams[game['away']]['rating']
        venue = 0.0 if game['location'] == 'Neutral' else coefficient('home_field')
        rest_input = _rest_difference(game['home_rest'], game['away_rest'])
        rest = None if rest_input is None else rest_input * coefficient('rest_difference')
        rates = corrected['scoring_rates']
        values = [rates[game[side]][kind] for side in ('away', 'home') for kind in ('pf', 'pa')]
        expected_total = math.fsum(values) / 2
        reconciles = rest is not None and all(math.isclose(actual, expected, rel_tol=0, abs_tol=1e-9)
            for actual, expected in ((margin, gap + venue + rest), (total, expected_total),
                (game['home_points'], (total + margin) / 2),
                (game['away_points'], (total - margin) / 2)))
        if reconciles:
            venue_text = ('The neutral site adds no home advantage.' if game['location'] == 'Neutral'
                          else f'Playing at home adds {venue:.1f} points for {home}.')
            rest_text = ('Both teams have the same rest, so there is no rest adjustment.'
                         if game['home_rest'] == game['away_rest'] else
                         f'The saved schedule gives {home} {game["home_rest"]} days of rest and '
                         f'{away} {game["away_rest"]}; the rest adjustment is {rest:+.2f} '
                         f'points to the home-team lead (the difference is capped at seven days).')
            drivers = (
                '<div class="forecast-reason-block"><h3>How the edge is built</h3>'
                f'<p>Before the venue adjustment: {_spread({**game, "margin": gap})}. '
                f'{venue_text} {rest_text} That leaves {_spread(game)}.</p></div>'
                '<div class="forecast-reason-block"><h3>Team and quarterback inputs</h3>'
                '<p>The team ratings combine recent results, passing and rushing efficiency, '
                'sacks, turnovers, and quarterback history. These are model inputs, '
                'not a scouting explanation of how this particular game will unfold. '
                'Past team defense results are included, but current edge-rusher and linebacker depth '
                'and the quality of their backups are not rated separately.</p>'
                f'<p>Expected quarterbacks: {away}: {html.escape(teams[game["away"]]["qb_name"])}; '
                f'{home}: {html.escape(teams[game["home"]]["qb_name"])}. Their history is already '
                'in the ratings; it is not added again here. '
                f'<a href="#corrected-rating-{away}">{away} rating explanation</a> &middot; '
                f'<a href="#corrected-rating-{home}">{home} rating explanation</a>.</p></div>'
                '<div class="forecast-reason-block"><h3>Combined points</h3>'
                '<p>Combined points uses each team’s 2025 regular-season points scored and '
                f'allowed per game: {away} {values[0]:.2f} scored / {values[1]:.2f} allowed; '
                f'{home} {values[2]:.2f} scored / {values[3]:.2f} allowed. '
                f'Add those four averages and divide by two: {total:.2f}. '
                'This is a simple scoring-history estimate.</p></div>'
                '<div class="forecast-reason-block"><h3>Injury assumptions</h3>'
                '<p>Injuries beyond the quarterback are not included in this saved forecast. '
                '<a href="#nonqb-availability">Separate injury scenarios and missing information</a>.</p></div>'
            )
    edition = html.escape(str(game.get('source_edition', 'See this archive’s saved method')))
    return ('<details class="forecast-reason"><summary>Why this forecast</summary>'
            f'<div class="forecast-reason-body">{drivers}</div>'
            '<details class="forecast-reason-block forecast-reason-calculation">'
            '<summary>Full calculation and saved version</summary>'
            f'{arithmetic}'
            f'<p>Saved edition: {edition}. Experimental / HOLD; this explains the calculation, '
            'not certainty about the result.</p></details></details>')


def _forecast_weeks(games, results, *, weekly=False, corrected=None, reasons=None, series=None, incumbent_label="September 7"):
    result_by_id = {row["game_id"]: row for row in results}
    weeks = []
    for week in sorted({game["week"] for game in games}):
        rows = []
        for game in (item for item in games if item["week"] == week):
            result = result_by_id.get(game["game_id"])
            actual = "&mdash;"
            if result:
                actual = (
                    f'{html.escape(game["away"])} {result["away_score"]}, '
                    f'{html.escape(game["home"])} {result["home_score"]}'
                )
            averages = (
                f'{html.escape(game["away"])} {_projected_score(game["away_points"])}, '
                f'{html.escape(game["home"])} {_projected_score(game["home_points"])}'
            )
            rounded = [Decimal(str(game[key])).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                       for key in ('away_points', 'home_points')]
            summary = (f'About {rounded[0]} points each' if rounded[0] == rounded[1] else
                       f'{html.escape(game["away"])} {rounded[0]}, {html.escape(game["home"])} {rounded[1]}')
            score = f'{summary}<details><summary>Model averages</summary><p>{averages}</p></details>'
            timing = ""
            if weekly:
                cutoff = html.escape(game["lock_at"], quote=True)
                status = "Locked" if _current_utc() >= _utc(game["lock_at"]) else "Draft"
                timing = (
                    f'<td><span class="weekly-status" data-weekly-cutoff="{cutoff}">{status}</span>'
                    f'<br>{_snapshot_kickoff_time(game["lock_at"])}</td>'
                )
            kind = series or ("weekly" if weekly else "snapshot")
            comparison = ""
            if weekly and "incumbent_margin" in game:
                controls = ((incumbent_label, "incumbent_margin"), ("PGO v0", "pgo_v0_margin"))
                comparison = '<details><summary>Compare forecasts</summary>' + "".join(
                    f'<p>{label}: {_spread({**game, "margin": game[key]})}</p>'
                    for label, key in controls) + '</details>'
            edition = (f'<br><small>{html.escape(_edition_name(game["source_edition"]))}</small>'
                       if weekly and game.get('source_edition') else '')
            rows.append(
                f'<tr data-{kind}-game-id="{html.escape(game["game_id"], quote=True)}">'
                f'<th scope="row">{html.escape(game["away"])} @ {html.escape(game["home"])}{edition}{comparison}</th>'
                f'<td>{_spread(game)}</td><td>{score}</td><td>{float(game["total"]):.1f}</td>'
                f'{timing}'
                f'<td>{_snapshot_kickoff_time(game["kickoff"])}</td>'
                f'<td>{actual}</td></tr>'
                f'<tr class="forecast-reason-row"><td colspan="{7 if weekly else 6}">'
                f'{reasons[game["game_id"]] if reasons is not None else _forecast_reason(game, corrected if weekly else None)}</td></tr>'
            )
        weeks.append(
            f'<details class="forecast-week {kind}-week"{" open" if week == min(game["week"] for game in games) else ""}>'
            f'<summary>Week {week} <span>{len(rows)} games</span></summary>'
            '<div class="table-shell"><table><thead><tr><th>Matchup</th><th>Who PGO favors</th>'
            '<th>Estimated score</th><th>Combined points</th>'
            f'{"<th>Prediction deadline (Eastern)</th>" if weekly else ""}'
            f'<th>Scheduled kickoff</th><th>Final score</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></details>'
        )
    return "".join(weeks)


def _rating_labels():
    return {
        "pgo_v0": "PGO v0 results-history input",
        "passing_epa_per_play_for": "Team passing efficiency (EPA per dropback)",
        "passing_epa_per_play_against": "Pass defense (opponent EPA prevented)",
        "rushing_epa_per_play_for": "Team rushing efficiency (EPA per carry)",
        "rushing_epa_per_play_against": "Run defense (opponent EPA prevented)",
        "explosive_play_rate_for": "Offensive explosive-play rate",
        "explosive_play_prevention_rate": "Explosive-play prevention",
        "sack_avoidance_rate": "Team sack avoidance",
        "sack_creation_rate": "Defensive sack creation",
        "giveaway_avoidance_rate": "Team giveaway avoidance",
        "takeaway_rate": "Defensive takeaway rate",
        "qb_epa_per_dropback": "QB passing efficiency (historical EPA)",
        "qb_cpoe": "QB completion rate above expectation",
        "qb_sack_avoidance": "QB historical sack avoidance",
        "qb_ball_security": "QB historical ball security",
        "qb_rushing_epa_per_carry": "QB historical rushing efficiency",
        "qb_log_dropbacks": "QB historical passing sample size",
        "qb_experience_prior": "QB experience prior",
        "qb_draft_prior": "QB draft-position prior",
        "returning_offense_snap_share": "Returning offensive snap share",
        "returning_defense_snap_share": "Returning defensive snap share",
        "incoming_prior_snap_share": "Incoming players' prior snap share",
        "rookie_draft_capital": "Rookie draft capital",
        "head_coach_continuity": "Head-coach continuity",
        "head_coach_tenure": "Head-coach tenure",
        "offense_availability": "Offensive availability adjustment",
        "defense_availability": "Defensive availability adjustment",
        "qb_current_minus_full": "QB lineup adjustment",
        "home_field": "Home-field adjustment",
        "rest_difference": "Rest adjustment",
    }
def _rating_explanations(snapshot):
    """Explain saved centered contributions without recomputing ratings."""
    labels = _rating_labels()
    teams = sorted(snapshot["teams"], key=lambda team: team["rank"])
    preprocessor = snapshot["fit"]["preprocessor"]
    names = [*preprocessor["feature_names"],
             *(name + "_missing" for name in preprocessor["missing_features"])]
    groups = (
        ("Results history", ("pgo_v0",)),
        ("Team passing efficiency", ("passing_epa_per_play_for",)),
        ("Other team efficiency", tuple(name for name in PERFORMANCE_FEATURES
                                        if name != "passing_epa_per_play_for")),
        ("QB history", QB_FEATURES),
        ("Roster composition", ("returning_offense_snap_share", "returning_defense_snap_share",
                                "incoming_prior_snap_share", "rookie_draft_capital")),
        ("Coaching", ("head_coach_continuity", "head_coach_tenure")),
    )
    grouped_names = {name for _, members in groups for name in members}
    groups += (("Other adjustments", tuple(name for name in names if name not in grouped_names)),)

    def contribution_row(label, value):
        number = f"{value:+.3f}".replace("-0.000", "+0.000")
        return f'<tr><th scope="row">{html.escape(label)}</th><td>{number}</td></tr>'

    cards = []
    for index, team in enumerate(teams):
        contributions = team["contributions"]
        if (not contributions or set(contributions) != set(names)
                or not all(math.isfinite(v) for v in contributions.values())
                or not math.isclose(math.fsum(contributions.values()), team["rating"],
                                    abs_tol=1e-8, rel_tol=0)):
            raise ValueError("Saved contributions must reconcile to the team rating")
        group_values = [(label, math.fsum(contributions.get(name, 0.0) for name in members))
                        for label, members in groups]
        rows = [contribution_row(label, value) for label, value in group_values]
        rows.append(contribution_row("Total model rating", team["rating"]))
        upward = sorted((item for item in group_values if item[1] > 1e-12), key=lambda item: -item[1])[:2]
        downward = min(group_values, key=lambda item: item[1])
        takeaway = ('Largest upward groups: ' + ', '.join(f'{name} ({value:+.3f})' for name, value in upward)
                    + '.') if upward else 'No input group contributes positively relative to the league average.'
        if downward[1] < -1e-12:
            takeaway += f' Largest downward group: {downward[0]} ({downward[1]:+.3f}).'
        qb_note = ''
        if team['team'] in ('NE', 'JAX') and 'qb_epa_per_dropback' in contributions:
            qb_note = (f'<p>{html.escape(team["qb_name"])} is the saved QB1; his QB passing term contributes '
                       f'{contributions["qb_epa_per_dropback"]:+.3f} within the QB-history group.</p>')
            if team['team'] == 'NE':
                qb_note += ('<p><strong>Why first place is uncertain:</strong> recent results and passing drive NE high, '
                            'but these inputs overlap. Its narrow lead also includes a counterintuitive roster-continuity '
                            'benefit. The <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_input_audit/README.md">'
                            'new input audit</a> tests roster eligibility, preseason transition effects, and QB valuations. '
                            'NE ranks first through fourth across seven specified constructions and stays first after '
                            'removing the transition fields; none of the six new candidates clears the improvement screen. '
                            'This saved rank does not establish that New England is clearly the best team in football.</p>')
            if (team['team'] == 'JAX' and team.get('old_selector_qb_name') == 'Trevor Lawrence'
                    and team.get('qb_policy_effect') == 0):
                qb_note += ('<p>The active-only roster already selects Lawrence under either selector, so the isolated '
                            'starter-policy effect is zero. The July-to-September change also includes roster inputs '
                            'and league centering.</p>')
        terms = []
        for name in names:
            label = labels.get(name.removesuffix("_missing"), name.replace("_", " "))
            if name.endswith("_missing"):
                label = "Missing-data adjustment: " + label
            terms.append(contribution_row(label, contributions[name]))
        gaps = []
        for neighbor, direction in ((index - 1, "below"), (index + 1, "above")):
            if 0 <= neighbor < len(teams):
                other = teams[neighbor]
                gap = abs(team["rating"] - other["rating"])
                gaps.append(f'{gap:.3f} {direction} #{other["rank"]} {html.escape(other["team"])}')
        cards.append(
            f'<details class="lab-detail rating-explanation" id="rating-{html.escape(team["team"], quote=True)}">'
            f'<summary>#{team["rank"]} {html.escape(team["team"])} &middot; {team["rating"]:+.3f}</summary>'
            f'<p class="rating-takeaway"><strong>Issued September 7 snapshot.</strong> {html.escape(takeaway)}</p>{qb_note}'
            f'<p>{"; ".join(gaps)}.'
            + ('' if qb_note else f' Expected QB1: {html.escape(team["qb_name"])}.') + '</p>'
            '<p>These are model contributions, not independent team grades. '
            '<a href="#rating-glossary">How to read them</a>.</p>'
            '<table class="rating-summary"><thead><tr><th>Input group</th><th>Contribution</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            f'<details class="lab-detail"><summary>All {len(names)} fitted terms</summary>'
            '<p>The same input order for every team, including zero contributions. Group totals can hide offsetting positive and negative terms.</p>'
            '<table class="rating-terms"><thead><tr><th>Fitted input</th><th>Contribution</th></tr></thead>'
            f'<tbody>{"".join(terms)}</tbody></table></details></details>'
        )
    return '''<details class="lab-detail" id="rating-explanations">
<summary>Why teams rank here &middot; All 32 September ratings</summary>
<p>Open a team to see what raises and lowers its saved September 7 output. Higher totals rank higher; the gaps show how close neighboring teams are.</p>
<p><strong>Archived July comparison</strong>: the board preserves its July ratings. <strong>Issued September 7 snapshot</strong>: the explanations below describe that saved preseason edition. <strong>Unadopted research</strong>: later candidate studies remain separate and do not replace either edition.</p>
<p><a href="#rating-NE">New England</a> &middot; <a href="#rating-JAX">Jacksonville</a> &middot; <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/docs/model-audit-2026-09-07.md">Read the outlier audit</a></p>
<details class="lab-detail" id="rating-glossary"><summary>How the contribution tables are calculated &middot; Glossary and limits</summary>
<p>Every summary shows the same seven input groups in the same order, so you can compare teams row by row. All are centered against the 32-team average and sum to the rating before rounding. These are fitted adjustments, <strong>not independent football grades</strong>, player values, or calibrated point-spread prices.</p>
<p>Team passing efficiency is shown separately from the other nine team-efficiency inputs. QB history combines eight QB inputs; roster composition combines returning offensive and defensive snap shares, incoming snap share, and rookie draft capital; coaching combines continuity and tenure. Other adjustments include availability, the QB lineup adjustment, venue, rest, and missing-data indicators. A zero here does not establish comprehensive injury coverage. Open the full breakdown to see every term.</p>
<p>EPA means expected points added. Team efficiency uses games through 2025 with a four-game half-life; QB efficiency uses shrunk player history. The PGO v0 input carries the earlier results rating forward without a new offseason shrink, unlike the separate v0 game-forecast baseline.</p>
<p><strong>Audit finding:</strong> lower returning offensive snap share raises this saved model's output, and head-coach continuity lowers it. Later research improved when roster-continuity inputs were removed. The <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_input_audit/README.md">new input audit</a> also identified different historical/current roster eligibility and preseason transition effects. These findings weaken a football interpretation of those contributions. Returning snap share tracks historical snap weight and a player's last recorded team, not the percentage of last season's team snaps retained. Issued values remain archived; research corrections are separate.</p>
</details>
''' + "".join(cards) + '''<p>Full precision and all inputs: <a href="evidence/forecast-lab-2026/september-07/snapshot.json">saved snapshot JSON</a>. Ratings remain EXPERIMENTAL / HOLD.</p></details>'''


def _corrected_section(snapshot, *, latest_inactive_notes=False):
    if snapshot is None:
        return ''
    postseason = snapshot.get('edition') == 'pgo-postseason-week1-2026-09-09'
    prefix = 'postseason' if postseason else 'corrected'
    container = 'div' if postseason else 'section'
    edition_date = 'September 9, 2026' if postseason else 'September 8, 2026'
    heading = 'Why teams rank here — September 9, 2026' if postseason else 'PGO Corrected — September 8, 2026'
    introduction = (
        'This edition includes regular season and playoffs in its team and quarterback history. '
        'Historical testing did not establish an accuracy improvement.' if postseason else
        '“Corrected” means we repaired problems in the calculation. It does not mean this version has proved more accurate.')
    history_label = '2025 regular season and playoffs, and earlier seasons' if postseason else '2025 regular season and earlier'
    contract = 'pgo_postseason_candidate' if postseason else 'pgo_week1_corrected'
    audit_doc = 'model-update-2026-09-09.md' if postseason else 'model-depth-audit-2026-09-09.md'
    default_download = f'evidence/forecast-lab-2026/september-{"09-postseason" if postseason else "08-corrected"}/snapshot.json'
    labels = _rating_labels()
    plain_labels = {
        'pgo_v0': 'recent game results',
        'passing_epa_per_play_for': 'the team’s passing numbers',
        'passing_epa_per_play_against': 'opponents’ passing numbers',
        'rushing_epa_per_play_for': 'the team’s running numbers',
        'rushing_epa_per_play_against': 'opponents’ running numbers',
        'explosive_play_rate_for': 'big plays on offense',
        'explosive_play_prevention_rate': 'limiting opponents’ big plays',
        'sack_avoidance_rate': 'the team’s history of taking sacks',
        'sack_creation_rate': 'sacks made by the defense',
        'giveaway_avoidance_rate': 'the team’s history of losing the ball',
        'takeaway_rate': 'the defense’s history of winning the ball back',
        'qb_epa_per_dropback': 'the quarterback’s passing numbers',
        'qb_cpoe': 'the quarterback’s completion numbers',
        'qb_sack_avoidance': 'the quarterback’s history of taking sacks',
        'qb_ball_security': 'the quarterback’s history of losing the ball',
        'qb_rushing_epa_per_carry': 'the quarterback’s running numbers',
        'qb_log_dropbacks': 'how much quarterback passing history is available',
        'qb_experience_prior': 'quarterback experience',
        'qb_draft_prior': 'where the quarterback was drafted',
    }
    cards = []
    ne_explanation = ''
    for team in sorted(snapshot['teams'], key=lambda row: row['rank']):
        terms = team['contributions']
        if not terms or not all(math.isfinite(value) for value in terms.values()) or not math.isclose(
                math.fsum(terms.values()), team['rating'], abs_tol=1e-8, rel_tol=0):
            raise ValueError('Corrected contributions must reconcile to the team rating')
        coverage = team['coverage']
        notes = coverage.get('notes', [])
        if isinstance(notes, str):
            notes = [notes]
        absences = coverage.get('known_unavailable', [])
        note_list = ''.join(f'<li>{html.escape(str(note))}</li>' for note in notes)
        def observation(item):
            if not isinstance(item, dict):
                return html.escape(str(item))
            name = item.get('player_name') or item.get('name') or item.get('full_name') or 'Player'
            status = item.get('game_status') or item.get('status') or item.get('practice_status') or 'Status unavailable'
            if not item.get('game_status') and not item.get('status') and item.get('practice_status'):
                status = 'Practice: ' + status
            position = item.get('report_position') or item.get('position') or item.get('roster_position')
            return html.escape(f'{name}' + (f' ({position})' if position else '') + f': {status}')
        absence_list = ''.join(f'<li>{observation(item)} — not included in this rating</li>' for item in absences)
        absent_ids = {item.get('gsis_id') for item in absences if isinstance(item, dict) and item.get('gsis_id')}
        observations = ''.join(f'<li>{observation(item)}</li>' for item in coverage.get('observations', [])
                               if not isinstance(item, dict) or item.get('gsis_id') not in absent_ids)
        report_status = ('We have not saved an official injury report. That does not mean everyone is healthy'
                         if coverage['source_kind'] == 'no_formal_report'
                         else 'An official report is available. Injuries beyond the quarterback are not included in the rating')
        if coverage.get('status') == 'BLOCKED_EXPECTED_QB_UNAVAILABLE':
            report_status = 'The listed quarterback is unavailable. This rating assumes he plays; this update contains no game forecast for this team'
        source_link = (f'<a href="{html.escape(_https_url(coverage["source_url"]), quote=True)}">Official report source</a>.'
                       if coverage.get('source_url') else '')
        rows = []
        for name, value in sorted(terms.items(), key=lambda item: -abs(item[1])):
            missing = name.endswith('_missing')
            base_name = name.removesuffix('_missing') if missing else name
            label = labels.get(base_name, base_name.replace('_', ' ')) + (' (missing flag)' if missing else '')
            raw = team['features'].get(base_name)
            shown = str(int(raw is None)) if missing else ('Unavailable' if raw is None else f'{raw:.4g}')
            rows.append(f'<tr><th scope="row">{html.escape(label)}</th><td>{shown}</td><td>{value:+.3f}</td></tr>')
        upward = sorted(((name, value) for name, value in terms.items() if value > 1e-8),
                        key=lambda item: -item[1])[:3]
        drivers = ', '.join(plain_labels.get(name, 'adjustments for missing information'
                            if name.endswith('_missing') else 'other adjustments')
                            for name, _value in upward) or 'no individual input above the league average'
        downward_note = ''
        if postseason:
            downward = sorted(((name, value) for name, value in terms.items() if value < -1e-8),
                              key=lambda item: item[1])[:3]
            drags = ', '.join(plain_labels.get(name, 'adjustments for missing information'
                             if name.endswith('_missing') else 'other adjustments') for name, _value in downward)
            downward_note = ('<p><strong>What holds this rating back:</strong> the largest downward contributions come from '
                             + html.escape(drags) + '.</p>') if drags else ''
        if team['team'] == 'NE':
            ne_explanation = (f'<p><strong>Why does New England rank #{team["rank"]}?</strong> '
                              f'The biggest boosts in this calculation come from {html.escape(drivers)}. '
                              '<strong>The model does not separately grade current edge-rusher and linebacker depth '
                              'or the quality of their backups.</strong> This is not a complete assessment of the current roster. '
                              f'<a href="https://github.com/walshja9/Postgame_Outlet/blob/main/docs/{audit_doc}">'
                              'What the model includes and misses</a>. '
                              'Several performance inputs describe the same games, so they are not separate proof '
                              'of the team’s strength. We have not established that this is the right ranking.</p>')
        caution = ('The model does not separately grade current edge-rusher and linebacker depth or the quality of their backups. '
                   'This is not a complete assessment of the current roster. '
                   'Recent results and passing numbers partly describe the same games. This position in the ranking '
                   'is not proof that New England is the NFL’s best team.' if team['team'] == 'NE' else
                   'Several inputs describe the same games. This ranking is not proof of how the team will perform next.')
        if postseason and team['team'] == 'NE':
            caution = ('The model does not separately grade current edge-rusher and linebacker depth or the quality of their backups. '
                       'Past team results and quarterback history partly describe the same games. This is an incomplete assessment of the current roster.')
        report_heading = 'Report saved with this forecast' if postseason else 'Injury report'
        report_timing = html.escape(str(coverage.get('report_date') or 'Report date unavailable'))
        if postseason:
            report_timing = ('Captured ' + _snapshot_kickoff_time(coverage['captured_at'])
                             if coverage.get('captured_at') else 'Capture time unavailable')
            report_timing += '. These are the earlier saved inputs. '
            report_timing += ('<a href="#latest-inactive-notes">Later final-inactive notes for NE–SEA</a> '
                             'are separate context and do not change the saved rating' if latest_inactive_notes else
                             'Later final-inactive notes are unavailable in this view')
        edition_comparison = (f'<p>September 8 comparison: #{team["baseline_rank"]}, '
                              f'rating {team["baseline_rating"]:+.3f}. This edition adds playoff history; '
                              'the change compares model editions, not movement from a newly played game.</p>'
                              if postseason else '')
        cards.append(f'''<details class="lab-detail rating-explanation corrected-team" id="{prefix}-rating-{html.escape(team['team'], quote=True)}">
<summary>#{team['rank']} {html.escape(team['team'])} &middot; PGO rating {team['rating']:+.3f}</summary>
{edition_comparison}
<p><strong>Expected quarterback:</strong> {html.escape(team['qb_name'])}.</p>
<p><strong>What lifts this rating:</strong> the biggest boosts in the calculation come from {html.escape(drivers)}.</p>
{downward_note}
<p><strong>Keep in mind:</strong> {caution} A boost from an input reflects how the formula weighs it; it is not a separate football grade.</p>
<p><strong>{report_heading}:</strong> {report_status}.
{report_timing}. {source_link}</p>
<ul>{absence_list}{observations}</ul>
<details class="technical-details"><summary>Technical details and calculations</summary>
<ul>{note_list}</ul>
<p>These terms sum to the output relative to the league average. Related performance signals overlap; they are conditional model contributions, not independent player or team grades.</p>
<div class="table-shell"><table class="study-table"><thead><tr><th>Input</th><th>Raw input</th><th>Fitted contribution</th></tr></thead><tbody>{''.join(rows)}
<tr><th>Total model output</th><td>&mdash;</td><td>{team['rating']:+.3f}</td></tr></tbody></table></div></details></details>''')
    skipped = ''.join(f'<li>{html.escape(row["game_id"])}: {html.escape(row["reason"])}</li>'
                      for row in snapshot.get('skipped_games', []))
    skipped = f'<p>Games without a new forecast in this update:</p><ul>{skipped}</ul>' if skipped else ''
    return f'''<{container} id="{prefix}-ratings"><h2>{heading}</h2>
<p><strong>Experimental — accuracy is still being tested.</strong> {introduction}</p>
<p>Higher ratings mean the model expects a stronger team; zero is the average of these 32 teams. A +5 rating does not mean a team should be favored by five points.</p>
<p>Roster information saved through {_snapshot_kickoff_time(snapshot['inputs_as_of'])}. Game and player performance comes from the {history_label}.</p>
<p class="notice"><strong>Injuries beyond the quarterback are not included.</strong> These ratings assume the listed quarterback plays.
Being on the active roster does not mean a player is healthy. {'Later injury updates are dated separately; issued forecasts keep their saved inputs.' if postseason else 'Reports need another review before each game locks.'}</p>
{ne_explanation}
<p>Choose a team below for its main reasons and injury information. <a href="#{prefix}-rating-NE">New England</a> &middot; <a href="#{prefix}-rating-JAX">Jacksonville</a></p>
<details class="technical-details"><summary>How the model works — technical notes and sources</summary>
<p><strong>EXPERIMENTAL / HOLD.</strong> Model construction: {edition_date}.
Snapshot generated {_snapshot_kickoff_time(snapshot['generated_at'])}.
Outputs are model units, not established neutral-field point prices or rank-confidence intervals.</p>
<p>This version matches historical and current ACT eligibility, removes six roster/coaching transition inputs,
uses statistic-specific QB exposure and enforces symmetric neutral-field predictions. It keeps four-game team history and a one-year QB half-life.
Those construction repairs do not establish superior forecasting accuracy. The same historical seasons have already been examined.</p>
<p>The results-history input responds to winning or losing margins that beat the model’s own expectation, not fans’ or media expectations.</p>
<p><a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/{contract}/charter.md">Fixed construction and evaluation contract</a> &middot;
<a href="{html.escape(snapshot.get('_download_url', default_download), quote=True)}">All inputs and source evidence</a></p></details>
<details id="{'postseason-model-editions' if postseason else 'model-editions'}"><summary>Model versions and snapshot dates</summary>
<p><strong>July 21 — archived PGO v1 ratings:</strong> the original saved preseason board.
<strong>September 7 — refreshed v1 construction:</strong> active expected starters with the recovered original fit.
<strong>September 8 — PGO Corrected:</strong> the separately fitted regular-season-history construction.</p>
{'<p><strong>September 9 — primary experimental edition:</strong> adds playoff history. Earlier editions remain available under Compare previous models; this display choice is not proof of greater accuracy.</p>' if postseason else ''}
<p>The July/August frozen 272-game season forecast is a separate 75% v0 / 25% challenger blend.
It is preserved as its own forecast record, not identified as the July v1 ratings board.</p>
<p>The earlier research name <strong>PGO v2</strong> identifies a separate roster-age and draft-pedigree experiment that remained HOLD.
It is not the name of this {'postseason' if postseason else 'corrected'} edition. A model version describes the calculation; a snapshot date records a particular set of inputs and outputs.
Every saved edition remains available. A newer date does not establish greater predictive accuracy.</p></details>
{skipped}{''.join(cards)}</{container}>'''


def _load_corrected(directory, weekly, weekly_root):
    import pgo_forecast_corrected
    if directory is None:
        revisions = [row for row in weekly.get('revisions', [])
                     if row.get('source_edition') == pgo_forecast_corrected.EDITION]
        directory = ((Path(weekly_root) / revisions[-1]['source_directory']).resolve()
                     if revisions else CORRECTED_DIR)
    directory = Path(directory).resolve()
    snapshot = pgo_forecast_corrected.load_snapshot(directory)
    snapshot['_manifest_sha256'] = hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest()
    snapshot['_download_url'] = f'evidence/forecast-lab-2026/{directory.name}/snapshot.json'
    return snapshot, directory


def _weekly_section(weekly, snapshot, results, provenance, corrected=None):
    incumbent = {game["game_id"]: game for game in snapshot["games"]}
    games = [{**game, "incumbent_margin": game.get(
        "incumbent_margin", incumbent[game["game_id"]]["margin"])} for game in weekly["games"]]
    metrics = snapshot_interim_metrics({**snapshot, "games": games}, results)
    source_dates = sorted({game["source_generated_at"] for game in games})
    source_text = ", ".join(_snapshot_kickoff_time(value) for value in source_dates)
    sources = (
        f'<p>Forecast snapshot created: {source_text}. '
        '<strong>Injuries beyond the quarterback are not included.</strong> '
        'These forecasts assume the listed quarterback plays. Team injury information is below.</p>'
        if games else '<p>No weekly edition has been recorded yet.</p>'
    )
    revisions = "".join(
        f'<li>Saved {_snapshot_kickoff_time(item["registered_at"])}; '
        f'{html.escape(_edition_name(item.get("source_edition", item["source_directory"])))}; '
        f'<a href="evidence/forecast-lab-2026/weekly/{html.escape(item["revision"], quote=True)}">'
        f'forecast revision</a></li>' for item in weekly.get("revisions", [])
    )
    result_sources = "".join(
        f'<li>{html.escape(str(item["captured_at"]))}: '
        f'<a href="{html.escape(_https_url(item["source_url"]), quote=True)}">'
        f'reviewed result source</a> ({item["rows"]} rows; CSV SHA-256 '
        f'<code>{html.escape(str(item["results_file_sha256"]))}</code>)</li>'
        for item in provenance
    ) or "<li>No weekly results recorded.</li>"
    return f'''
<header class="lab-hero hero"><div class="status" data-model-status="HOLD">Experimental &mdash; still being tested</div>
<h1>PGO Forecast Lab</h1><h2>Weekly game forecasts</h2>
<p>See who the model favors, its estimated scores, and how the predictions compare with final results.</p>
<p>Each prediction becomes final <strong>60 minutes before kickoff</strong>. We keep the last saved prediction before that deadline and record its misses as well as its wins.</p>
<p>A draft can change before its own deadline. A locked prediction cannot. An early game does not lock every other game that week.</p>
<p><a href="index.html">Back to McCabe Ratings</a> &middot; <a href="#corrected-ratings">Why teams rank here</a> &middot; <a href="#preseason-baseline">Full-season archive</a> &middot; <a href="#forecast-process">How we track every forecast</a></p></header>
<section><h2>Weekly predictions</h2>{sources}
<p>Open &ldquo;Why this forecast&rdquo; for the saved calculation. The current model combines recent results, passing and rushing, sacks and turnovers, and quarterback history, then adjusts for venue and rest. Combined points uses 2025 scoring averages.</p>
<p>“SEA by 3.0 points” means the model favors Seattle by three. Combined points adds both teams’ estimates.</p>
<p>Scores are rounded to whole points. Open “Model averages” for decimal estimates. “About 25 points each” means both estimates round to 25; it does not predict a tied game. The favored team uses the unrounded numbers. Rounded scores may not add up to the combined-points estimate.</p>
<p><strong>How much should you trust the scores?</strong> In historical testing, the combined-score estimate missed by about 11 points per game on average. It did not clearly beat using a simple league average. Treat these scores as an experiment.</p>
{_forecast_weeks(games, results, weekly=True, corrected=corrected)}</section>
<section><h2>Weekly forecast record</h2><p>{len(results)} of {len(games)} saved weekly forecasts have final results. We will keep the misses as well as the hits. Early results alone cannot prove the model works.</p>{_snapshot_metric_cards(metrics, "weekly")}</section>
<details class="lab-detail" id="forecast-process"><summary>How we track every forecast — saved versions and technical details</summary>
<p>Research status: EXPERIMENTAL / HOLD. Score summaries use whole-number rounded averages; model averages and combined points use one decimal. The favored team uses the original unrounded margin, including edges below 0.1 point. Evaluation uses unrounded values.</p>
<p><a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_input_audit/README.md#game-totals-need-their-own-evidence">Historical totals test and limitations</a>.</p>
<ol><li><strong>Review sources</strong>: verify roster, expected starters, injury coverage, and source dates. Missing formal reports remain unknown; refreshes require review.</li>
<li><strong>Save a revision</strong>: record a dated forecast revision before the relevant game's deadline. Keep every earlier revision.</li>
<li><strong>Lock each matchup</strong>: at T-60, freeze that game's scores, spread, and total together from its last eligible saved revision.</li>
<li><strong>Grade every issued matchup</strong>: add verified final results, including losses and misses. Report the number graded and every outstanding game.</li>
<li><strong>Compare benchmarks</strong>: evaluate the same games against the stated baselines. Interim results do not satisfy a full-season acceptance gate.</li>
<li><strong>Test future versions</strong>: freeze a separate evaluation before future games. Research findings can propose a new version; they never rewrite issued predictions.</li></ol>
<h3>Saved revisions</h3><ul>{revisions or "<li>No revisions yet.</li>"}</ul>
<p>Revisions are saved separately and cannot be submitted at or after the cutoff. A saved timestamp records local registration; the repository history records publication. A schedule change requires review and cannot silently extend an existing deadline.</p>
<p>Fresh weekly inputs require a separately reviewed source snapshot. Source refresh is not automated. Future weeks without a weekly edition remain available in the preseason baseline below.</p>
<h3>Weekly results provenance</h3><ul>{result_sources}</ul></details>'''


def _snapshot_section(snapshot, results, provenance):
    generated = _utc(snapshot["generated_at"])
    games = list(snapshot["games"])
    if any(generated >= _utc(game["kickoff"]) for game in games):
        raise ValueError("September snapshot must be generated before every kickoff")
    metrics = snapshot_interim_metrics(snapshot, results)
    ratings = "".join(
        f'<tr class="snapshot-team" data-pgo-team="{html.escape(team["team"], quote=True)}">'
        f'<td class="pgo-rank pgo-essential">{team["rank"]}</td>'
        f'<th scope="row" class="pgo-team pgo-essential"><a href="#rating-{html.escape(team["team"], quote=True)}">'
        f'{pgo_current_board.team_identity(team["team"])}</a></th>'
        f'<td class="pgo-rating-value pgo-essential" data-value="{team["rating"]}">{_signed(team["rating"])}</td>'
        f'<td class="pgo-rating-scale pgo-detail">{pgo_current_board.rating_bar(team["rating"])}</td>'
        f'<td class="pgo-detail">{html.escape(team["qb_name"])}</td>'
        f'<td class="pgo-detail">{html.escape(team["old_selector_qb_name"])} ({_signed(team["old_selector_rating"])})</td></tr>'
        for team in sorted(snapshot["teams"], key=lambda item: item["rank"])
    )
    method = snapshot.get("method", {})
    method_items = "".join(
        f'<li><strong>{html.escape(label)}:</strong> {html.escape(str(method[key]))}</li>'
        for key, label in (
            ("roster_policy", "Roster policy"),
            ("injury_coverage", "Injury coverage"),
            ("history", "History"),
            ("totals", "Projected totals"),
            ("fit_recovery", "Fit recovery"),
            ("evaluation", "Evaluation boundary"),
            ("schedule", "Schedule"),
        ) if method.get(key)
    )
    source_items = "".join(
        f'<li>{html.escape(str(source["name"]))}: '
        f'<a href="{html.escape(_https_url(source["url"]), quote=True)}">source</a>; '
        f'captured {html.escape(str(source["captured_at"]))}; SHA-256 '
        f'<code>{html.escape(str(source["sha256"]))}</code></li>'
        for source in snapshot.get("sources", ())
    ) or "<li>See the verified snapshot manifest.</li>"
    result_sources = "".join(
        f'<li>{html.escape(str(item["captured_at"]))}: '
        f'<a href="{html.escape(_https_url(item["source_url"]), quote=True)}">'
        f'reviewed transcription source</a> ({item["rows"]} rows; CSV SHA-256 '
        f'<code>{html.escape(str(item["results_file_sha256"]))}</code>)</li>'
        for item in provenance
    ) or "<li>No September result transcriptions recorded.</li>"
    return f'''
<header class="lab-hero hero"><div class="status">{html.escape(str(method.get("status", "EXPERIMENTAL — HOLD")))}</div>
<h1>PGO Forecast Lab</h1><h2>September 7 preseason snapshot</h2>
<p><strong>{html.escape(str(method.get("name", "Active-roster preseason scenario")))}</strong>. Each game shows the team the model favors and its estimated winning margin.</p>
<p>ACT is an administrative roster status, not proof of health or game-day availability. Week 1 and the full schedule use the same September 7 state; later weeks are not weekly lineup updates.</p>
<p><strong>Season-method check:</strong> a separate historical replay found that freezing preseason model strength all year performed worse than both weekly updates and a simpler frozen rating. That replay also uses retrospective Week 1 identities, so it cannot certify what was knowable before the season. <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_input_audit/README.md#freezing-strength-for-an-entire-season-performs-worse">Read the season test and its limits</a>.</p>
<p><strong>{len(results)} of {len(games)} finalized results recorded.</strong> Interim tracking &mdash; not a validation result.</p>
<p><a href="index.html">Back to McCabe Ratings</a></p></header>
<section><h2>September snapshot record</h2>{_snapshot_metric_cards(metrics)}</section>
<section><h2>Week 1 and full-season forecasts</h2><p>Score summaries use whole-number rounded averages; model averages and combined points use one decimal. Evaluation uses the original unrounded projections.</p><p>Open “Model averages” for decimal estimates. “About 25 points each” means both estimates round to 25; it does not predict a tied game. The favored team uses the unrounded numbers. Rounded scores may not add up to the combined-points estimate.</p>{_forecast_weeks(games, results)}</section>
<details class="lab-detail" open><summary>32-team active-roster ratings and QB assumptions</summary><div class="pgo-snapshot-board"><label class="pgo-column-toggle" for="snapshot-pgo-columns"><input id="snapshot-pgo-columns" type="checkbox"> Show QB and prior-selector comparison</label><div class="table-shell"><table class="pgo-snapshot-table"><thead><tr><th class="pgo-essential">Rank</th><th class="pgo-essential">Team</th><th class="pgo-essential">PGO rating</th><th class="pgo-detail"><span class="pgo-scale-label"><span aria-hidden="true">-14</span><span>Rating scale</span><span aria-hidden="true">+14</span></span></th><th class="pgo-detail">Expected QB1</th><th class="pgo-detail">Old QB-selector comparison</th></tr></thead><tbody>{ratings}</tbody></table></div></div></details>
<details class="lab-detail"><summary>September method, sources, and downloads</summary><p>Generated {_display_time(generated, "UTC")}. This inference-policy change and the simple projected-score method remain experimental; through-2025 performance does not validate them.</p><ul>{method_items}</ul><p><a href="evidence/forecast-lab-2026/september-07/snapshot.json">Snapshot JSON</a> &middot; <a href="evidence/forecast-lab-2026/september-07/forecasts.csv">Forecast CSV</a> &middot; <a href="evidence/forecast-lab-2026/september-07/ratings.csv">Ratings CSV</a> &middot; <a href="evidence/forecast-lab-2026/september-07/manifest.json">Verification manifest</a></p><ul>{source_items}</ul><p>No calibrated probabilities, market claims, or retrospective promotion are attached to this snapshot.</p><h3>September results provenance</h3><ul>{result_sources}</ul></details>'''


def _metric_cards(metrics):
    if metrics["blend"]["count"] == 0:
        return '<p class="empty">No finalized results recorded yet.</p>'
    labels = {
        "blend": "Frozen 25% stability blend",
        "pgo_v0": "PGO v0 baseline",
        "zero": "Zero-margin diagnostic",
        "venue": "Venue-only diagnostic",
    }
    cards = []
    for name in ("blend", "pgo_v0", "zero", "venue"):
        metric = metrics[name]
        winner = ""
        if "winner" in metric:
            item = metric["winner"]
            value = "Unavailable" if item["accuracy"] is None else f'{item["accuracy"]:.1%}'
            winner = (
                f'<div>Winner accuracy <strong>{value}</strong> '
                f'<small>({item["correct"]}/{item["denominator"]}; ties and zero forecasts excluded)</small></div>'
            )
        cards.append(
            f'<article class="metric"><h3>{html.escape(labels[name])}</h3>'
            f'<div>Results <strong>{metric["count"]}</strong></div>'
            f'<div>MAE <strong>{metric["mae"]:.3f}</strong></div>'
            f'<div>RMSE <strong>{metric["rmse"]:.3f}</strong></div>{winner}</article>'
        )
    return '<div class="metric-grid">' + "".join(cards) + "</div>"


def load_model_sensitivity(directory, snapshot):
    """Read descriptive research only; never fit or alter issued predictions."""
    directory = Path(directory)
    manifest_raw = (directory / "manifest.json").read_bytes()
    if directory.resolve() == SENSITIVITY_DIR.resolve() and _sha256(manifest_raw) != SENSITIVITY_MANIFEST_SHA256:
        raise ValueError("Sensitivity manifest hash mismatch")
    manifest = json.loads(manifest_raw)
    if manifest.get("identity") != "pgo-opponent-epa-retrospective-20260907":
        raise ValueError("Unexpected sensitivity research identity")
    verified = {}
    for name in ("ratings.csv", "run-receipt.json", "metrics.json"):
        raw = (directory / name).read_bytes()
        entry = manifest.get("files", {}).get(name, {})
        if len(raw) != entry.get("bytes") or _sha256(raw) != entry.get("sha256"):
            raise ValueError(f"Sensitivity bytes/hash mismatch: {name}")
        verified[name] = raw.decode("utf-8")
    receipt = json.loads(verified["run-receipt.json"])
    metrics = json.loads(verified["metrics.json"])
    if (receipt.get("status") != "EXPLORATORY_RETROSPECTIVE_RESEARCH"
            or metrics.get("leakage_verdict") != "REVIEW REQUIRED"
            or any(metrics.get("screening", {}).get(arm, {}).get("merits_further_prospective_study") is not False
                   for arm in ("team_epa", "team_qb_epa"))):
        raise ValueError("Sensitivity research status changed; review presentation")
    completed = receipt.get("completed_at", "")
    _utc(completed)
    rows = list(csv.DictReader(io.StringIO(verified["ratings.csv"])))
    teams = pgo_prospective.pgo_model.CURRENT_TEAMS
    if len(rows) != 32 or {row.get("team") for row in rows} != set(teams):
        raise ValueError("Sensitivity requires exactly 32 unique teams")
    baseline = {row["team"]: row for row in snapshot["teams"]}
    if len(snapshot["teams"]) != 32 or set(baseline) != set(teams):
        raise ValueError("Sensitivity baseline requires exactly 32 unique teams")
    for row in rows:
        for arm in SENSITIVITY_ARMS:
            for kind in ("rank", "rating"):
                key = arm + "_" + kind
                row[key] = pgo_comparison._finite(row.get(key), f"Sensitivity {key}")
        old = baseline[row["team"]]
        if (row["raw__offseason_unchanged_rank"] != old["rank"]
                or not math.isclose(row["raw__offseason_unchanged_rating"], old["rating"], rel_tol=0, abs_tol=1e-10)):
            raise ValueError("Sensitivity raw arm differs from issued September baseline")
    for arm in SENSITIVITY_ARMS:
        if {row[arm + "_rank"] for row in rows} != set(range(1, 33)):
            raise ValueError("Sensitivity arm requires unique ranks 1 through 32")
    mccabe = {row["abbr"]: row for row in pgo_comparison.load_mccabe_rows(pgo_comparison.MCCABE_PATH)}
    compared = []
    for row in sorted(rows, key=lambda item: item["raw__offseason_unchanged_rank"]):
        team = row["team"]
        ranks = [int(row[arm + "_rank"]) for arm in SENSITIVITY_ARMS]
        ratings = [row[arm + "_rating"] for arm in SENSITIVITY_ARMS]
        rank = int(row["raw__offseason_unchanged_rank"])
        compared.append({"team": team, "pgo_rank": rank, "mccabe_rank": mccabe[team]["rank"],
            "rank_gap": rank - mccabe[team]["rank"], "rank_span": [min(ranks), max(ranks)],
            "rating_span": [min(ratings), max(ratings)]})
    return {"teams": compared, "completed_at": completed,
        "mccabe_as_of": pgo_comparison.mccabe_source_timestamp(pgo_comparison.MCCABE_PATH),
        "snapshot_generated_at": snapshot["generated_at"],
        "depth_as_of": snapshot.get("depth_as_of", "Unavailable"),
        "source_captures": sorted({source["captured_at"] for source in snapshot.get("sources", [])}),
        "manifest_sha256": _sha256(manifest_raw)}


def load_strength_study(directory):
    """Load the fixed retrospective study summary, independently of forecasts."""
    directory = Path(directory)
    raw = (directory / 'manifest.json').read_bytes()
    if directory.resolve() == STRENGTH_STUDY_DIR.resolve() and _sha256(raw) != STRENGTH_STUDY_MANIFEST_SHA256:
        raise ValueError('Current-strength manifest hash mismatch')
    manifest = json.loads(raw)
    if manifest.get('identity') != 'pgo-current-strength-research-20260908':
        raise ValueError('Unexpected current-strength study identity')
    loaded = {}
    for name in ('metrics.json', 'run-receipt.json'):
        raw = (directory / name).read_bytes()
        entry = manifest.get('files', {}).get(name, {})
        if len(raw) != entry.get('bytes') or _sha256(raw) != entry.get('sha256'):
            raise ValueError(f'Current-strength bytes/hash mismatch: {name}')
        loaded[name] = json.loads(raw)
    receipt, metrics = loaded['run-receipt.json'], loaded['metrics.json']
    if (receipt.get('status') != 'EXPLORATORY_RETROSPECTIVE_RESEARCH'
            or receipt.get('promotion_status') != 'HOLD'
            or receipt.get('leakage_verdict') != 'REVIEW REQUIRED'
            or receipt.get('raw_final_fit_reproduction', {}).get('passed') is not True):
        raise ValueError('Current-strength study status requires review')
    for arm in STRENGTH_STUDY_ARMS:
        row = metrics['metrics'][arm]['overall']
        for name in ('mae', 'rmse'):
            if pgo_comparison._finite(row[name], f'{arm} {name}') < 0:
                raise ValueError('Current-strength error metric must be nonnegative')
        if row['count'] != 2127 or not 0 <= row['winner']['accuracy'] <= 1:
            raise ValueError('Current-strength evaluation coverage differs')
    _utc(receipt['completed_at'])
    return {'metrics': metrics['metrics'], 'completed_at': receipt['completed_at']}


def _strength_study_summary(study):
    if study is None:
        return ''
    labels = ('Raw control', 'Recorded starter', 'Starter + QB recency', 'Starter + recency + skill efficiency')
    rows = []
    for arm, label in zip(STRENGTH_STUDY_ARMS, labels):
        metric = study['metrics'][arm]['overall']
        winner = metric['winner']
        rows.append(f'<tr><th scope="row">{label}</th><td>{metric["mae"]:.4f}</td>'
                    f'<td>{winner["accuracy"]:.2%} ({winner["correct"]}/{winner["denominator"]})</td></tr>')
    ablation_mae = study['metrics']['without_roster_continuity']['overall']['mae']
    return f'''<h3>Current-strength study — separate retrospective experiment</h3>
<p><strong>All four arms remain HOLD.</strong> On 2,127 matched 2018–2025 games, the three starter-based candidates meet the screen for further prospective study against raw. That is not model promotion. Winner accuracy excludes eight actual ties; these arms have no zero-margin abstentions.</p>
<p><strong>Later audit:</strong> these historical arms used a broader roster population than the active-only September forecast. Their fitted neutral-field margins also retain an offset for identical teams. The <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_input_audit/README.md">input and valuation audit</a> tests those issues separately; the earlier numerical screen does not establish current-model readiness.</p>
<div class="table-shell"><table class="study-table"><thead><tr><th>Study arm</th><th>Margin MAE</th><th>Winner accuracy</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>The starter change lowers MAE versus raw; adding recency and then skill efficiency does not lower MAE further. Historical selections use recorded actual starters, not verified pregame/T-60 expectations. Seasons were already inspected and historical publication vintage remains REVIEW REQUIRED. Offensive-line and defensive player quality remain unavailable; the added skill features are efficiency proxies.</p>
<p>Refitting without roster-continuity inputs reached margin MAE {ablation_mae:.4f}: an exploratory simplification to test prospectively, not an adopted model change.</p>
<p><a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_current_strength/availability-20260908/scenario-report.md">Separate availability scenario</a>, captured September 8 at 02:24 UTC: 11 formal player-report rows for New England and Seattle; the other 30 teams remain unknown. This later capture does not change the frozen September baseline.</p>
<p>This study is separate from the six-variant opponent-adjustment experiment above; those sensitivity spans do not include these four arms. Completed {html.escape(study['completed_at'])}. <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_current_strength/README.md">Study method and findings</a> &middot; <a href="https://github.com/walshja9/Postgame_Outlet/tree/main/research/pgo_current_strength/run-20260908">Verified results and receipts</a>.</p>'''


def _model_sensitivity(sensitivity, strength_study=None):
    if sensitivity is None:
        return ""
    rows = "".join(
        f'<tr class="sensitivity-team"><th scope="row">{html.escape(row["team"])}</th>'
        f'<td>{row["mccabe_rank"]}</td><td>{row["pgo_rank"]}</td><td>{row["rank_gap"]:+d}</td>'
        f'<td>{row["rank_span"][0]}–{row["rank_span"][1]}</td>'
        f'<td>{row["rating_span"][0]:+.3f} to {row["rating_span"][1]:+.3f}</td></tr>'
        for row in sensitivity["teams"])
    captures = ", ".join(sensitivity["source_captures"]) or "Unavailable"
    return f'''<details class="lab-detail" id="model-sensitivity"><summary>Rank gaps, source freshness, and model sensitivity</summary>
<p><strong>Latest review:</strong> <a href="https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_input_audit/README.md">Input definitions, roster eligibility, neutral-field consistency, and separate weekly/season tests</a>. The earlier experiments below remain available as dated evidence.</p>
<p>The completed input audit compares seven constructions on 2,127 matched games. NE ranks 1&ndash;4 and JAX 5&ndash;7 across those specific choices; these are sensitivity ranges, not confidence intervals. The symmetric arm fixes neutral-field reversal and has the lowest margin MAE (10.0982 versus 10.1198 for its reference), but none of the six new candidates passes the predeclared improvement screen. All remain HOLD.</p>
<p><strong>EXPERIMENTAL — HOLD. Calibrated uncertainty: unavailable.</strong> The ranges below show how six specified model variants change each team's output. This is model sensitivity, not a confidence or prediction interval; it does not measure the chance that a rating or game result falls inside the range.</p>
<p>McCabe's human ranks are compared with the September 7 preseason PGO baseline here. The main board leads with the September 9 postseason edition; September 8 and July remain available for comparison. Rank gap = PGO rank minus McCabe rank: positive means PGO ranks the team lower. No point-price gap is calculated.</p>
<p>Source freshness: McCabe source revision {html.escape(sensitivity['mccabe_as_of'])}; September baseline generated {html.escape(sensitivity['snapshot_generated_at'])}; depth snapshot {html.escape(sensitivity['depth_as_of'])}. Roster/source captures: {html.escape(captures)}. Performance history ends with the 2025 regular season; these are not current injury updates.</p>
<div class="table-shell"><table><thead><tr><th>Team</th><th>McCabe rank</th><th>September PGO rank</th><th>Rank gap</th><th>Sensitivity: rank span</th><th>Sensitivity: model-output span</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>The six variants cross raw, opponent-adjusted team EPA, and opponent-adjusted team plus QB EPA with either the unchanged earlier results-based PGO input or 50% offseason retention of that input. Ranges are descriptive, centered model-scale outputs. Both opponent-adjustment arms remain HOLD; this retrospective study does not replace issued forecasts or validate the September inference policy.</p>
<p>Historical publication vintage: REVIEW REQUIRED. Final/backfilled historical releases lack complete row-publication receipts; all evaluation seasons were previously inspected. Research completed {html.escape(sensitivity['completed_at'])}.</p>
<p><a href="https://github.com/walshja9/Postgame_Outlet/tree/main/research/pgo_opponent_adjustment/run-20260907">Research ratings, method, and receipts</a>. Verified research manifest SHA-256: <code>{html.escape(sensitivity['manifest_sha256'])}</code>.</p>{_strength_study_summary(strength_study)}</details>'''


def render_lab(lock, results, provenance, *, snapshot=None, sensitivity=None, strength_study=None,
               snapshot_results=(), snapshot_provenance=(), weekly=None,
               weekly_results=(), weekly_provenance=(), corrected=None):
    """Render a standalone, escaped, no-fetch Forecast Lab page."""
    from pgo_availability_view import render_current_scenario
    from pgo_model_updates import EDITION as selected_edition, render_current_updates
    css = _shared_css()
    if snapshot is None:
        lead = f'''<header class="lab-hero hero"><div class="status">Experimental &middot; frozen archive</div>
<h1>PGO Forecast Lab</h1><h2>Can PGO predict football?</h2>
<p>This page tracks one frozen 2026 experiment. Each forecast is an estimated scoring margin: positive favors the home team; negative favors the away team.</p>
<p><strong>{len(results)} of {len(lock["games"])} finalized results recorded.</strong> Interim tracking &mdash; not a validation result.</p>
<p><a href="index.html">Back to McCabe Ratings</a></p></header>'''
        archive_open = archive_close = archive_heading = ""
    else:
        lead = _snapshot_section(snapshot, snapshot_results, snapshot_provenance)
        if weekly is not None:
            updates = render_current_updates()
            selected = f'data-edition="{selected_edition}"' in updates
            lead = (
                _weekly_section(weekly, snapshot, weekly_results, weekly_provenance, corrected=corrected)
                + _corrected_section(corrected)
                + render_current_scenario()
                + _rating_explanations(snapshot)
                + '<details class="preseason-archive" id="preseason-baseline">'
                '<summary>September 7 preseason baseline &middot; All 272 games and 32 team ratings</summary>'
                + lead.replace('<h1>PGO Forecast Lab</h1>', '') + '</details>'
            )
            if selected:
                confidence_link = ('<a href="#pgo-season">Current rankings, picks and records</a>.' if 'id="pgo-season"' in updates else
                                   '<a href="#pgo-confidence-picks">PGO confidence picks</a>.'
                                   if 'id="pgo-confidence-picks"' in updates else
                                   '<a href="confidence-pool.html">Confidence pool calculator</a>.')
                lead = ('<header class="lab-hero hero"><h1>PGO Forecast Lab</h1>'
                        '<p>Dated predictions, explanations and grades throughout the season. '
                        '<a href="index.html">Back to the ratings board</a>. '
                        + confidence_link + '</p></header>'
                        + updates + '<details class="lab-detail" id="previous-models">'
                        '<summary>Compare previous models</summary>' + lead + '</details>')
            else:
                lead += updates
        else:
            lead += _rating_explanations(snapshot)
        archive_open = '<details class="original-archive"><summary>Original July/August archive &middot; Frozen 25% stability blend</summary>'
        archive_heading = '<section><h2>Original frozen forecast record</h2><p>This separate 272-game archive and its HOLD gate remain unchanged.</p></section>'
        archive_close = "</details>"
    lead += _model_sensitivity(sensitivity, strength_study)
    result_by_id = {row["game_id"]: row for row in results}
    metrics = interim_metrics(lock, results)
    weeks = []
    for week in sorted({game["week"] for game in lock["games"]}):
        body = []
        for game in (item for item in lock["games"] if item["week"] == week):
            result = result_by_id.get(game["game_id"])
            actual = error = "&mdash;"
            if result:
                actual = (
                    f'{html.escape(game["away"])} {result["away_score"]}, '
                    f'{html.escape(game["home"])} {result["home_score"]}; '
                    f'home margin {_signed(result["actual_margin"])}'
                )
                error = f'{abs(result["actual_margin"] - game["candidate_prediction"]):.1f}'
            body.append(
                f'<tr data-game-id="{html.escape(game["game_id"], quote=True)}">'
                f'<th scope="row">{html.escape(game["away"])} @ {html.escape(game["home"])}</th>'
                f'<td>{_spread({**game, "margin": game["candidate_prediction"]})}</td>'
                f'<td>{_spread({**game, "margin": game["pgo_v0_prediction"]})}</td>'
                f'<td>{_kickoff_time(game["kickoff"])}</td>'
                f'<td>{actual}</td><td>{error}</td></tr>'
            )
        weeks.append(
            f'<details class="forecast-week"{" open" if week == 1 else ""}>'
            f'<summary>Week {week} <span>{len(body)} games</span></summary>'
            '<div class="table-shell"><table><thead><tr><th>Matchup</th>'
            '<th>Original forecast favors</th><th>PGO v0 comparison favors</th><th>Frozen kickoff</th>'
            f'<th>Final score</th><th>Original forecast miss (points)</th></tr></thead><tbody>{"".join(body)}</tbody></table></div></details>'
        )
    sources = []
    for item in provenance:
        source_url = _https_url(item.get("source_url", ""))
        sources.append(
            f'<li>{html.escape(item.get("captured_at", ""))}: '
            f'<a href="{html.escape(source_url, quote=True)}">reviewed transcription source</a> '
            f'({html.escape(str(item.get("rows", 0)))} rows; CSV SHA-256 '
            f'<code>{html.escape(item.get("results_file_sha256", ""))}</code>)</li>'
        )
    sources = "".join(sources) or "<li>No result transcriptions recorded.</li>"
    diagnostic_rows = "".join(
        f'<tr><th scope="row">{html.escape(game["away"])} @ {html.escape(game["home"])}</th>'
        f'<td>{_spread({**game, "margin": game["challenger_prediction"]})}</td>'
        f'<td>{_spread({**game, "margin": game["challenger_full_strength_prediction"]})}</td></tr>'
        for game in lock["games"]
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PGO Forecast Lab</title><style>{css}
.lab-wrap{{max-width:1180px;margin:0 auto;padding:24px 18px 60px}}.lab-wrap a{{color:var(--accent)}}.lab-hero{{max-width:none;padding:26px;border-radius:14px;color:#fff;text-align:left}}.lab-hero a{{color:var(--highlight)}}.lab-hero a:focus-visible{{outline-color:var(--highlight)}}.lab-hero .status{{border-color:var(--highlight);margin-bottom:22px}}
.status{{display:inline-block;padding:6px 10px;border:1px solid var(--orange);border-radius:999px;font-weight:800}}.metric-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:16px 0}}.metric{{padding:14px;border:1px solid var(--border);border-radius:10px;background:var(--panel)}}.metric h3{{margin-top:0}}.forecast-week,.lab-detail,.original-archive,.preseason-archive{{margin:12px 0;border:1px solid var(--border);border-radius:10px;padding:12px}}.forecast-week summary,.lab-detail summary,.original-archive>summary,.preseason-archive>summary{{cursor:pointer;font-weight:800}}.forecast-week summary span{{color:var(--mut);font-weight:500}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid var(--border);text-align:right;white-space:nowrap}}th:first-child{{text-align:left}}.notice{{padding:14px;border-left:4px solid var(--orange);background:var(--panel)}}code{{overflow-wrap:anywhere}}.weekly-status{{font-weight:800}}
.forecast-week>.table-shell{{container-type:inline-size}}.forecast-week .forecast-reason-row>td{{text-align:left;padding:0 9px 10px;white-space:normal}}.forecast-reason{{width:min(960px,calc(100cqw - 18px));max-width:100%;font-size:13px;font-weight:400;line-height:1.5}}.forecast-reason>summary{{padding:7px 0;font-size:13px}}.forecast-reason-body{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px;padding:8px 0 4px;white-space:normal;font-size:13px;font-weight:400;line-height:1.5;overflow-wrap:anywhere}}.forecast-reason-block{{min-width:0;padding:14px;border:1px solid var(--border);border-radius:8px;background:var(--panel)}}.forecast-reason-block h3{{margin:0 0 8px;font-size:14px;color:var(--accent)}}.forecast-reason-block p{{margin:0 0 10px;white-space:normal}}.forecast-reason-block p:last-child{{margin-bottom:0}}.forecast-reason-calculation{{margin-top:12px;white-space:normal;overflow-wrap:anywhere}}.forecast-reason-calculation>summary{{margin-bottom:8px}}.forecast-week th,.forecast-week td{{vertical-align:top}}
.rating-explanation table{{table-layout:fixed}}.rating-explanation th{{white-space:normal;user-select:text}}.rating-explanation tbody th{{background:transparent;color:inherit;font-size:inherit;letter-spacing:normal;text-transform:none}}.rating-explanation thead th:last-child{{width:110px}}.rating-summary tr:last-child{{font-weight:800}}
.study-table{{table-layout:fixed}}.study-table th,.study-table td{{white-space:normal;overflow-wrap:anywhere}}.study-table th:first-child{{width:42%}}
.forecast-week tbody th{{text-transform:none;letter-spacing:normal}}
.corrected-team thead th{{font-size:11px;letter-spacing:normal;text-transform:none}}
.corrected-team td{{white-space:nowrap;overflow-wrap:normal;font-size:12px}}
</style><link rel="stylesheet" href="pgo-theme.css?v=20260910-readable"></head><body><main class="lab-wrap">
{lead}{archive_open}{archive_heading}
<section><h2>Record so far</h2>{_metric_cards(metrics)}
<p>The theoretical 50% winner benchmark is a reference only.</p></section>
<section class="notice"><h2>What was frozen</h2>
<p>The source cutoff was {_display_time(lock["as_of"], "EDT")}. The exact forecasts were publicly attested on {_display_time(ATTESTED_AT, "EDT")}, before the first kickoff. This track is 75% PGO v0 and 25% of an archived challenger fit; it is not the live ratings-table model.</p>
<p><a href="evidence/forecast-lab-2026/prospective_lock.json">Download exact lock</a> &middot; <a href="evidence/forecast-lab-2026/prospective_predictions.csv">Download exact prediction CSV</a> &middot; <a href="https://github.com/walshja9/Postgame_Outlet/blob/{ATTESTATION_COMMIT}/research/pgo_stability_blend/prospective_attestation.json">Immutable attestation</a></p>
</section>
<details><summary>Method, metrics, and scientific boundary</summary>
<p>These are model-estimated home-score margins, not market prices, final-score predictions, or calibrated probabilities. MAE is mean absolute margin error; RMSE gives larger misses more weight.</p>
<p>Winner accuracy is derived from frozen margin signs. It excludes actual ties and zero-margin abstentions, reports its denominator, and is separate from calibration and every promotion gate. The theoretical 50% benchmark is a reference; no observed coin-flip record is invented.</p>
<p>Constant zero and venue-only (+2.5 Home, 0 Neutral) are fixed diagnostic margin baselines outside the preregistered full-season gate. Market and McCabe game-pick comparisons are unavailable because they were not captured before kickoff.</p>
<p>Raw source cutoff: <code>{html.escape(lock["as_of"])}</code>. Raw attestation time: <code>{html.escape(ATTESTED_AT)}</code>.</p>
<p>Partial metrics are descriptive only. The unchanged canonical grade requires all 272 exact final results and is the only path to a prospective PASS, HOLD, or BLOCKED receipt.</p></details>
<section><h2>Frozen forecasts and observed results</h2><p>Kickoffs are the frozen schedule record and may differ from the current schedule. Original forecasts are never rewritten.</p>{"".join(weeks)}</section>
<details><summary>Archived challenger diagnostic</summary><p>These are outputs from the archived July-cutoff fit (delta 0.75 with QB-depth uncertainty), kept separate from the public ratings-table fit.</p><div class="table-shell"><table><thead><tr><th>Matchup</th><th>Current-lineup forecast favors</th><th>Full-strength forecast favors</th></tr></thead><tbody>{diagnostic_rows}</tbody></table></div></details>
<section><h2>Results provenance</h2><p>Each entry is a reviewed transcription. Its digest verifies the archived CSV, not the remote source contents.</p><ul>{sources}</ul></section>
<section><h2>Staff Picks</h2><p>No editorial picks are published in this model archive. Staff Picks remain a separate human product.</p></section>
{archive_close}
</main>{FORECAST_DISPLAY_SCRIPT}</body></html>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--predictions", type=Path, default=PREDICTIONS_PATH)
    parser.add_argument("--attestation", type=Path, default=ATTESTATION_PATH)
    parser.add_argument("--captures", type=Path, default=CAPTURE_ROOT)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--corrected", type=Path, help="Defaults to the latest verified corrected weekly source")
    parser.add_argument("--weekly", type=Path, default=WEEKLY_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    records = parser.add_mutually_exclusive_group()
    records.add_argument("--record-results", type=Path)
    records.add_argument("--record-snapshot-results", type=Path)
    records.add_argument("--record-weekly-results", type=Path)
    parser.add_argument("--source-url")
    args = parser.parse_args(argv)
    try:
        args.output = _validate_output_path(
            args.output,
            (args.lock, args.predictions, args.attestation, args.record_results,
             args.record_snapshot_results, args.record_weekly_results),
            (ARCHIVE_DIR, args.captures, args.snapshot, args.corrected or CORRECTED_DIR, args.weekly, SENSITIVITY_DIR, STRENGTH_STUDY_DIR),
        )
        lock = load_archive(args.lock, args.predictions, args.attestation)
        snapshot = _load_snapshot(args.snapshot)
        sensitivity = load_model_sensitivity(SENSITIVITY_DIR, snapshot) if snapshot is not None else None
        strength_study = load_strength_study(STRENGTH_STUDY_DIR) if sensitivity is not None else None
        weekly = pgo_forecast_weekly.load_weekly(args.weekly)
        corrected, corrected_directory = _load_corrected(args.corrected, weekly, args.weekly)
        _validate_output_path(args.output, (), (corrected_directory,))
        weekly_lock = {"games": weekly["games"]}
        if args.record_results or args.record_snapshot_results or args.record_weekly_results:
            if not args.source_url:
                raise ValueError("--source-url is required when recording results")
            if args.record_weekly_results:
                if not weekly["games"]:
                    raise ValueError("Cannot record results without verified weekly forecasts")
                record_results(
                    args.record_weekly_results, args.source_url,
                    args.weekly / "results", weekly_lock,
                )
            elif args.record_snapshot_results:
                if snapshot is None:
                    raise ValueError("Cannot record results without a verified snapshot")
                record_results(
                    args.record_snapshot_results, args.source_url,
                    args.snapshot / "results", snapshot["lock"],
                )
            else:
                record_results(
                    args.record_results, args.source_url, args.captures, lock,
                )
        elif args.source_url:
            raise ValueError("capture metadata requires a result-recording option")
        results, provenance = load_results(args.captures, lock)
        snapshot_results, snapshot_provenance = [], []
        if snapshot is not None:
            snapshot_results, snapshot_provenance = load_results(
                args.snapshot / "results", snapshot["lock"]
            )
        weekly_results, weekly_provenance = load_results(args.weekly / "results", weekly_lock)
        atomic_write_text(args.output, render_lab(
            lock, results, provenance, snapshot=snapshot, sensitivity=sensitivity, strength_study=strength_study,
            snapshot_results=snapshot_results,
            snapshot_provenance=snapshot_provenance,
            weekly=weekly if snapshot is not None else None,
            weekly_results=weekly_results,
            weekly_provenance=weekly_provenance,
            corrected=corrected,
        ))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Forecast Lab failed: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output.resolve()} ({len(results)} of {len(lock['games'])} results)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
