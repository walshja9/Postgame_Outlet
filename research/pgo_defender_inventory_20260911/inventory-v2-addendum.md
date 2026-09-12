# Inventory version 2: dated inactive roster context

Declared September 12, 2026 before version 2 production captures. DESCRIPTIVE / NOT IN MODEL.

Version 1 preserved the previously constructed ACT/RES/DEV/EXE defender cohort. It omitted provider INA rows, even when those rows retained current team identities. Its saved captures, counts, unavailable subset and replay remain unchanged.

New version 2 captures additionally retain INA defenders with stable identities, dated roster season/week/game type where supplied, depth positions and prior history. Team summaries separately count these roster-inactive defenders. INA is a provider roster label, not an injury diagnosis or proof that a player will miss an upcoming game. INA alone never sets the unavailable flag; existing reserve-status and verified official-report rules remain unchanged. Existing ACT/RES/DEV/EXE role-summary semantics are unchanged.

The scheduled season writer explicitly requests version 2. The capture function keeps version 1 as its compatibility default. The reader replays each saved version using that version's rules and rejects unsupported versions. Never recreate a version 1 capture with version 2 membership or admit later roster status as earlier evidence.

All original protocol source, identity, missingness, final-result and durable T-60 requirements remain in force. Version 2 uses the same detached usage join. Missing histories and target rows remain unknown. No injury deduction, replacement-quality estimate, model fitting, forecast update or prospective accuracy claim follows from the added coverage.
