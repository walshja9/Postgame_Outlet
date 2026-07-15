#!/usr/bin/env python3
"""
Generate a standalone, self-contained index.html for the NFL Power Ratings.

Reads data/ratings.csv + data/prior_2025.csv, computes the preseason blend
(same logic we settled on: 50/50 prior-vs-build, 75/25 for injury-deflated
2025 finishers, then a soft squeeze of the tails), and writes a single
index.html with embedded CSS + vanilla JS (sortable table, team-color chips,
tier heat-map). No external dependencies — double-click to open.

Re-run after editing the CSVs to refresh the page.
"""

import argparse
import csv
import html
import json
import os
import re
import sys
from datetime import datetime

from release_ratings import load_release_rows
from snapshot import load_snaps

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
WRITEUPS = os.path.join(DATA, "writeups")
QB_WRITEUPS = os.path.join(DATA, "qb_writeups")  # optional per-QB overrides
PREVIEW_ROOT = os.path.join(HERE, "output", "ratings-preview")
CANONICAL_URL = "https://postgameoutlet.com/pages/power-ratings"


def default_preview_path(today=None):
    today = today or datetime.now().astimezone().date()
    return os.path.join(PREVIEW_ROOT, today.isoformat(), "index.html")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=default_preview_path(),
        help="Generated HTML path; defaults to a dated private local preview.",
    )
    return parser.parse_args(argv)

# Teams whose 2025 ending rating was deflated by a hurt/benched starter —
# trust the talent build more for these.
INJURY_DEFLATED = {"Kansas City Chiefs", "Cincinnati Bengals", "Baltimore Ravens"}

# Primary / secondary brand colors + abbreviation per team.
TEAM = {
    "Buffalo Bills": ("BUF", "#00338D", "#C60C30"),
    "Miami Dolphins": ("MIA", "#008E97", "#FC4C02"),
    "New England Patriots": ("NE", "#002244", "#C60C30"),
    "New York Jets": ("NYJ", "#125740", "#FFFFFF"),
    "Baltimore Ravens": ("BAL", "#241773", "#9E7C0C"),
    "Cincinnati Bengals": ("CIN", "#FB4F14", "#000000"),
    "Cleveland Browns": ("CLE", "#311D00", "#FF3C00"),
    "Pittsburgh Steelers": ("PIT", "#FFB612", "#101820"),
    "Houston Texans": ("HOU", "#03202F", "#A71930"),
    "Indianapolis Colts": ("IND", "#002C5F", "#A2AAAD"),
    "Jacksonville Jaguars": ("JAX", "#006778", "#9F792C"),
    "Tennessee Titans": ("TEN", "#0C2340", "#4B92DB"),
    "Denver Broncos": ("DEN", "#FB4F14", "#002244"),
    "Kansas City Chiefs": ("KC", "#E31837", "#FFB81C"),
    "Las Vegas Raiders": ("LV", "#000000", "#A5ACAF"),
    "Los Angeles Chargers": ("LAC", "#0080C6", "#FFC20E"),
    "Dallas Cowboys": ("DAL", "#003594", "#869397"),
    "New York Giants": ("NYG", "#0B2265", "#A71930"),
    "Philadelphia Eagles": ("PHI", "#004C54", "#A5ACAF"),
    "Washington Commanders": ("WAS", "#5A1414", "#FFB612"),
    "Chicago Bears": ("CHI", "#0B162A", "#C83803"),
    "Detroit Lions": ("DET", "#0076B6", "#B0B7BC"),
    "Green Bay Packers": ("GB", "#203731", "#FFB612"),
    "Minnesota Vikings": ("MIN", "#4F2683", "#FFC62F"),
    "Atlanta Falcons": ("ATL", "#A71930", "#000000"),
    "Carolina Panthers": ("CAR", "#0085CA", "#101820"),
    "New Orleans Saints": ("NO", "#D3BC8D", "#101820"),
    "Tampa Bay Buccaneers": ("TB", "#D50A0A", "#34302B"),
    "Arizona Cardinals": ("ARI", "#97233F", "#000000"),
    "Los Angeles Rams": ("LAR", "#003594", "#FFA300"),
    "San Francisco 49ers": ("SF", "#AA0000", "#B3995D"),
    "Seattle Seahawks": ("SEA", "#002244", "#69BE28"),
}


def load_config():
    cfg = {}
    with open(os.path.join(DATA, "config.csv"), newline="") as f:
        for row in csv.DictReader(f):
            cfg[row["key"]] = row["value"]
    return cfg


def load_prior():
    path = os.path.join(DATA, "prior_2025.csv")
    if not os.path.exists(path):
        return {}
    return {r["team"]: float(r["end_2025_rating"])
            for r in csv.DictReader(open(path, newline=""))}


def squeeze(x):
    """Soft-compress the tails so preseason is tighter than end-of-year."""
    if x > 5:
        return 5 + (x - 5) * 0.6
    if x < -3:
        return -3 + (x + 3) * 0.55
    return x


def load_teams(prior):
    rows = []
    path = os.path.join(DATA, "ratings.csv")
    for r in load_release_rows(path):
        qb = float(r["qb_value"] or 0)
        off = float(r["off_value"] or 0)
        dfn = float(r["def_value"] or 0)
        rating = round(qb + off + dfn, 1)
        p = prior.get(r["team"])
        rows.append({
            "team": r["team"], "conf": r["conf"], "div": r["division"],
            "qb_name": r["qb_name"], "qb": qb, "off": off, "def": dfn,
            "prior": p if p is not None else "",
            "rating": rating, "notes": r.get("notes", ""),
            "injury": r["team"] in INJURY_DEFLATED,
        })
    rows.sort(key=lambda x: -x["rating"])
    return rows


