from __future__ import annotations

import json

import pytest

from src.pipeline.extraction.scenario_bindings import _main, build_binding_artifact, verify_scenario_bindings

SPEC_654 = {
    "guideline_id": "654_2",
    "rubricator_revision": "654_2",
    "duration": "5-7 days",
    "row_groups": [
        {
            "page": 122,
            "table_index": 0,
            "row_start": 5,
            "row_end": 5,
            "drug_col": 2,
            "dose_col": 3,
            "atc": "J01CA04",
            "drug": "Амоксициллин",
            "therapy_line": "dose_reference",
            "blocking_reasons": ["DOSE_TABLE_NOT_LINKED_TO_TREATMENT_SCENARIO"],
        },
        {
            "page": 122,
            "table_index": 0,
            "row_start": 3,
            "row_end": 3,
            "drug_col": 2,
            "dose_col": 3,
            "atc": "J01FA10",
            "drug": "Азитромицин",
            "therapy_line": "dose_reference",
            "blocking_reasons": ["DOSE_TABLE_NOT_LINKED_TO_TREATMENT_SCENARIO", "MULTIPLE_ROUTES"],
        },
    ],
}

SPEC_714 = {
    "guideline_id": "714_2",
    "rubricator_revision": "714_2",
    "duration": "7-10 days",
    "row_groups": [
        {
            "page": 44,
            "row_start": 1,
            "atc": "J01FA10",
            "drug": "Азитромицин",
            "therapy_line": "dose_reference",
            "duration": "3 days",
            "population_constraints": {"age_months_min_inclusive": 6, "age_years_max_inclusive": 12},
            "blocking_reasons": ["MULTIPLE_AGE_WEIGHT_STRATA"],
        },
        {
            "page": 44,
            "row_start": 2,
            "atc": "J01CA04",
            "drug": "Амоксициллин",
            "therapy_line": "dose_reference",
            "blocking_reasons": ["MAXIMUM_DOSE_NOT_STRUCTURED"],
        },
    ],
}

SPEC_CLEAN = {
    "guideline_id": "999_1",
    "duration": "5 days",
    "row_groups": [
        {
            "page": 1,
            "row_start": 1,
            "atc": "J01CA04",
            "drug": "Амоксициллин",
            "therapy_line": "dose_reference",
            "blocking_reasons": [],
        },
    ],
}


