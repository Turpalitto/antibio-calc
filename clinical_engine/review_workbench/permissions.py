"""Review role permission matrix. Administrators cannot approve medicine."""

from __future__ import annotations

from .models import ReviewRole

PERMISSIONS: dict[str, frozenset[ReviewRole]] = {
    "claim_first": frozenset({ReviewRole.REVIEWER_A}),
    "submit_first": frozenset({ReviewRole.REVIEWER_A}),
    "claim_second": frozenset({ReviewRole.REVIEWER_B}),
    "submit_second": frozenset({ReviewRole.REVIEWER_B}),
    "adjudicate": frozenset({ReviewRole.ADJUDICATOR}),
    "request_adjudication": frozenset({
        ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B, ReviewRole.MEDICAL_QA_LEAD,
    }),
    "close": frozenset({ReviewRole.MEDICAL_QA_LEAD}),
    "waive": frozenset({ReviewRole.MEDICAL_QA_LEAD}),
    "add_note": frozenset({
        ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B, ReviewRole.ADJUDICATOR,
        ReviewRole.MEDICAL_QA_LEAD, ReviewRole.ADMINISTRATOR,
    }),
    "administer": frozenset({ReviewRole.ADMINISTRATOR}),
}


class PermissionDenied(RuntimeError):
    pass


def require(action: str, role: ReviewRole) -> None:
    if role not in PERMISSIONS.get(action, frozenset()):
        raise PermissionDenied(f"Role {role.value} cannot perform {action}")
