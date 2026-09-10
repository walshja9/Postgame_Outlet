# PGO weekly rankings and prediction records

PGO automatically checks for verified final results every 15 minutes. GitHub runner queues and source publication delays can make an update later. The public board shows its last completed check. An open PGO board checks for a newer published edition every minute.

The W/L/T record grades each model against its own saved forecast. A tie is shown separately; a missing or withheld pick is not a win or loss. Different editions can cover different numbers of games, so their pending counts can differ. The continuing weekly model and the original opening-week models are labeled separately. A corrected final score or inconsistent game identity pauses acceptance for review instead of silently changing the archived result.

When all games in a week have verified finals and the required team/player statistics are available, PGO advances its existing model inputs and publishes the next weekly edition. The existing coefficients are not refitted. The [nflverse data schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html) explains why detailed statistics may arrive later than scores. Missing statistics keep the last verified rankings visible with a delay notice. Bye weeks are taken from the actual schedule. After Week 18, the final rankings are updated and the regular-season process stops.

Availability is checked for games within 24 hours of kickoff until their 60-minute pre-kickoff cutoff. Official injury reports and complete official inactive lists are distinct sources. Missing reports, unresolved identities and incomplete lists remain explicit. Non-QB injuries are context, not fitted numerical adjustments. If an expected QB is confirmed unavailable, the conditional pick is withheld; an unknown later report does not erase that finding. A newly sourced first-string QB may produce a new unlocked forecast. Every earlier revision stays archived. A delayed job cannot revise a locked game.

## How the numbers connect

- A team rating is its model strength relative to the average of the 32 teams. In this model, subtracting the opponent's saved rating gives the projected neutral-site margin at equal rest. An individual +5 rating does not describe a complete matchup.
- Venue and rest adjustments turn that difference into the estimated game margin. Archived games explain the ratings used when that prediction was issued, even after the current rankings change.
- The scoring-history estimate gives combined points. Half the total plus half the home margin gives the home score; the other half gives the away score. These sum back to the total and differ by the margin. Rounded equal scores mean closely matched averages, not a literal tie prediction.
- A fixed historical probability curve converts the margin to home-win, away-win and tie probabilities that sum to one. Win probabilities remain experimental estimates.
- Each weekly confidence slate assigns unique points once. A pre-lock QB revision may change the win probability while preserving that game's assigned points. Expected pool points equal assigned confidence points times the selected team's win probability; these are different units from NFL scoreboard points.

The scoring-total heuristic still uses the frozen 2025 regular-season and playoff scoring rates. Current defensive roster depth and non-QB replacement quality are not fitted features. Overlapping team and QB inputs are influences in one formula, not independent evidence of team quality. Reported profits alone do not establish predictive accuracy; dated forecasts and an auditable record are the public evidence for any model.

## Operations and evidence

`python pgo_season.py --refresh` captures actual provider responses, verifies finals, checks rollover and pregame availability, and writes a new dated state plus a hashed pointer under `docs/evidence/season-2026/`. It does not overwrite earlier editions. The model seed reproduces all 320 saved team ratio values from 3,562 pinned historical games. Windows reproduces the saved opening inputs exactly; Linux floating-point library replay differs by at most one binary rounding unit in six log features.

`.github/workflows/update-season.yml` runs the checks and publisher only in the canonical repository. On an input conflict it publishes the last verified edition with the reason for the delay. The original Week 1 forecast and confidence files remain byte-for-byte unchanged; Seattle's separately added full-slate confidence value remains marked after lock and excluded from probability validation.

Future raw sources and compressed audit packages live in the public Git repository and are linked directly from the site. The Pages build excludes only the new source-archive, availability-v2 and runs-v2 folders; current.json remains on the site for freshness checks. Earlier files and their URLs remain available. New availability packages retain only the game identities and roster fields needed for replay, including player-name aliases, and compress their inputs and raw HTML. New season states use state.json.gz; manifests hash the compressed bytes, and the reader still verifies older uncompressed packages. A replay of the actual opening-week capture reduced its package from 4,612,434 to 227,476 bytes while preserving the observations; its season state compressed from 347,892 to 34,482 bytes. These changes keep repeated captures out of the website size limit without discarding earlier predictions.

