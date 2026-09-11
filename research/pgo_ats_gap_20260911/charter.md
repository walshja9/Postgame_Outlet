# PGO saved-line benchmark and ATS gap monitoring — September 11, 2026

Protocol version 1. This charter is saved before the implementation's first
evaluation. Existing outcomes were already observed; the initial report is
descriptive. A local file clock is not proof of prior public publication.

## Question and population

Does a larger absolute difference between PGO's saved home winning margin and
the negative of the saved DraftKings home handicap correspond to a different
ATS record? The unit is one scheduled NFL regular-season game with an issued
PGO weekly forecast. Both team perspectives remain one game.

Decision time is kickoff minus 60 minutes. Admit only an internally consistent
saved DraftKings comparison issued strictly before this cutoff, with the quoted
ESPN response captured at or before issuance and no more than 60 minutes old.
Inputs must precede PGO issuance, which must precede comparison issuance. The
comparison's forecast identity, edition, clocks and unrounded margin must match
the current saved weekly forecast. Do not substitute an older retained PGO
comparison after the main forecast changed. Validate schedule, team, event and
final identities and clocks. Caller verifies the immutable archive and source
bytes; the report also replays quoted and final ESPN source content.

Missing, late, invalid, duplicate or inconsistent evidence is never a zero line.
Structural duplicate or unknown game identities invalidate the report; individual
ineligible rows receive reason codes. Pending games remain pending. Finals must
be saved explicit FINAL observations after kickoff and before the state clock.

## Fixed measurements

Primary benchmark: mean absolute home-margin error, using exactly the same
eligible final game IDs for PGO and DraftKings. Difference is PGO error minus
DraftKings error; a negative number favors PGO on those games. Keep full
precision until display. Secondary: both straight-up records on these same
games; zero model margin or pick'em is a separate no-pick, and an actual tie is
separate from wins and losses. This does not measure sportsbook closing lines.

ATS records are recomputed against the saved sportsbook handicap from final
scores. Positive absolute disagreement bands are fixed now:

- Exactly zero: no edge; no ATS suggestion.
- Greater than zero and less than 1 point.
- At least 1 and less than 3 points.
- At least 3 points.

Report wins, losses, pushes, pending, no-edge and unavailable cases with explicit
counts and game IDs. Pushes are not wins or losses. Do not estimate cover
probabilities, profit, recommended stakes or odds-adjusted returns. Do not use
these outcomes to choose a minimum gap, weight, band boundary or model version.

## Temporal and decision limits

There is no fitting, training window, hyperparameter search, threshold promotion
or model-adoption rule. This is an expanding descriptive ledger, not an untouched
holdout. Preserve the initial evaluation and every later attempt separately.
Each report pins the charter, implementation, tests, state pointer, manifest,
state payload and referenced source hashes. Replays may correct implementation
defects only in a new attempt with the reason recorded; never rewrite a result.

All observations remain descriptive, including newly arriving games. Prospective
research status is unavailable until a separate prior public protocol witness
and explicit cohort admission process have been verified. A larger sample alone
does not validate a selection threshold or establish a betting advantage.
