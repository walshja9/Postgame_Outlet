# Handoff — NFL Power Ratings

This repository owns the independent ratings data, snapshots, writeups, and
interactive ratings artifact. Shopify owns the public site shell, navigation,
articles, products, cart, and checkout. See `README.md` and `SHOPIFY.md` for the
full workflow.

## Source of truth

Editable ratings content lives under `data/`:

- `data/ratings.csv` — 32 teams, component values, notes, and the editorial gate
- `data/writeups/<ABBR>.md` — team analysis
- `data/qb_depth.csv`, `data/hfa.csv`, and `data/config.csv` — supporting inputs
- `data/snapshots.json` — append-only published-edition history and corrections

Every release row must have `needs_review=N`. Missing, unknown, or `Y` values
block generation and snapshots.

## Preview workflow

```bash
python generate_site.py
```

The default command writes a dated private artifact under
`output/ratings-preview/YYYY-MM-DD/index.html`. It does not change the GitHub
Pages file or Shopify. Review that artifact before any release command.

After explicit release approval, generate the approved public artifact with an
explicit destination such as:

```bash
python generate_site.py --output docs/index.html
```

Do not hand-edit generated HTML. Edit the source data or writeups, regenerate,
and commit the reviewed source and artifact together.

## Requirements

The ratings site and snapshot tools use the Python standard library. `openpyxl`
is needed only for the optional Excel workbook.
