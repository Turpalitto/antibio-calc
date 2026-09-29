"""Local FastAPI surface. No public deployment and no raw SQLite writes.

Authentication (2026-09-27)
--------------------------
Every state-changing endpoint and every packet-reading endpoint requires a
reviewer session token in the ``X-Review-Token`` header, and the acting identity
is taken from that session — never from the request body. See
:mod:`clinical_engine.review_workbench.auth` for the design and
:class:`~clinical_engine.review_workbench.reviewer_registry.ReviewerRegistry` for
token storage; only the SHA-256 of a token is ever persisted.

Read-only surfaces with no clinical content (``/``, ``/metrics``, ``/issues``,
``/docs`` and the ``/ui`` HTML shells) stay unauthenticated, but the queue
listing — which returns whole task records — is authenticated and blinded per
caller, because a full task record carries Reviewer A's verdict.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import auth
from .models import (
    PriorityBand, QAVerdict, ReviewDecision, ReviewRole, ReviewState, TargetType,
)
from .reviewer_registry import ReviewerRegistrationError, ReviewerRegistry
from .service import InvalidTransition, ReviewerValidationError, ReviewService
from .storage import ConcurrencyError, ReviewStore

# Role assumed for a list projection when the caller names no role. The most
# restrictive one: an unassigned, unquoted viewer is treated as a second reviewer
# and therefore blinded.
_DEFAULT_VIEW_ROLE = ReviewRole.REVIEWER_B


class ActorRequest(BaseModel):
    # `actor` is OPTIONAL and, when present, must equal the authenticated
    # session. It is kept only so an existing client that still sends it gets a
    # clear 403 rather than a silent identity swap.
    actor: str = ""
    role: ReviewRole
    expected_revision: int


class DecisionRequest(ActorRequest):
    decision: ReviewDecision
    target_version: int
    reason_codes: tuple[str, ...] = ()
    comments: str = ""


class NoteRequest(ActorRequest):
    comments: str


class WaiverRequest(ActorRequest):
    reason: str
    expires_at: str


class QASignoffRequest(BaseModel):
    actor: str = ""
    role: ReviewRole
    verdict: QAVerdict
    rationale: str
    expected_revision: int
    target_version: int


class AssignRequest(BaseModel):
    reviewer_id: str
    role: ReviewRole
    # `assigned_by` names the person making the assignment. It must equal the
    # authenticated session; naming a registered stranger is not enough.
    assigned_by: str = ""


class RevokeAssignmentRequest(BaseModel):
    reason: str
    # Optional, and if present must equal the authenticated session.
    actor: str = ""
    # The role the caller claims for the revocation. It is an authorisation
    # claim, not an identity claim: the registry checks it, and the service
    # additionally requires the caller to be the assigner or an ADMINISTRATOR.
    role: ReviewRole


def create_app(database_path: str | Path, registry_path: str | Path = "reviewer_registry.sqlite",
               *, owner_token: str | None = None) -> FastAPI:
    store = ReviewStore(database_path)
    registry = ReviewerRegistry(registry_path)
    service = ReviewService(store, registry)
    # Only the SHA-256 is persisted; the raw value is returned once, here, and
    # only ever handed to the in-process operator (see __main__.py) or a test.
    owner_token_raw = registry.ensure_owner_token(owner_token)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            store.close()
            registry.close()

    app = FastAPI(title="ANTIBIO Clinical Review Workbench", version="5.7", lifespan=lifespan)
    app.state.store = store
    app.state.registry = registry
    app.state.service = service
    app.state.owner_token = owner_token_raw

    def domain_error(_request, error: Exception):
        status = (
            401 if isinstance(error, auth.AuthError)
            else 403 if isinstance(error, (ReviewerValidationError, ReviewerRegistrationError,
                                           auth.IdentityMismatchError))
            else 422 if isinstance(error, ValueError)
            else 409
        )
        detail = getattr(error, "reason_code", str(error))
        return JSONResponse(status_code=status, content={"detail": detail})

    for error_type in (auth.AuthError, auth.IdentityMismatchError, ReviewerValidationError,
                       ReviewerRegistrationError, InvalidTransition, ConcurrencyError, ValueError):
        app.add_exception_handler(error_type, domain_error)

    def session_for(request: Request) -> auth.Session:
        """Every protected route starts here. Raises AuthError (401) — or
        IdentityMismatchError (403) for the owner token — and never returns
        without a proved identity."""
        return auth.require_reviewer_session(request, registry)

    def owner_session_for(request: Request) -> auth.Session:
        session = auth.authenticate(request, registry)
        if not session.is_owner:
            raise auth.AuthError(auth.OWNER_SESSION_REQUIRED)
        return session

    # --- session-token administration (owner-token only) ----------------------

    @app.post("/reviewers/{reviewer_id}/session-token")
    def issue_session_token(reviewer_id: str,
                            session: auth.Session = Depends(owner_session_for)):
        """Mint a reviewer session token. Requires the workbench owner token.

        Returns the raw token exactly once; only its SHA-256 is stored. Re-issuing
        invalidates the previous token for that reviewer.
        """
        return {
            "reviewer_id": reviewer_id,
            "session_token": registry.issue_session_token(reviewer_id),
            "header": auth.TOKEN_HEADER,
            "token_displayed_once": True,
        }

    @app.delete("/reviewers/{reviewer_id}/session-token")
    def revoke_session_token(reviewer_id: str,
                             session: auth.Session = Depends(owner_session_for)):
        registry.revoke_session_token(reviewer_id)
        return {"reviewer_id": reviewer_id, "revoked": True}

    # --- read surfaces -------------------------------------------------------

    @app.get("/queue")
    def queue(request: Request, target_type: TargetType | None = None,
              priority: PriorityBand | None = None, state: ReviewState | None = None,
              safety_axis: str | None = None, role: ReviewRole | None = None,
              limit: int = 100, offset: int = 0,
              session: auth.Session = Depends(session_for)):
        reviewer = auth.resolve_actor(session, request.query_params.get("reviewer_id"))
        view_role = role or _DEFAULT_VIEW_ROLE
        return [service.task_view_for_reviewer(task, reviewer, view_role) for task in service.list_queue(
            target_type=target_type, priority=priority, state=state, safety_axis=safety_axis,
            limit=min(limit, 1000), offset=offset)]

    @app.get("/tasks/{task_id}")
    def task_details(task_id: str, request: Request, reviewer_id: str | None = None,
                     role: ReviewRole | None = None,
                     session: auth.Session = Depends(session_for)):
        """Role-aware, blinded packet (Phase 4).

        The acting reviewer comes from the session token, so ``reviewer_id`` and
        ``role`` are no longer the caller's word for who they are: a
        ``reviewer_id`` that contradicts the session is a 403, and ``role``
        selects the permission branch rather than the identity. Blinding itself
        is decided by ``ReviewService.is_blinded_for``, which reads the task's
        OWN stored reviewer assignments (and the reviewer registry, which
        validates that the quoted role is actually registered) rather than the
        quoted role alone.
        """
        reviewer = auth.resolve_actor(session, reviewer_id)
        try:
            return service.packet_for_reviewer(task_id, reviewer, role or _DEFAULT_VIEW_ROLE)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error

    @app.get("/tasks/{task_id}/export")
    def export_packet(task_id: str, request: Request, reviewer_id: str | None = None,
                      role: ReviewRole | None = None,
                      session: auth.Session = Depends(session_for)):
        reviewer = auth.resolve_actor(session, reviewer_id)
        return service.packet_for_reviewer(task_id, reviewer, role or _DEFAULT_VIEW_ROLE)

    @app.get("/metrics")
    def metrics():
        return service.metrics()

    @app.get("/issues")
    def issues(status: str | None = None, severity: str | None = None,
               limit: int = 100, offset: int = 0):
        return store.list_issues(status=status, severity=severity, limit=min(limit, 1000), offset=offset)

    # --- state-changing endpoints --------------------------------------------

    @app.post("/tasks/{task_id}/assign")
    def assign(task_id: str, request: AssignRequest, session: auth.Session = Depends(session_for)):
        assigner = auth.resolve_actor(session, request.assigned_by)
        assignment = service.assign_reviewer(
            task_id, reviewer_id=request.reviewer_id, role=request.role, assigned_by=assigner,
        )
        return asdict(assignment)

    @app.post("/tasks/{task_id}/claim")
    def claim(task_id: str, request: ActorRequest, session: auth.Session = Depends(session_for)):
        reviewer = auth.resolve_actor(session, request.actor)
        return asdict(service.claim(task_id, reviewer=reviewer, role=request.role,
                                    expected_revision=request.expected_revision))

    @app.post("/tasks/{task_id}/start")
    def start(task_id: str, request: ActorRequest, session: auth.Session = Depends(session_for)):
        reviewer = auth.resolve_actor(session, request.actor)
        return asdict(service.start_review(task_id, reviewer=reviewer, role=request.role,
                                           expected_revision=request.expected_revision))

    @app.post("/tasks/{task_id}/release")
    def release(task_id: str, request: ActorRequest, session: auth.Session = Depends(session_for)):
        reviewer = auth.resolve_actor(session, request.actor)
        return asdict(service.release(task_id, reviewer=reviewer, role=request.role,
                                      expected_revision=request.expected_revision))

    @app.post("/tasks/{task_id}/first-review")
    def first_review(task_id: str, request: DecisionRequest,
                     session: auth.Session = Depends(session_for)):
        reviewer = auth.resolve_actor(session, request.actor)
        return asdict(service.submit_first_review(
            task_id, reviewer=reviewer, role=request.role, decision=request.decision,
            reason_codes=request.reason_codes, comments=request.comments,
            expected_revision=request.expected_revision, target_version=request.target_version))

    @app.post("/tasks/{task_id}/second-review")
    def second_review(task_id: str, request: DecisionRequest,
                      session: auth.Session = Depends(session_for)):
        reviewer = auth.resolve_actor(session, request.actor)
        return asdict(service.submit_second_review(
            task_id, reviewer=reviewer, role=request.role, decision=request.decision,
            reason_codes=request.reason_codes, comments=request.comments,
            expected_revision=request.expected_revision, target_version=request.target_version))

    @app.post("/tasks/{task_id}/adjudicate")
    def adjudicate(task_id: str, request: DecisionRequest, session: auth.Session = Depends(session_for)):
        adjudicator = auth.resolve_actor(session, request.actor)
        return asdict(service.adjudicate(
            task_id, adjudicator=adjudicator, role=request.role, decision=request.decision,
            reason_codes=request.reason_codes, comments=request.comments,
            expected_revision=request.expected_revision, target_version=request.target_version))

    @app.post("/tasks/{task_id}/qa-signoff")
    def qa_signoff(task_id: str, request: QASignoffRequest,
                   session: auth.Session = Depends(session_for)):
        qa_reviewer = auth.resolve_actor(session, request.actor)
        return asdict(service.submit_medical_qa_signoff(
            task_id, medical_qa_reviewer_id=qa_reviewer, role=request.role, verdict=request.verdict,
            rationale=request.rationale, expected_revision=request.expected_revision,
            target_version=request.target_version,
        ))

    @app.post("/tasks/{task_id}/request-adjudication")
    def request_adjudication(task_id: str, request: NoteRequest,
                             session: auth.Session = Depends(session_for)):
        actor = auth.resolve_actor(session, request.actor)
        return asdict(service.request_adjudication(
            task_id, actor=actor, role=request.role, reason=request.comments,
            expected_revision=request.expected_revision,
        ))

    @app.post("/tasks/{task_id}/notes")
    def add_note(task_id: str, request: NoteRequest, session: auth.Session = Depends(session_for)):
        actor = auth.resolve_actor(session, request.actor)
        return asdict(service.add_note(task_id, actor=actor, role=request.role,
                                       comments=request.comments, expected_revision=request.expected_revision))

    @app.post("/tasks/{task_id}/waivers")
    def add_waiver(task_id: str, request: WaiverRequest, session: auth.Session = Depends(session_for)):
        authority = auth.resolve_actor(session, request.actor)
        return asdict(service.add_waiver(
            task_id, authority=authority, role=request.role, reason=request.reason,
            expires_at=request.expires_at, expected_revision=request.expected_revision,
        ))

    @app.post("/tasks/{task_id}/close")
    def close(task_id: str, request: ActorRequest, session: auth.Session = Depends(session_for)):
        actor = auth.resolve_actor(session, request.actor)
        return asdict(service.close(task_id, actor=actor, role=request.role,
                                    expected_revision=request.expected_revision))

    @app.post("/tasks/{task_id}/assignments/{assignment_id}/revoke")
    def revoke_assignment(task_id: str, assignment_id: str, request: RevokeAssignmentRequest,
                          session: auth.Session = Depends(session_for)):
        """Revoke a task-level assignment, under the same session authentication.

        ``ReviewService.revoke_assignment`` requires the caller to be the person
        who made the assignment or a registered ADMINISTRATOR, and audit-logs
        every refusal; the identity it checks is the session's, not the body's.
        """
        actor = auth.resolve_actor(session, request.actor)
        assignment = service.revoke_assignment(
            assignment_id, reason=request.reason, actor=actor, role=request.role,
            expected_task_id=task_id,
        )
        return {"assignment_id": assignment_id, "task_id": assignment.task_id,
                "revoked_by": actor, "reason": request.reason}

    # --- unauthenticated, no clinical content --------------------------------

    @app.get("/")
    def dashboard():
        metrics = service.metrics()
        return {
            "name": "ANTIBIO Clinical Review Workbench",
            "mode": "LOCAL_REVIEW_ONLY",
            "clinical_engine_connected": False,
            "authentication": {
                "header": auth.TOKEN_HEADER,
                "loopback_only": True,
            },
            "metrics": metrics,
            "views": ["dashboard", "queue", "task details", "source/provenance", "comparison",
                      "first review", "second review", "adjudication", "medical QA sign-off",
                      "issue registry", "corpus review"],
        }

    @app.get("/ui", response_class=HTMLResponse)
    def ui_dashboard():
        return """<!doctype html><html><head><meta charset='utf-8'><title>ANTIBIO Review</title>
