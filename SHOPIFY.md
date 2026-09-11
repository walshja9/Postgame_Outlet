# PGO hosting and Shopify

The live Power Ratings page at `https://postgameoutlet.com/pages/power-ratings` embeds `https://walshja9.github.io/Postgame_Outlet/index.html`. Shopify supplies native pages, navigation, articles and commerce. The repository supplies the app and Forecast Lab. This site is already live.

## Required assets

The app is no longer one self-contained HTML file. Deploy the docs site with its existing `_config.yml` exclusions, including:

- `index.html`: McCabe ratings, PGO model, saved games and Fantasy preview.
- `forecast-lab.html`: explanations, accuracy, research and archives.
- `pgo-theme.css`: shared styling.
- `evidence/season-2026/current.json`: saved-state clock for open-page freshness checks.
- Linked methodology and evidence at their existing relative paths.

Large new raw-source, availability-v2 and runs-v2 archives are excluded from Pages and linked through the public Git repository. Preserve their paths/hashes and older evidence URLs. Copying only index.html omits styling and records.

## Generate and deploy

Follow [README](README.md) and [season operations](docs/pgo-season-operations.md). Combined render commands:

```bash
python pgo_comparison.py --refresh-mccabe
python pgo_forecast_lab.py
```

These write local pages. Board, season and named-edition workflows commit output and explicitly request Pages builds. Source tests precede the board/edition publishing lock; the publication guard rejects untested intervening source changes. A push alone does not prove deployment.

`python generate_site.py` produces a private McCabe preview, not the complete public app.

## Embed behavior

Keep the iframe title `NFL Power Ratings` and existing host/child message bridge. The child posts its measured height; the Shopify wrapper resizes the iframe and sends the visible viewport slice so team drawers remain accessible while scrolling. Initial fixed height is a loading fallback.

When editing this bridge, validate message origin/source and finite, bounded sizing values. Preserve the reviewed implementation; do not paste the full generated app into Shopify's rich-text editor. Shopify page copy and the hosted app are separate publication surfaces.

## Verification

Confirm source CI and the actual Pages build. Compare fetched assets with committed Git blob bytes, not Windows working-copy bytes that may use different line endings. Check Power Ratings and Forecast Lab on desktop and phone, including tabs, game details, links and iframe scrolling. Save the observed commit and state clock.

Keep Methodology/Accountability copy aligned with current model scope, grades and limitations. Do not infer complete injury adjustment, exact-time automation or predictive accuracy from a successful deployment.
