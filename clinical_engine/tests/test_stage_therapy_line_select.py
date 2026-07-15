"""Milestone 4: Stage 4 — TherapyLineSelect.

Per DECISIONS.md 2026-07-10: this stage is a pass-through, not a filter.
Mismatched therapy lines must survive to RankRecommendations (Milestone 8),
which scores them via a partial-credit table.
"""

from __future__ import annotations

from clinical_engine.models import DecisionCode, PatientQuery, Preferences
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages.therapy_line_select import TherapyLineSelect
from clinical_engine.tests.conftest import make_candidate, make_recommendation


def _state(preference: str | None, *lines: str) -> PipelineState:
    query = PatientQuery(preferences=Preferences(therapy_line=preference))
    recs = tuple(
        make_recommendation(make_candidate(f"r{i}", therapy_line=line))
        for i, line in enumerate(lines)
    )
    return PipelineState(patient=query, candidates=recs)


class TestTherapyLineSelect:
    def test_no_preference_keeps_all_lines_untouched(self, stage_context: StageContext) -> None:
        state = _state(None, "first", "alternative", "reserve")
        result = TherapyLineSelect().run(state, stage_context)
        assert len(result.state.candidates) == 3
        assert result.state.excluded == ()
        assert result.metrics["therapy_line_preference"] is None

    def test_preference_does_not_exclude_mismatched_lines(
        self, stage_context: StageContext
    ) -> None:
        state = _state("first", "first", "alternative", "reserve", "unknown")
        result = TherapyLineSelect().run(state, stage_context)
        # All 4 survive -- RankRecommendations (Milestone 8) will score them, not this stage.
        assert len(result.state.candidates) == 4
        assert result.state.excluded == ()

    def test_preference_recorded_in_trace(self, stage_context: StageContext) -> None:
        state = _state("reserve", "first")
        result = TherapyLineSelect().run(state, stage_context)
        matches = [t for t in result.state.traces if t.decision_code is DecisionCode.THERAPY_LINE]
        assert len(matches) == 1
        assert "reserve" in matches[0].reason

    def test_no_preference_adds_no_trace(self, stage_context: StageContext) -> None:
        state = _state(None, "first")
        result = TherapyLineSelect().run(state, stage_context)
        assert result.state.traces == ()

    def test_candidates_unchanged_identity_when_no_preference(
        self, stage_context: StageContext
    ) -> None:
        state = _state(None, "first")
        result = TherapyLineSelect().run(state, stage_context)
        assert result.state.candidates == state.candidates
