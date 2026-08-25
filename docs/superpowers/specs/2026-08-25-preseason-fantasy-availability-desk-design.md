# Preseason Fantasy Availability Desk Design

**Status:** Draft for review; design direction approved
**Date:** August 25, 2026
**Product:** Postgame Outlet NFL model and Fantasy editorial preview
**Release boundary:** Local research and unpublished Shopify preview only

## 1. Decision

The first slice is one source-backed vertical path from preseason availability
evidence to a private Fantasy page. It will process all 32 NFL teams, preserve
the meaning of each official source, run only eligible rows through a temporary
PGO current-lineup shadow analysis, and use the reviewed evidence for a Dynasty
and DFS availability desk in the existing unpublished content-first theme.

This slice improves model-input integrity and gives readers a real fantasy
surface. It does not tune the PGO model, promote it, alter protected ratings or
prospective evidence, change the store, or publish anything live.

## 2. Goals

1. Prove that every NFL team was checked against a frozen official preseason
   source, including teams whose source lists no players or says that no formal
   report is available.
2. Preserve the difference between a formal injury status, a preseason
   non-participation decision, a reserve-list transaction, and an official news
   update.
3. Resolve each listed player to a stable GSIS ID before the evidence can reach
   model input or public-facing draft copy.
4. Produce a temporary overlay and coverage receipt whose row counts reconcile
   exactly with each other and with the frozen source ledger.
5. Verify that eligible availability evidence changes only the PGO
   current-lineup view while full-strength ratings remain unchanged.
6. Create a useful unpublished Fantasy page with separate Dynasty and DFS
   sections, named provenance, and a visible update time.
7. Remove the three reproducible unclosed-CSV warnings in the site generator.

## 3. Non-goals

- No PGO feature, coefficient, hyperparameter, loss, gate, or evaluation-window
  change.
- No attempt to force `PASS`; `Experimental model — HOLD` remains the required
  label without a new genuine PASS receipt.
- No player projection model, start/sit optimizer, league sync, waiver engine,
  or lineup assistant.
- No inference that an unlisted player or a team without a formal report is
  healthy.
- No use of unofficial aggregators when an official club or league source is
  unavailable.
- No rewrite of the July 16 historical comparison or July 21 prospective lock.
- No live Shopify edit, theme publication, navigation change, analytics change,
  GitHub push, Pages deployment, or store modification.
- No automated scraper. The first snapshot is manually reviewed because the
  official preseason sources are heterogeneous and this is a one-cycle proof.

## 4. Frozen source ledger

The snapshot is a JSON object with a timezone-bearing capture timestamp,
exactly the current 32 normalized team abbreviations, one official coverage
record per team, and zero or more player records.

Each team coverage record contains:

- normalized team abbreviation;
- official source URL;
- source publication or update timestamp when the source supplies one;
- source kind: `formal_injury_report`, `preseason_availability_list`,
  `reserve_list`, `official_news`, or `no_formal_report`;
- target preseason game when the source is game-specific;
- a short factual coverage note.

Each player record contains the team, GSIS ID, displayed name, position,
injury text when supplied, the source's exact practice/game/availability
language, and the matching team source reference. Duplicate `(team, gsis_id)`
records fail unless the snapshot explicitly retains multiple source events and
selects one deterministic latest record before import.

`no_formal_report` is evidence that the team was checked. It is never evidence
that the roster is healthy. A missing team coverage record is a hard stop.

The snapshot is written under `output/` during initial verification. Its exact
bytes receive a SHA-256 recorded in the generated coverage receipt. It is not
copied into `data/` or committed as canonical evidence in this slice.

## 5. Eligibility and model semantics

Source meaning is preserved before any probability is assigned.

For this shadow, decision time `T` is the frozen snapshot's capture timestamp.
A row is model-eligible only when the official evidence was visible by `T` and
describes availability that applies at `T`; later revisions cannot flow backward.

- Formal report rows may use the existing fail-closed practice/game-status
  mapping in `pgo_challenger.availability_probability`.
- An explicit current reserve-list placement may map to unavailable only when
  the official source directly identifies that placement and the model as-of
  falls within it.
- A preseason availability list, healthy veteran rest decision, or official
  news update remains editorial evidence. It does not become a regular-season
  injury probability.
- Unknown or conflicting language is rejected rather than guessed.

The generated overlay retains the existing PGO availability CSV schema. The
coverage receipt additionally records all 32 team sources, per-team eligible
overlay counts, excluded editorial-only counts, exclusion reasons, total source
players, total overlay players, and the raw snapshot hash.

