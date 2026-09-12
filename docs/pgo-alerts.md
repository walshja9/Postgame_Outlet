# PGO owner alerts

The season workflow delivers a native GitHub issue assigned only to `walshja9`. It uses the workflow's existing `GITHUB_TOKEN` with repository `issues: write`; it adds no service, secret, personal-token scope or notification preference change.

Successful issue assignment is delivery evidence, not confirmation that email, mobile or inbox notifications arrived or were read. GitHub notification preferences still control those channels. This check runs inside the existing refresh workflow: it cannot independently notify when GitHub Actions is disabled or never starts. The board's visible overdue indicator remains useful then.

## Invocation

Run after publication and rollover observation under `if: always()`, inside the existing `board-update` concurrency group. Set `GH_TOKEN` to the workflow token and pass explicit step outcomes. Immediately before the refresh command, write a UTC timestamp to the refresh step's `started_at` output.

```text
python pgo_alerts.py --deliver --check-public
  --run-refresh <route.run_refresh>
  --verify-outcome <verify.outcome>
  --refresh-outcome <refresh.outcome>
  --render-outcome <render.outcome>
  --publish-outcome <publish.outcome>
  --rollover-outcome <rollover.outcome>
  --refresh-started-at <refresh.started_at>
```

`GITHUB_REPOSITORY`, `GITHUB_RUN_ID` and `GITHUB_RUN_ATTEMPT` supply the fixed recipient repository and workflow link. Delivery is restricted to `walshja9/Postgame_Outlet`; workflow URLs must match that repository. Without `--deliver`, the CLI prints a safe read-only assessment and makes no issue requests. Without `--check-public`, incident resolution is held.

A route value of `false` is an intentional no-op: no saved-state load, public GET, issue read, create, comment or resolution occurs. A missing route value does not count as a successfully skipped tick. Failed delivery returns a failed step with a generic error. Notification failure must not suppress the earlier truthful source-state publication.

## Conditions

- Reuse `pgo_workflow_status.report_health` for main source/availability failures and normal next-week waiting. Explicitly `BLOCKED` independent penalty, scoring, model-weight and defender updates produce nonurgent conditions (`monitor-penalty`, `monitor-totals`, `monitor-weights`, `monitor-replacement-depth`). Missing optional components, experimental HOLD and historical fitting admission do not trigger these alerts. Blocked sportsbook capture retains its separate alert.
- Reuse `pgo_season.availability_watch`: final lists can normally be awaited until 75 minutes before kickoff. Missing lists then need attention; a completed pregame list whose last check is older than 10 minutes is stale. Missing lists remain visible for the existing post-kickoff watch window. Pregame failures are urgent.
- Match the board's existing freshness rules: saved automation older than 45 minutes is overdue; an unlocked game's availability check within the next 24 hours is overdue after 30 minutes.
- Check only the fixed HTTPS Pages `evidence/season-2026/current.json` for public deployment health. Unavailable, malformed, future-dated or older-than-45-minute pointers need attention. This small read-only check is not another model-input collector. It allows ordinary publication delay within that freshness window; it does not require the newly pushed snapshot to be instantly public.
- Explicit verify, refresh, render, publish or rollover-verification failures alert even if the old saved state still looks healthy. The shared `STAGES` list defines required outcomes; incomplete or missing outcomes cannot resolve an incident. Rollover `WAITING` is a valid successful observation, while an invalid receipt fails that stage and produces `failed-rollover`. Intentional skipped ticks remain no-ops.
- Normal next-week waiting does not immediately alert. Once all current-week scheduled games have unique matching saved verified finals, a missing next edition becomes attention after more than six hours from the latest `finalized_at`. This grace period is an operator threshold, not a delivery deadline or a claim that upstream data must be ready.

No raw provider errors, credentials, source URLs or stack traces appear in issue content. Public messages use fixed descriptions, validated team names and normalized timestamps. Existing workflow evidence remains the place to investigate details.

## One incident, controlled retries

The stable marker is `<!-- pgo-alerts:v1 -->`. The issue must be created by `github-actions[bot]` with Bot type and assigned exactly to `walshja9`. The writer paginates all open issues. A marker on a human-authored issue or pull request, an altered assignee, malformed metadata or multiple marked issues blocks mutation for review.

Unchanged conditions make no writes. New conditions or higher urgency update the issue and add one notification comment. A saved pending marker and paginated bot-comment check make failed delivery retryable without repeating a comment whose response was lost. Condition removals update the issue quietly.

Resolve only after all required stages succeeded, the verified saved state is fresh and captured after this run's refresh began, the public pointer is fresh, and no alert conditions remain. Old apparently healthy snapshots, missing start times or skipped ticks cannot close an incident. A later incident opens a new assigned issue; closed history remains available.

GitHub has no atomic create-if-absent issue operation. Existing workflow concurrency prevents concurrent writers. Creation validates the POST response and then reads the returned issue ID directly using the same ownership, assignment and metadata checks. It still paginates the open list for duplicates, but temporary omission from that list does not invalidate the directly confirmed issue. An observed duplicate fails visibly instead of silently closing either issue. POST is never automatically retried, and an API failure still requires a later check. Do not run concurrent manual deliveries outside that lock.

Delivery errors now identify a fixed safe category: `GITHUB_API`, `ISSUE_RESPONSE`, `ISSUE_OWNERSHIP`, `ISSUE_METADATA`, `ISSUE_DUPLICATE`, `ISSUE_CONFIRMATION` or `INPUT_INVALID`. These distinguish unavailable API confirmation from invalid ownership without disclosing exception details. This addresses the confirmation ambiguity observed when issue #8 was created and assigned successfully but its immediate confirmation step failed; the original transient cause was not established.

Post-lock inactive context is selected using a fresh clock after the forecast capture attempt. If that attempt crosses T-60, the same run can collect later context while retaining the original forecast error and immutable pick/confidence records. This closes an intra-run timing gap; it does not guarantee GitHub schedule start times.

The current publication step proves that its git push and Pages build request succeeded. It does not prove that the resulting build finished or a reader's browser refreshed. Resolution therefore says "fresh saved refresh and publication request"; the separate public-pointer check detects a public update stalled beyond the freshness allowance.

## Commissioning and checks

Exercise the real route with a genuine incident or a clearly labeled setup check. The only commissioning condition key is `commissioning`; it receives the title **Notification delivery check** and explicitly says it is not a model or data failure. Normal health assessment never emits that key. Run commissioning under the bot token in Actions, only when fresh health and the absence of another open owned incident are verified. Resolve through the normal fresh-health gate and retain the issue/run receipt. Never fabricate a source/model failure or alter saved season data to test delivery.

```text
python -m unittest tests.test_pgo_alerts tests.test_pgo_workflow_status tests.test_pgo_inactive_monitor
```

Tests cover watch thresholds, safe wording, stale/future/missing state, public-pointer freshness, weekly grace, pipeline failures, no-op behavior, ownership, pagination, deduplication, partial API failures, recipient restriction and fresh resolution. They do not prove live notification receipt.

The implementation uses the installed CLI with JSON supplied through stdin and no shell interpolation. See the official [GitHub Issues API](https://docs.github.com/en/rest/issues/issues) and [GitHub CLI API command](https://cli.github.com/manual/gh_api).
