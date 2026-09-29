"""Milestone 6: Stage 7 — DoseAdjustment.

Per DECISIONS.md 2026-07-10: renal and hepatic adjustment data are always
unstructured free text today, so both branches only ever WARN — they never
numerically adjust and hepatic never escalates to exclusion in v1.
"""

from __future__ import annotations

import pytest

from clinical_engine.models import (
    DecisionCode,
    DoseCalculationMethod,
    DoseDetail,
    Patient,
    PatientQuery,
    RecommendationOutcome,
    SafetyAction,
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


class TestUncalculatedIsUntouched:
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


# ── C-2 / H-5: an unapplied adjustment must not masquerade as a dose ──────


class TestDoseIsNotPatientSpecific:
    def test_renal_unparsed_marks_the_dose_not_patient_specific(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(renal_function=12.0), "peds_test_drug", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, stage_context).state.candidates[0]
        assert rec.dose.calculated_dose_mg == 500.0  # degraded: number still shown
        assert rec.dose.dose_is_patient_specific is False
        assert "renal_adjustment_unparsed" in rec.dose.adjustment_history[-1]
        assert "NOT patient-specific" in rec.dose.calculation_note
        assert rec.dose.adjustment_applied.startswith("none applied")

    def test_hepatic_unparsed_marks_the_dose_not_patient_specific(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(hepatic_impairment=True), "peds_test_drug", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, stage_context).state.candidates[0]
        assert rec.dose.dose_is_patient_specific is False
        assert "hepatic_adjustment_unparsed" in rec.dose.adjustment_history[-1]

    def test_healthy_patient_keeps_the_dose_patient_specific(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(age=45), "peds_test_drug", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, stage_context).state.candidates[0]
        assert rec.dose is _FIXED_DOSE  # untouched: nothing to apply
        assert rec.dose.dose_is_patient_specific is True
        assert rec.safety_flags == ()

    def test_hepatic_no_data_is_missing_data_not_an_unapplied_adjustment(
        self, stage_context: StageContext
    ) -> None:
        """Invariant #11: absent guidance is a WARNING, not a failed adjustment.
        Marking such a dose non-specific would make every hepatic patient's
        dose look unsafe, which is the opposite of the degraded-mode contract."""
        state = _state(Patient(hepatic_impairment=True), "amoxicillin", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, stage_context).state.candidates[0]
        assert any(f.code == "HEPATIC_NO_DATA" for f in rec.safety_flags)
        assert rec.dose.dose_is_patient_specific is True


class TestHepaticEscalation:
    """H-5: hepatic impairment could only ever produce MONITOR_CLOSELY, i.e. a
    purely advisory flag next to a full unadjusted dose."""

    def test_caution_text_escalates_the_action(self, stage_context: StageContext) -> None:
        state = _state(Patient(hepatic_impairment=True), "peds_test_drug", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, stage_context).state.candidates[0]
        flag = [f for f in rec.safety_flags if f.code == "HEPATIC_ADJ_UNPARSED"][0]
        assert flag.action is SafetyAction.AVOID_IF_POSSIBLE
        assert flag.requires_physician_acknowledgement is True
        # Still never an exclusion: the text says "при печёночной
        # недостаточности" and Patient carries only a boolean, so the severity
        # is unknown and an absolute exclusion cannot be justified.
        assert rec.outcome is not RecommendationOutcome.EXCLUDED

    def test_source_level_drives_the_escalation(self, make_drug_reference_context) -> None:
        """A source text stating a contraindication is at least as loud as one
        stating caution — both must be acknowledged, neither is routine."""
        ctx = make_drug_reference_context(
            {
                "hep_ban": {
                    "inn": "ГепаБан", "class": "Тестовый класс",
                    "renal_adjustment": None,
                    "hepatic_adjustment": "Противопоказан при тяжёлой печёночной недостаточности",
                    "pregnancy_category": None, "age_restriction_min": None,
                },
                "hep_quiet": {
                    "inn": "ГепаТихий", "class": "Тестовый класс",
                    "renal_adjustment": None,
                    "hepatic_adjustment": "информационный текст без указаний",
                    "pregnancy_category": None, "age_restriction_min": None,
                },
            }
        )
        for ref, expected_action in (
            ("hep_ban", SafetyAction.AVOID_IF_POSSIBLE),
            ("hep_quiet", SafetyAction.MONITOR_CLOSELY),
        ):
            state = _state(Patient(hepatic_impairment=True), ref, _FIXED_DOSE)
            rec = DoseAdjustment().run(state, ctx).state.candidates[0]
            flag = [f for f in rec.safety_flags if f.code == "HEPATIC_ADJ_UNPARSED"][0]
            assert flag.action is expected_action, ref
            assert rec.dose.dose_is_patient_specific is False, ref


class TestNoAdjustmentSentinels:
    """L-3: the sentinel was an exact string, so 'Не требуется.', 'НЕ ТРЕБУЕТСЯ'
    and 'Не требуется при ХБП' all raised a spurious RENAL_ADJ_UNPARSED."""

    @pytest.mark.parametrize(
        "text",
        ["Не требуется", "не требуется.", "НЕ ТРЕБУЕТСЯ", "Не требуется при ХБП",
         "  не требуется  ", "not required", "Not required."],
    )
    def test_no_adjustment_phrasings_raise_nothing(self, text, make_drug_reference_context) -> None:
        ctx = make_drug_reference_context(
            {
                "quiet_drug": {
                    "inn": "Тихий", "class": "Тестовый класс",
                    "renal_adjustment": text, "hepatic_adjustment": None,
                    "pregnancy_category": None, "age_restriction_min": None,
                }
            }
        )
        state = _state(Patient(renal_function=12.0), "quiet_drug", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, ctx).state.candidates[0]
        assert rec.safety_flags == ()
        assert rec.dose.dose_is_patient_specific is True

    def test_real_adjustment_text_still_flags(self, make_drug_reference_context) -> None:
        ctx = make_drug_reference_context(
            {
                "loud_drug": {
                    "inn": "Громкий", "class": "Тестовый класс",
                    "renal_adjustment": "СКФ<30: коррекция дозы", "hepatic_adjustment": None,
                    "pregnancy_category": None, "age_restriction_min": None,
                }
            }
        )
        state = _state(Patient(renal_function=12.0), "loud_drug", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, ctx).state.candidates[0]
        assert any(f.code == "RENAL_ADJ_UNPARSED" for f in rec.safety_flags)

    def test_same_sentinel_applies_to_the_hepatic_field(
        self, make_drug_reference_context
    ) -> None:
        ctx = make_drug_reference_context(
            {
                "quiet_liver": {
                    "inn": "ТихаяПечень", "class": "Тестовый класс",
                    "renal_adjustment": None, "hepatic_adjustment": "Не требуется.",
                    "pregnancy_category": None, "age_restriction_min": None,
                }
            }
        )
        state = _state(Patient(hepatic_impairment=True), "quiet_liver", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, ctx).state.candidates[0]
        assert rec.safety_flags == ()
        assert rec.dose.dose_is_patient_specific is True


class TestRenalFunctionInputShape:
    """L-4: api/contract.py declares renal_function as str and assigns it
    straight into Patient."""

    def test_numeric_string_is_accepted(self, stage_context: StageContext) -> None:
        state = _state(Patient(renal_function="12"), "peds_test_drug", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, stage_context).state.candidates[0]
        assert any(f.code == "RENAL_ADJ_UNPARSED" for f in rec.safety_flags)
        assert not any(f.code == "RENAL_DATA_UNPARSEABLE" for f in rec.safety_flags)

    def test_string_with_unit_is_accepted(self, stage_context: StageContext) -> None:
        assert Patient(renal_function="СКФ 30 мл/мин").gfr_ml_min == 30.0
        assert Patient(renal_function="eGFR 45").gfr_ml_min == 45.0
        assert Patient(renal_function="12,5").gfr_ml_min == 12.5

    def test_unusable_value_degrades_loudly_never_silently(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(renal_function="норма"), "peds_test_drug", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, stage_context).state.candidates[0]
        codes = {f.code for f in rec.safety_flags}
        assert "RENAL_DATA_UNPARSEABLE" in codes
        assert "RENAL_ADJ_UNPARSED" not in codes  # nothing was evaluated
        flag = [f for f in rec.safety_flags if f.code == "RENAL_DATA_UNPARSEABLE"][0]
        assert flag.action is SafetyAction.AVOID_IF_POSSIBLE
        assert flag.requires_physician_acknowledgement is True
        assert rec.dose.dose_is_patient_specific is False


class TestVerifiedProductionScenarios:
    """H-5 / C-2 / L-3: the concrete cases from the bug report, against the
    shipped db/index.json rather than the small test fixture."""

    def test_hepatic_impairment_on_doxycycline_is_not_merely_advisory(
        self, production_context: StageContext
    ) -> None:
        # db/index.json: doxycycline.hepatic_adjustment =
        # "С осторожностью при печёночной недостаточности"
        state = _state(Patient(age=44, hepatic_impairment=True), "doxycycline", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, production_context).state.candidates[0]
        assert rec.dose.calculated_dose_mg == 500.0  # never escalated to exclusion
        flag = [f for f in rec.safety_flags if f.code == "HEPATIC_ADJ_UNPARSED"][0]
        assert flag.level is SafetyLevel.WARNING
        assert flag.action is SafetyAction.AVOID_IF_POSSIBLE
        assert flag.requires_physician_acknowledgement is True
        assert rec.dose.dose_is_patient_specific is False

    def test_metronidazole_hepatic_caution_too(self, production_context: StageContext) -> None:
        state = _state(Patient(age=44, hepatic_impairment=True), "metronidazole", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, production_context).state.candidates[0]
        flag = [f for f in rec.safety_flags if f.code == "HEPATIC_ADJ_UNPARSED"][0]
        assert flag.action is SafetyAction.AVOID_IF_POSSIBLE
        assert rec.dose.dose_is_patient_specific is False

    def test_renal_function_low_on_amoxicillin_is_not_patient_specific(
        self, production_context: StageContext
    ) -> None:
        # The C-2 scenario: GFR 12 on a drug that carries renal guidance.
        state = _state(Patient(age=62, renal_function=12.0), "amoxicillin", _FIXED_DOSE)
        rec = DoseAdjustment().run(state, production_context).state.candidates[0]
        assert any(f.code == "RENAL_ADJ_UNPARSED" for f in rec.safety_flags)
        assert rec.dose.dose_is_patient_specific is False

    def test_production_no_adjustment_drug_raises_no_flag(
        self, production_context: StageContext
    ) -> None:
        """L-3: db/index.json has 5 drugs whose renal text is exactly
        "Не требуется" — they must not raise RENAL_ADJ_UNPARSED."""
        import json
        from pathlib import Path

        doc = json.loads(Path("db/index.json").read_text(encoding="utf-8"))["drugs_reference"]
        quiet = [k for k, v in doc.items()
                 if not k.startswith("_") and v.get("renal_adjustment") == "Не требуется"]
        assert quiet, "expected 'Не требуется' drugs in db/index.json"
        for ref in quiet:
            state = _state(Patient(renal_function=12.0), ref, _FIXED_DOSE)
            rec = DoseAdjustment().run(state, production_context).state.candidates[0]
            assert rec.safety_flags == (), ref
            assert rec.dose.dose_is_patient_specific is True, ref

    def test_renal_contraindication_text_is_escalated(
        self, production_context: StageContext
    ) -> None:
        """Some db/index.json drugs state "Противопоказан при СКФ<30" — the
        load-time level is PROHIBITED, so the flag must be acknowledged."""
        import json
        from pathlib import Path

        doc = json.loads(Path("db/index.json").read_text(encoding="utf-8"))["drugs_reference"]
        banned = [k for k, v in doc.items()
                  if not k.startswith("_")
                  and isinstance(v.get("renal_adjustment"), str)
                  and "противопоказан" in v["renal_adjustment"].lower()]
        assert banned, "expected renal contraindication text in db/index.json"
        for ref in banned:
            state = _state(Patient(renal_function=12.0), ref, _FIXED_DOSE)
            rec = DoseAdjustment().run(state, production_context).state.candidates[0]
            flag = [f for f in rec.safety_flags if f.code == "RENAL_ADJ_UNPARSED"][0]
            assert flag.action is SafetyAction.AVOID_IF_POSSIBLE, ref
            assert flag.requires_physician_acknowledgement is True, ref
            assert rec.dose.dose_is_patient_specific is False, ref
