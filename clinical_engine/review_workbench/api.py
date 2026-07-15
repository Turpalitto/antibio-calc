"""Local FastAPI surface. No public deployment and no raw SQLite writes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .models import PriorityBand, QAVerdict, ReviewDecision, ReviewRole, ReviewState, TargetType
from .reviewer_registry import ReviewerRegistrationError, ReviewerRegistry
from .service import InvalidTransition, ReviewerValidationError, ReviewService
from .storage import ConcurrencyError, ReviewStore


class ActorRequest(BaseModel):
    actor: str
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
    actor: str
    role: ReviewRole
    verdict: QAVerdict
    rationale: str
    expected_revision: int
    target_version: int


class AssignRequest(BaseModel):
    reviewer_id: str
    role: ReviewRole
    assigned_by: str


def create_app(database_path: str | Path, registry_path: str | Path = "reviewer_registry.sqlite") -> FastAPI:
    store = ReviewStore(database_path)
    registry = ReviewerRegistry(registry_path)
    service = ReviewService(store, registry)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            store.close()
            registry.close()

    app = FastAPI(title="ANTIBIO Clinical Review Workbench", version="5.6", lifespan=lifespan)

    def domain_error(_request, error: Exception):
        status = (
            403 if isinstance(error, (ReviewerValidationError, ReviewerRegistrationError))
            else 422 if isinstance(error, ValueError)
            else 409
        )
        detail = getattr(error, "reason_code", str(error))
        return JSONResponse(status_code=status, content={"detail": detail})

    for error_type in (ReviewerValidationError, ReviewerRegistrationError, InvalidTransition,
                       ConcurrencyError, ValueError):
        app.add_exception_handler(error_type, domain_error)

    @app.get("/queue")
    def queue(target_type: TargetType | None = None, priority: PriorityBand | None = None,
              state: ReviewState | None = None, safety_axis: str | None = None,
              limit: int = 100, offset: int = 0):
        return [asdict(task) for task in service.list_queue(
            target_type=target_type, priority=priority, state=state, safety_axis=safety_axis,
            limit=min(limit, 1000), offset=offset)]

    @app.get("/tasks/{task_id}")
    def task_details(task_id: str, reviewer_id: str, role: ReviewRole):
        """Role-aware, blinded packet (Phase 4) — reviewer_id/role are required
        query params so the response can never accidentally leak the other
        reviewer's verdict via an unauthenticated call."""
        try:
            return service.packet_for_reviewer(task_id, reviewer_id, role)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error

    @app.post("/tasks/{task_id}/assign")
    def assign(task_id: str, request: AssignRequest):
        assignment = service.assign_reviewer(
            task_id, reviewer_id=request.reviewer_id, role=request.role, assigned_by=request.assigned_by,
        )
        return asdict(assignment)

    @app.post("/tasks/{task_id}/claim")
    def claim(task_id: str, request: ActorRequest):
        return asdict(service.claim(task_id, reviewer=request.actor, role=request.role,
                                    expected_revision=request.expected_revision))

    @app.post("/tasks/{task_id}/start")
    def start(task_id: str, request: ActorRequest):
        return asdict(service.start_review(task_id, reviewer=request.actor, role=request.role,
                                           expected_revision=request.expected_revision))

    @app.post("/tasks/{task_id}/release")
    def release(task_id: str, request: ActorRequest):
        return asdict(service.release(task_id, reviewer=request.actor, role=request.role,
                                      expected_revision=request.expected_revision))

    @app.post("/tasks/{task_id}/first-review")
    def first_review(task_id: str, request: DecisionRequest):
        return asdict(service.submit_first_review(
            task_id, reviewer=request.actor, role=request.role, decision=request.decision,
            reason_codes=request.reason_codes, comments=request.comments,
            expected_revision=request.expected_revision, target_version=request.target_version))

    @app.post("/tasks/{task_id}/second-review")
    def second_review(task_id: str, request: DecisionRequest):
        return asdict(service.submit_second_review(
            task_id, reviewer=request.actor, role=request.role, decision=request.decision,
            reason_codes=request.reason_codes, comments=request.comments,
            expected_revision=request.expected_revision, target_version=request.target_version))

    @app.post("/tasks/{task_id}/adjudicate")
    def adjudicate(task_id: str, request: DecisionRequest):
        return asdict(service.adjudicate(
            task_id, adjudicator=request.actor, role=request.role, decision=request.decision,
            reason_codes=request.reason_codes, comments=request.comments,
            expected_revision=request.expected_revision, target_version=request.target_version))

    @app.post("/tasks/{task_id}/qa-signoff")
    def qa_signoff(task_id: str, request: QASignoffRequest):
        return asdict(service.submit_medical_qa_signoff(
            task_id, medical_qa_reviewer_id=request.actor, role=request.role, verdict=request.verdict,
            rationale=request.rationale, expected_revision=request.expected_revision,
            target_version=request.target_version,
        ))

    @app.post("/tasks/{task_id}/request-adjudication")
    def request_adjudication(task_id: str, request: NoteRequest):
        return asdict(service.request_adjudication(
            task_id, actor=request.actor, role=request.role, reason=request.comments,
            expected_revision=request.expected_revision,
        ))

    @app.post("/tasks/{task_id}/notes")
    def add_note(task_id: str, request: NoteRequest):
        return asdict(service.add_note(task_id, actor=request.actor, role=request.role,
                                       comments=request.comments, expected_revision=request.expected_revision))

    @app.post("/tasks/{task_id}/waivers")
    def add_waiver(task_id: str, request: WaiverRequest):
        return asdict(service.add_waiver(
            task_id, authority=request.actor, role=request.role, reason=request.reason,
            expires_at=request.expires_at, expected_revision=request.expected_revision,
        ))

    @app.post("/tasks/{task_id}/close")
    def close(task_id: str, request: ActorRequest):
        return asdict(service.close(task_id, actor=request.actor, role=request.role,
                                    expected_revision=request.expected_revision))

    @app.get("/tasks/{task_id}/export")
    def export_packet(task_id: str, reviewer_id: str, role: ReviewRole):
        return service.packet_for_reviewer(task_id, reviewer_id, role)

    @app.get("/metrics")
    def metrics():
        return service.metrics()

    @app.get("/issues")
    def issues(status: str | None = None, severity: str | None = None,
               limit: int = 100, offset: int = 0):
        return store.list_issues(status=status, severity=severity, limit=min(limit, 1000), offset=offset)

    @app.get("/")
    def dashboard():
        metrics = service.metrics()
        return {
            "name": "ANTIBIO Clinical Review Workbench",
            "mode": "LOCAL_REVIEW_ONLY",
            "clinical_engine_connected": False,
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
<nav><a href='/ui'>Dashboard</a> · <a href='/ui/metrics'>Metrics</a> · <a href='/ui/issues'>Issue registry</a> · <a href='/ui/corpus'>Corpus review</a> · <a href='/docs'>Governed API</a></nav>
<pre id='metrics'>Loading metrics…</pre><h2>Queue</h2><label>Type <input id='type'></label>
<label>Status <input id='state' value='PENDING'></label><button onclick='loadQueue()'>Filter</button>
<table><thead><tr><th>Priority</th><th>Type</th><th>Issue</th><th>Task</th></tr></thead><tbody id='queue'></tbody></table>
<script>
async function loadQueue(){const t=document.getElementById('type').value,s=document.getElementById('state').value;
 const q=new URLSearchParams({limit:'200'});if(t)q.set('target_type',t);if(s)q.set('state',s);
 const data=await fetch('/queue?'+q).then(r=>r.json());document.getElementById('queue').innerHTML=data.map(x=>`<tr><td>${x.priority_score} ${x.priority}</td><td>${x.target_type}</td><td>${x.issue_type}</td><td><a href='/ui/tasks/${x.task_id}'>${x.task_id}</a></td></tr>`).join('');}
fetch('/metrics').then(r=>r.json()).then(x=>metrics.textContent=JSON.stringify(x,null,2));loadQueue();
</script></body></html>"""

    @app.get("/ui/tasks/{task_id}", response_class=HTMLResponse)
    def ui_task(task_id: str):
        safe_id = task_id.replace("'", "").replace('"', "")
        return f"""<!doctype html><html><head><meta charset='utf-8'><title>Review {safe_id}</title>
<style>body{{font:15px system-ui;max-width:1200px;margin:2rem auto}}pre{{white-space:pre-wrap;border:1px solid #ccc;padding:1rem}}input,select,textarea,button{{display:block;margin:.4rem 0;padding:.4rem;width:100%}}</style></head>
<body><a href='/ui'>← Queue</a><h1>Task {safe_id}</h1>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:1rem'><section><h2>Normalized object</h2><pre id='normalized'>Loading…</pre></section><section><h2>Source and provenance</h2><pre id='provenance'>Loading…</pre></section></div><h2>Complete immutable packet</h2><pre id='packet'></pre>
<h2>Governed action</h2><input id='actor' placeholder='Registered reviewer_id'><select id='role'><option>REVIEWER_A</option><option>REVIEWER_B</option><option>ADJUDICATOR</option><option>MEDICAL_QA_LEAD</option></select>
<select id='decision'><option>ACCEPT</option><option>ACCEPT_WITH_NOTE</option><option>REJECT_FIDELITY</option><option>REJECT_CLINICAL</option><option>NEEDS_INFO</option><option>ABSTAIN</option></select>
<textarea id='comments' placeholder='Comments'></textarea><button onclick='claim()'>Claim</button><button onclick='first()'>Submit first review</button><button onclick='second()'>Submit second review</button><button onclick='adjudicate()'>Adjudicate</button><pre id='result'></pre>
<script>let task;async function load(){{const q=new URLSearchParams({{reviewer_id:actor.value||'unassigned',role:role.value}});const p=await fetch('/tasks/{safe_id}?'+q).then(r=>r.json());task=p.task;normalized.textContent=JSON.stringify(p.normalized_object,null,2);provenance.textContent=JSON.stringify({{source_references:p.source_references,field_level_provenance:p.field_level_provenance,original_source_wording:p.original_source_wording}},null,2);packet.textContent=JSON.stringify(p,null,2)}}
function base(){{return {{actor:actor.value,role:role.value,expected_revision:task.revision}}}}function dec(){{return {{...base(),decision:decision.value,target_version:task.target_version,reason_codes:[],comments:comments.value}}}}
async function call(path,body){{const r=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});result.textContent=await r.text();await load()}}
function claim(){{call('/tasks/{safe_id}/claim',base())}}function first(){{call('/tasks/{safe_id}/first-review',dec())}}function second(){{call('/tasks/{safe_id}/second-review',dec())}}function adjudicate(){{call('/tasks/{safe_id}/adjudicate',dec())}}load();</script></body></html>"""

    @app.get("/ui/metrics", response_class=HTMLResponse)
    def ui_metrics():
        return """<!doctype html><meta charset='utf-8'><title>Review metrics</title><body><a href='/ui'>← Dashboard</a><h1>Review metrics</h1><pre id='data'>Loading…</pre><script>fetch('/metrics').then(r=>r.json()).then(x=>data.textContent=JSON.stringify(x,null,2))</script></body>"""

    @app.get("/ui/issues", response_class=HTMLResponse)
    def ui_issues():
        return """<!doctype html><meta charset='utf-8'><title>Issue registry</title><body><a href='/ui'>← Dashboard</a><h1>Clinical data issue registry</h1><label>Severity <input id='severity'></label><button onclick='load()'>Filter</button><pre id='data'>Loading…</pre><script>function load(){const q=new URLSearchParams({limit:'200'});if(severity.value)q.set('severity',severity.value);fetch('/issues?'+q).then(r=>r.json()).then(x=>data.textContent=JSON.stringify(x,null,2))}load()</script></body>"""

    @app.get("/ui/corpus", response_class=HTMLResponse)
    def ui_corpus():
        return """<!doctype html><meta charset='utf-8'><title>Corpus review</title><body><a href='/ui'>← Dashboard</a><h1>Corpus exclusion review</h1><pre id='data'>Loading…</pre><script>fetch('/queue?target_type=CorpusExclusionDecision&limit=1000').then(r=>r.json()).then(x=>data.textContent=JSON.stringify(x,null,2))</script></body>"""

    return app
