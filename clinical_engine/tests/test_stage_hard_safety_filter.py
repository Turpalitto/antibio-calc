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
        self, make_drug_reference_context
    ) -> None:
        """A drug whose class matches no curated family is still unverifiable:
        Unknown != Safe, so it is flagged and requires acknowledgement."""
        ctx = make_drug_reference_context(
            {
                "mystery_drug": {
                    "inn": "Мистери Драг", "class": "неизвестная фармакологическая группа",
                    "renal_adjustment": None, "hepatic_adjustment": None,
                    "pregnancy_category": None, "age_restriction_min": None,
                }
            }
        )
        state = _state(Patient(allergies=("Пенициллины",)), "mystery_drug")
        result = HardSafetyFilter().run(state, ctx)
        assert len(result.state.candidates) == 1  # not excluded — can't verify
        flags = result.state.candidates[0].safety_flags
        assert any(f.code == "ALLERGY_UNVERIFIABLE" for f in flags)
        assert any(f.requires_physician_acknowledgement for f in flags)

    def test_class_resolved_from_the_drug_own_label(
        self, make_drug_reference_context
    ) -> None:
        """M-4: a drug absent from allergy_class_map is still classified, via
        the curated family vocabulary matched against its own class label."""
        ctx = make_drug_reference_context(
            {
                "tobramycin_like": {
                    "inn": "Тобрамицин", "class": "Аминогликозиды",
                    "renal_adjustment": None, "hepatic_adjustment": None,
                    "pregnancy_category": None, "age_restriction_min": None,
                }
            }
        )
        state = _state(Patient(allergies=("Аминогликозиды",)), "tobramycin_like")
        result = HardSafetyFilter().run(state, ctx)
        assert result.state.candidates == ()
        rec, reason = result.state.excluded[0]
        assert "allergy" in reason and "Аминогликозиды" in reason
        assert rec.safety_flags[0].code == "ALLERGY"
        assert any("drug_class_label" in t.reason for t in result.state.traces)

    def test_detailed_class_label_matches_the_stated_family(
        self, make_drug_reference_context
    ) -> None:
        """A physician may state either the family or the detailed label; both
        must compare equal to the same family."""
        ctx = make_drug_reference_context(
            {
                "pen_like": {
                    "inn": "Пен_like", "class": "Полусинтетические пенициллины широкого спектра",
                    "renal_adjustment": None, "hepatic_adjustment": None,
                    "pregnancy_category": None, "age_restriction_min": None,
                }
            }
        )
        for stated in ("Пенициллины", "пенициллины", "Полусинтетические пенициллины широкого спектра"):
            state = _state(Patient(allergies=(stated,)), "pen_like")
            result = HardSafetyFilter().run(state, ctx)
            assert result.state.candidates == (), stated

    def test_penicillin_allergy_warns_on_cephalosporin_but_does_not_exclude(
        self, make_ceph_context
    ) -> None:
        """M-4: documented penicillin <-> cephalosporin cross-reactivity. A
        WARNING (avoid if possible, acknowledge), never an exclusion."""
        ctx = make_ceph_context(
            {
                "cefixime": {
                    "inn": "Цефиксим", "class": "Цефалоспорины III поколения (per os)",
                    "renal_adjustment": None, "hepatic_adjustment": None,
                    "pregnancy_category": None, "age_restriction_min": None,
                }
            }
        )
        state = _state(Patient(allergies=("Пенициллины",)), "cefixime")
        result = HardSafetyFilter().run(state, ctx)
        assert len(result.state.candidates) == 1
        assert result.state.excluded == ()
        flags = result.state.candidates[0].safety_flags
        cross = [f for f in flags if f.code == "ALLERGY_CROSS_REACTIVITY"]
        assert len(cross) == 1
        assert cross[0].level is SafetyLevel.WARNING
        assert cross[0].requires_physician_acknowledgement
        assert any("cross-react" in t.reason for t in result.state.traces)

    def test_unrelated_family_raises_no_cross_reactivity_flag(
        self, make_ceph_context
    ) -> None:
        ctx = make_ceph_context(
            {
                "cefixime": {
                    "inn": "Цефиксим", "class": "Цефалоспорины III поколения (per os)",
                    "renal_adjustment": None, "hepatic_adjustment": None,
                    "pregnancy_category": None, "age_restriction_min": None,
                }
            }
        )
        state = _state(Patient(allergies=("Тетрациклины",)), "cefixime")
        result = HardSafetyFilter().run(state, ctx)
        codes = {f.code for f in result.state.candidates[0].safety_flags}
        assert codes == set()

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

    def test_trimester_conditional_contraindication_excludes(
        self, stage_context: StageContext
    ) -> None:
        """C-1: "Противопоказан в I и III триместрах" is a contraindication and
        must exclude. It used to be downgraded to CAUTION, which does not."""
        state = _state(Patient(pregnant=True), "levofloxacin")
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates == ()
        rec, reason = result.state.excluded[0]
        assert "pregnancy" in reason
        assert rec.safety_flags[0].code == "PREGNANCY_CI"
        # The verbatim source text travels with the flag, so the physician sees
        # the trimester conditionality rather than an opaque category.
        assert "триместрах" in rec.safety_flags[0].message

    def test_caution_does_not_exclude_but_warns(
        self, make_drug_reference_context
    ) -> None:
        ctx = make_drug_reference_context(
            {
                "gent_like": {
                    "inn": "Гента_лайк", "class": "Аминогликозиды",
                    "renal_adjustment": None, "hepatic_adjustment": None,
                    "pregnancy_category": "С осторожностью (риск ототоксичности у плода)",
                    "age_restriction_min": None,
                }
            }
        )
        state = _state(Patient(pregnant=True), "gent_like")
        result = HardSafetyFilter().run(state, ctx)
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


