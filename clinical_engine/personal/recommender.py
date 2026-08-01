"""Stable API-v2-facing service for owner-reviewed personal bundles."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .bundle import (
    attest as append_attestation,
    build_personal_bundle,
    load_owner_profile,
    load_personal_bundle,
    register_owner as create_owner_profile,
)
from .guard import PersonalPhysicianGuard
from .models import (
    OWNER_BUNDLE_STATUS,
    OwnerProfile,
    PersonalModeError,
    PersonalPhysicianBundle,
    PersonalRecommendationResult,
    PersonalRegimen,
)

if TYPE_CHECKING:
    from clinical_engine.api.v2_contract import V2RecommendRequest
else:
    V2RecommendRequest = Any


class PersonalModeService:
    """Serve only validated owner-attested records from one immutable bundle.

    This class is intentionally independent of the frozen Engine and of
    ``PHYSICIAN_APPROVED``. It performs exact lookup and fail-closed input/safety
    checks; it does not calculate or silently select a dose.
    """

    def __init__(
        self,
        *,
        profile: OwnerProfile,
        bundle: PersonalPhysicianBundle,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._profile = profile
        self._bundle = bundle
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._guard = PersonalPhysicianGuard(profile=profile, bundle=bundle, clock=self._clock)

    register_owner = staticmethod(create_owner_profile)
    attest = staticmethod(append_attestation)
    build_bundle = staticmethod(build_personal_bundle)

    @classmethod
    def from_paths(
        cls,
        owner_profile_path: str | Path,
        bundle_path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> "PersonalModeService":
        profile = load_owner_profile(owner_profile_path)
        bundle = load_personal_bundle(bundle_path, profile=profile)
        return cls(profile=profile, bundle=bundle, clock=clock)

    @property
    def bundle_version(self) -> str:
        return self._bundle.bundle_version

    def health(self) -> dict[str, Any]:
        """Read-only local health summary; never changes approval or bundle state."""
        try:
            stale_after = datetime.fromisoformat(self._bundle.stale_after.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PersonalModeError("BUNDLE_TIME_INVALID", "stale_after must be ISO-8601") from exc
        if stale_after.tzinfo is None:
            raise PersonalModeError("BUNDLE_TIME_INVALID", "stale_after must include timezone")
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        stale = now >= stale_after
        static_guard_ok = (
            self._profile.active
            and self._profile.request_audit_local
            and self._profile.request_audit_append_only
            and not self._profile.persist_patient_data
            and self._bundle.status == OWNER_BUNDLE_STATUS
            and all(item.provenance.guideline_status == "CURRENT" for item in self._bundle.regimens)
        )
        eligible = static_guard_ok and not stale
        return {
            "status": "ok" if eligible else "blocked",
            "ready": eligible,
            "recommendation_eligible": eligible,
            "mode": "PERSONAL_PHYSICIAN",
            "owner_active": self._profile.active,
            "governance_status": OWNER_BUNDLE_STATUS,
            "bundle_version": self._bundle.bundle_version,
            "bundle_payload_sha256": self._bundle.payload_sha256,
            "regimen_count": len(self._bundle.regimens),
            "stale": stale,
        }

    def recommend(
        self,
        *,
        request: V2RecommendRequest,
        host: str,
        origin: str,
    ) -> dict[str, Any]:
        """Return the stable personal-mode mapping consumed by API v2.

        Ordinary guard or evidence/input failures return ``BLOCKED`` or
        ``REVIEW_REQUIRED`` with an empty recommendation list. Only malformed
        service configuration/bundle raises :class:`PersonalModeError`.
        """
        decision = self._guard.evaluate(request=request, host=host, origin=origin)
        if not decision.allowed:
            return PersonalRecommendationResult(
                status=decision.status,
                recommendations=(),
                bundle_version=self._bundle.bundle_version,
                review={"code": decision.code, "detail": decision.detail},
                trace={
                    "governance_status": OWNER_BUNDLE_STATUS,
                    "bundle_payload_sha256": self._bundle.payload_sha256,
                    "participating_stages": ["personal_physician_guard"],
                    "guard": {"code": decision.code, "allowed": False},
                },
            ).to_dict()

        query = _request_value(request, "query") or request
        diagnosis = _clean(_request_value(query, "diagnosis"))
        icd10 = _clean(_request_value(query, "icd10"))
        if not diagnosis and not icd10:
            return self._review_required(
                "DIAGNOSIS_REQUIRED", "query requires diagnosis or icd10", considered=[]
            )

        matched = tuple(item for item in self._bundle.regimens if _matches(item, diagnosis, icd10))
        if not matched:
            return self._review_required(
                "NO_OWNER_REVIEWED_REGIMEN",
                "no exact owner-reviewed regimen matches the query",
                considered=[],
            )

        patient = _request_value(query, "patient")
        preferences = _request_value(query, "preferences") or _request_value(request, "preferences")
        accepted: list[PersonalRegimen] = []
        considered: list[dict[str, Any]] = []
        for regimen in matched:
            reasons = _patient_rejection_reasons(regimen, patient, preferences)
            considered.append({
                "regimen_id": regimen.regimen_id,
                "accepted": not reasons,
                "rejection_reasons": reasons,
            })
            if not reasons:
                accepted.append(regimen)

        if not accepted:
            return self._review_required(
                "PATIENT_CONTEXT_INCOMPLETE_OR_UNSAFE",
                "all matching owner-reviewed regimens were withheld",
                considered=considered,
            )

        recommendations = tuple(_serialize_recommendation(item, rank=index) for index, item in enumerate(accepted, 1))
        trace = {
            "governance_status": OWNER_BUNDLE_STATUS,
            "bundle_payload_sha256": self._bundle.payload_sha256,
            "owner_id": self._profile.owner_id,
            "participating_stages": [
                "personal_physician_guard",
                "exact_owner_bundle_lookup",
                "patient_input_completeness",
                "personal_safety_filter",
                "trace_serialization",
            ],
            "considered_regimens": considered,
            "dose_calculation": "NOT_PERFORMED_SELECT_IN_CALCULATOR",
        }
        return PersonalRecommendationResult(
            status="OWNER_REVIEWED",
            recommendations=recommendations,
            bundle_version=self._bundle.bundle_version,
            trace=trace,
        ).to_dict()

    def _review_required(
        self,
        code: str,
        detail: str,
        *,
        considered: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return PersonalRecommendationResult(
            status="REVIEW_REQUIRED",
            recommendations=(),
            bundle_version=self._bundle.bundle_version,
            review={"code": code, "detail": detail},
            trace={
                "governance_status": OWNER_BUNDLE_STATUS,
                "bundle_payload_sha256": self._bundle.payload_sha256,
                "participating_stages": [
                    "personal_physician_guard", "exact_owner_bundle_lookup",
                    "patient_input_completeness", "personal_safety_filter",
                ],
                "considered_regimens": considered,
            },
        ).to_dict()


# Naming alias accepted by the RFC while PersonalModeService remains canonical.
PersonalRecommender = PersonalModeService


def _matches(regimen: PersonalRegimen, diagnosis: str | None, icd10: str | None) -> bool:
    diagnosis_match = diagnosis is not None and regimen.diagnosis.casefold() == diagnosis.casefold()
    icd_match = icd10 is not None and any(code.casefold() == icd10.casefold() for code in regimen.icd10)
    return diagnosis_match or icd_match


def _patient_rejection_reasons(regimen: PersonalRegimen, patient: Any, preferences: Any = None) -> list[str]:
    reasons: list[str] = []
    if patient is None:
        return ["PATIENT_CONTEXT_MISSING"]
    safety = regimen.safety
    population = _clean(_request_value(preferences, "population"))
    age = _request_value(patient, "age")
    if not population and isinstance(age, (int, float)) and not isinstance(age, bool):
        population = "neonate" if age < 28 / 365 else "child" if age < 18 else "adult"
    if not population:
        reasons.append("POPULATION_REQUIRED")
    elif population not in regimen.population.eligible_groups:
        reasons.append("POPULATION_NOT_ELIGIBLE")
    therapy_line = _clean(_request_value(preferences, "therapy_line"))
    if therapy_line and therapy_line.casefold() != regimen.therapy_line.casefold():
        reasons.append("THERAPY_LINE_MISMATCH")
    route = _clean(_request_value(preferences, "route_preference"))
    if route and route.casefold() != regimen.dose.route.casefold():
        reasons.append("ROUTE_MISMATCH")
    weight = _request_value(patient, "weight_kg")
    if safety.requires_weight_kg and (
        isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0
    ):
        reasons.append("WEIGHT_REQUIRED")
    renal = _clean(_request_value(patient, "renal_function"))
    if safety.requires_renal_function and (not renal or renal.casefold() in {"unknown", "неизвестно"}):
        reasons.append("RENAL_FUNCTION_REQUIRED")
    if safety.requires_pregnancy_status and _request_value(patient, "pregnant") is None:
        reasons.append("PREGNANCY_STATUS_REQUIRED")
    if _request_value(patient, "pregnant") is True and not any(term in regimen.population.pregnancy.casefold() for term in ("разреш", "eligible", "allowed")):
        reasons.append("PREGNANCY_REVIEW_REQUIRED")
    if safety.requires_hepatic_function and _request_value(patient, "hepatic_impairment") is None:
        reasons.append("HEPATIC_STATUS_REQUIRED")
    if _request_value(patient, "hepatic_impairment") is True and regimen.population.hepatic.casefold() not in {"eligible", "allowed", "разрешён"}:
        reasons.append("HEPATIC_REVIEW_REQUIRED")
    if safety.contraindications and _request_value(patient, "contraindications_cleared") is not True:
        reasons.append("CONTRAINDICATION_SCREEN_REQUIRED")
    if safety.interactions and _request_value(patient, "interactions_reviewed") is not True:
        reasons.append("INTERACTION_SCREEN_REQUIRED")
    if renal and renal.casefold() not in {"normal", "норма", "нет"} and regimen.population.renal.casefold() not in {"eligible", "allowed", "разрешён"}:
        reasons.append("RENAL_REVIEW_REQUIRED")

    allergy_terms = {
        value.casefold()
        for value in tuple(_request_value(patient, "allergies") or ())
        if isinstance(value, str)
    }
    regimen_terms = {
        regimen.drug.casefold(),
        *(item.casefold() for item in regimen.components),
        *(item.casefold() for item in safety.allergy_classes),
    }
    if allergy_terms.intersection(regimen_terms):
        reasons.append("ALLERGY_CONTRAINDICATION")
    return reasons


def _serialize_recommendation(regimen: PersonalRegimen, *, rank: int) -> dict[str, Any]:
    doc = asdict(regimen)
    doc["rank"] = rank
    doc["guideline_id"] = regimen.provenance.guideline_id
    doc["source"] = doc.pop("provenance")
    doc["governance_status"] = OWNER_BUNDLE_STATUS
    doc["calculation"] = {
        "performed": False,
        "instruction": "Physician must select a candidate before existing calculator arithmetic",
        "inputs": {},
        "output": None,
        "rounding_steps": [],
    }
    doc["local_mode_banner"] = {
        "required": True,
        "dismissible": False,
        "status": OWNER_BUNDLE_STATUS,
        "text": "Single-physician owner-reviewed experimental decision support",
    }
    return doc


def _request_value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None) if value is not None else None


def _clean(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = ["PersonalModeError", "PersonalModeService", "PersonalRecommender"]
