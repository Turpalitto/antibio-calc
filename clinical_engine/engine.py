"""Engine — orchestrates the pipeline (§2.1, §5.8).

Milestone 8 (final) scope: wires readers + runs the complete 10-stage
pipeline (DiagnosisMatch, RegimenLoad, PopulationFilter, TherapyLineSelect,
HardSafetyFilter, DoseCalculation, DoseAdjustment, InteractionCheck,
RankRecommendations, Trace). ``recommend()`` now returns a fully ranked,
safety-filtered, dose-calculated, interaction-checked RecommendationSet.

Not implemented (explicitly out of scope, documented in DECISIONS.md
2026-07-10 rather than silently skipped):
  - Confidence propagation (§7.3) -- Recommendation.confidence/
    confidence_breakdown stay at their defaults (0.0/None).
  - Plugin hooks (BEFORE_RANKING etc.) -- no plugin registry exists.
  - guideline_version in EngineMetadata -- placeholder "unversioned" until
    resources/diagnosis_index.json (294 curated entries) exists.
  - Non-default score profiles (ent/urology/icu/pediatrics) -- content
    curation task, not an architecture gap.
"""

from __future__ import annotations

import json
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

from clinical_engine.config import EngineConfig
from clinical_engine.models import (
    DecisionContext,
    DecisionReport,
    EngineError,
    EngineErrorCode,
    EngineMetadata,
    EngineNote,
    EngineRuntime,
    NoteSeverity,
    PatientQuery,
    RecommendationSet,
    SafetyLevel,
)
from clinical_engine.pipeline import ClinicalConstants, PipelineState, ScoreWeights, StageContext
from clinical_engine.readers.diagnosis_reader import DiagnosisProviderAdapter, JsonDiagnosisProvider
from clinical_engine.readers.drug_reference_reader import DrugReferenceReader, DrugSafetyProviderAdapter
from clinical_engine.readers.sqlite_reader import RegimenProviderAdapter, SQLiteReader
from clinical_engine.terminology import BasicTerminologyProvider, TerminologyProvider
from clinical_engine.stages.diagnosis_match import DiagnosisMatch
from clinical_engine.stages.dose_adjustment import DoseAdjustment
from clinical_engine.stages.dose_calculation import DoseCalculation
from clinical_engine.stages.hard_safety_filter import HardSafetyFilter
from clinical_engine.stages.interaction_check import InteractionCheck
from clinical_engine.stages.population_filter import PopulationFilter
from clinical_engine.stages.rank_recommendations import RankRecommendations
from clinical_engine.stages.regimen_load import RegimenLoad
from clinical_engine.stages.therapy_line_select import TherapyLineSelect
from clinical_engine.stages.trace import Trace

ENGINE_VERSION = "1.0.0"

# Milestone 13 Production Guard: diagnosis_index statuses that are NOT
# production-ready (uncurated clinical routing).
_UNCURATED_INDEX_STATUSES = frozenset({"AUTO_GENERATED_DRAFT", "PARTIALLY_CURATED"})

# See DECISIONS.md 2026-07-10 "EngineMetadata — real values where available".
_KNOWLEDGE_DATASET_VERSION = "KB-2026-07-09"  # documented KB build date, see PROJECT_STATE.md
_GUIDELINE_VERSION_PLACEHOLDER = "unversioned"  # pending resources/diagnosis_index.json curation

# Audit fix M3 (Milestone 9): resolve engine-owned resources relative to this
# package, not the process CWD, so the engine works regardless of where it is
# launched from (packaging / Flutter / tests from any directory).
_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent
_DICTIONARY_METADATA_PATH = _REPO_ROOT / "medical_dictionary" / "metadata.json"
_SCORE_PROFILES_DIR = _PACKAGE_DIR / "resources" / "score_profiles"


