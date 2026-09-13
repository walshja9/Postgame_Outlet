# Historical injury source admission findings

Reviewed September 13, 2026. Initial checkout: `70c54db3de2e4b31dfb4c3b498a7eb0250a84ebb`. **No historical game was newly admitted. Fitting remains blocked.** These are source-admission findings, not defects in the existing charters or permission to alter an experiment.

The prior report02 receipt reports 63 verified inputs. This pass reused that receipt; it did not freshly rehash all 63 inputs. This pass freshly rehashed only the four report members and 14 historical raw sources (13 pinned injury files plus the schedule). It did not rerun fitting, reconstruct features or revise the previous diagnostic. The executed [audit](audit_review.py) and [result](audit01.json) retain each source's metadata, all per-season prior counts, and the bounded checks below. Raw HTTP bodies and receipts are retained in the named subdirectories. Initial captures occurred at 2026-09-13 05:02:50-05:02:51 UTC; follow-up data/code captures at 05:03:40 UTC. The later GitHub documentation capture has its own exact clocks in its receipt.

### [SOURCE-01] Keep current annual files outside historical pregame admission

- **Evidence:** `research/pgo_nonqb_validation_20260912/charter.md:16` requires pre-T60 evidence and distinguishes modification time from archived source versions. `research/pgo_nonqb_validation_20260912/report02/source-admission.json:12` remains REVIEW REQUIRED. The official [injury dictionary](https://nflreadr.nflverse.com/articles/dictionary_injuries.html) defines `date_modified` as the update time of injury information; the [loader](https://github.com/nflverse/nflreadr/blob/main/R/load_injuries.R) selects one season file, with no as-of version parameter. Actual release metadata is retained in `injuries-release/response.bin`.
- **Impact:** A season-end status or a later corrected row could be mistaken for the information available at the model's decision time. An old record timestamp does not identify which saved source bytes were then available.
- **Effort:** L for historical source recovery; feasibility is not established. This bounded audit is complete.
- **Risk:** HIGH if retrospectively published files are admitted as pregame inputs; no risk to existing forecasts from retaining the block.
- **Confidence:** HIGH for the observed admission gap and metadata; no claim that all possible historical archives are absent.
- **Fix sketch:** Require source-specific original-version publication evidence before admitting historical features. Keep each failed/missing admission explicit. Do not fill missing clocks or use the corrected identity package as timing evidence.

Actual repository observations:

| Source | Observed source metadata | Permitted claim / limit |
|---|---|---|
| `injuries_2013.csv` | Asset created July 26, 2022; 689,228 bytes | Current hosted object is retrospective to 2013; its date does not prove 2013 availability. |
| `injuries_2018.csv` | Asset created July 26, 2022; 665,119 bytes | Same retrospective limitation. |
| `injuries_2024.csv` | Asset created February 13, 2025; 816,989 bytes | Current hosted version postdates the 2024 regular season. |
| Current `injuries_2025.csv` | Asset created September 7, 2026 at 12:23:41 UTC; SHA `873ca1606dd575bd01152508a243ef6b3a0f8f97b90b707217e62ee8c7ceb735` | Actual HTTP 200 file exists, but is retrospective and has no `date_modified` column. |
| Pinned 2025 source | SHA `15ee790fef634caea988e7b6562fc393a63739dd7ee38229d1b42161427709df` | Preserved unchanged; differs from the current remote bytes. Both contain 5,477 relevant REG non-QB records without usable update clocks. |
| Official availability documentation | Still says injury source ended after 2024 and 2025 data unavailable | Documentation is stale relative to the observed 2025/2026 release assets. Do not use this text to deny the files' existence or infer their provenance. |

The current 2025 file contains 6,068 total records, 5,783 REG records, of which 5,477 are non-QB, 224 QB and 82 special teams. Its byte change from the pinned source does not remedy timing admission. These counts were recomputed from the retained response. The previous qualified identity package still has scope STRICT_HISTORICAL_IDENTITY_ONLY; it does not establish report vintage or completeness.

### [SOURCE-02] Investigate the narrow 2024 injurybot publication lead without admitting it

- **Evidence:** `source-review/injurybot-release/response.bin` contains 114 game assets; 105 match the pinned 2024 REG schedule. Of those, 101 asset-update timestamps precede T60 and four do not. Retained producer code `injurybot-fetch/response.bin:25` selects presentation columns without GSIS; `injurybot-auto/response.bin:72` saves/uploads one game-named RDS object. Two downloaded samples and their full decoded records are in `audit01.json`.
- **Impact:** This is a concrete possible historical subset, covering weeks 12-18 of 2024, rather than a reason to treat all 2013-2025 rows as admitted. Current annual files do not expose these older game-specific versions.
- **Effort:** M for a bounded provenance/identity/completeness qualification spike; full historical reconstruction effort is unknown.
- **Risk:** MED: accepting filename dates, repository metadata or a presentation table without the remaining checks would create false source admission. A current code commit does not prove the historical producer version.
- **Confidence:** HIGH for counts and sample contents; MED for whether sufficient independent publication/completeness proof can be obtained.
- **Fix sketch:** For a separately declared subset, retain stable asset IDs, exact bytes/hash and pre-T60 creation/update evidence; corroborate what those timestamps attest. Then resolve identities through qualified dated roster evidence and verify complete official reports for both teams. Admit no row until all checks pass; a social post or official archived report could corroborate original publication, but none was fetched or qualified here.

The [injurybot release](https://github.com/nflverse/nflverse-injurybot/releases/tag/injuries_2024) was created November 22, 2024. Its current API says `immutable=false`; older assets have no stored digest field. This alone does **not** prove that their historical timestamps are invalid. [GitHub's documented asset API](https://docs.github.com/en/rest/releases/assets?apiVersion=2022-11-28) identifies assets by ID and exposes creation/update metadata; the edit endpoint documents name, label and state fields. Therefore asset identity plus bytes and timestamp provenance is a legitimate candidate witness to investigate, not automatic qualification or automatic rejection.

The four late assets are `2024_12_BAL_LAC` and `2024_12_DET_IND` (after kickoff), `2024_13_NYG_DAL` and `2024_18_CLE_BAL` (after T60). They cannot supply the selected pre-T60 version in their observed form. No older replacement version was recovered.

The sampled `2024_12_ARI_SEA.rds` has 22 rows and was uploaded November 24, 2024 at 17:04:07 UTC, before its game cutoff. `2024_12_DET_IND.rds` has 16 rows and was uploaded at 20:37:30 UTC, after its game kickoff. Both contain team, position, full name, weekday practice text and game-status text; neither contains GSIS, an exact report/capture timestamp, or an explicit complete-report attestation. Provider missing game designations were retained as null, not converted to healthy.

### [SOURCE-03] Require complete team reports before constructing zero absence burden

- **Evidence:** `research/pgo_nonqb_validation_20260912/audit_sources.py:94` explicitly records complete-report coverage as unknown. Its `season_summary` counts teams with any row, which cannot certify an entire team report. `source-review/injurybot-game/response.bin:35` groups only teams appearing in injury rows; `injurybot-auto/response.bin:47` skips an empty game table. The existing non-QB charter at lines 18-20 preserves missingness by design.
- **Impact:** Treating missing reports or omitted players as healthy would create artificial zero-burden controls and contaminate an offense/defense comparison even after stable player IDs are fixed.
- **Effort:** M for an explicit coverage-admission check against original complete reports; historical source acquisition is uncertain.
- **Risk:** HIGH if unknown report coverage is silently converted to zero. LOW for keeping unknowns/exclusions visible.
- **Confidence:** HIGH for the missing completeness evidence in inspected sources.
- **Fix sketch:** Require a dated complete report for each game/team, including an explicit no-designation/empty-report condition when applicable. Distinguish report completeness from whether an individual player has an injury row. Missing prior usage also remains missing; complete reports do not establish player quality or point effects.

No numerical feature walk, fit, publication, forecast edit, source-authority change or previous artifact rewrite occurred. Current-source retrieval proves what was available to this audit on September 13, 2026; it does not backdate that receipt to any historical game. The parent-owned experiment contract remains blocked at historical admission unless a separately reviewed source package closes these gaps.
