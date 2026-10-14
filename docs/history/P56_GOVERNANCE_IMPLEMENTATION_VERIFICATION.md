# Governance Implementation Verification — Phase 6

Generated: 2026-07-15. Independent verification directly against source code (`grep`/`sed` line inspection), not derived from test results or report prose.

## GOV-001 — reviewer identity enforcement

| Requirement | Verified in code | Evidence |
|---|---|---|
| All clinical writes validate a registered `reviewer_id` | ✔ | `grep -n "self._validate("` in `service.py` finds **13** call sites: `assign_reviewer`, `claim` (both branches), `release`, `start_review`, `submit_first_review`, `submit_second_review`, `adjudicate`, `submit_medical_qa_signoff`, `request_adjudication`, `close`, `add_note`, `add_waiver`, `packet_for_reviewer` — every write path (and the reviewer-facing read path) passes through `_validate()` before touching task state. |
| Arbitrary strings fail | ✔ | `ReviewerRegistry.validate_reviewer_action()` calls `self.get(reviewer_id)`, which raises `ReviewerRegistrationError` for any `reviewer_id` not present in the `reviewers` table (`reviewer_registry.py:204-210`); `_validate()` converts this to `reason_code=REVIEWER_NOT_REGISTERED`, `allowed=False`. |
| Rejected attempts are audit-logged | ✔ | `_validate()` calls `self.store.log_rejected_attempt(...)` before raising, for every denial branch (registry-level and the `_SINGLE_ROLE_ACTIONS` check) — writes to `review_rejected_attempts`, a table separate from `review_tasks`, so the rejection is recorded without any `UPDATE` to task state. |
| Display name cannot act as identity | ✔ | Every lookup in `reviewer_registry.py` (`get`, `require_registered_active`, `validate_reviewer_action`, `list_active`) keys exclusively on `reviewer_id` (`WHERE reviewer_id=?`). `display_name` appears only as a stored, returned field — never in a `WHERE` clause, never compared against a caller-supplied identity value. |

## GOV-002 — second-review blinding

| Requirement | Verified in code | Evidence |
|---|---|---|
| Reviewer B pre-submission packet omits A's verdict | ✔ | `_redact_first_reviewer_verdict()` (`service.py:528-548`) blanks `task["decision"]`, `task["first_decision"]`, `task["first_comments"]`, `task["comments"]`, `task["consensus_result"]` to `""`. |
| Omits rationale | ✔ | `comments` and `first_comments` both blanked (rationale is carried in these fields). |
| Omits reason codes | ✔ | `task["reason_codes"]` and `task["first_reason_codes"]` set to `[]`. |
| Audit history does not leak them | ✔ | Every `audit_history` entry with `event_type == "SUBMIT_FIRST"` is rewritten with `decision`/`reason_codes`/`comments` blanked, in place, before being returned. |
| Metrics/status/error responses do not reveal direction | ✔ | `ReviewService.metrics()` (`service.py`, unchanged surface) returns only aggregate counters (`total`, `total_pending`, `by_type`, `by_priority`, `by_state`, `by_diagnosis`, `by_antibiotic`, `by_safety_category`, `average_review_time_seconds`) — no per-task field exists through which a specific verdict could leak. No `InvalidTransition`/`ReviewerValidationError` message string embeds a decision value (all messages are static or embed only role/reason-code names). |
| Applied when it matters, not always | ✔ | `packet_for_reviewer()` only redacts for `role is REVIEWER_B and lifecycle_state is SECOND_REVIEW`; `MEDICAL_QA_LEAD`/`ADJUDICATOR` always get the full packet (their job is to see both), and Reviewer B gets the full packet once the state moves past `SECOND_REVIEW` (both decisions are then legitimately comparable). |
| No anonymous access path | ✔ | `GET /tasks/{task_id}` (`api.py:93`) and `GET /tasks/{task_id}/export` (`api.py:178`) both require `reviewer_id: str, role: ReviewRole` as mandatory (non-default) parameters — FastAPI will 422 without them. |

