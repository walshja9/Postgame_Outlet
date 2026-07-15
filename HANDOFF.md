# Handoff — NFL Power Ratings

You're taking this project over. Here's the 2-minute orientation; full detail is
in `README.md` and `SHOPIFY.md`.

## What it is
A roster-based NFL power-rating system. You edit plain data files, run a Python
script, and it spits out a standalone `index.html` (the ratings website), an
Excel workbook, and a spreads-vs-market page. No install, no API keys, no server.

## The one thing to understand: content lives in data files
All the editable **content** is under `data/`:
- `data/ratings.csv`      — the 32 teams' QB/Off/Def numbers, names, notes (THE main file)
- `data/writeups/<ABBR>.md` — the per-team analysis that expands on each row (BUF.md, SEA.md, ...)
- `data/qb_depth.csv`, `data/hfa.csv`, `data/config.csv` — supporting inputs

Edit those, then regenerate:
```bash
cd nfl-power-ratings
python3 generate_site.py      # rebuilds index.html from the data files
```
That's the whole content-editing loop. `index.html` is generated output — don't
hand-edit it; edit the data and re-run.

## Putting it on Shopify
`index.html` is fully self-contained. Host it statically somewhere (GitHub Pages
or Netlify — free), then embed that URL in a Shopify page via `<iframe>`. Shopify
strips the inline `<script>`/`<style>`, so pasting the raw HTML won't work — the
iframe is the way. Details in `SHOPIFY.md`.

## Sean stays in the content loop
Sean will keep editing content on his side by changing the same `data/` files and
re-running `generate_site.py`, then sending you the updated `index.html` (or the
changed data files) to re-publish. Keep `data/` as the source of truth so those
edits merge cleanly.

## Requirements
Python 3 with `openpyxl` (only needed for the Excel workbook):
```bash
pip3 install openpyxl
```
The website and spreads scripts use the standard library only.