<style>body{font:16px system-ui;max-width:1200px;margin:2rem auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.4rem}button,input,select,textarea{margin:.2rem;padding:.4rem}</style></head>
<body><h1>ANTIBIO Clinical Review Workbench</h1><p>LOCAL_REVIEW_ONLY · Clinical Engine disconnected</p>
<p>Every clinical endpoint requires a reviewer session token in the <code>X-Review-Token</code> header. Paste the token minted for you by the workbench owner; it is kept in this tab's sessionStorage only.</p>
<label>Session token <input id='token' type='password' size='60' placeholder='reviewer session token'></label>
<button onclick='saveToken()'>Use token</button><button onclick='clearToken()'>Forget token</button><span id='tokstate'></span>
<nav><a href='/ui'>Dashboard</a> · <a href='/ui/metrics'>Metrics</a> · <a href='/ui/issues'>Issue registry</a> · <a href='/ui/corpus'>Corpus review</a> · <a href='/docs'>Governed API</a></nav>
<pre id='metrics'>Loading metrics…</pre><h2>Queue</h2><label>Type <input id='type'></label>
<label>Status <input id='state' value='PENDING'></label><button onclick='loadQueue()'>Filter</button>
<table><thead><tr><th>Priority</th><th>Type</th><th>Issue</th><th>Task</th></tr></thead><tbody id='queue'></tbody></table>
<script>
const TOKEN_KEY='antibio.review.token';
function saveToken(){sessionStorage.setItem(TOKEN_KEY,document.getElementById('token').value);tokstate.textContent='token stored for this tab';}
function clearToken(){sessionStorage.removeItem(TOKEN_KEY);document.getElementById('token').value='';tokstate.textContent='token cleared';}
function authHeaders(h){const t=sessionStorage.getItem(TOKEN_KEY);const out=Object.assign({},h||{});if(t)out['X-Review-Token']=t;return out;}
function describe(r){return r.status+' '+(r.status===401?'— session token missing or invalid':(r.status===403?'— not permitted for this identity':''));}
async function loadQueue(){const t=document.getElementById('type').value,s=document.getElementById('state').value;
 const q=new URLSearchParams({limit:'200'});if(t)q.set('target_type',t);if(s)q.set('state',s);
 const r=await fetch('/queue?'+q,{headers:authHeaders()});
 if(!r.ok){queue.innerHTML='<tr><td colspan="4">'+describe(r)+'</td></tr>';return;}
 const data=await r.json();queue.innerHTML=data.map(x=>`<tr><td>${x.priority_score} ${x.priority}</td><td>${x.target_type}</td><td>${x.issue_type}</td><td><a href='/ui/tasks/${x.task_id}'>${x.task_id}</a></td></tr>`).join('');}
 fetch('/metrics').then(r=>r.json()).then(x=>metrics.textContent=JSON.stringify(x,null,2));loadQueue();