The authoritative overlay loader must reject duplicate team coverage, unknown
teams, timestamp disagreement, missing or extra per-team count keys, negative
or non-integer counts, total-count disagreement, and any mismatch between the
coverage receipt and actual overlay keys. This closes the current gap where a
receipt can assert 32-team processing without reconciling its row counts to the
overlay it accompanies.

## 6. Shadow model run

The importer writes only temporary outputs under `output/`. The PGO challenger
then runs with the frozen source timestamp, locked historical sources, the
temporary overlay, and its coverage receipt. A statistical `HOLD` is a valid
result; an integrity or source failure is `BLOCKED`.

The existing MAE, comparison baseline, confidence-interval gate, and historical
folds stay locked. This shadow evaluates a new availability snapshot, not a new
model candidate, and therefore cannot trigger tuning or metric selection.

Verification compares the shadow result with the protected baseline and
requires:

- numerically identical full-strength values at unrounded precision;
- current-lineup changes only for matched, model-eligible availability rows;
- every overlay GSIS ID matching the current roster;
- explicit role estimates preceding learned estimates, which precede generic
  priors;
- finite ratings, probabilities, role shares, and adjustments;
- unchanged July 16 comparison history, July 21 prospective evidence, checked-in
  overlay, checked-in research receipts, and `docs/index.html`;
- unchanged `HOLD`/`EXPERIMENTAL` status unless an independently reviewed PASS
  receipt genuinely satisfies the existing gate.

No shadow result is promoted in this slice.

## 7. Fantasy preview

The existing hash-verified content-first Shopify package is the starting point,
not a new theme. Before editing, obtain a fresh duplicate-theme capture when
Shopify access is available. If access remains unavailable, produce only a new
local review package and record that its commerce baseline is the older captured
theme.

The unpublished `/pages/fantasy` preview contains:

1. a concise preseason availability desk with source/capture time and a plain
   statement that team coverage does not mean every absence is an injury;
2. a Dynasty section focused on durable role or value implications;
3. a DFS section focused on the named preseason slate and clearly separated
   from regular-season expectations;
4. links to methodology and accountability material;
5. merchandise only after the analysis, using the existing "From the Outlet"
   supporting treatment.

The page uses the approved byline `PGO Editorial Staff`. It does not call the
PGO team-rating model a fantasy model, does not expose shadow ratings as
certified predictions, and does not display an empty tool interface.

## 8. Site-generator hardening

`generate_site.load_prior` and `generate_site.load_qbs` currently leave three
CSV handles for `prior_2025.csv`, `ratings.csv`, and `qb_depth.csv` to garbage
collection. Replace those direct `open(...)` expressions with the existing
context-manager pattern already used elsewhere in the file. Add one regression
check that records `ResourceWarning` while loading both paths and fails if any
unclosed file warning is emitted.

No generator refactor, new helper, dependency, or framework is warranted.

## 9. Failure behavior

Stop without producing an accepted shadow package when any team lacks an
official coverage record, a player identity is ambiguous, timestamps conflict,
source semantics cannot be classified, coverage counts disagree, an overlay
player does not match the roster, a protected artifact changes, or the theme
baseline cannot be identified.

Unavailable or editorial-only evidence remains visible in the audit with a
reason. It is not silently dropped and is not coerced into a probability.

## 10. Testing and review

Implementation follows test-first changes:

1. A coverage mismatch regression fails against the current loader, then passes
   after the smallest shared-loader fix.
2. A source-semantics regression proves that preseason rest/editorial rows never
   enter the model overlay while formal statuses still use the existing mapper.
3. A resource-warning regression fails against the current generator and passes
   after the three context-manager edits.
4. Existing importer, challenger, comparison, prospective, workflow, and full
   repository suites pass.
5. The generated shadow outputs and protected artifacts receive structural and
   hash comparisons.
6. The Fantasy page is reviewed at mobile and desktop widths, with keyboard,
   heading, link, contrast, iframe, cart, and checkout smoke checks kept as
   separate certification gates.

Browser or Shopify unavailability is reported as an unrun visual/live gate; it
does not get replaced with a claim based only on source inspection.

## 11. Acceptance criteria

The slice is complete when a frozen 32-team preseason source ledger and its
temporary outputs pass every integrity check; the shadow model preserves all
protected artifacts and remains honestly labeled; the generator emits no
unclosed-file warnings; and an unpublished Fantasy preview supplies real
Dynasty/DFS availability analysis with content ahead of merchandise.

Completion authorizes review only. Committing importer code, committing source
evidence, updating checked-in data, uploading a draft theme, publishing the
theme, or deploying ratings remain separate decisions.
