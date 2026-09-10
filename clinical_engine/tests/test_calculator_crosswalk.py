"""Tests for the calculator ⇄ guideline-corpus crosswalk (navigation layer).

Covers three guarantees:

1. **Determinism** — the same inputs always produce a byte-identical artifact,
   so the committed JSON can be drift-checked in CI.
2. **Correctness of the join** — the two identifier namespaces (rubricator
   ``cr_id`` vs internal corpus ``guideline_id``) are never joined by id; only
   ICD-10 and exact titles produce links.
3. **Safety** — the artifact declares itself navigation-only and never claims
   clinical approval or unblocks calculation.
"""

from __future__ import annotations

import json

import pytest

from clinical_engine.crosswalk import (
    METHOD_CONFIDENCE,
    METHOD_ICD10_BLOCK,
    METHOD_ICD10_EXACT,
    METHOD_TITLE_EXACT,
    CalculatorCrosswalk,
    CrosswalkBuildError,
    build_crosswalk,
    canonical_json,
    compact_links,
    content_sha256,
    crosswalk_summary,
    icd_block,
    normalize_icd10_values,
    normalize_text,
)
from clinical_engine.crosswalk.builder import (
    DEFAULT_CALCULATOR_DB,
    DEFAULT_DIAGNOSIS_INDEX,
    DEFAULT_OUTPUT,
    build_crosswalk_from_paths,
    write_crosswalk,
)


def _calculator(recs):
    return {"recommendations": recs}


def _index(entries):
    return {"meta": {"status": "AUTO_GENERATED_DRAFT"}, "entries": entries}


@pytest.fixture()
def tiny_pair():
    calculator = _calculator(
        [
            {
                "id": "tonsillitis_child",
                "name": "Острый тонзиллит у детей",
                "cr_id": "306_3",
                "mkb10": ["J03", "J03.0"],
            },
            {
                "id": "sepsis_neonatal",
                "name": "Неонатальный сепсис",
                "cr_id": "912_1",
                "mkb10": ["P36.9"],
            },
            {
                "id": "orphan",
                "name": "Нозология без совпадений",
                "cr_id": "999_1",
                "mkb10": ["Z99.9"],
            },
        ]
    )
    index = _index(
        [
            {
                "guideline_id": "1269",
                "guideline_title": "Острый тонзиллит и фарингит",
                "guideline_year": 2024,
                "guideline_revision_date": None,
                "diagnosis_name": "Острый стрептококковый тонзиллит",
                "icd10_codes": ["J03", "J03.9"],
                "source_url": "",
            },
            {
                "guideline_id": "912",
                "guideline_title": "Системный склероз",
                "guideline_year": 2021,
                "guideline_revision_date": None,
                "diagnosis_name": "Интерстициальная пневмония",
                "icd10_codes": ["M34.9"],
                "source_url": "",
            },
        ]
    )
    return calculator, index


# ── normalization ───────────────────────────────────────────────────────────


def test_normalize_icd10_splits_comma_joined_strings():
    assert normalize_icd10_values(["C83.5, C91.0, C95.0"]) == ["C83.5", "C91.0", "C95.0"]


def test_normalize_icd10_expands_block_ranges():
    assert normalize_icd10_values(["B20-24"]) == ["B20", "B21", "B22", "B23", "B24"]


def test_normalize_icd10_drops_malformed_tokens_without_guessing():
    assert normalize_icd10_values(["A00.0", "не код", "", None, "12345"]) == ["A00.0"]


def test_normalize_icd10_deduplicates_preserving_order():
    assert normalize_icd10_values(["A01", "a01", "A02"]) == ["A01", "A02"]


def test_normalize_icd10_rejects_ranges_that_cross_a_letter():
    # "A99-B01" is ambiguous; it must not be expanded into invented codes.
    assert normalize_icd10_values(["A99-B01"]) == []


@pytest.mark.parametrize(
    "code,block",
    [("G00.1", "G00"), ("A00", "A00"), ("", None), ("12", None)],
)
def test_icd_block(code, block):
    assert icd_block(code) == block


def test_normalize_text_is_case_yo_and_punctuation_insensitive():
    assert normalize_text("Острый  тонзиллит!") == normalize_text("острый тонзиллит")
    assert normalize_text("Ёлка") == normalize_text("елка")
    assert normalize_text("Отит средний острый") == "отит средний острый"
    assert normalize_text(None) == ""


# ── join behaviour ──────────────────────────────────────────────────────────


