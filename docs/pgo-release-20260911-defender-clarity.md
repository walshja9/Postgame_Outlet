# September 11: defender evidence and clearer records

New defensive captures retain named roster, depth, availability and prior-usage records, including explicit unknown history. A separate source-verified reader can compare that original inventory with later playing-time reports. It does not identify causal replacements, fit injury deductions or revise predictions. Old captures without the inventory remain unavailable.

The update also collects post-lock availability context in the same run when a forecast refresh crosses T-60. New alert issues are confirmed through their exact ID as well as duplicate checks; malformed responses yield fixed diagnostic categories. Off-days link to the next matchup and full saved slate, winner records explain straight-up grading, and accuracy counts distinguish pending scores from exclusions.

Source: `7cadcaa`, with retained-inventory wording repair `10074bc58c024808f756063c2ce09cbfa8d633cd`.

## Verification

- Independent delivery, defender and UI review completed. The malformed-comment response finding was repaired and regression-tested. A later review corrected the wording for a retained inventory after a blocked refresh.
- Exact scheduled-update gate: 219 tests passed locally (28.853 seconds) and in production workflow [34653036810](https://github.com/walshja9/Postgame_Outlet/actions/runs/34653036810) (17.663 seconds). The alert suite also passed under Python 3.12. These counts overlap and are not added together.
- Full release workflow [34652998914](https://github.com/walshja9/Postgame_Outlet/actions/runs/34652998914): succeeded on the exact source 10074bc. Main suite: 895 tests run in 705.386 seconds, 894 passed and 1 skipped; both supplemental suites passed 14 each. Total: **922 passed, 1 skipped**. Final render 447fe43375001b2aae01507cc0cbba16e9b941b2 and Pages 34654076061 succeeded; index, Forecast Lab and CSS matched Git bytes again at 22:28:28 UTC.
- Actual archive `runs-v2/20260911T221428752349Z` durably saved at `2026-09-11T22:14:46.083921+00:00`. Source replay verified 1,194 defenders, 32 teams, 14 pre-lock games and 2,963 roster identity rows. All 16 saved pick values and both locked game records were preserved against the pre-release archive; injury adjustment remains null.
- Season publication `e546708906d9057e76e2b5f6452b709a7194b227`, Pages [34653339524](https://github.com/walshja9/Postgame_Outlet/actions/runs/34653339524), succeeded. At `22:19:06 UTC`, public index, Forecast Lab and CSS matched exact Git bytes. The Shopify iframe displayed the new inventory count, full-slate link and straight-up heading. The PGO panel had no horizontal overflow at 390px viewport width (286px panel); wide tables retain their existing scroll containers. Temporary viewport overrides were reset.
- Normal notification health result was `healthy`, with `can_resolve: true`. No extra test issue or recipient was introduced. This does not establish inbox receipt.

Detailed local receipts, source replay, test logs and review notes are retained under ignored `output/defender-clarity-20260911/`. No original forecast, quote, earlier study charter, capture or attempt was rewritten. The usage reader remains a separate descriptive command; later snap-source reports require a fresh retained observation after verified finals. No model improvement is claimed from these software checks.
