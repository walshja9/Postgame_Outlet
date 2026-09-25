# Task A editorial repair report

Status: COMPLETE locally, uncommitted. No production refresh, tracked page build, network capture, push, or deployment.

## Changes

- `generate_site.py`: the shared QB drawer loader now accepts the selected value and reuses a team QB section only when its opening has the selected full name and current value. A stale or ambiguous section falls back to the existing QB note or empty-state hint. Per-player overrides retain precedence.
- `data/writeups/{CHI,WAS,NYG,SEA}.md`: current team and QB prose reflects the selected QBs and current values. Seattle's Week 1 score is correctly a 13–10 win. Stale injury timelines were removed or dated; earlier games remain labeled by week.
- `data/writeups/{BUF,KC,MIN}.md`: full-name binding and current KC/MIN QB values restored. BUF's existing number and prose otherwise remain intact.
- Follow-up review corrected Minnesota's Wentz reference to “Week 1–2 appearances”; Murray started Week 1 and Wentz entered in relief.
- Twelve additional team writeups (`BAL,CLE,DAL,IND,LAC,LV,MIA,NE,NO,PIT,SF,TB`): current QB paragraphs now match current ratings notes. Each superseded QB paragraph is retained verbatim under `Quarterback: through Week 1 2026 (historical)`.
- `results.py`: CLI heading, ATS footer, and JSON metadata explicitly state that old games are regraded retrospectively using current ratings and fetched market lines. The grading math and game records are unchanged.
- Focused regressions in `tests/test_editorial_binding.py`; the existing QB drawer fixture in `tests/test_ratings_release.py` now includes an explicit identity and value.

## Red and green checks

- Initial red: `python -B -m unittest tests.test_editorial_binding tests.test_ratings_release` failed for the four mismatched QB drawers and unlabeled retrospective CLI output.
- Expanded red after value binding: `python -B -m unittest tests.test_ratings_release tests.test_editorial_binding` failed for the 12 stale-value team sections.
- Green: `python -B -m unittest tests.test_ratings_release tests.test_editorial_binding` — 31 tests passed after removing a Week 3-specific assertion that would reject a valid future starter change. The dynamic 32-team binding check and focused fallback fixtures remain.
- The same focused command passed after the Minnesota wording correction; `git diff --check -- data/writeups/MIN.md` passed.
- `git diff --check -- generate_site.py results.py tests/test_ratings_release.py data/writeups` passed (only existing LF/CRLF checkout warnings); `git diff --exit-code -- data/ratings.csv data/snapshots.json` passed.
- Verified the 12 prior QB paragraphs against `HEAD` byte-decoded content: all are retained verbatim beneath dated historical headings.

## Scope clarification and limits

`results.py` has no HTML renderer; its output paths are CLI text and JSON. Generated ratings-page HTML takes the corrected writeups and dated historical headings. The retrospective grade disclosure is present in the CLI/JSON; no new HTML results page was added.

The opening identity/value check is deliberately strict. Future writeups without a full QB name and current value at the start of the canonical section use the existing note fallback until corrected. Per-player override files are independent editorial content and are not value-checked by this team-section guard.

No numerical ratings, snapshots, archived forecasts, or published pages were edited.