def test_links_are_built_from_icd10_not_from_identifier_collision(tiny_pair):
    calculator, index = tiny_pair
    crosswalk = build_crosswalk(calculator, index)
    by_disease = {link["disease_id"]: link for link in crosswalk["links"]}

    # Exact ICD-10 match links the calculator nozology to the corpus guideline.
    assert by_disease["tonsillitis_child"]["guideline_id"] == "1269"
    assert by_disease["tonsillitis_child"]["method"] == METHOD_ICD10_EXACT
    assert by_disease["tonsillitis_child"]["matched_icd10"] == ["J03"]
    assert by_disease["tonsillitis_child"]["guideline_title"] == "Острый тонзиллит и фарингит"

    # The numeric coincidence cr_id "912_1" ↔ guideline_id "912" must NOT link:
    # those are different namespaces (Неонатальный сепсис vs Системный склероз).
    assert "sepsis_neonatal" not in by_disease


def test_unmatched_diseases_are_reported_explicitly(tiny_pair):
    calculator, index = tiny_pair
    crosswalk = build_crosswalk(calculator, index)
    unmatched = {item["disease_id"]: item for item in crosswalk["unmatched_diseases"]}
    assert set(unmatched) == {"sepsis_neonatal", "orphan"}
    assert unmatched["orphan"]["reason"] == "NO_CORPUS_ENTRY_FOR_ICD10_OR_TITLE"
    assert unmatched["orphan"]["mkb10"] == ["Z99.9"]


def test_block_level_match_is_recorded_with_medium_confidence():
    calculator = _calculator([{"id": "meningitis", "name": "Менингит", "cr_id": "1_1", "mkb10": ["G00.1"]}])
    index = _index(
        [
            {
                "guideline_id": "55",
                "guideline_title": "Бактериальные менингиты",
                "guideline_year": None,
                "guideline_revision_date": None,
                "diagnosis_name": "Менингококковый менингит",
                "icd10_codes": ["G00.9"],
                "source_url": "",
            }
        ]
    )
    link = build_crosswalk(calculator, index)["links"][0]
    assert link["method"] == METHOD_ICD10_BLOCK
    assert link["confidence"] == METHOD_CONFIDENCE[METHOD_ICD10_BLOCK]
    assert link["matched_icd10"] == ["G00"]


def test_exact_title_match_is_used_when_icd10_does_not_overlap():
    # A69 (Лайм) vs L99 — different blocks, so only the title can link them.
    calculator = _calculator([{"id": "borreliosis", "name": "Болезнь Лайма у взрослых", "cr_id": "—", "mkb10": ["A69.2"]}])
    index = _index(
        [
            {
                "guideline_id": "77",
                "guideline_title": "Болезнь Лайма у взрослых",
                "guideline_year": 2023,
                "guideline_revision_date": None,
                "diagnosis_name": "Иксодовый клещевой боррелиоз",
                "icd10_codes": ["L99"],
                "source_url": "",
            }
        ]
    )
    link = build_crosswalk(calculator, index)["links"][0]
    assert link["method"] == METHOD_TITLE_EXACT
    assert link["confidence"] == METHOD_CONFIDENCE[METHOD_TITLE_EXACT]
    assert link["matched_icd10"] == []


def test_title_match_does_not_override_a_stronger_icd10_link():
    calculator = _calculator([{"id": "borreliosis", "name": "Болезнь Лайма у взрослых", "cr_id": "—", "mkb10": ["A69.2"]}])
    index = _index(
        [
            {
                "guideline_id": "77",
                "guideline_title": "Болезнь Лайма у взрослых",
                "guideline_year": 2023,
                "guideline_revision_date": None,
                "diagnosis_name": "Иксодовый клещевой боррелиоз",
                "icd10_codes": ["A69.9"],
                "source_url": "",
            }
        ]
    )
    link = build_crosswalk(calculator, index)["links"][0]
    assert link["method"] == METHOD_ICD10_BLOCK


def test_exact_icd10_wins_over_block_for_the_same_guideline():
    calculator = _calculator([{"id": "d", "name": "Д", "cr_id": "1_1", "mkb10": ["A41.5", "A40"]}])
    index = _index(
        [
            {
                "guideline_id": "9",
                "guideline_title": "Сепсис",
                "guideline_year": None,
                "guideline_revision_date": None,
                "diagnosis_name": "Сепсис",
                "icd10_codes": ["A41.5"],
                "source_url": "",
            }
        ]
    )
    link = build_crosswalk(calculator, index)["links"][0]
    assert link["method"] == METHOD_ICD10_EXACT
    # Only codes that actually participated in a match are recorded: A41.5
    # matched exactly, A41 matched at block level, A40 has no corpus counterpart.
    assert sorted(link["matched_icd10"]) == ["A41", "A41.5"]


