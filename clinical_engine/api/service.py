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

from clinical_engine.api import contract, v2_contract
from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.models import SAFETY_ACTION_SEVERITY

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
    # PERSONAL_PHYSICIAN_MODE_RFC: separate additive service. Never reused by
    # v1 and never interpreted as production physician approval.
    personal_service: Any | None = None

    @classmethod
    def default(cls) -> "ApiContext":
        # Additive local facade. It stays fail-closed until an owner profile
        # and an explicitly activated immutable bundle exist.
        from clinical_engine.personal.runtime import PersonalRuntime

        return cls(corpus=CorpusLocator(), personal_service=PersonalRuntime())


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


def _flag_obj(flag: Any) -> dict[str, Any]:
    """Serialize one SafetyFlag. H-4: the engine raised it; the transport
    dropped it, so a pregnancy contraindication was indistinguishable from a
    clean recommendation."""
    return {
        "code": getattr(flag, "code", None),
        "level": _enum_value(getattr(flag, "level", None)),
        "message": getattr(flag, "message", None),
        "drug_ref": getattr(flag, "drug_ref", None),
        "stage": getattr(flag, "stage", None),
        "action": _enum_value(getattr(flag, "action", None)),
        "requires_physician_acknowledgement": bool(
            getattr(flag, "requires_physician_acknowledgement", False)),
    }


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _minimal_recommendations(result: Any) -> list[dict[str, Any]]:
    """INT-5b-1: envelope only — identifiers, NO clinical dose fields yet (5b-2).

    H-4: safety fields are NOT part of that 5b-2 deferral. A recommendation
    that carries a contraindication, an unapplied dose adjustment or a
    non-patient-specific dose must say so at the transport layer too, so the
    fields below are emitted unconditionally whenever the engine supplied them.
    """
    out = []
    for i, rec in enumerate(getattr(result, "accepted", ()) or (), start=1):
        c = getattr(rec, "candidate", None)
        item: dict[str, Any] = {
            "rank": i,
            "regimen_id": getattr(c, "regimen_id", None),
            "guideline_id": getattr(c, "guideline_id", None),
            "therapy_line": getattr(c, "therapy_line", None),
        }
        flags = [_flag_obj(f) for f in (getattr(rec, "safety_flags", ()) or ())]
        if flags:
            item["safety_flags"] = flags
            item["requires_physician_acknowledgement"] = any(
                f["requires_physician_acknowledgement"] for f in flags)
            item["most_severe_action"] = _worst_action(
                [f["action"] for f in flags])
        dose = getattr(rec, "dose", None)
        if dose is not None and hasattr(dose, "dose_is_patient_specific"):
            item["dose_is_patient_specific"] = bool(dose.dose_is_patient_specific)
        sev = getattr(rec, "interaction_severity", None)
        if sev is not None:
            item["interaction_severity"] = _enum_value(sev)
        out.append(item)
    return out


# Ordered most severe first (models.SAFETY_ACTION_SEVERITY). `_worst_action`
# reuses that single source of truth rather than restating the ordering — a
# second table is how the transport and the engine drift apart.
def _worst_action(actions: list[str]) -> str | None:
    for action in SAFETY_ACTION_SEVERITY:
        if action.value in actions:
            return action.value
    return next((a for a in actions if a), None)


