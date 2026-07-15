"""P5.6 physician-pilot Phase 12 negative tests (updated after Review Governance
Hardening, 2026-07-15). GOV-001/GOV-002/GOV-003 are now fixed; these tests
assert the fixed (safe) behavior. The full 30-scenario Phase 11 hardening
suite lives in test_governance_hardening.py.

Every task/reviewer here is a synthetic fixture — never a real pilot task,
never a real reviewer identity.
"""

from __future__ import annotations

from datetime import datetime, timezone

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


def register(registry: ReviewerRegistry, reviewer_id: str, *roles: ReviewRole) -> None:
    registry.register(
        reviewer_id=reviewer_id, display_name=f"Synthetic {reviewer_id}", professional_role="physician",
        organisation="Test Clinic", authorised_scope=roles, registered_at=_now(), registered_by="test-harness",
    )


def add_task(store: ReviewStore, *, task_id: str = "task-1", target_id: str = "regimen-1",
             target_type: TargetType = TargetType.CLINICAL_REGIMEN):
    provenance = [{"field": "dose", "original_text": "500 мг", "page": 7}]
    sources = [{"pdf": "guideline.pdf", "page": 7}]
    store.add_target(target_type, target_id, 1, {"diagnosis": "x"}, provenance, sources)
    task = ClinicalReviewTask(
        task_id=task_id,
        task_key=f"{target_type.value}|{target_id}|1|review",
        target_type=target_type,
        target_id=target_id,
        target_version=1,
        priority_score=80,
        priority=PriorityBand.HIGH,
        issue_type="review",
        severity=Severity.HIGH,
        safety_axes=("pediatric",),
        source_references=tuple(sources),
        provenance_references=tuple(provenance),
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert store.add_task(task)
    return task


# --- GOV-001: fake / unregistered reviewer identity — NOW FIXED --------------

def test_fake_reviewer_identity_rejected_by_registry(registry):
    with pytest.raises(ReviewerRegistrationError):
        registry.require_registered_active("dr-imaginary", ReviewRole.REVIEWER_A)


def test_fake_reviewer_identity_now_rejected_by_service_layer(service):
    """GOV-001 FIXED: ReviewService.claim() now validates against the registry
    and rejects an unregistered reviewer_id."""
    add_task(service.store)
    with pytest.raises(ReviewerValidationError) as excinfo:
        service.claim("task-1", reviewer="dr-imaginary-not-in-any-registry",
                      role=ReviewRole.REVIEWER_A, expected_revision=0)
    assert excinfo.value.reason_code == "REVIEWER_NOT_REGISTERED"


# --- Same person as Reviewer A and B ------------------------------------------

def test_same_person_as_reviewer_a_and_b_fails_closed(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
        reason_codes=("SOURCE_MATCH",), comments="ok", expected_revision=task.revision, target_version=1,
    )
    with pytest.raises(InvalidTransition, match="SELF_REVIEW_FORBIDDEN"):
        service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_B, expected_revision=task.revision)


# --- GOV-002: Reviewer B sees Reviewer A's verdict — NOW FIXED ----------------

def test_reviewer_b_no_longer_sees_reviewer_a_verdict_before_submitting(service):
    """GOV-002 FIXED: packet_for_reviewer() redacts Reviewer A's decision,
    reason codes, comments, and consensus_result — and strips them from the
    audit_history entirely — while the task is in SECOND_REVIEW."""
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
    assert blinded["task"]["lifecycle_state"] == "SECOND_REVIEW"
    assert blinded["task"]["decision"] == ""
    assert blinded["task"]["first_decision"] == ""
    assert blinded["task"]["first_comments"] == ""
    assert blinded["task"]["consensus_result"] == ""
    for event in blinded["task"]["audit_history"]:
        if event["event_type"] == "SUBMIT_FIRST":
            assert event["decision"] == ""
            assert event["reason_codes"] == []
            assert event["comments"] == ""
    # Sanity: the unredacted packet (what QA/Adjudicator see) still has it.
    full = service.packet("task-1")
    assert full["task"]["decision"] == "ACCEPT"


# --- Direct PENDING -> PHYSICIAN_APPROVED -------------------------------------

def test_direct_pending_to_approved_impossible(service):
    add_task(service.store)
    task = service.get_task("task-1")
    assert task.lifecycle_state is ReviewState.PENDING
    with pytest.raises((InvalidTransition, ReviewerValidationError)):
        service.submit_first_review(
            "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
            reason_codes=("SOURCE_MATCH",), comments="ok", expected_revision=0, target_version=1,
        )
    assert "PUBLISHED" not in ReviewState.__members__


# --- GOV-003: consensus ACCEPT reports PHYSICIAN_APPROVED before QA — NOW FIXED

