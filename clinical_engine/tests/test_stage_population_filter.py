"""Milestone 4: Stage 3 — PopulationFilter."""

from __future__ import annotations

import dataclasses

from clinical_engine.models import DecisionCode, Patient, PatientQuery, Preferences, Recommendation
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages.population_filter import PopulationFilter
from clinical_engine.tests.conftest import make_candidate, make_recommendation


def _state(query: PatientQuery, *flags: tuple[bool, bool]) -> PipelineState:
    recs = tuple(
        make_recommendation(make_candidate(f"r{i}", adult=adult, child=child))
        for i, (adult, child) in enumerate(flags)
    )
    return PipelineState(patient=query, candidates=recs)


class TestPopulationFilter:
    def test_adult_patient_keeps_only_adult_candidates(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(patient=Patient(age=45))
        state = _state(query, (True, False), (False, True))
        result = PopulationFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        assert result.state.candidates[0].candidate.adult is True
        assert len(result.state.excluded) == 1
        assert "population_mismatch" in result.state.excluded[0][1]

    def test_child_patient_keeps_only_child_candidates(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(patient=Patient(age=10))
        state = _state(query, (True, False), (False, True))
        result = PopulationFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        assert result.state.candidates[0].candidate.child is True

    def test_neonate_age_maps_onto_child_flag(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(age=10 / 365))  # 10 days old
        state = _state(query, (True, False), (False, True))
        result = PopulationFilter().run(state, stage_context)
        assert result.metrics["population_target"] == "neonate"
        assert len(result.state.candidates) == 1
        assert result.state.candidates[0].candidate.child is True

    def test_explicit_preference_overrides_age(self, stage_context: StageContext) -> None:
        query = PatientQuery(
            patient=Patient(age=45), preferences=Preferences(population="child")
        )
        state = _state(query, (True, False), (False, True))
        result = PopulationFilter().run(state, stage_context)
        assert result.metrics["population_target"] == "child"
        assert result.state.candidates[0].candidate.child is True

    def test_age_none_and_no_preference_is_ambiguous_no_filtering(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery()
        state = _state(query, (True, False), (False, True))
        result = PopulationFilter().run(state, stage_context)
        assert len(result.state.candidates) == 2  # nothing excluded
        assert result.state.excluded == ()
        assert result.metrics["population_target"] == "ambiguous"
        assert any(t.decision_code is DecisionCode.POPULATION for t in result.state.traces)

    def test_unrecognized_preference_value_degrades_to_ambiguous(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(preferences=Preferences(population="adolescent"))
        state = _state(query, (True, False), (False, True))
        result = PopulationFilter().run(state, stage_context)
        assert len(result.state.candidates) == 2
        assert result.metrics["population_target"] == "ambiguous"

    def test_existing_excluded_entries_are_preserved(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(age=45))
        state = _state(query, (True, False))
        prior_excluded = (state.candidates[0], "already_excluded_upstream")
        state = dataclasses.replace(state, candidates=(), excluded=(prior_excluded,))
        result = PopulationFilter().run(state, stage_context)
        assert result.state.excluded == (prior_excluded,)  # untouched, only grows

    def test_empty_candidates_is_a_noop(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(age=45))
        state = PipelineState(patient=query)
        result = PopulationFilter().run(state, stage_context)
        assert result.state.candidates == ()
        assert result.state.excluded == ()
