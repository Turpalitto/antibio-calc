from __future__ import annotations

import sqlite3
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from clinical_engine.review_workbench.models import (
    ClinicalReviewTask,
    PriorityBand,
    QAVerdict,
    ReviewDecision,
    ReviewRole,
    ReviewState,
    Severity,
    TargetType,
    governance_state,
)
from clinical_engine.review_workbench.priority import score_priority
from clinical_engine.review_workbench.queue_builder import QueueBuilder, _task_identity
from clinical_engine.review_workbench.reporting import summarize_queue
from clinical_engine.review_workbench.reviewer_registry import ReviewerRegistry
from clinical_engine.review_workbench.service import InvalidTransition, ReviewerValidationError, ReviewService
from clinical_engine.review_workbench.storage import (
    ImmutableRecordError,
    ReviewStore,
    SCHEMA_VERSION,
)


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


def add_task(store: ReviewStore, *, task_id: str = "task-1", target_id: str = "regimen-1"):
    provenance = [{"field": "dose", "original_text": "500 мг", "page": 7}]
    sources = [{"pdf": "guideline.pdf", "page": 7}]
    store.add_target(TargetType.CLINICAL_REGIMEN, target_id, 1, {"diagnosis": "x"}, provenance, sources)
    task = ClinicalReviewTask(
        task_id=task_id,
        task_key=f"ClinicalRegimen|{target_id}|1|review",
        target_type=TargetType.CLINICAL_REGIMEN,
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


def claim_and_first(service: ReviewService, decision=ReviewDecision.ACCEPT, doctor_a_roles=(ReviewRole.REVIEWER_A,)):
    add_task(service.store)
    register(service.registry, "doctor-a", *doctor_a_roles)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    return service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, decision=decision,
        reason_codes=("SOURCE_MATCH",), comments="checked", expected_revision=task.revision,
        target_version=1,
    )


def claim_first_and_second(service: ReviewService, first=ReviewDecision.ACCEPT, second=ReviewDecision.ACCEPT):
    task = claim_and_first(service, decision=first)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B,
                         expected_revision=task.revision)
    return service.submit_second_review(
        "task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B,
        decision=second, reason_codes=(), comments="confirmed",
        expected_revision=task.revision, target_version=1,
    )


def test_priority_high_for_pediatric():
    result = score_priority(severity=Severity.HIGH, safety_axes=["pediatric"])
    assert result.band is PriorityBand.HIGH and result.score == 75


def test_priority_medium_for_missing_metadata():
    result = score_priority(severity=Severity.LOW, reasons=["missing_metadata"])
    assert result.band is PriorityBand.MEDIUM and result.score == 25


def test_priority_low_for_formatting():
    result = score_priority(severity=Severity.LOW, reasons=["formatting"])
    assert result.band is PriorityBand.LOW and result.score == 5


def test_missing_unit_is_high_even_with_low_severity():
    result = score_priority(severity=Severity.LOW, reasons=["missing_unit"])
    assert result.band is PriorityBand.HIGH


def test_priority_is_order_independent():
    left = score_priority(severity=Severity.MEDIUM, reasons=["renal", "missing_dose", "renal"])
    right = score_priority(severity=Severity.MEDIUM, reasons=["missing_dose", "renal"])
    assert left == right


def test_task_identity_is_deterministic():
    assert _task_identity(TargetType.CLINICAL_REGIMEN, "r", 1, "x") == _task_identity(
        TargetType.CLINICAL_REGIMEN, "r", 1, "x"
    )


def test_duplicate_task_is_deduplicated(store):
    task = add_task(store)
    assert store.add_task(task) is False
    assert store.metrics()["total"] == 1


def test_target_version_is_immutable(store):
    store.add_target(TargetType.CLINICAL_REGIMEN, "r", 1, {"x": 1}, [{"p": 1}], [{"pdf": "a"}])
    with pytest.raises(ImmutableRecordError):
        store.add_target(TargetType.CLINICAL_REGIMEN, "r", 1, {"x": 2}, [{"p": 1}], [{"pdf": "a"}])


def test_provenance_is_part_of_immutable_snapshot(store):
    store.add_target(TargetType.CLINICAL_REGIMEN, "r", 1, {"x": 1}, [{"p": 1}], [{"pdf": "a"}])
    with pytest.raises(ImmutableRecordError):
        store.add_target(TargetType.CLINICAL_REGIMEN, "r", 1, {"x": 1}, [{"p": 2}], [{"pdf": "a"}])


def test_claim_requires_first_reviewer_role(service, store):
    add_task(store)
    with pytest.raises(ReviewerValidationError):
        service.claim("task-1", reviewer="admin", role=ReviewRole.ADMINISTRATOR, expected_revision=0)


