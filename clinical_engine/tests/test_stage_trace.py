"""Milestone 8: Stage 10 — Trace (outcome labeling only)."""

from __future__ import annotations

from clinical_engine.models import (
    PatientQuery,
    RecommendationOutcome,
    SafetyAction,
    SafetyFlag,
    SafetyLevel,
)
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages.trace import Trace
from clinical_engine.tests.conftest import make_candidate, make_recommendation


def _flag(level: SafetyLevel, code: str = "TEST") -> SafetyFlag:
    return SafetyFlag(
        level=level,
        code=code,
        message="test",
        drug_ref="",
        stage="Test",
        action=SafetyAction.MONITOR_CLOSELY,
        requires_physician_acknowledgement=False,
    )


class TestOutcomeLabeling:
    def test_no_flags_is_accepted(self, stage_context: StageContext) -> None:
        c = make_recommendation(make_candidate("r1"))
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = Trace().run(state, stage_context)
        assert result.state.candidates[0].outcome is RecommendationOutcome.ACCEPTED

    def test_warning_flag_is_warning_outcome(self, stage_context: StageContext) -> None:
        c = make_recommendation(
            make_candidate("r1"), safety_flags=(_flag(SafetyLevel.WARNING),)
        )
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = Trace().run(state, stage_context)
        assert result.state.candidates[0].outcome is RecommendationOutcome.WARNING

    def test_absolute_contraindication_is_excluded_outcome(
        self, stage_context: StageContext
    ) -> None:
        # Defensive case: should not normally occur since ABSOLUTE flags are
        # always paired with a real exclusion by the raising stage.
        c = make_recommendation(
            make_candidate("r1"), safety_flags=(_flag(SafetyLevel.ABSOLUTE_CONTRAINDICATION),)
        )
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = Trace().run(state, stage_context)
        assert result.state.candidates[0].outcome is RecommendationOutcome.EXCLUDED

    def test_excluded_list_gets_excluded_outcome(self, stage_context: StageContext) -> None:
        c = make_recommendation(make_candidate("r1"))
        state = PipelineState(
            patient=PatientQuery(), candidates=(), excluded=((c, "allergy"),)
        )
        result = Trace().run(state, stage_context)
        rec, reason = result.state.excluded[0]
        assert rec.outcome is RecommendationOutcome.EXCLUDED
        assert reason == "allergy"

    def test_does_not_change_candidate_count(self, stage_context: StageContext) -> None:
        c1 = make_recommendation(make_candidate("r1"))
        c2 = make_recommendation(make_candidate("r2"))
        state = PipelineState(patient=PatientQuery(), candidates=(c1, c2))
        result = Trace().run(state, stage_context)
        assert len(result.state.candidates) == 2

    def test_empty_state_is_a_noop(self, stage_context: StageContext) -> None:
        state = PipelineState(patient=PatientQuery())
        result = Trace().run(state, stage_context)
        assert result.state.candidates == ()
        assert result.state.excluded == ()
