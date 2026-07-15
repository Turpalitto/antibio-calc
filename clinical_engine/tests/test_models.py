"""Milestone 1: models.py — instantiation + frozen-invariant tests."""

from __future__ import annotations

import dataclasses

import pytest

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


def _candidate(**overrides: object) -> RecommendationCandidate:
    base = dict(
        regimen_id="r1",
        guideline_id="g1",
        drug_normalized="amoxicillin",
        drug_ref="amoxicillin",
        dose=500.0,
        dose_unit="mg",
        route="oral",
        frequency=3.0,
        duration_min=5.0,
        duration_max=7.0,
        duration_recommended=5.0,
        therapy_line="first",
        adult=True,
        child=False,
        pregnancy=None,
        renal_adjustment=False,
        atc_code="J01CA04",
        confidence=0.9,
        validation_verdict="PASS",
        source_pdf="cr654.pdf",
        source_page="28",
        source_quote="Drug of choice",
        source_section="",
        diagnosis="CAP",
        mkb="J18",
        guideline_year=2024,
    )
    base.update(overrides)
    return RecommendationCandidate(**base)


class TestEnums:
    def test_validation_policy_values(self) -> None:
        assert ValidationPolicy.STRICT.value == "strict"
        assert ValidationPolicy.ALLOW_REVIEW.value == "allow_review"
        assert ValidationPolicy.DEBUG.value == "debug"
        assert ValidationPolicy.AUDIT.value == "audit"

    def test_interaction_severity_ordering(self) -> None:
        assert InteractionSeverity.UNKNOWN.value == 0
        assert InteractionSeverity.CONTRAINDICATED.value == 4
        assert (
            InteractionSeverity.UNKNOWN.value
            < InteractionSeverity.MINOR.value
            < InteractionSeverity.MODERATE.value
            < InteractionSeverity.MAJOR.value
            < InteractionSeverity.CONTRAINDICATED.value
        )

    def test_confidence_level_is_discrete(self) -> None:
        assert {c.value for c in ConfidenceLevel} == {0.0, 0.25, 0.5, 0.75, 1.0}

    def test_pregnancy_category_members(self) -> None:
        assert {c.name for c in PregnancyCategory} == {
            "PROHIBITED",
            "CAUTION",
            "ALLOWED",
            "UNKNOWN",
        }

    def test_decision_code_covers_spec_codes(self) -> None:
        expected = {
            "ALLERGY",
            "PREGNANCY",
            "RENAL",
            "AGE",
            "THERAPY_LINE",
            "POPULATION",
            "INTERACTION",
            "NO_MATCH",
            "DIAGNOSIS_RESOLVED",
            "DRUG_UNKNOWN",
            "DOSE_UNCALCULABLE",
            "CI",
            "HEPATIC",
        }
        assert {c.name for c in DecisionCode} == expected


class TestEngineError:
    def test_engine_error_carries_code_and_stage(self) -> None:
        err = EngineError(EngineErrorCode.SQLITE_NOT_FOUND, "no db", stage="RegimenLoad")
        assert err.code is EngineErrorCode.SQLITE_NOT_FOUND
        assert err.detail == "no db"
        assert err.stage == "RegimenLoad"
        assert isinstance(err, Exception)

    def test_engine_error_stage_optional(self) -> None:
        err = EngineError(EngineErrorCode.SQLITE_CORRUPT, "bad db")
        assert err.stage is None


class TestFrozenInvariant:
    """Constitutional Invariant #4: all dataclasses frozen, slots."""

    @pytest.mark.parametrize(
        "instance",
        [
            Patient(),
            Preferences(),
            PatientQuery(),
            DrugForm(form_type="tablet", concentration="500mg"),
            _candidate(),
        ],
    )
    def test_assignment_raises(self, instance: object) -> None:
        # frozen=True + slots=True rebuilds the class, so __setattr__'s closure
        # over the pre-slots class only reliably raises for a *real* field name
        # (unknown names hit a cls-identity mismatch and raise TypeError instead).
        first_field = dataclasses.fields(instance)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, first_field, "mutated")

    def test_all_public_dataclasses_are_frozen(self) -> None:
        import clinical_engine.models as models_module

        for name in dir(models_module):
            obj = getattr(models_module, name)
            if dataclasses.is_dataclass(obj):
                assert obj.__dataclass_params__.frozen, f"{name} must be frozen"


class TestPatientQuery:
    def test_defaults(self) -> None:
        q = PatientQuery()
        assert q.diagnosis is None
        assert q.patient == Patient()
        assert q.preferences == Preferences()

    def test_replace_creates_new_instance(self) -> None:
        q = PatientQuery(diagnosis="CAP")
        q2 = dataclasses.replace(q, icd10="J18")
        assert q.icd10 is None
        assert q2.icd10 == "J18"
        assert q2.diagnosis == "CAP"


class TestDrugInfo:
    def test_construct_with_all_fields(self) -> None:
        info = DrugInfo(
            drug_ref="amoxicillin",
            inn="amoxicillin",
            drug_class="penicillins",
            renal_adjustment="GFR<30: extend interval",
            hepatic_adjustment=None,
            pregnancy_category=PregnancyCategory.CAUTION,
            age_restriction_min=None,
            age_restriction_max=None,
            contraindications=None,
            interactions=None,
            monitoring=None,
            forms=(DrugForm(form_type="tablet", concentration="500mg"),),
            dilution={},
            pediatric_dosing=PediatricDosing(mg_per_kg_day=40.0, max_daily_mg=1500.0),
        )
        assert info.pregnancy_category is PregnancyCategory.CAUTION
        assert info.pediatric_dosing is not None
        assert info.pediatric_dosing.mg_per_kg_day == 40.0


