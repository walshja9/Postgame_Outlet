# Postgame Outlet: ratings, forecasts and records

PGO publishes Sean McCabe's human NFL ratings alongside an independent experimental model, saved game predictions, straight-up and spread records, and a Fantasy preview. Shopify supplies the public site and commerce shell; the app and Forecast Lab are hosted by GitHub Pages.

Start with [season operations](docs/pgo-season-operations.md) for automatic updates, verification, locks and archives. See [Shopify hosting](SHOPIFY.md) for required assets and [the September 10 model update](docs/model-update-2026-09-10.md) for research findings.

## Separate inputs and products

| Product | Inputs and workflow |
|---|---|
| McCabe human ratings | `data/ratings.csv`, `data/qb_depth.csv`, `data/writeups/<ABBR>.md`, `data/config.csv`; reviewed components and analysis |
| McCabe edition history | `data/snapshots.json`; `snapshot.py` and the manual Publish edition workflow |
| PGO weekly model | `pgo_season.py`, `pgo_season_model.py`, frozen fitted coefficients and verified inputs; current pointer at `docs/evidence/season-2026/current.json` |
| PGO picks and grades | Saved weekly records, verified finals, `pgo_season_accuracy.py`, `pgo_ats.py` and fixed confidence allocation |
| Availability | Archived official reports/inactive lists and separate later context with matchup, player and source-time checks |
| Fantasy | Saved preview projections, scoring controls and dated availability annotations |
| Research | Frozen experiments in `research/` and linked evidence; distinct from the production model |

Editing McCabe's CSV does not edit PGO's fitted coefficients. PGO's current weekly model uses regular-season plus postseason history and advances verified inputs after complete weeks without automatically refitting coefficients. Current non-QB injury and replacement effects are context, not adopted numerical adjustments. The model remains experimental.

## Setup and checks

Use Python 3.12, matching CI:

```bash
python -m pip install -r requirements-pgo.txt
python -m unittest discover -s tests
```

The optional Excel export additionally needs `openpyxl`; the PGO web app does not. CI also runs the dedicated corrected-roster and defensive-depth research checks in `.github/workflows/update-board.yml`.

## Preview and publication

`python generate_site.py` writes a dated private McCabe preview under `output/ratings-preview/`. It is not the combined public app. Missing or unreviewed McCabe rows block generation; resolve their `needs_review` flags through editorial review.

The combined render uses the existing PGO/Fantasy panels and verified saved season state:

```bash
python pgo_comparison.py --refresh-mccabe
python pgo_forecast_lab.py
```

These write `docs/index.html` and `docs/forecast-lab.html`; they do not deploy by themselves. Preview changes in an isolated or ignored staging copy, then let the tested board workflow render and publish from the admitted source. Do not use `generate_site.py --output docs/index.html` for a combined release: that path omits the complete PGO/Fantasy enrichment.

- `update-board.yml` tests source, admits permitted newer mutable season data, renders and requests deployment.
- `update-season.yml` captures verified sources, grades finals and advances eligible weekly editions.
- `publish-edition.yml` saves a named McCabe edition and refreshes the app through the tested-source publication pattern.

`python pgo_season.py` verifies and summarizes the saved state without capturing sources. `python pgo_season.py --refresh` is a separate writing operation: it captures actual feeds, archives state and can issue/revise unlocked forecasts. Prefer the canonical season workflow for production captures.

Publish required `docs/` assets together, respecting `_config.yml` archive exclusions. Verify CI, the actual Pages build, public bytes and the Shopify embed. A source push alone is not a deployment receipt.

## Meaning of the numbers

McCabe's rating is the sum of his QB, non-QB offense and defense components. His prior-year column is a reference, not an automatic blend. The human board's Methodology tab describes these judgments.

For the current PGO model, subtracting the opponent's rating gives the neutral-site, equal-rest margin. Venue and rest adjustments produce the game margin. Expected team scores split the scoring-total estimate using that margin; their sum and difference reconcile. These averages are not exact-score promises.

Straight-up records grade who won. Sportsbook ATS records grade the saved handicap and keep pushes, missing quotes and no-edge choices separate. PGO's own line has an exceeded/matched/below check; that is not a sportsbook record or a measure of closeness. Expected pool points equal fixed confidence points times the selected team's win probability and are not NFL scoreboard points.

## Archives and experiments

Saved forecasts, lines, source clocks and grades remain auditable. Late entries cannot become pregame probability evidence. Earlier PGO v0/v1 and corrected editions are historical evidence; their scripts are not the current operating procedure. Do not rerun or overwrite frozen research attempts during routine publishing. The penalty and alternative-weight studies failed their improvement screens; updating totals remains a separate candidate. Historical results and software tests do not promote a model.
