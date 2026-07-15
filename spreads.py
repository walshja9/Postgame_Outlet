#!/usr/bin/env python3
"""
Pull the NFL schedule + market spreads from ESPN's free (unofficial) JSON API,
compare each game's market line to the spread implied by our power ratings, and
flag the biggest edges.

Usage:
    python3 spreads.py            # current/upcoming week
    python3 spreads.py 1          # regular-season week 1
    python3 spreads.py 1 2026     # week 1 of the 2026 season
    python3 spreads.py 1 --html   # also write spreads.html
    python3 spreads.py all        # every regular-season week (1-18)
    python3 spreads.py all 2026 --html   # full season + spreads.html

Spread model:
    my_margin(home) = rating_home - rating_away + HFA
    HFA = base (per-team, default 1.5) + 0.5 if a primetime home game
    my_spread(home) = -my_margin       (negative = home favored)
    edge = market_spread(home) - my_spread(home)
           (positive edge => market gives home more points than we do
            => value on the home side relative to the market)

No API key or install required. Endpoint is undocumented and may change;
spreads only populate close to game week.
"""

import csv
import json
import os
import sys
import urllib.request

from release_ratings import load_release_rows

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ENDPOINT = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
            "scoreboard?dates={year}&seasontype=2&week={week}")
REG_SEASON_WEEKS = 18


def load_ratings():
    out = {}
    path = os.path.join(DATA, "ratings.csv")
    for r in load_release_rows(path):
        out[r["team"]] = round(
            float(r["qb_value"] or 0)
            + float(r["off_value"] or 0)
            + float(r["def_value"] or 0),
            1,
        )
    return out


def load_hfa():
    hfa, default = {}, 1.5
    path = os.path.join(DATA, "hfa.csv")
    if os.path.exists(path):
        for r in csv.DictReader(open(path, newline="")):
            if r["team"] == "DEFAULT":
                default = float(r["home_field"])
            else:
                hfa[r["team"]] = float(r["home_field"])
    return hfa, default


def fetch_week(week, year):
    url = ENDPOINT.format(year=year, week=week)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def is_primetime(iso_utc):
    """Kickoff hour in US Eastern. Primetime ~ 8pm ET (Thu/Sun/Mon night).
    ESPN times are UTC; ET is UTC-4 (Sep-Nov, DST). 20:00 ET -> 00:00 UTC.
    Treat UTC hour >= 23 or <= 4 as a primetime (night) kickoff."""
    try:
        hh = int(iso_utc[11:13])
    except (ValueError, IndexError):
        return False
    return hh >= 23 or hh <= 4


def round_half(x):
    return round(x * 2) / 2


def parse_games(payload, ratings, hfa, default_hfa):
    games = []
    for e in payload.get("events", []):
        c = e["competitions"][0]
        comp = {t["homeAway"]: t["team"]["displayName"] for t in c["competitors"]}
        home, away = comp.get("home"), comp.get("away")
        if home not in ratings or away not in ratings:
            # name mismatch (e.g. relocation/abbrev) — skip rather than guess
            continue
        odds = c.get("odds") or []
        market = odds[0].get("spread") if odds else None  # home-relative
        details = odds[0].get("details") if odds else None
        ou = odds[0].get("overUnder") if odds else None

        prime = is_primetime(e.get("date", ""))
        base = hfa.get(home, default_hfa)
        eff_hfa = base + (0.5 if prime else 0.0)
        my_margin = ratings[home] - ratings[away] + eff_hfa
        my_spread = round_half(-my_margin)  # home-relative, neg = home favored

        edge = None
        if market is not None:
            edge = round(market - my_spread, 1)

        games.append({
            "date": e.get("date", ""), "prime": prime,
            "home": home, "away": away,
            "rh": ratings[home], "ra": ratings[away], "hfa": eff_hfa,
            "my_spread": my_spread, "market": market,
            "details": details, "ou": ou, "edge": edge,
        })
    return games


def fmt_spread(home, s):
    if s is None:
        return "(no line)"
    if s < 0:
        return f"{abbrev(home)} {s:g}"
    if s > 0:
        return f"{abbrev(home)} +{s:g}"
    return "PK"


