# Capture 01 follow-up

Capture 01 and its manifest are preserved unchanged. The exact executed module is retained as `capture01-capture.py.txt`, matching the receipt's code SHA-256. `capture01-test_pgo_replacement_depth.py.txt` preserves the eight-test pre-regression fixture source.

A new regression exposed a missing display case: an official observation can retain a resolved GSIS ID from its own source roster while that defender is absent from the latest roster used for current depth. The original capture builder silently omitted this observation. The repaired builder retains the name in `unresolved_official_names`; it never invents a current team role or injury value. The new test failed before the guard and passes afterward.

The same follow-up adds explicit archive `href` links to returned source references. Raw sources, capture01, historical admission and all prior experiments are unchanged. A new actual observation is recorded in capture02 with its own code hash and times. This is a descriptive source-display repair, not a model refit or historical-experiment retry.

## Capture 02 follow-up

Capture02 and its manifest remain unchanged. `capture02-capture.py.txt` matches its recorded code SHA-256; `capture02-test_pgo_replacement_depth.py.txt` preserves its nine-test source. A new regression proved that a verified archive can contain an UNKNOWN team report. Renaming `teams_with_verified_observations` to `teams_with_saved_observations` prevents the package-presence field from overstating report coverage; per-team report statuses are unchanged. The regression failed before the rename, then all ten tests passed. Capture03 records the corrected schema under a new code hash and real clock.