Run `python -m unittest discover -s tests -p "test_pgo_season*.py"` for the season checks. They exercise full-week rollover, incomplete weeks, missing statistics, byes, end-of-season ratings, source hashes, game/provider identity, final-status conflicts, fixed confidence points, pregame QB changes, timestamp boundaries and immutable prior forecasts. A 16-game simulated completion produced 32 updated rankings and all 16 actual Week 2 fixtures; synthetic outcomes are test data and are not published as real results.

Operational checks do not prove the model predicts accurately. PGO remains EXPERIMENTAL / HOLD while its prospective record accumulates.

### Board publication and queued season updates

The board workflow tests its exact triggering commit without holding the shared `board-update` publishing lock. After those tests pass, its publisher takes the same lock used by the season updater and checks out the latest `main`. The tested commit's `pgo_publication_guard.py` requires that commit to be an ancestor. It permits additions to the existing season archive folders and updates to `current.json`, `docs/index.html` and `docs/forecast-lab.html`. Existing archives cannot be rewritten or deleted; the season model seed is excluded. Source, workflow, dependency, styling and frozen-evidence changes require their own passing run.

The publisher renders from that checked-out state and pushes without rebasing an older render. A conflicting push fails instead of overwriting newer work. Canonical pushes explicitly request a Pages build; the testing mirror keeps its artifact upload and deployment flow. This removes the long full test suite from the season updater's lock, but GitHub scheduling and the shorter publishing jobs can still delay checks.

After attempting publication, the season workflow reports the saved state and penalty status in its Actions summary and emits a warning for a blocked update. Next-week waiting, source conflicts and availability failures have distinct labels and retain the exact reason and check time. Reporting does not stop a truthful blocked state from being published.

Run `python -m unittest tests.test_pgo_publication_guard tests.test_pgo_workflow_status tests.test_public_board_workflow` to check allowed mutable updates, rejected source/frozen-file drift, rename handling, tested ancestry, health reporting and workflow ordering.

### Accuracy and continuing model comparisons

The accuracy view derives its measures from saved forecasts and verified finals. Each metric states its own eligible count. Historical models are compared only on identical eligible games, and absent original probabilities or totals are not reconstructed. After-lock confidence entries remain visible in pool accounting but do not enter pregame probability scores. Expected pool points and NFL scoreboard points use different units.

Totals and weight/probability comparisons are fixed, separately issued forecasts. The updater grades existing pairs and captures eligible future pairs without refitting or changing the main forecast. All earlier pairs remain immutable. The new defensive depth capture is descriptive; fitting an injury effect remains blocked by absent historical role timing. The existing penalty experiment retains its original definitions. Each component has independent runtime status in the public view and Actions summary. See [the September 10 update](model-update-2026-09-10.md) for methods and findings.

### Spread records

The primary W/L/T record is straight-up. The separate spread view reports PGO's model line, the saved sportsbook line, winner-pick coverage and ATS-choice coverage. Its PGO-line check measures exceeding, falling below or matching the original projected margin; it is distinct from market ATS and from margin accuracy.

`pgo_ats.py` reads the archived ESPN scoreboard used by the season updater, validates the DraftKings provider, signed home/away handicaps and exact event/team/kickoff identities, and saves source evidence with the selection. A source observation at most 60 minutes old may supply a newly issued line. This is a capture-age limit, not a claim that ESPN supplies a bookmaker publication timestamp. Unlocked quotes may refresh; after T-60 the last saved line and choice cannot change. A failed refresh retains an earlier valid quote with its original clock and stale reason. The durable writer rechecks the actual cutoff, and later readers verify archived quote hashes even after current source captures rotate.

A missing pre-lock sportsbook quote excludes that game from sportsbook records. It does not erase an authentic original PGO forecast or its independent model-line check. Pushes, no-edge selections, pending games and unavailable lines remain separate. ATS does not reallocate confidence points or reuse straight-up win probability as a cover probability. No paid feed, new model fit or betting-profit calculation is introduced.
