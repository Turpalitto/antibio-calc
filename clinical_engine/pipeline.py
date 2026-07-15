"""PipelineStage Protocol + PluginHook + stage context/state scaffolding.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md section 5.7.

Reader types are imported under TYPE_CHECKING (audit fix M5, Milestone 9):
readers import from models/config only, never from pipeline, so there is no
runtime circular import — TYPE_CHECKING keeps import graph clean while
restoring static type safety on the most-used context objects.

No I/O, no clinical logic — this module only defines the stage contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

from clinical_engine.config import EngineConfig
from clinical_engine.models import PatientQuery, Recommendation, SafetyFlag, StageTrace

if TYPE_CHECKING:
    from clinical_engine.readers.diagnosis_reader import DiagnosisProvider
    from clinical_engine.readers.drug_reference_reader import DrugReferenceReader, DrugSafetyProvider
    from clinical_engine.readers.sqlite_reader import RegimenProvider, SQLiteReader
    from clinical_engine.terminology import TerminologyProvider


class PluginHook(Enum):
    BEFORE_RANKING = "before_ranking"
    AFTER_RANKING = "after_ranking"
    BEFORE_DOSE = "before_dose"
    AFTER_DOSE = "after_dose"
    BEFORE_RETURN = "before_return"


@dataclass(frozen=True, slots=True)
class ClinicalConstants:
    """Typed constants -- not dict."""

    age_bands: dict[str, tuple[float, float]]
    renal_thresholds: dict[str, float]
    allergy_class_map: dict[str, str]
    allergy_class_hierarchy: dict[str, tuple[str, ...]]
    # Note: interaction severity keywords are NOT here -- they belong to
    # preparation-time tooling that builds structured fields in drugs_reference.
    # Engine does not parse interaction text at runtime (invariant #13).


@dataclass(frozen=True, slots=True)
class ScoreWeights:
    """Typed score weights -- not dict."""

    therapy_line_match: float = 3.0
    confidence: float = 2.0
    evidence_recency: float = 1.5
    safety_fit: float = 2.5
    route_preference: float = 1.0
    population_match: float = 1.5
    interaction_penalty: float = 0.5  # multiplied by InteractionSeverity.value (0-4)


@dataclass(frozen=True, slots=True)
class StageContext:
    config: EngineConfig
    sqlite_reader: "SQLiteReader"
    drug_ref_reader: "DrugReferenceReader"
    diagnosis_provider: "DiagnosisProvider"
    # P0-2 providers (adapters behind ports). Legacy readers kept for transition coexistence.
    regimen_provider: "RegimenProvider"
    drug_safety_provider: "DrugSafetyProvider"
    # P1: terminology for ATC/allergy. Additive.
    terminology_provider: "TerminologyProvider"
    constants: ClinicalConstants
    score_weights: ScoreWeights


@dataclass(frozen=True, slots=True)
class PipelineState:
    # immutable -- stages use dataclasses.replace()
    patient: PatientQuery
    guideline_ids: tuple[str, ...] = ()
    candidates: tuple[Recommendation, ...] = ()
    excluded: tuple[tuple[Recommendation, str], ...] = ()
    traces: tuple[StageTrace, ...] = ()  # immutable + append-only
    safety_flags: tuple[SafetyFlag, ...] = ()


@dataclass(frozen=True, slots=True)
class StageResult:
    state: PipelineState
    metrics: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    warnings: tuple[str, ...] = ()


class PipelineStage(Protocol):
    name: str

    def run(self, state: PipelineState, ctx: StageContext) -> StageResult: ...
