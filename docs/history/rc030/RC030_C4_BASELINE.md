# RC-030 C4 — Baseline (Phase 0)

## HEAD / branch

- HEAD before any C4 work: `d79bb3c98f16b2c425f3f6247e07c5db5f46d72c` (C3)
- Branch: `main`
- Parent chain: C3 → C2 (`35d432eddf032f4d6283bbe27f51528909b5e303`) → C1 (`aa753317617f6871f8faff4e7c795bc920e9df75`) → base (`394818675b0ed199e03cae1d89e38a488f5102ce`)

**Required check — HEAD equals C3: PASS.**

## Staging area / tracked files

`git diff --cached --name-status` — empty. `git status --short` shows zero `M`/`MM`/`AM` entries against any C1/C2/C3 tracked file. **Staging area empty, C1/C2/C3 clean: PASS.**

## Candidate C4 paths (discovered from worktree, not assumed)

```
dose_verification_sandbox/precision_calculator.py
dose_verification_sandbox/validation_unit.py
dose_verification_sandbox/verdict_taxonomy.py
dose_verification_sandbox/owner_fidelity_events.py
dose_verification_sandbox/owner_fidelity_event_schema.json
```

## Candidate C4 test paths (discovered)

```
tests/dose_verification_sandbox/test_owner_pilot_consolidation.py   (pre-existing, 18 tests)
tests/dose_verification_sandbox/test_targeted_recovery_pilot.py     (pre-existing, 10 tests)
tests/dose_verification_sandbox/test_c4_governance_hardening.py     (new this turn, 53 tests)
```

`test_targeted_recovery_pilot.py` was inspected: it exercises `owner_fidelity_events`/`precision_calculator` behavior identical in spirit to `test_owner_pilot_consolidation.py` (synthetic-only, same modules) — both are genuine C4 test material, not a separate concern, and are included.

No other untracked `.py` file references any of the four modules by import (checked via `grep -rl` across the full untracked-file inventory) — the candidate list above is complete.

## Previous Part III files (context, not candidates)

`models.py`, `parser.py`, `calculator.py`, `evidence_model.py`, `golden.py`, `issues.py`, `pilot.py`, `snapshot.py`, `verify.py`, `ambiguity_workflow.py`, `semantics_*.py`, `validation_status.py` are already committed (C1, `aa75331`) and out of scope for C4 — untouched.

## Owner interface files

`generated/rc030_recovery/RC030_OWNER_REVIEW_INTERFACE.html`, `RC030_OWNER_CONTROL_SAMPLE_INTERFACE.html` — untracked, under `generated/`, explicitly excluded from C4 per owner authorization ("inclusion of owner HTML interfaces in C4" not authorized). Untouched.

## AI audit files

`RC030_AI_AUDIT_PASS1.json`, `RC030_AI_AUDIT_PASS2.json`, `RC030_AI_PRE_REVIEW_EVENTS.json`, `RC030_AUTONOMOUS_AI_AUDIT_EVENTS.json`, `RC030_AI_OWNER_CONTROL_SAMPLE.json` — untracked, explicitly excluded ("inclusion of AI audit event datasets in C4" not authorized). Untouched; used only as read-only reference material to confirm the AI event field vocabulary (`review_origin`, `owner_verified`, `clinically_approved`, `human_validated`) that the hardened `owner_fidelity_events.py` now explicitly rejects.

## Owner event exports

No real owner-event export file exists anywhere in this worktree for regimen 6657 or any other regimen (searched `dose_verification_sandbox/data/`, `generated/`, and the full untracked inventory — none found). `RC030_FULL_REPAIR_BASELINE.json` records `"owner_events": 1` as a fact but the underlying export file is not present on disk. Phase 13 (regimen 6657 compatibility) is therefore satisfied with a schema-compliant **synthetic** reproduction of the documented facts, not a copy of a real file — see `test_c4_governance_hardening.py`'s `_regimen_6657_synthetic_event()` and its docstring.

## Generated artifacts

`generated/` (34 MB) and `dose_verification_sandbox/data/` (15 MB, gitignored) untouched — not read or written by any C4 code path (verified: none of the four modules perform file I/O; see `RC030_C4_ARCHITECTURE_AUDIT.md`).

## Database hashes (pre-C4)

| Database | SHA-256 |
|---|---|
| `assembled_regimens.sqlite` | `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9` |
| `kb_final.db` | `16c31fba2ecafbb9d6bf7c5bc54afee5b46e41d6088cc0ac10492c852abd67dd` |
| `review_workbench_p56.sqlite` | `3e479ee70e59ce9aafa6ba44718dda68d867dbcc660796b81ff63d2b19ca0f29` |

## Safety state (pre-C4, directly measured)

- `calculation_eligible` = 0 (0 of 2675 rows have `approved_by` set; none pass `TYPES_MEETING_PRECISION_THRESHOLD`)
- `approved_objects` = 0
- `TYPES_MEETING_PRECISION_THRESHOLD` = `set()` (`dose_verification_sandbox/validation_status.py:38`)
- `review_decisions` = 0 (`review_workbench_p56.sqlite`)
- `review_tasks` = 9153, all `lifecycle_state = PENDING`
- Clinical Engine: disconnected (live pipeline reads via `sqlite_reader.SQLiteReader`, not the `assembled_regimens`-backed shadow adapter — see prior C2 verification)

## Result

All Phase 0 preconditions hold: HEAD equals C3, staging area is empty, no C1/C2/C3 tracked file carries an uncommitted modification, and the exact C4 candidate set (4 modules + 1 schema + 3 test files) has been enumerated from the actual worktree rather than assumed. Proceeding to Part II (architectural boundary audit).
