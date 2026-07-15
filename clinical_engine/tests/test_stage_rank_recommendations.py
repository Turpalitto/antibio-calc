"""Milestone 8: Stage 9 — RankRecommendations.

Invariant #3 (Constitution §12): operates ONLY on state.candidates. Cannot
touch state.excluded, SafetyFlags, or DoseDetail.
"""

from __future__ import annotations

from clinical_engine.models import (
    InteractionSeverity,
    Patient,
    PatientQuery,
    Preferences,
    SafetyAction,
    SafetyFlag,
    SafetyLevel,
)
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages.rank_recommendations import RankRecommendations
from clinical_engine.tests.conftest import make_candidate, make_recommendation


def _warning_flag(code: str = "TEST_WARNING") -> SafetyFlag:
    return SafetyFlag(
        level=SafetyLevel.WARNING,
        code=code,
        message="test",
        drug_ref="",
        stage="Test",
        action=SafetyAction.MONITOR_CLOSELY,
        requires_physician_acknowledgement=False,
    )


class TestConfidenceScoring:
    def test_higher_confidence_ranks_higher(self, stage_context: StageContext) -> None:
        low = make_recommendation(make_candidate("low", confidence=0.2))
        high = make_recommendation(make_candidate("high", confidence=0.9))
        state = PipelineState(patient=PatientQuery(), candidates=(low, high))
        result = RankRecommendations().run(state, stage_context)
        ranked_ids = [r.candidate.regimen_id for r in result.state.candidates]
        assert ranked_ids == ["high", "low"]
        assert result.state.candidates[0].rank == 1
        assert result.state.candidates[1].rank == 2


class TestTherapyLineScoring:
    def test_exact_match_beats_partial(self, stage_context: StageContext) -> None:
        exact = make_recommendation(make_candidate("exact", therapy_line="first"))
        partial = make_recommendation(make_candidate("partial", therapy_line="reserve"))
        query = PatientQuery(preferences=Preferences(therapy_line="first"))
        state = PipelineState(patient=query, candidates=(partial, exact))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].candidate.regimen_id == "exact"

    def test_partial_score_table_first_preference(self, stage_context: StageContext) -> None:
        query = PatientQuery(preferences=Preferences(therapy_line="first"))
        alt = make_recommendation(make_candidate("alt", therapy_line="alternative"))
        reserve = make_recommendation(make_candidate("reserve", therapy_line="reserve"))
        state = PipelineState(patient=query, candidates=(reserve, alt))
        result = RankRecommendations().run(state, stage_context)
        # "first" pref: alternative=0.5 > reserve=0.3 -- alt should rank higher
        assert result.state.candidates[0].candidate.regimen_id == "alt"

    def test_no_preference_gives_first_line_half_bonus(self, stage_context: StageContext) -> None:
        first = make_recommendation(make_candidate("first_c", therapy_line="first"))
        other = make_recommendation(make_candidate("other_c", therapy_line="alternative"))
        state = PipelineState(patient=PatientQuery(), candidates=(other, first))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].candidate.regimen_id == "first_c"

    def test_undefined_preference_degrades_to_conservative_partial(
        self, stage_context: StageContext
    ) -> None:
        # "prophylaxis"/"empiric" preferences have no row in the spec table.
        query = PatientQuery(preferences=Preferences(therapy_line="prophylaxis"))
        c = make_recommendation(make_candidate("r1", therapy_line="first"))
        state = PipelineState(patient=query, candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].score_breakdown["therapy_line"] == 0.1


class TestRecencyScoring:
    def test_recent_guideline_ranks_higher(self, stage_context: StageContext) -> None:
        recent = make_recommendation(make_candidate("recent", guideline_year=2025))
        old = make_recommendation(make_candidate("old", guideline_year=2010))
        state = PipelineState(patient=PatientQuery(), candidates=(old, recent))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].candidate.regimen_id == "recent"

    def test_missing_year_scores_zero_recency(self, stage_context: StageContext) -> None:
        c = make_recommendation(make_candidate("r1", guideline_year=None))
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].score_breakdown["evidence_recency"] == 0.0


