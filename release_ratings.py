"""Release-only reads for ratings-derived public artifacts."""

import csv


def load_release_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    flagged = [
        row.get("team", "(unnamed row)")
        for row in rows
        if (row.get("needs_review") or "").strip().upper() == "Y"
    ]
    if flagged:
        raise ValueError(
            "Release blocked: needs_review=Y for " + ", ".join(flagged)
        )
    return rows