class TestDilutionRoute:
    def test_defaults(self) -> None:
        route = DilutionRoute(solvent_options=({"name": "saline"},))
        assert route.steps == ()
        assert route.concentration_standard_mg_ml is None


class TestRecommendationAndSet:
    def test_recommendation_minimal(self) -> None:
        rec = Recommendation(
            candidate=_candidate(),
            dose=None,
            safety_flags=(),
            interaction_severity=None,
        )
        assert rec.outcome is None
        assert rec.rank is None
        assert rec.score_breakdown == {}

    def test_recommendation_with_dose_and_safety(self) -> None:
        dose = DoseDetail(
            calculated_dose_mg=500.0,
            dose_unit="mg",
            frequency_per_day=3.0,
            duration_days=5.0,
            max_daily_mg=1500.0,
            calculation_method=DoseCalculationMethod.FIXED,
            adjustment_applied=None,
            calculation_note=None,
        )
        flag = SafetyFlag(
            level=SafetyLevel.WARNING,
            code="DRUG_UNKNOWN",
            message="not in reference",
            drug_ref="unknown_drug",
            stage="HardSafetyFilter",
            action=SafetyAction.MONITOR_CLOSELY,
            requires_physician_acknowledgement=False,
        )
        rec = Recommendation(
            candidate=_candidate(),
            dose=dose,
            safety_flags=(flag,),
            interaction_severity=InteractionSeverity.UNKNOWN,
            outcome=RecommendationOutcome.WARNING,
        )
        assert rec.dose.calculation_method is DoseCalculationMethod.FIXED
        assert rec.safety_flags[0].level is SafetyLevel.WARNING

    def test_recommendation_set_assembly(self) -> None:
        rec = Recommendation(
            candidate=_candidate(), dose=None, safety_flags=(), interaction_severity=None
        )
        metadata = EngineMetadata(
            decision_engine_version="1.0.0",
            knowledge_dataset_version="KB-2026-07-09",
            normalizer_version="1.2.0",
            dictionary_version="1.0.0",
            guideline_version="2024-07",
        )
        runtime = EngineRuntime(
            generated_at="2026-07-10T00:00:00Z",
            elapsed_ms=12.3,
            profile=ValidationPolicy.STRICT,
        )
        query = PatientQuery(diagnosis="CAP")
        ctx = DecisionContext(
            patient=query.patient,
            query=query,
            engine_metadata=metadata,
            runtime=runtime,
            profile=ValidationPolicy.STRICT,
        )
        rset = RecommendationSet(
            accepted=(rec,),
            excluded=(),
            warnings=(),
            traces=(),
            safety_flags=(),
            metadata=metadata,
            runtime=runtime,
            decision_context=ctx,
            engine_notes=(),
            query=query,
            elapsed_ms=12.3,
        )
        assert rset.accepted[0] is rec
        assert rset.metadata.decision_engine_version == "1.0.0"


class TestEvidenceAndTrace:
    def test_stage_trace_defaults(self) -> None:
        trace = StageTrace(
            stage_name="DiagnosisMatch",
            decision_code=DecisionCode.NO_MATCH,
            reason="not found",
        )
        assert trace.evidence is None
        assert trace.decision_confidence is ConfidenceLevel.FULL

    def test_evidence_full(self) -> None:
        ev = Evidence(
            source_pdf="cr654.pdf",
            source_page="28",
            source_quote="quote",
            source_section="Antibacterial therapy",
            guideline_title="CAP in adults",
            guideline_year=2024,
            guideline_revision_date="2024-03-15",
            source_url="https://cr.minzdrav.gov.ru/recomend/654",
        )
        assert ev.guideline_year == 2024


class TestDecisionReport:
    def test_to_dict_and_to_json_roundtrip(self) -> None:
        metadata = EngineMetadata(
            decision_engine_version="1.0.0",
            knowledge_dataset_version="KB-2026-07-09",
            normalizer_version="1.2.0",
            dictionary_version="1.0.0",
            guideline_version="2024-07",
        )
        runtime = EngineRuntime(
            generated_at="2026-07-10T00:00:00Z", elapsed_ms=1.0, profile=ValidationPolicy.STRICT
        )
        query = PatientQuery(diagnosis="CAP")
        report = DecisionReport(
            query=query,
            accepted=(),
            excluded=(),
            warnings=(),
            traces=(),
            confidence_breakdowns={},
            metadata=metadata,
            runtime=runtime,
            engine_notes=(
                EngineNote(
                    code="NO_MATCH", message="not found", stage="DiagnosisMatch",
                    severity=NoteSeverity.INFO,
                ),
            ),
        )
        d = report.to_dict()
        assert d["metadata"]["decision_engine_version"] == "1.0.0"
        assert d["engine_notes"][0]["severity"] == "info"
        json_str = report.to_json()
        assert "decision_engine_version" in json_str

    def test_confidence_breakdown_shape(self) -> None:
        breakdown = ConfidenceBreakdown(
            source=0.9, decision=0.8, dose=1.0, completeness=0.7, evidence=1.0, final=0.87
        )
        assert breakdown.final == 0.87