def test_claim_and_release(service, store):
    add_task(store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.release("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                           expected_revision=task.revision)
    assert task.lifecycle_state is ReviewState.PENDING and task.assigned_reviewer == ""


def test_only_owner_can_start_review(service, store):
    add_task(store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    register(service.registry, "doctor-x", ReviewRole.REVIEWER_A)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    with pytest.raises(InvalidTransition):
        service.start_review("task-1", reviewer="doctor-x", role=ReviewRole.REVIEWER_A,
                             expected_revision=task.revision)


def test_first_accept_never_auto_approves(service):
    task = claim_and_first(service)
    assert task.lifecycle_state is ReviewState.SECOND_REVIEW
    assert governance_state(task.target_type, task.lifecycle_state) == "REVIEW_REQUIRED"


def test_self_second_review_forbidden(service):
    task = claim_and_first(service, doctor_a_roles=(ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B))
    with pytest.raises(InvalidTransition, match="SELF_REVIEW_FORBIDDEN"):
        service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_B,
                      expected_revision=task.revision)


def test_matching_second_review_reaches_medical_qa_pending_not_approved(service):
    task = claim_first_and_second(service, first=ReviewDecision.ACCEPT, second=ReviewDecision.ACCEPT)
    assert task.lifecycle_state is ReviewState.MEDICAL_QA_PENDING
    assert task.consensus_result == "CONSENSUS_ACCEPT"
    # GOV-003 fix: consensus alone is never PHYSICIAN_APPROVED.
    assert governance_state(task.target_type, task.lifecycle_state) == "REVIEW_REQUIRED"


def test_qa_signoff_approve_reaches_physician_approved(service):
    task = claim_first_and_second(service)
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    task = service.submit_medical_qa_signoff(
        "task-1", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
        verdict=QAVerdict.APPROVE, rationale="Consensus verified, provenance complete",
        expected_revision=task.revision, target_version=1,
    )
    assert task.lifecycle_state is ReviewState.PHYSICIAN_APPROVED
    assert governance_state(task.target_type, task.lifecycle_state) == "PHYSICIAN_APPROVED"


def test_qa_signoff_on_therapeutic_option_maps_to_medically_reviewed(service):
    service.store.add_target(TargetType.THERAPEUTIC_OPTION, "opt-1", 1, {"x": 1},
                             [{"field": "dose", "original_text": "500 мг", "page": 1}],
                             [{"pdf": "g.pdf", "page": 1}])
    task = ClinicalReviewTask(
        task_id="task-to", task_key="TherapeuticOption|opt-1|1|review", target_type=TargetType.THERAPEUTIC_OPTION,
        target_id="opt-1", target_version=1, priority_score=10, priority=PriorityBand.LOW, issue_type="review",
        severity=Severity.LOW, safety_axes=(), source_references=({"pdf": "g.pdf", "page": 1},),
        provenance_references=({"field": "dose", "original_text": "500 мг", "page": 1},),
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert service.store.add_task(task)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    task = service.claim("task-to", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-to", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.submit_first_review("task-to", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                       decision=ReviewDecision.ACCEPT, reason_codes=(), comments="ok",
                                       expected_revision=task.revision, target_version=1)
    task = service.claim("task-to", reviewer="doctor-b", role=ReviewRole.REVIEWER_B,
                         expected_revision=task.revision)
    task = service.submit_second_review("task-to", reviewer="doctor-b", role=ReviewRole.REVIEWER_B,
                                        decision=ReviewDecision.ACCEPT, reason_codes=(), comments="agree",
                                        expected_revision=task.revision, target_version=1)
    task = service.submit_medical_qa_signoff(
        "task-to", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
        verdict=QAVerdict.APPROVE, rationale="ok", expected_revision=task.revision, target_version=1,
    )
    assert task.lifecycle_state is ReviewState.PHYSICIAN_APPROVED
    assert governance_state(task.target_type, task.lifecycle_state) == "MEDICALLY_REVIEWED"


def test_disagreeing_second_review_requires_adjudication(service):
    task = claim_first_and_second(service, first=ReviewDecision.ACCEPT, second=ReviewDecision.REJECT_CLINICAL)
    assert task.lifecycle_state is ReviewState.NEEDS_ADJUDICATION


def test_only_adjudicator_can_adjudicate(service):
    task = claim_first_and_second(service, first=ReviewDecision.ACCEPT, second=ReviewDecision.REJECT_CLINICAL)
    with pytest.raises(ReviewerValidationError):
        service.adjudicate("task-1", adjudicator="admin", role=ReviewRole.ADMINISTRATOR,
                           decision=ReviewDecision.ACCEPT, reason_codes=(), comments="",
                           expected_revision=task.revision, target_version=1)


def test_adjudication_reaches_medical_qa_pending(service):
    task = claim_first_and_second(service, first=ReviewDecision.ACCEPT, second=ReviewDecision.REJECT_CLINICAL)
    register(service.registry, "doctor-c", ReviewRole.ADJUDICATOR)
    task = service.adjudicate(
        "task-1", adjudicator="doctor-c", role=ReviewRole.ADJUDICATOR,
        decision=ReviewDecision.REJECT_CLINICAL, reason_codes=("SAFETY",), comments="resolved",
        expected_revision=task.revision, target_version=1,
    )
    # GOV-003 fix: adjudicated outcome still requires Medical QA sign-off, not a direct terminal state.
    assert task.lifecycle_state is ReviewState.MEDICAL_QA_PENDING
    assert task.adjudicator == "doctor-c"
    assert task.consensus_result == "CONSENSUS_REJECT_CLINICAL"


def test_stale_revision_rejected(service, store):
    add_task(store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    with pytest.raises(InvalidTransition):
        service.release("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)


def test_stale_target_version_rejected(service):
    task = claim_and_first(service)
    register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B,
                         expected_revision=task.revision)
    with pytest.raises(InvalidTransition):
        service.submit_second_review(
            "task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B,
            decision=ReviewDecision.ACCEPT, reason_codes=(), comments="",
            expected_revision=task.revision, target_version=2,
        )


def test_audit_events_are_append_only(service, store):
    add_task(store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.connection.execute("UPDATE review_events SET comments='x'")
    store.connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.connection.execute("DELETE FROM review_events")


def test_targets_are_immutable_at_database_level(store):
    add_task(store)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.connection.execute("DELETE FROM review_targets")


def test_packet_contains_provenance_and_declares_unsupported_checks(service, store):
    add_task(store)
    packet = service.packet("task-1")
    assert packet["field_level_provenance"][0]["original_text"] == "500 мг"
    assert packet["source_references"][0]["pdf"] == "guideline.pdf"
    assert packet["unsupported_checks"]["drug_interactions"] == "NOT AVAILABLE / UNSATISFIABLE"


def test_queue_builder_rejects_missing_clinical_provenance(store):
    builder = QueueBuilder(store)
    with pytest.raises(ValueError, match="complete source provenance"):
        builder.add(
            target_type=TargetType.CLINICAL_REGIMEN, target_id="r", target_version=1,
            payload={}, provenance=[], sources=[], issue_type="x", severity=Severity.HIGH,
            safety_axes=[], reasons=[],
        )


def test_waiver_requires_medical_qa_lead(service, store):
    add_task(store)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    with pytest.raises(ReviewerValidationError):
        service.add_waiver("task-1", authority="admin", role=ReviewRole.ADMINISTRATOR,
                           reason="documented", expires_at=future, expected_revision=0)


def test_waiver_requires_future_expiry(service, store):
    add_task(store)
    register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    with pytest.raises(ValueError, match="in future"):
        service.add_waiver(
            "task-1", authority="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD, reason="documented",
            expires_at="2020-01-01T00:00:00+00:00", expected_revision=0,
        )


def test_state_survives_restart(tmp_path):
    path = tmp_path / "review.sqlite"
    registry_path = tmp_path / "reviewers.sqlite"
    with ReviewStore(path) as first, ReviewerRegistry(registry_path) as reg:
        add_task(first)
        register(reg, "doctor-a", ReviewRole.REVIEWER_A)
        ReviewService(first, reg).claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                        expected_revision=0)
    with ReviewStore(path) as second:
        task = second.get_task("task-1")
        assert task.lifecycle_state is ReviewState.CLAIMED
        assert len(task.audit_history) == 1


def test_schema_version_is_explicit(store):
    assert store.connection.execute("SELECT version FROM schema_meta").fetchone()[0] == SCHEMA_VERSION


def test_metrics_report_pending_and_safety(service, store):
    add_task(store)
    metrics = service.metrics()
    assert metrics["total_pending"] == 1
    assert metrics["by_safety_category"] == {"pediatric": 1}


def test_add_note_preserves_audit_trail(service, store):
    add_task(store)
    register(service.registry, "admin", ReviewRole.ADMINISTRATOR)
    task = service.add_note("task-1", actor="admin", role=ReviewRole.ADMINISTRATOR,
                            comments="operational note", expected_revision=0)
    assert task.comments == "operational note"
    assert task.audit_history[-1].event_type == "ADD_NOTE"


def test_explicit_adjudication_request(service, store):
    add_task(store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.request_adjudication(
        "task-1", actor="doctor-a", role=ReviewRole.REVIEWER_A,
        reason="source conflict", expected_revision=task.revision,
    )
    assert task.lifecycle_state is ReviewState.NEEDS_ADJUDICATION
    assert task.audit_history[-1].event_type == "REQUEST_ADJUDICATION"


def test_unassigned_reviewer_cannot_request_adjudication(service, store):
    add_task(store)
    register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    register(service.registry, "doctor-x", ReviewRole.REVIEWER_B)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A, expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    with pytest.raises(InvalidTransition, match="assigned reviewer"):
        service.request_adjudication(
            "task-1", actor="doctor-x", role=ReviewRole.REVIEWER_B,
            reason="source conflict", expected_revision=task.revision,
        )


def test_direct_publish_state_does_not_exist():
    assert "PUBLISHED" not in ReviewState.__members__


def test_unsupported_schema_is_not_mutated(tmp_path):
    path = tmp_path / "future.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE schema_meta(version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_meta VALUES(99)")
    connection.commit()
    connection.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError, match="Unsupported review schema version: 99"):
        ReviewStore(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_queue_report_separates_measurement_from_projection(store):
    add_task(store)
    report = summarize_queue(store)
    assert report["measured"]["total"] == 1
    assert report["measured"]["by_safety_axis"] == {"pediatric": 1}
    assert report["workload_projection"]["status"] == "PLANNING_ESTIMATE_NOT_BENCHMARK"