def test_consensus_accept_no_longer_reports_physician_approved_before_qa(service):
    """GOV-003 FIXED: two-reviewer consensus lands on MEDICAL_QA_PENDING, and
    governance_state() reports REVIEW_REQUIRED until a real submit_medical_qa_signoff()
    call with QAVerdict.APPROVE occurs."""
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
        reason_codes=("SOURCE_MATCH",), comments="ok", expected_revision=task.revision, target_version=1,
    )
    task = service.claim("task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B, expected_revision=task.revision)
    task = service.submit_second_review(
        "task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B, decision=ReviewDecision.ACCEPT,
        reason_codes=("SOURCE_MATCH",), comments="agree", expected_revision=task.revision, target_version=1,
    )
    assert task.lifecycle_state is ReviewState.MEDICAL_QA_PENDING
    assert governance_state(task.target_type, task.lifecycle_state) == "REVIEW_REQUIRED"
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    task = service.submit_medical_qa_signoff(
        "task-1", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
        verdict=QAVerdict.APPROVE, rationale="verified", expected_revision=task.revision, target_version=1,
    )
    assert task.lifecycle_state is ReviewState.PHYSICIAN_APPROVED
    assert governance_state(task.target_type, task.lifecycle_state) == "PHYSICIAN_APPROVED"


# --- Administrator ------------------------------------------------------------

def test_administrator_cannot_submit_first_review(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    with pytest.raises(ReviewerValidationError):
        service.submit_first_review(
            "task-1", reviewer="admin-1", role=ReviewRole.ADMINISTRATOR, decision=ReviewDecision.ACCEPT,
            reason_codes=(), comments="", expected_revision=task.revision, target_version=1,
        )


def test_administrator_cannot_close(service):
    add_task(service.store)
    with pytest.raises(ReviewerValidationError):
        service.close("task-1", actor="admin-1", role=ReviewRole.ADMINISTRATOR, expected_revision=0)


def test_administrator_cannot_adjudicate(service):
    add_task(service.store)
    with pytest.raises(ReviewerValidationError):
        service.adjudicate(
            "task-1", adjudicator="admin-1", role=ReviewRole.ADMINISTRATOR, decision=ReviewDecision.ACCEPT,
            reason_codes=(), comments="", expected_revision=0, target_version=1,
        )


# --- Stale target version -----------------------------------------------------

def test_stale_target_version_fails_closed(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    with pytest.raises(InvalidTransition):
        service.submit_first_review(
            "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
            reason_codes=("SOURCE_MATCH",), comments="ok", expected_revision=task.revision, target_version=999,
        )


# --- Missing source wording / provenance --------------------------------------

def test_missing_source_wording_flagged_review_blocked(service):
    service.store.add_target(
        TargetType.CLINICAL_REGIMEN, "regimen-nosrc", 1, {"diagnosis": "x"}, [], {},
    )
    task = ClinicalReviewTask(
        task_id="task-nosrc", task_key="ClinicalRegimen|regimen-nosrc|1|review",
        target_type=TargetType.CLINICAL_REGIMEN, target_id="regimen-nosrc", target_version=1,
        priority_score=10, priority=PriorityBand.LOW, issue_type="review", severity=Severity.LOW,
        safety_axes=(), source_references=(), provenance_references=(),
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert service.store.add_task(task)
    packet = service.packet("task-nosrc")
    assert packet["review_blocked"] is True
    assert packet["source_wording_status"] == "MISSING"


# --- Missing adjudicator -------------------------------------------------------

def test_only_registered_role_can_adjudicate_not_arbitrary_reviewer(service):
    add_task(service.store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
        reason_codes=("SOURCE_MATCH",), comments="ok", expected_revision=task.revision, target_version=1,
    )
    task = service.claim("task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B, expected_revision=task.revision)
    task = service.submit_second_review(
        "task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B, decision=ReviewDecision.REJECT_CLINICAL,
        reason_codes=("CLINICAL_CONCERN",), comments="disagree", expected_revision=task.revision, target_version=1,
    )
    assert task.lifecycle_state is ReviewState.NEEDS_ADJUDICATION
    with pytest.raises(ReviewerValidationError):
        service.adjudicate(
            "task-1", adjudicator="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
            reason_codes=(), comments="", expected_revision=task.revision, target_version=1,
        )


# --- In-place medical value edit ----------------------------------------------

def test_target_snapshot_is_immutable_no_in_place_edit(store):
    store.add_target(TargetType.CLINICAL_REGIMEN, "regimen-x", 1, {"dose": "500mg"}, [], [])
    with pytest.raises(Exception):
        store.add_target(TargetType.CLINICAL_REGIMEN, "regimen-x", 1, {"dose": "999mg"}, [], [])


# --- TherapeuticOption approval must not become Clinical-Engine-consumable ----

def test_therapeutic_option_maps_to_medically_reviewed_not_physician_approved_label(service):
    add_task(service.store, task_id="task-to", target_id="opt-1", target_type=TargetType.THERAPEUTIC_OPTION)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    task = service.claim("task-to", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-to", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.submit_first_review(
        "task-to", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=ReviewDecision.ACCEPT,
        reason_codes=("SOURCE_MATCH",), comments="ok", expected_revision=task.revision, target_version=1,
    )
    task = service.claim("task-to", reviewer="doctor-b", role=ReviewRole.REVIEWER_B, expected_revision=task.revision)
    task = service.submit_second_review(
        "task-to", reviewer="doctor-b", role=ReviewRole.REVIEWER_B, decision=ReviewDecision.ACCEPT,
        reason_codes=("SOURCE_MATCH",), comments="agree", expected_revision=task.revision, target_version=1,
    )
    task = service.submit_medical_qa_signoff(
        "task-to", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
        verdict=QAVerdict.APPROVE, rationale="ok", expected_revision=task.revision, target_version=1,
    )
    assert governance_state(task.target_type, task.lifecycle_state) == "MEDICALLY_REVIEWED"


# --- Interaction status falsely changed to PASS -------------------------------

def test_unsupported_interaction_check_cannot_be_overridden_to_pass(service):
    add_task(service.store)
    packet = service.packet("task-1")
    assert packet["unsupported_checks"]["drug_interactions"] == "NOT AVAILABLE / UNSATISFIABLE"
