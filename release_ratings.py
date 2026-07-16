"""Release-only reads for ratings-derived public artifacts."""

import csv
import os
import tempfile


def load_release_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "needs_review" not in reader.fieldnames:
            raise ValueError("Invalid ratings schema: missing needs_review column")
        rows = list(reader)
    invalid = [
        (row.get("team") or "(unnamed row)", row.get("needs_review"))
        for row in rows
        if (row.get("needs_review") or "").strip().upper() not in {"Y", "N"}
    ]
    if invalid:
        names = ", ".join(
            f"{team} ({value!r})"
            for team, value in invalid
        )
        raise ValueError(
            "Invalid needs_review value for "
            + names
            + "; expected Y or N"
        )
    flagged = [
        row.get("team", "(unnamed row)")
        for row in rows
        if row["needs_review"].strip().upper() == "Y"
    ]
    if flagged:
        raise ValueError(
            "Release blocked: needs_review=Y for " + ", ".join(flagged)
        )
    return rows


def atomic_write_text(path, content):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=directory,
        prefix=f".{os.path.basename(path)}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
