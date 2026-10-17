# RC-030 C3 — Complete Worktree Inventory (Phase 0)

Recorded prior to any staging for C3.

## HEAD / branch

- HEAD: `35d432eddf032f4d6283bbe27f51528909b5e303` (C2)
- Branch: `main`
- Parent of HEAD: `aa753317617f6871f8faff4e7c795bc920e9df75` (C1)
- Base of the RC-030 program: `394818675b0ed199e03cae1d89e38a488f5102ce`

**Required check — HEAD exactly equals C2 commit: PASS.**

## Staging area

`git diff --cached --name-status` — empty. **Staging area initially empty: PASS.**

## Tracked modifications

`git status --short` shows zero `M`/`MM`/`AM` entries. **No tracked production-code modification remains: PASS.** C1 and C2 files are clean (no diff against HEAD).

## Untracked paths (141 entries from `git status --short`)

Full raw listing captured via `git status --short` before any C3 action. Broken down by category:

| Category | Count (approx.) | Examples |
|---|---|---|
| RC-030 governance `.md` reports | 55 | `RC030_FULL_REPAIR_BASELINE.md`, `RC030_AUTHORITATIVE_RANGE_MIGRATION_PROPOSAL.md` |
| RC-030 generated `.json` evidence/manifests | 20 | `RC030_RANGE_REPROCESS_MANIFEST.json` (304 KB), `RC030_RANGE_REBUILD_DIFF.json` (109 KB) |
| AI/owner audit event stores (`.json`) | 6 | `RC030_AUTONOMOUS_AI_AUDIT_EVENTS.json` (93 KB), `RC030_AI_PRE_REVIEW_EVENTS.json` (75 KB) |
| Owner review batch exports | 49 files across 2 dirs | `pilot_review_batch/crt_*.json`, `pilot_review_batch_v2/crt_*.json` |
| `dose_verification_sandbox` Part III source (untracked `.py`) | 4 + 1 schema | `precision_calculator.py`, `validation_unit.py`, `verdict_taxonomy.py`, `owner_fidelity_events.py`, `owner_fidelity_event_schema.json` |
| `dose_verification_sandbox` tests for the above (untracked) | 2 | `tests/dose_verification_sandbox/test_owner_pilot_consolidation.py`, `test_targeted_recovery_pilot.py` |
| Non-RC-030 governance docs (different stream, already closed) | 3 | `P56_GOVERNANCE_HARDENING_CLOSURE_REPORT.md`, `_FRESH_CLONE_REPORT.md`, `_STAGED_AUDIT.md` |
| Session/handoff docs (out of RC-030 scope) | 2 | `SESSION_HISTORY.md` (115 KB, raw session transcript), `SESSION_SUMMARY.md` |
| Historical unrelated artifact | 1 | `RECOVERY_TRACKED_FILES.txt` — a stale `git status` dump referencing a pre-refactor repo layout (`antibiotic_calc.html`, `db/`), unrelated to `medical_normalizer`/`clinical_engine` |
| Generated data (non-RC-030) | 2 | `CORPUS_MANIFEST.json` (210 KB), `medical_dictionary/unknown_drugs.csv` (83 KB) |
| Large generated directories | 2 | `generated/` (34 MB — PDFs, page crops, MinerU/Docling/RapidTable/DocLayout-YOLO raw outputs, owner-review HTML, one SQLite), `dose_verification_sandbox/data/` (15 MB — gitignored by `.gitignore` line 95-97) |
| Misc inventory dump | 1 | `REPOSITORY_UNTRACKED_INVENTORY.json` (68 KB) |

## Ignored paths

`git status --ignored --short` — 217 entries (`!!`), dominated by `.venv/`, `__pycache__/`, `*.sqlite`/`*.db` (authoritative DBs, correctly gitignored), `.mypy_cache/`, `.pytest_cache/`, `backups/`.

## Generated SQLite artifacts (must stay excluded)

- `generated/rc030_range_rebuild/assembled_regimens_range_v2.sqlite` — experimental, non-authoritative
- `assembled_regimens.sqlite`, `kb_final.db`, `kb_p44.db`, `review_workbench_p56.sqlite` — authoritative, gitignored, untouched

## Generated JSON artifacts (evidence-scale, must stay excluded)

`RC030_RANGE_REPROCESS_MANIFEST.json` (304 KB, 365-row payload), `RC030_RANGE_REBUILD_DIFF.json` (109 KB), `RC030_AUTONOMOUS_AI_AUDIT_EVENTS.json` (93 KB), `RC030_AI_PRE_REVIEW_EVENTS.json` (75 KB), `REPOSITORY_UNTRACKED_INVENTORY.json` (68 KB), `RC030_MISSING_PDF_MANIFEST.json` (61 KB, per-PDF filenames), `RC030_VALIDATION_SAMPLE_MANIFEST.json` (51 KB), `RC030_AI_AUDIT_PASS1.json`/`PASS2.json` (33/21 KB), `RC030_FULL_REPAIR_PILOT_REPLAY.json` (21 KB), `RC030_MAXIMUM_RANGE_DISAMBIGUATION.json` (15 KB), `RC030_MAX_DOSE_OWNER_QUEUE.json` (15 KB), `RC030_AI_OWNER_CONTROL_SAMPLE.json` (13 KB), `RC030_TARGET_PAGE_MANIFEST.json` (10 KB), `RC030_OWNER_PILOT_QUEUE.json` (5 KB), `CORPUS_MANIFEST.json` (210 KB).

## HTML interfaces

All under `generated/rc030_recovery/` — `RC030_OWNER_REVIEW_INTERFACE.html`, `RC030_OWNER_CONTROL_SAMPLE_INTERFACE.html`, plus `backups/` copies. Not staged.

## Owner exports

`pilot_review_batch/` (26 files) and `pilot_review_batch_v2/` (23 files) — per-task JSON exports (`crt_*.json`). Not staged.

## AI audit event files

`RC030_AI_AUDIT_PASS1.json`, `RC030_AI_AUDIT_PASS2.json`, `RC030_AI_PRE_REVIEW_EVENTS.json`, `RC030_AUTONOMOUS_AI_AUDIT_EVENTS.json`, `RC030_AI_OWNER_CONTROL_SAMPLE.json`, `generated/rc030_recovery/_ai_audit_blinded_input.json`. Not staged.

## Temporary scripts / caches / logs

None found as loose files outside `generated/` (which is entirely excluded) and the standard ignored cache directories (`.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`).

## Previous Part-III artifacts

`dose_verification_sandbox/precision_calculator.py`, `validation_unit.py`, `verdict_taxonomy.py`, `owner_fidelity_events.py`, `owner_fidelity_event_schema.json`, and their tests — self-identified by `RC030_FULL_REPAIR_IMPLEMENTATION_REPORT.md` line 18 as "unrelated to this repair; classified separately." Treated as out of C3 scope (see classification matrix — category H, owner decision required).

## Result

HEAD, staging area, and tracked-file cleanliness all match the required Phase 0 preconditions. No tracked production-code modification exists that would need classification before proceeding. Full untracked inventory recorded above feeds Phase 2 classification.
