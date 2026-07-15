"""Milestone 6: Stage 6 — DoseCalculation."""

from __future__ import annotations

from clinical_engine.models import (
    DecisionCode,
    DoseCalculationMethod,
    Patient,
    PatientQuery,
    Preferences,
)
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages.dose_calculation import DoseCalculation
from clinical_engine.tests.conftest import make_candidate, make_recommendation


def _state(query: PatientQuery, *candidates) -> PipelineState:
    recs = tuple(make_recommendation(c) for c in candidates)
    return PipelineState(patient=query, candidates=recs)


class TestAdultFixedDose:
    def test_dose_and_frequency_present_yields_fixed_dose(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(patient=Patient(age=45))
        c = make_candidate("r1", adult=True, child=False, dose=500.0, dose_unit="mg", frequency=3.0)
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        dose = result.state.candidates[0].dose
        assert dose.calculation_method is DoseCalculationMethod.FIXED
        assert dose.calculated_dose_mg == 500.0
        assert dose.frequency_per_day == 3.0
        assert dose.adjustment_history == ("base: 500.0mg",)

    def test_missing_dose_is_uncalculated_with_warning(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(patient=Patient(age=45))
        c = make_candidate("r1", adult=True, child=False, dose=None)
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        rec = result.state.candidates[0]
        assert rec.dose.calculation_method is DoseCalculationMethod.UNCALCULATED
        assert any(f.code == "DOSE_UNCALCULABLE" for f in rec.safety_flags)
        assert any(t.decision_code is DecisionCode.DOSE_UNCALCULABLE for t in result.state.traces)

    def test_missing_frequency_is_uncalculated(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(age=45))
        c = make_candidate("r1", adult=True, child=False, dose=500.0, frequency=None)
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        assert result.state.candidates[0].dose.calculation_method is DoseCalculationMethod.UNCALCULATED

    def test_ambiguous_population_falls_back_to_adult_flag(
        self, stage_context: StageContext
    ) -> None:
        # No age, no preference -> target None; candidate.adult=True,
        # child=False -> adult fallback per §6.2.
        query = PatientQuery()
        c = make_candidate("r1", adult=True, child=False, dose=250.0, frequency=2.0)
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        assert result.state.candidates[0].dose.calculation_method is DoseCalculationMethod.FIXED

    def test_ambiguous_population_dual_flag_candidate_is_ambiguous_not_adult(
        self, stage_context: StageContext
    ) -> None:
        # No fallback exists for dual adult+child candidates when population
        # is ambiguous -- neither the adult nor the peds branch condition
        # matches, so it's POPULATION_AMBIGUOUS (see stage docstring).
        query = PatientQuery()
        c = make_candidate("r1", adult=True, child=True, dose=250.0, frequency=2.0)
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        rec = result.state.candidates[0]
        assert rec.dose.calculation_method is DoseCalculationMethod.UNCALCULATED
        assert any(f.code == "POPULATION_AMBIGUOUS" for f in rec.safety_flags)


class TestPediatricDosing:
    def test_no_pediatric_dosing_data_is_uncalculated(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(patient=Patient(age=10, weight_kg=30))
        c = make_candidate("r1", adult=False, child=True, drug_ref="amoxicillin")
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        rec = result.state.candidates[0]
        assert rec.dose.calculation_method is DoseCalculationMethod.UNCALCULATED
        assert any(f.code == "PEDS_DOSING_UNKNOWN" for f in rec.safety_flags)

    def test_weight_missing_is_uncalculated(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(age=10, weight_kg=None))
        c = make_candidate("r1", adult=False, child=True, drug_ref="peds_test_drug")
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        rec = result.state.candidates[0]
        assert rec.dose.calculation_method is DoseCalculationMethod.UNCALCULATED
        assert any(f.code == "WEIGHT_REQUIRED_FOR_PEDS" for f in rec.safety_flags)

    def test_mg_per_kg_calculation(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(age=10, weight_kg=20))
        c = make_candidate("r1", adult=False, child=True, drug_ref="peds_test_drug", frequency=3.0)
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        dose = result.state.candidates[0].dose
        assert dose.calculation_method is DoseCalculationMethod.MG_PER_KG
        # 40 mg/kg/day * 20 kg = 800 mg/day, / 3 doses = 266.67 mg
        assert dose.calculated_dose_mg == 800.0 / 3.0
        assert dose.max_daily_mg == 1500.0

    def test_max_daily_clamp(self, stage_context: StageContext) -> None:
        query = PatientQuery(patient=Patient(age=10, weight_kg=40))  # 40*40=1600 > clamp 1500
        c = make_candidate("r1", adult=False, child=True, drug_ref="peds_test_drug", frequency=3.0)
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        dose = result.state.candidates[0].dose
        assert dose.calculated_dose_mg == 1500.0 / 3.0
        assert "1500.0mg/day" in dose.adjustment_history[0]

    def test_weight_below_band_still_calculates_with_warning(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(patient=Patient(age=1, weight_kg=2))  # below weight_min_kg=3
        c = make_candidate("r1", adult=False, child=True, drug_ref="peds_test_drug", frequency=3.0)
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        rec = result.state.candidates[0]
        assert rec.dose.calculation_method is DoseCalculationMethod.MG_PER_KG
        assert any(f.code == "BELOW_WEIGHT_BAND" for f in rec.safety_flags)

    def test_weight_above_band_still_calculates_with_warning(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(patient=Patient(age=17, weight_kg=60))  # above weight_max_kg=40
        c = make_candidate("r1", adult=False, child=True, drug_ref="peds_test_drug", frequency=3.0)
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        rec = result.state.candidates[0]
        assert any(f.code == "ABOVE_WEIGHT_BAND" for f in rec.safety_flags)

    def test_frequency_none_computes_daily_but_not_single_dose(
        self, stage_context: StageContext
    ) -> None:
        query = PatientQuery(patient=Patient(age=10, weight_kg=20))
        c = make_candidate(
            "r1", adult=False, child=True, drug_ref="peds_test_drug", frequency=None
        )
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        dose = result.state.candidates[0].dose
        assert dose.calculation_method is DoseCalculationMethod.MG_PER_KG
        assert dose.calculated_dose_mg is None
        assert "800.0 mg/day" in dose.calculation_note

    def test_neonate_target_uses_peds_branch(self, stage_context: StageContext) -> None:
        query = PatientQuery(
            patient=Patient(weight_kg=3.5), preferences=Preferences(population="neonate")
        )
        c = make_candidate(
            "r1", adult=False, child=True, drug_ref="peds_test_drug", frequency=2.0
        )
        state = _state(query, c)
        result = DoseCalculation().run(state, stage_context)
        assert result.state.candidates[0].dose.calculation_method is DoseCalculationMethod.MG_PER_KG


class TestEmptyCandidates:
    def test_no_candidates_is_a_noop(self, stage_context: StageContext) -> None:
        state = PipelineState(patient=PatientQuery(patient=Patient()))
        result = DoseCalculation().run(state, stage_context)
        assert result.state.candidates == ()
