# PGO Matchup Comparison Design

## Goal

Create a private, all-scheduled-games matchup view that compares three separate
numbers for each NFL game:

1. McCabe's implied line from `data/ratings.csv` and the existing home-field
   adjustment.
2. The independent PGO shadow fair line from a frozen PGO ratings artifact.
3. The sourced ESPN market line, when one is available.

The output is analytical and preview-only. It must not blend the numbers, alter
McCabe's ratings, or change the public Pages artifact.

## Scope and non-goals

- Include every scheduled game returned for the requested week or season.
- Keep games whose market line is missing; show the market and both edges as
  unavailable rather than estimating them.
- Treat the PGO model as experimental/HOLD unless its supplied receipt says
  otherwise. The view is private regardless of model status.
- Do not use market data as a PGO model input.
- Do not add Shopify, GitHub Pages, scheduled refresh, database, or new
  third-party dependency work.
- Do not replace the existing McCabe-versus-market `spreads.py` output.

## Approaches considered

### Extend `spreads.py`

Add a second rating map and extra columns to the existing script. This is the
smallest line count, but it changes a working McCabe-versus-market command and
couples the new experimental artifact to its existing CLI.

### Add a private adapter (recommended)

Create `pgo_matchup_comparison.py` that reuses `spreads.fetch_week`,
`spreads.parse_games`, `spreads.load_ratings`, and the HFA helpers. It calls the
existing parser once for each rating map, joins on kickoff/home/away, and
renders a separate private HTML preview. Existing behavior stays unchanged.

### Build a new service or frontend

This adds deployment and state-management surface without solving a current
need. It is explicitly out of scope.

## Data flow

1. Load McCabe ratings and HFA from the existing `data/` files.
2. Load the PGO ratings CSV supplied by `--pgo-ratings` (default:
   `research/pgo_v1/ratings_2026_preseason.csv`) and its sibling
   `backtest.json` receipt. A v2 artifact may be selected explicitly. Require
   32 current teams, finite headline ratings, a consistent `as_of`, and an
   experimental or validated status label.
3. Fetch the requested ESPN scoreboard payload through the existing
   proxy-friendly fetch helper. Record one UTC capture timestamp and the exact
   request URL as market provenance.
4. Derive both home-relative model lines with the existing convention:

   ```text
   margin = home_rating - away_rating + HFA
   line = -margin       # negative means home favored
   edge = market_line - model_line
   ```

5. Join the two parser results by event date and the canonical home/away team
   names. Reject duplicate or unmatched events rather than silently pairing
   different games.
6. Write only to
   `output/pgo-matchup-preview/<date>/index.html` unless the caller supplies a
   path under `output/`.

## Preview contract

Each row shows matchup, kickoff, McCabe line, PGO line, market line, McCabe
edge, PGO edge, and a market-source/capture note. Lines are explicitly labeled
as applying to the named matchup, not to either team's league rank.

The page header states that McCabe, PGO, and the market remain independent.
The PGO status, artifact `as_of`, and HOLD reason are visible in the private
preview. A missing market line renders `Unavailable`; it never becomes zero or
an inferred edge.

## Validation and failure behavior

- Invalid or missing PGO artifacts fail closed before any HTML is written.
- Unknown team abbreviations, duplicate events, mismatched joins, non-finite
  ratings, and malformed market spreads are errors.
- A missing ESPN odds object is not an error; it produces an unavailable market
  cell for that game.
- Unit tests cover model-line algebra, team mapping, event joins, unavailable
  markets, receipt/status labeling, and output-path containment.
- The existing full test suite remains the release gate.

## Acceptance criteria

- A private preview can render all requested games from a fixture payload with
  all three columns present where data exists.
- McCabe and PGO lines are numerically independent and are never blended.
- Market edges use the same home-relative sign convention as `spreads.py`.
- Missing market data is visible and non-certifying.
- No `docs/index.html`, Shopify asset, or live deployment changes occur.
