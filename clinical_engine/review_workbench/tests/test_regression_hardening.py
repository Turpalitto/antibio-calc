"""Regression tests for the C1/H1/H2/M1/M2/M3/M10/M11 hardening round.

Each test names the defect it pins. Nothing here touches a real pilot task or a
real reviewer identity — every fixture is synthetic.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from clinical_engine.review_workbench import permissions
from clinical_engine.review_workbench.api import create_app
from clinical_engine.review_workbench.dose_unit_audit import audit, auto_recoverable, classify
from clinical_engine.review_workbench.models import (
    ClinicalReviewTask, CloseOutcome, ConsensusResult, PriorityBand, QAVerdict, ReviewDecision,
    ReviewRole, ReviewState, Severity, TargetType, close_outcome_or_blank, consensus_or_blank,
)
from clinical_engine.review_workbench.reviewer_registry import ReviewerRegistry
from clinical_engine.review_workbench.service import (
    InvalidTransition, ReviewerValidationError, ReviewService,
)
from clinical_engine.review_workbench.storage import ReviewStore


# ── fixtures ────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _register(registry, reviewer_id, *roles):
    registry.register(
        reviewer_id=reviewer_id, display_name=f"Synthetic {reviewer_id}",
        professional_role="physician", organisation="Test Clinic",
        authorised_scope=roles, registered_at=_now(), registered_by="test-harness",
    )


def _add_task(store, task_id="task-1", target_id="regimen-1"):
    provenance = [{"field": "dose", "original_text": "500 мг", "page": 7}]
    sources = [{"pdf": "guideline.pdf", "page": 7}]
    store.add_target(TargetType.CLINICAL_REGIMEN, target_id, 1, {"diagnosis": "x"},
                     provenance, sources)
    task = ClinicalReviewTask(
        task_id=task_id, task_key=f"ClinicalRegimen|{target_id}|1|review",
        target_type=TargetType.CLINICAL_REGIMEN, target_id=target_id, target_version=1,
        priority_score=80, priority=PriorityBand.HIGH, issue_type="review",
        severity=Severity.HIGH, safety_axes=("pediatric",),
        source_references=tuple(sources), provenance_references=tuple(provenance),
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert store.add_task(task)
    return task


def _task_in_second_review(service, *, extra_roles_for_b: tuple[ReviewRole, ...] = ()):
    """Drive a task to SECOND_REVIEW with a secret first verdict."""
    _add_task(service.store)
    _register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    _register(service.registry, "doctor-b", ReviewRole.REVIEWER_B, *extra_roles_for_b)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                         expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
        decision=ReviewDecision.REJECT_CLINICAL, reason_codes=("SAFETY_CONCERN",),
        comments="SECRET_A_VERDICT_CONTRAINDICATED",
        expected_revision=task.revision, target_version=1,
    )
    return service.get_task("task-1")


SECRET = "SECRET_A_VERDICT_CONTRAINDICATED"


def _session_token(registry_path, reviewer_id):
    """Mint a real reviewer session token (only its SHA-256 is persisted)."""
    with ReviewerRegistry(registry_path) as registry:
        return registry.issue_session_token(reviewer_id)


# ── C1: second-reviewer blinding must not be bypassable with one query param ──


def test_c1_reviewer_b_cannot_unblind_by_quoting_reviewer_a(service):
    """C1: redaction was keyed on the role the CALLER CLAIMED. Quoting
    REVIEWER_A fell through to the unredacted packet and exposed
    first_decision, first_comments, consensus_result and the SUBMIT_FIRST audit
    body. Blinding is now derived from the task's own reviewer assignments."""
    _task_in_second_review(service, extra_roles_for_b=(ReviewRole.REVIEWER_A,))
    assert service.get_task("task-1").lifecycle_state is ReviewState.SECOND_REVIEW

    blinded = service.packet_for_reviewer("task-1", "doctor-b", ReviewRole.REVIEWER_A)
    assert blinded["task"]["first_decision"] == ""
    assert blinded["task"]["first_comments"] == ""
    assert blinded["task"]["consensus_result"] == ""
    assert SECRET not in json.dumps(blinded, ensure_ascii=False)
    for event in blinded["task"]["audit_history"]:
        if event["event_type"] == "SUBMIT_FIRST":
            assert event["decision"] == ""
            assert event["reason_codes"] == []
            assert event["comments"] == ""


