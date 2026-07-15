"""P5.6 Review Governance Hardening — Phase 11 (30 negative scenarios) and
Phase 12 (synthetic positive workflow). All reviewer identities here are
synthetic test fixtures. No real pilot task or real reviewer is ever touched.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from clinical_engine.review_workbench.models import (
    ClinicalReviewTask, PriorityBand, QAVerdict, ReviewDecision, ReviewRole, ReviewState,
    Severity, TargetType, governance_state,
)
from clinical_engine.review_workbench.reviewer_registry import ReviewerRegistrationError, ReviewerRegistry
from clinical_engine.review_workbench.service import InvalidTransition, ReviewerValidationError, ReviewService
from clinical_engine.review_workbench.storage import ReviewStore


@pytest.fixture
def store(tmp_path):
    value = ReviewStore(tmp_path / "review.sqlite")
    yield value
    value.close()


@pytest.fixture
def registry(tmp_path):
    value = ReviewerRegistry(tmp_path / "reviewers.sqlite")
    yield value
    value.close()


@pytest.fixture
def service(store, registry):
    return ReviewService(store, registry)


def _now():
    return datetime.now(timezone.utc).isoformat()


def register(registry, reviewer_id, *roles, target_type_scope=(), credential_expires_at=""):
    registry.register(
        reviewer_id=reviewer_id, display_name=f"Synthetic {reviewer_id}", professional_role="physician",
        organisation="Test Clinic", authorised_scope=roles, registered_at=_now(), registered_by="test-harness",
        target_type_scope=target_type_scope, credential_expires_at=credential_expires_at,
    )


def add_task(store, *, task_id="task-1", target_id="regimen-1",
             target_type=TargetType.CLINICAL_REGIMEN, with_provenance=True):
    provenance = [{"field": "dose", "original_text": "500 мг", "page": 7}] if with_provenance else []
    sources = [{"pdf": "guideline.pdf", "page": 7}] if with_provenance else []
    store.add_target(target_type, target_id, 1, {"diagnosis": "x"}, provenance, sources)
    task = ClinicalReviewTask(
        task_id=task_id, task_key=f"{target_type.value}|{target_id}|1|review", target_type=target_type,
        target_id=target_id, target_version=1, priority_score=80, priority=PriorityBand.HIGH,
        issue_type="review", severity=Severity.HIGH, safety_axes=("pediatric",),
        source_references=tuple(sources), provenance_references=tuple(provenance),
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert store.add_task(task)
    return task


def run_to_medical_qa_pending(service, task_id="task-1", first=ReviewDecision.ACCEPT,
                              second=ReviewDecision.ACCEPT, target_version=1):
    try:
        service.get_task(task_id)
    except KeyError:
        add_task(service.store, task_id=task_id, target_id=f"regimen-{task_id}")
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    task = service.claim(task_id, reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review(task_id, reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.submit_first_review(
        task_id, reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=first,
        reason_codes=("SOURCE_MATCH",), comments="ok", expected_revision=task.revision,
        target_version=target_version,
    )
    task = service.claim(task_id, reviewer="doctor-b", role=ReviewRole.REVIEWER_B, expected_revision=task.revision)
    task = service.submit_second_review(
        task_id, reviewer="doctor-b", role=ReviewRole.REVIEWER_B, decision=second,
        reason_codes=("SOURCE_MATCH",), comments="agree", expected_revision=task.revision,
        target_version=target_version,
    )
    return task


# 1. Arbitrary reviewer string rejected
def test_01_arbitrary_reviewer_string_rejected(service):
    add_task(service.store)
    with pytest.raises(ReviewerValidationError):
        service.claim("task-1", reviewer="just-a-made-up-string", role=ReviewRole.REVIEWER_A, expected_revision=0)


# 2. Unregistered reviewer rejected
def test_02_unregistered_reviewer_rejected(service):
    add_task(service.store)
    with pytest.raises(ReviewerValidationError) as excinfo:
        service.claim("task-1", reviewer="never-registered", role=ReviewRole.REVIEWER_A, expected_revision=0)
    assert excinfo.value.reason_code == "REVIEWER_NOT_REGISTERED"


# 3. Inactive reviewer rejected
def test_03_inactive_reviewer_rejected(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    service.registry.deactivate("doctor-a")
    with pytest.raises(ReviewerValidationError) as excinfo:
        service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    assert excinfo.value.reason_code == "REVIEWER_INACTIVE"


# 4. Expired credential rejected
def test_04_expired_credential_rejected(service):
    add_task(service.store)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A, credential_expires_at=past)
    with pytest.raises(ReviewerValidationError) as excinfo:
        service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    assert excinfo.value.reason_code == "CREDENTIAL_EXPIRED"


# 5. Wrong role rejected
def test_05_wrong_role_rejected(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_B)  # not authorised as REVIEWER_A
    with pytest.raises(ReviewerValidationError) as excinfo:
        service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    assert excinfo.value.reason_code == "ROLE_NOT_AUTHORISED"


# 6. Wrong scope rejected
def test_06_wrong_scope_rejected(service):
    add_task(service.store, target_type=TargetType.CLINICAL_REGIMEN)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A,
             target_type_scope=(TargetType.THERAPEUTIC_OPTION,))
    with pytest.raises(ReviewerValidationError) as excinfo:
        service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    assert excinfo.value.reason_code == "SCOPE_NOT_AUTHORISED"


# 7. Administrator clinical approval rejected
def test_07_administrator_clinical_approval_rejected(service):
    task = run_to_medical_qa_pending(service)
    with pytest.raises(ReviewerValidationError) as excinfo:
        service.submit_medical_qa_signoff(
            "task-1", medical_qa_reviewer_id="admin-1", role=ReviewRole.ADMINISTRATOR,
            verdict=QAVerdict.APPROVE, rationale="x", expected_revision=task.revision, target_version=1,
        )
    assert excinfo.value.reason_code == "ADMIN_CLINICAL_ACTION_FORBIDDEN"


# 8. Reviewer A = Reviewer B rejected
def test_08_reviewer_a_equals_b_rejected(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
        reason_codes=(), comments="ok", expected_revision=task.revision, target_version=1,
    )
    with pytest.raises(InvalidTransition, match="SELF_REVIEW_FORBIDDEN"):
        service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_B, expected_revision=task.revision)


# 9/10. Reviewer B packet omits A verdict and rationale
def test_09_10_reviewer_b_packet_omits_a_verdict_and_rationale(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.REJECT_CLINICAL,
        reason_codes=("SAFETY_CONCERN",), comments="This drug is contraindicated for this population",
        expected_revision=task.revision, target_version=1,
    )
    blinded = service.packet_for_reviewer("task-1", "doctor-b", ReviewRole.REVIEWER_B)
    assert blinded["task"]["decision"] == ""
    assert blinded["task"]["first_decision"] == ""
    assert blinded["task"]["first_comments"] == ""
    assert "contraindicated" not in str(blinded)


# 11. History does not leak A verdict
def test_11_history_does_not_leak_a_verdict(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
        reason_codes=("SOURCE_MATCH",), comments="ok", expected_revision=task.revision, target_version=1,
    )
    blinded = service.packet_for_reviewer("task-1", "doctor-b", ReviewRole.REVIEWER_B)
    for event in blinded["task"]["audit_history"]:
        assert event["decision"] == "" or event["event_type"] != "SUBMIT_FIRST"


# 12. Metrics do not leak verdict before B submission
def test_12_metrics_do_not_leak_verdict_before_b_submission(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
        reason_codes=(), comments="ok", expected_revision=task.revision, target_version=1,
    )
    metrics = service.metrics()
    # metrics() only ever returns aggregate counters (by_type/by_priority/by_state/etc.);
    # it has no per-task field, so there is no key path through which a specific
    # reviewer's verdict could leak before the other reviewer submits.
    expected_keys = {"total", "total_pending", "by_type", "by_priority", "by_state",
                     "average_review_time_seconds", "by_diagnosis", "by_antibiotic", "by_safety_category"}
    assert set(metrics.keys()) == expected_keys
    assert metrics["by_state"].get("SECOND_REVIEW") == 1


# 13. Two ACCEPT reviews do not produce PHYSICIAN_APPROVED
def test_13_two_accepts_do_not_produce_physician_approved(service):
    task = run_to_medical_qa_pending(service)
    assert task.lifecycle_state is not ReviewState.PHYSICIAN_APPROVED
    assert governance_state(task.target_type, task.lifecycle_state) != "PHYSICIAN_APPROVED"


# 14. Consensus produces MEDICAL_QA_PENDING
def test_14_consensus_produces_medical_qa_pending(service):
    task = run_to_medical_qa_pending(service)
    assert task.lifecycle_state is ReviewState.MEDICAL_QA_PENDING
    assert task.consensus_result == "CONSENSUS_ACCEPT"


# 15. Medical QA sign-off required
def test_15_medical_qa_signoff_required_before_close(service):
    task = run_to_medical_qa_pending(service)
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    with pytest.raises(InvalidTransition, match="Medical QA sign-off"):
        service.close("task-1", actor="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD, expected_revision=task.revision)


# 16. Unregistered Medical QA rejected
def test_16_unregistered_medical_qa_rejected(service):
    task = run_to_medical_qa_pending(service)
    with pytest.raises(ReviewerValidationError) as excinfo:
        service.submit_medical_qa_signoff(
            "task-1", medical_qa_reviewer_id="unregistered-qa", role=ReviewRole.MEDICAL_QA_LEAD,
            verdict=QAVerdict.APPROVE, rationale="x", expected_revision=task.revision, target_version=1,
        )
    assert excinfo.value.reason_code == "REVIEWER_NOT_REGISTERED"


# 17. Reviewer A cannot act as Medical QA on same task
def test_17_reviewer_a_cannot_act_as_qa_same_task(service):
    """doctor-a is Reviewer A on this task. Even if the same person also holds
    a Medical QA Lead credential (multi-role registration, permitted in
    general), they must not be allowed to sign off the task they reviewed."""
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A, ReviewRole.MEDICAL_QA_LEAD)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
        reason_codes=(), comments="ok", expected_revision=task.revision, target_version=1,
    )
    task = service.claim("task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B, expected_revision=task.revision)
    task = service.submit_second_review(
        "task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B, decision=ReviewDecision.ACCEPT,
        reason_codes=(), comments="agree", expected_revision=task.revision, target_version=1,
    )
    with pytest.raises(InvalidTransition, match="SELF_REVIEW_FORBIDDEN"):
        service.submit_medical_qa_signoff(
            "task-1", medical_qa_reviewer_id="doctor-a", role=ReviewRole.MEDICAL_QA_LEAD,
            verdict=QAVerdict.APPROVE, rationale="x", expected_revision=task.revision, target_version=1,
        )


# 18. Unresolved adjudication blocks QA
def test_18_unresolved_adjudication_blocks_qa(service):
    task = run_to_medical_qa_pending(service, first=ReviewDecision.ACCEPT, second=ReviewDecision.REJECT_CLINICAL)
    assert task.lifecycle_state is ReviewState.NEEDS_ADJUDICATION
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    with pytest.raises(InvalidTransition, match="not awaiting Medical QA"):
        service.submit_medical_qa_signoff(
            "task-1", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
            verdict=QAVerdict.APPROVE, rationale="x", expected_revision=task.revision, target_version=1,
        )


# 19. Stale target blocks QA
def test_19_stale_target_blocks_qa(service):
    task = run_to_medical_qa_pending(service)
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    with pytest.raises(InvalidTransition):
        service.submit_medical_qa_signoff(
            "task-1", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
            verdict=QAVerdict.APPROVE, rationale="x", expected_revision=task.revision, target_version=999,
        )


# 20. Missing provenance blocks QA
def test_20_missing_provenance_blocks_qa(service):
    add_task(service.store, with_provenance=False)
    task = run_to_medical_qa_pending(service)
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    with pytest.raises(InvalidTransition, match="source wording"):
        service.submit_medical_qa_signoff(
            "task-1", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
            verdict=QAVerdict.APPROVE, rationale="x", expected_revision=task.revision, target_version=1,
        )


# 21. Interaction NOT AVAILABLE cannot be changed to PASS
def test_21_interaction_not_available_immutable(service):
    add_task(service.store)
    packet = service.packet("task-1")
    assert packet["unsupported_checks"]["drug_interactions"] == "NOT AVAILABLE / UNSATISFIABLE"
    assert not hasattr(service, "set_interaction_status")


# 22. TherapeuticOption cannot become executable regimen
def test_22_therapeutic_option_cannot_become_executable_regimen(service):
    add_task(service.store, task_id="task-to", target_id="opt-1", target_type=TargetType.THERAPEUTIC_OPTION)
    task = run_to_medical_qa_pending(service, task_id="task-to")
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    task = service.submit_medical_qa_signoff(
        "task-to", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
        verdict=QAVerdict.APPROVE, rationale="x", expected_revision=task.revision, target_version=1,
    )
    assert governance_state(task.target_type, task.lifecycle_state) == "MEDICALLY_REVIEWED"
    assert governance_state(task.target_type, task.lifecycle_state) != "PHYSICIAN_APPROVED"


# 23. Close before QA rejected
def test_23_close_before_qa_rejected(service):
    task = run_to_medical_qa_pending(service)
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    with pytest.raises(InvalidTransition, match="Medical QA sign-off"):
        service.close("task-1", actor="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD, expected_revision=task.revision)


# 24. Duplicate QA sign-off rejected
def test_24_duplicate_qa_signoff_rejected(service):
    task = run_to_medical_qa_pending(service)
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    task = service.submit_medical_qa_signoff(
        "task-1", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
        verdict=QAVerdict.APPROVE, rationale="x", expected_revision=task.revision, target_version=1,
    )
    with pytest.raises(InvalidTransition, match="not awaiting Medical QA"):
        service.submit_medical_qa_signoff(
            "task-1", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
            verdict=QAVerdict.APPROVE, rationale="again", expected_revision=task.revision, target_version=1,
        )


# 25. Submitted decision immutable
def test_25_submitted_decision_immutable(service):
    task = run_to_medical_qa_pending(service)
    decisions = service.store.list_decisions("task-1")
    assert len(decisions) == 2
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        service.store.connection.execute("UPDATE review_decisions SET verdict='HACKED'")


# 26. Revoked assignment rejected
def test_26_revoked_assignment_rejected(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    assignment = service.store.active_assignment_for_role("task-1", ReviewRole.REVIEWER_A)
    service.revoke_assignment(assignment.assignment_id, reason="reassigned")
    with pytest.raises(InvalidTransition, match="Assignment revoked"):
        service.submit_first_review(
            "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
            reason_codes=(), comments="ok", expected_revision=task.revision, target_version=1,
        )


# 27. Forged display name does not bypass reviewer_id validation
def test_27_forged_display_name_does_not_bypass_validation(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    # Attempting to claim using the display name instead of the reviewer_id must fail —
    # identity is keyed exclusively on reviewer_id.
    with pytest.raises(ReviewerValidationError) as excinfo:
        service.claim("task-1", reviewer="Synthetic doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    assert excinfo.value.reason_code == "REVIEWER_NOT_REGISTERED"


# 28. Audit rejection recorded
def test_28_audit_rejection_recorded(service):
    add_task(service.store)
    with pytest.raises(ReviewerValidationError):
        service.claim("task-1", reviewer="ghost", role=ReviewRole.REVIEWER_A, expected_revision=0)
    attempts = service.store.list_rejected_attempts("task-1")
    assert len(attempts) == 1
    assert attempts[0]["reason_code"] == "REVIEWER_NOT_REGISTERED"
    assert attempts[0]["actor"] == "ghost"
    # Task state itself was not changed by the rejected attempt.
    assert service.get_task("task-1").lifecycle_state is ReviewState.PENDING


# 29. Approved object count remains zero in synthetic no-QA flow
def test_29_approved_count_zero_without_qa(service):
    for i in range(3):
        add_task(service.store, task_id=f"task-{i}", target_id=f"regimen-{i}")
    for i in range(3):
        register(service.registry, f"doctor-a-{i}", ReviewRole.REVIEWER_A)
        register(service.registry, f"doctor-b-{i}", ReviewRole.REVIEWER_B)
        task = service.claim(f"task-{i}", reviewer=f"doctor-a-{i}", role=ReviewRole.REVIEWER_A,
                             expected_revision=0)
        task = service.start_review(f"task-{i}", reviewer=f"doctor-a-{i}", role=ReviewRole.REVIEWER_A,
                                    expected_revision=task.revision)
        task = service.submit_first_review(
            f"task-{i}", reviewer=f"doctor-a-{i}", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
            reason_codes=(), comments="ok", expected_revision=task.revision, target_version=1,
        )
        task = service.claim(f"task-{i}", reviewer=f"doctor-b-{i}", role=ReviewRole.REVIEWER_B,
                             expected_revision=task.revision)
        service.submit_second_review(
            f"task-{i}", reviewer=f"doctor-b-{i}", role=ReviewRole.REVIEWER_B, decision=ReviewDecision.ACCEPT,
            reason_codes=(), comments="agree", expected_revision=task.revision, target_version=1,
        )
    approved = service.store.list_tasks(state=ReviewState.PHYSICIAN_APPROVED, limit=1000)
    assert len(approved) == 0


# 30. No Clinical Engine import introduced
def test_30_no_clinical_engine_import_introduced():
    import clinical_engine.engine as engine_module
    import clinical_engine.pipeline as pipeline_module
    for module in (engine_module, pipeline_module):
        source = inspect.getsource(module)
        assert "review_workbench" not in source


# --- Phase 12: synthetic positive workflow (never touches the real pilot DB) --

def test_synthetic_positive_workflow_reaches_physician_approved(tmp_path):
    store = ReviewStore(tmp_path / "synthetic_review.sqlite")
    registry = ReviewerRegistry(tmp_path / "synthetic_reviewers.sqlite")
    service = ReviewService(store, registry)
    try:
        # 1-4: register synthetic Reviewer A, Reviewer B, Adjudicator, Medical QA Lead
        register(registry, "syn-reviewer-a", ReviewRole.REVIEWER_A)
        register(registry, "syn-reviewer-b", ReviewRole.REVIEWER_B)
        register(registry, "syn-adjudicator", ReviewRole.ADJUDICATOR)
        register(registry, "syn-qa-lead", ReviewRole.MEDICAL_QA_LEAD)

        task = add_task(store, task_id="syn-task-1", target_id="syn-regimen-1")

        # 5: assign roles explicitly
        service.assign_reviewer("syn-task-1", reviewer_id="syn-reviewer-a", role=ReviewRole.REVIEWER_A,
                                assigned_by="owner")

        # 6: submit independent A review
        task = service.claim("syn-task-1", reviewer="syn-reviewer-a", role=ReviewRole.REVIEWER_A,
                             expected_revision=task.revision)
        task = service.start_review("syn-task-1", reviewer="syn-reviewer-a", role=ReviewRole.REVIEWER_A,
                                    expected_revision=task.revision)
        task = service.submit_first_review(
            "syn-task-1", reviewer="syn-reviewer-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
            reason_codes=("SOURCE_MATCH",), comments="Verified against source PDF page 7",
            expected_revision=task.revision, target_version=1,
        )

        # 7: verify B cannot see A decision
        blinded = service.packet_for_reviewer("syn-task-1", "syn-reviewer-b", ReviewRole.REVIEWER_B)
        assert blinded["task"]["decision"] == ""
        assert blinded["task"]["first_decision"] == ""

        # 8: submit compatible B review
        task = service.claim("syn-task-1", reviewer="syn-reviewer-b", role=ReviewRole.REVIEWER_B,
                             expected_revision=task.revision)
        task = service.submit_second_review(
            "syn-task-1", reviewer="syn-reviewer-b", role=ReviewRole.REVIEWER_B, decision=ReviewDecision.ACCEPT,
            reason_codes=("SOURCE_MATCH",), comments="Independently verified, agree",
            expected_revision=task.revision, target_version=1,
        )

        # 9: verify state = MEDICAL_QA_PENDING
        assert task.lifecycle_state is ReviewState.MEDICAL_QA_PENDING
        assert governance_state(task.target_type, task.lifecycle_state) == "REVIEW_REQUIRED"

        # 10: submit QA sign-off
        task = service.submit_medical_qa_signoff(
            "syn-task-1", medical_qa_reviewer_id="syn-qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
            verdict=QAVerdict.APPROVE, rationale="All governance checks pass: distinct reviewers, "
            "consensus reached, provenance complete, no unresolved conflicts",
            expected_revision=task.revision, target_version=1,
        )

        # 11: verify eligible synthetic ClinicalRegimen reaches PHYSICIAN_APPROVED
        assert task.lifecycle_state is ReviewState.PHYSICIAN_APPROVED
        assert governance_state(task.target_type, task.lifecycle_state) == "PHYSICIAN_APPROVED"

        task = service.close("syn-task-1", actor="syn-qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
                             expected_revision=task.revision)
        assert task.lifecycle_state is ReviewState.CLOSED
        assert task.close_outcome == "CLOSED_APPROVED"

        # 12: verify immutable audit history
        history = task.audit_history
        assert len(history) >= 6
        event_types = [event.event_type for event in history]
        assert event_types == [
            "CLAIM_FIRST", "START_REVIEW", "SUBMIT_FIRST", "CLAIM_SECOND", "SUBMIT_SECOND",
            "MEDICAL_QA_SIGNOFF", "CLOSE",
        ]
        decisions = store.list_decisions("syn-task-1")
        assert len(decisions) == 3
    finally:
        store.close()
        registry.close()
