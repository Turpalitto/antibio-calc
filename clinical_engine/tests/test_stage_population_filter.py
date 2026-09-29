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

    def test_age_overrides_conflicting_preference(self, stage_context: StageContext) -> None:
        """C-3: age is a fact, preferences.population is only a hint.

        The old code returned the preference immediately, so this query resolved
        to "child" for a 45-year-old and filtered adult regimens away.
        """
        query = PatientQuery(
            patient=Patient(age=45), preferences=Preferences(population="child")
        )
        state = _state(query, (True, False), (False, True))
        result = PopulationFilter().run(state, stage_context)
        assert result.metrics["population_target"] == "adult"
        assert result.state.candidates[0].candidate.adult is True
        # The override is recorded, never silent.
        conflicts = [t for t in result.state.traces if "overridden" in t.reason]
        assert len(conflicts) == 1
        assert conflicts[0].decision_code is DecisionCode.POPULATION

    def test_infant_with_adult_preference_stays_pediatric(
        self, stage_context: StageContext
    ) -> None:
        """The verified harm: age=0.25 (3 months) + preference "adult" used to
        resolve to ADULT, and DoseCalculation then applied a 500 mg adult fixed
        dose (~119 mg/kg) to a 4.2 kg infant with no flag."""
        query = PatientQuery(
            patient=Patient(age=0.25, weight_kg=4.2),
            preferences=Preferences(population="adult"),
        )
        state = _state(query, (True, False), (False, True))
        result = PopulationFilter().run(state, stage_context)
        assert result.metrics["population_target"] == "child"  # 3 months: past the 28-day band
        assert result.state.candidates[0].candidate.child is True
        assert any("overridden" in t.reason for t in result.state.traces)

    def test_agreeing_preference_is_accepted_without_conflict(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(
            patient=Patient(age=45), preferences=Preferences(population="adult")
        )
        result = PopulationFilter().run(_state(query, (True, False)), stage_context)
        assert result.metrics["population_target"] == "adult"
        assert not any("overridden" in t.reason for t in result.state.traces)

    def test_preference_decides_only_when_age_is_unknown(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(preferences=Preferences(population="child"))
        result = PopulationFilter().run(_state(query, (True, False), (False, True)), stage_context)
        assert result.metrics["population_target"] == "child"
        assert result.state.candidates[0].candidate.child is True

    def test_unrecognized_preference_with_known_age_uses_age(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(
            patient=Patient(age=45), preferences=Preferences(population="adolescent")
        )
        result = PopulationFilter().run(_state(query, (True, False), (False, True)), stage_context)
        assert result.metrics["population_target"] == "adult"

    def test_negative_age_is_ambiguous_never_the_child_band(
        self, stage_context: StageContext
    ) -> None:
        """L-1: child_min was bound and never used, so -1 fell into the child band."""
        query = PatientQuery(patient=Patient(age=-1))
        result = PopulationFilter().run(_state(query, (True, False), (False, True)), stage_context)
        assert result.metrics["population_target"] == "ambiguous"
        assert result.state.excluded == ()  # degraded, not a silent exclusion
        assert any("out of range" in t.reason for t in result.state.traces)

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
