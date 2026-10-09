# Reviewed starter updates

Starter changes use three separate commands. Each command reloads the verified current season state and its latest saved roster. None refreshes, fits, saves, or publishes a forecast.

The selected game must belong to the current scheduled week or its immediate pending week. Pending-week capture, review and activation replay the archived provider finals and require the current week to be complete. A missing final, duplicate schedule identity or unrelated future week blocks admission. A failed weekly build retains its actual captured input references in the saved blocked state, including roster timestamps and hashes, while the previous rankings and forecasts remain intact.

## 1. Capture

Run before the game's T-60 cutoff with one official club news URL, an eligible scheduled game, the team, the player's GSIS ID, and the exact sentence from the article:

```powershell
python pgo_starter_capture.py capture `
  --url "https://www.atlantafalcons.com/news/example" `
  --game-id "2026_02_CAR_ATL" `
  --team "ATL" `
  --gsis-id "00-0000000" `
  --statement "Exact announcement sentence."
```

The command checks the saved active roster is at most 24 hours old and validates the official team domain before making one request; it does not follow redirects. It prints a hash-named file under `docs/evidence/season-2026/starter-drafts/`. The draft preserves the exact response bytes, including a partial body, status, headers, final URL, request start, and completion time. Redirects, HTTP errors, incomplete responses, request failures, a backwards wall clock, and capture reaching T-60 return exit code 1 but retain their draft receipt. Capture does not change `data/pgo_starter_announcements.json`.

## 2. Review

Inspect the draft and article, then pass the printed draft basename or safe relative path:

```powershell
python pgo_starter_capture.py review --draft "<capture-sha256>.json"
```

Review reloads the current matchup and an active roster captured within 24 hours, checks the receipt hash, exact statement and player name, article matchup and week, publication and modification dates, source bytes, redirect status, and all capture/review clocks. A valid review writes the existing immutable `official_starter_announcement` envelope under `source-archive/` and prints a hash-named receipt under `starter-reviews/`. It also pins the current starter configuration hash. Review does not activate the rule.

If the article discusses earlier games, review may add repeatable `--historical-context "Exact full sentence."` arguments. Inspect each sentence as historical context first: it is recorded in the hash-bound decision, must occur exactly once in the primary article, must mention only earlier numbered weeks, and cannot overlap the reviewed starter statement. Headline, starter statement and all unselected text retain the strict week check. No historical context is inferred automatically; without these explicit annotations the original strict check remains.

## 3. Activate

Activate only the reviewed receipt that was just inspected:

```powershell
python pgo_starter_capture.py activate --review "<review-sha256>.json"
```

Activation reloads the current state and current active roster, requires that roster capture to be at most 24 hours old, and replays the immutable source through `pgo_expected_starters`. An exclusive sidecar lock covers the config read, conflict checks, staging, and replacement. After staging and flushing the new bytes, activation rechecks the config hash and actual clock immediately before replacement; both activation clocks must be strictly before T-60. It rejects tampering, future or wrong-game evidence, a stale roster, configuration drift, a busy activation, or another announcement for the same game and team. It atomically appends one rule to `data/pgo_starter_announcements.json`.

Activation does not run the season refresh, change a forecast, fit a model, push, or publish. Those remain separate operator actions under the existing season workflow.

On the next authorized season refresh, initial issuance and pre-lock revisions resolve applicable reviewed announcements before checking default depth for the remaining teams. Numerical updates still require all 32 teams to have unique eligible quarterbacks; unrelated conflicts continue to block. Issued games retain their announcement references for save/load replay. Later revisions and inactive-list context replay already locked games' archived authority using its original clocks; their issued forecasts and confidence allocations remain fixed.

An announcement applies only to its verified matchup and week. A prior Atlanta announcement against Pittsburgh cannot establish a starter for Carolina at Atlanta. Software readiness does not establish a current starter: without supported game-specific evidence or consistent provider roster/depth, the input hold remains.

If the process is terminated while activating, inspect `.pgo_starter_announcements.json.activation.lock` and confirm that no activation is running before removing that stale lock and retrying.

For an alternate evidence root used in offline testing, place `--root PATH` before the subcommand. Receipt arguments accept only their SHA-256 basename or their exact `starter-drafts/` or `starter-reviews/` relative path; absolute paths outside that root and symlinks are refused.


## Separately timestamped current projections

After T-60, the approved current projection uses `capture-current`, `review-current`, and `activate-current` with the same arguments as the original commands. The current commands retain actual capture, review and activation times, exact official bytes, matchup/week/active-roster identity checks, and the atomic configuration drift checks. They write only `data/pgo_current_starter_announcements.json`. Their evidence is marked `current_projection` and cannot be admitted by the original prelock commands or replayed as original forecast authority. Article publication and modification must precede kickoff; recovery is limited to the six-hour game window.

The season updater uses the existing completed-week statistical feature and coefficient machinery to create a separate `current_projections` entry. It does not change the original locked game, confidence allocation, sportsbook quote, issue time or on-time record. The current projection shows its actual issue and source clocks and whether it was issued after T-60 or kickoff. It is excluded from original forecast grading. Unverified or ambiguous starters remain an explicit input block; human quarterback grades are not statistical inputs. Prior current projections and the source/state archives remain saved.
