"""Public API contract: versioning, status, error taxonomy, request parsing (INT-5a).

Framework-agnostic (stdlib only). Defines the STABLE shapes every client depends
on, per docs/architecture/INT-5_API_Architecture_Review.md. No clinical logic,
no medical data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── versioning ────────────────────────────────────────────────
API_VERSION = "1"
SUPPORTED_API_VERSIONS = ("1",)


# ── application status (carried over HTTP 200) ────────────────
class Status:
    APPROVED = "APPROVED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ERROR = "ERROR"


# ── error taxonomy (stable codes; reuses INT-2/3/4 codes) ─────
# category -> codes
ERROR_CATEGORIES: dict[str, tuple[str, ...]] = {
    "review_required": ("NO_APPROVED_DIAGNOSIS", "NO_APPROVED_REGIMEN", "KNOWLEDGE_UNAVAILABLE"),
    "missing_diagnosis": ("DIAGNOSIS_NOT_FOUND",),
    "missing_regimen": ("REGIMEN_NOT_FOUND", "NO_REGIMENS_EXTRACTED", "MISSING_REGIMEN"),
    "provenance_failure": ("METADATA_NOT_FOUND", "PDF_NOT_FOUND", "SHA_MISMATCH",
                           "REVIEW_INFO_MISSING", "PROVENANCE_CHAIN_BROKEN"),
    "corpus_unavailable": ("CORPUS_UNAVAILABLE",),
    "validation_failure": ("DUPLICATE_DECISION", "ORPHAN_REVIEW", "ORPHAN_CURATED_ENTRY",
                           "APPROVED_DIAGNOSIS_MISSING_REGIMEN",
                           "APPROVED_REGIMEN_MISSING_DIAGNOSIS", "PHYSICIAN_APPROVAL_MISSING"),
    "request": ("UNSUPPORTED_API_VERSION", "INVALID_REQUEST", "NOT_IMPLEMENTED"),
}

# reverse lookup: code -> category
CODE_TO_CATEGORY: dict[str, str] = {
    code: cat for cat, codes in ERROR_CATEGORIES.items() for code in codes
}


def error_obj(code: str, detail: str = "") -> dict[str, Any]:
    return {"code": code, "category": CODE_TO_CATEGORY.get(code, "request"), "detail": detail}


# ── request DTOs ──────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class PatientDTO:
    age: float | None = None
    weight_kg: float | None = None
    pregnant: bool = False
    renal_function: str | None = None
    hepatic_impairment: bool = False
    allergies: tuple[str, ...] = ()
    current_meds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreferencesDTO:
    therapy_line: str | None = None
    route_preference: str | None = None
    population: str | None = None


@dataclass(frozen=True, slots=True)
class RecommendRequest:
    api_version: str
    diagnosis: str | None
    icd10: str | None
    patient: PatientDTO
    preferences: PreferencesDTO


class RequestError(Exception):
    """Malformed request. Carries a stable error code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def parse_recommend_request(body: dict[str, Any]) -> RecommendRequest:
    """Validate the request envelope. Raises RequestError with a stable code.
    Does NOT perform clinical validation (that is the engine's job)."""
    if not isinstance(body, dict):
        raise RequestError("INVALID_REQUEST", "request body must be a JSON object")

    api_version = str(body.get("api_version") or API_VERSION)
    if api_version not in SUPPORTED_API_VERSIONS:
        raise RequestError("UNSUPPORTED_API_VERSION",
                           f"api_version {api_version!r} not in {list(SUPPORTED_API_VERSIONS)}")

    query = body.get("query")
    if not isinstance(query, dict):
        raise RequestError("INVALID_REQUEST", "missing 'query' object")
    if not (query.get("diagnosis") or query.get("icd10")):
        raise RequestError("INVALID_REQUEST", "query requires 'diagnosis' or 'icd10'")

    p = query.get("patient") or {}
    pref = query.get("preferences") or {}
    if not isinstance(p, dict) or not isinstance(pref, dict):
        raise RequestError("INVALID_REQUEST", "'patient' and 'preferences' must be objects")

    patient = PatientDTO(
        age=p.get("age"), weight_kg=p.get("weight_kg"),
        pregnant=bool(p.get("pregnant", False)),
        renal_function=p.get("renal_function"),
        hepatic_impairment=bool(p.get("hepatic_impairment", False)),
        allergies=tuple(p.get("allergies") or ()),
        current_meds=tuple(p.get("current_meds") or ()),
    )
    preferences = PreferencesDTO(
        therapy_line=pref.get("therapy_line"),
        route_preference=pref.get("route_preference"),
        population=pref.get("population"),
    )
    return RecommendRequest(
        api_version=api_version,
        diagnosis=query.get("diagnosis"), icd10=query.get("icd10"),
        patient=patient, preferences=preferences,
    )


# ── response envelope helpers ─────────────────────────────────
def envelope(status: str, *, knowledge_version: str | None = None,
             errors: list[dict] | None = None, notes: list[dict] | None = None,
             **extra: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {"api_version": API_VERSION, "status": status,
                           "knowledge_version": knowledge_version}
    doc.update(extra)
    doc["errors"] = errors or []
    doc["notes"] = notes or []
    return doc


def error_response(code: str, detail: str = "") -> dict[str, Any]:
    return envelope(Status.ERROR, errors=[error_obj(code, detail)])