def _adult_disease() -> dict:
    return {
        "id": "cap_adult",
        "name": "Внебольничная пневмония, взрослые",
        "cr_id": "654_2",
        "cr_year": 2024,
        "calculation_blocked": True,
        "calculation_block_reason": "review pending",
        "age_groups": ["adult"],
        "scenarios": [
            {
                "id": "cap_adult_out_no_risk",
                "name": "Амбулаторно, без рисков",
                "age_group": "adult",
                "lines": [
                    {
                        "line_number": 1,
                        "line_label": "Первая линия",
                        "drugs": [
                            {
                                "drug_ref": "amoxicillin",
                                "route": ["per_os"],
                                "regimens": [
                                    {"age_group": "adult", "dose_mg_day_fixed": 1500, "freq_per_day": 3, "duration_days": "5-7"},
                                ],
                            },
                        ],
                    },
                    {
                        "line_number": 2,
                        "line_label": "Альтернатива",
                        "drugs": [
                            {
                                "drug_ref": "azithromycin",
                                "route": ["per_os"],
                                "regimens": [
                                    {"age_group": "adult", "dose_mg_day_fixed": 500, "freq_per_day": 1, "duration_days": "3-5"},
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }


def _child_disease() -> dict:
    return {
        "id": "cap_child",
        "name": "Внебольничная пневмония, дети",
        "cr_id": "714_2",
        "cr_year": 2024,
        "calculation_blocked": True,
        "calculation_block_reason": "review pending",
        "age_groups": ["child"],
        "scenarios": [
            {
                "id": "cap_child_out",
                "name": "Амбулаторно",
                "age_group": "child",
                "lines": [
                    {
                        "line_number": 1,
                        "line_label": "Первая линия",
                        "drugs": [
                            {
                                "drug_ref": "azithromycin",
                                "route": ["per_os"],
                                "regimens": [
                                    {"age_group": "child", "dose_mg_kg_day": 10, "freq_per_day": 1, "duration_days": "3"},
                                    {"age_group": "child", "dose_mg_kg_day": 10, "freq_per_day": 1, "duration_days": "5"},
                                ],
                            },
                            {
                                "drug_ref": "amoxicillin",
                                "route": ["per_os"],
                                "regimens": [
                                    {"age_group": "child", "dose_mg_kg_day": 90, "freq_per_day": 2, "duration_days": "7-10"},
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }


def _clean_disease() -> dict:
    return {
        "id": "clean_disease",
        "name": "Clean",
        "cr_id": "999_1",
        "cr_year": 2024,
        "calculation_blocked": True,
        "age_groups": ["adult"],
        "scenarios": [
            {
                "id": "clean_out",
                "age_group": "adult",
                "lines": [
                    {
                        "line_number": 1,
                        "drugs": [
                            {
                                "drug_ref": "amoxicillin",
                                "route": ["per_os"],
                                "regimens": [{"duration_days": "5"}],
                            },
                        ],
                    },
                ],
            },
        ],
    }


def _prepare(tmp_path, recommendations, specs):
    db_path = tmp_path / "db.json"
    db_path.write_text(json.dumps({"recommendations": recommendations}, ensure_ascii=False), encoding="utf-8")
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    for cr_id, spec in specs.items():
        (specs_dir / f"{cr_id}.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    bindings_dir = tmp_path / "bindings"
    bindings_dir.mkdir()
    return db_path, bindings_dir, specs_dir


def _build_and_write(db_path, bindings_dir, specs_dir):
    db = json.loads(db_path.read_text(encoding="utf-8"))
    artifacts = {}
    for disease in db["recommendations"]:
        cr_id = str(disease["cr_id"])
        spec = json.loads((specs_dir / f"{cr_id}.json").read_text(encoding="utf-8"))
        artifacts[cr_id] = build_binding_artifact(db, spec, disease["id"], "2026-09-02")
        (bindings_dir / f"{cr_id}.json").write_text(
            json.dumps(artifacts[cr_id], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return artifacts


def _load_artifact(bindings_dir, cr_id):
    return json.loads((bindings_dir / f"{cr_id}.json").read_text(encoding="utf-8"))


def _write_artifact(bindings_dir, cr_id, artifact):
    (bindings_dir / f"{cr_id}.json").write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")


def _binding(report, disease_id, drug_ref, regimen_index=0):
    disease = next(d for d in report["diseases"] if d["disease_id"] == disease_id)
    return next(
        b for b in disease["bindings"]
        if b["drug_ref"] == drug_ref and b["regimen_index"] == regimen_index
    )


def test_build_and_verify_happy_path(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    report = verify_scenario_bindings(db_path, bindings_dir, specs_dir)

    assert report["schema_version"] == "1.0.0"
    assert report["artifact_count"] == 2
    assert report["binding_count"] == 5
    counts = {d["disease_id"]: d["binding_count"] for d in report["diseases"]}
    assert counts == {"cap_adult": 2, "cap_child": 3}
    assert all(d["unblock_eligible_count"] == 0 for d in report["diseases"])

    amox = _binding(report, "cap_adult", "amoxicillin")
    assert amox["spec_row_index"] == 0
    assert amox["atc"] == "J01CA04"
    assert amox["spec_page"] == 122
    assert amox["route"] == "LINKED"
    assert amox["duration"] == "GLOBAL_SPEC"
    assert amox["age_weight"] == "GUIDELINE_SCOPE_ADULT"
    assert amox["severity"] == "DOSE_TABLE_NOT_STRATIFIED"
    assert amox["remaining_blockers"] == []
    assert amox["duration_review_required"] is False
    assert amox["unblock_eligible"] is False

    azithro = _binding(report, "cap_adult", "azithromycin")
    assert azithro["route"] == "AMBIGUOUS"
    assert azithro["remaining_blockers"] == ["MULTIPLE_ROUTES"]
    assert azithro["unblock_eligible"] is False

    child_azithro_0 = _binding(report, "cap_child", "azithromycin", regimen_index=0)
    assert child_azithro_0["duration"] == "ROW"
    assert child_azithro_0["age_weight"] == "MULTIPLE_STRATA_REVIEW"
    assert child_azithro_0["duration_review_required"] is False

    child_azithro_1 = _binding(report, "cap_child", "azithromycin", regimen_index=1)
    assert child_azithro_1["duration_review_required"] is True

    child_amox = _binding(report, "cap_child", "amoxicillin")
    assert child_amox["duration"] == "GLOBAL_SPEC"
    assert child_amox["age_weight"] == "NOT_CONSTRAINED"


def test_builder_rejects_unblocked_disease(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    disease = _adult_disease()
    disease["calculation_blocked"] = False
    db = {"recommendations": [disease]}
    with pytest.raises(ValueError, match="calculation must stay blocked"):
        build_binding_artifact(db, SPEC_654, "cap_adult", "2026-09-02")


def test_builder_rejects_spec_guideline_mismatch(tmp_path):
    db = {"recommendations": [_adult_disease()]}
    with pytest.raises(ValueError, match="guideline_id"):
        build_binding_artifact(db, SPEC_714, "cap_adult", "2026-09-02")


def test_builder_rejects_missing_drug_ref(tmp_path):
    disease = _adult_disease()
    disease["scenarios"][0]["lines"][0]["drugs"][0].pop("drug_ref")
    db = {"recommendations": [disease]}
    with pytest.raises(ValueError, match="drug_ref missing"):
        build_binding_artifact(db, SPEC_654, "cap_adult", "2026-09-02")


def test_builder_rejects_non_unique_row(tmp_path):
    spec = json.loads(json.dumps(SPEC_654))
    spec["row_groups"].append(json.loads(json.dumps(spec["row_groups"][0])))
    db = {"recommendations": [_adult_disease()]}
    with pytest.raises(ValueError, match="not unique"):
        build_binding_artifact(db, spec, "cap_adult", "2026-09-02")


def test_builder_rejects_zero_bindings(tmp_path):
    disease = _adult_disease()
    disease["scenarios"] = []
    db = {"recommendations": [disease]}
    with pytest.raises(ValueError, match="no bindings produced"):
        build_binding_artifact(db, SPEC_654, "cap_adult", "2026-09-02")


def test_verify_rejects_wrong_schema(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    artifact = _load_artifact(bindings_dir, "654_2")
    artifact["schema_version"] = "9.9.9"
    _write_artifact(bindings_dir, "654_2", artifact)
    with pytest.raises(ValueError, match="schema_version"):
        verify_scenario_bindings(db_path, bindings_dir, specs_dir)


def test_verify_rejects_unlocked_artifact(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    artifact = _load_artifact(bindings_dir, "654_2")
    artifact["calculation_blocked"] = False
    _write_artifact(bindings_dir, "654_2", artifact)
    with pytest.raises(ValueError, match="calculation_blocked must stay true"):
        verify_scenario_bindings(db_path, bindings_dir, specs_dir)


def test_verify_rejects_unblocked_disease(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    db = json.loads(db_path.read_text(encoding="utf-8"))
    db["recommendations"][0]["calculation_blocked"] = False
    db_path.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="must stay calculation-blocked"):
        verify_scenario_bindings(db_path, bindings_dir, specs_dir)


def test_verify_rejects_missing_spec(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    (specs_dir / "654_2.json").unlink()
    with pytest.raises(ValueError, match="spec .* is missing"):
        verify_scenario_bindings(db_path, bindings_dir, specs_dir)


def test_verify_rejects_changed_disease_record(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    db = json.loads(db_path.read_text(encoding="utf-8"))
    db["recommendations"][0]["name"] = "Изменённое название"
    db_path.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="disease record changed"):
        verify_scenario_bindings(db_path, bindings_dir, specs_dir)


def test_verify_rejects_changed_spec_row_groups(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    spec = json.loads((specs_dir / "654_2.json").read_text(encoding="utf-8"))
    spec["row_groups"][0]["blocking_reasons"].append("NEW_BLOCKER")
    (specs_dir / "654_2.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="row_groups changed"):
        verify_scenario_bindings(db_path, bindings_dir, specs_dir)


def test_verify_rejects_wrong_spec_row_index(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    artifact = _load_artifact(bindings_dir, "714_2")
    binding = next(b for b in artifact["bindings"] if b["drug_ref"] == "azithromycin" and b["regimen_index"] == 0)
    binding["spec_row_index"] = 1
    _write_artifact(bindings_dir, "714_2", artifact)
    with pytest.raises(ValueError, match="does not match drug_ref"):
        verify_scenario_bindings(db_path, bindings_dir, specs_dir)


def test_verify_rejects_duplicate_binding(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    artifact = _load_artifact(bindings_dir, "654_2")
    artifact["bindings"].append(json.loads(json.dumps(artifact["bindings"][0])))
    _write_artifact(bindings_dir, "654_2", artifact)
    with pytest.raises(ValueError, match="duplicate binding"):
        verify_scenario_bindings(db_path, bindings_dir, specs_dir)


def test_verify_rejects_coverage_gap(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    artifact = _load_artifact(bindings_dir, "714_2")
    artifact["bindings"] = [b for b in artifact["bindings"] if b["drug_ref"] != "amoxicillin"]
    _write_artifact(bindings_dir, "714_2", artifact)
    with pytest.raises(ValueError, match="coverage mismatch"):
        verify_scenario_bindings(db_path, bindings_dir, specs_dir)


def test_severity_guard_keeps_eligibility_false(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(tmp_path, [_clean_disease()], {"999_1": SPEC_CLEAN})
    _build_and_write(db_path, bindings_dir, specs_dir)
    report = verify_scenario_bindings(db_path, bindings_dir, specs_dir)

    binding = _binding(report, "clean_disease", "amoxicillin")
    assert binding["route"] == "LINKED"
    assert binding["age_weight"] == "GUIDELINE_SCOPE_ADULT"
    assert binding["duration_review_required"] is False
    assert binding["remaining_blockers"] == []
    assert binding["severity"] == "DOSE_TABLE_NOT_STRATIFIED"
    assert binding["unblock_eligible"] is False
    disease = report["diseases"][0]
    assert disease["unblock_eligible_count"] == 0


def test_cli_writes_report(tmp_path):
    db_path, bindings_dir, specs_dir = _prepare(
        tmp_path, [_adult_disease(), _child_disease()], {"654_2": SPEC_654, "714_2": SPEC_714}
    )
    _build_and_write(db_path, bindings_dir, specs_dir)
    output = tmp_path / "out" / "report.json"
    exit_code = _main([
        "--db", str(db_path),
        "--bindings", str(bindings_dir),
        "--specs", str(specs_dir),
        "--output", str(output),
    ])
    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["artifact_count"] == 2
    assert report["binding_count"] == 5
