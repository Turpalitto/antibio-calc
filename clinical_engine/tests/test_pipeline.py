"""Milestone 1: pipeline.py — stage contract scaffolding."""

from __future__ import annotations

import dataclasses

import pytest

from clinical_engine.config import EngineConfig
from clinical_engine.models import PatientQuery
from clinical_engine.pipeline import (
    ClinicalConstants,
    PipelineStage,
    PluginHook,
    PipelineState,
    ScoreWeights,
    StageContext,
    StageResult,
)


class TestPluginHook:
    def test_all_hooks_present(self) -> None:
        names = {h.name for h in PluginHook}
        assert names == {
            "BEFORE_RANKING",
            "AFTER_RANKING",
            "BEFORE_DOSE",
            "AFTER_DOSE",
            "BEFORE_RETURN",
        }


class TestScoreWeights:
    def test_defaults_match_spec(self) -> None:
        w = ScoreWeights()
        assert w.therapy_line_match == 3.0
        assert w.confidence == 2.0
        assert w.evidence_recency == 1.5
        assert w.safety_fit == 2.5
        assert w.route_preference == 1.0
        assert w.population_match == 1.5
        assert w.interaction_penalty == 0.5

    def test_frozen(self) -> None:
        w = ScoreWeights()
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(w, "confidence", 99.0)


class TestClinicalConstants:
    def test_construct(self) -> None:
        constants = ClinicalConstants(
            age_bands={"neonate": (0.0, 28 / 365)},
            renal_thresholds={"amoxicillin": 30.0},
            allergy_class_map={"amoxicillin": "penicillins"},
            allergy_class_hierarchy={"penicillins": ("amoxicillin", "ampicillin")},
        )
        assert constants.allergy_class_map["amoxicillin"] == "penicillins"


class TestPipelineState:
    def test_defaults_are_empty(self) -> None:
        state = PipelineState(patient=PatientQuery())
        assert state.guideline_ids == ()
        assert state.candidates == ()
        assert state.excluded == ()
        assert state.traces == ()
        assert state.safety_flags == ()

    def test_replace_is_only_mutation_path(self) -> None:
        state = PipelineState(patient=PatientQuery())
        state2 = dataclasses.replace(state, guideline_ids=("g1", "g2"))
        assert state.guideline_ids == ()
        assert state2.guideline_ids == ("g1", "g2")

    def test_frozen(self) -> None:
        state = PipelineState(patient=PatientQuery())
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(state, "guideline_ids", ("g1",))


class TestStageContract:
    """A dummy stage proves the Protocol is usable without concrete readers."""

    def test_dummy_stage_conforms_to_protocol(self) -> None:
        class NoOpStage:
            name = "NoOp"

            def run(self, state: PipelineState, ctx: StageContext) -> StageResult:
                return StageResult(state=state)

        stage: PipelineStage = NoOpStage()
        ctx = StageContext(
            config=EngineConfig(sqlite_path="x.sqlite"),
            sqlite_reader=None,
            drug_ref_reader=None,
            diagnosis_provider=None,
            # P0-2
            regimen_provider=None,
            drug_safety_provider=None,
            terminology_provider=None,
            constants=ClinicalConstants(
                age_bands={}, renal_thresholds={}, allergy_class_map={}, allergy_class_hierarchy={}
            ),
            score_weights=ScoreWeights(),
        )
        state = PipelineState(patient=PatientQuery())
        result = stage.run(state, ctx)
        assert result.state is state
        assert result.elapsed_ms == 0.0
        assert result.warnings == ()

    def test_stage_result_defaults(self) -> None:
        state = PipelineState(patient=PatientQuery())
        result = StageResult(state=state)
        assert result.metrics == {}
        assert result.warnings == ()
