# PGO Matchup Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private preview for every scheduled game that displays McCabe's implied line, the independent PGO shadow fair line, the ESPN market line, and each model's market edge without changing the public board.

**Architecture:** Add one small stdlib-only adapter, `pgo_matchup_comparison.py`, that validates the frozen PGO artifact, reuses `spreads.py` for schedule fetching, HFA, sign convention, team formatting, and model-line calculation, then writes HTML only under `output/pgo-matchup-preview/`. Keep `spreads.py`, `docs/index.html`, Pages, and Shopify behavior unchanged.

**Tech Stack:** Python 3, `unittest`, existing `spreads.py` and `espn_api.py` helpers, CSV/JSON/HTML from the standard library, existing repository PGO artifacts.

## Global Constraints

- Work only in `D:\CodexWorktrees\Postgame_Outlet-ci-clean` on `codex/matchup-comparison`; preserve the dirty legacy checkout and do not edit `main` directly.
- Keep the existing PR #3 CI/dependency fix separate; this feature may be based on its branch but must not rewrite its five-file scope.
- Do not add dependencies, a service, a frontend framework, a scheduled workflow, Shopify files, or a public Pages artifact.
- Do not modify `spreads.py`'s existing CLI/output or `docs/index.html`.
- Keep PGO team ratings independent from McCabe ratings; never average, overwrite, or relabel either source.
- Fail closed for invalid PGO artifacts, malformed market spreads, unknown teams, duplicate events, unmatched joins, and output paths outside `output/`.
- A missing ESPN odds object is valid and must render `Unavailable` with no edge.
- Use `apply_patch` for edits and run the focused test before the full suite after each implementation slice.

---

## Task 1: Add red tests and reusable fixtures

**Files:** `tests/test_pgo_matchup_comparison.py` (new)

- [ ] Create a self-contained `unittest` fixture with two canonical teams plus a full 32-team PGO CSV fixture generated in a temporary directory, a sibling `backtest.json` receipt, and a scoreboard payload containing two events (one priced, one without odds).
- [ ] Add failing tests for the public interfaces that the implementation must provide:
  - `load_pgo_ratings(path, receipt_path=None)` returns full-team-name ratings and metadata.
  - `build_matchup_rows(payload, mccabe_ratings, pgo_ratings, hfa, default_hfa)` returns one row per scheduled event.
  - `render_preview(rows, metadata, *, year, week, captured_at, source_url)` emits the private comparison page.
  - `default_preview_path(captured_at)` returns `output/pgo-matchup-preview/<YYYY-MM-DD>/index.html`.
  - `write_preview(html, path)` rejects a path outside the repository `output/` directory.
- [ ] Cover the required behavior in the red tests: `line = -(home - away + effective_hfa)`, half-point rounding, positive/negative edges using `market - model_line`, McCabe/PGO lines remaining different, unavailable market cells, primetime HFA, team abbreviation mapping, PGO status/as-of/HOLD text, and no public-file path.
- [ ] Add failure cases for missing columns, duplicate teams, unknown abbreviations, non-finite headline ratings, inconsistent `as_of`, missing receipt, invalid receipt status/checks, duplicate events, unmatched model joins, unknown event teams, and malformed non-numeric market spreads.

**Verification:** `python -m unittest tests.test_pgo_matchup_comparison -v` must fail because `pgo_matchup_comparison.py` does not yet exist; the failure must be import/interface failures rather than a test syntax error.

## Task 2: Implement strict PGO artifact loading

**Files:** `pgo_matchup_comparison.py` (new), `tests/test_pgo_matchup_comparison.py`