def test_c1_every_claimed_role_is_blinded_for_a_non_assigned_reviewer(service):
    """C1: no quoted role other than a blinding-exempt one may unblind, and the
    exempt set is a closed set inside the service."""
    _task_in_second_review(service, extra_roles_for_b=(ReviewRole.REVIEWER_A,))
    for claimed in ReviewRole:
        if claimed in {ReviewRole.MEDICAL_QA_LEAD, ReviewRole.ADJUDICATOR}:
            continue
        _register(service.registry, f"probe-{claimed.value}", claimed)
        packet = service.packet_for_reviewer("task-1", f"probe-{claimed.value}", claimed)
        assert packet["task"]["first_comments"] == "", claimed
        assert SECRET not in json.dumps(packet, ensure_ascii=False), claimed


def test_c1_unregistered_caller_cannot_unblind_either(service):
    """C1: the registry check still runs first — an unregistered caller never
    reaches the packet at all."""
    _task_in_second_review(service)
    with pytest.raises(ReviewerValidationError):
        service.packet_for_reviewer("task-1", "not-registered", ReviewRole.REVIEWER_A)


def test_c1_qa_lead_and_adjudicator_still_see_both_decisions(service):
    """The fix must not weaken the roles whose job is to review BOTH decisions."""
    _task_in_second_review(service)
    _register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    _register(service.registry, "arbiter", ReviewRole.ADJUDICATOR)

    qa = service.packet_for_reviewer("task-1", "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    assert qa["task"]["first_comments"] == SECRET

    arb = service.packet_for_reviewer("task-1", "arbiter", ReviewRole.ADJUDICATOR)
    assert arb["task"]["first_comments"] == SECRET


def test_c1_reviewer_a_still_sees_their_own_prior_submission(service):
    """Nothing is hidden from Reviewer A about their own submission."""
    _task_in_second_review(service)
    own = service.packet_for_reviewer("task-1", "doctor-a", ReviewRole.REVIEWER_A)
    assert own["task"]["first_comments"] == SECRET


def test_c1_second_reviewer_after_claiming_is_still_the_task_recorded_role(service):
    """Once claimed, the task records doctor-b as the second reviewer; a
    REVIEWER_B quote for the actual first reviewer stays unblinded only for
    themselves."""
    _register(service.registry, "doctor-a", ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B)
    _register(service.registry, "doctor-b", ReviewRole.REVIEWER_B)
    _add_task(service.store)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                         expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    task = service.submit_first_review(
        "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
        decision=ReviewDecision.REJECT_CLINICAL, reason_codes=("SAFETY_CONCERN",),
        comments=SECRET, expected_revision=task.revision, target_version=1,
    )
    task = service.claim("task-1", reviewer="doctor-b", role=ReviewRole.REVIEWER_B,
                         expected_revision=task.revision)
    assert task.second_reviewer == "doctor-b"
    assert SECRET in json.dumps(
        service.packet_for_reviewer("task-1", "doctor-a", ReviewRole.REVIEWER_B),
        ensure_ascii=False,
    )


def test_c1_http_endpoint_cannot_be_unblinded_with_a_query_parameter(tmp_path):
    """C1 over HTTP: ``role`` is a caller-supplied query param.

    ``reviewer_id`` is no longer a query param at all — the acting identity comes
    from the session token, so the attack has to be carried by ``role`` alone.
    """
    db = tmp_path / "api.sqlite"
    with ReviewStore(db) as backing:
        _add_task(backing)
    registry_path = tmp_path / "reviewers.sqlite"
    with ReviewerRegistry(registry_path) as reg:
        _register(reg, "doctor-a", ReviewRole.REVIEWER_A)
        _register(reg, "doctor-b", ReviewRole.REVIEWER_B, ReviewRole.REVIEWER_A)
    store = ReviewStore(db)
    service = ReviewService(store, ReviewerRegistry(registry_path))
    try:
        task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                             expected_revision=0)
        task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                    expected_revision=task.revision)
        service.submit_first_review(
            "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
            decision=ReviewDecision.REJECT_CLINICAL, reason_codes=("SAFETY_CONCERN",),
            comments=SECRET, expected_revision=task.revision, target_version=1,
        )
    finally:
        store.close()
    doctor_b_token = _session_token(registry_path, "doctor-b")

    with TestClient(create_app(db, registry_path=registry_path),
                    base_url="http://127.0.0.1") as client:
        honest = client.get("/tasks/task-1", params={"role": "REVIEWER_B"},
                            headers={"X-Review-Token": doctor_b_token})
        assert honest.status_code == 200
        assert honest.json()["task"]["first_comments"] == ""

        attack = client.get("/tasks/task-1", params={"role": "REVIEWER_A"},
                            headers={"X-Review-Token": doctor_b_token})
        assert attack.status_code == 200
        assert attack.json()["task"]["first_comments"] == ""
        assert SECRET not in attack.text

        # …and the queue listing, which also returns whole task records, is
        # blinded for the same caller.
        queue = client.get("/queue", params={"role": "REVIEWER_A"},
                           headers={"X-Review-Token": doctor_b_token})
        assert queue.status_code == 200
        assert SECRET not in queue.text
        assert all(item["first_comments"] == "" for item in queue.json())