def test_repeated_corpus_entries_collapse_into_one_link_per_guideline():
    calculator = _calculator([{"id": "d", "name": "Д", "cr_id": "1_1", "mkb10": ["J18"]}])
    index = _index(
        [
            {
                "guideline_id": "3",
                "guideline_title": "Пневмония",
                "guideline_year": 2024,
                "guideline_revision_date": None,
                "diagnosis_name": "Внебольничная пневмония",
                "icd10_codes": ["J18"],
                "source_url": "",
            },
            {
                "guideline_id": "3",
                "guideline_title": "Пневмония",
                "guideline_year": 2024,
                "guideline_revision_date": None,
                "diagnosis_name": "Пневмония у пожилых",
                "icd10_codes": ["J18"],
                "source_url": "",
            },
        ]
    )
    crosswalk = build_crosswalk(calculator, index)
    assert len(crosswalk["links"]) == 1
    assert crosswalk["links"][0]["diagnosis_names"] == ["Внебольничная пневмония", "Пневмония у пожилых"]
    assert crosswalk["links"][0]["guideline_years"] == [2024]


# ── determinism / drift guard ───────────────────────────────────────────────


def test_artifact_is_byte_identical_for_identical_inputs(tiny_pair):
    calculator, index = tiny_pair
    first = canonical_json(build_crosswalk(calculator, index))
    second = canonical_json(build_crosswalk(json.loads(json.dumps(calculator)), index))
    assert first == second


def test_embedded_guideline_links_do_not_look_like_input_drift(tiny_pair):
    """``build_db.py`` writes ``guideline_links`` back into the calculator DB.

    The input hash only covers the fields the crosswalk actually reads, so a
    second pass over the enriched database must produce the same artifact.
    """
    calculator, index = tiny_pair
    first = build_crosswalk(calculator, index)
    enriched = json.loads(json.dumps(calculator))
    for rec, links in zip(enriched["recommendations"], [first["links"]] * 3):
        rec["guideline_links"] = compact_links(first).get(rec["id"], [])
        rec["calculation_blocked"] = True
    second = build_crosswalk(enriched, index)
    assert second["content_sha256"] == first["content_sha256"]


def test_committed_artifact_matches_its_inputs():
    """Drift guard over the REAL committed artifact (the CI contract)."""
    rebuilt = build_crosswalk_from_paths(DEFAULT_CALCULATOR_DB, DEFAULT_DIAGNOSIS_INDEX)
    expected = json.dumps(rebuilt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    assert DEFAULT_OUTPUT.is_file(), (
        "clinical_engine/resources/calculator_crosswalk.json is missing — "
        "run `python -m clinical_engine.crosswalk --write`"
    )
    assert DEFAULT_OUTPUT.read_text(encoding="utf-8") == expected, (
        "committed crosswalk is stale — run `python -m clinical_engine.crosswalk --write`"
    )


def test_write_crosswalk_roundtrips(tmp_path, tiny_pair):
    calculator, index = tiny_pair
    crosswalk = build_crosswalk(calculator, index)
    path = write_crosswalk(crosswalk, tmp_path / "nested" / "crosswalk.json")
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["content_sha256"] == crosswalk["content_sha256"]


def test_content_sha256_is_stable():
    assert content_sha256({"b": 1, "a": [1, 2]}) == content_sha256({"a": [1, 2], "b": 1})


# ── safety contract ─────────────────────────────────────────────────────────


def test_artifact_declares_navigation_only_purpose(tiny_pair):
    calculator, index = tiny_pair
    meta = build_crosswalk(calculator, index)["meta"]
    assert meta["purpose"] == "NAVIGATION_ONLY"
    assert "не одобрение" in meta["warning"].lower() or "НЕ одобрение" in meta["warning"]
    assert "рубрикатор" in meta["id_namespace_note"].lower()


def test_no_link_field_claims_clinical_approval(tiny_pair):
    calculator, index = tiny_pair
    for link in build_crosswalk(calculator, index)["links"]:
        assert set(link) == {
            "disease_id",
            "disease_name",
            "cr_id",
            "guideline_id",
            "guideline_title",
            "guideline_years",
            "method",
            "confidence",
            "matched_icd10",
            "diagnosis_names",
        }


def test_coverage_counts_are_consistent(tiny_pair):
    calculator, index = tiny_pair
    crosswalk = build_crosswalk(calculator, index)
    coverage = crosswalk["meta"]["coverage"]
    assert coverage["calculator_diseases"] == 3
    assert coverage["linked_diseases"] == 1
    assert coverage["unmatched_diseases"] == 2
    assert coverage["links"] == len(crosswalk["links"])
    assert sum(coverage["links_by_method"].values()) == coverage["links"]


def test_committed_artifact_links_real_calculator_diseases_and_guidelines():
    """The shipped artifact must reference ids that actually exist on both sides."""
    db = json.loads(DEFAULT_CALCULATOR_DB.read_text(encoding="utf-8-sig"))
    index = json.loads(DEFAULT_DIAGNOSIS_INDEX.read_text(encoding="utf-8-sig"))
    crosswalk = CalculatorCrosswalk.load(DEFAULT_OUTPUT)

    disease_ids = {rec["id"] for rec in db["recommendations"]}
    guideline_ids = {entry["guideline_id"] for entry in index["entries"]}

    assert len(crosswalk) > 0
    for link in crosswalk.links:
        assert link["disease_id"] in disease_ids, link["disease_id"]
        assert link["guideline_id"] in guideline_ids, link["guideline_id"]

    coverage = crosswalk.coverage
    assert coverage["calculator_diseases"] == len(disease_ids)
    assert coverage["linked_diseases"] == len({link["disease_id"] for link in crosswalk.links})


# ── reader ──────────────────────────────────────────────────────────────────


def test_reader_lookups(tiny_pair, tmp_path):
    calculator, index = tiny_pair
    crosswalk = build_crosswalk(calculator, index)
    reader = CalculatorCrosswalk(crosswalk)

    assert [item["guideline_id"] for item in reader.for_disease("tonsillitis_child")] == ["1269"]
    assert [item["disease_id"] for item in reader.for_guideline("1269")] == ["tonsillitis_child"]
    assert reader.for_disease("unknown") == []
    assert reader.for_guideline("unknown") == []

    by_code = reader.for_icd10("J03")
    assert [item["guideline_id"] for item in by_code] == ["1269"]
    # block-level lookup resolves a sub-code to the same link
    assert [item["guideline_id"] for item in reader.for_icd10("J03.8")] == ["1269"]
    assert reader.for_icd10("не код") == []

    assert [item["guideline_id"] for item in reader.for_title("острый тонзиллит и фарингит")] == ["1269"]
    assert reader.for_title("Ничего") == []

    summary = reader.summary()
    assert summary["purpose"] == "NAVIGATION_ONLY"
    assert summary["links"] == 1
    assert reader.purpose == "NAVIGATION_ONLY"
    assert len(reader) == 1


def test_reader_is_fail_closed(tmp_path):
    with pytest.raises(CrosswalkBuildError):
        CalculatorCrosswalk.load(tmp_path / "absent.json")

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CrosswalkBuildError):
        CalculatorCrosswalk.load(bad)

    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"meta": {"artifact_type": "SOMETHING_ELSE"}, "links": []}), encoding="utf-8")
    with pytest.raises(CrosswalkBuildError):
        CalculatorCrosswalk.load(wrong)

    no_links = tmp_path / "no_links.json"
    no_links.write_text(
        json.dumps({"meta": {"artifact_type": "CALCULATOR_GUIDELINE_CROSSWALK"}}), encoding="utf-8"
    )
    with pytest.raises(CrosswalkBuildError):
        CalculatorCrosswalk.load(no_links)