def _stage_diagnosis_provider():
    from clinical_engine.readers.diagnosis_reader import JsonDiagnosisProvider
    from clinical_engine.tests.conftest import FIXTURES_DIR

    return JsonDiagnosisProvider(FIXTURES_DIR / "test_diagnosis_index.json")


class TestProductionAllergyClassCoverage:
    """M-4: 7 drugs in db/index.json (tobramycin, netilmicin, ofloxacin,
    tetracycline, tinidazole, rifaximin, furazidin) appear in NEITHER
    allergy_class_map NOR allergy_class_hierarchy, so every allergic patient
    got ALLERGY_UNVERIFIABLE for them."""

    def _production_resolver(self):
        import json
        from pathlib import Path

        from clinical_engine.engine import _load_clinical_constants

        constants_path = Path("clinical_engine/resources/clinical_constants.json")
        index_path = Path("db/index.json")
        if not constants_path.exists() or not index_path.exists():
            pytest.skip("production clinical_constants.json / db/index.json not present")
        return _load_clinical_constants(constants_path), json.loads(
            index_path.read_text(encoding="utf-8")
        )["drugs_reference"]

    def test_every_production_drug_resolves_to_a_class(self) -> None:
        from clinical_engine.terminology import AllergyClassResolver

        constants, drugs_reference = self._production_resolver()
        resolver = AllergyClassResolver(constants)
        unresolved = []
        for ref, entry in drugs_reference.items():
            if ref.startswith("_") or not isinstance(entry, dict):
                continue
            resolution = resolver.resolve(ref, entry.get("class"))
            if resolution.class_name is None:
                unresolved.append(ref)
        assert unresolved == [], f"drugs with no resolvable allergy class: {unresolved}"

    def test_documented_gap_drugs_are_now_classified(self) -> None:
        from clinical_engine.terminology import AllergyClassResolver

        constants, drugs_reference = self._production_resolver()
        resolver = AllergyClassResolver(constants)
        expected = {
            "tobramycin": "Аминогликозиды",
            "netilmicin": "Аминогликозиды",
            "ofloxacin": "Фторхинолоны",
            "tetracycline": "Тетрациклины",
            "tinidazole": "Нитроимидазолы",       # 5-nitroimidazoles, as metronidazole
            "furazidin": "Нитрофураны",
        }
        for ref, family in expected.items():
            resolution = resolver.resolve(ref, drugs_reference[ref].get("class"))
            assert resolution.class_name == family, (ref, resolution)

    def test_allergic_patient_gets_no_unverifiable_flag_in_production(
        self, sqlite_path: Path
    ) -> None:
        import json
        from pathlib import Path

        from clinical_engine.config import EngineConfig
        from clinical_engine.engine import _load_clinical_constants
        from clinical_engine.pipeline import ScoreWeights, StageContext
        from clinical_engine.readers.drug_reference_reader import (
            DrugReferenceReader,
            DrugSafetyProviderAdapter,
        )
        from clinical_engine.readers.sqlite_reader import RegimenProviderAdapter, SQLiteReader
        from clinical_engine.terminology import BasicTerminologyProvider

        constants_path = Path("clinical_engine/resources/clinical_constants.json")
        index_path = Path("db/index.json")
        if not constants_path.exists() or not index_path.exists():
            pytest.skip("production constants / db/index.json not present")
        constants = _load_clinical_constants(constants_path)
        reader = DrugReferenceReader(index_path)
        sqlite_reader = SQLiteReader(sqlite_path)
        try:
            ctx = StageContext(
                config=EngineConfig(
                    sqlite_path=str(sqlite_path),
                    clinical_constants_path=str(constants_path),
                    drug_reference_path=str(index_path),
                ),
                sqlite_reader=sqlite_reader,
                drug_ref_reader=reader,
                diagnosis_provider=_stage_diagnosis_provider(),
                regimen_provider=RegimenProviderAdapter(sqlite_reader),
                drug_safety_provider=DrugSafetyProviderAdapter(reader),
                terminology_provider=BasicTerminologyProvider(constants),
                constants=constants,
                score_weights=ScoreWeights(),
            )
            drugs = [k for k, v in json.loads(index_path.read_text(encoding="utf-8"))[
                "drugs_reference"
            ].items() if not k.startswith("_")]
            state = PipelineState(
                patient=PatientQuery(patient=Patient(allergies=("Пенициллины",))),
                candidates=tuple(
                    make_recommendation(make_candidate(f"r{i}", drug_ref=ref))
                    for i, ref in enumerate(drugs)
                ),
            )
            result = HardSafetyFilter().run(state, ctx)
        finally:
            sqlite_reader.close()
        codes = {f.code for rec in result.state.candidates for f in rec.safety_flags}
        assert "ALLERGY_UNVERIFIABLE" not in codes
        # Sanity: the beta-lactams really were excluded, so the resolver is
        # doing work rather than everything being accepted.
        excluded = {
            rec.candidate.drug_ref for rec, _ in result.state.excluded
        }
        assert "amoxicillin" in excluded
        assert "amoxiclav" in excluded

