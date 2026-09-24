# PGO accuracy, injury research and website follow-through

User chose all three workstreams on September 22. The existing isolated
checkout is based on `39f5e05ff96b20aec123c2b3591265c5e2623be3`; its source
matches the completed Week 3 release. Routine design choices are delegated
as recorded in `2026-09-12-pgo-source-refresh-and-readiness.md`.

## Accuracy

- Replay the hash-verified saved state and captured finals/quotes through
  `pgo_season_accuracy.py`, `pgo_weekly_review.py` and the existing market,
  totals and weights monitors. Report metric-specific eligible counts and
  same-game comparisons for Weeks 1 and 2.
- Preserve the registered end-of-season decision rules. Current results are
  descriptive; no fitting, tuning, promotion or forecast reconstruction.
- Retain executable audit, source hashes, game diagnostics and a concise
  assessment under `C:/Users/Alex/outputs/pgo-all-three-20260922/accuracy/`.

## Injury research

- Replay the unchanged September 17 research adapter against current
  archive readers, retaining dependency hashes and the stale-dependency
  failure. Inspect earlier pre-lock archives as well as current state.
- Separate source-complete exposure diagnostics from formal prospective
  model eligibility, which additionally requires an approved protocol.
- Preserve unknown versus zero, official medical OUT membership, identity,
  complete reports and genuine pre-T60 custody. No injury-to-points fitting
  or production wiring. Retain new evidence under the sibling `injury/`.
- Repair the demonstrated empty-availability placeholder bug separately on
  `codex/pgo-nonqb-empty-availability-20260922`, based on `d2f2a4e`, in the
  existing `Postgame_Outlet-record-style-repair-20260916` worktree. The
  production updater legitimately retains `availability={}` before a first
  report. `_availability_candidates` must skip exactly `{}` rather than
  indexing its nonexistent `checked_at`. Nonempty malformed observations
  still fail closed. Cover empty forecast/context placeholders and missing
  clocks in `research/pgo_nonqb_scores_20260917/test_adapter.py`; preserve the
  original failing replay and run a new NYG-LA diagnostic with current readers.

## Website

Live desktop/mobile review found Accuracy hidden under More and the latest
completed review more than 5,000 CSS pixels below the mobile PGO introduction.

- In `pgo_season_view.render_season`, replace the primary Winner records
  navigation entry with Accuracy; retain Winner records under More. Keep
  four primary links, existing anchors and native navigation behavior.
- Add the newest verified completed weekly review near the PGO introduction
  only when `weekly_reviews` is nonempty. The sole production caller passes
  `pgo_weekly_review.links()`, which verifies reports and orders them by week.
  Reuse `_sources` for link validation and escaping; do not invent a URL.
- List completed weekly reviews newest first in the accuracy section.
- Browser checking also reproduced a live iframe navigation defect: following
  a completed-review link leaves Shopify scrolled below the short report,
  displaying a blank viewport. Add a fixed `standalone=False` keyword to
  `_sources`; when enabled it emits `target="_top"`. Enable it only for both
  weekly-review placements. Preserve ordinary source links and all archived
  report bytes. Verify full-tab report navigation and browser Back.
- Update the existing navigation regression and add a focused regression
  covering latest/empty reviews, safe links and unchanged input state.
- Run `python -m unittest tests.test_pgo_season_view tests.test_pgo_weekly_review`.
  Render a local preview using current saved state and existing styles, then
  inspect 390px and desktop layouts, anchor behavior and both review links.
  Preserve generated public files and archived report bytes during review.

## Completion

Independently review the bounded diff and source-backed conclusions. Keep
all original forecasts, grades, model coefficients, human ratings, source
archives, frozen experiments and unfavorable results unchanged. Record local
verification separately from any later publication.

## Verified outcomes

- Accuracy audit: 35 captured schedule/final/quote sources verified. PGO is
  19-12 on 31 eligible main forecasts. On 30 identical saved-market games,
  PGO is 18-12 versus 21-9 for the market favorite; margin MAE is 12.2452
  versus 11.6333. No scoring defect or supported weight change was found.
  The formal weights study has only 16 timing-screened Week 2 pairs, far
  short of its end-of-season 150-game/12-week evidence floor. Full assessment:
  `C:/Users/Alex/outputs/pgo-all-three-20260922/accuracy/REPORT.md`.
- Injury replay: 1,105 archived states support 2/16 complete Week 1 and 6/16
  complete Week 2 post-lock diagnostics; all 16 Week 3 games await qualifying
  sources. The reader repair admits NYG-LA's real timely report, but missing
  dated historical membership for Kamren Kinchens correctly keeps that game
  blocked. Fifteen adapter tests and independent review passed. Initial and
  corrected receipts remain separate. Full assessment:
  `C:/Users/Alex/outputs/pgo-all-three-20260922/injury/ASSESSMENT.md`.
- Website source: 38 focused tests passed on Python 3.12.10, including the
  reproduced navigation/iframe failures; independent review passed. Public
  generated HTML, CSS, current pointer and existing weekly reports retain
  their before-change hashes. The combined local preview is under ignored
  `output/site-review-20260922/`; it uses the pinned saved state, so its clock
  warnings must not be mistaken for a new live-site freshness audit.
  Desktop/390px checks passed, including primary Accuracy, both weekly
  reports, standalone navigation from a tall iframe, report Back and browser
  Back. Evidence: `C:/Users/Alex/outputs/pgo-all-three-20260922/website/WEBSITE-REVIEW.md`.

These changes are local. No new model fitting, production integration,
public deployment or saved-evidence rewrite occurred in this task.
