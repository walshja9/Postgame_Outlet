# NFL Power Ratings (2026 season)

A roster-based, points-denominated power-rating system. Every team's rating is
expressed in **points vs. a league-average team (0.0)** and is the straight sum
of its components:

```
Team Rating = QB + Offense(non-QB) + Defense   (+ Coaching + Scheme + Edge, future)
```

All numbers live in `data/ratings.csv` — that is the one file you edit. Three
scripts read it and produce the artifacts below. Edit the CSV, re-run the
script(s), done.

## Files

```
data/
  ratings.csv      THE file you edit. 32 teams: QB/Off/Def values + names + notes.
  qb_depth.csv     Backup QBs (2nd/3rd string) with values. Feeds the QB Depth tab.
  prior_2025.csv   Last season's ENDING ratings (reference prior).
  hfa.csv          Home-field advantage: base 1.5, per-team bumps. Used by spreads.py.
  config.csv       Home-field default, season label.
  writeups/        Optional per-team analysis: one <ABBR>.md per team (e.g. SEA.md).

build_ratings.py   -> NFL_Power_Ratings_2026.xlsx  (workbook: ratings, QBs, depth, projections)
generate_site.py   -> output/ratings-preview/YYYY-MM-DD/index.html (private preview)
spreads.py         -> terminal + spreads.html       (schedule + my line vs. ESPN market line)
```

## Commands

```bash
cd ~/nfl-power-ratings

# After editing data/ratings.csv, regenerate whichever you want:
python3 build_ratings.py          # the Excel workbook
python generate_site.py
# -> output/ratings-preview/YYYY-MM-DD/index.html (dated private preview)

# Production output is explicit and is run only after preview approval:
python generate_site.py --output docs/index.html

# Spreads vs. the market (free, unofficial ESPN JSON API — no key/install):
python3 spreads.py 1              # one week
python3 spreads.py all            # full 18-week season + summary
python3 spreads.py all 2026 --html # also write spreads.html

# Open output/ratings-preview/YYYY-MM-DD/index.html in your browser.
```

Generation stops if any row in `data/ratings.csv` has `needs_review=Y`. Clear
those flags through editorial review; never bypass the gate. The default command
writes a private preview and does not replace the GitHub Pages artifact.

## Team write-ups (click-to-expand on the site)

Every team row on `index.html` expands (click it) to show a QB/Off/Def bar
breakdown plus your analysis. The analysis comes from `data/writeups/<ABBR>.md`
— plain markdown (`##` headings, `**bold**`, `- bullets`, paragraphs). If a team
has no write-up file yet, the row falls back to the one-line `notes` from
`ratings.csv` and shows a hint with the filename to create.

```bash
# Team abbreviations match the chips (BUF, SEA, KC, LAR, ...). To add one:
$EDITOR data/writeups/BUF.md      # write markdown
python3 generate_site.py          # re-embed into index.html
```

Two examples ship already: `data/writeups/SEA.md` and `KC.md`.

## Publishing to postgameoutlet.com

See `SHOPIFY.md` — host the generated `index.html` statically (GitHub Pages /
Netlify drop) and embed it in a Shopify page via `<iframe>` (Shopify strips the
inline `<script>`/`<style>` the site needs, so pasting raw HTML won't work).

## Rating conventions (how the numbers were calibrated)

- **QB**: the dominant lever. 0.0 ≈ ~QB16-18 (a middling starter). Elite +5 to +6.5,
  worst starter floor ~ -2.5. Backups: 2nd string -2.5 to -4.5, 3rd string -4.5 to -6.0.
  QB value is *expected 2026 value*, so injury uncertainty is priced in (e.g. Mahomes
  carries an injury haircut despite being the most talented).
- **Offense / Defense** (non-QB units): centered at average — ~16 teams above 0.0 on
  each, almost all within +/-1.0. Driven by the 2026 FA/draft roster movement; the
  `notes` column in ratings.csv records the key adds/losses behind each number.
- **Spread model** (spreads.py): `my_margin(home) = rating_home - rating_away + HFA`,
  where `HFA = per-team base (default 1.5) + 0.5 for a primetime home game`.
  `my_spread = -my_margin` (negative = home favored). `edge = market - my_spread`;
  |edge| >= 1.5 is flagged.

## The prior / blend (history)

The 2026 preseason numbers were sanity-checked against `prior_2025.csv` (last
season's ending ratings) — injury-deflated finishers (KC/CIN/BAL, whose QBs were
hurt) were trusted toward the roster build, hot finishers (SEA) toward the prior.
The displayed Rating is now the straight component sum, NOT a blend; the prior is
kept only as a reference column on the website.

## Notes & caveats

- ESPN endpoint is undocumented/unofficial; spreads only populate close to game week.
  Early-summer lines are placeholders — don't over-read specific edges yet.
- If one or two teams dominate the season-long edge list, that usually means YOUR
  rating on those teams is the outlier, not the market. (As of last build: GB and
  NYJ recurred — worth a sanity check when real lines firm up.)
- Coaching / Scheme / Edge columns exist in ratings.csv but are still 0.0 — the
  natural next layer.
- Eventual goal: embed the ratings (and maybe spreads) table into the Shopify store
  (postgameoutlet.com), built standalone first.
```