def _safety_summary(result: Any) -> dict[str, Any] | None:
    """Pass the engine's own SafetySummary through verbatim.

    H-4: the engine computes it (models.SafetySummary.from_result) and the
    transport must NOT recompute or drop it — recomputation is how the two
    paths drifted apart in the first place.
    """
    s = getattr(result, "safety_summary", None)
    if s is None:
        return None
    return {
        "status": getattr(s, "status", None),
        "requires_physician_review": bool(getattr(s, "requires_physician_review", False)),
        "total_flags": int(getattr(s, "total_flags", 0) or 0),
        "flag_counts": dict(getattr(s, "flag_counts", {}) or {}),
        "flag_codes": list(getattr(s, "flag_codes", ()) or ()),
        "most_severe_action": _enum_value(getattr(s, "most_severe_action", None)),
        "actions": [_enum_value(a) for a in (getattr(s, "actions", ()) or ())],
        "requires_physician_acknowledgement": int(
            getattr(s, "requires_physician_acknowledgement", 0) or 0),
        "absolute_contraindications": int(
            getattr(s, "absolute_contraindications", 0) or 0),
        "dose_is_patient_specific": bool(getattr(s, "dose_is_patient_specific", True)),
    }


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

    # H-4: the engine's own safety verdict is authoritative. Stamping APPROVED
    # over a set the engine marked REVIEW_REQUIRED is exactly the bug.
    summary = _safety_summary(result)
    status = contract.Status.APPROVED
    notes: list[dict[str, Any]] = []
    if summary is not None and summary.get("requires_physician_review"):
        status = contract.Status.REVIEW_REQUIRED
        notes.append(contract.error_obj(
            "CLINICAL_REVIEW_REQUIRED",
            "engine raised safety flags on the returned set: "
            + ", ".join(summary.get("flag_codes") or []) or "unspecified"))

    return 200, contract.envelope(
        status, knowledge_version=kv, notes=notes,
        safety_summary=summary,
        recommendations=recs)


def handle_recommend_v2(
    ctx: ApiContext,
    body: dict[str, Any],
    *,
    host: str,
    origin: str = "",
) -> tuple[int, dict[str, Any]]:
    """Fail-closed local personal-physician API.

    This path is deliberately separate from :func:`handle_recommend`: API v1
    and its production approval vocabulary remain frozen.
    """
    try:
        request = v2_contract.parse_recommend_request(body)
    except v2_contract.RequestError as exc:
        return 400, v2_contract.blocked(exc.code, exc.detail, status=v2_contract.Status.ERROR)

    if ctx.personal_service is None:
        return 200, v2_contract.blocked(
            "PERSONAL_MODE_NOT_CONFIGURED",
            "owner-reviewed personal service is not configured",
            status=v2_contract.Status.REVIEW_REQUIRED,
        )

    try:
        raw = ctx.personal_service.recommend(
            request=request,
            host=host,
            origin=origin,
        )
    except Exception as exc:  # domain errors are converted, never leaked
        code = str(getattr(exc, "code", "PERSONAL_MODE_BLOCKED"))
        detail = str(getattr(
            exc, "detail", "personal-mode guard or bundle validation failed"
        ))
        return 200, v2_contract.blocked(code, detail)

    if not isinstance(raw, dict):
        return 200, v2_contract.blocked(
            "INVALID_PERSONAL_SERVICE_RESULT",
            "personal service returned a non-object result",
        )

    status = raw.get("status")
    if status == "APPROVED" or status not in v2_contract.ALLOWED_STATUSES:
        return 200, v2_contract.blocked(
            "INVALID_PERSONAL_SERVICE_STATUS",
            "personal service returned a forbidden or unknown status",
        )

    recommendations = raw.get("recommendations") or []
    if not isinstance(recommendations, list):
        return 200, v2_contract.blocked(
            "INVALID_PERSONAL_RECOMMENDATIONS",
            "recommendations must be an array",
        )

    if status != v2_contract.Status.OWNER_REVIEWED:
        recommendations = []
    elif not recommendations:
        return 200, v2_contract.blocked(
            "NO_OWNER_REVIEWED_REGIMEN",
            "no eligible owner-reviewed regimen for this request",
            status=v2_contract.Status.REVIEW_REQUIRED,
        )
    elif any(
        not isinstance(item, dict)
        or item.get("governance_status") != "OWNER_REVIEWED_EXPERIMENTAL"
        for item in recommendations
    ):
        return 200, v2_contract.blocked(
            "INVALID_RECOMMENDATION_GOVERNANCE",
            "every recommendation must be OWNER_REVIEWED_EXPERIMENTAL",
        )

    return 200, v2_contract.envelope(
        status,
        recommendations=recommendations,
        bundle_version=raw.get("bundle_version"),
        review=raw.get("review"),
        errors=raw.get("errors"),
        trace=raw.get("trace"),
    )
