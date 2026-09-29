"""Review role permission matrix — the single source of truth for authorization.

Administrators cannot approve medicine. There is exactly ONE authorization
matrix for the Review Workbench; :class:`clinical_engine.review_workbench.service.ReviewService`
delegates to :func:`require` instead of keeping a second, parallel copy of the
role rules (that duplication was the bug — two sources of truth for the same
governance decision, one of which nothing read).

Two kinds of entry:

* ``SINGLE_ROLE_ACTIONS`` — the action has exactly ONE legitimate acting role,
  regardless of which other roles the same person is registered for. Without this
  a reviewer's own authorised role could be reused to perform an action that
  requires a different, specific role (e.g. Reviewer A calling adjudicate()
  while quoting a role they legitimately hold).
* ``ROLE_SET_ACTIONS`` — the action is open to any of a set of roles. This is
  additive: the reviewer registry still has to authorise the quoted role, so an
  entry here can only ever remove capability, never grant it.

Actions absent from both maps (``claim``, ``start_review``, ``release``,
``assign``, ``view_packet``) are governed by the reviewer registry plus the
service's own state checks; :func:`require` does not constrain them.
"""

from __future__ import annotations

from .models import ReviewRole

# Actions with exactly one legitimate acting role, regardless of which role a
# caller might otherwise be registered for on their own account.
SINGLE_ROLE_ACTIONS: dict[str, ReviewRole] = {
    "submit_first": ReviewRole.REVIEWER_A,
    "submit_second": ReviewRole.REVIEWER_B,
    "adjudicate": ReviewRole.ADJUDICATOR,
    "qa_signoff": ReviewRole.MEDICAL_QA_LEAD,
    "close": ReviewRole.MEDICAL_QA_LEAD,
    "waive": ReviewRole.MEDICAL_QA_LEAD,
}

# Actions open to a set of roles. The registry remains the authority on whether
# the quoted role is authorised at all; these entries only narrow it further.
ROLE_SET_ACTIONS: dict[str, frozenset[ReviewRole]] = {
    "request_adjudication": frozenset({
        ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B, ReviewRole.MEDICAL_QA_LEAD,
    }),
    "add_note": frozenset({
        ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B, ReviewRole.ADJUDICATOR,
        ReviewRole.MEDICAL_QA_LEAD, ReviewRole.ADMINISTRATOR,
    }),
    "administer": frozenset({ReviewRole.ADMINISTRATOR}),
}


class PermissionDenied(RuntimeError):
    pass


def allowed_roles(action: str) -> frozenset[ReviewRole]:
    """The roles this action permits, or an empty set when the matrix does not
    constrain the action."""
    single = SINGLE_ROLE_ACTIONS.get(action)
    if single is not None:
        return frozenset({single})
    return ROLE_SET_ACTIONS.get(action, frozenset())


def require(action: str, role: ReviewRole) -> None:
    """Raise :class:`PermissionDenied` unless ``role`` may perform ``action``.

    Unknown actions are permitted here on purpose: authorization for them comes
    from the reviewer registry and the service's own state checks.
    """
    permitted = allowed_roles(action)
    if permitted and role not in permitted:
        raise PermissionDenied(f"Role {role.value} cannot perform {action}")


__all__ = [
    "PermissionDenied", "ROLE_SET_ACTIONS", "SINGLE_ROLE_ACTIONS", "allowed_roles", "require",
]
