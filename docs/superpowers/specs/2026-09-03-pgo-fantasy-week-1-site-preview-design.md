# PGO Fantasy Week 1 Site Preview Design

**Date:** 2026-09-03

**Status:** Approved design; implementation not yet authorized

**Scope:** A private, site-faithful preview of 2026 Week 1 fantasy rankings inside the existing PGO ratings experience

## Decision

Add a `Fantasy Week 1` tab to a privately generated copy of the existing PGO ratings page. The tab shows every ranking-eligible player from the qualified 2026 Week 1 preview, defaults to a SUPERFLEX ranking, and supports QB, RB, WR, TE, and FLEX views.

This iteration stops at a local HTML artifact under `output/`. It must not change `docs/index.html`, GitHub Pages, Shopify, workflows, or any public URL. Publishing requires a separate explicit decision because both the Shopify draft and production page embed the same GitHub Pages URL.

## Qualified Input

The review artifact is:

- Path: `D:\Claude Context\Postgame_Outlet\prospective_evidence\fantasy-2026-week-01\operational-v2-2026-09-03-134700\preview-week-1-v2-2026-09-03-135256.json`
- File SHA-256: `65b90d8860044613e9acce45cf644b62dbbc3bf22ffae25c309fe19a111548a2`
- Embedded artifact SHA-256: `0f26a03dc1cd760455d1107c17a33632e8ef0716e28c737fc22ddfabe93210aa`
- Config SHA-256: `5b93ca84421579d9e979c71df89a55762456d16a13d76f52a8bcf445b48e6bff`
- Model: `pgo_fantasy_2026_baseline_v2`
- Generated: `2026-09-03T13:52:56.012798-04:00`
- Rows: 502 total; 447 ranking-eligible
- Eligible positions: 32 QB, 113 RB, 182 WR, and 120 TE
- State: `PREVIEW`, `HOLD`, `EXPERIMENTAL`, and non-gradeable
- Coverage: roster and depth data cover all 32 teams; definitive availability is absent for all 32 teams

The operational qualification remains local evidence only. The rankings are pre-lock half-PPR estimates, player availability is unverified, and the artifact may change before lock.

## Goals

- Let a reader inspect the real Week 1 fantasy output in the same visual shell used by the current ratings site.
- Make the most common decision path immediate: SUPERFLEX first, then position-specific or FLEX rankings.
- Keep the default table compact while preserving technical fields behind one `Show all columns` control.
- Make the PREVIEW/HOLD and unverified-availability state impossible to mistake for a final or gradeable release.
- Keep the generation path deterministic, offline, and incapable of publishing this preview.

## Non-Goals

- No GitHub Pages, Shopify, draft-theme, production-theme, workflow, or remote changes.
- No live data fetch, refresh, lock, model run, recalculation, or source normalization.
- No browser-side request for the JSON artifact.
- No new web application, framework, package, endpoint, database, or build system.
- No player detail pages, projections editor, lineup optimizer, accounts, saved filters, or comparison tool.
- No change to the existing PGO or McCabe tab content.
- No claim that the preview is final, publishable, locked, or scientifically approved.

## Reader Experience

### Placement and initial state

The private output keeps the existing page header and tab strip, with one tab added:

`PGO Model | Fantasy Week 1 | McCabe Ratings | McCabe QBs | McCabe Method`

For this dedicated review artifact, `Fantasy Week 1` is selected on load. Existing tabs remain usable and unchanged.

### Warning and context

The panel begins with a prominent `PREVIEW / HOLD` notice that states, in plain language:

- These are pre-lock half-PPR projections.
- Player availability is unverified.
- Rankings may change before lock.
- This artifact is not gradeable.

The generated timestamp appears adjacent to the notice so readers can judge freshness.

### Controls

The primary controls are native, keyboard-operable elements:

- Position pills: `SUPERFLEX`, `QB`, `RB`, `WR`, `TE`, and `FLEX`
- Player search: case-insensitive substring match on player name
- Team filter: `All teams` plus the teams present in the eligible rows
- `Show all columns` checkbox

SUPERFLEX is selected by default. The visible-player count updates whenever the position, search, or team filter changes.

### Ranking views

- `SUPERFLEX`: all ranking-eligible QB/RB/WR/TE rows, ordered by `superflex_rank`
- `QB`, `RB`, `WR`, or `TE`: ranking-eligible rows at that position, ordered by `position_rank`
- `FLEX`: ranking-eligible RB/WR/TE rows, ordered by `flex_rank`

The first column label follows the selected view: `SF#`, `QB#`, `RB#`, `WR#`, `TE#`, or `FLEX#`.

### Table

The reader-first table initially shows:

1. Selected-view rank
2. Player
3. Position
4. Team
5. Opponent
6. Projected points

Projected points display to one decimal place, while filtering and sorting retain the source numeric value. Rank sorting is ascending by default. Existing table sorting behavior is reused for visible sortable columns.

`Show all columns` adds:

