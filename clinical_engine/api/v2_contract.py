"""Version 2 contract for local PERSONAL_PHYSICIAN decision support.

API v1 stays frozen in :mod:`clinical_engine.api.contract`.  This module is
additive and deliberately cannot serialize a personal result as ``APPROVED``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


API_VERSION = "2"
OPERATING_MODE = "PERSONAL_PHYSICIAN"


class Status:
    OWNER_REVIEWED = "OWNER_REVIEWED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


ALLOWED_STATUSES = frozenset({
    Status.OWNER_REVIEWED,
    Status.REVIEW_REQUIRED,
    Status.BLOCKED,
    Status.ERROR,
})


class RequestError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class PatientDTO:
    age: float | None = None
    weight_kg: float | None = None
    pregnant: bool | None = None
    renal_function: str | None = None
    hepatic_impairment: bool | None = None
    allergies: tuple[str, ...] = ()
    current_meds: tuple[str, ...] = ()
    contraindications_cleared: bool | None = None
    interactions_reviewed: bool | None = None


@dataclass(frozen=True, slots=True)
class PreferencesDTO:
    therapy_line: str | None = None
    route_preference: str | None = None
    population: str | None = None


@dataclass(frozen=True, slots=True)
class V2RecommendRequest:
    api_version: str
    operating_mode: str
    owner_id: str
    session_token: str
    diagnosis: str | None
    icd10: str | None
    patient: PatientDTO
    preferences: PreferencesDTO


def _optional_number(value: Any, field: str, *, allow_zero: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RequestError("INVALID_REQUEST", f"{field} must be numeric")
    number = float(value)
    if number < 0 or (number == 0 and not allow_zero):
        relation = "zero or greater" if allow_zero else "greater than zero"
        raise RequestError("INVALID_REQUEST", f"{field} must be {relation}")
    return number


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) for v in value):
        raise RequestError("INVALID_REQUEST", f"{field} must be an array of strings")
    return tuple(v.strip() for v in value if v.strip())


def parse_recommend_request(body: dict[str, Any]) -> V2RecommendRequest:
    if not isinstance(body, dict):
        raise RequestError("INVALID_REQUEST", "request body must be a JSON object")
    if str(body.get("api_version") or "") != API_VERSION:
        raise RequestError("UNSUPPORTED_API_VERSION", "api_version must be '2'")
    if body.get("operating_mode") != OPERATING_MODE:
        raise RequestError("INVALID_OPERATING_MODE", f"operating_mode must be {OPERATING_MODE}")

    owner_id = body.get("owner_id")
    session_token = body.get("session_token")
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise RequestError("OWNER_ID_REQUIRED", "owner_id is required")
    if not isinstance(session_token, str) or not session_token.strip():
        raise RequestError("SESSION_TOKEN_REQUIRED", "session_token is required")

    query = body.get("query")
    if not isinstance(query, dict):
        raise RequestError("INVALID_REQUEST", "missing 'query' object")
    diagnosis = query.get("diagnosis")
    icd10 = query.get("icd10")
    if not isinstance(diagnosis, (str, type(None))) or not isinstance(icd10, (str, type(None))):
        raise RequestError("INVALID_REQUEST", "diagnosis and icd10 must be strings")
    diagnosis = diagnosis.strip() if diagnosis else None
    icd10 = icd10.strip() if icd10 else None
    if not diagnosis and not icd10:
        raise RequestError("INVALID_REQUEST", "query requires diagnosis or icd10")

    raw_patient = query.get("patient") or {}
    raw_preferences = query.get("preferences") or {}
    if not isinstance(raw_patient, dict) or not isinstance(raw_preferences, dict):
        raise RequestError("INVALID_REQUEST", "patient and preferences must be objects")

    renal = raw_patient.get("renal_function")
    if renal is not None and not isinstance(renal, str):
        raise RequestError("INVALID_REQUEST", "renal_function must be a string")
    pregnant = raw_patient.get("pregnant")
    hepatic = raw_patient.get("hepatic_impairment")
    contraindications_cleared = raw_patient.get("contraindications_cleared")
    interactions_reviewed = raw_patient.get("interactions_reviewed")
    if pregnant is not None and not isinstance(pregnant, bool):
        raise RequestError("INVALID_REQUEST", "pregnant must be boolean or null")
    if hepatic is not None and not isinstance(hepatic, bool):
        raise RequestError("INVALID_REQUEST", "hepatic_impairment must be boolean or null")
    if contraindications_cleared is not None and not isinstance(contraindications_cleared, bool):
        raise RequestError("INVALID_REQUEST", "contraindications_cleared must be boolean or null")
    if interactions_reviewed is not None and not isinstance(interactions_reviewed, bool):
        raise RequestError("INVALID_REQUEST", "interactions_reviewed must be boolean or null")

    patient = PatientDTO(
        age=_optional_number(raw_patient.get("age"), "age", allow_zero=True),
        weight_kg=_optional_number(raw_patient.get("weight_kg"), "weight_kg"),
        pregnant=pregnant,
        renal_function=renal.strip() if renal else None,
        hepatic_impairment=hepatic,
        allergies=_string_tuple(raw_patient.get("allergies"), "allergies"),
        current_meds=_string_tuple(raw_patient.get("current_meds"), "current_meds"),
        contraindications_cleared=contraindications_cleared,
        interactions_reviewed=interactions_reviewed,
    )
    preferences = PreferencesDTO(
        therapy_line=raw_preferences.get("therapy_line"),
        route_preference=raw_preferences.get("route_preference"),
        population=raw_preferences.get("population"),
    )
    return V2RecommendRequest(
        api_version=API_VERSION,
        operating_mode=OPERATING_MODE,
        owner_id=owner_id.strip(),
        session_token=session_token.strip(),
        diagnosis=diagnosis,
        icd10=icd10,
        patient=patient,
        preferences=preferences,
    )


def envelope(
    status: str,
    *,
    recommendations: list[dict[str, Any]] | None = None,
    bundle_version: str | None = None,
    review: dict[str, Any] | None = None,
    errors: list[dict[str, str]] | None = None,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in ALLOWED_STATUSES or status == "APPROVED":
        raise ValueError(f"invalid personal-mode status: {status}")
    result: dict[str, Any] = {
        "api_version": API_VERSION,
        "operating_mode": OPERATING_MODE,
        "status": status,
        "governance_status": "OWNER_REVIEWED_EXPERIMENTAL",
        "bundle_version": bundle_version,
        "recommendations": recommendations or [],
        "errors": errors or [],
        "trace": trace or {},
        "banner": {
            "code": "PERSONAL_PHYSICIAN_SINGLE_REVIEW",
            "text": (
                "Локальный режим врача-владельца. Проверяйте схему и расчёт "
                "по указанной клинической рекомендации."
            ),
            "dismissible": False,
        },
    }
    if review is not None:
        result["review"] = review
    return result


def blocked(code: str, detail: str, *, status: str = Status.BLOCKED) -> dict[str, Any]:
    return envelope(
        status,
        review={"code": code, "reason": detail},
        errors=[] if status == Status.REVIEW_REQUIRED else [{"code": code, "detail": detail}],
    )
