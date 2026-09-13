# Current prospective readiness review

Audit status: **BLOCKED_DIRECT_PROVIDER_HISTORY_NOT_ADMITTED**.

The pinned current archive replays successfully, but it cannot yet produce the charter's new confirmed-absence feature. The direct provider `offense_pct` and `defense_pct` history, including explicit zero games, was not built or calculated in this audit. No coefficient was fit and no source or current-state file was changed.

## Current evidence

- HEAD: `70c54db3de2e4b31dfb4c3b498a7eb0250a84ebb`
- Current pointer: `runs-v2/20260913T045508716190Z`; checked `2026-09-13T04:55:08.716190+00:00`; pointer unchanged during replay: `true`.
- Slate: 16 issued games, 2 finals, and 14 future games. Offensive and defensive postgame usage each have 0 joined games; 14 games remain pending.
- Availability: 13/14 future games and 26/28 teams have the current archive. Missing: DEN, KC (2026_01_DEN_KC).
- Team report statuses: {'UNKNOWN': 2, 'VERIFIED_REPORT': 26}. Final inactive statuses: {'UNKNOWN': 28}.
- Documented injury OUT: offense 9, defense 13. Documented injury INACTIVE: offense 0, defense 0.

## Legacy coverage hints

These are diagnostics from the old `role_observations` path. They keep positive observations and use a maximum-player denominator. They are not direct provider percentages, they do not preserve explicit zero games, and their sums are not values of the proposed feature.

- Offense: 635/966 current players and 7/9 documented absences have a legacy hint.
- Defense: 726/1049 current players and 13/13 documented absences have a legacy hint.
- Missing documented-absence legacy hints: NO Oscar Delp (TE); PHI Eli Stowers (TE).

## Per-game report and absence counts

| Game | Reports (away/home) | Final inactive lists | Off OUT/INA | Def OUT/INA | Legacy hints all O;D (known/missing) | Documented absences (known/missing) |
|---|---|---|---:|---:|---:|---:|
| `2026_01_ATL_PIT` | ATL VERIFIED_REPORT; PIT VERIFIED_REPORT | ATL UNKNOWN; PIT UNKNOWN | 1/0 | 1/0 | O 40/26; D 53/22 | 2/0 |
| `2026_01_BAL_IND` | BAL VERIFIED_REPORT; IND VERIFIED_REPORT | BAL UNKNOWN; IND UNKNOWN | 0/0 | 3/0 | O 45/23; D 42/29 | 3/0 |
| `2026_01_BUF_HOU` | BUF VERIFIED_REPORT; HOU VERIFIED_REPORT | BUF UNKNOWN; HOU UNKNOWN | 0/0 | 0/0 | O 47/22; D 56/22 | 0/0 |
| `2026_01_CHI_CAR` | CHI VERIFIED_REPORT; CAR VERIFIED_REPORT | CHI UNKNOWN; CAR UNKNOWN | 0/0 | 1/0 | O 52/21; D 53/27 | 1/0 |
| `2026_01_CLE_JAX` | CLE VERIFIED_REPORT; JAX VERIFIED_REPORT | CLE UNKNOWN; JAX UNKNOWN | 1/0 | 0/0 | O 42/24; D 51/25 | 1/0 |
| `2026_01_NO_DET` | NO VERIFIED_REPORT; DET VERIFIED_REPORT | NO UNKNOWN; DET UNKNOWN | 2/0 | 1/0 | O 50/22; D 53/25 | 2/1 (NO Oscar Delp) |
| `2026_01_NYJ_TEN` | NYJ VERIFIED_REPORT; TEN VERIFIED_REPORT | NYJ UNKNOWN; TEN UNKNOWN | 1/0 | 2/0 | O 43/22; D 63/17 | 3/0 |
| `2026_01_TB_CIN` | TB VERIFIED_REPORT; CIN VERIFIED_REPORT | TB UNKNOWN; CIN UNKNOWN | 0/0 | 0/0 | O 40/22; D 49/22 | 0/0 |
| `2026_01_ARI_LAC` | ARI VERIFIED_REPORT; LAC VERIFIED_REPORT | ARI UNKNOWN; LAC UNKNOWN | 1/0 | 3/0 | O 48/25; D 50/21 | 4/0 |
| `2026_01_GB_MIN` | GB VERIFIED_REPORT; MIN VERIFIED_REPORT | GB UNKNOWN; MIN UNKNOWN | 0/0 | 1/0 | O 43/27; D 52/23 | 1/0 |
| `2026_01_MIA_LV` | MIA VERIFIED_REPORT; LV VERIFIED_REPORT | MIA UNKNOWN; LV UNKNOWN | 1/0 | 0/0 | O 41/30; D 47/29 | 1/0 |
| `2026_01_WAS_PHI` | WAS VERIFIED_REPORT; PHI VERIFIED_REPORT | WAS UNKNOWN; PHI UNKNOWN | 1/0 | 1/0 | O 50/18; D 55/19 | 1/1 (PHI Eli Stowers) |
| `2026_01_DAL_NYG` | DAL VERIFIED_REPORT; NYG VERIFIED_REPORT | DAL UNKNOWN; NYG UNKNOWN | 1/0 | 0/0 | O 50/20; D 55/19 | 1/0 |
| `2026_01_DEN_KC` | DEN UNKNOWN; KC UNKNOWN | DEN UNKNOWN; KC UNKNOWN | 0/0 | 0/0 | O 44/29; D 47/23 | 0/0 |

The legacy columns report known/missing coverage. The last column applies only to documented absences and names any missing player. Both are coverage warnings, not feature calculations.

## Charter gaps

- The direct provider offense_pct and defense_pct history required by the charter has not been built or replayed, so explicit zero games and the required denominator are unverified.
- DEN and KC have no current versioned availability archive for 2026_01_DEN_KC; report completeness is 26 of 28 future teams.
- All 28 future-team final-inactive statuses are UNKNOWN; documented game-day inactive absences are not yet observed.
- The 14 prospective games have no final targets or postgame usage joins. The two existing finals predate eligible inventories.
- The legacy positive-only role path lacks hints for NO TE Oscar Delp and PHI TE Eli Stowers. This is a coverage warning only and does not establish whether direct provider history exists.
- The saved defensive confirmed_unavailable population mixes 121 reserve-roster rows with 13 documented OUT rows and cannot define the charter population.
- Historical injury timing, identity, completeness, and source-vintage gates remain unadmitted; no historical substitution or fitting is allowed.
- The prospective minimums of 200 games, 12 weeks, all 32 teams, 50 nonzero observations per unit difference, and a rank-two feature matrix are unmet.

The current evidence therefore supports collector and source-gap review only. The study remains source-admission blocked and has no admissible numerical feature values or training rows.
