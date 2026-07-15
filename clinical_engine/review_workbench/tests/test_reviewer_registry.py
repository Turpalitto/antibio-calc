"""Reviewer registration workflow tests. No identity is invented here — every
registered reviewer in these tests is a synthetic test fixture, never treated
as a real clinician, and never used to submit a real review decision."""

from datetime import datetime, timezone

import pytest

from clinical_engine.review_workbench.models import ReviewRole
from clinical_engine.review_workbench.reviewer_registry import (
    ReviewerRegistrationError, ReviewerRegistry, pilot_status,
)


@pytest.fixture
def registry(tmp_path):
    reg = ReviewerRegistry(tmp_path / "reviewers.sqlite")
    yield reg
    reg.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_empty_registry_is_waiting_for_reviewers(registry):
    assert pilot_status(registry) == "WAITING_FOR_REVIEWERS"


def test_register_requires_organisation(registry):
    with pytest.raises(ReviewerRegistrationError):
        registry.register(
            reviewer_id="r1", display_name="Test Reviewer", professional_role="physician",
            organisation="", authorised_scope=(ReviewRole.REVIEWER_A,),
            registered_at=_now(), registered_by="owner",
        )


def test_register_requires_at_least_one_role(registry):
    with pytest.raises(ReviewerRegistrationError):
        registry.register(
            reviewer_id="r1", display_name="Test Reviewer", professional_role="physician",
            organisation="Test Clinic", authorised_scope=(),
            registered_at=_now(), registered_by="owner",
        )


def test_duplicate_reviewer_id_rejected(registry):
    registry.register(
        reviewer_id="r1", display_name="Test Reviewer", professional_role="physician",
        organisation="Test Clinic", authorised_scope=(ReviewRole.REVIEWER_A,),
        registered_at=_now(), registered_by="owner",
    )
    with pytest.raises(ReviewerRegistrationError):
        registry.register(
            reviewer_id="r1", display_name="Someone Else", professional_role="physician",
            organisation="Test Clinic", authorised_scope=(ReviewRole.REVIEWER_B,),
            registered_at=_now(), registered_by="owner",
        )


def test_only_reviewer_a_registered_still_waiting(registry):
    registry.register(
        reviewer_id="r1", display_name="Test Reviewer A", professional_role="physician",
        organisation="Test Clinic", authorised_scope=(ReviewRole.REVIEWER_A,),
        registered_at=_now(), registered_by="owner",
    )
    assert pilot_status(registry) == "WAITING_FOR_REVIEWERS"


def test_same_person_only_role_still_waiting(registry):
    """A single person registered for both A and B roles must not count as two
    independent reviewers — independence requires distinct people."""
    registry.register(
        reviewer_id="r1", display_name="Test Reviewer", professional_role="physician",
        organisation="Test Clinic", authorised_scope=(ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B),
        registered_at=_now(), registered_by="owner",
    )
    assert pilot_status(registry) == "WAITING_FOR_REVIEWERS"


def test_two_distinct_reviewers_registered_are_ready(registry):
    registry.register(
        reviewer_id="r1", display_name="Test Reviewer A", professional_role="physician",
        organisation="Test Clinic", authorised_scope=(ReviewRole.REVIEWER_A,),
        registered_at=_now(), registered_by="owner",
    )
    registry.register(
        reviewer_id="r2", display_name="Test Reviewer B", professional_role="physician",
        organisation="Test Clinic", authorised_scope=(ReviewRole.REVIEWER_B,),
        registered_at=_now(), registered_by="owner",
    )
    assert pilot_status(registry) == "REVIEWERS_REGISTERED"


def test_unknown_reviewer_id_rejected(registry):
    with pytest.raises(ReviewerRegistrationError):
        registry.require_registered_active("nonexistent", ReviewRole.REVIEWER_A)


def test_inactive_reviewer_rejected(registry):
    registry.register(
        reviewer_id="r1", display_name="Test Reviewer", professional_role="physician",
        organisation="Test Clinic", authorised_scope=(ReviewRole.REVIEWER_A,),
        registered_at=_now(), registered_by="owner",
    )
    registry.deactivate("r1")
    with pytest.raises(ReviewerRegistrationError):
        registry.require_registered_active("r1", ReviewRole.REVIEWER_A)


def test_reviewer_not_authorised_for_role_rejected(registry):
    registry.register(
        reviewer_id="r1", display_name="Test Reviewer", professional_role="physician",
        organisation="Test Clinic", authorised_scope=(ReviewRole.REVIEWER_A,),
        registered_at=_now(), registered_by="owner",
    )
    with pytest.raises(ReviewerRegistrationError):
        registry.require_registered_active("r1", ReviewRole.ADJUDICATOR)
