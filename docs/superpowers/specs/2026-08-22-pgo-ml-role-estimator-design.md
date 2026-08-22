# PGO ML Role Estimator Design

**Status:** Approved design  
**Date:** August 22, 2026  
**Product:** Postgame Outlet NFL Power Ratings  
**Model:** Independent PGO role-estimation challenger

## 1. Goal

Add a small, learned role-estimation layer to PGO so current injury overlays
can estimate a player's expected healthy offensive or defensive snap share
when a sourced row does not provide one. The existing Huber-ridge team-margin
model remains the only final PGO predictor.

The role layer is research-only until it improves the locked team-margin
evaluation with a paired confidence interval whose lower bound is strictly
positive. PGO remains `Experimental model — HOLD` during this work.

## 2. Fixed validation contract

The following remain unchanged:

- The frozen historical source lock, cache, and model `as_of` boundary.
- The 2,127-game outer evaluation covering seasons 2018 through 2025.
- PGO v0 as the incumbent benchmark and scoring-margin MAE as the primary
  metric.
- Chronological training and validation folds.
- Huber-ridge loss for the final team-margin model.
- The existing deterministic bootstrap, seed `20260721`, gates, receipts,
  HOLD/PASS semantics, and public-release safeguards.
- Full-strength ratings, McCabe ratings, PGO model rows, and historical
  snapshots remain unchanged by the role layer.

No post-kickoff roster, injury, snap, or target row may influence a role
estimate or team prediction.

## 3. Source boundary

The role estimator consumes the existing normalized availability overlay
contract in `data/mccabe_availability.csv`. The overlay remains the source of
availability probability and source notes.

For complete current coverage, the upstream snapshot must process all 32 team
rosters and record zero-injury teams explicitly in its audit. It must provide
stable player identity, position, source timestamp, and a raw-source hash. No
missing team or player may be filled with a fabricated injury row.

Historical role training reuses the locked nflverse roster, injury, snap, and
player-history data already used by PGO. It does not add a second historical
source or refit the public model from current McCabe notes.

## 4. Learned role layer

Train two bounded regression models from historical pregame player states:

- healthy offensive snap-share estimate;
- healthy defensive snap-share estimate.

Training targets are the player's next observed snap share in a game where the
player was available. Injury status is not used to redefine the healthy-role
target. This keeps availability probability and role share separate.

Features are limited to information available before kickoff:

- position group;
- prior offensive and defensive snap shares;
- recent player usage and team usage;
- prior starter or rotation indicator;
- experience and prior participation;
- missingness indicators already supported by the PGO preprocessor.

Use the existing lightweight NumPy/Huber-ridge path where practical. Do not
add a new ML framework or a second end-to-end team-margin model. Clip predicted
shares to `[0, 1]` and fail closed when the required identity or historical
features are unavailable.

## 5. Overlay integration

For each current overlay player:

1. Preserve an explicit low/base/high role estimate supplied by the source.
2. Otherwise, use the learned healthy-role estimate for the selected role
   scenario.
3. Apply the sourced availability probability to the current-lineup view.
4. Never alter the full-strength view or historical PGO training rows.

The existing generic role prior remains a fallback only when the ML estimate
cannot be produced. The receipt must distinguish explicit source roles,
learned roles, and generic fallback roles.

## 6. Leakage and validation

Role models are fit inside each chronological outer fold using only player
states before that fold's validation games. The role estimate for a validation
game may not inspect that game's snap count, later injury revision, or later
roster row.

Measure both:

- held-out healthy-role snap-share MAE;
- paired team-margin MAE against the current challenger and PGO v0.

The role layer is not accepted because role MAE improves alone. It must also
improve the locked team-margin result, with the existing paired-bootstrap lower
bound strictly above zero. Otherwise retain the role layer as research-only
and leave public artifacts untouched.

## 7. Testing and verification

Focused tests must prove:

- role targets exclude unavailable player-weeks;
- each fold's role model excludes post-kickoff rows;
- explicit overlay roles override learned roles;
- learned roles fill missing fields without changing full-strength features;
- generic priors are used only when the learned estimate is unavailable;
- predicted shares are bounded and missing inputs fail closed;
- repeated fits and receipts are deterministic;
- source coverage audits all 32 teams without fabricating rows.

Before any promotion decision:

1. Run focused role and overlay tests.
2. Run the full test suite.
3. Run compilation and whitespace checks.
4. Run the locked historical comparison into a unique temporary directory.
5. Inspect role MAE, team-margin MAE, paired interval, coverage, and every
   existing gate.
6. Regenerate public files only if a separately authorized release passes all
   gates. Never promote or relabel PGO during this work.

## 8. Non-goals

This work does not blend PGO with McCabe, change the PGO target or incumbent,
rewrite historical snapshots, add recent-form features, scrape an undocumented
feed as a production dependency, change public wording, or deploy to Pages.
