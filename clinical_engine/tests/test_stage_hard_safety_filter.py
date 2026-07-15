"""Milestone 5: Stage 5 — HardSafetyFilter.

Edge cases per spec §6.1: drug_ref not found -> WARNING not exclude;
age unknown -> WARNING; pregnancy UNKNOWN/CAUTION -> WARNING not exclude;
CI text present but unstructured -> WARNING; allergies empty -> skip check.
"""

from __future__ import annotations

from clinical_engine.models import DecisionCode, Patient, PatientQuery, SafetyLevel
from clinical_engine.pipeline import PipelineState, StageContext
from clinical_engine.stages.hard_safety_filter import HardSafetyFilter
from clinical_engine.tests.conftest import make_candidate, make_recommendation


def _state(patient: Patient, *drug_refs_or_candidates) -> PipelineState:
    recs = []
    for i, item in enumerate(drug_refs_or_candidates):
        if isinstance(item, str) or item is None:
            recs.append(make_recommendation(make_candidate(f"r{i}", drug_ref=item)))
        else:
            recs.append(make_recommendation(item))
    return PipelineState(patient=PatientQuery(patient=patient), candidates=tuple(recs))


class TestAllergyCheck:
    def test_matching_class_allergy_excludes(self, stage_context: StageContext) -> None:
        state = _state(Patient(allergies=("Пенициллины",)), "amoxicillin")
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates == ()
        assert len(result.state.excluded) == 1
        rec, reason = result.state.excluded[0]
        assert "allergy" in reason
        assert rec.safety_flags[0].level is SafetyLevel.ABSOLUTE_CONTRAINDICATION
        assert rec.safety_flags[0].code == "ALLERGY"
        assert any(t.decision_code is DecisionCode.ALLERGY for t in result.state.traces)

    def test_non_matching_class_allergy_keeps_candidate(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(allergies=("Тетрациклины",)), "amoxicillin")
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        assert result.state.excluded == ()

    def test_no_allergies_skips_check(self, stage_context: StageContext) -> None:
        state = _state(Patient(), "amoxicillin")
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        assert result.state.candidates[0].safety_flags == ()

    def test_allergy_match_is_case_insensitive(self, stage_context: StageContext) -> None:
        # Audit fix M1: patient states allergy in lowercase; map has
        # "Пенициллины" — must still exclude.
        state = _state(Patient(allergies=("пенициллины",)), "amoxicillin")
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates == ()
        assert len(result.state.excluded) == 1

    def test_unresolvable_class_with_allergy_warns_not_silent(
        self, stage_context: StageContext
    ) -> None:
        # Audit fix M1: ci_test_drug exists in drugs_reference but its class
        # is not in allergy_class_map -> class unknown. With a stated allergy,
        # emit ALLERGY_UNVERIFIABLE (Unknown != Safe), never a silent include.
        state = _state(Patient(allergies=("Пенициллины",)), "ci_test_drug")
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1  # not excluded — can't verify
        flags = result.state.candidates[0].safety_flags
        assert any(f.code == "ALLERGY_UNVERIFIABLE" for f in flags)
        assert any(f.requires_physician_acknowledgement for f in flags)

    def test_unresolvable_class_without_allergy_is_silent(
        self, stage_context: StageContext
    ) -> None:
        # No stated allergy -> nothing to verify -> no ALLERGY_UNVERIFIABLE noise.
        state = _state(Patient(), "ci_test_drug")
        result = HardSafetyFilter().run(state, stage_context)
        codes = {f.code for f in result.state.candidates[0].safety_flags}
        assert "ALLERGY_UNVERIFIABLE" not in codes


class TestPregnancyCheck:
    def test_prohibited_excludes(self, stage_context: StageContext) -> None:
        state = _state(Patient(pregnant=True), "doxycycline")
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates == ()
        rec, reason = result.state.excluded[0]
        assert "pregnancy" in reason
        assert rec.safety_flags[0].code == "PREGNANCY_CI"

    def test_caution_does_not_exclude_but_warns(self, stage_context: StageContext) -> None:
        state = _state(Patient(pregnant=True), "levofloxacin")  # trimester-conditional -> CAUTION
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        flags = result.state.candidates[0].safety_flags
        assert any(f.code == "PREGNANCY_CAUTION" and f.level is SafetyLevel.WARNING for f in flags)

    def test_unknown_does_not_exclude_but_warns(self, stage_context: StageContext) -> None:
        state = _state(Patient(pregnant=True), "unmapped_drug")  # pregnancy_category=null -> UNKNOWN
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        flags = result.state.candidates[0].safety_flags
        assert any(f.code == "PREGNANCY_UNKNOWN" for f in flags)

    def test_allowed_no_flag(self, stage_context: StageContext) -> None:
        state = _state(Patient(pregnant=True), "amoxicillin")  # ALLOWED
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()

    def test_not_pregnant_skips_check_even_for_prohibited_drug(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(pregnant=False), "doxycycline")
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        assert result.state.excluded == ()