# ── H2: state transition + immutable decision ledger must be one transaction ──


def test_h2_failed_ledger_insert_rolls_back_the_state_change(service, store, monkeypatch):
    """H2: ``record_decision`` used to open a SECOND transaction AFTER the
    transition had committed, so an I/O failure left a task advanced, with a
    SUBMIT_FIRST audit event, and NO ledger row. Now all three writes share one
    transaction, so a ledger failure rolls everything back."""
    _add_task(store)
    _register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                         expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)
    revision_before = task.revision

    def boom(_record):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "_insert_decision", boom)
    with pytest.raises(sqlite3.OperationalError):
        service.submit_first_review(
            "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
            decision=ReviewDecision.ACCEPT, reason_codes=("SOURCE_MATCH",), comments="ok",
            expected_revision=task.revision, target_version=1,
        )
    monkeypatch.undo()

    after = store.get_task("task-1")
    assert after.lifecycle_state is ReviewState.IN_REVIEW
    assert after.revision == revision_before
    assert after.first_decision == ""
    assert not [e for e in after.audit_history if e.event_type == "SUBMIT_FIRST"]
    assert store.list_decisions("task-1") == []


def test_h2_stale_revision_rolls_back_the_ledger_row_too(service, store, monkeypatch):
    """The concurrency guard must not leave an orphan ledger row either."""
    _add_task(store)
    _register(service.registry, "doctor-a", ReviewRole.REVIEWER_A)
    task = service.claim("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                         expected_revision=0)
    task = service.start_review("task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
                                expected_revision=task.revision)

    real_transition = store.transition

    def racing(previous, current, event, **kwargs):
        # simulate another process having advanced the revision underneath us
        store.connection.execute(
            "UPDATE review_tasks SET revision=revision+1 WHERE task_id=?", (current.task_id,)
        )
        store.connection.commit()
        return real_transition(previous, current, event, **kwargs)

    monkeypatch.setattr(store, "transition", racing)
    from clinical_engine.review_workbench.storage import ConcurrencyError
    with pytest.raises(ConcurrencyError):
        service.submit_first_review(
            "task-1", reviewer="doctor-a", role=ReviewRole.REVIEWER_A,
            decision=ReviewDecision.ACCEPT, reason_codes=(), comments="ok",
            expected_revision=task.revision, target_version=1,
        )
    monkeypatch.undo()
    assert store.list_decisions("task-1") == []


def test_h2_normal_path_still_records_exactly_one_ledger_row(service, store):
    _task_in_second_review(service)
    decisions = store.list_decisions("task-1")
    assert [d.decision_sequence for d in decisions] == [1]
    assert decisions[0].reviewer_id == "doctor-a"
    assert decisions[0].rationale == SECRET


# ── M1: one authorization matrix, not two ───────────────────────────────────


def test_m1_single_role_requirement_is_enforced_from_the_shared_matrix(service):
    """A reviewer registered for BOTH roles still cannot reuse their OWN
    authorised role to perform another role's single-role action — the exact
    case the deleted duplicate matrix documented."""
    _add_task(service.store)
    _register(service.registry, "dual", ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B)
    with pytest.raises(ReviewerValidationError) as exc:
        service.submit_second_review(
            "task-1", reviewer="dual", role=ReviewRole.REVIEWER_A,
            decision=ReviewDecision.ACCEPT, reason_codes=(), comments="",
            expected_revision=0, target_version=1,
        )
    assert exc.value.reason_code == "ROLE_NOT_AUTHORISED"
    assert service.store.list_rejected_attempts("task-1")[-1]["action"] == "submit_second"

    with pytest.raises(ReviewerValidationError) as exc:
        service.adjudicate(
            "task-1", adjudicator="dual", role=ReviewRole.REVIEWER_A,
            decision=ReviewDecision.ACCEPT, reason_codes=(), comments="",
            expected_revision=0, target_version=1,
        )
    assert exc.value.reason_code == "ROLE_NOT_AUTHORISED"


def test_m1_matrix_is_the_only_place_role_rules_live():
    """No second, drifting copy of the role rules anywhere in the package."""
    import inspect

    from clinical_engine.review_workbench import service as service_module
    from clinical_engine.review_workbench import storage as storage_module

    for module in (service_module, storage_module):
        assert "_SINGLE_ROLE_ACTIONS" not in inspect.getsource(module)
    # and the single-role action set is exactly the governed clinical writes
    assert set(permissions.SINGLE_ROLE_ACTIONS) == {
        "submit_first", "submit_second", "adjudicate", "qa_signoff", "close", "waive",
    }
    assert permissions.allowed_roles("submit_first") == frozenset({ReviewRole.REVIEWER_A})
    assert permissions.allowed_roles("claim") == frozenset()
    with pytest.raises(permissions.PermissionDenied):
        permissions.require("qa_signoff", ReviewRole.ADJUDICATOR)
    permissions.require("claim", ReviewRole.REVIEWER_A)  # unconstrained by the matrix


def test_m1_qa_eligible_states_is_the_one_source_for_the_qa_gate():
    """The gate is driven by QA_ELIGIBLE_STATES, not a hardcoded literal."""
    import inspect

    from clinical_engine.review_workbench import service as service_module
    from clinical_engine.review_workbench.models import QA_ELIGIBLE_STATES

    assert QA_ELIGIBLE_STATES == frozenset({ReviewState.MEDICAL_QA_PENDING})
    body = inspect.getsource(service_module.ReviewService.submit_medical_qa_signoff)
    assert "QA_ELIGIBLE_STATES" in body
    assert "is ReviewState.MEDICAL_QA_PENDING" not in body


# ── M2: consensus_result / close_outcome are real enums ─────────────────────


def test_m2_consensus_result_is_a_real_enum_after_second_review(service):
    from clinical_engine.review_workbench.tests.test_governance_hardening import (
        run_to_medical_qa_pending,
    )
    task = run_to_medical_qa_pending(service)
    assert task.consensus_result is ConsensusResult.CONSENSUS_ACCEPT
    # str-backed, so the published string form is unchanged
    assert task.consensus_result == "CONSENSUS_ACCEPT"


def test_m2_close_outcome_is_a_real_enum(service):
    from clinical_engine.review_workbench.tests.test_governance_hardening import (
        run_to_medical_qa_pending,
    )
    task = run_to_medical_qa_pending(service)
    _register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    task = service.submit_medical_qa_signoff(
        "task-1", medical_qa_reviewer_id="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
        verdict=QAVerdict.APPROVE, rationale="ok",
        expected_revision=task.revision, target_version=1,
    )
    task = service.close("task-1", actor="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
                         expected_revision=task.revision)
    assert task.close_outcome is CloseOutcome.CLOSED_APPROVED
    assert task.close_outcome == "CLOSED_APPROVED"


def test_m2_a_typo_in_a_persisted_value_is_rejected_not_silently_accepted():
    with pytest.raises(ValueError):
        consensus_or_blank("CONSENSUS_ACCEPTED")   # near-miss typo
    with pytest.raises(ValueError):
        close_outcome_or_blank("CLOSED_OK")
    assert consensus_or_blank("") == ""
    assert close_outcome_or_blank("") == ""
    assert consensus_or_blank("NEEDS_ADJUDICATION") is ConsensusResult.NEEDS_ADJUDICATION
    assert close_outcome_or_blank("CLOSED_REJECTED") is CloseOutcome.CLOSED_REJECTED


def test_m2_enum_values_persist_and_read_back_as_values(service, store):
    from clinical_engine.review_workbench.tests.test_governance_hardening import (
        run_to_medical_qa_pending,
    )
    task = run_to_medical_qa_pending(service)
    row = store.connection.execute(
        "SELECT consensus_result FROM review_tasks WHERE task_id=?", (task.task_id,)
    ).fetchone()
    # plain vocabulary value in the DB, enum member in memory
    assert row[0] == "CONSENSUS_ACCEPT"
    assert store.get_task(task.task_id).consensus_result is ConsensusResult.CONSENSUS_ACCEPT


def test_m2_consensus_reached_state_is_documented_as_never_persisted(service, store):
    """Kept in the published vocabulary but never written: a completed
    two-reviewer consensus goes straight to MEDICAL_QA_PENDING, because
    consensus alone is never an approval."""
    from clinical_engine.review_workbench.tests.test_governance_hardening import (
        run_to_medical_qa_pending,
    )

    assert ReviewState.CONSENSUS_REACHED.value == "CONSENSUS_REACHED"
    task = run_to_medical_qa_pending(service)
    assert task.lifecycle_state is ReviewState.MEDICAL_QA_PENDING
    assert store.connection.execute(
        "SELECT COUNT(*) FROM review_tasks WHERE lifecycle_state=?",
        (ReviewState.CONSENSUS_REACHED.value,),
    ).fetchone()[0] == 0


# ── M3: SQL identifiers are allow-listed, not interpolated ───────────────────


def test_m3_ddl_identifiers_are_allowlisted(store):
    from clinical_engine.review_workbench import storage as storage_module

    with pytest.raises(ValueError):
        store._column_names("review_tasks; DROP TABLE review_tasks")
    with pytest.raises(ValueError):
        store._column_names("sqlite_master")
    assert "lifecycle_state" in store._column_names("review_tasks")
    assert storage_module._checked_identifier(
        "consensus_result", storage_module._ALLOWED_COLUMN_IDENTIFIERS, "column"
    ) == "consensus_result"


# ── M10/M11: dose-unit audit ────────────────────────────────────────────────


def _dose_db(directory) -> sqlite3.Connection:
    db = directory / "kb.sqlite"
    connection = sqlite3.connect(db)
    connection.executescript("""
        CREATE TABLE objects(id TEXT PRIMARY KEY, type TEXT, content TEXT);
        CREATE TABLE provenance(obj_id TEXT, guideline_id TEXT, pdf TEXT, page INTEGER,
            table_row INTEGER, table_col INTEGER, original_text TEXT);
    """)
    return connection


def test_m10_audit_handles_paths_containing_uri_delimiters(tmp_path):
    """M10: the path was interpolated raw into ``file:<path>?mode=ro``, so a '?'
    or '#' in a directory name terminated the URI early and opened the WRONG
    file (or nothing). ``as_uri()`` percent-escapes them."""
    directory = tmp_path / "kb?draft#2"
    directory.mkdir()
    connection = _dose_db(directory)
    connection.execute(
        "INSERT INTO objects VALUES(?,?,?)",
        ("d1", "Dose", json.dumps({"raw": "1 г", "unit": ""}, ensure_ascii=False)),
    )
    connection.execute(
        "INSERT INTO provenance VALUES(?,?,?,?,?,?,?)", ("d1", "g1", "kr.pdf", 5, 1, 2, "1 г")
    )
    connection.commit()
    connection.close()

    result = audit(directory / "kb.sqlite")
    assert result["total"] == 1
    assert result["records"][0]["object_id"] == "d1"


@pytest.mark.parametrize(
    ("text", "recoverable"),
    [
        ("1 мг", True),
        ("1 mg", True),
        ("500 мкг", True),
        ("1 г", False),
        ("1 g", False),
    ],
)
def test_m11_grams_are_never_automatically_recoverable(text, recoverable):
    """M11: ``_SIMPLE_UNIT`` matches grams, so a source reading "1 г" was
    classified A_PARSER_MISSED_EXPLICIT_UNIT and flagged for AUTOMATIC
    recovery of a gram dose — clinically wrong."""
    category, unit, _ = classify([text])
    assert category == "A_PARSER_MISSED_EXPLICIT_UNIT"
    assert unit is not None
    assert auto_recoverable(category, unit) is recoverable


def test_m11_non_recoverable_categories_stay_non_recoverable():
    category, unit, _ = classify(["1.5"])
    assert category == "G_GENUINELY_MISSING_UNIT"
    assert auto_recoverable(category, unit) is False
    assert auto_recoverable("J_REQUIRES_PHYSICIAN_REVIEW", "мг") is False


# ── guard-rail: the closed() transition must not have lost its gate ──────────


def test_close_before_qa_signoff_is_still_refused(service):
    _add_task(service.store)
    _register(service.registry, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    with pytest.raises(InvalidTransition, match="Medical QA sign-off"):
        service.close("task-1", actor="qa-lead", role=ReviewRole.MEDICAL_QA_LEAD,
                      expected_revision=0)
