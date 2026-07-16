#!/usr/bin/env python3
"""
Freeze the current power ratings under a week label so the website can show
historical snapshots in its dropdown.

Usage:
    python snapshot.py "Week 1"
    python snapshot.py --list
    python snapshot.py --correct "Week 1" "Corrected opponent label; rating unchanged."

Snapshots are stored in data/snapshots.json and cannot be overwritten or removed.
Corrections are appended as disclosed notes without changing frozen rating rows.
"""

import csv
import json
import os
import sys
from datetime import datetime

from release_ratings import atomic_write_text, load_release_rows

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
    path = os.path.join(DATA, "ratings.csv")
    for r in load_release_rows(path):
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


def normalize_snapshot_entry(value):
    if isinstance(value, list):
        return {"published_at": "", "rows": value, "corrections": []}
    if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
        raise ValueError("Invalid snapshot entry: expected a row list or snapshot object")
    return {
        "published_at": value.get("published_at", ""),
        "rows": value["rows"],
        "corrections": list(value.get("corrections", [])),
    }


def load_snaps(path=SNAP):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_snaps(snaps, path=SNAP):
    atomic_write_text(path, json.dumps(snaps, indent=1, ensure_ascii=False) + "\n")


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def add_snapshot(snaps, label, rows, at=None):
    if label in snaps:
        raise ValueError(f"Snapshot '{label}' already exists; snapshots are immutable")
    snaps[label] = {
        "published_at": at or timestamp(),
        "rows": rows,
        "corrections": [],
    }


def add_correction(snaps, label, note, at=None):
    if label not in snaps:
        raise ValueError(f"No snapshot named '{label}'")
    note = note.strip()
    if not note:
        raise ValueError("Correction note cannot be empty")
    entry = normalize_snapshot_entry(snaps[label])
    entry["corrections"].append({"at": at or timestamp(), "note": note})
    snaps[label] = entry


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 0
    if args[0] == "--list":
        snaps = load_snaps()
        if not snaps:
            print("  No snapshots saved yet.")
        for label, value in snaps.items():
            entry = normalize_snapshot_entry(value)
            print(f"  {label:<16} ({len(entry['rows'])} teams)")
        return 0
    if args[0] == "--correct":
        if len(args) < 3:
            print('  Usage: snapshot.py --correct "Week 1" "Correction note"', file=sys.stderr)
            return 2
        snaps = load_snaps()
        try:
            add_correction(snaps, args[1], " ".join(args[2:]))
        except ValueError as error:
            print(f"  {error}", file=sys.stderr)
            return 1
        save_snaps(snaps)
        print(f"  Added disclosed correction to '{args[1]}'.")
        return 0
    if args[0].startswith("--"):
        print(f"  Unknown command: {args[0]}", file=sys.stderr)
        return 2

    label = args[0]
    snaps = load_snaps()
    try:
        add_snapshot(snaps, label, snapshot_current())
    except ValueError as error:
        print(f"  {error}", file=sys.stderr)
        return 1
    save_snaps(snaps)
    print(f"  Saved snapshot '{label}' ({len(snaps[label]['rows'])} teams).")
    print("  Re-run: python generate_site.py   to update the private preview.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