## GOV-003 — consensus/QA separation

| Requirement | Verified in code | Evidence |
|---|---|---|
| Compatible A/B decisions produce `MEDICAL_QA_PENDING` | ✔ | `submit_second_review` (`service.py`): every branch of `_CONSENSUS_MATCH` sets `state = ReviewState.MEDICAL_QA_PENDING`. |
| Never `PHYSICIAN_APPROVED` directly | ✔ | `grep -n "ReviewState.PHYSICIAN_APPROVED" clinical_engine/review_workbench/*.py` finds exactly **one** line that *assigns* it: `service.py:404`, inside `submit_medical_qa_signoff`, conditioned on `verdict is QAVerdict.APPROVE or APPROVE_WITH_NOTE`. No other method in the codebase sets this state. |
| Only valid Medical QA action can create approval | ✔ | `submit_medical_qa_signoff` requires `task.lifecycle_state is ReviewState.MEDICAL_QA_PENDING` (raises `InvalidTransition` otherwise) and `role is MEDICAL_QA_LEAD` (`_SINGLE_ROLE_ACTIONS["qa_signoff"]`, checked after registry validation). |
| Administrator cannot substitute for QA | ✔ | `ReviewRole.ADMINISTRATOR` + action `"qa_signoff"` (`CLINICAL_ACTIONS`) → `validate_reviewer_action` returns `ADMIN_CLINICAL_ACTION_FORBIDDEN` before any state check runs. |
| `TherapeuticOption` cannot become executable regimen | ✔ | `governance_state(TargetType.THERAPEUTIC_OPTION, ReviewState.PHYSICIAN_APPROVED)` returns `"MEDICALLY_REVIEWED"`, never `"PHYSICIAN_APPROVED"` (`models.py:119-122`); and Clinical Engine has zero import of `review_workbench` (re-verified below), so there is no code path by which either label reaches the engine without a new, separate, explicit wire-up. |

## Additional Phase 6 checks

| Requirement | Verified in code | Evidence |
|---|---|---|
| Assignment revocation blocks submission | ✔ | `submit_first_review`/`submit_second_review` each re-fetch `active_assignment_for_role(task_id, role)` and raise `InvalidTransition("Assignment revoked or missing...")` if it's `None` or the `reviewer_id` doesn't match — independent of the task's scalar `assigned_reviewer`/`second_reviewer` field. |
| Immutable decisions | ✔ | `review_decisions_no_update`/`review_decisions_no_delete` triggers (`storage.py`) `RAISE(ABORT,'review_decisions are append-only')` on any `UPDATE`/`DELETE`. |
| Close semantics | ✔ | `close()` `allowed_states` maps only `{PHYSICIAN_APPROVED, REJECTED, NEEDS_INFO, ABSTAINED}` — `SECOND_REVIEW`/`NEEDS_ADJUDICATION`/`MEDICAL_QA_PENDING` are all excluded, so close before QA sign-off fails closed. |
| Stale target protection | ✔ | 8 distinct `"Stale task or target version"`/`"Stale task revision"` raise sites across `claim`/`release`/`submit_first_review`/`submit_second_review`/`adjudicate`/`submit_medical_qa_signoff`/`request_adjudication`/`add_note`/`add_waiver`. |
| Interaction status remains `NOT AVAILABLE` | ✔ | Exactly 2 occurrences of `unsupported_checks` in the entire module: the hardcoded construction in `packet()` and the defensive re-check inside `submit_medical_qa_signoff`. No setter, no reviewer-facing field, no override path exists. |
| Clinical Engine has no dependency on `review_workbench` | ✔ | `grep -rln "review_workbench" clinical_engine/engine.py clinical_engine/pipeline.py clinical_engine/readers/ clinical_engine/api/` → zero matches (re-run fresh for this report). |

## Conclusion

All GOV-001/002/003 fixes and all Phase 3/7/8 hardening claims are independently confirmed by direct source inspection, not inferred from the test suite or prior report prose.
