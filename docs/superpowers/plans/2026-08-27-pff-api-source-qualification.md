# PFF API Source Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether PFF's new API is contractually and technically sufficient for PGO's approved team and weekly half-PPR fantasy models before any subscription purchase, credential use, source ingestion, or model integration.

**Architecture:** Treat PFF as an unapproved external source behind one fail-closed qualification gate. Obtain written API-specific rights, a data dictionary, and representative inactive/status responses; compare them with the locked T-90 decision contract; then issue `PASS`, `HOLD`, or `BLOCKED`. Do not design an adapter against an undocumented schema.

**Tech Stack:** Written PFF sales response, API-specific supplemental or enterprise terms, API data dictionary, representative JSON responses, Markdown review, SHA-256 evidence hashes.

## Global Constraints

- Work from `D:\Claude Context\Postgame_Outlet` on `main` and preserve unrelated untracked files.
- Do not purchase a subscription, accept new terms, submit payment information, or create an enterprise account under this plan.
- Do not use a personal PFF consumer credential, browser session, CSV export, undocumented endpoint, scraper, or reverse-engineered client.
- Do not place credentials, quotes, contracts, confidential documentation, or sample PFF payloads in Git.
- Do not ingest PFF data, fit or score a model with PFF data, or change the approved model contract unless this gate is `PASS` and a later implementation plan is explicitly approved.
- Do not modify, regenerate, grade, or overwrite the existing team model, July 2026 prospective evidence, public ratings, site, Shopify theme, workflows, or deployment state.
- Consumer PFF+ access is not commercial/modeling authorization. Only written API-specific supplemental or enterprise terms can override PFF's consumer restrictions.
- A PFF marketing statement is not evidence that official inactive history, T-90 timestamps, stable identities, retention rights, or derived-output publication rights are included.
- `HOLD` and `BLOCKED` are valid outcomes. Do not weaken the source contract to make PFF pass.

---

## Public Evidence Baseline

As of August 27, 2026:

- PFF's August 26 announcement says its API and CLI may feed projection models and scheduled scripts: <https://www.pff.com/news/introducing-the-next-generation-of-pff-products>.
- The announcement does not identify the entitled subscription tier, API pricing, inactive-list endpoints, historical snapshot coverage, rate limits, service latency, or publication rights.
- PFF's March 24, 2026 consumer terms restrict consumer use to personal and non-commercial purposes and restrict commercial reuse, bulk extraction, model use, and publication unless supplemental or enterprise terms apply: <https://www.pff.com/terms>.
- PFF's current sales contact is `sales@pff.com`.

## Locked PGO Need

PFF is useful only if it can support both independent tracks without changing their scientific contracts:

1. Team model: pregame final home margin at 90 minutes before kickoff, with current-lineup availability separated from full strength.
2. Fantasy model: weekly regular-season half-PPR projections for every officially active QB/RB/FB/WR/TE, with FLEX and Superflex derived, at 90 minutes before each player's kickoff.

For the inactive layer, the minimum grain is one player-game status observation keyed by stable player and game identities, with source lineage and the time that status was available. Historical coverage must span every 2020-2025 regular-season game; 2026 must support prospective capture before each kickoff window.

---

## Task 1: Send the Exact Qualification Request

**External recipient:** `sales@pff.com`

**Files changed:** None.

- [ ] Send the following message without adding claims that PGO already has API rights or an existing commercial license.

```text
Subject: PFF API licensing and NFL inactive-history coverage for Postgame Outlet

Hello PFF Sales,

Postgame Outlet is an early-stage NFL and fantasy-football analytics site evaluating PFF's newly announced API. We would use licensed PFF data as inputs to our own pregame team-rating and weekly fantasy-projection models. We would not redistribute raw PFF data.

Before purchasing, could you confirm the following in writing and share the applicable API-specific terms, data dictionary, and representative responses?

1. Which current plan includes API and CLI access, and is a separate commercial or enterprise agreement required for a public site?
2. May Postgame Outlet use the API data to train, validate, and run statistical or machine-learning projection models?
3. May we store/cache licensed API responses for reproducible historical backtests and retain the necessary frozen evidence after a subscription or agreement ends?
4. May we publish only our derived team ratings, player projections, fantasy ranks, confidence information, and model-validation metrics on a commercial/editorial website, without exposing raw PFF fields?
5. Does the API provide NFL official game-day inactive designations for every regular-season game from 2020 through 2025 and live coverage for 2026?
6. For each inactive/status record, are stable player IDs, game IDs, team, status, source/provenance, original publication or available-at timestamp, and revision timestamps included?
7. Are live inactive/status records reliably available by 90 minutes before kickoff, and what freshness or service commitments apply?
8. Can PFF player IDs be mapped directly to GSIS IDs? If not, is a complete supported crosswalk provided?
9. Do historical endpoints preserve the status known at the original decision time, rather than only today's corrected final state?
10. What are the API rate limits, pagination rules, historical lookback limits, schema/versioning policy, and permitted automated refresh frequency?
11. What attribution is required for derived public outputs?
12. May we retain and publish non-reversible SHA-256 hashes of licensed source snapshots in audit receipts without publishing the source data itself?

Our operational target is one refresh per NFL kickoff window, covering all 32 teams and all fantasy-eligible players. A sandbox, OpenAPI document, endpoint list, or redacted sample response would let us confirm technical fit before integration.

Thank you,
Alex
Postgame Outlet
```

