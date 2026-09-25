"""NFL game results, stats, and pick-grading for the McCabe Method.

Pulls final scores and box-score stats from ESPN's free JSON API and reads them
through the ratings lens:

  1. Pick grade vs. my spread  — did the McCabe number beat the market ATS?
  2. Luck / quality read        — yards vs. points, turnover margin, 3rd-down
                                  efficiency, and opponent rating.
  3. QB / team stat lines       — box-score detail behind each result.
  4. Adjustment signals         — flags (never auto-applies) teams whose result
                                  + stats suggest a rating tweak; Sean decides.

Stdlib only. Uses espn_api.fetch_json (proxy-robust UA handling) and the same
ratings/HFA loaders as spreads.py so the predicted spread matches the site.

CLI:
    python3 results.py 1              # week 1 of the configured season
    python3 results.py 1 2025        # week 1 of 2025 explicitly
    python3 results.py 1 --json      # machine-readable (for the agent)
"""

import json
import os
import sys

from espn_api import fetch_json
from release_ratings import load_release_rows

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

SCOREBOARD = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
              "scoreboard?dates={year}&seasontype=2&week={week}")
SUMMARY = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
           "summary?event={event}")


# ---- shared loaders (mirror spreads.py so predictions line up) --------------

def load_ratings():
    out = {}
    for r in load_release_rows(os.path.join(DATA, "ratings.csv")):
        out[r["team"]] = round(
            float(r["qb_value"] or 0)
            + float(r["off_value"] or 0)
            + float(r["def_value"] or 0), 1)
    return out


def load_hfa():
    import csv
    hfa, default = {}, 1.5
    path = os.path.join(DATA, "hfa.csv")
    if os.path.exists(path):
        for r in csv.DictReader(open(path, newline="")):
            if r["team"] == "DEFAULT":
                default = float(r["home_field"])
            else:
                hfa[r["team"]] = float(r["home_field"])
    return hfa, default


def load_config():
    import csv
    cfg = {}
    path = os.path.join(DATA, "config.csv")
    if os.path.exists(path):
        for r in csv.DictReader(open(path, newline="")):
            cfg[r["key"]] = r["value"]
    return cfg


def is_primetime(iso_utc):
    try:
        hh = int(iso_utc[11:13])
    except (ValueError, IndexError):
        return False
    return hh >= 23 or hh <= 4


def round_half(x):
    return round(x * 2) / 2


# ---- stats extraction -------------------------------------------------------

def _team_stat(team_block, key):
    for s in team_block.get("statistics", []):
        if s.get("name") == key:
            return s.get("displayValue")
    return None


def _third_down_pct(eff):
    """'7-14' -> 50.0 (percent), or None."""
    try:
        made, att = eff.split("-")
        att = int(att)
        return round(100.0 * int(made) / att, 0) if att else None
    except (ValueError, AttributeError, ZeroDivisionError):
        return None


def fetch_boxscore(event_id):
    """Return {home:{...}, away:{...}} team stats + QB lines, or {} on failure."""
    try:
        s = fetch_json(SUMMARY.format(event=event_id))
    except Exception:  # noqa: BLE001 — network is best-effort
        return {}
    bs = s.get("boxscore", {})
    out = {"home": {}, "away": {}}

    # team-level box score
    for tb in bs.get("teams", []):
        side = tb.get("homeAway")
        if side not in out:
            continue
        eff = _team_stat(tb, "thirdDownEff")
        out[side] = {
            "team": tb.get("team", {}).get("displayName"),
            "total_yards": _num(_team_stat(tb, "totalYards")),
            "yards_per_play": _num(_team_stat(tb, "yardsPerPlay")),
            "turnovers": _num(_team_stat(tb, "turnovers")),
            "third_down": eff,
            "third_down_pct": _third_down_pct(eff),
            "possession": _team_stat(tb, "possessionTime"),
            "qb": None,
        }

    # QB (top passer) per side, mapped via athlete's team
    side_by_team = {out[s].get("team"): s for s in ("home", "away") if out.get(s)}
    for pb in bs.get("players", []):
        team_name = pb.get("team", {}).get("displayName")
        side = side_by_team.get(team_name)
        if not side:
            continue
        for grp in pb.get("statistics", []):
            if grp.get("name") == "passing" and grp.get("athletes"):
                a = grp["athletes"][0]
                line = dict(zip(grp.get("labels", []), a.get("stats", [])))
                out[side]["qb"] = {
                    "name": a["athlete"]["displayName"],
                    "line": line,  # e.g. {'C/ATT':'26/41','YDS':'273','TD':'1','INT':'0','QBR':'59.3'}
                }
                break
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---- core: build graded results for a week ----------------------------------