class TestSafetyFitScoring:
    def test_warnings_reduce_score(self, stage_context: StageContext) -> None:
        clean = make_recommendation(make_candidate("clean"))
        flagged_candidate = make_candidate("flagged")
        flagged = make_recommendation(flagged_candidate, safety_flags=(_warning_flag(),))
        state = PipelineState(patient=PatientQuery(), candidates=(flagged, clean))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].candidate.regimen_id == "clean"

    def test_safety_fit_never_negative(self, stage_context: StageContext) -> None:
        many_flags = tuple(_warning_flag(f"W{i}") for i in range(10))
        c = make_recommendation(make_candidate("r1"), safety_flags=many_flags)
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].score_breakdown["safety_fit"] == 0.0
        assert result.state.candidates[0].score >= 0.0


class TestRoutePreference:
    def test_matching_route_scores_bonus(self, stage_context: StageContext) -> None:
        query = PatientQuery(preferences=Preferences(route_preference="oral"))
        c = make_recommendation(make_candidate("r1", route="oral"))
        state = PipelineState(patient=query, candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].score_breakdown["route_preference"] == 1.0

    def test_no_preference_scores_zero(self, stage_context: StageContext) -> None:
        c = make_recommendation(make_candidate("r1", route="oral"))
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].score_breakdown["route_preference"] == 0.0


class TestPopulationMatchScoring:
    def test_matching_population_scores_full(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(age=45))
        c = make_recommendation(make_candidate("r1", adult=True, child=False))
        state = PipelineState(patient=query, candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].score_breakdown["population_match"] == 1.5  # weight * 1.0

    def test_ambiguous_population_scores_half(self, stage_context: StageContext) -> None:
        c = make_recommendation(make_candidate("r1"))
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].score_breakdown["population_match"] == 0.75  # weight * 0.5


class TestInteractionPenalty:
    def test_higher_severity_penalizes_more(self, stage_context: StageContext) -> None:
        unknown = make_recommendation(
            make_candidate("unknown"), interaction_severity=InteractionSeverity.UNKNOWN
        )
        major = make_recommendation(
            make_candidate("major"), interaction_severity=InteractionSeverity.MAJOR
        )
        state = PipelineState(patient=PatientQuery(), candidates=(major, unknown))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].candidate.regimen_id == "unknown"

    def test_no_interaction_no_penalty(self, stage_context: StageContext) -> None:
        c = make_recommendation(make_candidate("r1"), interaction_severity=None)
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].score_breakdown["interaction_penalty"] == 0.0


class TestInvariants:
    def test_never_touches_excluded(self, stage_context: StageContext) -> None:
        excluded_rec = make_recommendation(make_candidate("excl"))
        c = make_recommendation(make_candidate("r1"))
        prior_excluded = ((excluded_rec, "some_reason"),)
        state = PipelineState(
            patient=PatientQuery(), candidates=(c,), excluded=prior_excluded
        )
        result = RankRecommendations().run(state, stage_context)
        assert result.state.excluded == prior_excluded  # byte-identical, untouched

    def test_never_changes_safety_flags(self, stage_context: StageContext) -> None:
        flags = (_warning_flag(),)
        c = make_recommendation(make_candidate("r1"), safety_flags=flags)
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == flags

    def test_never_changes_dose(self, stage_context: StageContext) -> None:
        c = make_recommendation(make_candidate("r1"), dose=None)
        state = PipelineState(patient=PatientQuery(), candidates=(c,))
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates[0].dose is None

    def test_deterministic_ranking(self, stage_context: StageContext) -> None:
        a = make_recommendation(make_candidate("a", confidence=0.5))
        b = make_recommendation(make_candidate("b", confidence=0.5))
        state = PipelineState(patient=PatientQuery(), candidates=(a, b))
        r1 = RankRecommendations().run(state, stage_context)
        r2 = RankRecommendations().run(state, stage_context)
        assert [r.candidate.regimen_id for r in r1.state.candidates] == [
            r.candidate.regimen_id for r in r2.state.candidates
        ]


class TestEmptyCandidates:
    def test_no_candidates_is_a_noop(self, stage_context: StageContext) -> None:
        state = PipelineState(patient=PatientQuery())
        result = RankRecommendations().run(state, stage_context)
        assert result.state.candidates == ()
