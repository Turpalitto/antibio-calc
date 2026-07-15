# Medical QA Sign-off Specification

Version 1.0 — 2026-07-15 (P5.6 Review Governance Hardening, closes GOV-003).

## Method

```python
ReviewService.submit_medical_qa_signoff(
    task_id, *, medical_qa_reviewer_id, role, verdict: QAVerdict, rationale: str,
    expected_revision: int, target_version: int,
) -> ClinicalReviewTask
```

`QAVerdict`: `APPROVE`, `APPROVE_WITH_NOTE`, `RETURN_FOR_ADJUDICATION`, `RETURN_FOR_REVIEW`, `REJECT_GOVERNANCE`, `NEEDS_INFO`, `ABSTAIN`.

## Preconditions (all enforced, all fail closed)

1. Registry validation: `medical_qa_reviewer_id` must be registered, active, authorised for `MEDICAL_QA_LEAD`, in-scope for the task's `target_type`, credential not expired (`ReviewerRegistry.validate_reviewer_action`).
2. `role` must literally be `MEDICAL_QA_LEAD` (`_SINGLE_ROLE_ACTIONS["qa_signoff"]`) — a reviewer cannot invoke this by passing their own legitimately-held role.
3. `task.revision == expected_revision` and `task.target_version == target_version` — stale task or stale target both fail closed (`InvalidTransition`).
4. `task.lifecycle_state is ReviewState.MEDICAL_QA_PENDING` — cannot sign off a task still in `SECOND_REVIEW`, `NEEDS_ADJUDICATION`, or already `CLOSED`/`PHYSICIAN_APPROVED`/`REJECTED` (blocks both premature and duplicate sign-off).
5. `medical_qa_reviewer_id` must not be `task.assigned_reviewer`, `task.second_reviewer`, or `task.adjudicator` on this task — a reviewer/adjudicator cannot QA their own case, even if they separately hold a `MEDICAL_QA_LEAD` credential.
6. `rationale` must be non-empty.

## Additional checklist before an `APPROVE`/`APPROVE_WITH_NOTE` verdict is honored

7. Reviewer A and Reviewer B assignments must both exist (`store.active_assignment_for_role`) and must be **distinct** `reviewer_id`s.
8. Both `task.first_decision` and `task.second_decision` must be populated (independently submitted — structurally guaranteed by the state machine, re-checked here defensively).
9. `task.consensus_result` must be non-empty (a real consensus or adjudication outcome was recorded).
10. `packet(task_id)["review_blocked"]` must be `False` and `source_wording_status == "AVAILABLE"` — source wording/provenance must be present.
11. `packet(task_id)["unsupported_checks"]["drug_interactions"]` must still read `"NOT AVAILABLE / UNSATISFIABLE"` — this is a hardcoded literal in `packet()` with no reviewer-facing override path, so this check can never fail unless the code itself is tampered with; it is asserted defensively anyway.

Not exhaustively enforced by code (documented honestly, not silently assumed): waiver-expiry validity and unresolved-conflict governance are recorded via `add_waiver`/`comments` but are not independently re-validated inside `submit_medical_qa_signoff` beyond what's listed above — a Medical QA Lead is expected to read the full packet (`detected_conflicts`, `validation_failures`, waiver notes in `comments`) as part of forming their rationale, per the existing `close_outcome`/`comments` audit trail.

## Verdict → state mapping

| Verdict | Resulting `lifecycle_state` |
|---|---|
| `APPROVE` / `APPROVE_WITH_NOTE`, consensus direction = accept | `PHYSICIAN_APPROVED` |
| `APPROVE` / `APPROVE_WITH_NOTE`, consensus direction = reject | `REJECTED` (QA confirms the rejection is correct) |
| `REJECT_GOVERNANCE` | `REJECTED` (QA overrides on governance grounds regardless of reviewer direction) |
| `RETURN_FOR_ADJUDICATION` | `NEEDS_ADJUDICATION` |
| `RETURN_FOR_REVIEW` | `NEEDS_INFO` |
| `NEEDS_INFO` | `NEEDS_INFO` |
| `ABSTAIN` | `ABSTAINED` |

Every QA sign-off action is recorded as an immutable `ReviewDecisionRecord` (decision_sequence 4) in `review_decisions`, in addition to the `MEDICAL_QA_SIGNOFF` `AuditEvent`.

## Close semantics (Phase 7)

`close()` requires `lifecycle_state` in `{PHYSICIAN_APPROVED, REJECTED, NEEDS_INFO, ABSTAINED}` — i.e., only reachable **after** a real QA sign-off (or a reviewer-level `NEEDS_INFO`/`ABSTAINED` outcome that never needed QA). Close is restricted to `MEDICAL_QA_LEAD` and sets `close_outcome` to the matching `CLOSED_APPROVED`/`CLOSED_REJECTED`/`CLOSED_NEEDS_INFO`/`CLOSED_ABSTAINED`. Closing from `SECOND_REVIEW`, `NEEDS_ADJUDICATION`, or `MEDICAL_QA_PENDING` fails closed with `InvalidTransition`.

## Test coverage

`test_governance_hardening.py` #7, #15–#20, #22–#24; `test_review_workbench.py::test_qa_signoff_approve_reaches_physician_approved`, `test_qa_signoff_on_therapeutic_option_maps_to_medically_reviewed`; `test_pilot_safety_checks.py::test_consensus_accept_no_longer_reports_physician_approved_before_qa`.