</script></body></html>"""

    @app.get("/ui/tasks/{task_id}", response_class=HTMLResponse)
    def ui_task(task_id: str):
        safe_id = task_id.replace("'", "").replace('"', "")
        return f"""<!doctype html><html><head><meta charset='utf-8'><title>Review {safe_id}</title>
<style>body{{font:15px system-ui;max-width:1200px;margin:2rem auto}}pre{{white-space:pre-wrap;border:1px solid #ccc;padding:1rem}}input,select,textarea,button{{display:block;margin:.4rem 0;padding:.4rem;width:100%}}</style></head>
<body><a href='/ui'>← Queue</a><h1>Task {safe_id}</h1>
<label>Session token <input id='token' type='password' placeholder='reviewer session token'></label><button onclick='saveToken()'>Use token</button>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:1rem'><section><h2>Normalized object</h2><pre id='normalized'>Loading…</pre></section><section><h2>Source and provenance</h2><pre id='provenance'>Loading…</pre></section></div><h2>Complete immutable packet</h2><pre id='packet'></pre>
<h2>Governed action</h2><p>Your identity is the token, not this form. The field below only has to agree with it.</p>
<input id='actor' placeholder='Registered reviewer_id (must match token)'><select id='role'><option>REVIEWER_A</option><option>REVIEWER_B</option><option>ADJUDICATOR</option><option>MEDICAL_QA_LEAD</option></select>
<select id='decision'><option>ACCEPT</option><option>ACCEPT_WITH_NOTE</option><option>REJECT_FIDELITY</option><option>REJECT_CLINICAL</option><option>NEEDS_INFO</option><option>ABSTAIN</option></select>
<textarea id='comments' placeholder='Comments'></textarea><button onclick='claim()'>Claim</button><button onclick='first()'>Submit first review</button><button onclick='second()'>Submit second review</button><button onclick='adjudicate()'>Adjudicate</button><pre id='result'></pre>
<script>
const TOKEN_KEY='antibio.review.token';
function saveToken(){{sessionStorage.setItem(TOKEN_KEY,document.getElementById('token').value);load();}}
function authHeaders(h){{const t=sessionStorage.getItem(TOKEN_KEY);const out=Object.assign({{}},h||{{}});if(t)out['X-Review-Token']=t;return out;}}
function describe(r){{return r.status+' '+(r.status===401?'— session token missing or invalid':(r.status===403?'— identity or role not permitted':''));}}
async function load(){{document.getElementById('token').value=sessionStorage.getItem(TOKEN_KEY)||'';const q=new URLSearchParams({{role:role.value}});if(actor.value)q.set('reviewer_id',actor.value);
 const r=await fetch('/tasks/{safe_id}?'+q,{{headers:authHeaders()}});if(!r.ok){{result.textContent=describe(r);return;}}
 const p=await r.json();task=p.task;normalized.textContent=JSON.stringify(p.normalized_object,null,2);provenance.textContent=JSON.stringify({{source_references:p.source_references,field_level_provenance:p.field_level_provenance,original_source_wording:p.original_source_wording}},null,2);packet.textContent=JSON.stringify(p,null,2);if(task&&task.assigned_reviewer)actor.value=task.assigned_reviewer}}
function base(){{return {{actor:actor.value,role:role.value,expected_revision:task.revision}}}}function dec(){{return {{...base(),decision:decision.value,target_version:task.target_version,reason_codes:[],comments:comments.value}}}}
async function call(path,body){{const r=await fetch(path,{{method:'POST',headers:authHeaders({{'Content-Type':'application/json'}}),body:JSON.stringify(body)}});result.textContent=r.ok?await r.text():describe(r);await load()}}
function claim(){{call('/tasks/{safe_id}/claim',base())}}function first(){{call('/tasks/{safe_id}/first-review',dec())}}function second(){{call('/tasks/{safe_id}/second-review',dec())}}function adjudicate(){{call('/tasks/{safe_id}/adjudicate',dec())}}load();</script></body></html>"""

    @app.get("/ui/metrics", response_class=HTMLResponse)
    def ui_metrics():
        return """<!doctype html><meta charset='utf-8'><title>Review metrics</title><body><a href='/ui'>← Dashboard</a><h1>Review metrics</h1><pre id='data'>Loading…</pre><script>fetch('/metrics').then(r=>r.json()).then(x=>data.textContent=JSON.stringify(x,null,2))</script></body>"""

    @app.get("/ui/issues", response_class=HTMLResponse)
    def ui_issues():
        return """<!doctype html><meta charset='utf-8'><title>Issue registry</title><body><a href='/ui'>← Dashboard</a><h1>Clinical data issue registry</h1><label>Severity <input id='severity'></label><button onclick='load()'>Filter</button><pre id='data'>Loading…</pre><script>function load(){const q=new URLSearchParams({limit:'200'});if(severity.value)q.set('severity',severity.value);fetch('/issues?'+q).then(r=>r.json()).then(x=>data.textContent=JSON.stringify(x,null,2))}load()</script></body>"""

    @app.get("/ui/corpus", response_class=HTMLResponse)
    def ui_corpus():
        return """<!doctype html><meta charset='utf-8'><title>Corpus review</title><body><a href='/ui'>← Dashboard</a><h1>Corpus exclusion review</h1><pre id='data'>Loading…</pre><script>const TOKEN_KEY='antibio.review.token';function authHeaders(h){const t=sessionStorage.getItem(TOKEN_KEY);const out=Object.assign({},h||{});if(t)out['X-Review-Token']=t;return out;}async function load(){const r=await fetch('/queue?target_type=CorpusExclusionDecision&limit=1000',{headers:authHeaders()});if(!r.ok){data.textContent=r.status+(r.status===401?' — session token missing or invalid':' — not permitted');return;}const x=await r.json();data.textContent=JSON.stringify(x,null,2)}load()</script></body>"""

    return app


def run_server(database_path: str | Path, registry_path: str | Path = "reviewer_registry.sqlite",
               *, host: str = "127.0.0.1", port: int = 8099, owner_token: str | None = None) -> None:
    """Serve the workbench. Loopback is the DEFAULT and the only sensible bind.

    The workbench drives clinical approval decisions; it must never be reachable
    from another host. The request-level checks in :mod:`.auth` reject a
    non-loopback peer, ``Host`` or ``Origin`` even if this is bound wider, but
    binding wide is a configuration error and is not what this function does.
    """
    import uvicorn  # optional dependency, only needed to actually serve

    app = create_app(database_path, registry_path=registry_path, owner_token=owner_token)
    if not is_loopback_host(host):
        raise ValueError(
            f"refusing to bind the clinical review workbench to non-loopback host {host!r}; "
            "the workbench is loopback-only"
        )
    if app.state.owner_token:
        print("ANTIBIO Review Workbench owner token (shown once, store it now):\n"
              f"{app.state.owner_token}")
    else:
        print("ANTIBIO Review Workbench: an owner token was already issued for this registry and "
              "only its SHA-256 was stored, so it cannot be shown again. Pass --owner-token to use "
              "the token you saved.")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def is_loopback_host(value: str) -> bool:
    """Bind-time half of the check in :func:`auth.is_loopback_request`."""
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        return False
    if value == "::1":
        return True
    try:
        parsed = urlsplit(f"//{value}")
    except ValueError:
        return False
    if parsed.username or parsed.password or parsed.path not in ("",):
        return False
    return (parsed.hostname or "").lower().rstrip(".") in {"localhost", "127.0.0.1", "::1"}



__all__ = ["create_app", "is_loopback_host", "run_server"]
