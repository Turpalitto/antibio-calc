# P5.6 Review Governance Hardening — Final Report

Generated: 2026-07-15.

## What was fixed

| Defect | Root cause | Fix |
|---|---|---|
| **GOV-001** | `ReviewService` had no dependency on any reviewer identity system — any string was accepted as `reviewer`/`actor`/`adjudicator`. | `ReviewerRegistry.validate_reviewer_action()` (deterministic, never raises, returns `allowed`/`reason_code`/`reviewer_record_version`/`role`/`scope`/`checked_at`) is now called by every write path in `ReviewService` before any state change. Rejected attempts are audit-logged (`review_rejected_attempts`) without touching task state. |
| **GOV-002** | `packet()` returned the full task dict — including `decision`/`audit_history` — unconditionally; `GET /tasks/{id}` called it with no caller context. | `packet_for_reviewer(task_id, reviewer_id, role)` renders a role/state-aware view; while a task is in `SECOND_REVIEW`, Reviewer B's view has Reviewer A's `decision`, `first_decision`, `comments`, `reason_codes`, and `consensus_result` blanked, and every `SUBMIT_FIRST` audit event is rewritten with those fields empty. `GET /tasks/{id}` now requires `reviewer_id`+`role` query params and calls this instead of the raw packet. |
| **GOV-003** | `governance_state(ACCEPTED)` returned `"PHYSICIAN_APPROVED"` directly — no Medical QA Lead gate existed between two-reviewer consensus and the approved label. | New `ReviewState.MEDICAL_QA_PENDING` is the landing state for every consensus/adjudication outcome (accept or reject). `PHYSICIAN_APPROVED`/`REJECTED` are now only reachable via the new `submit_medical_qa_signoff()` method, which independently re-validates reviewer distinctness, provenance/source-wording completeness, and the untampered interaction-check literal before honoring an `APPROVE` verdict. |

## Additional hardening delivered beyond the three defects

- **Phase 3 — `ReviewAssignment`**: explicit, append-only, revocable task-level role assignment, separate from mere registration. Revoking an assignment blocks further decision submission under it, re-checked at `submit_first_review`/`submit_second_review` time.
- **Phase 8 — immutable decision ledger**: `review_decisions` table (append-only via SQLite triggers) records every `SUBMIT_FIRST`/`SUBMIT_SECOND`/`ADJUDICATE`/`MEDICAL_QA_SIGNOFF` as a structured, sequenced, never-updated record, independent of (and in addition to) the existing `AuditEvent` history.
- **Close semantics (Phase 7)**: `close()` now requires `PHYSICIAN_APPROVED`/`REJECTED`/`NEEDS_INFO`/`ABSTAINED` — i.e., a real QA sign-off (or a reviewer-level terminal outcome that never needed one) — and records an explicit `close_outcome` (`CLOSED_APPROVED`/`CLOSED_REJECTED`/`CLOSED_NEEDS_INFO`/`CLOSED_ABSTAINED`).
- **`TherapeuticOption` isolation**: `governance_state()` maps `PHYSICIAN_APPROVED` to the distinct `"MEDICALLY_REVIEWED"` label for `TherapeuticOption`, never `"PHYSICIAN_APPROVED"` — and the Clinical Engine's zero import dependency on `review_workbench` (re-verified, `test_30_no_clinical_engine_import_introduced`) means this can never become directly consumable as executable regimen data without a new, explicit, separately-reviewed wire-up.

## Phase 9 — migration safety

Pre-migration audit of `review_workbench_p56.sqlite` (schema v1): 9,153 tasks, **0 non-PENDING**, **0 decisions**, **0 audit events**, integrity OK. Backed up to `backups/p5_6_governance_hardening_pre_migration_20260715/` (SHA-256 verified byte-identical). Migration applied (10 additive columns on `review_tasks`, 3 new empty tables). Post-migration: 9,153 tasks preserved, all still PENDING, target-type counts unchanged, spot-checked pilot task byte-identical aside from new empty columns, integrity OK. Full detail: `P56_REVIEW_GOVERNANCE_MIGRATION_REPORT.md`.

## Phase 11/12 — test results

