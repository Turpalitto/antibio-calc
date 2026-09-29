"""Governed local service for two-reviewer clinical validation.

Hardened 2026-07-15 (P5.6 Review Governance Hardening) to close GOV-001,
GOV-002, GOV-003: every write requires registry-validated reviewer identity,
Reviewer B is blinded to Reviewer A's verdict until they submit their own,
and consensus alone never equals PHYSICIAN_APPROVED — a Medical QA Lead
sign-off is a mandatory, separate gate.
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import permissions
from .models import (
    AuditEvent, ClinicalReviewTask, CloseOutcome, ConsensusResult, FINAL_STATES, QAVerdict,
    QA_ELIGIBLE_STATES, ReviewAssignment, ReviewDecision, ReviewDecisionRecord, ReviewRole,
    ReviewState, TargetType, consensus_or_blank,
)
from .reviewer_registry import ReviewerRegistry
from .storage import ReviewStore


class InvalidTransition(RuntimeError):
    pass


class ReviewerValidationError(RuntimeError):
    """Raised by every write path when validate_reviewer_action() denies the
    action. Carries the deterministic reason_code (Phase 2)."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def resolve_source_wording(provenance: list[dict[str, Any]], payload: dict[str, Any]) -> list[str | None]:
    """RC-027 canonical fix — REVIEW_PACKET_CONTRACT.md precedence, tiers 1-4, else None (tier 5).

    Tolerates every provenance-dict shape already in production storage (FieldProvenance-derived
    {"field","source_object_id",...}, {"source_quote": ...}, golden-case {"author","source",...})
    without requiring any producer or stored review_targets row to change. One resolved string per
    provenance entry, in storage order — never re-sorted, never deduplicated, never fabricated.
    """
    target_level_quote = payload.get("source_quote") or None          # tier 3

    if not provenance:
        return [target_level_quote] if target_level_quote else [None]

    resolved: list[str | None] = []
    for entry in provenance:
        wording = (
            entry.get("original_text")                    # tier 1: field-level original_text
            or entry.get("source_quote")                   # tier 2: field-level source_quote
            or target_level_quote                           # tier 3: target payload's own source_quote
            or entry.get("source")                          # tier 4: golden-case provenance {"source": ...}
            or None
        )
        resolved.append(wording or None)
    return resolved


def source_wording_missing(resolved: list[str | None]) -> bool:
    """True when tiers 1-4 produced nothing usable for ANY entry — packet is review_blocked."""
    return not any(resolved)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


# Individual-decision -> consensus-direction mapping used by QA sign-off.
_ACCEPT_FAMILY = {ReviewDecision.ACCEPT, ReviewDecision.ACCEPT_WITH_NOTE}
_REJECT_FAMILY = {ReviewDecision.REJECT_FIDELITY, ReviewDecision.REJECT_CLINICAL}

_CONSENSUS_MATCH = {
    (ReviewDecision.ACCEPT, ReviewDecision.ACCEPT): "CONSENSUS_ACCEPT",
    (ReviewDecision.ACCEPT, ReviewDecision.ACCEPT_WITH_NOTE): "CONSENSUS_ACCEPT_WITH_NOTE",
    (ReviewDecision.ACCEPT_WITH_NOTE, ReviewDecision.ACCEPT): "CONSENSUS_ACCEPT_WITH_NOTE",
    (ReviewDecision.ACCEPT_WITH_NOTE, ReviewDecision.ACCEPT_WITH_NOTE): "CONSENSUS_ACCEPT_WITH_NOTE",
    (ReviewDecision.REJECT_FIDELITY, ReviewDecision.REJECT_FIDELITY): "CONSENSUS_REJECT_FIDELITY",
    (ReviewDecision.REJECT_CLINICAL, ReviewDecision.REJECT_CLINICAL): "CONSENSUS_REJECT_CLINICAL",
}


