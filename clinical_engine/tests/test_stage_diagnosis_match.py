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


class TestRoutingProvenance:
    """M-1: the two lookup signals must agree, and mixed provenance must be
    visible instead of merged into one anonymous list."""

    def test_conflicting_signals_select_nothing_and_flag_it(
        self, stage_context: StageContext
    ) -> None:
        # "ostryi tsistit" -> g_cystitis; "J18" -> g_cap_adult. Disjoint.
        query = PatientQuery(diagnosis="ostryi tsistit", icd10="J18")
        result = DiagnosisMatch().run(PipelineState(patient=query), stage_context)
        assert result.state.guideline_ids == ()
        codes = {f.code for f in result.state.safety_flags}
        assert "DIAGNOSIS_ROUTING_CONFLICT" in codes
        flag = [f for f in result.state.safety_flags
                if f.code == "DIAGNOSIS_ROUTING_CONFLICT"][0]
        assert flag.requires_physician_acknowledgement
        assert result.state.traces[-1].decision_code is DecisionCode.NO_MATCH
        # The trace names both signals, so the physician sees the contradiction.
        assert "Matched by name" in result.state.traces[-1].reason
        assert "Matched by ICD-10" in result.state.traces[-1].reason

    def test_single_guideline_match_adds_no_provenance_flag(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", icd10="J18")
        result = DiagnosisMatch().run(PipelineState(patient=query), stage_context)
        assert result.state.guideline_ids == ("g_cap_adult",)
        assert "MIXED_GUIDELINE_PROVENANCE" not in {f.code for f in result.state.safety_flags}

    def test_mixed_guideline_provenance_is_flagged(
        self, stage_context: StageContext, tmp_path
    ) -> None:
        import dataclasses
        import json

        from clinical_engine.readers.diagnosis_reader import JsonDiagnosisProvider

        entries = [
            {"guideline_id": "g1", "diagnosis_name": "пневмония", "icd10_codes": ["J18"],
             "guideline_title": "a", "guideline_year": 2024,
             "guideline_revision_date": None, "source_url": ""},
            {"guideline_id": "g2", "diagnosis_name": "пневмония", "icd10_codes": ["J18"],
             "guideline_title": "b", "guideline_year": 2023,
             "guideline_revision_date": None, "source_url": ""},
        ]
        index = tmp_path / "idx.json"
        index.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        ctx = dataclasses.replace(
            stage_context, diagnosis_provider=JsonDiagnosisProvider(index)
        )
        result = DiagnosisMatch().run(PipelineState(patient=PatientQuery(diagnosis="пневмония")), ctx)
        assert set(result.state.guideline_ids) == {"g1", "g2"}
        flag = [f for f in result.state.safety_flags
                if f.code == "MIXED_GUIDELINE_PROVENANCE"][0]
        assert "g1" in flag.message and "g2" in flag.message
        assert any("mixed guideline provenance" in t.reason for t in result.state.traces)
