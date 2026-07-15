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
    """Governance (lifecycle) state. Never confuse with ConsensusResult —
    two-reviewer agreement alone is CONSENSUS_REACHED, not PHYSICIAN_APPROVED."""
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    IN_REVIEW = "IN_REVIEW"
    SECOND_REVIEW = "SECOND_REVIEW"
    NEEDS_ADJUDICATION = "NEEDS_ADJUDICATION"
    CONSENSUS_REACHED = "CONSENSUS_REACHED"
    MEDICAL_QA_PENDING = "MEDICAL_QA_PENDING"
    PHYSICIAN_APPROVED = "PHYSICIAN_APPROVED"
    REJECTED = "REJECTED"
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
    """Individual reviewer/adjudicator verdict vocabulary."""
    ACCEPT = "ACCEPT"
    ACCEPT_WITH_NOTE = "ACCEPT_WITH_NOTE"
    REJECT_FIDELITY = "REJECT_FIDELITY"
    REJECT_CLINICAL = "REJECT_CLINICAL"
    NEEDS_INFO = "NEEDS_INFO"
    ABSTAIN = "ABSTAIN"


class ConsensusResult(str, Enum):
    """Outcome of comparing Reviewer A and Reviewer B decisions. Distinct from
    ReviewState/governance_state — reaching a consensus is never itself an
    approval."""
    NO_CONSENSUS = "NO_CONSENSUS"
    CONSENSUS_ACCEPT = "CONSENSUS_ACCEPT"
    CONSENSUS_ACCEPT_WITH_NOTE = "CONSENSUS_ACCEPT_WITH_NOTE"
    CONSENSUS_REJECT_FIDELITY = "CONSENSUS_REJECT_FIDELITY"
    CONSENSUS_REJECT_CLINICAL = "CONSENSUS_REJECT_CLINICAL"
    NEEDS_INFO = "NEEDS_INFO"
    NEEDS_ADJUDICATION = "NEEDS_ADJUDICATION"
    ABSTENTION_PENDING = "ABSTENTION_PENDING"


class QAVerdict(str, Enum):
    """Medical QA Lead sign-off vocabulary. This is the only path to
    PHYSICIAN_APPROVED / REJECTED (Phase 6)."""
    APPROVE = "APPROVE"
    APPROVE_WITH_NOTE = "APPROVE_WITH_NOTE"
    RETURN_FOR_ADJUDICATION = "RETURN_FOR_ADJUDICATION"
    RETURN_FOR_REVIEW = "RETURN_FOR_REVIEW"
    REJECT_GOVERNANCE = "REJECT_GOVERNANCE"
    NEEDS_INFO = "NEEDS_INFO"
    ABSTAIN = "ABSTAIN"


class CloseOutcome(str, Enum):
    CLOSED_APPROVED = "CLOSED_APPROVED"
    CLOSED_REJECTED = "CLOSED_REJECTED"
    CLOSED_NEEDS_INFO = "CLOSED_NEEDS_INFO"
    CLOSED_ABSTAINED = "CLOSED_ABSTAINED"
    CLOSED_SUPERSEDED = "CLOSED_SUPERSEDED"


# States after which no further reviewer/adjudicator/QA action is expected.
FINAL_STATES = frozenset({
    ReviewState.PHYSICIAN_APPROVED,
    ReviewState.REJECTED,
    ReviewState.CLOSED,
})

# States a task must reach before Medical QA sign-off is permitted.
QA_ELIGIBLE_STATES = frozenset({ReviewState.MEDICAL_QA_PENDING})


def governance_state(target_type: TargetType, state: ReviewState) -> str:
    """Map internal lifecycle state to the canonical governance vocabulary the
    rest of ANTIBIO (docs, Golden Dataset eligibility, any future Clinical
    Engine wire-up) is allowed to read. TherapeuticOption never reports
    PHYSICIAN_APPROVED — it maps to MEDICALLY_REVIEWED, the existing distinct
    canonical state for that target type, and must never become directly
    consumable as executable regimen data."""
    if state is ReviewState.PHYSICIAN_APPROVED:
        if target_type is TargetType.THERAPEUTIC_OPTION:
            return "MEDICALLY_REVIEWED"
        return "PHYSICIAN_APPROVED"
    if state is ReviewState.REJECTED:
        return "REJECTED"
    if state is ReviewState.CLOSED:
        return "CLOSED"
    return "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class ReviewAssignment:
    """Governed task-level role assignment (Phase 3). Registration alone does
    not grant task access — a reviewer must be explicitly assigned to a task
    in a given role before they may act on it."""
    assignment_id: str
    task_id: str
    reviewer_id: str
    assigned_role: ReviewRole
    assigned_by: str
    assigned_at: str
    active: bool = True
    revoked_at: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ReviewDecisionRecord:
    """Immutable decision ledger entry (Phase 8). Never updated in place —
    corrections create a new record with `supersedes_decision_id` set."""
    decision_id: str
    task_id: str
    target_version: int
    reviewer_id: str
    reviewer_role: ReviewRole
    verdict: str
    reason_codes: tuple[str, ...]
    rationale: str
    source_verified: bool
    submitted_at: str
    decision_sequence: int
    supersedes_decision_id: str = ""


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
    qa_reviewer: str = ""
    decision: str = ""
    reason_codes: tuple[str, ...] = ()
    comments: str = ""
    first_decision: str = ""
    first_reason_codes: tuple[str, ...] = ()
    first_comments: str = ""
    second_decision: str = ""
    second_reason_codes: tuple[str, ...] = ()
    second_comments: str = ""
    consensus_result: str = ""
    qa_verdict: str = ""
    close_outcome: str = ""
    created_at: str = ""
    claimed_at: str = ""
    completed_at: str = ""
    revision: int = 0
    audit_history: tuple[AuditEvent, ...] = field(default_factory=tuple)