class TestVerifiedProductionScenarios:
    """The exact scenarios from the bug report, against the shipped
    db/index.json + clinical_constants.json."""

    def test_c1_pregnant_patient_excludes_a_trimester_teratogen(
        self, production_context: StageContext
    ) -> None:
        """db/index.json drugs whose text is "Противопоказан ... триместр" were
        downgraded to CAUTION, and CAUTION does not exclude."""
        import json
        from pathlib import Path

        doc = json.loads(Path("db/index.json").read_text(encoding="utf-8"))["drugs_reference"]
        teratogens = [
            k for k, v in doc.items()
            if not k.startswith("_")
            and isinstance(v.get("pregnancy_category"), str)
            and v["pregnancy_category"].strip().lower().startswith("противопоказан")
            and "триместр" in v["pregnancy_category"].lower()
        ]
        assert len(teratogens) == 2, teratogens
        for ref in teratogens:
            state = _state(Patient(pregnant=True), ref)
            result = HardSafetyFilter().run(state, production_context)
            assert result.state.candidates == (), ref
            rec, reason = result.state.excluded[0]
            assert reason == "pregnancy: prohibited", ref
            assert rec.safety_flags[0].code == "PREGNANCY_CI", ref
            assert "триместр" in rec.safety_flags[0].message, ref

    def test_m4_drug_missing_from_the_class_map_is_still_excluded(
        self, production_context: StageContext
    ) -> None:
        """tobramycin is absent from allergy_class_map; it used to produce
        ALLERGY_UNVERIFIABLE for every allergic patient."""
        state = _state(Patient(allergies=("Аминогликозиды",)), "tobramycin", "amikacin")
        result = HardSafetyFilter().run(state, production_context)
        excluded = {rec.candidate.drug_ref for rec, _ in result.state.excluded}
        assert excluded == {"tobramycin", "amikacin"}
        codes = {f.code for rec in result.state.candidates for f in rec.safety_flags}
        assert "ALLERGY_UNVERIFIABLE" not in codes

    def test_m4_tinidazole_alias_resolves_to_the_nitroimidazole_family(
        self, production_context: StageContext
    ) -> None:
        """tinidazole is "Производные имидазола" in db/index.json and in
        NEITHER curated source; metronidazole is a nitroimidazole."""
        state = _state(Patient(allergies=("Нитроимидазолы",)), "tinidazole", "metronidazole")
        result = HardSafetyFilter().run(state, production_context)
        excluded = {rec.candidate.drug_ref for rec, _ in result.state.excluded}
        assert excluded == {"tinidazole", "metronidazole"}

    def test_m4_penicillin_allergy_on_a_cephalosporin_warns(
        self, production_context: StageContext
    ) -> None:
        state = _state(Patient(allergies=("Пенициллины",)), "cefixime")
        result = HardSafetyFilter().run(state, production_context)
        assert len(result.state.candidates) == 1
        assert result.state.excluded == ()
        assert any(
            f.code == "ALLERGY_CROSS_REACTIVITY" for f in result.state.candidates[0].safety_flags
        )

    def test_m4_unmapped_study_drug_against_a_penicillin_allergy(
        self, production_context: StageContext
    ) -> None:
        """The class label is the detailed family, the physician states the
        family: both must resolve to the same class."""
        state = _state(Patient(allergies=("Пенициллины",)), "oxacillin")
        result = HardSafetyFilter().run(state, production_context)
        assert result.state.candidates == ()


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
        self, make_drug_reference_context
    ) -> None:
        # Allergy that cannot be verified (ALLERGY_UNVERIFIABLE) plus an
        # unclassified pregnancy category (PREGNANCY_UNKNOWN) on the same
        # surviving candidate. C-1 moved levofloxacin out of this test: it is a
        # trimester-conditional CONTRAINDICATION and is now excluded.
        ctx = make_drug_reference_context(
            {
                "mystery_drug": {
                    "inn": "Мистери Драг", "class": "неизвестная фармакологическая группа",
                    "renal_adjustment": None, "hepatic_adjustment": None,
                    "pregnancy_category": None, "age_restriction_min": None,
                }
            }
        )
        state = _state(Patient(pregnant=True, allergies=("Пенициллины",)), "mystery_drug")
        result = HardSafetyFilter().run(state, ctx)
        flags = result.state.candidates[0].safety_flags
        codes = {f.code for f in flags}
        assert "PREGNANCY_UNKNOWN" in codes
        assert "ALLERGY_UNVERIFIABLE" in codes

    def test_age_restriction_present_but_unparseable_degrades_to_a_flag(
        self, make_drug_reference_context
    ) -> None:
        """L-2: a restriction string that cannot be parsed used to skip the age
        check silently, even with a known age."""
        ctx = make_drug_reference_context(
            {
                "odd_drug": {
                    "inn": "Странный", "class": "Тестовый класс",
                    "renal_adjustment": None, "hepatic_adjustment": None,
                    "pregnancy_category": None,
                    "age_restriction_min": "с 18 лет и старше",
                }
            }
        )
        state = _state(Patient(age=45), "odd_drug")
        result = HardSafetyFilter().run(state, ctx)
        assert len(result.state.candidates) == 1  # degraded, never excluded on missing data
        flags = result.state.candidates[0].safety_flags
        assert any(f.code == "AGE_RESTRICTION_UNPARSED" for f in flags)
        assert any(f.requires_physician_acknowledgement for f in flags)

    def test_empty_candidates_is_a_noop(self, stage_context: StageContext) -> None:
        state = PipelineState(patient=PatientQuery(patient=Patient()))
        result = HardSafetyFilter().run(state, stage_context)
        assert result.state.candidates == ()
        assert result.state.excluded == ()