- Position rank
- FLEX rank
- SUPERFLEX rank
- Baseline projection (`null_prediction`)
- Model delta (`strong_prediction - null_prediction`)
- History count
- Initialization reason
- Availability status

Stable player IDs and configuration hashes do not appear in the main table.

### Technical disclosure

A compact disclosure below the table includes:

- Model version and generated timestamp
- Embedded artifact SHA-256 and config SHA-256
- Total and eligible row counts
- Roster, depth, and availability coverage
- PREVIEW/HOLD, EXPERIMENTAL, and non-gradeable status
- The unverified-availability limitation

## Architecture

The smallest safe data flow is:

`qualified frozen preview JSON -> strict loader -> existing pgo_comparison renderer -> private HTML under output/`

### Strict Week 1 loader

Add one strict Week 1 preview loader beside the existing serialization logic in `pgo_fantasy_prospective.py`. The renderer reuses it rather than maintaining a second parser. Generalizing this loader to other weeks is deferred until another week needs a consumer.

The loader reads the input bytes once, parses strict JSON, validates the complete contract, recomputes the embedded canonical artifact hash, requires the bytes to match canonical serialization, and returns the validated object. It performs no network or filesystem reads beyond the explicitly supplied JSON file.

Validation rejects the input unless all of the following hold:

- JSON has no duplicate object keys, non-finite numbers, or unexpected fields at any level.
- `schema_version` is `1` and `artifact_kind` is `PGO_FANTASY_WEEKLY_PREVIEW`.
- The artifact is season `2026`, week `1`, model `pgo_fantasy_2026_baseline_v2`.
- `evidence_mode` is `PREVIEW`, `status` is `HOLD`, `publication_status` is `EXPERIMENTAL`, and `gradeable` is exactly `false`.
- The embedded artifact SHA-256 matches the canonical serialization already defined by the prospective module.
- The config SHA-256 is valid and every row carries the same value.
- `generated_at` is a timezone-aware timestamp.
- `teams_processed` is exactly the canonical 32-team set and `teams_missing` is empty.
- Roster and depth coverage each process all 32 teams with none missing.
- Availability processes no teams, marks all 32 teams missing, and every row is `UNVERIFIED`.
- Rows have the exact approved schema and valid primitive types; booleans are not accepted as integers.
- Season, week, team, opponent, position, game ID, and stable player ID are present and internally consistent.
- Positions are limited to QB, RB, WR, and TE; projections are finite numbers; `history_count` is a nonnegative integer; ranks are positive integers when present.
- `(season, week, game_id, gsis_id)` is unique.
- Every eligible row has a position rank and SUPERFLEX rank; eligible RB/WR/TE rows also have a FLEX rank; eligible QBs do not.
- Every ineligible row has no position, FLEX, or SUPERFLEX rank.
- Position, FLEX, and SUPERFLEX ranks are unique and contiguous within their respective populations.
- Exactly one QB per team is ranking-eligible, for 32 eligible QBs total.

The exact top-level keys are `schema_version`, `artifact_kind`, `artifact_sha256`, `config_sha256`, `evidence_mode`, `generated_at`, `gradeable`, `model_version`, `publication_status`, `rows`, `season`, `source_coverage`, `status`, `teams_missing`, `teams_processed`, and `week`. `source_coverage` has exactly the `roster`, `depth`, and `availability` entries, each containing exactly `processed` and `missing`.

The exact row keys are `availability_status`, `config_sha256`, `flex_rank`, `game_id`, `gsis_id`, `history_count`, `initialization_reason`, `null_prediction`, `opponent`, `player_name`, `position`, `position_rank`, `qb_depth_rank`, `ranking_eligible`, `season`, `strong_prediction`, `superflex_rank`, `team`, and `week`.

Any contract mismatch is a hard error. The loader does not repair, infer, coerce, skip, or partially accept rows.

### Private renderer integration

Extend `pgo_comparison.py` with one opt-in argument:

`--fantasy-preview <json-path>`

The argument is valid only in private-output mode, whose destination resolves under the repository's existing `output/` boundary. It is rejected when combined with `--publish` or `--refresh-mccabe`, before any input is loaded or output is written.

Without `--fantasy-preview`, all existing output, publish, refresh, and workflow behavior remains byte-for-byte unchanged.

When the argument is present, the renderer:

1. Loads and validates the frozen JSON.
2. Keeps only `ranking_eligible == true` rows for the fantasy panel.
3. Builds static, escaped HTML rows and the minimum inline control script needed for view selection, filtering, column visibility, counts, and sorting.
4. Injects the new tab and panel into the existing generated page.
5. Selects the fantasy tab for this private artifact.
6. Uses the existing atomic private-output write.

All data needed for interaction is embedded in the generated document. The browser performs no fetch.

### HTML, CSS, and JavaScript

Reuse the existing page typography, colors, tab treatment, table behavior, responsive breakpoints, and inline-asset pattern. Add only selectors and script branches required for the fantasy panel. No separate bundle or dependency is introduced for 447 static rows.

