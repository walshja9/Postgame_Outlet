# Reviewed starter updates

Starter changes use three separate commands. Each command reloads the verified current season state and its latest saved roster. None refreshes, fits, saves, or publishes a forecast.

## 1. Capture

Run before the game's T-60 cutoff with one official club news URL, the current game, the team, the player's GSIS ID, and the exact sentence from the article:

```powershell
python pgo_starter_capture.py capture `
  --url "https://www.atlantafalcons.com/news/example" `
  --game-id "2026_02_ATL_PIT" `
  --team "ATL" `
  --gsis-id "00-0000000" `
  --statement "Exact announcement sentence."
```

The command validates the official team domain before making one request and does not follow redirects. It prints a hash-named file under `docs/evidence/season-2026/starter-drafts/`. The draft preserves the exact response bytes, including a partial body, status, headers, final URL, request start, and completion time. Redirects, HTTP errors, incomplete responses, request failures, and a backwards wall clock return exit code 1 but retain their draft receipt. Capture does not change `data/pgo_starter_announcements.json`.

## 2. Review

Inspect the draft and article, then pass the printed draft basename or safe relative path:

```powershell
python pgo_starter_capture.py review --draft "<capture-sha256>.json"
```

Review reloads the current matchup and an active roster captured within 24 hours, checks the receipt hash, exact statement and player name, article matchup and week, publication and modification dates, source bytes, redirect status, and all capture/review clocks. A valid review writes the existing immutable `official_starter_announcement` envelope under `source-archive/` and prints a hash-named receipt under `starter-reviews/`. It also pins the current starter configuration hash. Review does not activate the rule.

## 3. Activate

Activate only the reviewed receipt that was just inspected:

```powershell
python pgo_starter_capture.py activate --review "<review-sha256>.json"
```

Activation reloads the current state and current active roster, requires that roster capture to be at most 24 hours old, and replays the immutable source through `pgo_expected_starters`. An exclusive sidecar lock covers the config read, conflict checks, staging, and replacement. After staging and flushing the new bytes, activation rechecks the config hash and actual clock immediately before replacement; both activation clocks must be strictly before T-60. It rejects tampering, future or wrong-game evidence, a stale roster, configuration drift, a busy activation, or another announcement for the same game and team. It atomically appends one rule to `data/pgo_starter_announcements.json`.

Activation does not run the season refresh, change a forecast, fit a model, push, or publish. Those remain separate operator actions under the existing season workflow.

If the process is terminated while activating, inspect `.pgo_starter_announcements.json.activation.lock` and confirm that no activation is running before removing that stale lock and retrying.

For an alternate evidence root used in offline testing, place `--root PATH` before the subcommand. Receipt arguments accept only their SHA-256 basename or their exact `starter-drafts/` or `starter-reviews/` relative path; absolute paths outside that root and symlinks are refused.
