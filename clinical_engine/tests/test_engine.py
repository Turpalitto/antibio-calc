"""Engine — PatientQuery -> RecommendationSet (Stages 1-10, complete pipeline).

These are integration smoke tests proving the wiring, not clinical
correctness tests (those are Milestone 10 golden cases).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from clinical_engine.config import EngineConfig
from clinical_engine.engine import Engine
from clinical_engine.models import (
    EngineError,
    EngineErrorCode,
    NoteSeverity,
    Patient,
    PatientQuery,
    SafetyAction,
    ValidationPolicy,
)


class TestEngineRecommend:
    def test_matched_diagnosis_returns_candidates(self, engine_config: EngineConfig) -> None:
        with Engine(engine_config) as engine:
            result = engine.recommend(PatientQuery(diagnosis="vnebolnichnaya pnevmoniya"))
        assert len(result.accepted) == 1
        assert result.accepted[0].candidate.drug_normalized == "Амоксициллин"
        assert result.engine_notes == ()

    def test_no_match_returns_empty_with_engine_note(self, engine_config: EngineConfig) -> None:
        with Engine(engine_config) as engine:
            result = engine.recommend(PatientQuery(diagnosis="nonexistent disease"))
        assert result.accepted == ()
        assert len(result.engine_notes) == 1
        assert result.engine_notes[0].code == "NO_DIAGNOSIS_MATCH"
        assert result.engine_notes[0].severity is NoteSeverity.INFO

    def test_matched_guideline_no_regimens_under_strict_policy(
        self, engine_config: EngineConfig
    ) -> None:
        # g_cap_adult has PASS/REVIEW/REJECT; under STRICT (default) only the
        # REJECT-only guideline would produce zero -- use icd10 with no
        # matching SQLite rows instead to exercise the "matched but empty" path.
        with Engine(engine_config) as engine:
            result = engine.recommend(PatientQuery(diagnosis="ostryi sinusit"))
        assert result.accepted == ()
        assert result.engine_notes[0].code == "NO_REGIMENS_EXTRACTED"

    def test_debug_policy_surfaces_review_and_reject_too(self, engine_config: EngineConfig) -> None:
        import dataclasses

        debug_config = dataclasses.replace(
            engine_config, validation_policy=ValidationPolicy.DEBUG
        )
        with Engine(debug_config) as engine:
            result = engine.recommend(PatientQuery(diagnosis="vnebolnichnaya pnevmoniya"))
        assert len(result.accepted) == 3

    def test_result_carries_query_and_runtime(self, engine_config: EngineConfig) -> None:
        query = PatientQuery(
            diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45)
        )
        with Engine(engine_config) as engine:
            result = engine.recommend(query)
        assert result.query is query
        assert result.runtime.profile is ValidationPolicy.STRICT
        assert result.elapsed_ms >= 0.0
        assert "DiagnosisMatch" in result.runtime.pipeline_time_breakdown
        assert "RegimenLoad" in result.runtime.pipeline_time_breakdown

    def test_metadata_property(self, engine_config: EngineConfig) -> None:
        with Engine(engine_config) as engine:
            meta = engine.metadata
        assert meta.decision_engine_version == "1.0.0"
        assert meta.normalizer_version == "1.0.0"  # from medical_normalizer.NORMALIZER_VERSION
        assert meta.dictionary_version == "1.0.0"  # from medical_dictionary/metadata.json
        assert meta.knowledge_dataset_version == "KB-2026-07-09"
        # L-5: no more silent "unversioned" placeholder. The fixture index is a
        # bare list (no meta), so the loud sentinel is expected here; a real
        # index carries guideline_set_version (see the test below).
        assert meta.guideline_version == "UNKNOWN_NO_GUIDELINE_SET_VERSION"

    def test_guideline_version_comes_from_the_index(self, engine_config, tmp_path) -> None:
        entry = {
            "guideline_id": "g1", "diagnosis_name": "dx", "icd10_codes": ["A00"],
            "guideline_title": "t", "guideline_year": None,
            "guideline_revision_date": None, "source_url": "",
        }
        index = tmp_path / "idx.json"
        index.write_text(
            json.dumps({"meta": {"status": "PRODUCTION_CURATED",
                                 "guideline_set_version": "kr-2026-01"}, "entries": [entry]}),
            encoding="utf-8",
        )
        cfg = dataclasses.replace(engine_config, diagnosis_index_path=str(index))
        with Engine(cfg) as engine:
            assert engine.metadata.guideline_version == "kr-2026-01"

    def test_result_carries_ranked_candidates(self, engine_config: EngineConfig) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45))
        with Engine(engine_config) as engine:
            result = engine.recommend(query)
        assert result.accepted[0].rank == 1
        assert result.accepted[0].score is not None
        assert result.accepted[0].score_breakdown  # non-empty

    def test_accepted_outcome_labeled_by_trace(self, engine_config: EngineConfig) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45))
        with Engine(engine_config) as engine:
            result = engine.recommend(query)
        from clinical_engine.models import RecommendationOutcome

        assert result.accepted[0].outcome is RecommendationOutcome.ACCEPTED

    def test_excluded_outcome_labeled_by_trace(self, engine_config: EngineConfig) -> None:
        query = PatientQuery(
            diagnosis="vnebolnichnaya pnevmoniya",
            patient=Patient(allergies=("Пенициллины",)),
        )
        with Engine(engine_config) as engine:
            result = engine.recommend(query)
        from clinical_engine.models import RecommendationOutcome

        assert result.excluded[0][0].outcome is RecommendationOutcome.EXCLUDED

    def test_build_report(self, engine_config: EngineConfig) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45))
        with Engine(engine_config) as engine:
            result = engine.recommend(query)
            report = engine.build_report(result)
        assert report.query is query
        assert report.accepted == result.accepted
        assert report.confidence_breakdowns == {}  # §7.3 not implemented, honest empty dict
        d = report.to_dict()
        assert d["metadata"]["decision_engine_version"] == "1.0.0"
        assert "decision_engine_version" in report.to_json()

    def test_all_excluded_by_safety_filter_is_distinguished_from_no_regimens(
        self, engine_config: EngineConfig
    ) -> None:
        # Amoxicillin is the only candidate for g_cap_adult under STRICT; an
        # allergy to its class excludes it in Stage 5, not "no regimens".
        query = PatientQuery(
            diagnosis="vnebolnichnaya pnevmoniya",
            patient=Patient(allergies=("Пенициллины",)),
        )
        with Engine(engine_config) as engine:
            result = engine.recommend(query)
        assert result.accepted == ()
        assert len(result.excluded) == 1
        assert result.engine_notes[0].code == "ALL_CANDIDATES_EXCLUDED"
        assert result.engine_notes[0].severity is NoteSeverity.WARN

    def test_interaction_check_wired_end_to_end(self, engine_config: EngineConfig) -> None:
        # amoxicillin fixture interactions text mentions "аллопуринолом".
        query = PatientQuery(
            diagnosis="vnebolnichnaya pnevmoniya",
            patient=Patient(age=45, current_meds=("аллопуринол",)),
        )
        with Engine(engine_config) as engine:
            result = engine.recommend(query)
        assert len(result.accepted) == 1
        flags = result.accepted[0].safety_flags
        assert any(f.code == "INTERACTION_UNKNOWN" for f in flags)
        assert result.accepted[0].interaction_severity is not None

    def test_dose_calculated_end_to_end(self, engine_config: EngineConfig) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45))
        with Engine(engine_config) as engine:
            result = engine.recommend(query)
        assert result.accepted[0].dose is not None
        assert result.accepted[0].dose.calculated_dose_mg is not None

    def test_deterministic_for_same_input(self, engine_config: EngineConfig) -> None:
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya")
        with Engine(engine_config) as engine:
            r1 = engine.recommend(query)
            r2 = engine.recommend(query)
        assert [r.candidate.regimen_id for r in r1.accepted] == [
            r.candidate.regimen_id for r in r2.accepted
        ]


class TestSafetySummaryPublished:
    """H-4: every flag the engine computed was dropped on the way out, so a
    response carrying PREGNANCY_CI / RENAL_ADJ_UNPARSED was byte-identical to a
    clean one. The engine now publishes its own aggregate verdict; the transport
    layer must pass it through."""

    def test_clean_result_is_marked_cleared(self, engine_config: EngineConfig) -> None:
        with Engine(engine_config) as engine:
            res = engine.recommend(
                PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45))
            )
        s = res.safety_summary
        assert s is not None
        assert s.status == "CLEARED"
        assert s.requires_physician_review is False
        assert s.total_flags == 0
        assert s.dose_is_patient_specific is True

    def test_allergy_exclusion_is_surfaced(self, engine_config: EngineConfig) -> None:
        with Engine(engine_config) as engine:
            res = engine.recommend(
                PatientQuery(diagnosis="vnebolnichnaya pnevmoniya",
                             patient=Patient(allergies=("Пенициллины",)))
            )
        s = res.safety_summary
        assert s is not None
        assert s.flag_counts == {"ALLERGY": 1}
        assert "ALLERGY" in s.flag_codes
        assert s.most_severe_action is SafetyAction.STOP_IMMEDIATELY
        assert s.absolute_contraindications == 1
        assert s.requires_physician_acknowledgement == 1
        assert s.requires_physician_review is True
        assert s.status == "REVIEW_REQUIRED"

    def test_renal_case_is_surfaced_and_dose_marked_generic(
        self, engine_config: EngineConfig
    ) -> None:
        with Engine(engine_config) as engine:
            res = engine.recommend(
                PatientQuery(diagnosis="vnebolnichnaya pnevmoniya",
                             patient=Patient(age=62, renal_function=12.0))
            )
        s = res.safety_summary
        assert s is not None
        assert "RENAL_ADJ_UNPARSED" in s.flag_codes
        assert s.most_severe_action is SafetyAction.AVOID_IF_POSSIBLE
        assert s.dose_is_patient_specific is False  # C-2
        assert s.status == "REVIEW_REQUIRED"

    def test_report_carries_the_summary(self, engine_config: EngineConfig) -> None:
        with Engine(engine_config) as engine:
            res = engine.recommend(
                PatientQuery(diagnosis="vnebolnichnaya pnevmoniya",
                             patient=Patient(allergies=("Пенициллины",)))
            )
            report = engine.build_report(res)
        assert report.safety_summary is not None
        assert report.safety_summary.flag_counts == {"ALLERGY": 1}
        assert report.to_dict()["safety_summary"]["status"] == "REVIEW_REQUIRED"

    def test_non_clinical_profile_is_recorded_in_the_result(
        self, engine_config: EngineConfig
    ) -> None:
        """M-2: DEBUG/AUDIT load REJECT regimens; the result must say so."""
        import dataclasses as _dc
        import warnings

        cfg = _dc.replace(engine_config, validation_policy=ValidationPolicy.DEBUG)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with Engine(cfg) as engine:
                res = engine.recommend(
                    PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45))
                )
        notes = {n.code: n for n in res.engine_notes}
        assert "NON_CLINICAL_VALIDATION_PROFILE" in notes
        assert notes["NON_CLINICAL_VALIDATION_PROFILE"].severity is NoteSeverity.WARN
        assert engine_config.is_non_clinical_profile is False
        assert cfg.is_non_clinical_profile is True

    def test_interaction_check_early_return_reports_a_real_duration(
        self, engine_config: EngineConfig
    ) -> None:
        """M-3: the early return hardcoded elapsed_ms=0.0, corrupting
        pipeline_time_breakdown."""
        with Engine(engine_config) as engine:
            res = engine.recommend(
                PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45))
            )
        assert "InteractionCheck" in res.runtime.pipeline_time_breakdown
        assert res.runtime.pipeline_time_breakdown["InteractionCheck"] > 0.0

    def test_guideline_diagnosis_names_is_exposed_for_icd_only_queries(
        self, engine_config: EngineConfig
    ) -> None:
        """api/contract.py permits an ICD-only request; the curated layer needs
        the code->name mapping and must not duplicate the diagnosis index."""
        with Engine(engine_config) as engine:
            names = engine.guideline_diagnosis_names("J18")
            assert "g_cap_adult" == engine._diagnosis_provider.lookup(None, "J18")[0].guideline_id
        assert "vnebolnichnaya pnevmoniya" in names
        assert engine_names_are_deduped(names)
        with Engine(engine_config) as engine:
            assert engine.guideline_diagnosis_names("Z99") == ()


def engine_names_are_deduped(names: tuple[str, ...]) -> bool:
    return len(names) == len(set(names))


class TestP1TerminologyBenefit:
    """M-4: the allergy class is resolved through the curated class hierarchy,
    so a drug missing from the per-drug allergy_class_map is still classified
    and a penicillin allergy excludes it.

    Historically the excluded drug ('unmapped_pen') was only classifiable via a
    synthetic ATC entry injected into the real lookup map (L-6) on the
    terminology-binding path. Both problems are gone: the class now comes from
    the drug's own class label matched against the family vocabulary, which
    works identically with and without the terminology flag.
    """

    def _run(self, config, query):
        with Engine(config) as engine:
            return engine.recommend(query)

    def test_unmapped_class_drug_is_excluded_in_both_binding_modes(
        self, p1_engine_config: EngineConfig
    ) -> None:
        query = PatientQuery(
            diagnosis="vnebolnichnaya pnevmoniya",
            patient=Patient(age=45, allergies=["Пенициллины"]),
        )
        legacy = self._run(p1_engine_config, query)
        term = self._run(
            dataclasses.replace(p1_engine_config, use_terminology_binding=True), query
        )
        for res in (legacy, term):
            excluded = {rec.candidate.drug_ref for rec, _ in res.excluded}
            assert "amoxicillin" in excluded
            assert "unmapped_pen" in excluded
            # The class WAS resolvable, so it is not reported as unverifiable.
            assert "ALLERGY_UNVERIFIABLE" not in {f.code for f in res.safety_flags}
            assert res.accepted == ()

    def test_synthetic_atc_is_gone(self, p1_engine_config: EngineConfig) -> None:
        """L-6: a real ATC map must not carry an invented entry for a drug."""
        with Engine(p1_engine_config) as engine:
            assert engine._terminology_provider.get_atc("unmapped_pen") is None


class TestProductionGuard:
    """Milestone 13: Engine refuses/warns on an uncurated diagnosis_index."""

    def _index(self, tmp_path: Path, status: str | None) -> Path:
        entry = {
            "guideline_id": "g1", "diagnosis_name": "dx", "icd10_codes": ["A00"],
            "guideline_title": "t", "guideline_year": None,
            "guideline_revision_date": None, "source_url": "",
        }
        p = tmp_path / "idx.json"
        if status is None:
            p.write_text(json.dumps([entry]), encoding="utf-8")  # bare list, no meta
        else:
            p.write_text(json.dumps({"meta": {"status": status}, "entries": [entry]}),
                         encoding="utf-8")
        return p

    def _cfg(self, engine_config, tmp_path, status, strict_mode):
        return dataclasses.replace(
            engine_config,
            diagnosis_index_path=str(self._index(tmp_path, status)),
            strict_mode=strict_mode,
        )

    @pytest.mark.parametrize("status", ["AUTO_GENERATED_DRAFT", "PARTIALLY_CURATED"])
    def test_strict_mode_refuses_uncurated_index(self, engine_config, tmp_path, status) -> None:
        with pytest.raises(EngineError) as exc:
            Engine(self._cfg(engine_config, tmp_path, status, strict_mode=True))
        assert exc.value.code is EngineErrorCode.RESOURCE_NOT_CURATED

    @pytest.mark.parametrize("status", ["AUTO_GENERATED_DRAFT", "PARTIALLY_CURATED"])
    def test_non_strict_warns_but_runs(self, engine_config, tmp_path, status) -> None:
        with pytest.warns(UserWarning, match="not physician-curated"):
            eng = Engine(self._cfg(engine_config, tmp_path, status, strict_mode=False))
        eng.close()

    def test_curated_index_passes_strict(self, engine_config, tmp_path) -> None:
        eng = Engine(self._cfg(engine_config, tmp_path, "PRODUCTION_CURATED", strict_mode=True))
        eng.close()  # no raise, no warning

    def test_absent_status_is_not_blocked(self, engine_config, tmp_path) -> None:
        # bare-list index (no meta) -> unknown status -> guard does not fire.
        eng = Engine(self._cfg(engine_config, tmp_path, None, strict_mode=True))
        eng.close()


# P0-2 Provider Ports equality (legacy vs adapters). Must be identical.
class TestProviderPorts:
    def test_provider_path_identical_to_legacy(self, engine_config: EngineConfig) -> None:
        """Run same query with default (legacy attrs) and provider ports. Results match."""
        query = PatientQuery(diagnosis="vnebolnichnaya pnevmoniya", patient=Patient(age=45))

        # Legacy path (use_provider_ports=False default)
        with Engine(engine_config) as eng_legacy:
            res_legacy = eng_legacy.recommend(query)

        # Provider port path (flag True)
        cfg_prov = dataclasses.replace(engine_config, use_provider_ports=True)
        with Engine(cfg_prov) as eng_prov:
            res_prov = eng_prov.recommend(query)

        # Structural identity on key outputs (100% behavior)
        assert len(res_prov.accepted) == len(res_legacy.accepted)
        assert len(res_prov.excluded) == len(res_legacy.excluded)
        assert len(res_prov.safety_flags) == len(res_legacy.safety_flags)
        assert len(res_prov.traces) == len(res_legacy.traces)
        assert res_prov.engine_notes == res_legacy.engine_notes
        # regimen ids match
        acc_l = [r.candidate.regimen_id for r in res_legacy.accepted]
        acc_p = [r.candidate.regimen_id for r in res_prov.accepted]
        assert acc_p == acc_l
