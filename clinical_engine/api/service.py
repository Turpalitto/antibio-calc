"""Framework-agnostic API handlers (INT-5a).

Each handler returns ``(http_status:int, body:dict)`` so it is testable with no
running server and no web framework. The FastAPI binding (app.py) is a thin
adapter over these.

INT-5a implements: health, version, and a reserved /v1/recommend stub (501,
NOT_IMPLEMENTED) — the recommendation logic lands in INT-5b. No clinical logic,
upstream corpus is only probed read-only for availability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clinical_engine.api import contract
from clinical_engine.corpus.locator import CorpusLocator

_DEFAULT_KNOWLEDGE = "clinical_engine/resources/curated_knowledge.json"


@dataclass(frozen=True)
class ApiContext:
    """Injected dependencies.

    INT-5b-1: ``recommender`` is an object exposing ``recommend(query) -> result``
    (a ``CuratedEngine`` in production, a fake in tests). It is injected so API
    behaviour can be validated without building a real Engine over the upstream
    corpus (which must stay read-only). When ``None``, the recommend endpoint
    returns an explicit review-required state — never a silent recommendation.
    """
    corpus: CorpusLocator
    curated_knowledge_path: str = _DEFAULT_KNOWLEDGE
    recommender: Any | None = None

    @classmethod
    def default(cls) -> "ApiContext":
        return cls(corpus=CorpusLocator())


def _knowledge_meta(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"present": False, "status": None, "knowledge_version": None}
    try:
        meta = json.loads(p.read_text(encoding="utf-8")).get("meta", {})
    except Exception:
        return {"present": True, "status": "UNREADABLE", "knowledge_version": None}
    return {
        "present": True,
        "status": meta.get("status"),
        "knowledge_version": meta.get("guideline_set_version") or meta.get("generated_at"),
        "counts": meta.get("counts"),
    }


def handle_version(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    km = _knowledge_meta(ctx.curated_knowledge_path)
    return 200, {
        "api_version": contract.API_VERSION,
        "supported_api_versions": list(contract.SUPPORTED_API_VERSIONS),
        "knowledge_version": km["knowledge_version"],
        "error_categories": {k: list(v) for k, v in contract.ERROR_CATEGORIES.items()},
    }


def handle_health(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Report readiness. Corpus is probed read-only (existence checks only).
    Never opens or writes anything."""
    st = ctx.corpus.status()
    km = _knowledge_meta(ctx.curated_knowledge_path)
    corpus_ok = st.available
    # The API can answer only if the corpus is reachable (content is read live).
    ready = corpus_ok
    body = {
        "api_version": contract.API_VERSION,
        "status": "ok" if ready else "degraded",
        "ready": ready,
        "corpus": {
            "available": corpus_ok,
            "root": str(st.root),
            "normalized_regimens": st.normalized_regimens_exists,
            "metadata": st.metadata_exists,
            "pdf_dirs_present": list(st.pdf_dirs_present),
        },
        "curated_knowledge": km,
    }
    # Health itself always returns 200 (it *is* the readiness report); the
    # 'ready'/'status' fields carry the degraded signal. 503 is reserved for the
    # recommend endpoint refusing to answer when the corpus is unavailable.
    return 200, body


def _to_query(req: "contract.RecommendRequest"):
    """Build the engine's PatientQuery from the validated request DTO."""
    from clinical_engine.models import Patient, PatientQuery, Preferences
    p = req.patient
    patient = Patient(
        age=p.age, weight_kg=p.weight_kg, pregnant=p.pregnant,
        renal_function=p.renal_function, hepatic_impairment=p.hepatic_impairment,
        allergies=tuple(p.allergies), current_meds=tuple(p.current_meds),
    )
    prefs = Preferences(
        therapy_line=req.preferences.therapy_line,
        route_preference=req.preferences.route_preference,
        population=req.preferences.population,
    )
    return PatientQuery(diagnosis=req.diagnosis, icd10=req.icd10,
                        patient=patient, preferences=prefs)


def _review_from_notes(result: Any) -> dict[str, str] | None:
    """Extract an explicit REVIEW_REQUIRED signal from the CuratedEngine notes.
    Note message is 'INNER_CODE: reason' (see CuratedEngine)."""
    for n in getattr(result, "engine_notes", ()) or ():
        if getattr(n, "code", None) == "REVIEW_REQUIRED":
            msg = getattr(n, "message", "") or ""
            inner, _, reason = msg.partition(": ")
            return {"code": inner or "NO_APPROVED_DIAGNOSIS", "reason": reason or msg}
    return None


def _minimal_recommendations(result: Any) -> list[dict[str, Any]]:
    """INT-5b-1: envelope only — identifiers, NO clinical fields yet (that is 5b-2)."""
    out = []
    for i, rec in enumerate(getattr(result, "accepted", ()) or (), start=1):
        c = getattr(rec, "candidate", None)
        out.append({
            "rank": i,
            "regimen_id": getattr(c, "regimen_id", None),
            "guideline_id": getattr(c, "guideline_id", None),
            "therapy_line": getattr(c, "therapy_line", None),
        })
    return out


def handle_recommend(ctx: ApiContext, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """INT-5b-1: connect CuratedEngine and return the complete envelope.

    Full clinical serialization (dose/route/duration/alternatives/contraindications)
    is INT-5b-2 — here recommendations carry identifiers only.
    """
    # 1. request contract
    try:
        req = contract.parse_recommend_request(body)
    except contract.RequestError as exc:
        code = 400 if exc.code in ("INVALID_REQUEST", "UNSUPPORTED_API_VERSION") else 422
        return code, contract.error_response(exc.code, exc.detail)

    km = _knowledge_meta(ctx.curated_knowledge_path)
    kv = km.get("knowledge_version")

    # 2. corpus must be reachable (content is read live) — else refuse, never degrade.
    if not ctx.corpus.available():
        return 503, contract.envelope(contract.Status.ERROR, knowledge_version=kv,
                                      errors=[contract.error_obj(
                                          "CORPUS_UNAVAILABLE",
                                          f"corpus not available at {ctx.corpus.root}")])

    # 3. recommender must be wired — else explicit review-required (never silent).
    if ctx.recommender is None:
        return 200, contract.envelope(
            contract.Status.REVIEW_REQUIRED, knowledge_version=kv,
            review={"code": "KNOWLEDGE_UNAVAILABLE",
                    "reason": "curated recommender not configured"},
            recommendations=[])

    # 4. run curated recommendation
    result = ctx.recommender.recommend(_to_query(req))

    review = _review_from_notes(result)
    if review is not None:
        return 200, contract.envelope(contract.Status.REVIEW_REQUIRED, knowledge_version=kv,
                                      review=review, recommendations=[])

    recs = _minimal_recommendations(result)
    if not recs:
        # curated engine yielded neither approval nor an explicit review note
        return 200, contract.envelope(
            contract.Status.REVIEW_REQUIRED, knowledge_version=kv,
            review={"code": "NO_APPROVED_REGIMEN",
                    "reason": "no physician-approved recommendation for this query"},
            recommendations=[])

    return 200, contract.envelope(contract.Status.APPROVED, knowledge_version=kv,
                                  recommendations=recs)
