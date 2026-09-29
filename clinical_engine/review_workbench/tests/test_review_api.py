from __future__ import annotations

from fastapi.testclient import TestClient

from datetime import datetime, timezone

from clinical_engine.review_workbench.api import create_app
from clinical_engine.review_workbench.models import (
    ClinicalReviewTask,
    PriorityBand,
    ReviewRole,
    Severity,
    TargetType,
)
from clinical_engine.review_workbench.reviewer_registry import ReviewerRegistry
from clinical_engine.review_workbench.storage import ReviewStore


def seed(path):
    with ReviewStore(path) as store:
        provenance = [{"field": "dose", "original_text": "500 мг"}]
        sources = [{"pdf": "source.pdf", "page": 3}]
        store.add_target(TargetType.CLINICAL_REGIMEN, "r-1", 1, {"diagnosis": "x"}, provenance, sources)
        store.add_task(ClinicalReviewTask(
            task_id="task-1", task_key="ClinicalRegimen|r-1|1|review",
            target_type=TargetType.CLINICAL_REGIMEN, target_id="r-1", target_version=1,
            priority_score=80, priority=PriorityBand.HIGH, issue_type="review",
            severity=Severity.HIGH, safety_axes=("renal",), source_references=tuple(sources),
            provenance_references=tuple(provenance), created_at="2026-01-01T00:00:00+00:00",
        ))


def seed_reviewer(registry_path, reviewer_id="reviewer-a", *roles):
    with ReviewerRegistry(registry_path) as registry:
        registry.register(
            reviewer_id=reviewer_id, display_name="Synthetic Reviewer", professional_role="physician",
            organisation="Test Clinic", authorised_scope=roles or (ReviewRole.REVIEWER_A,),
            registered_at=datetime.now(timezone.utc).isoformat(), registered_by="test-harness",
        )


def _app(path, tmp_path):
    return create_app(path, registry_path=tmp_path / "reviewers.sqlite")


def _client(app):
    # base_url must be loopback: the workbench refuses a non-loopback Host.
    return TestClient(app, base_url="http://127.0.0.1")


def _session(registry_path, reviewer_id):
    """Mint a real reviewer session token for an already-registered reviewer.

    Returns the raw token, which the caller must send as the ``X-Review-Token``
    header. Tests that drive a clinical endpoint through HTTP use this instead of
    putting a reviewer_id in the JSON body — the body is no longer, and must
    never be, the authentication.
    """
    with ReviewerRegistry(registry_path) as registry:
        return registry.issue_session_token(reviewer_id)


def test_dashboard_declares_engine_disconnected(tmp_path):
    path = tmp_path / "api.sqlite"
    seed(path)
    with _client(_app(path, tmp_path)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["clinical_engine_connected"] is False


def test_queue_filters(tmp_path):
    # The queue returns whole task records (including verdicts), so it is an
    # authenticated, role-blinded surface and the caller must present a session.
    path = tmp_path / "api.sqlite"
    seed(path)
    seed_reviewer(tmp_path / "reviewers.sqlite", "reviewer-a", ReviewRole.REVIEWER_A)
    token = _session(tmp_path / "reviewers.sqlite", "reviewer-a")
    with _client(_app(path, tmp_path)) as client:
        response = client.get(
            "/queue", params={"priority": "HIGH", "state": "PENDING"},
            headers={"X-Review-Token": token},
        )
        assert response.status_code == 200
        assert [item["task_id"] for item in response.json()] == ["task-1"]


def test_task_details_expose_source_and_provenance(tmp_path):
    path = tmp_path / "api.sqlite"
    seed(path)
    seed_reviewer(tmp_path / "reviewers.sqlite", "reviewer-a", ReviewRole.REVIEWER_A)
    token = _session(tmp_path / "reviewers.sqlite", "reviewer-a")
    with _client(_app(path, tmp_path)) as client:
        packet = client.get(
            "/tasks/task-1", params={"role": "REVIEWER_A"},
            headers={"X-Review-Token": token},
        ).json()
        assert packet["source_references"][0] == {"page": 3, "pdf": "source.pdf"}
        assert packet["field_level_provenance"][0]["original_text"] == "500 мг"


def test_administrator_cannot_claim_clinical_review(tmp_path):
    # Registered ADMINISTRATOR, authenticated as themselves: the refusal is now
    # the registry's authorisation decision (403), not a missing token (401).
    path = tmp_path / "api.sqlite"
    seed(path)
    seed_reviewer(tmp_path / "reviewers.sqlite", "admin", ReviewRole.ADMINISTRATOR)
    token = _session(tmp_path / "reviewers.sqlite", "admin")
    with _client(_app(path, tmp_path)) as client:
        response = client.post(
            "/tasks/task-1/claim",
            json={"actor": "admin", "role": "ADMINISTRATOR", "expected_revision": 0},
            headers={"X-Review-Token": token},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "ADMIN_CLINICAL_ACTION_FORBIDDEN"


def test_ui_is_local_review_surface(tmp_path):
    path = tmp_path / "api.sqlite"
    seed(path)
    with _client(_app(path, tmp_path)) as client:
        response = client.get("/ui")
        assert response.status_code == 200
        assert "LOCAL_REVIEW_ONLY" in response.text
        assert "X-Review-Token" in response.text


def test_review_support_views_exist(tmp_path):
    path = tmp_path / "api.sqlite"
    seed(path)
    with _client(_app(path, tmp_path)) as client:
        for route in ("/ui/metrics", "/ui/issues", "/ui/corpus"):
            assert client.get(route).status_code == 200
