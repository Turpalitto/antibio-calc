"""Clinical Decision Engine — ANTIBIO.

Public API surface grows as milestones land (see docs/superpowers/specs/
clinical-decision-engine-v1.md). Milestone 1 exposes only the data model
layer (enums, dataclasses, config, pipeline scaffolding). ``Engine`` itself
is added once engine.py and the stage pipeline exist.
"""

from __future__ import annotations

from clinical_engine.config import EngineConfig, Profiles
from clinical_engine.engine import Engine
from clinical_engine.manifest import BundleManifest, load_manifest, validate_manifest
from clinical_engine.terminology import BasicTerminologyProvider, TerminologyProvider
from clinical_engine.models import (
    ClinicalPriority,
    ConfidenceBreakdown,
    ConfidenceLevel,
    DecisionCode,
    DecisionContext,
    DecisionReport,
    DilutionRoute,
    DiagnosisEntry,
    DoseCalculationMethod,
    DoseDetail,
    DrugForm,
    DrugInfo,
    EngineError,
    EngineErrorCode,
    EngineMetadata,
    EngineNote,
    EngineRuntime,
    Evidence,
    InteractionSeverity,
    NoteSeverity,
    Patient,
    PatientQuery,
    PediatricDosing,
    Preferences,
    PregnancyCategory,
    Recommendation,
    RecommendationCandidate,
    RecommendationOutcome,
    RecommendationSet,
    SafetyAction,
    SafetyFlag,
    SafetyLevel,
    StageTrace,
    ValidationPolicy,
)

__all__ = [
    "BundleManifest",
    "load_manifest",
    "validate_manifest",
    "Engine",
    "EngineConfig",
    "Profiles",
    "ClinicalPriority",
    "ConfidenceBreakdown",
    "ConfidenceLevel",
    "DecisionCode",
    "DecisionContext",
    "DecisionReport",
    "DilutionRoute",
    "DiagnosisEntry",
    "DoseCalculationMethod",
    "DoseDetail",
    "DrugForm",
    "DrugInfo",
    "EngineError",
    "EngineErrorCode",
    "EngineMetadata",
    "EngineNote",
    "EngineRuntime",
    "Evidence",
    "InteractionSeverity",
    "NoteSeverity",
    "Patient",
    "PatientQuery",
    "PediatricDosing",
    "Preferences",
    "PregnancyCategory",
    "Recommendation",
    "RecommendationCandidate",
    "RecommendationOutcome",
    "RecommendationSet",
    "SafetyAction",
    "SafetyFlag",
    "SafetyLevel",
    "StageTrace",
    "ValidationPolicy",
    "TerminologyProvider",
    "BasicTerminologyProvider",
]