class TestAgeCheck:
    def test_below_minimum_excludes(self, stage_context: StageContext) -> None:
        state = _state(Patient(age=5), "doxycycline")  # min "8 лет"
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates == ()
        rec, reason = result.state.excluded[0]
        assert "age" in reason
        assert rec.safety_flags[0].code == "AGE_BELOW_MIN"
        assert any(t.decision_code is DecisionCode.AGE for t in result.state.traces)

    def test_above_minimum_is_kept(self, stage_context: StageContext) -> None:
        state = _state(Patient(age=10), "doxycycline")
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        assert result.state.excluded == ()

    def test_age_unknown_with_restriction_present_warns(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(age=None), "doxycycline")  # has age_restriction_min
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        flags = result.state.candidates[0].safety_flags
        assert any(f.code == "AGE_UNKNOWN" for f in flags)

    def test_age_unknown_without_restriction_is_silent(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(age=None), "amoxicillin")  # no age_restriction_min
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()


class TestContraindicationsCheck:
    def test_unstructured_text_warns_never_excludes(self, stage_context: StageContext) -> None:
        state = _state(Patient(), "ci_test_drug")
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1  # never excluded, per Invariant #13
        flags = result.state.candidates[0].safety_flags
        assert any(f.code == "CI_UNPARSED" and f.level is SafetyLevel.WARNING for f in flags)

    def test_absent_contraindications_is_silent(self, stage_context: StageContext) -> None:
        state = _state(Patient(), "amoxicillin")  # contraindications=None
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates[0].safety_flags == ()


class TestDrugRefUnresolved:
    def test_none_drug_ref_warns_and_skips_all_checks(
        self, stage_context: StageContext
    ) -> None:
        state = _state(
            Patient(allergies=("Пенициллины",), pregnant=True, age=1), None
        )
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1  # never excluded on missing data
        flags = result.state.candidates[0].safety_flags
        assert len(flags) == 1
        assert flags[0].code == "DRUG_UNKNOWN"
        assert any(t.decision_code is DecisionCode.NO_MATCH for t in result.state.traces)

    def test_unresolved_key_not_in_reference_same_as_none(
        self, stage_context: StageContext
    ) -> None:
        state = _state(Patient(), "totally_unindexed_drug_ref")
        result = HardSafetyFilter().run(state, stage_context)
        assert len(result.state.candidates) == 1
        assert result.state.candidates[0].safety_flags[0].code == "DRUG_UNKNOWN"


class TestInvariantsHere:
    def test_excluded_only_grows_and_never_reappears_in_candidates(
        self, stage_context: StageContext
    ) -> None:
        state = _state(
            Patient(allergies=("Пенициллины",), age=45), "amoxicillin", "gentamicin"
        )
        result = HardSafetyFilter().run(state, stage_context)
        excluded_ids = {rec.candidate.regimen_id for rec, _ in result.state.excluded}
        candidate_ids = {rec.candidate.regimen_id for rec in result.state.candidates}
        assert excluded_ids.isdisjoint(candidate_ids)
        assert len(excluded_ids) == 1  # only amoxicillin (allergy)

    def test_multiple_flags_can_accumulate_on_one_candidate(
        self, stage_context: StageContext
    ) -> None:
        # pregnant + age unknown + drug has age restriction -> AGE_UNKNOWN,
        # plus CAUTION pregnancy on the same surviving candidate.
        state = _state(Patient(pregnant=True, age=None), "levofloxacin")
        result = HardSafetyFilter().run(state, stage_context)
        flags = result.state.candidates[0].safety_flags
        codes = {f.code for f in flags}
        assert "PREGNANCY_CAUTION" in codes
        assert "AGE_UNKNOWN" in codes

    def test_empty_candidates_is_a_noop(self, stage_context: StageContext) -> None:
        state = PipelineState(patient=PatientQuery(patient=Patient()))
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates == ()
        assert result.state.excluded == ()