ABBR = {
    "Buffalo Bills": "BUF", "Miami Dolphins": "MIA", "New England Patriots": "NE",
    "New York Jets": "NYJ", "Baltimore Ravens": "BAL", "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE", "Pittsburgh Steelers": "PIT", "Houston Texans": "HOU",
    "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Tennessee Titans": "TEN",
    "Denver Broncos": "DEN", "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC", "Dallas Cowboys": "DAL", "New York Giants": "NYG",
    "Philadelphia Eagles": "PHI", "Washington Commanders": "WAS", "Chicago Bears": "CHI",
    "Detroit Lions": "DET", "Green Bay Packers": "GB", "Minnesota Vikings": "MIN",
    "Atlanta Falcons": "ATL", "Carolina Panthers": "CAR", "New Orleans Saints": "NO",
    "Tampa Bay Buccaneers": "TB", "Arizona Cardinals": "ARI", "Los Angeles Rams": "LAR",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA",
}


def abbrev(name):
    return ABBR.get(name, name[:3].upper())


def print_table(games, week):
    print(f"\n  NFL Week {week} — My Spread vs. Market  "
          f"(edge = market − mine; |edge|≥1.5 flagged)\n")
    hdr = (f'  {"Matchup":<26}{"My Line":>12}{"Market":>12}'
           f'{"Edge":>7}  {"":<4}')
    print(hdr)
    print("  " + "-" * 64)
    for g in sorted(games, key=lambda x: -(abs(x["edge"]) if x["edge"] is not None else -1)):
        match = f'{abbrev(g["away"])} @ {abbrev(g["home"])}' + (" ★" if g["prime"] else "")
        mine = fmt_spread(g["home"], g["my_spread"])
        mkt = g["details"] or "(no line)"
        if g["edge"] is None:
            edge, flag = "  —", ""
        else:
            edge = f'{g["edge"]:+.1f}'
            flag = "<<" if abs(g["edge"]) >= 1.5 else ""
        print(f'  {match:<26}{mine:>12}{mkt:>12}{edge:>7}  {flag:<4}')
    print()


def write_html(games, week):
    rows = []
    for g in sorted(games, key=lambda x: -(abs(x["edge"]) if x["edge"] is not None else -1)):
        match = f'{g["away"]} @ {g["home"]}' + (" ★" if g["prime"] else "")
        mine = fmt_spread(g["home"], g["my_spread"])
        mkt = g["details"] or "(no line)"
        edge = "" if g["edge"] is None else f'{g["edge"]:+.1f}'
        cls = "big" if (g["edge"] is not None and abs(g["edge"]) >= 1.5) else ""
        rows.append(f"<tr class='{cls}'><td class='l'>{match}</td><td>{mine}</td>"
                    f"<td>{mkt}</td><td class='e'>{edge}</td></tr>")
    html = f"""<!DOCTYPE html><html><head><meta charset=utf-8>
<title>Week {week} Spreads</title><style>
body{{background:#0e1117;color:#e6edf3;font:15px -apple-system,Segoe UI,Roboto,sans-serif;}}
.wrap{{max-width:680px;margin:24px auto;padding:0 16px;}}
table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #283041;border-radius:10px;overflow:hidden;}}
th,td{{padding:9px 12px;text-align:right;border-bottom:1px solid #283041;}}
th{{background:#11161f;color:#8b949e;font-size:11px;text-transform:uppercase;}}
td.l,th.l{{text-align:left;}} td.e{{font-weight:700;}}
tr.big{{background:rgba(240,180,41,.12);}} tr.big td.e{{color:#f0b429;}}
h1{{font-size:22px;}} .sub{{color:#8b949e;font-size:13px;}}
</style></head><body><div class=wrap>
<h1>NFL Week {week} — My Line vs. Market</h1>
<div class=sub>Edge = market − my line. Highlighted = |edge| ≥ 1.5. ★ = primetime (home +0.5 HFA).</div>
<table><thead><tr><th class=l>Matchup</th><th>My Line</th><th>Market</th><th>Edge</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></body></html>"""
    out = os.path.join(HERE, "spreads.html")
    open(out, "w").write(html)
    print(f"  wrote {out}")


def collect_season(ratings, hfa, default_hfa, year):
    """Fetch every regular-season week; return {week: [games]}. Skips weeks
    that error or have no parseable games (e.g. schedule not posted yet)."""
    season = {}
    for wk in range(1, REG_SEASON_WEEKS + 1):
        try:
            payload = fetch_week(str(wk), year)
        except Exception as e:  # noqa: BLE001
            print(f"  week {wk}: fetch error ({e}); skipping")
            continue
        games = parse_games(payload, ratings, hfa, default_hfa)
        if games:
            season[wk] = games
    return season