class ReviewService:
    def __init__(self, store: ReviewStore, registry: ReviewerRegistry) -> None:
        self.store = store
        self.registry = registry

    # --- identity validation (Phase 1-2) --------------------------------------

    def _validate(self, task_id: str, reviewer_id: str, role: ReviewRole,
                  target_type: TargetType, action: str) -> None:
        """Registry check first, then the single role-permission matrix.

        ``permissions`` is the ONLY role matrix; this method must not grow a
        second copy of the role rules (that duplication is what let the two
        sources of truth drift apart).
        """
        result = self.registry.validate_reviewer_action(reviewer_id, role, target_type, action)
        if not result.allowed:
            self.store.log_rejected_attempt(
                task_id=task_id, actor=reviewer_id, role=role, action=action,
                reason_code=result.reason_code, timestamp=_now(),
            )
            raise ReviewerValidationError(result.reason_code)
        try:
            permissions.require(action, role)
        except permissions.PermissionDenied as denied:
            self.store.log_rejected_attempt(
                task_id=task_id, actor=reviewer_id, role=role, action=action,
                reason_code="ROLE_NOT_AUTHORISED", timestamp=_now(),
            )
            raise ReviewerValidationError("ROLE_NOT_AUTHORISED") from denied

    def list_queue(self, **filters: Any) -> list[ClinicalReviewTask]:
        return self.store.list_tasks(**filters)

    def get_task(self, task_id: str) -> ClinicalReviewTask:
        return self.store.get_task(task_id)

    def _apply(self, task: ClinicalReviewTask, updated: ClinicalReviewTask, *, actor: str,
               role: ReviewRole, event_type: str, decision: str = "",
               reason_codes: tuple[str, ...] = (), comments: str = "",
               ledger_record: ReviewDecisionRecord | None = None) -> ClinicalReviewTask:
        event = AuditEvent(
            sequence=len(task.audit_history) + 1, actor=actor, role=role, event_type=event_type,
            from_state=task.lifecycle_state, to_state=updated.lifecycle_state, decision=decision,
            reason_codes=reason_codes, comments=comments, timestamp=_now(),
        )
        return self.store.transition(task, updated, event, ledger_record=ledger_record)

    # --- Phase 3: governed assignment -----------------------------------------

    def assign_reviewer(self, task_id: str, *, reviewer_id: str, role: ReviewRole,
                        assigned_by: str) -> ReviewAssignment:
        """Explicit, governed task-level assignment. Registration alone does
        not grant task access."""
        task = self.get_task(task_id)
        self._validate(task_id, reviewer_id, role, task.target_type, "assign")
        if role not in (ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B,
                        ReviewRole.ADJUDICATOR, ReviewRole.MEDICAL_QA_LEAD):
            raise InvalidTransition(f"Cannot assign role {role.value} to a task")
        existing = self.store.active_assignment_for_role(task_id, role)
        if existing is not None:
            raise InvalidTransition(f"{role.value} already assigned to this task")
        if role is ReviewRole.REVIEWER_B:
            reviewer_a = self.store.active_assignment_for_role(task_id, ReviewRole.REVIEWER_A)
            if reviewer_a is not None and reviewer_a.reviewer_id == reviewer_id:
                raise InvalidTransition("SELF_REVIEW_FORBIDDEN: Reviewer A cannot also be Reviewer B")
        if role is ReviewRole.REVIEWER_A:
            reviewer_b = self.store.active_assignment_for_role(task_id, ReviewRole.REVIEWER_B)
            if reviewer_b is not None and reviewer_b.reviewer_id == reviewer_id:
                raise InvalidTransition("SELF_REVIEW_FORBIDDEN: Reviewer B cannot also be Reviewer A")
        assignment = ReviewAssignment(
            assignment_id=_new_id("asg"), task_id=task_id, reviewer_id=reviewer_id,
            assigned_role=role, assigned_by=assigned_by, assigned_at=_now(),
        )
        self.store.add_assignment(assignment)
        return assignment

    def revoke_assignment(self, assignment_id: str, *, reason: str,
                          actor: str | None = None, role: ReviewRole | None = None,
                          expected_task_id: str | None = None) -> ReviewAssignment:
        """Deactivate a task-level assignment; return the revoked record.

        When ``actor``/``role`` are supplied — which is always the case from the
        HTTP surface, where the actor is the authenticated session and never the
        request body — the revocation is governed: the caller must be a
        registered, active reviewer holding ``role``, and must be either the
        person who made the assignment or a registered ADMINISTRATOR. Both
        denials are audit-logged as rejected attempts.

        ``expected_task_id`` pins the revocation to a task, so a caller holding a
        valid assignment id for one task cannot revoke it through another task's
        URL.

        Omitting ``actor`` is the in-process administrative form used by
        maintenance tooling; it carries no registry check, so it must never be
        reachable from a request.
        """
        if not reason.strip():
            raise ValueError("Revocation requires a reason")
        assignment = self.find_assignment(assignment_id)
        if expected_task_id is not None and assignment.task_id != expected_task_id:
            raise InvalidTransition(
                f"assignment {assignment_id} is not on task {expected_task_id}"
            )
        if actor is not None and role is not None:
            self._validate(assignment.task_id, actor, role,
                           self.get_task(assignment.task_id).target_type, "revoke_assignment")
            if role is not ReviewRole.ADMINISTRATOR and assignment.assigned_by != actor:
                self.store.log_rejected_attempt(
                    task_id=assignment.task_id, actor=actor, role=role, action="revoke_assignment",
                    reason_code="ASSIGNMENT_REVOCATION_FORBIDDEN", timestamp=_now(),
                )
                raise ReviewerValidationError("ASSIGNMENT_REVOCATION_FORBIDDEN")
        self.store.revoke_assignment(assignment_id, revoked_at=_now(), reason=reason.strip())
        return assignment

    def find_assignment(self, assignment_id: str) -> ReviewAssignment:
        """Look up one assignment by id across tasks."""
        for task in self.store.list_tasks(limit=1_000_000):
            for assignment in self.store.list_assignments(task.task_id):
                if assignment.assignment_id == assignment_id:
                    return assignment
        raise InvalidTransition(f"Unknown assignment_id: {assignment_id}")

    def _require_active_assignment(self, task_id: str, reviewer_id: str, role: ReviewRole) -> None:
        assignment = self.store.active_assignment_for_role(task_id, role)
        if assignment is None or assignment.reviewer_id != reviewer_id:
            raise InvalidTransition(f"No active {role.value} assignment for {reviewer_id} on this task")

    # --- claim / start ----------------------------------------------------------

    def claim(self, task_id: str, *, reviewer: str, role: ReviewRole,
              expected_revision: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, reviewer, role, task.target_type, "claim")
        if task.revision != expected_revision:
            raise InvalidTransition("Stale task revision")
        if task.lifecycle_state is ReviewState.PENDING:
            if role is not ReviewRole.REVIEWER_A:
                raise InvalidTransition("Only Reviewer A may claim a PENDING task")
            existing = self.store.active_assignment_for_role(task_id, ReviewRole.REVIEWER_A)
            if existing is None:
                self.store.add_assignment(ReviewAssignment(
                    assignment_id=_new_id("asg"), task_id=task_id, reviewer_id=reviewer,
                    assigned_role=ReviewRole.REVIEWER_A, assigned_by=reviewer, assigned_at=_now(),
                ))
            elif existing.reviewer_id != reviewer:
                raise InvalidTransition("Reviewer A already assigned to a different reviewer")
            updated = replace(task, lifecycle_state=ReviewState.CLAIMED,
                              assigned_reviewer=reviewer, claimed_at=_now())
            return self._apply(task, updated, actor=reviewer, role=role, event_type="CLAIM_FIRST")
        if task.lifecycle_state is ReviewState.SECOND_REVIEW:
            if role is not ReviewRole.REVIEWER_B:
                raise InvalidTransition("Only Reviewer B may claim a SECOND_REVIEW task")
            if reviewer == task.assigned_reviewer:
                raise InvalidTransition("SELF_REVIEW_FORBIDDEN: Self-second-review is forbidden")
            if task.second_reviewer and task.second_reviewer != reviewer:
                raise InvalidTransition("Second review already claimed")
            existing = self.store.active_assignment_for_role(task_id, ReviewRole.REVIEWER_B)
            if existing is None:
                self.store.add_assignment(ReviewAssignment(
                    assignment_id=_new_id("asg"), task_id=task_id, reviewer_id=reviewer,
                    assigned_role=ReviewRole.REVIEWER_B, assigned_by=reviewer, assigned_at=_now(),
                ))
            updated = replace(task, second_reviewer=reviewer)
            return self._apply(task, updated, actor=reviewer, role=role, event_type="CLAIM_SECOND")
        raise InvalidTransition(f"Cannot claim task in {task.lifecycle_state.value}")

    def release(self, task_id: str, *, reviewer: str, role: ReviewRole,
                expected_revision: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, reviewer, role, task.target_type, "claim")
        if task.revision != expected_revision or task.lifecycle_state is not ReviewState.CLAIMED:
            raise InvalidTransition("Only current CLAIMED revision can be released")
        if task.assigned_reviewer != reviewer or role is not ReviewRole.REVIEWER_A:
            raise InvalidTransition("Only assigned first reviewer can release")
        updated = replace(task, lifecycle_state=ReviewState.PENDING, assigned_reviewer="", claimed_at="")
        return self._apply(task, updated, actor=reviewer, role=role, event_type="RELEASE")

    def start_review(self, task_id: str, *, reviewer: str, role: ReviewRole,
                     expected_revision: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, reviewer, role, task.target_type, "submit_first")
        if task.revision != expected_revision or task.lifecycle_state is not ReviewState.CLAIMED:
            raise InvalidTransition("Task is not claimable for first review")
        if task.assigned_reviewer != reviewer:
            raise InvalidTransition("Reviewer does not own task")
        updated = replace(task, lifecycle_state=ReviewState.IN_REVIEW)
        return self._apply(task, updated, actor=reviewer, role=role, event_type="START_REVIEW")

    # --- first / second review ---------------------------------------------------

    def submit_first_review(self, task_id: str, *, reviewer: str, role: ReviewRole,
                            decision: ReviewDecision, reason_codes: tuple[str, ...], comments: str,
                            expected_revision: int, target_version: int,
                            source_verified: bool = True) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, reviewer, role, task.target_type, "submit_first")
        if task.revision != expected_revision or task.target_version != target_version:
            raise InvalidTransition("Stale task or target version")
        if task.lifecycle_state not in {ReviewState.CLAIMED, ReviewState.IN_REVIEW}:
            raise InvalidTransition("First review not allowed from current state")
        if task.assigned_reviewer != reviewer:
            raise InvalidTransition("Reviewer does not own task")
        assignment = self.store.active_assignment_for_role(task_id, ReviewRole.REVIEWER_A)
        if assignment is None or assignment.reviewer_id != reviewer:
            raise InvalidTransition("Assignment revoked or missing: cannot submit decision")
        next_state = (
            ReviewState.NEEDS_INFO if decision is ReviewDecision.NEEDS_INFO
            else ReviewState.ABSTAINED if decision is ReviewDecision.ABSTAIN
            else ReviewState.SECOND_REVIEW
        )
        updated = replace(task, lifecycle_state=next_state, decision=decision.value,
                          reason_codes=reason_codes, comments=comments,
                          first_decision=decision.value, first_reason_codes=reason_codes,
                          first_comments=comments)
        return self._apply(
            task, updated, actor=reviewer, role=role, event_type="SUBMIT_FIRST",
            decision=decision.value, reason_codes=reason_codes, comments=comments,
            ledger_record=ReviewDecisionRecord(
                decision_id=_new_id("dec"), task_id=task_id, target_version=target_version,
                reviewer_id=reviewer, reviewer_role=role, verdict=decision.value,
                reason_codes=reason_codes, rationale=comments, source_verified=source_verified,
                submitted_at=_now(), decision_sequence=1,
            ),
        )

    def submit_second_review(self, task_id: str, *, reviewer: str, role: ReviewRole,
                             decision: ReviewDecision, reason_codes: tuple[str, ...], comments: str,
                             expected_revision: int, target_version: int,
                             source_verified: bool = True) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, reviewer, role, task.target_type, "submit_second")
        if task.revision != expected_revision or task.target_version != target_version:
            raise InvalidTransition("Stale task or target version")
        if task.lifecycle_state is not ReviewState.SECOND_REVIEW or task.second_reviewer != reviewer:
            raise InvalidTransition("Second review not claimed by reviewer")
        if reviewer == task.assigned_reviewer:
            raise InvalidTransition("SELF_REVIEW_FORBIDDEN: Self-second-review is forbidden")
        assignment = self.store.active_assignment_for_role(task_id, ReviewRole.REVIEWER_B)
        if assignment is None or assignment.reviewer_id != reviewer:
            raise InvalidTransition("Assignment revoked or missing: cannot submit decision")

        first_decision = ReviewDecision(task.first_decision) if task.first_decision else None

        if decision in {ReviewDecision.NEEDS_INFO, ReviewDecision.ABSTAIN}:
            state = ReviewState.NEEDS_INFO if decision is ReviewDecision.NEEDS_INFO else ReviewState.ABSTAINED
            consensus_result: ConsensusResult | str = (
                ConsensusResult.NEEDS_INFO if decision is ReviewDecision.NEEDS_INFO
                else ConsensusResult.ABSTENTION_PENDING
            )
        elif first_decision is not None and (first_decision, decision) in _CONSENSUS_MATCH:
            consensus_result = ConsensusResult(_CONSENSUS_MATCH[(first_decision, decision)])
            state = ReviewState.MEDICAL_QA_PENDING
        else:
            consensus_result = ConsensusResult.NEEDS_ADJUDICATION
            state = ReviewState.NEEDS_ADJUDICATION

        completed_at = _now() if state in FINAL_STATES else ""
        updated = replace(task, lifecycle_state=state, decision=decision.value,
                          reason_codes=reason_codes, comments=comments, completed_at=completed_at,
                          second_decision=decision.value, second_reason_codes=reason_codes,
                          second_comments=comments, consensus_result=consensus_result)
        return self._apply(
            task, updated, actor=reviewer, role=role, event_type="SUBMIT_SECOND",
            decision=decision.value, reason_codes=reason_codes, comments=comments,
            ledger_record=ReviewDecisionRecord(
                decision_id=_new_id("dec"), task_id=task_id, target_version=target_version,
                reviewer_id=reviewer, reviewer_role=role, verdict=decision.value,
                reason_codes=reason_codes, rationale=comments, source_verified=source_verified,
                submitted_at=_now(), decision_sequence=2,
            ),
        )

    def adjudicate(self, task_id: str, *, adjudicator: str, role: ReviewRole,
                   decision: ReviewDecision, reason_codes: tuple[str, ...], comments: str,
                   expected_revision: int, target_version: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, adjudicator, role, task.target_type, "adjudicate")
        if task.revision != expected_revision or task.target_version != target_version:
            raise InvalidTransition("Stale task or target version")
        if task.lifecycle_state is not ReviewState.NEEDS_ADJUDICATION:
            raise InvalidTransition("Task does not require adjudication")
        if adjudicator in {task.assigned_reviewer, task.second_reviewer}:
            raise InvalidTransition("SELF_REVIEW_FORBIDDEN: adjudicator cannot be a reviewer on this task")
        if decision in {ReviewDecision.NEEDS_INFO, ReviewDecision.ABSTAIN}:
            state = ReviewState.NEEDS_INFO if decision is ReviewDecision.NEEDS_INFO else ReviewState.ABSTAINED
            consensus_result: ConsensusResult | str = (
                ConsensusResult.NEEDS_INFO if decision is ReviewDecision.NEEDS_INFO
                else ConsensusResult.ABSTENTION_PENDING
            )
        else:
            state = ReviewState.MEDICAL_QA_PENDING
            consensus_result = (
                ConsensusResult.CONSENSUS_ACCEPT if decision is ReviewDecision.ACCEPT
                else ConsensusResult.CONSENSUS_ACCEPT_WITH_NOTE if decision is ReviewDecision.ACCEPT_WITH_NOTE
                else ConsensusResult.CONSENSUS_REJECT_FIDELITY if decision is ReviewDecision.REJECT_FIDELITY
                else ConsensusResult.CONSENSUS_REJECT_CLINICAL
            )
        updated = replace(task, lifecycle_state=state, adjudicator=adjudicator,
                          decision=decision.value, reason_codes=reason_codes, comments=comments,
                          consensus_result=consensus_result,
                          completed_at=_now() if state in FINAL_STATES else "")
        return self._apply(
            task, updated, actor=adjudicator, role=role, event_type="ADJUDICATE",
            decision=decision.value, reason_codes=reason_codes, comments=comments,
            ledger_record=ReviewDecisionRecord(
                decision_id=_new_id("dec"), task_id=task_id, target_version=target_version,
                reviewer_id=adjudicator, reviewer_role=role, verdict=decision.value,
                reason_codes=reason_codes, rationale=comments, source_verified=True,
                submitted_at=_now(), decision_sequence=3,
            ),
        )

    # --- Phase 6: Medical QA sign-off ------------------------------------------

    def submit_medical_qa_signoff(self, task_id: str, *, medical_qa_reviewer_id: str,
                                  role: ReviewRole, verdict: QAVerdict, rationale: str,
                                  expected_revision: int, target_version: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, medical_qa_reviewer_id, role, task.target_type, "qa_signoff")
        if task.revision != expected_revision or task.target_version != target_version:
            raise InvalidTransition("Stale task or target version")
        if task.lifecycle_state not in QA_ELIGIBLE_STATES:
            raise InvalidTransition("Task is not awaiting Medical QA sign-off")
        if medical_qa_reviewer_id in {task.assigned_reviewer, task.second_reviewer, task.adjudicator}:
            raise InvalidTransition(
                "SELF_REVIEW_FORBIDDEN: Medical QA Lead cannot have been a reviewer/adjudicator on this task"
            )
        if not rationale.strip():
            raise ValueError("Medical QA sign-off requires rationale")

        # Pre-APPROVE governance checklist (Phase 6).
        if verdict in (QAVerdict.APPROVE, QAVerdict.APPROVE_WITH_NOTE):
            reviewer_a = self.store.active_assignment_for_role(task_id, ReviewRole.REVIEWER_A)
            reviewer_b = self.store.active_assignment_for_role(task_id, ReviewRole.REVIEWER_B)
            if reviewer_a is None or reviewer_b is None:
                raise InvalidTransition("Cannot approve: Reviewer A/B assignment missing")
            if reviewer_a.reviewer_id == reviewer_b.reviewer_id:
                raise InvalidTransition("SELF_REVIEW_FORBIDDEN: Reviewer A and B must differ")
            if not task.first_decision or not task.second_decision:
                raise InvalidTransition("Cannot approve: both decisions must be independently submitted")
            if not task.consensus_result:
                raise InvalidTransition("Cannot approve: no consensus/adjudication result recorded")
            packet = self.packet(task_id)
            if packet["review_blocked"]:
                raise InvalidTransition("Cannot approve: source wording missing (review_blocked)")
            if not packet["source_wording_status"] == "AVAILABLE":
                raise InvalidTransition("Cannot approve: source wording not available")
            if packet["unsupported_checks"]["drug_interactions"] != "NOT AVAILABLE / UNSATISFIABLE":
                raise InvalidTransition("Cannot approve: interaction-check status has been tampered with")

        # QA-direction gate. A Medical QA Lead can never approve a target whose
        # two-reviewer (or adjudicated) direction was a REJECT: an APPROVE
        # verdict on a reject-direction consensus resolves to REJECTED.
        # This is the ONLY QA-direction check — the pre-approval checklist above
        # governs *readiness*, not direction.
        direction_reject = consensus_or_blank(task.consensus_result) in {
            ConsensusResult.CONSENSUS_REJECT_FIDELITY, ConsensusResult.CONSENSUS_REJECT_CLINICAL,
        }

        if verdict is QAVerdict.APPROVE or verdict is QAVerdict.APPROVE_WITH_NOTE:
            state = ReviewState.REJECTED if direction_reject else ReviewState.PHYSICIAN_APPROVED
        elif verdict is QAVerdict.REJECT_GOVERNANCE:
            state = ReviewState.REJECTED
        elif verdict is QAVerdict.RETURN_FOR_ADJUDICATION:
            state = ReviewState.NEEDS_ADJUDICATION
        elif verdict is QAVerdict.RETURN_FOR_REVIEW:
            state = ReviewState.NEEDS_INFO
        elif verdict is QAVerdict.NEEDS_INFO:
            state = ReviewState.NEEDS_INFO
        else:  # ABSTAIN
            state = ReviewState.ABSTAINED

        completed_at = _now() if state in FINAL_STATES else ""
        updated = replace(task, lifecycle_state=state, qa_reviewer=medical_qa_reviewer_id,
                          qa_verdict=verdict.value, completed_at=completed_at)
        return self._apply(
            task, updated, actor=medical_qa_reviewer_id, role=role,
            event_type="MEDICAL_QA_SIGNOFF", decision=verdict.value, comments=rationale,
            ledger_record=ReviewDecisionRecord(
                decision_id=_new_id("dec"), task_id=task_id, target_version=target_version,
                reviewer_id=medical_qa_reviewer_id, reviewer_role=role, verdict=verdict.value,
                reason_codes=(), rationale=rationale, source_verified=True,
                submitted_at=_now(), decision_sequence=4,
            ),
        )

    def request_adjudication(self, task_id: str, *, actor: str, role: ReviewRole, reason: str,
                             expected_revision: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, actor, role, task.target_type, "request_adjudication")
        if not reason.strip():
            raise ValueError("Adjudication request requires reason")
        if task.revision != expected_revision:
            raise InvalidTransition("Stale task revision")
        if task.lifecycle_state not in {
            ReviewState.IN_REVIEW, ReviewState.SECOND_REVIEW,
            ReviewState.NEEDS_INFO, ReviewState.ABSTAINED,
        }:
            raise InvalidTransition("Adjudication cannot be requested from current state")
        if role is not ReviewRole.MEDICAL_QA_LEAD and actor not in {
            task.assigned_reviewer, task.second_reviewer,
        }:
            raise InvalidTransition("Only assigned reviewer or Medical QA Lead can request adjudication")
        updated = replace(task, lifecycle_state=ReviewState.NEEDS_ADJUDICATION)
        return self._apply(task, updated, actor=actor, role=role, event_type="REQUEST_ADJUDICATION",
                           comments=reason.strip())

    # --- Phase 7: close semantics -------------------------------------------------

    def close(self, task_id: str, *, actor: str, role: ReviewRole,
              expected_revision: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, actor, role, task.target_type, "close")
        allowed_states: dict[ReviewState, CloseOutcome] = {
            ReviewState.PHYSICIAN_APPROVED: CloseOutcome.CLOSED_APPROVED,
            ReviewState.REJECTED: CloseOutcome.CLOSED_REJECTED,
            ReviewState.NEEDS_INFO: CloseOutcome.CLOSED_NEEDS_INFO,
            ReviewState.ABSTAINED: CloseOutcome.CLOSED_ABSTAINED,
        }
        if task.revision != expected_revision or task.lifecycle_state not in allowed_states:
            raise InvalidTransition(
                "Cannot close: task must have completed second review, adjudication (if required), "
                "and Medical QA sign-off first"
            )
        updated = replace(task, lifecycle_state=ReviewState.CLOSED,
                          close_outcome=allowed_states[task.lifecycle_state])
        return self._apply(task, updated, actor=actor, role=role, event_type="CLOSE")

    def add_note(self, task_id: str, *, actor: str, role: ReviewRole, comments: str,
                 expected_revision: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, actor, role, task.target_type, "add_note")
        if not comments.strip():
            raise ValueError("Governed note cannot be empty")
        if task.revision != expected_revision:
            raise InvalidTransition("Stale task revision")
        combined = "\n".join(value for value in (task.comments, comments.strip()) if value)
        updated = replace(task, comments=combined)
        return self._apply(task, updated, actor=actor, role=role, event_type="ADD_NOTE", comments=comments)

    def add_waiver(self, task_id: str, *, authority: str, role: ReviewRole, reason: str,
                   expires_at: str, expected_revision: int) -> ClinicalReviewTask:
        task = self.get_task(task_id)
        self._validate(task_id, authority, role, task.target_type, "waive")
        if not authority.strip() or not reason.strip():
            raise ValueError("Waiver requires named authority and reason")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Waiver expiry must be ISO-8601") from error
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError("Waiver expiry must be timezone-aware and in future")
        if task.revision != expected_revision:
            raise InvalidTransition("Stale task revision")
        note = f"WAIVER authority={authority.strip()} expires={expiry.isoformat()} reason={reason.strip()}"
        updated = replace(task, comments="\n".join(value for value in (task.comments, note) if value))
        return self._apply(task, updated, actor=authority, role=role, event_type="ADD_WAIVER", comments=note)

    # --- packets: full (governance-role) vs blinded (Phase 4) -----------------

    def packet(self, task_id: str) -> dict[str, Any]:
        """Unredacted packet. Only for callers already authorised to see the
        complete governance picture (Medical QA Lead, Adjudicator, internal
        reporting). Reviewer-facing code must call packet_for_reviewer()."""
        task = self.get_task(task_id)
        snapshot = self.store.target_snapshot(task)
        wording = resolve_source_wording(snapshot["provenance"], snapshot["payload"])
        blocked = source_wording_missing(wording)
        return {
            "task": asdict(task),
            "normalized_object": snapshot["payload"],
            "original_source_wording": wording,
            "source_wording_status": "MISSING" if blocked else "AVAILABLE",
            "review_blocked": blocked,
            "source_references": snapshot["source_references"],
            "field_level_provenance": snapshot["provenance"],
            "prior_versions": [],
            "detected_conflicts": snapshot["payload"].get("conflicts", []),
            "validation_failures": snapshot["payload"].get("needs_review_reasons", []),
            "decision_options": [decision.value for decision in ReviewDecision],
            "unsupported_checks": {"drug_interactions": "NOT AVAILABLE / UNSATISFIABLE"},
            "snapshot_hash": snapshot["snapshot_hash"],
        }

    @staticmethod
    def _redact_task_view(task: dict[str, Any]) -> dict[str, Any]:
        """Phase 4: strip Reviewer A's decision/rationale/reason codes and any
        derived consensus indicator from ONE task record, entirely — not merely
        hidden in a UI."""
        redacted = copy.deepcopy(task)
        for field_name in ("decision", "first_decision", "first_comments", "comments", "consensus_result"):
            if field_name in redacted:
                redacted[field_name] = ""
        for field_name in ("reason_codes", "first_reason_codes"):
            if field_name in redacted:
                redacted[field_name] = []
        redacted_history = []
        for event in redacted.get("audit_history", []):
            if event.get("event_type") == "SUBMIT_FIRST":
                event = dict(event)
                event["decision"] = ""
                event["reason_codes"] = []
                event["comments"] = ""
            redacted_history.append(event)
        redacted["audit_history"] = redacted_history
        return redacted

    @classmethod
    def _redact_first_reviewer_verdict(cls, packet: dict[str, Any]) -> dict[str, Any]:
        redacted = copy.deepcopy(packet)
        redacted["task"] = cls._redact_task_view(redacted["task"])
        return redacted

    # Roles whose entire job is to review BOTH decisions, so they are exempt
    # from second-reviewer blinding. Keyed on the registry-validated quoted role,
    # not on anything the caller can invent: validate_reviewer_action() has
    # already refused any reviewer_id not authorised for that role.
    _BLINDING_EXEMPT_ROLES = frozenset({ReviewRole.MEDICAL_QA_LEAD, ReviewRole.ADJUDICATOR})

    def _effective_reviewer_role(self, task: ClinicalReviewTask, reviewer_id: str,
                                 claimed_role: ReviewRole) -> ReviewRole:
        """The role a packet request must be *judged* as — derived from the task's
        OWN persisted assignments, never from the role the caller quotes.

        Quoting is self-asserted: the HTTP surface takes ``reviewer_id`` and
        ``role`` as query parameters, so keying redaction on ``claimed_role``
        let anyone simply quote REVIEWER_A (or anything else not in
        _BLINDING_EXEMPT_ROLES) to receive Reviewer A's unredacted verdict,
        comments, consensus indicator and SUBMIT_FIRST audit body. The task
        records who its reviewers are; that record is the only trustworthy input
        to a blinding decision.
        """
        if reviewer_id:
            if reviewer_id == task.assigned_reviewer:
                return ReviewRole.REVIEWER_A
            if reviewer_id == task.second_reviewer:
                return ReviewRole.REVIEWER_B
            for candidate in (ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B):
                assignment = self.store.active_assignment_for_role(task.task_id, candidate)
                if assignment is not None and assignment.reviewer_id == reviewer_id:
                    return candidate
        return claimed_role

    def is_blinded_for(self, task: ClinicalReviewTask, reviewer_id: str, role: ReviewRole) -> bool:
        """The one place the blinding decision is made, for every surface.

        Packet reads and queue projections must agree, so both ask here.
        """
        effective_role = self._effective_reviewer_role(task, reviewer_id, role)
        if effective_role in self._BLINDING_EXEMPT_ROLES:
            return False
        if effective_role is ReviewRole.REVIEWER_A and reviewer_id == task.assigned_reviewer:
            # Reviewer A's own prior submission: nothing is hidden from them.
            return False
        return True

    def task_view_for_reviewer(self, task: ClinicalReviewTask, reviewer_id: str,
                               role: ReviewRole) -> dict[str, Any]:
        """Single-task projection for list surfaces, blinded exactly as a packet is.

        ``list_queue`` returns whole :class:`ClinicalReviewTask` records, so an
        unredacted queue listing leaks Reviewer A's verdict to every caller while
        the task sits in SECOND_REVIEW — the very leak Phase 4 closed for
        ``packet_for_reviewer``, reachable through a cheaper endpoint.
        """
        view = asdict(task)
        return self._redact_task_view(view) if self.is_blinded_for(task, reviewer_id, role) else view

    def packet_for_reviewer(self, task_id: str, reviewer_id: str, role: ReviewRole) -> dict[str, Any]:
        """Role-aware packet rendering (Phase 4). While a task sits in
        SECOND_REVIEW, Reviewer A's verdict, rationale, reason codes, consensus
        indicator and SUBMIT_FIRST audit body are omitted entirely from the
        response — not just the UI.

        Whether a response is blinded is decided by the task's own stored
        assignments (:meth:`_effective_reviewer_role`), not by the role the caller
        quotes. Medical QA Lead / Adjudicator see the full picture because their
        role is exactly to review both decisions. Reviewer A never sees a *prior*
        verdict, and a caller who is neither an exempt role nor the task's own
        first reviewer is treated as a second reviewer and blinded.
        """
        task = self.get_task(task_id)
        self._validate(task_id, reviewer_id, role, task.target_type, "view_packet")
        full = self.packet(task_id)
        return self._redact_first_reviewer_verdict(full) if self.is_blinded_for(
            task, reviewer_id, role) else full

    def export_packet(self, task_id: str, path: str | Path,
                      *, reviewer_id: str | None = None, role: ReviewRole | None = None) -> Path:
        if reviewer_id is not None and role is not None:
            data = self.packet_for_reviewer(task_id, reviewer_id, role)
        else:
            data = self.packet(task_id)
        destination = Path(path)
        destination.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return destination

    def metrics(self) -> dict[str, Any]:
        result = self.store.metrics()
        diagnoses: dict[str, int] = {}
        antibiotics: dict[str, int] = {}
        safety: dict[str, int] = {}
        for task in self.store.list_tasks(limit=1_000_000):
            snapshot = self.store.target_snapshot(task)["payload"]
            diagnosis = str(snapshot.get("diagnosis") or snapshot.get("indication") or "UNKNOWN")
            antibiotic = str(snapshot.get("antibiotic") or snapshot.get("therapeutic_class") or "UNKNOWN")
            diagnoses[diagnosis] = diagnoses.get(diagnosis, 0) + 1
            antibiotics[antibiotic] = antibiotics.get(antibiotic, 0) + 1
            for axis in task.safety_axes:
                safety[axis] = safety.get(axis, 0) + 1
        result.update({"by_diagnosis": diagnoses, "by_antibiotic": antibiotics, "by_safety_category": safety})
        return result