- **31 new tests**: 10 reviewer-registry unit tests (`test_reviewer_registry.py`), 30 numbered Phase-11 negative scenarios + 1 Phase-12 synthetic positive end-to-end workflow (`test_governance_hardening.py`), plus the updated `test_pilot_safety_checks.py` (15 tests, now asserting the *fixed* behavior for GOV-001/002/003 instead of documenting the gap).
- **All 30 negative scenarios pass** (fake/unregistered/inactive/expired-credential/wrong-role/wrong-scope reviewers rejected; administrator blocked from every clinical action; self-review blocked in both reviewer and QA-lead capacities; blinding verified at packet, history, and metrics level; direct-to-approved impossible; stale target/revision rejected; missing provenance blocks QA sign-off; duplicate QA sign-off rejected; decisions immutable at the database level; revoked assignments rejected; display-name spoofing rejected (identity is keyed on `reviewer_id` only); rejected attempts audit-logged without state mutation; approved-object count stays 0 through a full synthetic no-QA flow; Clinical Engine import-freedom re-confirmed).
- **Synthetic positive workflow** (`test_synthetic_positive_workflow_reaches_physician_approved`) drives a complete, real, non-fabricated code path — register 4 synthetic reviewers → assign → independent first review → confirm B is blinded → independent second review → `MEDICAL_QA_PENDING` → QA sign-off → `PHYSICIAN_APPROVED` → close → verify full immutable audit trail (7 events) and 3 recorded decisions — entirely inside a throwaway `tmp_path` database, never touching `review_workbench_p56.sqlite`.
- **Regression**: `clinical_engine/review_workbench/tests` + `clinical_engine/regimen/tests`: **149/149 passed**. Full canonical suite (`clinical_engine/ medical_normalizer/ src/tests/`, excluding `slow`/`corpus`/`ml`-marked tests): **1450 passed, 1 failed, 1 xfailed** in 376s. The 1 failure (`medical_normalizer/tests/test_medical_dictionary_loader.py::TestLoaderDrugAtc::test_empty_until_review`) is a pre-existing test-isolation ordering artifact, unrelated to this work — it passes standalone and passes when the whole `medical_normalizer/tests/` directory runs alone (823/823); no file this session touched `medical_dictionary`/`medical_normalizer` code. Canonical `pytest --collect-only`: **1452 tests** (was 1421 before this session's additions), zero collection errors.

## Phase 13 — final state verification

| Check | Result |
|---|---|
| 30 real pilot tasks remain `PENDING` | ✔ confirmed against the migrated `review_workbench_p56.sqlite` |
| Approved objects remain 0 | ✔ confirmed database-wide (9,153 tasks, not just the 30-task pilot) |
| No real reviewer registered | ✔ `ReviewerRegistry` is not instantiated with any real-world reviewer anywhere in this session; `pilot_status = WAITING_FOR_REVIEWERS` |
| No clinical decision added | ✔ 0 rows in `review_decisions`, 0 in `review_events` beyond schema/migration bookkeeping |
| Clinical Engine disconnected | ✔ re-verified, zero `review_workbench` import in `clinical_engine/engine.py`/`pipeline.py` |

## Repository state

No commit was created during this hardening work (not requested). All changes remain in the working tree on top of commit `32096af`. `git status --short` shows the modified/new review-workbench source, tests, and the documentation files listed below, plus the pre-existing untracked/excluded pile from the recovery program (unchanged).

## Documentation delivered (Phase 14)

New: `P56_REVIEW_GOVERNANCE_HARDENING_BASELINE.md`, `REVIEWER_IDENTITY_AND_ASSIGNMENT_POLICY.md`, `SECOND_REVIEW_BLINDING_SPEC.md`, `MEDICAL_QA_SIGNOFF_SPEC.md`, `REVIEW_CONSENSUS_STATE_MODEL.md`, `P56_REVIEW_GOVERNANCE_MIGRATION_REPORT.md`, this report.
Updated: `ROOT_CAUSE_REGISTER.md` (GOV-001/002/003 added, marked FIXED), `REVIEW_WORKFLOW_RFC.md`, `REGIMEN_APPROVAL_MODEL.md`, `CLINICAL_KNOWLEDGE_LIFECYCLE.md` (implementation-note pointers), `PROJECT_STATE.md`, `NEXT_TASK.md`, `AI_LOG.md`.

No claim is made anywhere in this documentation that physician review occurred — it has not.

---

## Exit gates — verified

✔ arbitrary reviewer strings rejected · ✔ registry validation enforced in service layer · ✔ explicit task assignments implemented · ✔ Reviewer A and B must differ · ✔ Reviewer B is blinded before submission · ✔ no service/API/history/metrics leakage found · ✔ consensus separated from approval · ✔ Medical QA sign-off mandatory · ✔ TherapeuticOption remains non-executable (label-distinct, Engine-disconnected) · ✔ decisions immutable · ✔ migration safe (verified before/after, backed up) · ✔ negative tests pass (30/30) · ✔ synthetic positive flow passes · ✔ real pilot tasks remain untouched (still 30/30 PENDING) · ✔ approved objects remain 0 · ✔ Clinical Engine remains disconnected

## Final verdict

**A) GOVERNANCE HARDENING COMPLETE — PILOT WAITING FOR REAL REVIEWERS**

P6 remains BLOCKED. Real Reviewer A, Reviewer B, and Medical QA Lead may now be registered per `REVIEWER_IDENTITY_AND_ASSIGNMENT_POLICY.md`.