def season_summary(season):
    total = sum(len(g) for g in season.values())
    priced = [g for wk in season.values() for g in wk if g["edge"] is not None]
    print("\n  " + "=" * 64)
    print(f"  SEASON SUMMARY — {len(season)} weeks, {total} games "
          f"({len(priced)} with a market line)")
    print("  " + "=" * 64)
    if not priced:
        print("  No market lines posted yet for any week.\n")
        return
    big = [g for g in priced if abs(g["edge"]) >= 1.5]
    print(f"  Games with |edge| >= 1.5: {len(big)}")
    print("\n  Top 15 edges of the season:\n")
    print(f'  {"Wk":>3}  {"Matchup":<18}{"My Line":>11}{"Market":>11}{"Edge":>7}')
    print("  " + "-" * 52)
    ranked = sorted(priced, key=lambda x: -abs(x["edge"]))[:15]
    for g in ranked:
        wk = next(w for w, gs in season.items() if g in gs)
        match = f'{abbrev(g["away"])} @ {abbrev(g["home"])}' + ("★" if g["prime"] else "")
        mine = fmt_spread(g["home"], g["my_spread"])
        mkt = g["details"] or "(no line)"
        print(f'  {wk:>3}  {match:<18}{mine:>11}{mkt:>11}{g["edge"]:>+7.1f}')
    print()


def write_season_html(season, year):
    blocks = []
    for wk in sorted(season):
        rows = []
        for g in sorted(season[wk],
                        key=lambda x: -(abs(x["edge"]) if x["edge"] is not None else -1)):
            match = f'{g["away"]} @ {g["home"]}' + (" ★" if g["prime"] else "")
            mine = fmt_spread(g["home"], g["my_spread"])
            mkt = g["details"] or "(no line)"
            edge = "" if g["edge"] is None else f'{g["edge"]:+.1f}'
            cls = "big" if (g["edge"] is not None and abs(g["edge"]) >= 1.5) else ""
            rows.append(f"<tr class='{cls}'><td class='l'>{match}</td><td>{mine}</td>"
                        f"<td>{mkt}</td><td class='e'>{edge}</td></tr>")
        blocks.append(f"<h2>Week {wk}</h2><table><thead><tr><th class=l>Matchup</th>"
                      f"<th>My Line</th><th>Market</th><th>Edge</th></tr></thead>"
                      f"<tbody>{''.join(rows)}</tbody></table>")
    html = f"""<!DOCTYPE html><html><head><meta charset=utf-8>
<title>{year} Spreads — Full Season</title><style>
body{{background:#0e1117;color:#e6edf3;font:15px -apple-system,Segoe UI,Roboto,sans-serif;}}
.wrap{{max-width:680px;margin:24px auto;padding:0 16px;}}
table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #283041;border-radius:10px;overflow:hidden;margin-bottom:22px;}}
th,td{{padding:8px 12px;text-align:right;border-bottom:1px solid #283041;}}
th{{background:#11161f;color:#8b949e;font-size:11px;text-transform:uppercase;}}
td.l,th.l{{text-align:left;}} td.e{{font-weight:700;}}
tr.big{{background:rgba(240,180,41,.12);}} tr.big td.e{{color:#f0b429;}}
h1{{font-size:22px;}} h2{{font-size:16px;color:#f0b429;margin:18px 0 8px;}}
.sub{{color:#8b949e;font-size:13px;}}
</style></head><body><div class=wrap>
<h1>{year} NFL — My Line vs. Market (Full Season)</h1>
<div class=sub>Edge = market − my line. Highlighted = |edge| ≥ 1.5. ★ = primetime (home +0.5 HFA).</div>
{''.join(blocks)}</div></body></html>"""
    out = os.path.join(HERE, "spreads.html")
    open(out, "w").write(html)
    print(f"  wrote {out}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    want_html = "--html" in sys.argv
    week = args[0] if len(args) > 0 else "1"
    year = args[1] if len(args) > 1 else "2026"

    try:
        ratings = load_ratings()
    except ValueError as error:
        print(f"  {error}", file=sys.stderr)
        return 1
    hfa, default_hfa = load_hfa()

    if week.lower() == "all":
        print(f"  Fetching all {REG_SEASON_WEEKS} weeks of {year}...")
        season = collect_season(ratings, hfa, default_hfa, year)
        if not season:
            print("  No games parsed for any week (schedule not posted yet?).")
            return
        for wk in sorted(season):
            print_table(season[wk], wk)
        season_summary(season)
        if want_html:
            write_season_html(season, year)
        return

    try:
        payload = fetch_week(week, year)
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR fetching ESPN: {e}")
        sys.exit(1)
    games = parse_games(payload, ratings, hfa, default_hfa)
    if not games:
        print(f"  No games parsed for week {week}, {year} "
              "(no schedule posted yet, or all names mismatched).")
        return
    print_table(games, week)
    if want_html:
        write_html(games, week)


if __name__ == "__main__":
    raise SystemExit(main())
