"""Milestone 6: Stage 7 — DoseAdjustment.

Per DECISIONS.md 2026-07-10: renal and hepatic adjustment data are always
unstructured free text today, so both branches only ever WARN — they never
numerically adjust and hepatic never escalates to exclusion in v1.
"""

from __future__ import annotations

from clinical_engine.models import (
    DecisionCode,
    DoseCalculationMethod,
    DoseDetail,
    Patient,
    PatientQuery,
    SafetyLevel,
)
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages.dose_adjustment import DoseAdjustment
from clinical_engine.tests.conftest import make_candidate, make_recommendation

_FIXED_DOSE = DoseDetail(
    calculated_dose_mg=500.0,
    dose_unit="mg",
    frequency_per_day=3.0,
    duration_days=5.0,
    max_daily_mg=None,
    calculation_method=DoseCalculationMethod.FIXED,
    adjustment_applied=None,
    calculation_note=None,
)

_UNCALCULATED_DOSE = DoseDetail(
    calculated_dose_mg=None,
    dose_unit="mg",
    frequency_per_day=None,
    duration_days=None,
    max_daily_mg=None,
    calculation_method=DoseCalculationMethod.UNCALCULATED,
    adjustment_applied=None,
    calculation_note=None,
)


def _state(patient: Patient, drug_ref: str | None, dose: DoseDetail) -> PipelineState:
    c = make_candidate("r1", drug_ref=drug_ref)
    rec = make_recommendation(c, dose=dose)
    return PipelineState(patient=PatientQuery(patient=patient), candidates=(rec,))


class TestSkipUncalculated:
    def test_uncalculated_dose_is_never_touched(self, stage_context: StageContext) -> None:
        state = _state(
            Patient(renal_function=20.0, hepatic_impairment=True),
            "peds_test_drug",
            _UNCALCULATED_DOSE,
        )
        result = DoseAdjustment().run(state, stage_context)
        rec = result.state.candidates[0]
        assert rec.dose is _UNCALCULATED_DOSE
        assert rec.safety_flags == ()


class TestRenalAdjustment:
    def test_renal_function_present_and_text_present_warns(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(renal_function=20.0), "peds_test_drug", _FIXED_DOSE)
        result = DoseAdjustment().run(state, stage_context)
        rec = result.state.candidates[0]
        assert any(f.code == "RENAL_ADJ_UNPARSED" for f in rec.safety_flags)
        assert any(t.decision_code is DecisionCode.RENAL for t in result.state.traces)
        # Dose value itself is never modified in v1 (no structured data to act on).
        assert rec.dose.calculated_dose_mg == 500.0

    def test_renal_function_none_skips_check(self, stage_context: StageContext) -> None:
        state = _state(Patient(renal_function=None), "peds_test_drug", _FIXED_DOSE)
        result = DoseAdjustment().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()

    def test_no_renal_data_for_drug_is_silent(self, stage_context: StageContext) -> None:
        # doxycycline fixture has renal_adjustment=null -> nothing to warn about.
        state = _state(Patient(renal_function=20.0), "doxycycline", _FIXED_DOSE)
        result = DoseAdjustment().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()


class TestHepaticAdjustment:
    def test_hepatic_impairment_no_data_warns(self, stage_context: StageContext) -> None:
        state = _state(Patient(hepatic_impairment=True), "amoxicillin", _FIXED_DOSE)
        result = DoseAdjustment().run(state, stage_context)
        rec = result.state.candidates[0]
        assert any(f.code == "HEPATIC_NO_DATA" for f in rec.safety_flags)

    def test_hepatic_impairment_with_text_warns_never_excludes(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(hepatic_impairment=True), "peds_test_drug", _FIXED_DOSE)
        result = DoseAdjustment().run(state, stage_context)
        assert len(result.state.candidates) == 1  # never excluded, per DECISIONS.md
        assert result.state.excluded == ()
        rec = result.state.candidates[0]
        flags = rec.safety_flags
        assert any(f.code == "HEPATIC_ADJ_UNPARSED" and f.level is SafetyLevel.WARNING for f in flags)
        assert any(t.decision_code is DecisionCode.HEPATIC for t in result.state.traces)

    def test_no_hepatic_impairment_skips_check(self, stage_context: StageContext) -> None:
        state = _state(Patient(hepatic_impairment=False), "peds_test_drug", _FIXED_DOSE)
        result = DoseAdjustment().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()


class TestBothRenalAndHepatic:
    def test_both_flags_can_accumulate(self, stage_context: StageContext) -> None:
        state = _state(
            Patient(renal_function=20.0, hepatic_impairment=True), "peds_test_drug", _FIXED_DOSE
        )
        result = DoseAdjustment().run(state, stage_context)
        codes = {f.code for f in result.state.candidates[0].safety_flags}
        assert "RENAL_ADJ_UNPARSED" in codes
        assert "HEPATIC_ADJ_UNPARSED" in codes
        assert "RENAL_HEPATIC_DUAL" not in codes  # not implemented, no reachable case in v1


class TestUnresolvedDrugRef:
    def test_no_drug_info_skips_renal_but_hepatic_still_warns_no_data(
        self, stage_context: StageContext
    ) -> None:
        # §6.3: renal_data is None -> silent no-op (no warning at all).
        # hepatic_text is None (including "no drug_info at all") -> WARNING
        # HEPATIC_NO_DATA. This asymmetry is in the spec itself, not a bug.
        state = _state(
            Patient(renal_function=20.0, hepatic_impairment=True), None, _FIXED_DOSE
        )
        result = DoseAdjustment().run(state, stage_context)
        flags = result.state.candidates[0].safety_flags
        codes = {f.code for f in flags}
        assert codes == {"HEPATIC_NO_DATA"}


class TestEmptyCandidates:
    def test_no_candidates_is_a_noop(self, stage_context: StageContext) -> None:
        state = PipelineState(patient=PatientQuery(patient=Patient()))
        result = DoseAdjustment().run(state, stage_context)
        assert result.state.candidates == ()
