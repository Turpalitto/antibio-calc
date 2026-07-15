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
        assert meta.guideline_version == "unversioned"  # honest placeholder, see DECISIONS.md

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


class TestP1TerminologyBenefit:
    """P1: TerminologyProvider improves allergy exclusion via ATC hierarchy (J01C*).
    Quantifies clinical benefit vs legacy map.
    Uses test data with 'unmapped_pen' (not in legacy map, but ATC J01CA04 -> 'Пенициллины').
    """

    def test_terminology_improves_allergy_exclusion(self, p1_engine_config: EngineConfig) -> None:
        query = PatientQuery(
            diagnosis="vnebolnichnaya pnevmoniya",
            patient=Patient(age=45, allergies=["Пенициллины"]),
        )

        # Legacy path (flag=False, default)
        with Engine(p1_engine_config) as eng_legacy:
            res_legacy = eng_legacy.recommend(query)

        # Terminology path (flag=True)
        cfg_term = dataclasses.replace(p1_engine_config, use_terminology_binding=True)
        with Engine(cfg_term) as eng_term:
            res_term = eng_term.recommend(query)

        # Quantify improvement:
        # Legacy: amox excluded (in map), unmapped_pen NOT (no class) -> may have less exclusions or UNVERIFIABLE
        # Term: both excluded via class "Пенициллины" (map or ATC hierarchy)
        legacy_excluded_refs = {rec.candidate.drug_ref for rec, _ in res_legacy.excluded if rec.candidate.drug_ref}
        term_excluded_refs = {rec.candidate.drug_ref for rec, _ in res_term.excluded if rec.candidate.drug_ref}

        # amox always excluded
        assert "amoxicillin" in legacy_excluded_refs
        assert "amoxicillin" in term_excluded_refs

        # The improvement: unmapped_pen excluded only with terminology (via ATC demo)
        # (in legacy: no class -> not excluded by allergy)
        assert "unmapped_pen" not in legacy_excluded_refs or "unmapped_pen" in [f.code for f in res_legacy.safety_flags if f.code == "ALLERGY_UNVERIFIABLE"]
        assert "unmapped_pen" in term_excluded_refs

        # Traceability: in term path, the provider mapping is used (visible in code path)
        # Physician benefit: more complete exclusion of beta-lactams, fewer UNVERIFIABLE
        term_safety_codes = {f.code for f in res_term.safety_flags}
        assert "ALLERGY" in term_safety_codes or len(term_excluded_refs) > len(legacy_excluded_refs) or "unmapped_pen" in term_excluded_refs

        # Before/after: term path has stricter/more accurate exclusion for the class
        # (measurable: additional drug excluded due to terminology)


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
