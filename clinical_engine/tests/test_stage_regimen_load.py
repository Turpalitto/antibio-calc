"""Milestone 3: Stage 2 — RegimenLoad."""

from __future__ import annotations

import dataclasses

from clinical_engine.models import PatientQuery, ValidationPolicy
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages.regimen_load import RegimenLoad


class TestRegimenLoad:
    def test_no_guideline_ids_short_circuits(self, stage_context: StageContext) -> None:
        state = PipelineState(patient=PatientQuery())
        result = RegimenLoad().run(state, stage_context)
        assert result.state.candidates == ()
        assert result.metrics["candidates_loaded"] == 0

    def test_loads_candidates_for_matched_guideline(self, stage_context: StageContext) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state = PipelineState(patient=query, guideline_ids=("g_cap_adult",))
        result = RegimenLoad().run(state, stage_context)
        assert result.metrics["candidates_loaded"] == 1  # STRICT default -> PASS only
        assert len(result.state.candidates) == 1

    def test_validation_policy_from_config_is_respected(self, stage_context: StageContext) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state = PipelineState(patient=query, guideline_ids=("g_cap_adult",))
        debug_ctx = dataclasses.replace(
            stage_context,
            config=dataclasses.replace(
                stage_context.config, validation_policy=ValidationPolicy.DEBUG
            ),
        )
        result = RegimenLoad().run(state, debug_ctx)
        assert result.metrics["candidates_loaded"] == 3  # PASS + REVIEW + REJECT

    def test_drug_ref_resolved(self, stage_context: StageContext) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state = PipelineState(patient=query, guideline_ids=("g_cap_adult",))
        result = RegimenLoad().run(state, stage_context)
        candidate = result.state.candidates[0].candidate
        assert candidate.drug_normalized == "Амоксициллин"
        assert candidate.drug_ref == "amoxicillin"

    def test_unresolvable_drug_ref_is_none_not_an_error(self, stage_context: StageContext) -> None:
        query = PatientQuery(diagnosis="ostryi tsistit")
        state = PipelineState(patient=query, guideline_ids=("g_cystitis",))
        result = RegimenLoad().run(state, stage_context)
        candidate = result.state.candidates[0].candidate
        # "Фосфомицин" isn't in the drug-reference fixture -> unresolved, not a crash.
        assert candidate.drug_ref is None

    def test_guideline_year_joined_from_diagnosis_entry(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state = PipelineState(patient=query, guideline_ids=("g_cap_adult",))
        result = RegimenLoad().run(state, stage_context)
        candidate = result.state.candidates[0].candidate
        assert candidate.guideline_year == 2024

    def test_candidates_are_wrapped_in_recommendation_with_no_dose_yet(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        state = PipelineState(patient=query, guideline_ids=("g_cap_adult",))
        result = RegimenLoad().run(state, stage_context)
        rec = result.state.candidates[0]
        assert rec.dose is None
        assert rec.safety_flags == ()
        assert rec.interaction_severity is None
        assert rec.outcome is None

    def test_unknown_guideline_id_yields_no_candidates(self, stage_context: StageContext) -> None:
        state = PipelineState(patient=PatientQuery(), guideline_ids=("does_not_exist",))
        result = RegimenLoad().run(state, stage_context)
        assert result.state.candidates == ()
