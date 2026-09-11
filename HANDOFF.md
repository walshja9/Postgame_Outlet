# PGO operator handoff

This repository owns McCabe's ratings/writeups, the independent PGO weekly model, saved game records, Fantasy preview, generated app and Forecast Lab. Shopify owns native public pages, navigation, articles and commerce.

Read [README](README.md), [season operations](docs/pgo-season-operations.md) and [Shopify hosting](SHOPIFY.md). Dated handoffs describe their checkpoints; live main and the verified season pointer determine current state.

## Routine operation

- McCabe inputs are in `data/ratings.csv`, `data/qb_depth.csv` and `data/writeups/`. Every release row must have `needs_review=N`; resolve unreviewed flags rather than bypassing them.
- PGO's current state is `docs/evidence/season-2026/current.json` plus its hash-verified archive. `python pgo_season.py` reads it. Source refresh writes a new state.
- Verified finals grade saved picks. A complete verified week plus available statistics advances inputs through frozen coefficients and produces the next board. Missing statistics retain the prior board with a reason.
- Availability and sportsbook lines can refresh until T-60. Later inactive context cannot revise locked forecasts. Non-QB injury/replacement context is not a fitted point adjustment.
- Public Fantasy remains a preview. New display annotations do not change saved projections or make it gradeable.

## Change and release

Use the existing isolated workspace, review source changes and run relevant regressions. Full CI uses Python 3.12 and `requirements-pgo.txt`; its workflows contain required commands.

The combined publisher is `python pgo_comparison.py --refresh-mccabe`, followed by `python pgo_forecast_lab.py`. Plain `generate_site.py` is a human ratings preview. Let the tested board or named-edition workflow publish; retain source admission and non-rebasing pushes. Deploy all required app assets together.

Verify the actual Pages deployment, public bytes and Shopify embed. Preserve issued forecasts, source archives, frozen research and experimental labels. Software and deployment checks do not establish predictive improvement.