def build_week(week, year, ratings, hfa, default_hfa, with_box=True):
    payload = fetch_json(SCOREBOARD.format(year=year, week=week))
    games = []
    for e in payload.get("events", []):
        c = e["competitions"][0]
        status = c.get("status", {}).get("type", {})
        comp = {t["homeAway"]: t for t in c["competitors"]}
        if "home" not in comp or "away" not in comp:
            continue
        home = comp["home"]["team"]["displayName"]
        away = comp["away"]["team"]["displayName"]
        hs = _num(comp["home"].get("score"))
        as_ = _num(comp["away"].get("score"))

        prime = is_primetime(e.get("date", ""))
        base = hfa.get(home, default_hfa)
        eff_hfa = base + (0.5 if prime else 0.0)

        rh = ratings.get(home)
        ra = ratings.get(away)
        my_spread = my_margin = None
        if rh is not None and ra is not None:
            my_margin = rh - ra + eff_hfa
            my_spread = round_half(-my_margin)  # home-relative, neg = home favored

        # market spread (home-relative)
        odds = c.get("odds") or []
        market = odds[0].get("spread") if odds else None

        final = status.get("completed", False)
        actual_margin = (hs - as_) if (final and hs is not None and as_ is not None) else None

        # ---- pick grading (ATS) ----
        pick = _grade_pick(my_spread, market, actual_margin)

        g = {
            "event_id": e.get("id"),
            "date": e.get("date", ""),
            "status": status.get("name"),
            "final": final,
            "prime": prime,
            "home": home, "away": away,
            "home_score": hs, "away_score": as_,
            "rating_home": rh, "rating_away": ra, "hfa": eff_hfa,
            "my_spread": my_spread,      # home-relative
            "market": market,
            "actual_margin": actual_margin,  # home - away
            "pick": pick,                # dict: my_side, mkt_side, result vs market & vs straight-up
            "box": None,
            "luck": None,
            "signals": [],
        }

        if final and with_box and e.get("id"):
            box = fetch_boxscore(e["id"])
            g["box"] = box
            g["luck"] = _luck_read(g, box, ratings)
            g["signals"] = _adjustment_signals(g, box, ratings)

        games.append(g)
    return games


def _grade_pick(my_spread, market, actual_margin):
    """Grade the McCabe pick ATS vs the market line, and straight-up.

    my_spread / market are home-relative (neg = home favored).
    actual_margin = home_score - away_score.
    """
    if actual_margin is None:
        return None
    out = {}
    # Straight-up: did my number pick the right winner?
    if my_spread is not None:
        my_pick_home = my_spread < 0  # I favor home
        home_won = actual_margin > 0
        out["su_correct"] = (my_pick_home == home_won) if actual_margin != 0 else None
    # ATS vs market: does the side my_spread disagrees with the market on cover?
    if my_spread is not None and market is not None:
        # home covers market if (actual_margin + market) > 0
        home_cover_margin = actual_margin + market
        if abs(home_cover_margin) < 1e-9:
            out["ats_result"] = "push"
        else:
            home_covered = home_cover_margin > 0
            # my lean vs market: I lean home if my_spread < market (I like home more than market)
            i_lean_home = my_spread < market
            if abs(my_spread - market) < 1e-9:
                out["ats_result"] = "no-edge"
            else:
                out["ats_result"] = "win" if (i_lean_home == home_covered) else "loss"
        out["edge"] = round(market - my_spread, 1)
    return out


def _luck_read(g, box, ratings):
    """Heuristic luck/quality read: yards-vs-points, turnover margin, opponent rating."""
    if not box or not box.get("home") or not box.get("away"):
        return None
    h, a = box["home"], box["away"]
    read = {}
    # turnover margin (home perspective)
    if h.get("turnovers") is not None and a.get("turnovers") is not None:
        read["to_margin_home"] = int(a["turnovers"] - h["turnovers"])  # + = home won TO battle
    # yards vs result: did the yardage winner also win the game?
    if h.get("total_yards") is not None and a.get("total_yards") is not None and g["actual_margin"] is not None:
        yards_margin_home = h["total_yards"] - a["total_yards"]
        read["yards_margin_home"] = int(yards_margin_home)
        # "lucky win": won the game but lost the yardage battle by a lot
        if g["actual_margin"] > 0 and yards_margin_home < -60:
            read["flag"] = "home won despite being out-gained (possible lucky win)"
        elif g["actual_margin"] < 0 and yards_margin_home > 60:
            read["flag"] = "away won despite being out-gained (possible lucky win)"
    # quality of competition: opponent rating
    read["opp_rating_for_home"] = ratings.get(g["away"])
    read["opp_rating_for_away"] = ratings.get(g["home"])
    return read


