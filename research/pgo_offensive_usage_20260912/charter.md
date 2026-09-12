# Offensive participation observation, version 1

Declared September 12, 2026 before offensive source-data inspection or results.

This is future-only descriptive collection at game/team/GSIS player grain. It
does not fit a model, assign injury weights, infer replacement quality, change
forecasts, or admit a predictive claim. Forecast adjustment stays null and
predictive status stays UNAVAILABLE. Rookies and absent history have no penalty.

The roster cohort is RB, FB, WR, TE and provider offensive-line positions C, G,
OG, LG, RG, T, OT, LT, RT and OL, with ACT, RES, DEV, EXE or INA status retained.
QB and special teams are excluded. Roster status alone never diagnoses injury.
Roster and depth source captures must be at most 24 hours old; all 32 current
teams must be represented. Preserve provider depth timestamps separately from
receipt clocks; an old or missing provider role remains unknown. Verify exact
archive hashes, stable unique identities, roster team membership, and names.
Availability comes only from verified saved game-specific official packages;
missing or stale reports remain explicitly unknown. No earlier membership or
prior-quality values are reconstructed.

For each verified final choose the latest actually durable offensive inventory
strictly before T-60, before examining its targets. Generated, source, provider,
availability, state and durable clocks remain distinct. Freeze the selected
pointer or missing-inventory exclusion on first observation. A corrupt selected
inventory blocks collection without fallback. The two already completed opening
games have no offensive inventory and remain excluded. A later roster cannot
backfill a missing prospective cohort.

Targets are preserved nflverse snap-count bytes, requiring offense_snaps. Reuse
the existing acquisition/receipt mechanism. Target capture must occur strictly
after the verified final observation. Join exact game, season, week, REG type,
team, opponent and unique roster PFR-to-GSIS identity. Count duplicate identities
before filtering malformed snap values. Explicit integer zero is observed zero;
missing, malformed, duplicate or ambiguous targets remain unknown. Preserve
source failures and bytes, chosen cohorts and immutable report bytes.

Report cohort rows, eligible final rows, joined rows, zero/positive observations,
missing targets, pending rows/games, invalid/unresolved source rows and coverage.
These measure descriptive collection only, not model accuracy or readiness.
Optional failures are separately BLOCKED and must not suppress season grading or
publication. No current or frozen defensive study semantics or bytes change.

Offline checks cover archive replay, all-team scope, status/position scope,
identity moves, unknown versus zero, malformed and duplicate targets, delayed
finals/targets, exact T-60 and durable crossing, immutable selection/exclusions,
failure retention and zero input mutation. A bounded real archived roster/depth
replay is engineering evidence only, never a prospective historical observation.
