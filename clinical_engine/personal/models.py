"""Immutable contracts for the additive PERSONAL_PHYSICIAN mode.

These models deliberately do not import or extend the frozen Clinical Engine
models or the production approval lifecycle.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Mapping


PERSONAL_MODE = "PERSONAL_PHYSICIAN"
OWNER_BUNDLE_STATUS = "OWNER_REVIEWED_EXPERIMENTAL"


class PersonalModeError(Exception):
    """Malformed personal-mode configuration or bundle.

    ``code`` and ``detail`` are stable API-adapter fields. Ordinary guard and
    clinical review outcomes are returned as result mappings, not exceptions.
    """

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class OwnerProfile:
    owner_id: str
    display_name: str
    professional_role: str
    organisation: str
    registered_at: str
    active: bool
    mode_token_sha256: str
    request_audit_local: bool
    request_audit_append_only: bool
    persist_patient_data: bool = False


@dataclass(frozen=True, slots=True)
class OwnerAttestation:
    event_id: str
    event_sha256: str
    owner_id: str
    attested_at: str
    rationale: str
    source_snapshot_sha256: str
    attested_payload_sha256: str
    status: str


@dataclass(frozen=True, slots=True)
class Provenance:
    guideline_id: str
    guideline_title: str
    rubricator_id: str
    rubricator_version: str
    approval_year: int
    source_url: str
    source_pdf_sha256: str
    source_page: int
    source_wording: str
    guideline_status: str


@dataclass(frozen=True, slots=True)
class DoseSemantics:
    value_min: float
    value_max: float
    unit: str
    basis: str
    formulation_basis: str
    route: str
    frequency: str
    duration: str
    maximum_dose: str


@dataclass(frozen=True, slots=True)
class PopulationSemantics:
    eligible_groups: tuple[str, ...]
    adult: str
    pediatric: str
    neonatal: str
    pregnancy: str
    lactation: str
    renal: str
    hepatic: str


@dataclass(frozen=True, slots=True)
class SafetySemantics:
    allergy_classes: tuple[str, ...]
    contraindications: tuple[str, ...]
    interactions: tuple[str, ...]
    warnings: tuple[str, ...]
    requires_weight_kg: bool
    requires_renal_function: bool
    requires_pregnancy_status: bool
    requires_hepatic_function: bool


@dataclass(frozen=True, slots=True)
class TerminologyMapping:
    source: str
    normalized: str
    system: str
    code: str | None = None


@dataclass(frozen=True, slots=True)
class Alternative:
    regimen_id: str
    rejection_reason: str


@dataclass(frozen=True, slots=True)
class CalculatorBinding:
    disease_id: str
    scenario_id: str
    line_number: int
    route: str
    drug_ref: str | None
    combo_ref: tuple[str, ...]
    regimen_label: str | None
    regimen_index: int | None
    binding_version: str
    calculator_regimen_sha256: str


@dataclass(frozen=True, slots=True)
class PersonalRegimen:
    regimen_id: str
    diagnosis: str
    icd10: tuple[str, ...]
    therapy_line: str
    drug: str
    components: tuple[str, ...]
    dose: DoseSemantics
    population: PopulationSemantics
    safety: SafetySemantics
    provenance: Provenance
    terminology_mappings: tuple[TerminologyMapping, ...]
    alternatives: tuple[Alternative, ...]
    calculator_binding: CalculatorBinding
    attestation: OwnerAttestation
    governance_status: str


@dataclass(frozen=True, slots=True)
class PersonalPhysicianBundle:
    schema_version: str
    bundle_version: str
    build_version: str
    status: str
    owner_id: str
    built_at: str
    stale_after: str
    payload_sha256: str
    owner_signature: str
    regimens: tuple[PersonalRegimen, ...]


@dataclass(frozen=True, slots=True)
class PersonalRecommendationResult:
    status: str
    recommendations: tuple[Mapping[str, Any], ...]
    bundle_version: str | None
    review: Mapping[str, Any] | None = None
    trace: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "recommendations", tuple(_freeze_json(item) for item in self.recommendations))
        if self.review is not None:
            object.__setattr__(self, "review", _freeze_json(self.review))
        if self.trace is not None:
            object.__setattr__(self, "trace", _freeze_json(self.trace))

    def to_dict(self) -> dict[str, Any]:
        """Return the exact JSON-compatible mapping expected by API v2."""
        result: dict[str, Any] = {
            "status": self.status,
            "recommendations": [_copy_json(item) for item in self.recommendations],
            "bundle_version": self.bundle_version,
        }
        if self.review is not None:
            result["review"] = _copy_json(self.review)
        if self.trace is not None:
            result["trace"] = _copy_json(self.trace)
        return result


def dataclass_to_dict(value: Any) -> dict[str, Any]:
    """Convert a frozen personal DTO to an independent JSON-compatible dict."""
    return asdict(value)


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _copy_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _copy_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_json(item) for item in value]
    return value


__all__ = [
    "Alternative", "CalculatorBinding", "DoseSemantics", "OWNER_BUNDLE_STATUS", "OwnerAttestation",
    "OwnerProfile", "PERSONAL_MODE", "PersonalModeError", "PersonalPhysicianBundle",
    "PersonalRecommendationResult", "PersonalRegimen", "PopulationSemantics",
    "Provenance", "SafetySemantics", "TerminologyMapping", "dataclass_to_dict",
]
