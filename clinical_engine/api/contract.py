"""Public API contract: versioning, status, error taxonomy, request parsing (INT-5a).

Framework-agnostic (stdlib only). Defines the STABLE shapes every client depends
on, per docs/architecture/INT-5_API_Architecture_Review.md. No clinical logic,
no medical data.
"""

from __future__ import annotations

import math
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
    "clinical_review": ("CLINICAL_REVIEW_REQUIRED",),
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


# ── patient-field coercion (backported from api/v2_contract.py) ───────────────
# v1 previously coerced these with bare ``bool()``/``tuple()``, which silently
# accepted a string "false" as a pregnant patient and exploded a JSON string into
# one allergy per character — both fail-OPEN on a safety-relevant field. Every
# value below is now type-checked and rejected rather than coerced.

def _optional_number(value: Any, name: str, *, allow_zero: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RequestError("INVALID_REQUEST", f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RequestError("INVALID_REQUEST", f"{name} must be a finite number")
    if number < 0 or (number == 0 and not allow_zero):
        relation = "zero or greater" if allow_zero else "greater than zero"
        raise RequestError("INVALID_REQUEST", f"{name} must be {relation}")
    return number


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) for v in value):
        raise RequestError("INVALID_REQUEST", f"{name} must be an array of strings")
    return tuple(v.strip() for v in value if v.strip())


def _optional_bool(value: Any, name: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise RequestError("INVALID_REQUEST", f"{name} must be boolean")
    return value


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RequestError("INVALID_REQUEST", f"{name} must be a string")
    return value.strip() or None


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
    diagnosis = _optional_text(query.get("diagnosis"), "diagnosis")
    icd10 = _optional_text(query.get("icd10"), "icd10")
    if not diagnosis and not icd10:
        raise RequestError("INVALID_REQUEST", "query requires 'diagnosis' or 'icd10'")

    p = query.get("patient") or {}
    pref = query.get("preferences") or {}
    if not isinstance(p, dict) or not isinstance(pref, dict):
        raise RequestError("INVALID_REQUEST", "'patient' and 'preferences' must be objects")

    patient = PatientDTO(
        age=_optional_number(p.get("age"), "age", allow_zero=True),
        weight_kg=_optional_number(p.get("weight_kg"), "weight_kg"),
        pregnant=_optional_bool(p.get("pregnant"), "pregnant"),
        renal_function=_optional_text(p.get("renal_function"), "renal_function"),
        hepatic_impairment=_optional_bool(p.get("hepatic_impairment"), "hepatic_impairment"),
        allergies=_string_tuple(p.get("allergies"), "allergies"),
        current_meds=_string_tuple(p.get("current_meds"), "current_meds"),
    )
    preferences = PreferencesDTO(
        therapy_line=_optional_text(pref.get("therapy_line"), "therapy_line"),
        route_preference=_optional_text(pref.get("route_preference"), "route_preference"),
        population=_optional_text(pref.get("population"), "population"),
    )
    return RecommendRequest(
        api_version=api_version,
        diagnosis=diagnosis, icd10=icd10,
        patient=patient, preferences=preferences,
    )


# ── response envelope helpers ─────────────────────────────────
# D4 (audit 2026-10-05): `trace` is part of the v1 contract, not an optional
# extra — the Clinical Traceability Law requires the stage chain to be
# visible on every response. It is `{}` iff no engine result exists (parse
# errors, corpus unavailable, recommender not wired); once the engine ran it
# carries participating_stages/stages/considered_regimens (service._trace_obj).
def envelope(status: str, *, knowledge_version: str | None = None,
             errors: list[dict] | None = None, notes: list[dict] | None = None,
             trace: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {"api_version": API_VERSION, "status": status,
                           "knowledge_version": knowledge_version}
    doc.update(extra)
    doc["errors"] = errors or []
    doc["notes"] = notes or []
    doc["trace"] = trace or {}
    return doc


def error_response(code: str, detail: str = "") -> dict[str, Any]:
    return envelope(Status.ERROR, errors=[error_obj(code, detail)])