def _adjustment_signals(g, box, ratings):
    """Flag (never auto-apply) teams whose result+stats suggest a rating look.

    Conservative: only flags clear cases. Sean makes the call.
    """
    sig = []
    am = g.get("actual_margin")
    if am is None:
        return sig
    rh, ra = g.get("rating_home"), g.get("rating_away")
    my = g.get("my_spread")
    # Big miss vs my own number: predicted margin vs actual off by 2+ scores
    if my is not None:
        predicted_home_margin = -my
        if am - predicted_home_margin >= 14:
            sig.append(f"{g['home']}: beat my projection by {round(am - predicted_home_margin)}+ pts — look at raising")
        elif predicted_home_margin - am >= 14:
            sig.append(f"{g['home']}: fell short of my projection by {round(predicted_home_margin - am)}+ pts — look at lowering")
    # Blowout vs a quality opponent = quality signal
    if am >= 17 and ra is not None and ra >= 2.0:
        sig.append(f"{g['home']}: blew out a strong opponent ({g['away']} {ra:+.1f}) — quality win")
    if am <= -17 and rh is not None and rh >= 2.0:
        sig.append(f"{g['away']}: blew out a strong opponent ({g['home']} {rh:+.1f}) — quality win")
    return sig


# ---- rendering --------------------------------------------------------------

def print_week(games, week):
    print(f"\n=== NFL Results — Week {week} (RETROSPECTIVE) ===")
    print("Regraded using current ratings and fetched market lines; not an issued forecast or contemporaneous ATS record.\n")
    grades = {"win": 0, "loss": 0, "push": 0}
    for g in games:
        line = f"{g['away']} @ {g['home']}"
        if g["final"]:
            line = f"{g['away']} {int(g['away_score'])} @ {g['home']} {int(g['home_score'])}"
        else:
            line += f"  ({g['status']})"
        print(line)
        if g["my_spread"] is not None:
            mk = f"{g['market']:+.1f}" if g["market"] is not None else "n/a"
            print(f"    my line (home): {g['my_spread']:+.1f}   market: {mk}")
        p = g.get("pick") or {}
        if p.get("ats_result"):
            r = p["ats_result"]
            grades[r] = grades.get(r, 0) + 1
            su = p.get("su_correct")
            su_txt = "" if su is None else (" | SU ✓" if su else " | SU ✗")
            print(f"    pick vs market: {r.upper()} (edge {p.get('edge')}){su_txt}")
        lk = g.get("luck") or {}
        if lk.get("flag"):
            print(f"    ⚑ {lk['flag']}")
        if lk.get("to_margin_home") is not None:
            print(f"    turnover margin (home): {lk['to_margin_home']:+d} | "
                  f"yards margin (home): {lk.get('yards_margin_home','?'):+} ")
        for s in g.get("signals", []):
            print(f"    → signal: {s}")
        # QB lines
        box = g.get("box") or {}
        for side in ("away", "home"):
            qb = (box.get(side) or {}).get("qb")
            if qb:
                ln = qb["line"]
                print(f"      {qb['name']}: {ln.get('C/ATT','?')} {ln.get('YDS','?')}yds "
                      f"{ln.get('TD','?')}TD {ln.get('INT','?')}INT QBR {ln.get('QBR','?')}")
        print()
    w, l, pu = grades.get("win", 0), grades.get("loss", 0), grades.get("push", 0)
    if w or l or pu:
        print(f"Retrospective McCabe Method ATS vs market: {w}-{l}" + (f"-{pu} push" if pu else ""))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print("usage: python3 results.py <week> [year] [--json]")
        sys.exit(1)
    week = int(args[0])
    cfg = load_config()
    year = int(args[1]) if len(args) > 1 else int(cfg.get("season", "2026"))
    ratings = load_ratings()
    hfa, default_hfa = load_hfa()
    games = build_week(week, year, ratings, hfa, default_hfa, with_box=True)
    if as_json:
        print(json.dumps({"week": week, "year": year,
                          "grading_basis": "retrospective_current_ratings",
                          "grading_note": "Regraded using current ratings and fetched market lines; not an issued forecast or contemporaneous ATS record.",
                          "games": games}, indent=2))
    else:
        print_week(games, week)


if __name__ == "__main__":
    main()
