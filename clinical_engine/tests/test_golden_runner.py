"""Milestone 12: Golden Cases runner infrastructure.

Tests the harness against the fixture-backed engine (conftest engine_config).
These are INFRASTRUCTURE tests, not clinical golden cases — the assertions
target the fixture dataset (g_cap_adult -> Амоксициллин), not clinical truth.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from clinical_engine.config import EngineConfig
from clinical_engine.engine import Engine
from clinical_engine.golden_cases import runner


@pytest.fixture
def golden_engine(engine_config: EngineConfig):
    with Engine(engine_config) as eng:
        yield eng


def _case(**expect) -> runner.GoldenCase:
    return runner.GoldenCase.from_dict({
        "id": "t",
        "description": "test",
        "query": {"diagnosis": "vnebolnichnaya pnevmoniya", "patient": {"age": 45}},
        "expect": expect,
    })


class TestPassingAssertions:
    def test_first_drug_route_line_pass(self, golden_engine) -> None:
        r = runner.run_case(golden_engine, _case(
            first_drug_normalized="Амоксициллин", first_route="oral",
            first_therapy_line="first", min_accepted=1,
        ))
        assert r.status == "PASS"
        assert all(a.passed for a in r.assertions)

    def test_candidate_confidence_range_pass(self, golden_engine) -> None:
        r = runner.run_case(golden_engine, _case(first_candidate_confidence_range=[0.7, 1.0]))
        assert r.status == "PASS"


class TestFailingAssertions:
    def test_wrong_drug_fails_with_detail(self, golden_engine) -> None:
        r = runner.run_case(golden_engine, _case(first_drug_normalized="Цефтриаксон"))
        assert r.status == "FAIL"
        bad = [a for a in r.assertions if not a.passed]
        assert bad[0].name == "first_drug_normalized"
        assert bad[0].actual == "Амоксициллин"

    def test_empty_accepted_with_first_assertion_fails_not_crash(self, golden_engine) -> None:
        # No-match diagnosis -> accepted empty; first_* must FAIL cleanly.
        case = runner.GoldenCase.from_dict({
            "id": "nomatch", "description": "x",
            "query": {"diagnosis": "не существует", "patient": {"age": 45}},
            "expect": {"first_drug_normalized": "Амоксициллин"},
        })
        r = runner.run_case(golden_engine, case)
        assert r.status == "FAIL"
        assert any("accepted is empty" in a.detail for a in r.assertions)


class TestExclusionAssertions:
    def test_allergy_exclusion_case_passes(self, golden_engine) -> None:
        case = runner.GoldenCase.from_dict({
            "id": "allergy", "description": "penicillin allergy excludes amoxicillin",
            "query": {"diagnosis": "vnebolnichnaya pnevmoniya",
                      "patient": {"age": 45, "allergies": ["Пенициллины"]}},
            "expect": {
                "accepted_empty": True,
                "excluded_drug_refs": ["amoxicillin"],
                "excluded_reason_contains": "allergy",
                "engine_note_code": "ALL_CANDIDATES_EXCLUDED",
            },
        })
        r = runner.run_case(golden_engine, case)
        assert r.status == "PASS", [a for a in r.assertions if not a.passed]

    def test_no_diagnosis_match_note(self, golden_engine) -> None:
        case = runner.GoldenCase.from_dict({
            "id": "nm", "description": "x",
            "query": {"diagnosis": "не существует"},
            "expect": {"accepted_empty": True, "engine_note_code": "NO_DIAGNOSIS_MATCH"},
        })
        assert runner.run_case(golden_engine, case).status == "PASS"


class TestGuards:
    def test_case_without_assertions_is_not_pass(self, golden_engine) -> None:
        r = runner.run_case(golden_engine, _case())
        assert r.status == "FAIL"
        assert any(a.name == "<has_assertions>" for a in r.assertions)

    def test_unknown_assertion_key_fails_gracefully(self, golden_engine) -> None:
        r = runner.run_case(golden_engine, _case(totally_unknown_key=1))
        assert r.status == "FAIL"
        assert any("unknown assertion key" in a.detail for a in r.assertions)


    def test_not_guideline_id_passes_when_absent(self, golden_engine) -> None:
        """PASS if the forbidden guideline is not among accepted (exclusion proof)."""
        case = runner.GoldenCase.from_dict({
            "id": "t",
            "query": {"diagnosis": "vnebolnichnaya pnevmoniya", "patient": {"age": 45}},
            "expect": {"min_accepted": 1, "not_guideline_id": "g_cystitis"}
        })
        r = runner.run_case(golden_engine, case)
        assert r.status == "PASS"

    def test_not_guideline_id_fails_when_present(self, golden_engine) -> None:
        """FAIL if the forbidden guideline is present in accepted."""
        case = runner.GoldenCase.from_dict({
            "id": "t",
            "query": {"diagnosis": "vnebolnichnaya pnevmoniya", "patient": {"age": 45}},
            "expect": {"min_accepted": 1, "not_guideline_id": "g_cap_adult"}
        })
        r = runner.run_case(golden_engine, case)
        assert r.status == "FAIL"
        assert any(a.name == "not_guideline_id" and not a.passed for a in r.assertions)


class TestDirectoryLoading:
    def test_skips_infra_files(self, tmp_path: Path) -> None:
        (tmp_path / "_TEMPLATE.json").write_text("{}", encoding="utf-8")
        (tmp_path / "schema.json").write_text("{}", encoding="utf-8")
        (tmp_path / "real_case.json").write_text(json.dumps({
            "id": "real", "query": {"diagnosis": "x"}, "expect": {"min_accepted": 0}
        }), encoding="utf-8")
        cases = runner.load_cases(tmp_path)
        assert [c.id for c in cases] == ["real"]

    def test_run_directory_end_to_end(self, engine_config: EngineConfig, tmp_path: Path) -> None:
        (tmp_path / "cap.json").write_text(json.dumps({
            "id": "cap", "description": "CAP adult",
            "query": {"diagnosis": "vnebolnichnaya pnevmoniya", "patient": {"age": 45}},
            "expect": {"first_drug_normalized": "Амоксициллин", "min_accepted": 1},
        }), encoding="utf-8")
        results = runner.run_directory(engine_config, tmp_path)
        assert len(results) == 1
        assert results[0].status == "PASS"

    def test_empty_directory_yields_no_results(self, engine_config: EngineConfig, tmp_path: Path) -> None:
        assert runner.run_directory(engine_config, tmp_path) == []


class TestReporting:
    def test_summary_and_markdown(self, golden_engine) -> None:
        good = runner.run_case(golden_engine, _case(min_accepted=1))
        bad = runner.run_case(golden_engine, _case(first_drug_normalized="Нет"))
        s = runner.summary([good, bad])
        assert s == {"total": 2, "pass": 1, "fail": 1, "error": 0}
        md = runner.render_markdown([good, bad])
        assert "PASS **1**" in md and "FAIL **1**" in md


class TestM8ProductionGuard:
    """M-8: the runner used to hardcode strict_mode=False, so every golden case
    was validated against an AUTO_GENERATED_DRAFT index — the exact condition
    the Milestone-13 production guard exists to block."""

    def test_build_config_keeps_the_guard_on_by_default(self) -> None:
        cfg = runner.build_config("x.sqlite")
        assert cfg.strict_mode is True
        assert cfg.use_terminology_binding is True

    def test_running_against_uncurated_index_requires_explicit_opt_in(
        self, engine_config: EngineConfig, tmp_path: Path
    ) -> None:
        from clinical_engine.models import EngineError, EngineErrorCode

        (tmp_path / "case.json").write_text(json.dumps({
            "id": "cap", "description": "x",
            "query": {"diagnosis": "vnebolnichnaya pnevmoniya", "patient": {"age": 45}},
            "expect": {"min_accepted": 1},
        }), encoding="utf-8")
        # The fixture index has no status -> guard silent. Force an uncurated
        # one so the run is genuinely blocked by default.
        import dataclasses
        from clinical_engine.engine import Engine

        with Engine(engine_config) as eng:
            draft_path = tmp_path / "draft.json"
            draft_path.write_text(json.dumps({
                "meta": {"status": "AUTO_GENERATED_DRAFT"},
                "entries": eng._diagnosis_provider._entries and [
                    {
                        "guideline_id": e.guideline_id,
                        "diagnosis_name": e.diagnosis_name,
                        "icd10_codes": list(e.icd10_codes),
                        "guideline_title": e.guideline_title,
                        "guideline_year": e.guideline_year,
                        "guideline_revision_date": e.guideline_revision_date,
                        "source_url": e.source_url,
                    }
                    for e in eng._diagnosis_provider._entries
                ],
            }, ensure_ascii=False), encoding="utf-8")
        cfg = dataclasses.replace(engine_config, diagnosis_index_path=str(draft_path))
        assert cfg.strict_mode is True
        with pytest.raises(EngineError) as exc:
            Engine(cfg)
        assert exc.value.code is EngineErrorCode.RESOURCE_NOT_CURATED
        # ...and the opt-in still works, with the warning recorded in the report.
        relaxed = runner.build_config(str(engine_config.sqlite_path), allow_uncurated_index=True)
        assert relaxed.strict_mode is False
        assert "NOT physician-curated" in runner._UNCURATED_INDEX_WARNING
        md = runner.render_markdown([], header_notes=(runner._UNCURATED_INDEX_WARNING,))
        assert "NOT physician-curated" in md


class TestNewAssertions:
    def test_dose_is_patient_specific_assertion(self, golden_engine) -> None:
        ok = runner.run_case(golden_engine, _case(dose_is_patient_specific=True))
        assert ok.status == "PASS"
        bad = runner.run_case(golden_engine, _case(dose_is_patient_specific=False))
        assert bad.status == "FAIL"
        assert any(a.name == "dose_is_patient_specific" for a in bad.assertions)

    def test_first_outcome_assertion(self, golden_engine) -> None:
        assert runner.run_case(golden_engine, _case(first_outcome="accepted")).status == "PASS"
        assert runner.run_case(golden_engine, _case(first_outcome="warning")).status == "FAIL"

    def test_safety_flag_actions_assertion(self, golden_engine) -> None:
        case = runner.GoldenCase.from_dict({
            "id": "renal", "description": "x",
            "query": {
                "diagnosis": "vnebolnichnaya pnevmoniya",
                "patient": {"age": 62, "renal_function": 12},
            },
            "expect": {"safety_flag_actions": {"RENAL_ADJ_UNPARSED": "avoid_if_possible"}},
        })
        r = runner.run_case(golden_engine, case)
        assert r.status == "PASS", [a for a in r.assertions if not a.passed]
        # Wrong action is a FAIL, not a silent pass.
        case_bad = runner.GoldenCase.from_dict({
            "id": "renal", "query": case.query,
            "expect": {"safety_flag_actions": {"RENAL_ADJ_UNPARSED": "monitor_closely"}},
        })
        assert runner.run_case(golden_engine, case_bad).status == "FAIL"


class TestShippedInfraFilesAreNotCases:
    def test_repo_golden_cases_dir_has_no_unexpected_clinical_case_files(self) -> None:
        """Guard: only the explicitly listed demo/engineered cases may ship.

        Milestone 12 ships no physician-authored cases. M-7 added renal and
        hepatic patient coverage (renal_low_gfr_amoxicillin,
        hepatic_impairment_amoxicillin) — they are engineered regression cases
        over fixture data, not physician-authored clinical truth, so they are
        listed here explicitly rather than allowed in wholesale.
        """
        allowed = {
            "cap_penicillin_allergy.json",
            "renal_low_gfr_amoxicillin.json",
            "hepatic_impairment_amoxicillin.json",
        }
        d = Path("clinical_engine/golden_cases")
        case_files = [p.name for p in d.glob("*.json")
                      if not p.name.startswith("_") and p.name != "schema.json"
                      and not p.name.startswith("diagnosis_") and p.name not in allowed]
        assert case_files == [], f"unexpected clinical case files shipped: {case_files}"


def test_renal_and_hepatic_golden_cases(p1_engine_config: EngineConfig) -> None:
    """M-7: the golden set had ZERO renal/hepatic coverage (every shipped case
    used renal_function=null, hepatic_impairment=false)."""
    import clinical_engine.golden_cases.runner as runner
    from clinical_engine.engine import Engine

    cases = {c.id: c for c in runner.load_cases(Path("clinical_engine/golden_cases"))}
    for case_id in ("renal_low_gfr_amoxicillin", "hepatic_impairment_amoxicillin"):
        assert case_id in cases, f"{case_id}.json must exist and be loadable"
        eng = Engine(p1_engine_config)
        try:
            r = runner.run_case(eng, cases[case_id])
            assert r.status == "PASS", f"{case_id} failed: {r.assertions}"
        finally:
            eng.close()


def test_every_shipped_case_declares_patient_organ_status() -> None:
    """No golden case may leave renal/hepatic status implicit."""
    import clinical_engine.golden_cases.runner as runner

    for case in runner.load_cases(Path("clinical_engine/golden_cases")):
        patient = case.query.get("patient") or {}
        assert "renal_function" in patient, f"{case.id}: renal_function must be explicit"
        assert "hepatic_impairment" in patient, f"{case.id}: hepatic_impairment must be explicit"


def test_p1_diagnosis_golden_cases(p1_engine_config: EngineConfig) -> None:
    """Run P1 diagnosis golden cases with dedicated fixture to make execution reproducible in suite."""
    from pathlib import Path
    import clinical_engine.golden_cases.runner as runner
    from clinical_engine.engine import Engine
    cases = runner.load_cases(Path("clinical_engine/golden_cases"))
    p1_cases = [c for c in cases if c.id.startswith("diagnosis_")]
    cfg = dataclasses.replace(p1_engine_config, use_terminology_binding=True)
    eng = Engine(cfg)
    try:
        for case in p1_cases:
            r = runner.run_case(eng, case)
            assert r.status == "PASS", f"{case.id} failed: {r.assertions}"
    finally:
        eng.close()


def test_cap_penicillin_allergy_golden_is_executed(p1_engine_config: EngineConfig) -> None:
    """Ensure the demo Golden cap_penicillin_allergy.json is actually executed (was excluded from guards but must not be dead code)."""
    from pathlib import Path
    import clinical_engine.golden_cases.runner as runner
    from clinical_engine.engine import Engine
    cases = runner.load_cases(Path("clinical_engine/golden_cases"))
    cap = next((c for c in cases if c.id == "cap_penicillin_allergy"), None)
    assert cap is not None, "cap_penicillin_allergy.json must exist and be loadable"
    cfg = dataclasses.replace(p1_engine_config, use_terminology_binding=True)
    eng = Engine(cfg)
    try:
        r = runner.run_case(eng, cap)
        assert r.status == "PASS", f"cap_penicillin_allergy failed: {r.assertions}"
    finally:
        eng.close()