def _load_clinical_constants(path: str | Path) -> ClinicalConstants:
    """Loads resources/clinical_constants.json (see DECISIONS.md 2026-07-10
    "allergy_class_map curation" — this is a curated, hand-reviewed-pending
    resource, not a verbatim copy of db/index.json).
    """
    p = Path(path)
    if not p.exists():
        raise EngineError(
            EngineErrorCode.RESOURCE_PARSE_ERROR,
            f"clinical_constants not found: {p}",
            stage="HardSafetyFilter",
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise EngineError(
            EngineErrorCode.RESOURCE_PARSE_ERROR, str(exc), stage="HardSafetyFilter"
        ) from exc
    return ClinicalConstants(
        age_bands={k: tuple(v) for k, v in data.get("age_bands", {}).items()},
        renal_thresholds=dict(data.get("renal_thresholds", {})),
        allergy_class_map=dict(data.get("allergy_class_map", {})),
        allergy_class_hierarchy={
            k: tuple(v) for k, v in data.get("allergy_class_hierarchy", {}).items()
        },
    )


def _load_score_weights(profile_dir: str | Path, profile: str) -> ScoreWeights:
    """Loads resources/score_profiles/{profile}.json. Only "default" is
    curated today — see DECISIONS.md 2026-07-10."""
    p = Path(profile_dir) / f"{profile}.json"
    if not p.exists():
        raise EngineError(
            EngineErrorCode.SCORE_PROFILE_NOT_FOUND, f"score profile not found: {p}", stage="RankRecommendations"
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise EngineError(
            EngineErrorCode.RESOURCE_PARSE_ERROR, str(exc), stage="RankRecommendations"
        ) from exc
    fields = {f for f in ScoreWeights.__dataclass_fields__}
    return ScoreWeights(**{k: v for k, v in data.items() if k in fields})


def _load_dictionary_version(path: Path = _DICTIONARY_METADATA_PATH) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("version", "unknown"))
    except (OSError, json.JSONDecodeError):
        return "unknown"


class Engine:
    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self._constants = _load_clinical_constants(config.clinical_constants_path)
        self._sqlite_reader = SQLiteReader(config.sqlite_path)
        self._drug_ref_reader = DrugReferenceReader(config.drug_reference_path)
        self._diagnosis_provider = JsonDiagnosisProvider(config.diagnosis_index_path)
        # P0-2: always create adapters (thin). Flag decides what StageContext receives.
        self._regimen_provider = RegimenProviderAdapter(self._sqlite_reader)
        self._drug_safety_provider = DrugSafetyProviderAdapter(self._drug_ref_reader)
        self._diagnosis_provider_adapter = DiagnosisProviderAdapter(self._diagnosis_provider)
        # P1: TerminologyProvider. Always created, additive. Flag for use in stages.
        self._terminology_provider: TerminologyProvider = BasicTerminologyProvider(self._constants)
        self._guard_index_curation_status()
        self._score_weights = _load_score_weights(_SCORE_PROFILES_DIR, config.score_profile)
        self._stages = (
            DiagnosisMatch(),
            RegimenLoad(),
            PopulationFilter(),
            TherapyLineSelect(),
            HardSafetyFilter(),
            DoseCalculation(),
            DoseAdjustment(),
            InteractionCheck(),
            RankRecommendations(),
            Trace(),
        )
        self._metadata = EngineMetadata(
            decision_engine_version=ENGINE_VERSION,
            knowledge_dataset_version=_KNOWLEDGE_DATASET_VERSION,
            normalizer_version=self._normalizer_version(),
            dictionary_version=_load_dictionary_version(),
            guideline_version=_GUIDELINE_VERSION_PLACEHOLDER,
        )

    def _guard_index_curation_status(self) -> None:
        """Milestone 13 Production Guard. Detect an uncurated diagnosis_index.

        Only fires on an EXPLICIT draft status (AUTO_GENERATED_DRAFT /
        PARTIALLY_CURATED). An absent/empty status (e.g. bare-list test
        fixtures, or an index without meta) is treated as unknown, not draft,
        and never blocks. Does not touch any medical/clinical logic — a
        load-time data-status gate only.
        """
        status = (getattr(self._diagnosis_provider, "meta", {}) or {}).get("status")
        if status not in _UNCURATED_INDEX_STATUSES:
            return
        msg = (
            f"diagnosis_index status is '{status}' (not physician-curated): "
            f"{self.config.diagnosis_index_path}. Clinical routing is NOT "
            "verified for production."
        )
        if self.config.strict_mode:
            self._sqlite_reader.close()
            raise EngineError(EngineErrorCode.RESOURCE_NOT_CURATED, msg, stage="DiagnosisMatch")
        warnings.warn(msg, stacklevel=2)

    @staticmethod
    def _normalizer_version() -> str:
        # Imported lazily to avoid a hard import-time dependency between
        # packages; medical_normalizer is FROZEN and always available.
        from medical_normalizer.normalizer import NORMALIZER_VERSION

        return NORMALIZER_VERSION

    def close(self) -> None:
        self._sqlite_reader.close()

    def __enter__(self) -> "Engine":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    @property
    def metadata(self) -> EngineMetadata:
        return self._metadata

    def recommend(self, query: PatientQuery) -> RecommendationSet:
        run_start = time.perf_counter()
        # P0-2: always wire adapters to provider ports (wrap-only). Legacy reader attrs coexist for transition.
        # Flag (use_provider_ports) present for future gating / explicit tests. Behavior identical either way.
        ctx = StageContext(
            config=self.config,
            sqlite_reader=self._sqlite_reader,
            drug_ref_reader=self._drug_ref_reader,
            diagnosis_provider=self._diagnosis_provider,
            regimen_provider=self._regimen_provider,
            drug_safety_provider=self._drug_safety_provider,
            terminology_provider=self._terminology_provider,
            constants=self._constants,
            score_weights=self._score_weights,
        )
        state = PipelineState(patient=query)
        time_breakdown: dict[str, float] = {}

        for stage in self._stages:
            result = stage.run(state, ctx)
            state = result.state
            time_breakdown[stage.name] = result.elapsed_ms

        elapsed_ms = (time.perf_counter() - run_start) * 1000
        runtime = EngineRuntime(
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            elapsed_ms=elapsed_ms,
            profile=self.config.validation_policy,
            pipeline_time_breakdown=time_breakdown,
        )

        engine_notes: tuple[EngineNote, ...] = ()
        if not state.guideline_ids:
            engine_notes = (
                EngineNote(
                    code="NO_DIAGNOSIS_MATCH",
                    message="Diagnosis/ICD-10 not found in diagnosis_index",
                    stage="DiagnosisMatch",
                    severity=NoteSeverity.INFO,
                ),
            )
        elif not state.candidates and not state.excluded:
            engine_notes = (
                EngineNote(
                    code="NO_REGIMENS_EXTRACTED",
                    message="Matched guideline(s) have no regimens for this ValidationPolicy",
                    stage="RegimenLoad",
                    severity=NoteSeverity.INFO,
                ),
            )
        elif not state.candidates and state.excluded:
            engine_notes = (
                EngineNote(
                    code="ALL_CANDIDATES_EXCLUDED",
                    message=(
                        f"All {len(state.excluded)} matched regimen(s) were excluded "
                        "(population mismatch and/or safety exclusion) — see 'excluded'"
                    ),
                    stage="pipeline",  # could be PopulationFilter, HardSafetyFilter, or InteractionCheck
                    severity=NoteSeverity.WARN,
                ),
            )

        decision_context = DecisionContext(
            patient=query.patient,
            query=query,
            engine_metadata=self.metadata,
            runtime=runtime,
            profile=self.config.validation_policy,
        )

        return RecommendationSet(
            accepted=state.candidates,
            excluded=state.excluded,
            warnings=tuple(f for f in state.safety_flags if f.level is SafetyLevel.WARNING),
            traces=state.traces,
            safety_flags=state.safety_flags,
            metadata=self.metadata,
            runtime=runtime,
            decision_context=decision_context,
            engine_notes=engine_notes,
            query=query,
            elapsed_ms=elapsed_ms,
        )

    def build_report(self, result: RecommendationSet) -> DecisionReport:
        """§5.8. Confidence propagation (§7.3) not implemented yet (see
        module docstring) -- confidence_breakdowns is always {}."""
        return DecisionReport(
            query=result.query,
            accepted=result.accepted,
            excluded=result.excluded,
            warnings=result.warnings,
            traces=result.traces,
            confidence_breakdowns={},
            metadata=result.metadata,
            runtime=result.runtime,
            engine_notes=result.engine_notes,
        )
