#!/usr/bin/env python3
"""
Freeze the current power ratings under a week label so the website can show
historical snapshots in its dropdown.

Usage:
    python3 snapshot.py "Week 1"        # save current ratings as "Week 1"
    python3 snapshot.py "Week 1" --force  # overwrite an existing label
    python3 snapshot.py --list          # list saved snapshots
    python3 snapshot.py --remove "Week 1"  # delete a snapshot

Snapshots are stored in data/snapshots.json as {label: [team dicts]}, newest
last. After saving, re-run generate_site.py to refresh index.html.
"""

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SNAP = os.path.join(DATA, "snapshots.json")
INJURY_DEFLATED = {"Kansas City Chiefs", "Cincinnati Bengals", "Baltimore Ravens"}


def load_prior():
    path = os.path.join(DATA, "prior_2025.csv")
    if not os.path.exists(path):
        return {}
    return {r["team"]: float(r["end_2025_rating"])
            for r in csv.DictReader(open(path, newline=""))}


def snapshot_current():
    prior = load_prior()
    teams = []
    for r in csv.DictReader(open(os.path.join(DATA, "ratings.csv"), newline="")):
        qb = float(r["qb_value"] or 0)
        off = float(r["off_value"] or 0)
        dfn = float(r["def_value"] or 0)
        p = prior.get(r["team"], "")
        teams.append({
            "team": r["team"], "conf": r["conf"], "div": r["division"],
            "qb_name": r["qb_name"], "qb": qb, "off": off, "def": dfn,
            "prior": p if p != "" else "",
            "rating": round(qb + off + dfn, 1),
            "injury": r["team"] in INJURY_DEFLATED,
        })
    return teams


def load_snaps():
    if os.path.exists(SNAP):
        return json.load(open(SNAP))
    return {}


def save_snaps(snaps):
    json.dump(snaps, open(SNAP, "w"), indent=1)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "--list":
        snaps = load_snaps()
        if not snaps:
            print("  No snapshots saved yet.")
        for label in snaps:
            print(f"  {label:<16} ({len(snaps[label])} teams)")
        return
    if args[0] == "--remove":
        if len(args) < 2:
            print("  Usage: snapshot.py --remove \"Week 1\"")
            return
        snaps = load_snaps()
        if args[1] in snaps:
            del snaps[args[1]]
            save_snaps(snaps)
            print(f"  Removed '{args[1]}'. Re-run generate_site.py to refresh.")
        else:
            print(f"  No snapshot named '{args[1]}'.")
        return

    label = args[0]
    force = "--force" in args
    snaps = load_snaps()
    if label in snaps and not force:
        print(f"  '{label}' already exists. Use --force to overwrite.")
        return
    # If overwriting, drop and re-append so it keeps newest-last order.
    if label in snaps:
        del snaps[label]
    snaps[label] = snapshot_current()
    save_snaps(snaps)
    print(f"  Saved snapshot '{label}' ({len(snaps[label])} teams).")
    print("  Re-run: python3 generate_site.py   to update the website dropdown.")


if __name__ == "__main__":
    main()