def md_to_html(text):
    """Tiny, safe markdown -> HTML. Escapes first, then renders a useful subset:
    ## headings, **bold**, *italic*, `code`, - bullet lists, and paragraphs.
    Deliberately small — the write-ups are short prose, not documents."""
    text = text.strip()
    if not text:
        return ""
    blocks = re.split(r"\n\s*\n", text)  # blank-line separated blocks
    out = []
    for block in blocks:
        lines = [ln.rstrip() for ln in block.splitlines()]
        # Bullet list block
        if all(re.match(r"\s*[-*]\s+", ln) for ln in lines if ln.strip()):
            stripped = (re.sub(r"^\s*[-*]\s+", "", ln) for ln in lines)
            items = "".join(f"<li>{_inline(s)}</li>" for s in stripped if s.strip())
            out.append(f"<ul>{items}</ul>")
            continue
        # Heading block (## Title)
        m = re.match(r"^(#{1,4})\s+(.*)$", lines[0])
        if m and len(lines) == 1:
            lvl = min(len(m.group(1)) + 2, 6)  # ## -> h4 so it sits under panel h-type
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            continue
        # Paragraph (join wrapped lines)
        out.append(f"<p>{_inline(' '.join(l for l in lines if l.strip()))}</p>")
    return "".join(out)


def _inline(s):
    """Escape then apply inline emphasis/code. Order matters: escape first."""
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    return s


