"""Immutable domain model for physician review tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TargetType(str, Enum):
    CLINICAL_REGIMEN = "ClinicalRegimen"
    THERAPEUTIC_OPTION = "TherapeuticOption"
    CLINICAL_DATA_ISSUE = "ClinicalDataIssue"
    CORPUS_EXCLUSION_DECISION = "CorpusExclusionDecision"
    CONFLICT_RECORD = "ConflictRecord"
    GOLDEN_CASE = "GoldenCase"


class PriorityBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewState(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    IN_REVIEW = "IN_REVIEW"
    SECOND_REVIEW = "SECOND_REVIEW"
    NEEDS_ADJUDICATION = "NEEDS_ADJUDICATION"
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_NOTE = "ACCEPTED_WITH_NOTE"
    REJECTED_FIDELITY = "REJECTED_FIDELITY"
    REJECTED_CLINICAL = "REJECTED_CLINICAL"
    NEEDS_INFO = "NEEDS_INFO"
    ABSTAINED = "ABSTAINED"
    CLOSED = "CLOSED"


class ReviewRole(str, Enum):
    REVIEWER_A = "REVIEWER_A"
    REVIEWER_B = "REVIEWER_B"
    ADJUDICATOR = "ADJUDICATOR"
    MEDICAL_QA_LEAD = "MEDICAL_QA_LEAD"
    ADMINISTRATOR = "ADMINISTRATOR"


class ReviewDecision(str, Enum):
    ACCEPT = "ACCEPT"
    ACCEPT_WITH_NOTE = "ACCEPT_WITH_NOTE"
    REJECT_FIDELITY = "REJECT_FIDELITY"
    REJECT_CLINICAL = "REJECT_CLINICAL"
    NEEDS_INFO = "NEEDS_INFO"
    ABSTAIN = "ABSTAIN"


FINAL_STATES = frozenset({
    ReviewState.ACCEPTED,
    ReviewState.ACCEPTED_WITH_NOTE,
    ReviewState.REJECTED_FIDELITY,
    ReviewState.REJECTED_CLINICAL,
    ReviewState.CLOSED,
})


def governance_state(state: ReviewState, decision: str = "") -> str:
    if state in {ReviewState.ACCEPTED, ReviewState.ACCEPTED_WITH_NOTE}:
        return "PHYSICIAN_APPROVED"
    if state in {ReviewState.REJECTED_FIDELITY, ReviewState.REJECTED_CLINICAL}:
        return "REJECTED"
    if state is ReviewState.CLOSED:
        if decision in {ReviewDecision.ACCEPT.value, ReviewDecision.ACCEPT_WITH_NOTE.value}:
            return "PHYSICIAN_APPROVED"
        if decision in {ReviewDecision.REJECT_FIDELITY.value, ReviewDecision.REJECT_CLINICAL.value}:
            return "REJECTED"
    return "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    sequence: int
    actor: str
    role: ReviewRole
    event_type: str
    from_state: ReviewState
    to_state: ReviewState
    decision: str = ""
    reason_codes: tuple[str, ...] = ()
    comments: str = ""
    timestamp: str = ""


@dataclass(frozen=True, slots=True)
class ClinicalReviewTask:
    task_id: str
    task_key: str
    target_type: TargetType
    target_id: str
    target_version: int
    priority_score: int
    priority: PriorityBand
    issue_type: str
    severity: Severity
    safety_axes: tuple[str, ...]
    source_references: tuple[dict[str, Any], ...]
    provenance_references: tuple[dict[str, Any], ...]
    lifecycle_state: ReviewState = ReviewState.PENDING
    assigned_reviewer: str = ""
    second_reviewer: str = ""
    adjudicator: str = ""
    decision: str = ""
    reason_codes: tuple[str, ...] = ()
    comments: str = ""
    created_at: str = ""
    claimed_at: str = ""
    completed_at: str = ""
    revision: int = 0
    audit_history: tuple[AuditEvent, ...] = field(default_factory=tuple)
