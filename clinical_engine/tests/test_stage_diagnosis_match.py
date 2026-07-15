"""Milestone 3: Stage 1 — DiagnosisMatch."""

from __future__ import annotations

from clinical_engine.models import DecisionCode, Patient, PatientQuery
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages.diagnosis_match import DiagnosisMatch


class TestDiagnosisMatch:
    def test_match_by_diagnosis_name(self, stage_context: StageContext) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state = PipelineState(patient=query)
        result = DiagnosisMatch().run(state, stage_context)
        assert result.state.guideline_ids == ("g_cap_adult",)
        assert result.metrics["guideline_ids_matched"] == 1
        assert result.state.traces == ()

    def test_match_by_icd10(self, stage_context: StageContext) -> None:
        query = PatientQuery(icd10="N30")
        state = PipelineState(patient=query)
        result = DiagnosisMatch().run(state, stage_context)
        assert result.state.guideline_ids == ("g_cystitis",)

    def test_no_match_produces_empty_guideline_ids_and_trace(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(diagnosis="completely unknown disease")
        state = PipelineState(patient=query)
        result = DiagnosisMatch().run(state, stage_context)
        assert result.state.guideline_ids == ()
        assert result.metrics["guideline_ids_matched"] == 0
        assert len(result.state.traces) == 1
        assert result.state.traces[0].decision_code is DecisionCode.NO_MATCH

    def test_no_query_input_is_no_match(self, stage_context: StageContext) -> None:
        state = PipelineState(patient=PatientQuery(patient=Patient(age=30)))
        result = DiagnosisMatch().run(state, stage_context)
        assert result.state.guideline_ids == ()

    def test_does_not_touch_candidates(self, stage_context: StageContext) -> None:
        query = PatientQuery(diagnosis="ostryi sinusit")
        state = PipelineState(patient=query)
        result = DiagnosisMatch().run(state, stage_context)
        assert result.state.candidates == ()

    def test_diagnosis_normalization(self, stage_context: StageContext) -> None:
        tp = stage_context.terminology_provider
        norm = tp.normalize_diagnosis("острый гайморит", "J01.0")
        assert norm is not None
        assert norm.normalized_diagnosis == "Острый бактериальный синусит у взрослых"
        assert norm.confidence == "HIGH"
        assert "synonym" in norm.reason
