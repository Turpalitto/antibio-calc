"""Negative and positive tests for Review Workbench session authentication.

The defect these pin: every write endpoint in ``api.py`` used to read the acting
identity out of the JSON body (``service.claim(task_id, reviewer=request.actor,
...)``) and ``ReviewerRegistry`` only proved that the reviewer_id *string*
existed in the database. Anyone who could reach the port could therefore act as
any registered reviewer and drive a record to PHYSICIAN_APPROVED.

Every fixture here is synthetic; no real reviewer identity or pilot task is used.
The positive test at the bottom runs the whole governed workflow over HTTP with
nothing but a session token, which is the property the bug removed.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from clinical_engine.review_workbench import auth
from clinical_engine.review_workbench.api import create_app
from clinical_engine.review_workbench.models import (
    ClinicalReviewTask, PriorityBand, ReviewRole, ReviewState, Severity, TargetType,
)
from clinical_engine.review_workbench.reviewer_registry import ReviewerRegistry
from clinical_engine.review_workbench.storage import ReviewStore

HEADER = auth.TOKEN_HEADER


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _register(registry_path, reviewer_id, *roles):
    with ReviewerRegistry(registry_path) as registry:
        registry.register(
            reviewer_id=reviewer_id, display_name=f"Synthetic {reviewer_id}",
            professional_role="physician", organisation="Test Clinic",
            authorised_scope=roles, registered_at=_now(), registered_by="test-harness",
        )


def _add_task(store, task_id="task-1", target_id="regimen-1"):
    provenance = [{"field": "dose", "original_text": "500 мг", "page": 7}]
    sources = [{"pdf": "guideline.pdf", "page": 7}]
    store.add_target(TargetType.CLINICAL_REGIMEN, target_id, 1,
                     {"diagnosis": "acute cystitis",
                      "source_quote": "Ципрофлоксацин 500 мг 2 раза в сутки."},
                     provenance, sources)
    store.add_task(ClinicalReviewTask(
        task_id=task_id, task_key=f"ClinicalRegimen|{target_id}|1|review",
        target_type=TargetType.CLINICAL_REGIMEN, target_id=target_id, target_version=1,
        priority_score=80, priority=PriorityBand.HIGH, issue_type="review",
        severity=Severity.HIGH, safety_axes=("renal",),
        source_references=tuple(sources), provenance_references=tuple(provenance),
        created_at="2026-01-01T00:00:00+00:00",
    ))


def _session_token(registry_path, reviewer_id):
    with ReviewerRegistry(registry_path) as registry:
        return registry.issue_session_token(reviewer_id)


def _owner_token(registry_path):
    with ReviewerRegistry(registry_path) as registry:
        return registry.ensure_owner_token()


@pytest.fixture
def workbench(tmp_path):
    """A seeded workbench with four registered reviewers, each holding only
    their own role(s) plus a real session token."""
    db = tmp_path / "api.sqlite"
    registry_path = tmp_path / "reviewers.sqlite"
    with ReviewStore(db) as store:
        _add_task(store)
    _register(registry_path, "reviewer-a", ReviewRole.REVIEWER_A)
    _register(registry_path, "reviewer-b", ReviewRole.REVIEWER_B)
    _register(registry_path, "adjudicator", ReviewRole.ADJUDICATOR)
    _register(registry_path, "qa-lead", ReviewRole.MEDICAL_QA_LEAD)
    tokens = {who: _session_token(registry_path, who)
              for who in ("reviewer-a", "reviewer-b", "adjudicator", "qa-lead")}
    # Issued here, the way the CLI does on first run, so every test knows the
    # owner token deterministically even after create_app() stops being able to
    # show it again.
    owner_token = _owner_token(registry_path)
    return {"db": db, "registry_path": registry_path, "tokens": tokens,
            "owner_token": owner_token}


def _client(workbench, **kwargs):
    return TestClient(
        create_app(workbench["db"], registry_path=workbench["registry_path"]),
        base_url="http://127.0.0.1", **kwargs,
    )


def _auth(token):
    return {HEADER: token}


# ── the bug, restated: a JSON body alone must not authorise anything ─────────


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/tasks/task-1/claim",
         {"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0}),
        ("post", "/tasks/task-1/assign",
         {"reviewer_id": "reviewer-a", "role": "REVIEWER_A", "assigned_by": "qa-lead"}),
        ("post", "/tasks/task-1/notes",
         {"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0,
          "comments": "written by somebody nobody authenticated"}),
        ("post", "/tasks/task-1/close",
         {"actor": "qa-lead", "role": "MEDICAL_QA_LEAD", "expected_revision": 0}),
    ],
)
def test_auth01_a_bare_reviewer_id_in_a_body_is_rejected(workbench, method, path, body):
    """The pre-fix behaviour: naming a registered reviewer in the body was
    enough. It must now be a 401 — not a silent success."""
    with _client(workbench) as client:
        response = getattr(client, method)(path, json=body)
    assert response.status_code == 401
    assert response.json()["detail"] == auth.REVIEW_TOKEN_MISSING


def test_auth02_packet_reads_also_require_a_token(workbench):
    """Not only writes: a review packet is clinical content."""
    with _client(workbench) as client:
        assert client.get("/tasks/task-1", params={"role": "REVIEWER_A"}).status_code == 401
        assert client.get("/tasks/task-1/export", params={"role": "REVIEWER_A"}).status_code == 401
        assert client.get("/queue").status_code == 401


def test_auth03_a_wrong_token_is_rejected(workbench):
    with _client(workbench) as client:
        response = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers=_auth("not-even-a-real-token"),
        )
    assert response.status_code == 401
    assert response.json()["detail"] == auth.REVIEW_TOKEN_INVALID


def test_auth04_a_blank_token_is_rejected(workbench):
    with _client(workbench) as client:
        response = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers=_auth("   "),
        )
    assert response.status_code == 401
    assert response.json()["detail"] == auth.REVIEW_TOKEN_MISSING


def test_auth05_another_reviewers_token_cannot_act_as_someone_else(workbench):
    """reviewer-b's token + ``actor: reviewer-a`` is a contradiction, not a
    preference. Rejecting it is the whole point of deriving identity from the
    session."""
    with _client(workbench) as client:
        response = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers=_auth(workbench["tokens"]["reviewer-b"]),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == auth.IDENTITY_MISMATCH


def test_auth06_a_body_contradicting_the_session_is_rejected_on_every_write(workbench):
    """The contradiction check is not per-endpoint: claim, assign, notes,
    waivers, adjudication request, QA sign-off and close all take their actor
    from the session and all reject a mismatching body."""
    bodies = {
        "claim": {"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
        "start": {"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
        "release": {"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
        "first-review": {"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0,
                         "decision": "ACCEPT", "target_version": 1},
        "second-review": {"actor": "reviewer-a", "role": "REVIEWER_B", "expected_revision": 0,
                          "decision": "ACCEPT", "target_version": 1},
        "adjudicate": {"actor": "adjudicator", "role": "ADJUDICATOR", "expected_revision": 0,
                       "decision": "ACCEPT", "target_version": 1},
        "qa-signoff": {"actor": "qa-lead", "role": "MEDICAL_QA_LEAD", "expected_revision": 0,
                       "verdict": "APPROVE", "rationale": "ok", "target_version": 1},
        "request-adjudication": {"actor": "reviewer-a", "role": "REVIEWER_A",
                                 "expected_revision": 0, "comments": "why"},
        "notes": {"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0,
                  "comments": "hello"},
        "waivers": {"actor": "qa-lead", "role": "MEDICAL_QA_LEAD", "expected_revision": 0,
                    "reason": "r", "expires_at": "2099-01-01T00:00:00+00:00"},
        "close": {"actor": "qa-lead", "role": "MEDICAL_QA_LEAD", "expected_revision": 0},
    }
    # reviewer-b's session, but every body above names somebody else.
    with _client(workbench) as client:
        for action, body in bodies.items():
            response = client.post(
                f"/tasks/task-1/{action}", json=body,
                headers=_auth(workbench["tokens"]["reviewer-b"]),
            )
            assert response.status_code == 403, action
            assert response.json()["detail"] == auth.IDENTITY_MISMATCH, action
        # …and so does an assign that names a stranger as the assigner.
        response = client.post(
            "/tasks/task-1/assign",
            json={"reviewer_id": "reviewer-a", "role": "REVIEWER_A", "assigned_by": "qa-lead"},
            headers=_auth(workbench["tokens"]["reviewer-b"]),
        )
        assert response.status_code == 403
        assert response.json()["detail"] == auth.IDENTITY_MISMATCH
    # No state moved: the task is untouched.
    with ReviewStore(workbench["db"]) as store:
        task = store.get_task("task-1")
    assert task.lifecycle_state is ReviewState.PENDING
    assert task.revision == 0
    assert task.audit_history == ()


def test_auth07_a_query_parameter_cannot_contradict_the_session(workbench):
    """``reviewer_id`` in the query string is an identity claim too."""
    with _client(workbench) as client:
        response = client.get(
            "/tasks/task-1", params={"reviewer_id": "reviewer-a", "role": "REVIEWER_A"},
            headers=_auth(workbench["tokens"]["reviewer-b"]),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == auth.IDENTITY_MISMATCH


def test_auth08_non_loopback_peer_is_rejected(workbench):
    """A request that provably did not come from this machine."""
    with _client(workbench, client=("203.0.113.7", 51234)) as client:
        response = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers=_auth(workbench["tokens"]["reviewer-a"]),
        )
    assert response.status_code == 401
    assert response.json()["detail"] == auth.NON_LOOPBACK_REQUEST


def test_auth09_non_loopback_host_header_is_rejected(workbench):
    """A valid token presented to a Host that is not loopback — i.e. a rebinding
    or DNS-spoof attempt against a browser session."""
    with _client(workbench) as client:
        response = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers={**_auth(workbench["tokens"]["reviewer-a"]), "host": "reviewer.example.com"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == auth.NON_LOOPBACK_REQUEST


def test_auth10_non_loopback_origin_is_rejected(workbench):
    """A web page on another host cannot drive the workbench with a token it
    somehow has, because the Origin is refused."""
    with _client(workbench) as client:
        response = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers={**_auth(workbench["tokens"]["reviewer-a"]),
                     "origin": "https://attacker.example"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == auth.NON_LOOPBACK_REQUEST


def test_auth11_an_exception_in_the_auth_path_rejects_rather_than_allows(workbench, monkeypatch):
    """Fail closed: if the token lookup itself breaks, the request is refused.
    There must be no path where a broken authenticator becomes an allow."""
    app = create_app(workbench["db"], registry_path=workbench["registry_path"])

    def boom(_raw):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(app.state.registry, "authenticate_session_token", boom)
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        response = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers=_auth(workbench["tokens"]["reviewer-a"]),
        )
    assert response.status_code == 401
    assert response.json()["detail"] == auth.REVIEW_AUTH_UNAVAILABLE
    with ReviewStore(workbench["db"]) as store:
        assert store.get_task("task-1").lifecycle_state is ReviewState.PENDING


def test_auth11b_an_exception_in_the_ownership_check_rejects_rather_than_allows(
    workbench, monkeypatch,
):
    """The same fail-closed guarantee on the owner-only path: a broken
    authenticator must not fall through to "you are the owner"."""
    app = create_app(workbench["db"], registry_path=workbench["registry_path"])

    def boom(_raw):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(app.state.registry, "authenticate_session_token", boom)
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        response = client.post("/reviewers/reviewer-a/session-token",
                               headers=_auth(workbench["owner_token"]))
    assert response.status_code == 401
    assert response.json()["detail"] == auth.REVIEW_AUTH_UNAVAILABLE


def test_auth12_a_malformed_request_object_cannot_pass_the_loopback_check():
    """The loopback helper is total: anything it cannot understand is refused."""

    class Broken:
        @property
        def client(self):
            raise RuntimeError("no peer information")

    assert auth.is_loopback_request(Broken()) is False
    assert auth.is_loopback_request(object()) is False


def test_auth13_only_the_token_digest_is_persisted(workbench):
    """The raw token must not be recoverable from the registry database, and
    must never appear in the review database or the audit log."""
    token = workbench["tokens"]["reviewer-a"]
    with ReviewerRegistry(workbench["registry_path"]) as registry:
        rows = registry.connection.execute(
            "SELECT reviewer_id, token_sha256 FROM reviewer_sessions"
        ).fetchall()
    assert {row["reviewer_id"] for row in rows} == {
        "reviewer-a", "reviewer-b", "adjudicator", "qa-lead", auth.OWNER_SESSION,
    }
    for row in rows:
        assert len(row["token_sha256"]) == 64  # hex SHA-256
        assert token not in row["token_sha256"]
        if row["reviewer_id"] in workbench["tokens"]:
            assert row["token_sha256"] == auth.sha256_text(workbench["tokens"][row["reviewer_id"]])
        else:
            assert row["token_sha256"] == auth.sha256_text(workbench["owner_token"])
    with ReviewStore(workbench["db"]) as store:
        dump = "\n".join(store.connection.iterdump())
    assert token not in dump
    assert workbench["owner_token"] not in dump
    assert auth.sha256_text(token) not in dump


def test_auth14_reissuing_a_token_invalidates_the_previous_one(workbench):
    with ReviewerRegistry(workbench["registry_path"]) as registry:
        replacement = registry.issue_session_token("reviewer-a")
    assert replacement != workbench["tokens"]["reviewer-a"]
    with _client(workbench) as client:
        stale = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers=_auth(workbench["tokens"]["reviewer-a"]),
        )
        fresh = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers=_auth(replacement),
        )
    assert stale.status_code == 401
    assert fresh.status_code == 200


def test_auth15_a_revoked_token_stops_working(workbench):
    with ReviewerRegistry(workbench["registry_path"]) as registry:
        registry.revoke_session_token("reviewer-a")
    with _client(workbench) as client:
        response = client.post(
            "/tasks/task-1/claim",
            json={"actor": "reviewer-a", "role": "REVIEWER_A", "expected_revision": 0},
            headers=_auth(workbench["tokens"]["reviewer-a"]),
        )
    assert response.status_code == 401


def test_auth16_the_owner_token_may_not_perform_clinical_actions(workbench):
    """The owner mints tokens; it is not a registered reviewer, so it can never
    claim, review, adjudicate or sign off."""
    app = create_app(workbench["db"], registry_path=workbench["registry_path"])
    with TestClient(app, base_url="http://127.0.0.1") as client:
        owner = _auth(workbench["owner_token"])
        assert client.post(
            "/tasks/task-1/claim",
            json={"actor": "qa-lead", "role": "REVIEWER_A", "expected_revision": 0},
            headers=owner,
        ).status_code == 403
        # it may mint a session, and only for an already-registered reviewer
        minted = client.post("/reviewers/reviewer-a/session-token", headers=owner)
        assert minted.status_code == 200
        assert minted.json()["reviewer_id"] == "reviewer-a"
        assert client.post("/reviewers/stranger/session-token", headers=owner).status_code == 403


def test_auth17_a_reviewer_session_may_not_mint_sessions(workbench):
    with _client(workbench) as client:
        response = client.post(
            "/reviewers/reviewer-b/session-token",
            headers=_auth(workbench["tokens"]["reviewer-a"]),
        )
    assert response.status_code == 401
    assert response.json()["detail"] == auth.OWNER_SESSION_REQUIRED


def test_auth18_revoked_sessions_cannot_be_issued_without_the_owner_token(workbench):
    with _client(workbench) as client:
        assert client.delete(
            "/reviewers/reviewer-a/session-token",
            headers=_auth(workbench["tokens"]["reviewer-a"]),
        ).status_code == 401


def test_auth18b_a_deactivated_reviewer_cannot_be_given_a_token(workbench):
    """Possession of a token is not authorisation: standing a reviewer down
    closes the door at the door, not just at every endpoint."""
    with ReviewerRegistry(workbench["registry_path"]) as registry:
        registry.deactivate("reviewer-a")
    app = create_app(workbench["db"], registry_path=workbench["registry_path"])
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/reviewers/reviewer-a/session-token",
                               headers=_auth(workbench["owner_token"]))
    assert response.status_code == 403
    assert "REVIEWER_INACTIVE" in response.json()["detail"]


# ── revoke_assignment is under the same authentication ──────────────────────


def test_auth19_revoke_assignment_requires_a_session(workbench):
    assignment_id = _assign_via_api(workbench)
    with _client(workbench) as client:
        response = client.post(
            f"/tasks/task-1/assignments/{assignment_id}/revoke",
            json={"reason": "reassigned", "role": "MEDICAL_QA_LEAD"},
            headers=_auth(workbench["tokens"]["qa-lead"]),
        )
        assert response.status_code == 200
        no_token = client.post(
            f"/tasks/task-1/assignments/{assignment_id}/revoke",
            json={"reason": "reassigned", "role": "MEDICAL_QA_LEAD"},
        )
    assert no_token.status_code == 401
    assert response.json()["revoked_by"] == "qa-lead"


def test_auth20_revoke_assignment_rejects_a_reviewer_who_did_not_assign(workbench):
    """Authenticated, but not permitted: 403, not 401."""
    assignment_id = _assign_via_api(workbench)
    with _client(workbench) as client:
        response = client.post(
            f"/tasks/task-1/assignments/{assignment_id}/revoke",
            json={"reason": "not my call", "role": "REVIEWER_B"},
            headers=_auth(workbench["tokens"]["reviewer-b"]),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "ASSIGNMENT_REVOCATION_FORBIDDEN"


def test_auth21_revoke_assignment_rejects_a_body_that_contradicts_the_session(workbench):
    assignment_id = _assign_via_api(workbench)
    with _client(workbench) as client:
        response = client.post(
            f"/tasks/task-1/assignments/{assignment_id}/revoke",
            json={"reason": "reassigned", "role": "REVIEWER_B", "actor": "reviewer-b"},
            headers=_auth(workbench["tokens"]["qa-lead"]),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == auth.IDENTITY_MISMATCH


def _assign_via_api(workbench, task_id="task-1"):
    with _client(workbench) as client:
        response = client.post(
            f"/tasks/{task_id}/assign",
            json={"reviewer_id": "reviewer-a", "role": "REVIEWER_A",
                  "assigned_by": "qa-lead"},
            headers=_auth(workbench["tokens"]["qa-lead"]),
        )
    assert response.status_code == 200, response.text
    return response.json()["assignment_id"]


def test_auth20b_an_assignment_cannot_be_revoked_through_another_task_url(workbench):
    """A valid assignment id is not a capability on its own: the task in the
    path has to match the task the assignment belongs to."""
    with ReviewStore(workbench["db"]) as store:
        _add_task(store, task_id="task-2", target_id="regimen-2")
    assignment_id = _assign_via_api(workbench)
    with _client(workbench) as client:
        response = client.post(
            f"/tasks/task-2/assignments/{assignment_id}/revoke",
            json={"reason": "reassigned", "role": "MEDICAL_QA_LEAD"},
            headers=_auth(workbench["tokens"]["qa-lead"]),
        )
    assert response.status_code == 409
    with ReviewStore(workbench["db"]) as store:
        assert all(a.active for a in store.list_assignments("task-1"))


# ── positive: the whole workflow still works, over HTTP, on tokens alone ─────


def test_auth22_an_authenticated_reviewer_can_complete_the_full_workflow(workbench):
    """The property the bug removed was not the workflow — it was that the
    workflow was reachable by anyone. PENDING → … → PHYSICIAN_APPROVED → CLOSED,
    driven entirely by session tokens, with no identity asserted anywhere that
    the server does not verify against the token."""
    tokens = workbench["tokens"]
    with _client(workbench) as client:
        claimed = client.post("/tasks/task-1/claim",
                              json={"role": "REVIEWER_A", "expected_revision": 0},
                              headers=_auth(tokens["reviewer-a"]))
        assert claimed.status_code == 200
        revision = claimed.json()["revision"]

        started = client.post("/tasks/task-1/start",
                              json={"role": "REVIEWER_A", "expected_revision": revision},
                              headers=_auth(tokens["reviewer-a"]))
        assert started.status_code == 200
        revision = started.json()["revision"]

        first = client.post("/tasks/task-1/first-review",
                            json={"role": "REVIEWER_A", "expected_revision": revision,
                                  "decision": "ACCEPT", "target_version": 1,
                                  "reason_codes": ["SOURCE_MATCH"],
                                  "comments": "matches the source wording"},
                            headers=_auth(tokens["reviewer-a"]))
        assert first.status_code == 200
        revision = first.json()["revision"]

        second_claim = client.post("/tasks/task-1/claim",
                                   json={"role": "REVIEWER_B", "expected_revision": revision},
                                   headers=_auth(tokens["reviewer-b"]))
        assert second_claim.status_code == 200
        revision = second_claim.json()["revision"]

        second = client.post("/tasks/task-1/second-review",
                             json={"role": "REVIEWER_B", "expected_revision": revision,
                                   "decision": "ACCEPT", "target_version": 1,
                                   "reason_codes": ["SOURCE_MATCH"],
                                   "comments": "agrees"},
                             headers=_auth(tokens["reviewer-b"]))
        assert second.status_code == 200
        revision = second.json()["revision"]
        assert second.json()["lifecycle_state"] == "MEDICAL_QA_PENDING"

        signed_off = client.post("/tasks/task-1/qa-signoff",
                                 json={"role": "MEDICAL_QA_LEAD", "expected_revision": revision,
                                       "verdict": "APPROVE", "target_version": 1,
                                       "rationale": "pre-approval checklist complete"},
                                 headers=_auth(tokens["qa-lead"]))
        assert signed_off.status_code == 200, signed_off.text
        revision = signed_off.json()["revision"]
        assert signed_off.json()["lifecycle_state"] == "PHYSICIAN_APPROVED"

        closed = client.post("/tasks/task-1/close",
                             json={"role": "MEDICAL_QA_LEAD", "expected_revision": revision},
                             headers=_auth(tokens["qa-lead"]))
        assert closed.status_code == 200
        assert closed.json()["lifecycle_state"] == "CLOSED"
        assert closed.json()["close_outcome"] == "CLOSED_APPROVED"

    with ReviewStore(workbench["db"]) as store:
        task = store.get_task("task-1")
        decisions = store.list_decisions("task-1")
    assert [d.reviewer_id for d in decisions] == ["reviewer-a", "reviewer-b", "qa-lead"]
    assert task.lifecycle_state is ReviewState.CLOSED


def test_auth23_reviewer_b_cannot_reach_physician_approved_while_reviewer_a_holds_the_token(
    workbench,
):
    """The terminal clinical state is a privileged write, not a public one: with
    reviewer-a's token, every path to PHYSICIAN_APPROVED is a 403 or a 409, and
    the task never reaches it."""
    tokens = workbench["tokens"]
    with _client(workbench) as client:
        claimed = client.post("/tasks/task-1/claim",
                              json={"role": "REVIEWER_A", "expected_revision": 0},
                              headers=_auth(tokens["reviewer-a"]))
        revision = claimed.json()["revision"]
        # reviewer-a is not a Medical QA Lead: the registry forbids the role.
        assert client.post("/tasks/task-1/qa-signoff",
                           json={"role": "MEDICAL_QA_LEAD", "expected_revision": revision,
                                 "verdict": "APPROVE", "target_version": 1,
                                 "rationale": "I am Reviewer A"},
                           headers=_auth(tokens["reviewer-a"])).status_code == 403
        # reviewer-a is not an adjudicator either.
        assert client.post("/tasks/task-1/adjudicate",
                           json={"role": "ADJUDICATOR", "expected_revision": revision,
                                 "decision": "ACCEPT", "target_version": 1},
                           headers=_auth(tokens["reviewer-a"])).status_code == 403
        # and no reviewer may close a task that has not been through QA.
        assert client.post("/tasks/task-1/close",
                           json={"role": "MEDICAL_QA_LEAD", "expected_revision": revision},
                           headers=_auth(tokens["reviewer-a"])).status_code == 403
    with ReviewStore(workbench["db"]) as store:
        assert store.get_task("task-1").lifecycle_state is ReviewState.CLAIMED


def test_auth24_a_registered_reviewer_still_cannot_use_their_own_other_role(workbench):
    """Authentication did not weaken the single-role matrix in permissions.py:
    a reviewer who legitimately holds REVIEWER_A cannot reuse that to submit the
    second review."""
    with ReviewerRegistry(workbench["registry_path"]) as registry:
        registry.register(
            reviewer_id="dual", display_name="Synthetic dual", professional_role="physician",
            organisation="Test Clinic",
            authorised_scope=(ReviewRole.REVIEWER_A, ReviewRole.REVIEWER_B),
            registered_at=_now(), registered_by="test-harness",
        )
    dual_token = _session_token(workbench["registry_path"], "dual")
    with _client(workbench) as client:
        response = client.post("/tasks/task-1/second-review",
                               json={"role": "REVIEWER_A", "expected_revision": 0,
                                     "decision": "ACCEPT", "target_version": 1},
                               headers=_auth(dual_token))
    assert response.status_code == 403
    assert response.json()["detail"] == "ROLE_NOT_AUTHORISED"


# ── the owner token is issued once and is not recoverable from disk ──────────


def test_auth25_owner_token_is_displayed_once_and_only_its_digest_is_stored(tmp_path):
    registry_path = tmp_path / "reviewers.sqlite"
    with ReviewerRegistry(registry_path) as registry:
        first = registry.ensure_owner_token()
        assert first and registry.owner_token_state() == "ISSUED"
        # A restart must not invalidate the operator's saved token, so asking
        # again returns None (unknown) rather than regenerating or exploding.
        assert registry.ensure_owner_token() is None
    with ReviewerRegistry(registry_path) as registry:
        # supplying the same token again is accepted, a different one is not
        assert registry.ensure_owner_token(first) == first
        with pytest.raises(Exception) as excinfo:
            registry.ensure_owner_token("some-other-token")
        assert "OWNER_TOKEN_MISMATCH" in str(excinfo.value)
        rows = registry.connection.execute(
            "SELECT token_sha256 FROM reviewer_sessions"
        ).fetchall()
    assert [row["token_sha256"] for row in rows] == [auth.sha256_text(first)]
    assert first not in rows[0]["token_sha256"]


def test_auth26_the_workbench_refuses_to_bind_wider_than_loopback():
    from clinical_engine.review_workbench.api import is_loopback_host

    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert is_loopback_host("::1")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("192.168.1.10")
    assert not is_loopback_host("example.com")