All source strings are HTML-escaped before insertion. Client-side behavior operates on pre-rendered rows and data attributes; it does not evaluate source text as markup or script.

## Responsive and Accessible Behavior

- Tab and position controls expose selected state and work by keyboard.
- Search has a visible label; team and column controls have associated labels.
- Focus indicators remain visible.
- The result count is announced through an appropriate live region without announcing every row change.
- Table headers retain semantic scope and sortable headers expose their current direction.
- PREVIEW/HOLD meaning is conveyed in text, not color alone.
- The reader-first columns fit a 390-pixel viewport without horizontal page overflow.
- Expanded technical columns may scroll within the table container without widening the page.

## Failure and Write Safety

- Argument incompatibility or invalid input exits non-zero with a precise error.
- Validation completes before page generation and before any destination write.
- A failure leaves no new or partially written HTML.
- The input file is read-only; source evidence is never changed or copied into tracked files.
- Output stays beneath `output/` and uses a fresh review filename.
- `docs/index.html` must remain byte-identical to its starting SHA-256, `5094ad484807bacb8ce5dddf19cff38798ed86a07c1501d1bcbf09f84dd932fe`.
- No command in this iteration pushes, deploys, publishes, refreshes remote data, or touches Shopify.

## Expected Code Surface

The implementation should be limited to the existing shared path and its tests:

- `pgo_fantasy_prospective.py`: canonical strict preview loader
- `pgo_comparison.py`: opt-in private fantasy panel and controls
- `tests/test_pgo_fantasy_prospective.py`: loader contract checks
- `tests/test_pgo_comparison.py`: rendering and interaction-markup checks
- `tests/test_public_board_workflow.py`: publication guard regression, only if the existing coverage needs one additional assertion

No other production file is expected to change. In particular, `generate_site.py`, workflow files, `docs/index.html`, and the qualified JSON remain untouched.

## Verification

Implementation follows test-first development. The minimum verification set is:

### Loader tests

- Accept a canonical PREVIEW/HOLD, non-gradeable Week 1 artifact.
- Reject duplicate keys, non-finite values, unknown or missing fields, bad primitive types, and a corrupt embedded artifact hash.
- Reject the wrong schema, artifact kind, season, week, model, evidence mode, status, publication status, or gradeable value.
- Reject incomplete team/source coverage, verified or mixed availability, config drift, duplicate players, incompatible positions, malformed eligibility, missing ranks, duplicate ranks, and rank gaps.
- Reject any artifact without exactly one eligible QB per team.

### Renderer tests

- `--fantasy-preview` is accepted with private `--output` and rejected with `--publish` or `--refresh-mccabe`.
- Omitting `--fantasy-preview` preserves existing output exactly.
- The fantasy tab is selected only in the opt-in private preview.
- The generated panel contains exactly the eligible rows supplied by a canonical test fixture, with no ineligible rows.
- SUPERFLEX is the default and rank/view membership is correct for all six pills.
- Player search, team filtering, result count, sorting, and `Show all columns` are wired to validated data.
- Warning, generated timestamp, methodology fields, hashes, and coverage are present.
- Source text is escaped and no browser-side fetch is emitted.
- Existing PGO and McCabe panels remain present and unchanged.

### Repository and browser checks

- Run the focused prospective, comparison, and workflow tests.
- Run the full test suite.
- Run syntax/compile and whitespace checks already used by the repository.
- Generate one fresh private HTML file from the exact qualified artifact after independently confirming its file SHA-256.
- Confirm `docs/index.html` retains its starting SHA-256 and the worktree contains no unexpected change.
- Inspect the local artifact at desktop and 390-pixel mobile widths in a real browser.
- Exercise tabs, every position view, player search, team filter, sorting, `Show all columns`, keyboard focus, result announcements, and responsive overflow.
- Confirm the qualified artifact's exact 447 eligible rows (32 QB, 113 RB, 182 WR, and 120 TE) and the PREVIEW/HOLD warning visually.

## Acceptance Criteria

The implementation is ready for user review when:

1. A self-contained, private HTML artifact under `output/` faithfully matches the current site shell and opens with `Fantasy Week 1` selected.
2. It renders all 447 eligible players from the exact qualified input with correct view-specific ranks and filters.
3. The compact and expanded column sets match this design.
4. PREVIEW/HOLD, half-PPR, non-gradeable, and unverified-availability limitations are prominent.
5. Strict validation fails closed before writing for every incompatible input tested.
6. Existing non-fantasy rendering and workflow behavior remains unchanged.
7. Focused and full automated checks pass, desktop/mobile browser review passes, and `docs/index.html` is byte-identical.
8. Nothing has been published, deployed, pushed, or changed in Shopify.

## Promotion Boundary

This document authorizes only its own documentation commit. After the user reviews and approves this written design, a separate implementation plan may be written. Implementing the private preview, reviewing its appearance, enabling a publish path, changing GitHub Pages, changing Shopify, and promoting to the public site are distinct later gates.