def test_builder_rejects_unusable_inputs():
    with pytest.raises(CrosswalkBuildError):
        build_crosswalk({}, _index([]))
    with pytest.raises(CrosswalkBuildError):
        build_crosswalk(_calculator([]), {})


def test_builder_skips_entries_without_guideline_id():
    calculator = _calculator([{"id": "d", "name": "Д", "cr_id": "1_1", "mkb10": ["J03"]}])
    index = _index(
        [
            {
                "guideline_id": "",
                "guideline_title": "Без id",
                "diagnosis_name": "x",
                "icd10_codes": ["J03"],
            },
            "not-a-mapping",
        ]
    )
    crosswalk = build_crosswalk(calculator, index)
    assert crosswalk["links"] == []
    assert crosswalk["meta"]["coverage"]["skipped_index_entries"] == 2


# ── projections ─────────────────────────────────────────────────────────────


def test_compact_links_are_sorted_and_minimal(tiny_pair):
    calculator, index = tiny_pair
    compact = compact_links(build_crosswalk(calculator, index))
    assert list(compact) == ["tonsillitis_child"]
    assert compact["tonsillitis_child"] == [
        {
            "guideline_id": "1269",
            "title": "Острый тонзиллит и фарингит",
            "years": [2024],
            "method": METHOD_ICD10_EXACT,
            "codes": ["J03"],  # only the code that actually matched
        }
    ]
    # diagnosis_names stays in the artifact and is dropped from the projection
    assert "diagnosis_names" not in compact["tonsillitis_child"][0]


def test_crosswalk_summary_carries_no_hashes_of_inputs(tiny_pair):
    calculator, index = tiny_pair
    summary = crosswalk_summary(build_crosswalk(calculator, index))
    assert summary["purpose"] == "NAVIGATION_ONLY"
    assert summary["content_sha256"].startswith("sha256:")
    assert "inputs_sha256" not in summary
    assert summary["confidence_by_method"] == METHOD_CONFIDENCE