def load_writeup(abbr):
    """Return rendered HTML for data/writeups/<ABBR>.md, or '' if none exists."""
    if not abbr:
        return ""
    path = os.path.join(WRITEUPS, f"{abbr}.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return md_to_html(f.read())


def qb_slug(name):
    """Filename-safe slug for a QB name: 'C.J. Stroud' -> 'cj-stroud'."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s


def extract_qb_section(abbr):
    """Pull the raw markdown of a team write-up's 'Quarterback' section (the
    text under a `## Quarterback` heading, up to the next `##`). Returns '' if
    the team file or that section doesn't exist."""
    if not abbr:
        return ""
    path = os.path.join(WRITEUPS, f"{abbr}.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # Split on ## headings, find the Quarterback block.
    parts = re.split(r"(?m)^##\s+", text)
    for block in parts:
        head, _, body = block.partition("\n")
        if head.strip().lower() == "quarterback":
            return body.strip()
    return ""


def load_qb_writeup(name, abbr):
    """QB drawer prose (already HTML). Precedence: a dedicated per-QB override
    at data/qb_writeups/<slug>.md wins; otherwise reuse the team write-up's
    'Quarterback' section; otherwise ''. (Hybrid: reuse now, override later.)"""
    override = os.path.join(QB_WRITEUPS, f"{qb_slug(name)}.md")
    if os.path.exists(override):
        with open(override, encoding="utf-8") as f:
            return md_to_html(f.read())
    return md_to_html(extract_qb_section(abbr))


def qb_tier(v):
    """A short, honest tier label for a QB value (points vs. a league-avg QB)."""
    if v >= 5.0:
        return "Elite"
    if v >= 2.5:
        return "Top-tier starter"
    if v >= 0.5:
        return "Above-average starter"
    if v >= -0.5:
        return "Average starter"
    if v >= -2.0:
        return "Below-average starter"
    return "Replacement / bridge"


def qb_tier_short(v):
    """Compact tier label for the table column (the full label lives in the drawer)."""
    if v >= 5.0:
        return "Elite"
    if v >= 2.5:
        return "Top tier"
    if v >= 0.5:
        return "Above avg"
    if v >= -0.5:
        return "Average"
    if v >= -2.0:
        return "Below avg"
    return "Replacement"


def heat(v, lo, hi):
    """Map a rating to a teal(+)/red(-) tint that reads on the dark panel.
    Brighter base colors + moderate alpha so tiers pop against navy rows."""
    if v >= 0:
        f = min(v / hi, 1) if hi else 0
        return f"rgba(45,212,191,{0.08 + 0.34 * f:.2f})"
    f = min(v / lo, 1) if lo else 0
    return f"rgba(239,90,70,{0.08 + 0.34 * f:.2f})"


def load_qbs(team_ratings=None):
    """Return (starters, backups): starters = all 32 ranked by qb_value;
    backups = top 18 from qb_depth.csv ranked by value. Each QB carries age/exp
    (from the CSVs, may be blank) and — for starters — the team's overall rating."""
    team_ratings = team_ratings or {}
    starters = []
    for r in csv.DictReader(open(os.path.join(DATA, "ratings.csv"), newline="")):
        starters.append({"name": r["qb_name"], "team": r["team"],
                         "val": float(r["qb_value"] or 0),
                         "age": r.get("age", "").strip(), "exp": r.get("exp", "").strip(),
                         "team_rating": team_ratings.get(r["team"])})
    starters.sort(key=lambda x: -x["val"])

    backups = []
    path = os.path.join(DATA, "qb_depth.csv")
    if os.path.exists(path):
        for r in csv.DictReader(open(path, newline="")):
            backups.append({"name": r["qb_name"], "team": r["team"],
                            "string": int(r["string"]), "val": float(r["value"] or 0),
                            "notes": r.get("notes", ""),
                            "age": r.get("age", "").strip(), "exp": r.get("exp", "").strip(),
                            "team_rating": team_ratings.get(r["team"])})
        backups.sort(key=lambda x: (-x["val"], x["string"]))
        backups = backups[:18]
    return starters, backups


def _bar(label, v, scale=6.5):
    """One horizontal +/- bar for a component in the expanded team detail.
    Bars grow right from center for positive, left for negative."""
    frac = max(-1, min(1, v / scale))
    pct = abs(frac) * 50  # half-width max
    side = "left:50%" if frac >= 0 else f"right:50%"
    color = "var(--pos)" if v >= 0 else "var(--neg)"
    return (f'<div class="brk"><span class="brk-l">{label}</span>'
            f'<span class="brk-track"><span class="brk-fill" '
            f'style="{side};width:{pct:.1f}%;background:{color}"></span></span>'
            f'<span class="brk-v">{v:+.1f}</span></div>')


def render_rating_rows(rows, detail=True):
    """Render the Power Ratings <tr> rows for one set of team dicts (a live or
    archived snapshot). Rows are ranked by rating; rank reflects each set.

    When detail=True, each row is clickable (carries data-abbr) and opens the
    team drawer — the detail content itself lives in the DETAILS payload, so the
    table never shifts. Archived snapshots pass detail=False (no drawer)."""
    ranked = sorted(rows, key=lambda x: -x["rating"])
    ratings = [r["rating"] for r in ranked] or [0]
    hi, lo = max(ratings), min(ratings)
    out = []
    for i, r in enumerate(ranked, 1):
        abbr, c1, c2 = TEAM.get(r["team"], ("?", "#444", "#888"))
        nm = html.escape(r["team"])
        qbn = html.escape(r.get("qb_name", ""))
        star = ' <span class="inj" title="2025 finish deflated by injury; weighted toward roster talent">▲inj</span>' if r.get("injury") else ""
        prior = f'{r["prior"]:+.2f}' if r.get("prior", "") != "" else "—"
        bg = heat(r["rating"], lo, hi)
        rowattr = f' class="teamrow" data-abbr="{abbr}"' if detail else ""
        out.append(f"""    <tr{rowattr}>
      <td class="rank">{i}</td>
      <td class="team"><span class="chip" style="background:{c1};border-color:{c2}">{abbr}</span>
        <span class="tname">{nm}</span><span class="div">{r['conf']} {r['div']}</span></td>
      <td class="qbn">{qbn}{star}</td>
      <td data-v="{r['qb']}">{r['qb']:+.1f}</td>
      <td data-v="{r['off']}">{r['off']:+.1f}</td>
      <td data-v="{r['def']}">{r['def']:+.1f}</td>
      <td class="prior" data-v="{r['prior'] or -99}">{prior}</td>
      <td class="rating" data-v="{r['rating']}" style="background:{bg}">{r['rating']:+.1f}</td>
    </tr>""")
    return "\n".join(out)


def build_details(rows):
    """Return {abbr: drawer-inner-HTML} for the live teams — the QB/Off/Def bar
    breakdown plus the write-up (or notes fallback). Rendered once and shipped as
    a JS payload so clicking a row fills the drawer without moving the table."""
    details = {}
    for r in rows:
        abbr, c1, c2 = TEAM.get(r["team"], ("?", "#444", "#888"))
        nm = html.escape(r["team"])
        rating_cls = "pos" if r["rating"] >= 0 else "neg"
        writeup = load_writeup(abbr)
        if not writeup:  # fall back to the one-line notes from ratings.csv
            note = r.get("notes", "").strip()
            writeup = (f'<p class="stub">{_inline(note)}</p>'
                       f'<p class="stub-hint">No full write-up yet — add one at '
                       f'<code>data/writeups/{abbr}.md</code>.</p>') if note else \
                      f'<p class="stub-hint">Write-up coming soon.</p>'
        bars = (_bar("QB", r["qb"]) + _bar("Offense", r["off"])
                + _bar("Defense", r["def"]))
        subtitle = f'{r["conf"]} {r["div"]} &middot; QB: {html.escape(r.get("qb_name", ""))}'
        details[abbr] = (
            f'<div class="dr-head"><span class="chip" style="background:{c1};border-color:{c2}">{abbr}</span>'
            f'<div class="dr-title"><span class="dr-name">{nm}</span>'
            f'<span class="dr-sub">{subtitle}</span></div>'
            f'<span class="dr-rating {rating_cls}">{r["rating"]:+.1f}</span></div>'
            f'<div class="dr-bars">{bars}</div>'
            f'<div class="dr-writeup">{writeup}</div>')
    return details


def build_qb_detail(q, kind, rank):
    """Drawer-inner HTML for one QB row: value/tier/rank header, a value bar on
    the same scale as the team drawer, and the write-up (per-QB override, else
    the team's Quarterback section, else a graceful stub)."""
    abbr, c1, c2 = TEAM.get(q["team"], ("?", "#444", "#888"))
    name = q["name"]
    nm = html.escape(name)
    val = q["val"]
    val_cls = "pos" if val >= 0 else "neg"
    team_full = html.escape(q["team"])
    if kind == "backup":
        s = q.get("string")
        role = "2nd string" if s == 2 else ("3rd string" if s == 3 else f"{s} string")
        rank_line = f'Backup #{rank}'
    else:
        role = "Starter"
        rank_line = f'QB #{rank} of 32'
    subtitle = f'{team_full} &middot; {role} &middot; {rank_line}'

    writeup = load_qb_writeup(name, abbr)
    if not writeup:  # backups usually have only a one-line note; starters a section
        note = (q.get("notes") or "").strip()
        if note:
            writeup = f'<p class="stub">{_inline(note)}</p>'
        else:
            writeup = ('<p class="stub-hint">No write-up yet — add one at '
                       f'<code>data/qb_writeups/{qb_slug(name)}.md</code>.</p>')

    bar = _bar("Value", val)
    return (
        f'<div class="dr-head"><span class="chip" style="background:{c1};border-color:{c2}">{abbr}</span>'
        f'<div class="dr-title"><span class="dr-name">{nm}</span>'
        f'<span class="dr-sub">{subtitle}</span></div>'
        f'<span class="dr-rating {val_cls}">{val:+.1f}</span></div>'
        f'<div class="dr-tier">{qb_tier(val)} &middot; points vs. a league-average QB (0.0)</div>'
        f'<div class="dr-bars">{bar}</div>'
        f'<div class="dr-writeup">{writeup}</div>')


def build_html(rows, config, generated_at=None):
    season = config.get("season", "2026")
    edition = config.get("edition", f"{season} Preseason")
    author = config.get("author", "Sean McCabe")
    generated_at = generated_at or datetime.now().astimezone()
    updated_iso = generated_at.isoformat(timespec="seconds")
    updated = f"{generated_at:%B} {generated_at.day}, {generated_at.year}"
    body = render_rating_rows(rows)

    # Archived weekly snapshots -> {label: rendered <tr> rows}. "Current" is
    # always the live data; saved weeks come from data/snapshots.json.
    versions = {"Current": body}
    version_meta = {"Current": {"published_at": "", "corrections": []}}
    snap_path = os.path.join(DATA, "snapshots.json")
    snaps = load_snaps(snap_path)
    for label, entry in snaps.items():
        versions[label] = render_rating_rows(entry["rows"], detail=False)
        version_meta[label] = {
            "published_at": entry["published_at"],
            "corrections": entry["corrections"],
        }
    versions_json = json.dumps(versions)
    version_meta_json = json.dumps(version_meta).replace("<", "\\u003c")
    ver_opts = "".join(f'<option value="{html.escape(l)}">{html.escape(l)}</option>'
                       for l in versions)

    # QB tab: starters 1-32, then top-18 backups. Rows are clickable and open
    # the same drawer as teams, keyed by data-qb into the QB_DETAILS payload.
    starters, backups = build_html.qb_data or ([], [])
    qb_details = {}

    def qb_key(q, kind):
        # Unique per row: name + team + string (a name can appear as both a
        # starter on one team and a backup on another).
        return f'{kind}:{qb_slug(q["name"])}:{q["team"]}:{q.get("string", 1)}'

    def qb_row(rank, q, kind):
        abbr, c1, c2 = TEAM.get(q["team"], ("?", "#444", "#888"))
        nm = html.escape(q["name"])
        bg = heat(q["val"], -6, 6.5)
        tag = ""
        if kind == "backup":
            s = q.get("string")
            label = "2nd" if s == 2 else ("3rd" if s == 3 else f"{s}")
            tag = f'<span class="div">{label} string</span>'
        age = q.get("age") or "—"
        exp_raw = q.get("exp")
        exp = "R" if exp_raw in ("0", 0) else (exp_raw or "—")  # rookie = R
        tr = q.get("team_rating")
        tr_disp = f'{tr:+.1f}' if tr is not None else "—"
        tr_cls = "pos" if (tr is not None and tr >= 0) else ("neg" if tr is not None else "")
        key = qb_key(q, kind)
        qb_details[key] = build_qb_detail(q, kind, rank)
        return (f'<tr class="qbrow" data-qb="{html.escape(key)}"><td class="rank">{rank}</td>'
                f'<td class="team"><span class="chip" style="background:{c1};border-color:{c2}">{abbr}</span>'
                f'<span class="tname">{nm}</span>{tag}</td>'
                f'<td class="qbmeta">{age}</td>'
                f'<td class="qbmeta">{exp}</td>'
                f'<td class="qbmeta {tr_cls}">{tr_disp}</td>'
                f'<td class="qbtier">{qb_tier_short(q["val"])}</td>'
                f'<td class="rating" style="background:{bg}">{q["val"]:+.1f}</td></tr>')

    qb_starter_rows = "\n".join(qb_row(i, q, "starter") for i, q in enumerate(starters, 1))
    qb_backup_rows = "\n".join(qb_row(i, q, "backup") for i, q in enumerate(backups, 1))
    has_qbs = "block" if starters else "none"
    qb_details_json = json.dumps(qb_details)

    details_json = json.dumps(build_details(rows))

    return (TEMPLATE
            .replace("{{SEASON}}", str(season))
            .replace("{{EDITION}}", html.escape(edition))
            .replace("{{AUTHOR}}", html.escape(author))
            .replace("{{UPDATED_ISO}}", html.escape(updated_iso))
            .replace("{{UPDATED}}", updated)
            .replace("{{ROWS}}", body)
            .replace("{{DETAILS_JSON}}", details_json)
            .replace("{{VERSIONS_JSON}}", versions_json)
            .replace("{{VERSION_META_JSON}}", version_meta_json)
            .replace("{{VERSION_OPTS}}", ver_opts)
            .replace("{{QB_STARTERS}}", qb_starter_rows)
            .replace("{{QB_BACKUPS}}", qb_backup_rows)
            .replace("{{QB_DETAILS_JSON}}", qb_details_json)
            .replace("{{HAS_QBS}}", has_qbs))


build_html.qb_data = ([], [])  # set by main() before calling


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{EDITION}} NFL Power Ratings | Postgame Outlet</title>
<meta name="description" content="Sean McCabe’s {{EDITION}} NFL Power Ratings, expressed as neutral-field points above or below a league-average team.">
<link rel="canonical" href="https://postgameoutlet.com/pages/power-ratings">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  /* Postgame Outlet (Shopify Spotlight) palette: white canvas, slate-blue ink
     (#384f6f), orange accent (#fd962f family), Oswald display + Montserrat body. */
  :root {
    --bg:#ffffff; --bg2:#ffffff; --panel:#ffffff; --panel2:#f0f3f8;
    --row-alt:#f7f9fc; --hover:#edf1f7; --border:#dfe6ef; --border2:#c9d3e2;
    --ink:#384f6f; --mut:#647892; --dim:#8fa0b6;
    --teal:#e0821c; --teal2:#c96f0e; --violet:#384f6f; --violet2:#384f6f;
    --pos:#1a9a6c; --neg:#d94f36; --accent:#e0821c; --orange:#fd962f;
    --disp:'Oswald',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    --body:'Montserrat',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; color:var(--ink); font:15px/1.45 var(--body);
    background:var(--bg);
    background-attachment:fixed; min-height:100vh;
  }
  .wrap { max-width:1040px; margin:0 auto; padding:0 16px 72px; }

  /* Full-bleed slate banner, same family as the store's hero boxes */
  .hero { background:linear-gradient(120deg,#324763 0%,#384f6f 55%,#3f5878 100%);
          padding:38px 16px 34px; margin-bottom:26px;
          border-bottom:3px solid var(--orange); }
  header { text-align:center; max-width:1040px; margin:0 auto; }
  header h1 {
    margin:0; font-family:var(--disp); font-weight:700; line-height:.95;
    font-size:clamp(34px,6.5vw,60px); letter-spacing:.5px; color:#fff;
    text-transform:uppercase;
  }
  header h1 .accent { color:var(--orange); }
  header .sub { color:rgba(255,255,255,.72); font-size:13px; margin-top:9px;
                letter-spacing:.04em; }
  header .updated { color:rgba(255,255,255,.5); font-size:11px; margin-top:6px;
                    letter-spacing:.06em; text-transform:uppercase; }
  header .updated::before { content:"● "; color:var(--orange); }

  .panel.active { background:var(--panel);
    border:1px solid var(--border); border-radius:14px; padding:18px 16px 20px;
    box-shadow:0 10px 30px rgba(56,79,111,.10); }

  table { width:100%; border-collapse:collapse; background:transparent; }
  th,td { padding:10px 11px; text-align:right; white-space:nowrap; }
  th {
    background:var(--ink); color:rgba(255,255,255,.78); font-family:var(--body); font-weight:600;
    font-size:11px; letter-spacing:.07em; text-transform:uppercase; cursor:pointer;
    user-select:none; border-bottom:2px solid var(--orange);
  }
  th:first-child { border-top-left-radius:9px; } th:last-child { border-top-right-radius:9px; }
  th:hover { color:#ffc07a; background:#2e415c; }
  th.up { color:var(--orange); } th.down { color:var(--orange); }
  th.up::after { content:" \\2191"; } th.down::after { content:" \\2193"; }
  tbody tr { border-bottom:1px solid var(--border); }
  tbody tr:nth-child(even) { background:var(--row-alt); }
  tbody tr:last-child { border-bottom:none; }
  tbody tr:hover { background:var(--hover); }
  tr.teamrow, tr.qbrow { cursor:pointer; }
  tr.teamrow.sel, tr.qbrow.sel { background:rgba(56,79,111,.10); box-shadow:inset 3px 0 0 var(--violet); }
  td.rank { text-align:center; color:var(--dim); font-family:var(--body);
            font-weight:600; font-size:14px; width:40px; font-variant-numeric:tabular-nums; }
  td.team, th.team, td.qbn, th.qbn { text-align:left; }
  .chip { display:inline-block; min-width:40px; text-align:center; padding:3px 6px; margin-right:9px;
          border-radius:5px; font-size:11px; font-weight:700; color:#fff; border:1px solid;
          vertical-align:middle; text-shadow:0 1px 1px rgba(0,0,0,.55);
          box-shadow:0 1px 3px rgba(0,0,0,.4); }
  .tname { font-weight:600; color:var(--ink); }
  .div { color:var(--dim); font-size:11px; margin-left:8px; text-transform:uppercase; letter-spacing:.04em; }
  .qbn { color:var(--mut); font-weight:500; }
  .inj { color:var(--neg); font-size:11px; font-weight:700; }
  td.rating { font-family:var(--body); font-weight:700; font-size:16px; border-radius:4px;
              color:var(--teal2); }
  td.prior { color:var(--dim); }
  td[data-v] { font-variant-numeric:tabular-nums; color:var(--ink); }
  .legend { color:var(--mut); font-size:12px; margin-top:16px; line-height:1.7;
            border-top:1px solid var(--border); padding-top:12px; }
  .legend b { color:var(--ink); }

  /* Tabs = pill nav */
  .tabs { display:flex; gap:8px; margin-bottom:18px; flex-wrap:wrap; justify-content:center; }
  .tab {
    padding:8px 18px; background:var(--panel); border:1px solid var(--border);
    border-radius:9px; color:var(--mut); cursor:pointer; font-family:var(--body);
    font-size:14px; font-weight:600; letter-spacing:.01em; transition:all .12s;
  }
  .tab:hover { color:var(--ink); border-color:var(--border2); }
  .tab.active { color:#fff; background:var(--orange); border-color:var(--orange); }
  .panel { display:none; } .panel.active { display:block; }

  .weekbar { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
  .weekbar label { font-weight:600; color:var(--mut); font-size:13px; }
  .weekbar select { background:var(--panel2); color:var(--ink); border:1px solid var(--border2);
         border-radius:8px; padding:7px 12px; font-size:14px; font-family:var(--body); }
  .weekbar .note { color:var(--dim); font-size:12px; }
  .version-meta { color:var(--mut); font-size:12px; margin:8px 0 0; }
  .version-meta:empty { display:none; }
  .version-meta p { margin:4px 0 0; }
  .pos { color:var(--pos); } .neg { color:var(--neg); }
  .qbhead { font-family:var(--disp); font-weight:600; font-size:20px; color:var(--ink);
            margin:24px 0 10px; text-transform:uppercase; letter-spacing:.03em;
            border-bottom:2px solid var(--teal); padding-bottom:5px; }
  .qbhead:first-of-type { margin-top:2px; }
  .qbtable td.rating { text-align:right; }
  /* QB at-a-glance columns: age / exp / team rating (center), tier (right-ish) */
  th.qbmeta, td.qbmeta { text-align:center; width:58px; font-variant-numeric:tabular-nums; }
  td.qbmeta { color:var(--mut); font-weight:500; }
  td.qbmeta.pos { color:var(--pos); } td.qbmeta.neg { color:var(--neg); }
  th.qbtier, td.qbtier { text-align:right; }
  td.qbtier { color:var(--dim); font-size:12px; text-transform:uppercase;
              letter-spacing:.03em; white-space:nowrap; }
  @media (max-width:600px) {
    /* drop the wider tier label on narrow screens; keep age/exp/team rating */
    th.qbtier, td.qbtier { display:none; }
  }

  /* --- Team drawer (slides in from right; table stays put) --- */
  .scrim { position:fixed; inset:0; background:rgba(30,42,60,.45);
           backdrop-filter:blur(2px); opacity:0; pointer-events:none;
           transition:opacity .2s ease; z-index:40; }
  .scrim.open { opacity:1; pointer-events:auto; }
  .drawer {
    position:fixed; top:0; right:0; height:100vh; width:min(460px,92vw);
    background:var(--bg2); border-left:1px solid var(--border2);
    box-shadow:-24px 0 60px rgba(56,79,111,.25); z-index:50;
    transform:translateX(100%); transition:transform .24s cubic-bezier(.4,0,.2,1);
    display:flex; flex-direction:column;
  }
  .drawer.open { transform:translateX(0); }
  /* Embedded in an iframe: position:fixed anchors to the iframe, not the parent
     viewport, so the parent posts its visible slice and we pin the drawer to it
     via --vp-top / --vp-h (set from JS). Falls back sanely if no message. */
  body.embedded .scrim  { position:absolute; top:var(--vp-top,0); left:0; right:0;
                          height:var(--vp-h,100%); }
  body.embedded .drawer { position:absolute; top:var(--vp-top,0);
                          height:var(--vp-h,100vh); }
  @media (max-width:560px) {
    /* bottom sheet on phones — standalone only; embedded stays a pinned panel */
    body:not(.embedded) .drawer { top:auto; bottom:0; right:0; width:100%; height:88vh;
              border-left:none; border-top:1px solid var(--border2);
              border-radius:16px 16px 0 0; transform:translateY(100%); }
    body:not(.embedded) .drawer.open { transform:translateY(0); }
  }
  .drawer-close {
    position:absolute; top:12px; right:12px; width:32px; height:32px; z-index:2;
    display:flex; align-items:center; justify-content:center; cursor:pointer;
    background:var(--panel2); border:1px solid var(--border2); border-radius:8px;
    color:var(--mut); font-size:18px; line-height:1; transition:all .12s;
  }
  .drawer-close:hover { color:var(--ink); border-color:var(--border2); background:var(--hover); }
  .drawer-body { overflow-y:auto; padding:22px 22px 32px; }
  .dr-head { display:flex; align-items:center; gap:12px; padding-bottom:14px;
             margin-bottom:16px; border-bottom:1px solid var(--border); padding-right:36px; }
  .dr-title { display:flex; flex-direction:column; gap:2px; min-width:0; }
  .dr-name { font-family:var(--disp); font-weight:600; font-size:22px; color:var(--ink);
             text-transform:uppercase; letter-spacing:.02em; line-height:1.05; }
  .dr-sub { color:var(--dim); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
  .dr-rating { margin-left:auto; font-family:var(--disp); font-weight:700; font-size:26px; }
  .dr-rating.pos { color:var(--pos); } .dr-rating.neg { color:var(--neg); }
  .dr-tier { color:var(--mut); font-size:12px; margin:-6px 0 16px;
             text-transform:uppercase; letter-spacing:.03em; }
  .dr-tier::before { content:""; display:inline-block; width:8px; height:8px;
             border-radius:50%; background:var(--teal); margin-right:7px;
             vertical-align:middle; }
  .dr-bars { display:flex; flex-direction:column; gap:10px; margin-bottom:20px; }
  .brk { display:flex; align-items:center; gap:10px; font-size:12px; }
  .brk-l { width:58px; color:var(--mut); text-transform:uppercase; letter-spacing:.04em;
           font-size:11px; text-align:right; }
  .brk-track { position:relative; flex:1; height:14px; background:var(--panel2);
               border-radius:7px; overflow:hidden; box-shadow:inset 0 0 0 1px var(--border); }
  .brk-track::before { content:""; position:absolute; left:50%; top:0; bottom:0;
                       width:1px; background:var(--border2); }
  .brk-fill { position:absolute; top:0; bottom:0; border-radius:6px; }
  .brk-v { width:40px; font-weight:700; font-size:14px; text-align:right;
           font-variant-numeric:tabular-nums; color:var(--ink); }
  .dr-writeup { color:var(--ink); font-size:14px; line-height:1.65; }
  .dr-writeup h4,.dr-writeup h5,.dr-writeup h6 {
    font-family:var(--disp); font-weight:600; color:var(--teal2); text-transform:uppercase;
    letter-spacing:.03em; margin:18px 0 7px; font-size:14px; }
  .dr-writeup h4:first-child { margin-top:0; }
  .dr-writeup p { margin:0 0 11px; color:#4a5d78; }
  .dr-writeup ul { margin:0 0 11px; padding-left:20px; }
  .dr-writeup li { margin:3px 0; color:#4a5d78; }
  .dr-writeup strong { color:var(--ink); }
  .dr-writeup code { background:var(--panel2); padding:1px 5px; border-radius:4px;
                     font-size:12px; color:var(--teal2); }
  .dr-writeup .stub { font-style:italic; color:#4a5d78; }
  .dr-writeup .stub-hint { color:var(--dim); font-size:12px; margin-top:4px; }

  /* Methodology tab */
  .method { color:#4a5d78; font-size:15px; line-height:1.65; }
  .method h3 { font-family:var(--disp); font-weight:600; color:var(--ink);
               text-transform:uppercase; letter-spacing:.03em; font-size:19px;
               margin:24px 0 9px; border-bottom:2px solid var(--teal); padding-bottom:5px; }
  .method h3:first-child { margin-top:0; }
  .method p { margin:0 0 12px; } .method ul { margin:0 0 12px; padding-left:22px; }
  .method li { margin:4px 0; } .method b { color:var(--ink); }
  .method code { background:var(--panel2); padding:1px 6px; border-radius:4px;
               font-size:13px; color:var(--teal2); }
  .method .formula { background:var(--panel2); border-left:3px solid var(--teal);
                     padding:11px 14px; border-radius:0 8px 8px 0; margin:0 0 14px;
                     font-family:var(--body); font-size:14px; color:var(--ink); }
</style>
</head>
<body>
<div class="hero">
  <header>
    <h1>NFL Power Ratings <span class="accent">{{SEASON}}</span></h1>
    <div class="sub">Preseason &middot; roster-based, points vs. a league-average team (0.0)</div>
    <div class="updated">By {{AUTHOR}} &middot; {{EDITION}} &middot; Updated <time datetime="{{UPDATED_ISO}}">{{UPDATED}}</time></div>
  </header>
</div>
<div class="wrap">
  <div class="tabs">
    <div class="tab active" data-panel="ratings">Power Ratings</div>
    <div class="tab" data-panel="qbs" style="display:{{HAS_QBS}}">QB Rankings</div>
    <div class="tab" data-panel="method">Methodology</div>
  </div>
  <div class="panel active" id="panel-ratings">
  <div class="weekbar">
    <label for="ver">Snapshot</label>
    <select id="ver">{{VERSION_OPTS}}</select>
    <span class="note">Click any column to sort &middot; pick a past week to see ratings as they stood</span>
  </div>
    <div id="versionMeta" class="version-meta" role="status" aria-live="polite"></div>
  <table id="pr">
    <thead>
      <tr>
        <th class="rank" data-k="rank">#</th>
        <th class="team" data-k="team">Team</th>
        <th class="qbn" data-k="qbn">QB</th>
        <th data-k="num">QB</th>
        <th data-k="num">Off</th>
        <th data-k="num">Def</th>
        <th data-k="num">End '25</th>
        <th data-k="num" class="up">Rating</th>
      </tr>
    </thead>
    <tbody>
{{ROWS}}
    </tbody>
  </table>
  <div class="legend">
    <b>Rating</b> = QB + Offense + Defense (each in points vs. a league-average team, 0.0).<br>
    <b>Off / Def</b> are non-QB unit values. <b>End '25</b> is last season's ending rating, shown for reference. Green = above average, red = below.
  </div>
  </div><!-- /panel-ratings -->

  <div class="panel" id="panel-qbs">
    <div class="sub" style="margin:-6px 0 14px">QB value in points vs. a league-average QB (0.0). Starters ranked 1&ndash;32, then the top 18 backups. &middot; click any QB to explore</div>
    <h2 class="qbhead">Starting QBs</h2>
    <table class="qbtable">
      <thead><tr><th class="rank">#</th><th class="team">Quarterback</th>
        <th class="qbmeta">Age</th><th class="qbmeta">Exp</th>
        <th class="qbmeta">Team</th><th class="qbtier">Tier</th><th>Value</th></tr></thead>
      <tbody>
{{QB_STARTERS}}
      </tbody>
    </table>
    <h2 class="qbhead">Top 18 Backups</h2>
    <table class="qbtable">
      <thead><tr><th class="rank">#</th><th class="team">Quarterback</th>
        <th class="qbmeta">Age</th><th class="qbmeta">Exp</th>
        <th class="qbmeta">Team</th><th class="qbtier">Tier</th><th>Value</th></tr></thead>
      <tbody>
{{QB_BACKUPS}}
      </tbody>
    </table>
  </div><!-- /panel-qbs -->

  <div class="panel" id="panel-method">
    <div class="method">
      <h3>The quick version</h3>
      <p>Welcome to the Postgame Outlet power ratings corner. In a nutshell, our power
      ratings tell you how many points better or worse a team is than an average NFL
      team. If Green Bay is a <code>+9</code>, we see them as nine points stronger than
      a league-average team on a neutral field. If Kansas City is <code>+8.5</code>,
      Green Bay would be about half a point better than the Chiefs somewhere neutral.</p>
      <p>Home field plays a role too. We give about a point and a half for home field
      on average, but tougher buildings like Green Bay or Seattle get bumped closer to
      two, while friendlier stops like Jacksonville or the Chargers might only get a
      single point. Prime-time home games get an extra half-point for the intensity.</p>
      <p>These are <b>living numbers</b> — they move as we get new info: injuries,
      trades, or just last year's data mattering less as the new season takes shape.
      One thing we don't bake in is motivation. A team on a losing streak might come
      out extra fired up, and we leave that layer of context to you. Use the ratings
      to read the NFL landscape at a glance — and maybe find a little edge on your
      picks — but remember they're always evolving, just like the game itself.</p>

      <h3>What this is</h3>
      <p>A roster-based, points-denominated power rating for all 32 NFL teams. Every
      team's rating is expressed in <b>points versus a league-average team (0.0)</b> and
      is the straight sum of its parts:</p>
      <div class="formula">Team Rating = QB + Offense (non-QB) + Defense</div>
      <p>A rating of <code>+7.0</code> means that team would be favored by about a
      touchdown over a perfectly average team on a neutral field.</p>

      <h3>How the numbers are set</h3>
      <ul>
        <li><b>QB</b> — the dominant lever. 0.0 ≈ a middling starter (roughly QB16–18).
        Elite quarterbacks land +5 to +6.5; the worst starters floor around −2.5.
        Values are <em>expected 2026 value</em>, so injury and availability risk is
        already priced in.</li>
        <li><b>Offense / Defense</b> — the non-QB units, centered at average. Most teams
        sit within about ±1.0, driven by the 2026 free-agency and draft roster movement.</li>
      </ul>

      <h3>From ratings to a betting line</h3>
      <p>The spread model turns two ratings into a projected margin:</p>
      <div class="formula">my_margin(home) = rating_home − rating_away + HFA<br>
      HFA = per-team home-field (default 1.5) + 0.5 if it's a primetime home game</div>
      <p>The projected spread is <code>−my_margin</code> (negative = home favored). The
      <b>edge</b> is <code>market − my_spread</code>; anything 1.5 points or larger is
      flagged as a spot where my number disagrees with the market.</p>

      <h3>Honesty &amp; caveats</h3>
      <ul>
        <li>Market spreads come from an unofficial ESPN feed and only firm up close to
        game week — early-summer lines are placeholders, so don't over-read specific
        edges yet.</li>
        <li>If one or two teams dominate the season-long edge list, that usually means
        <em>my</em> rating on those teams is the outlier — not the market.</li>
        <li>Teams marked <span class="inj">▲inj</span> had a 2025 finish deflated by an
        injured or benched starter, so they're weighted toward roster talent rather than
        last year's record.</li>
      </ul>
    </div>
  </div><!-- /panel-method -->
</div>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-hidden="true">
  <div class="drawer-close" id="drawerClose" title="Close">&times;</div>
  <div class="drawer-body" id="drawerBody"></div>
</aside>

<script>
  const VERSIONS = {{VERSIONS_JSON}};
  const VERSION_META = {{VERSION_META_JSON}};
  const DETAILS = {{DETAILS_JSON}};
  const QB_DETAILS = {{QB_DETAILS_JSON}};
</script>
<script>
  const tb = document.querySelector('#pr tbody');
  const ths = document.querySelectorAll('#pr th');
  let sortCol = 7, asc = false;
  function val(tr, i) {
    const td = tr.children[i];
    const dv = td.getAttribute('data-v');
    if (dv !== null) return parseFloat(dv);
    if (i === 0) return parseFloat(td.textContent);
    return td.textContent.trim().toLowerCase();
  }
  function sortBy(i) {
    if (i === sortCol) asc = !asc; else { sortCol = i; asc = (i === 1 || i === 2); }
    const rows = [...tb.rows];
    rows.sort((a, b) => {
      const x = val(a, i), y = val(b, i);
      if (typeof x === 'number') return asc ? x - y : y - x;
      return asc ? (x < y ? -1 : x > y ? 1 : 0) : (x > y ? -1 : x < y ? 1 : 0);
    });
    rows.forEach(r => tb.appendChild(r));
    ths.forEach(t => t.classList.remove('up', 'down'));
    ths[i].classList.add(asc ? 'up' : 'down');
  }
  ths.forEach((th, i) => th.addEventListener('click', () => sortBy(i)));

  // --- shared drawer (teams + QBs; opens over the page, table never shifts) ---
  const scrim = document.getElementById('scrim');
  const drawer = document.getElementById('drawer');
  const drawerBody = document.getElementById('drawerBody');
  let lastRow = null;
  function openDrawer(html, row) {
    if (!html) return;
    drawerBody.innerHTML = html;
    drawerBody.scrollTop = 0;
    drawer.classList.add('open'); scrim.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    if (lastRow) lastRow.classList.remove('sel');
    lastRow = row; if (row) row.classList.add('sel');
  }
  function closeDrawer() {
    drawer.classList.remove('open'); scrim.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    if (lastRow) { lastRow.classList.remove('sel'); lastRow = null; }
  }
  function bindRows() {
    tb.querySelectorAll('tr.teamrow').forEach(row => {
      row.onclick = () => openDrawer(DETAILS[row.dataset.abbr], row);
    });
  }
  bindRows();
  // QB rows are static (no re-render), so bind once.
  document.querySelectorAll('tr.qbrow').forEach(row => {
    row.onclick = () => openDrawer(QB_DETAILS[row.dataset.qb], row);
  });
  scrim.addEventListener('click', closeDrawer);
  document.getElementById('drawerClose').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

  // --- snapshot dropdown (Current + archived weeks) ---
  const versionMeta = document.getElementById('versionMeta');
  function renderVersionMeta(label) {
    const meta = VERSION_META[label] || { published_at: '', corrections: [] };
    versionMeta.replaceChildren();
    if (meta.published_at) {
      const published = document.createElement('p');
      published.textContent = 'Snapshot locked ' + meta.published_at;
      versionMeta.appendChild(published);
    }
    meta.corrections.forEach(correction => {
      const note = document.createElement('p');
      note.textContent = 'Correction ' + correction.at + ': ' + correction.note;
      versionMeta.appendChild(note);
    });
  }
  renderVersionMeta('Current');

  const verSel = document.getElementById('ver');
  if (verSel) {
    verSel.addEventListener('change', e => {
      const cur = e.target.value === 'Current';
      tb.innerHTML = VERSIONS[e.target.value] || VERSIONS['Current'];
      renderVersionMeta(e.target.value);
      closeDrawer();       // archived snapshots have no drawer detail
      if (cur) bindRows(); // only the live table opens the drawer
      // reset sort to Rating descending (the archived rank order)
      sortCol = -1; asc = false; sortBy(7);
    });
  }

  // --- tabs ---
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      closeDrawer();  // don't leave a team/QB drawer open across tab switches
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('panel-' + tab.dataset.panel).classList.add('active');
    });
  });

  // --- iframe embed bridge (no-op when opened directly) ---
  if (window.parent !== window) {
    document.body.classList.add('embedded');
    // 1) Report our content height to the parent so it can size the iframe.
    let lastH = 0;
    function reportHeight() {
      const h = Math.ceil(document.documentElement.getBoundingClientRect().height);
      if (h !== lastH) { lastH = h;
        parent.postMessage({ type: 'npr:height', height: h }, '*'); }
    }
    if (window.ResizeObserver) new ResizeObserver(reportHeight).observe(document.body);
    window.addEventListener('load', reportHeight);
    setTimeout(reportHeight, 60); setTimeout(reportHeight, 400);
    // Content changed (tab switch, sort, snapshot) -> re-measure.
    document.addEventListener('click', () => setTimeout(reportHeight, 30), true);
    // 2) Parent tells us which vertical slice of the iframe is on screen, so the
    //    drawer/scrim pin to the visible area instead of the whole tall iframe.
    addEventListener('message', e => {
      const d = e.data;
      if (!d || d.type !== 'npr:viewport') return;
      document.body.style.setProperty('--vp-top', d.top + 'px');
      document.body.style.setProperty('--vp-h', d.height + 'px');
    });
    parent.postMessage({ type: 'npr:ready' }, '*');  // ask parent to start sending
  }
</script>
</body>
</html>
"""


def main(argv=None):
    args = parse_args(argv)
    cfg = load_config()
    prior = load_prior()
    try:
        rows = load_teams(prior)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    team_ratings = {row["team"]: row["rating"] for row in rows}
    build_html.qb_data = load_qbs(team_ratings)

    out = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(build_html(rows, cfg))
    print(f"Wrote {out}")
    print(
        f"  {len(rows)} teams | top: {rows[0]['team']} {rows[0]['rating']:+.1f}"
        f" | bottom: {rows[-1]['team']} {rows[-1]['rating']:+.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
