# Review Governance Hardening — Phase 0 Baseline

Generated: 2026-07-15. Reproduces GOV-001, GOV-002, GOV-003 against the pre-hardening code (as committed in `32096af`) using synthetic fixtures only — no real pilot task or real reviewer identity was touched.

## GOV-001 — ReviewService accepts arbitrary reviewer strings

- **Reproduction:** call `ReviewService.claim("task-1", reviewer="dr-imaginary-not-in-any-registry", role=ReviewRole.REVIEWER_A, expected_revision=0)` against a freshly seeded synthetic task. No `ReviewerRegistry` exists in the dependency graph of `ReviewService`.
- **Affected method:** `ReviewService.claim`, `.start_review`, `.submit_first_review`, `.submit_second_review`, `.adjudicate`, `.request_adjudication`, `.close`, `.add_note`, `.add_waiver` — all accept a bare `reviewer`/`actor`/`adjudicator`/`authority` string parameter with no existence or activity check.
- **Expected behaviour:** unknown or inactive reviewer identities must be rejected before any state change.
- **Actual behaviour (pre-fix):** the call succeeds; `task.assigned_reviewer == "dr-imaginary-not-in-any-registry"`. Demonstrated in `test_fake_reviewer_identity_not_rejected_by_service_layer` (previous session).
- **Affected task states:** `PENDING → CLAIMED` (and every subsequent transition) can be driven by any string.
- **Clinical impact:** none realized yet (pilot registry is empty, no real workflow has run), but this is the single technical control that stands between "any caller with API access" and "a clinical accept/reject decision attributed to a fabricated identity."
- **Governance severity:** **HIGH** — this is the root enabling condition for identity spoofing across the entire review pipeline.
- **Current workaround:** procedural only — this session's operator (Claude) simply does not call these methods with invented identities. Not a technical control.
- **Migration impact:** fixing this requires `ReviewService` to depend on a `ReviewerRegistry` and validate every actor before every write. No stored data needs migrating (no reviewer field format changes).

## GOV-002 — Reviewer B can see Reviewer A's verdict before independent submission

- **Reproduction:** seed a synthetic task, have `doctor-a` claim + submit `ACCEPT` as `REVIEWER_A` (task moves to `SECOND_REVIEW`), then call `ReviewService.packet("task-1")` — the *unauthenticated, role-blind* packet call, exactly what `GET /tasks/{id}` (`api.py::task_details`) invokes.
- **Affected method:** `ReviewService.packet()`, and transitively `api.py::task_details`, `api.py::export_packet`.
- **Expected behaviour:** while a task is in `SECOND_REVIEW` and has not yet received a second decision, any caller acting as (or capable of becoming) Reviewer B must not be able to see Reviewer A's `decision`, reason codes, or rationale, whether via the packet, audit history, or any derived summary.
- **Actual behaviour (pre-fix):** `packet()["task"]["decision"] == "ACCEPT"` and `packet()["task"]["audit_history"]` contains the full `SUBMIT_FIRST` event including its decision — visible unconditionally. Demonstrated in `test_reviewer_b_can_see_reviewer_a_verdict_via_packet_before_submitting` (previous session).
- **Affected task states:** `SECOND_REVIEW` (pre-decision).
- **Clinical impact:** breaks reviewer independence — a documented requirement of any credible two-reviewer clinical safety process; anchoring bias risk if a real second reviewer were exposed to this.
- **Governance severity:** **HIGH** — independence is the core value proposition of a two-reviewer design; without blinding it degrades to a single-reviewer process with a rubber-stamp second signature.
- **Current workaround:** none technical. Procedurally, no second reviewer has been asked to look at any packet in this pilot.
- **Migration impact:** requires a role-aware packet renderer (`packet_for_reviewer`) and an API change to require `reviewer_id` context on `GET /tasks/{id}`. No stored data format changes — this is a read-path fix only.

## GOV-003 — `governance_state(ACCEPTED)` returns `PHYSICIAN_APPROVED` before Medical QA sign-off

- **Reproduction:** `governance_state(ReviewState.ACCEPTED)` and `governance_state(ReviewState.ACCEPTED_WITH_NOTE)` both directly return `"PHYSICIAN_APPROVED"` — no code path requires a `MEDICAL_QA_LEAD`-authorized `close()` (or any QA action) to have occurred first. Demonstrated in `test_consensus_accept_reports_physician_approved_before_qa_close` (previous session).
- **Affected method:** `clinical_engine/review_workbench/models.py::governance_state`.
- **Expected behaviour:** two-reviewer consensus must produce an intermediate `CONSENSUS_REACHED` / `MEDICAL_QA_PENDING` state; `PHYSICIAN_APPROVED` must require an explicit, separately-authorized Medical QA Lead sign-off action.
- **Actual behaviour (pre-fix):** `ACCEPTED`/`ACCEPTED_WITH_NOTE` (reached the instant `submit_second_review` finds a matching decision) already reports as `PHYSICIAN_APPROVED` to any caller of `governance_state()`.
- **Affected task states:** `ACCEPTED`, `ACCEPTED_WITH_NOTE` (both currently reachable directly from `submit_second_review`, bypassing any QA gate).
- **Clinical impact:** this is the most severe of the three — it means the *system's own reported governance status* for a `ClinicalRegimen` could read `PHYSICIAN_APPROVED` (implying it is eligible for downstream clinical use) without any Medical QA Lead ever having reviewed the case. If anything ever consumed `governance_state()` output as an eligibility signal (e.g., a future Clinical Engine wire-up, or Phase 11 Golden Dataset eligibility), it would silently and incorrectly treat two-reviewer consensus as full physician approval.
- **Governance severity:** **CRITICAL** — this is the exact gate the pilot mandate says must never be automatic.
- **Current workaround:** none technical. Procedurally: approved-object count is still computed as 0 in this session's reporting because no consensus has actually been reached on any real task (all 30 pilot tasks remain `PENDING`), so the defect has not yet produced a false-positive approval in practice — but it would the moment two real reviewers agreed.
- **Migration impact:** requires extending `ReviewState` with `CONSENSUS_REACHED`, `MEDICAL_QA_PENDING`, and making `PHYSICIAN_APPROVED`/`REJECTED` themselves into explicit lifecycle states only reachable via a new `submit_medical_qa_signoff()` method. This changes the terminal-state vocabulary that existing tests assert against — the whole pre-hardening test suite for `submit_second_review` outcomes must be updated to expect `CONSENSUS_REACHED`/`MEDICAL_QA_PENDING` instead of the old direct `ACCEPTED`/`REJECTED_*` terminal states. No task ever reached these old terminal states in the real pilot database (`review_workbench_p56.sqlite` — all 30 pilot tasks and, in fact, all 9,153 tasks database-wide remain `PENDING`), so **no data migration of existing rows is required** beyond the schema/enum change itself (verified in Phase 9).

## Root-cause register

All three entries recorded in [ROOT_CAUSE_REGISTER.md](ROOT_CAUSE_REGISTER.md) as GOV-001, GOV-002, GOV-003.

## Reproduction tests exist before implementation

Confirmed: all three defects were already reproduced as passing (gap-documenting) tests in `clinical_engine/review_workbench/tests/test_pilot_safety_checks.py` from the prior session, before any hardening code in this session was written. New, stronger reproduction/regression tests are added in Phase 11 to assert the *fixed* (safe) behavior once implemented.