- [ ] Add module constants for `HERE`, `OUTPUT_ROOT`, the default PGO artifact `research/pgo_v1/ratings_2026_preseason.csv`, its sibling `backtest.json`, and the existing ESPN endpoint imported from `spreads.py`.
- [ ] Implement `load_pgo_ratings(path, receipt_path=None)` with the smallest strict loader:
  - Read CSV with `csv.DictReader` and require the fields `team`, `headline_rating`, `as_of`, and `validation_status` (allowing the existing artifact's additional audit columns).
  - Require 32 unique current-team abbreviations using `spreads.ABBR`'s inverse map; reject unknown or duplicate abbreviations.
  - Convert `headline_rating` to finite floats and map each abbreviation to its canonical full team name.
  - Require one consistent `as_of` value and a status of `EXPERIMENTAL` or `VALIDATED`.
  - Read the sibling receipt JSON, require matching `as_of`, `checks`, and `failed_checks`, and preserve the status/reason text for the preview. Derive `display_status` as `HOLD` when the CSV status is `EXPERIMENTAL` or any receipt check failed; only a `VALIDATED` artifact with no failed checks may display `VALIDATED`. A failed check never silently certifies the model.
  - Raise `ValueError` before any output write for each invalid condition, with the team/path and reason in the message.
- [ ] Return `(ratings_by_full_name, metadata)` where `metadata` contains `artifact_path`, `receipt_path`, `as_of`, `validation_status`, `display_status`, `status_reason`, `failed_checks`, and `checks` for rendering and tests.
- [ ] Keep all validation local to this adapter; do not weaken `release_ratings.py` or the public release gate.

**Verification:** Make the loader tests pass, then run `python -m py_compile pgo_matchup_comparison.py` and `python -m unittest tests.test_pgo_matchup_comparison -v`.

## Task 3: Implement comparison rows using existing spread logic

**Files:** `pgo_matchup_comparison.py`, `tests/test_pgo_matchup_comparison.py`

- [ ] Implement `build_matchup_rows(payload, mccabe_ratings, pgo_ratings, hfa, default_hfa)` by reusing `spreads.parse_games` twice—once with McCabe ratings and once with the validated PGO full-name map—rather than duplicating HFA or sign math.
- [ ] Before parsing, preflight every event's canonical home/away names and every supplied odds spread: unknown teams and non-numeric/non-finite spreads raise; absent odds remain `None`.
- [ ] Join parser results by `(date, home, away)`. Reject duplicate keys in either parser result and reject any key missing from the other result; never pair games by list position.
- [ ] Return deterministic rows sorted by kickoff date, with these keys: `date`, `prime`, `home`, `away`, `market`, `details`, `mccabe_line`, `pgo_line`, `mccabe_edge`, `pgo_edge`, `mccabe_hfa`, and `pgo_hfa`.
- [ ] Preserve ESPN's `details` string when present, but calculate both numeric edges only from the numeric home-relative `market` value. For `market is None`, set both edge fields to `None`.
- [ ] Keep the existing `spreads.round_half` behavior so both models use identical half-point rounding and primetime HFA treatment.

**Verification:** The algebra, join, missing-market, duplicate, unknown-team, and malformed-market tests pass; run the focused test module and `git diff --check`.

## Task 4: Implement private HTML preview and CLI

**Files:** `pgo_matchup_comparison.py`, `tests/test_pgo_matchup_comparison.py`

- [ ] Implement `render_preview(rows, metadata, *, year, week, captured_at, source_url)` as a single escaped HTML document using the existing dark-table style as a plain template; do not add JavaScript or a dependency.
- [ ] Render one table row per scheduled event with columns: matchup, kickoff, McCabe line, PGO fair line, market, McCabe edge, PGO edge, and market source/capture. Use `Unavailable` for missing market/edges; never render zero or an inferred value.
- [ ] Put a clear private-preview header and note that McCabe, PGO, and market numbers are independent matchup lines, not league ranks or a blended rating. Include PGO artifact path, `as_of`, validation status, HOLD reason/failed checks, ESPN URL, and UTC capture time.
- [ ] Implement `default_preview_path(captured_at)` and `write_preview(html, path)`. Resolve the candidate path and require it to remain under `OUTPUT_ROOT`; create parent directories only after validation and write UTF-8 HTML atomically with the existing `release_ratings.atomic_write_text` helper.
- [ ] Implement `main(argv=None)` with `week` and `year` positional defaults (`1`, `2026`) and optional `--pgo-ratings`, `--pgo-receipt`, and `--output` arguments. Fetch once with `spreads.fetch_week`, capture one UTC timestamp immediately around that fetch, load McCabe/HFA with existing helpers, build rows, and write only the private output. Return nonzero on validation/fetch/write errors and never create `docs/index.html`.
- [ ] Add CLI tests that patch `fetch_week`, pass a fixture artifact, verify the rendered file is under `output/`, and verify invalid output paths fail before creating files.

**Verification:** `python -m unittest tests.test_pgo_matchup_comparison -v` passes and a patched CLI invocation produces the expected private file without changing `docs/index.html`.

## Task 5: Document the private workflow and run release gates

**Files:** `README.md`, `tests/test_pgo_matchup_comparison.py` (only if a final regression test is needed)

- [ ] Add a short README section with the exact command:
  `python pgo_matchup_comparison.py 1 2026 --pgo-ratings research/pgo_v1/ratings_2026_preseason.csv`
  and state that it writes a private `output/pgo-matchup-preview/<date>/index.html`, does not publish, and treats the current experimental/HOLD receipt as non-certifying.
- [ ] Run focused tests: `python -m unittest tests.test_pgo_matchup_comparison -v`.
- [ ] Run the full release gate: `python -m unittest discover -s tests`; all tests must pass with no new failures.
- [ ] Run syntax and whitespace checks: `python -m py_compile pgo_matchup_comparison.py tests/test_pgo_matchup_comparison.py` and `git diff --check`.
- [ ] Confirm the public artifact is untouched: `git diff -- docs/index.html` is empty, no Shopify files changed, and `git status --short` contains only the intended adapter, test, README, and plan/spec files.
- [ ] Review the final diff for accidental changes to `spreads.py`, `data/ratings.csv`, `research/pgo_v1/*`, `.github/workflows/*`, or generated public output before committing.
- [ ] Commit the implementation separately from the design commit. Do not push or merge until the user explicitly authorizes the integration step; if pushed, keep it in a draft PR stacked on the existing CI-fix branch until PR #3 is merged, then retarget to `main`.

## Completion Criteria

- [ ] Every scheduled fixture game appears exactly once.
- [ ] McCabe and PGO lines are independently calculated with the existing home-relative convention.
- [ ] Market edges are `market - model_line` and are absent when the market is unavailable.
- [ ] Invalid PGO artifacts and unsafe output paths fail before any HTML is written.
- [ ] The full test suite passes and the public board/Pages inputs remain unchanged.
