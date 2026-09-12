# Injury usage admission — September 11, 2026

## September 12 follow-up

The new `source02` capture at 16:49:24 UTC returned HTTP 200, 16,543 bytes and
187 rows covering both NE–SEA and SF–LAR. `report03` repeats the original fixed
capture03 cohort against this release: **0 of 14 eligible final-game player rows
match**, and the other 122 cohort rows still await finals. The source now includes
SF–LAR, but it omits the unavailable defenders in this cohort. Omitted rows remain
unknown; this is not evidence that each player recorded zero defensive plays.

The [September 12 validation work](../pgo_nonqb_validation_20260912/README.md)
adds automatic checks of the separately captured full defender inventories.
No numerical injury adjustment has been admitted. Earlier source01/report01/report02
remain preserved; the original September 11 findings follow below.

**UNAVAILABLE / NO ADMITTED USAGE LINKS. Historical admission remains BLOCKED FOR FITTING.**

This extension replays the unchanged September 10 capture03 unavailable-defender cohort. It deliberately covers saved unavailable players (including reserve-list context), not every defender. Prior usage is preserved as prior usage; rookies and missing histories remain unknown. No numerical injury adjustment or automatic model adoption is implemented.

The actual 2026 snap-count source returned HTTP 200 with 8,397 bytes and 93 rows, all for `2026_01_NE_SEA`. That opener preceded this pregame capture and is excluded. The saved SF–LAR capture completed before T-60, and the verified season archive contains its final, but the target source has no SF–LAR rows. Thus 0 of 136 saved cohort player-games join, including 0 of 14 eligible final-game rows. The other 122 cohort rows lack a verified final. Fifty-eight cohort rows have unknown prior history; 134 have UNKNOWN official availability (reserve context does not establish an injury diagnosis).

- `charter.md`: locked descriptive contract before retrieval and construction.
- `source01/response.bin` and `source01/receipt.json`: original source bytes, URL, actual start/capture clocks, HTTP status, headers, raw hash and unknown publication clock.
- `report02/admission.json`: all cohort rows, unchanged roles/statuses/observations, source-row links when admitted, explicit exclusions, excluded target rows, coverage and timing.
- `report02/season-pointer.json`: exact verified season archive used.
- `report02/run-receipt.json` and `manifest.json`: code/test/charter/source-receipt hashes and immutable artifact inventory.

Replay into a new exclusive output directory:

```powershell
python -m research.pgo_injury_usage_20260911.audit --source research/pgo_injury_usage_20260911/source01 --output research/pgo_injury_usage_20260911/report03
python -m unittest tests.test_pgo_injury_usage -q
```

`audit.link(snapshot, roster, snaps, finals, target_captured_at)` is a pure descriptive join. The CLI verifies the pinned pregame manifest, preserved roster/depth bytes, actual target bytes/receipt and the existing verified current season archive. Targets require exact event/week/team/opponent and a unique preserved roster PFR-to-GSIS identity. Names never establish target identity. Explicit zero counts remain observed zeros; omitted players remain unknown. Duplicate, invalid, unmatched and late data cannot produce admitted values. Current target rows are not pregame predictors.

For a later actual snap release, create a NEW source directory with `response.bin` and `receipt.json`, then pass it through `--source`; never overwrite source01/report01. The receipt schema is the existing source01 receipt: exact URL, actual timezone-bearing started_at/captured_at, http_status, headers, raw bytes length and sha256, published_at only when independently known. Download only the source URL already recorded. A 200 response requires the tested source CSV schema; any non-200 response produces zero target rows with the failed HTTP receipt retained. Do not backdate retrieval to the game's date or turn an omitted player into zero snaps.

The next useful observation is a newly captured release containing SF–LAR, joined to these already-preserved pregame rows. Even a successful join establishes only descriptive usage coverage. Fitting or expected replacement quality requires a separate declared experiment and suitable accumulated chronological evidence.

## Review repair and latest replay

`report02` is the latest replay of unchanged source01, with its actual new execution clock and no new retrieval. It rejects all relevant target identity duplicates before count validation, so one valid zero plus one invalid NaN cannot admit zero. Final records must match both home_team and away_team. The two regression checks failed before repair and pass afterward. Ten injury checks plus eleven existing replacement-depth checks pass (21 total). Original report01 remains unchanged; its exact pre-repair code and tests are retained in `repairs/` and match the original run receipt pins. Both report manifests remain valid. The available-data result is unchanged: zero admitted usage links.