- [ ] Preserve PFF's complete reply and attached terms outside the repository.
- [ ] Do not interpret silence, a sales call, marketing copy, or consumer API credentials as approval.

**STOP:** Wait for a written response that addresses contract rights and data coverage. No later task may start from an unanswered request.

---

## Task 2: Apply the Contract Gate

**Files changed:** None until a complete vendor response exists.

- [ ] Confirm the governing document is an API-specific supplemental or enterprise agreement that expressly overrides conflicting consumer restrictions.
- [ ] Confirm the named licensee can be Postgame Outlet and the permitted use includes a public commercial/editorial website.
- [ ] Confirm automated API/CLI access, local caching, reproducible backtesting, statistical/ML training, inference, and derived-output publication are each expressly permitted.
- [ ] Confirm whether raw snapshots may be retained after termination. If not, classify long-term reproducibility as `HOLD` and do not silently substitute source hashes for reproducible evidence.
- [ ] Confirm derived team ratings, fantasy projections/ranks, confidence information, and aggregate validation metrics may be displayed publicly.
- [ ] Confirm any attribution, logo, naming, citation, or review requirement without agreeing to alter PGO's model results or editorial conclusions.

**Contract result:**

- `PASS`: every required use is expressly permitted in governing written terms.
- `HOLD`: commercial/modeling rights appear available but price, retention, attribution, or an executed agreement remains unresolved.
- `BLOCKED`: PFF declines any required use or consumer terms remain the only governing terms.

---

## Task 3: Apply the Data and Timing Gate

**Required evidence:** data dictionary plus representative inactive/status responses for one historical game and one current or sandbox game. Keep both outside Git.

- [ ] Verify complete 2020-2025 NFL regular-season inactive coverage for both teams in every game.
- [ ] Verify 2026 live inactive/status coverage is schedule-driven across all 32 teams, including explicit zero-row team/game coverage when no players are listed.
- [ ] Verify each record has a stable PFF player ID and either a GSIS ID or a complete supported PFF-to-GSIS crosswalk.
- [ ] Verify a stable game ID, team, season, week, kickoff, status, source/provenance, available-at timestamp, and revision timestamp.
- [ ] Verify timestamps include an unambiguous timezone and permit reconstruction of the state known at the locked T-90 decision time.
- [ ] Verify the historical endpoint does not replace original decision-time state with an unmarked corrected current state.
- [ ] Verify inactive designations are game-day statuses, not fantasy-draft availability, depth-chart status, injury risk, projected availability, or postgame participation.
- [ ] Verify documented pagination, rate limits, schema versioning, and refresh frequency can support one all-player pull per kickoff window with retry margin.
- [ ] Verify completeness can be audited without interpreting an absent team or player as healthy.

**Data result:**

- `PASS`: every required field, season, team, game, identity, timestamp, and live timing property is documented and present.
- `HOLD`: the source is licensed and useful for grades/stats but lacks only the inactive layer; PFF may later be evaluated as an optional feature source, not the availability authority.
- `BLOCKED`: inactive coverage is incomplete, final-state-only, identity-ambiguous, timestamp-ambiguous, or unavailable by T-90.

---

## Task 4: Issue the Qualification Decision

The overall result is the worse of the contract and data/timing results.

- [ ] `PASS`: amend the approved source section to name the exact PFF product/agreement and documented endpoints, then write a separate TDD implementation plan for a narrow PFF adapter and frozen-source audit. Obtain explicit approval before either change.
- [ ] `HOLD`: retain nflverse as the admissible baseline source, keep PFF out of model inputs, and document the exact commercial, retention, pricing, or coverage item still open.
- [ ] `BLOCKED`: exclude PFF from the model and return to either a different rights-cleared inactive vendor or an explicitly re-approved nflverse-only fantasy baseline.

Regardless of result:

- [ ] Never commit the agreement, pricing, API key, confidential documentation, or raw/sample PFF payloads.
- [ ] Never treat qualification as authorization to purchase, implement, run a model, publish, push, or deploy.
- [ ] Run `git status --short` and verify that this qualification work did not change any protected model, evidence, public, store, or deployment path.

## Plan Verification

Run:

```powershell
rg -n "sales@pff.com|2020-2025|90 minutes|machine-learning|derived|GSIS|available-at|PASS|HOLD|BLOCKED" docs/superpowers/plans/2026-08-27-pff-api-source-qualification.md
git diff --check -- docs/superpowers/plans/2026-08-27-pff-api-source-qualification.md
git status --short
```

Expected:

- the qualification questions and all three decision states are present;
- `git diff --check` emits no output;
- no protected source, model, evidence, public, store, workflow, or deployment file changed.
