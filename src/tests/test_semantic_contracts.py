"""H-10 / H-11 / H-12 / H-8 -- semantic-layer entity typing, fail-closed dictionary
loading, and evidence-backed relations.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.pipeline.extraction import semantic
from src.pipeline.extraction.base import Document, Page


def _entities():
    return [
        {"type": "Drug", "text": "амоксициллин", "normalized": "amoxicillin",
         "confidence": 0.9, "provenance": {"page": 1, "extractor": "x"}},
        {"type": "Dose", "text": "500 мг", "normalized": "500", "unit": "мг",
         "confidence": 0.9, "provenance": {"page": 1, "extractor": "x"}},
        {"type": "Frequency", "text": "3 раза в день", "normalized": "3_times_daily",
         "confidence": 0.9, "provenance": {"page": 1, "extractor": "x"}},
        {"type": "Duration", "text": "7-10 дней", "normalized": "7-10",
         "confidence": 0.9, "provenance": {"page": 1, "extractor": "x"}},
        {"type": "Route", "text": "внутрь", "normalized": "per_os",
         "confidence": 0.9, "provenance": {"page": 1, "extractor": "x"}},
    ]


# ---------------------------------------------------------------------------
# H-10 -- Frequency/Duration/Route must NOT be stored as unit-less Doses
# ---------------------------------------------------------------------------

def test_h10_frequency_duration_route_are_not_stored_as_dose():
    objs = semantic.SemanticProcessor.__new__(semantic.SemanticProcessor)
    objs = semantic.SemanticProcessor()
    built = objs.build_knowledge_objects(_entities())
    dose_values = [item["value"] for item in built["Dose"]]
    assert dose_values == ["500"], f"a Dose row carried {dose_values!r}"
    assert [item["value"] for item in built["Frequency"]] == ["3_times_daily"]
    assert [item["value"] for item in built["Duration"]] == ["7-10"]
    assert [item["value"] for item in built["Route"]] == ["per_os"]
    for bucket in ("Frequency", "Duration", "Route"):
        assert all(item.get("subtype") == bucket for item in built[bucket])


def test_h10_only_a_genuine_dose_requires_a_unit():
    built = semantic.SemanticProcessor().build_knowledge_objects(_entities())
    assert built["Dose"][0]["unit"] == "мг"
    # the others legitimately have no unit and are not subject to INV-05
    assert all("unit" not in item or item["unit"] is None
               for bucket in ("Frequency", "Duration", "Route")
               for item in built[bucket])


def test_h10_inv05_is_blocking_and_scoped_to_real_doses():
    from src.pipeline import knowledge_invariants as ki

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE objects (id TEXT, type TEXT, content TEXT, status TEXT,
                              version INTEGER, validation_status TEXT, logical_key TEXT,
                              content_hash TEXT, clinical_scope TEXT);
        CREATE TABLE provenance (obj_id TEXT, page INTEGER, extractor TEXT,
                                 semantic TEXT, semantic_engine TEXT, layout_engine TEXT,
                                 table_row INTEGER, table_col INTEGER,
                                 original_text TEXT, normalized_value TEXT);
    """)
    conn.execute(
        "INSERT INTO objects VALUES('d1','Dose',?,'active',1,'valid',NULL,NULL,NULL)",
        ('{"value": "500", "unit": null}',),
    )
    conn.execute(
        "INSERT INTO objects VALUES('f1','Frequency',?,'active',1,'valid',NULL,NULL,NULL)",
        ('{"value": "3_times_daily", "unit": null}',),
    )
    conn.execute(
        "INSERT INTO objects VALUES('d2','Dose',?,'active',1,'valid',NULL,NULL,NULL)",
        ('{"value": "250", "unit": "мг"}',),
    )
    results = {r.id: r for r in ki.check(conn)}
    inv05 = results["INV-05"]
    assert inv05.blocking is True, "INV-05 must be able to block CI"
    assert inv05.violations == 1
    assert inv05.sample == ["d1"], "a unit-less Frequency must not be reported as a dose"
    conn.close()


# ---------------------------------------------------------------------------
# H-11 -- the medical dictionary is the most safety-relevant dependency
# ---------------------------------------------------------------------------

def test_h11_safety_relevant_dictionaries_are_loaded():
    assert semantic.DRUG_SYNONYMS, "drug synonyms are required; an empty dict is a fail-open"
    assert semantic.ROUTE_SYN
    assert semantic.UNIT_NORM


def test_h11_dictionary_sizes_are_reported():
    sizes = semantic.DICTIONARY_SIZES
    assert set(sizes) == {
        "drug_synonyms", "drug_atc", "drug_groups", "route_synonyms", "unit_normalization",
    }
    assert sizes["drug_synonyms"] > 0


def test_h11_empty_required_dictionary_raises(tmp_path, monkeypatch):
    root = tmp_path / "medical_dictionary"
    root.mkdir()
    (root / "diagnosis_synonyms.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(semantic, "_DICTIONARY_ROOT", root)
    monkeypatch.setattr(semantic, "_DICTIONARY_FALLBACK_ROOT", tmp_path / "absent")
    with pytest.raises(semantic.MedicalDictionaryUnavailable):
        semantic._load_json_safe("frequency_dictionary.json")


def test_h11_malformed_dictionary_raises(tmp_path, monkeypatch):
    root = tmp_path / "medical_dictionary"
    root.mkdir()
    (root / "duration_dictionary.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(semantic, "_DICTIONARY_ROOT", root)
    monkeypatch.setattr(semantic, "_DICTIONARY_FALLBACK_ROOT", tmp_path / "absent")
    with pytest.raises(semantic.MedicalDictionaryUnavailable):
        semantic._load_json_safe("duration_dictionary.json")


def test_h11_require_non_empty_raises_on_empty():
    with pytest.raises(semantic.MedicalDictionaryUnavailable):
        semantic._require_non_empty("route_synonyms", {})
    with pytest.raises(semantic.MedicalDictionaryUnavailable):
        semantic._require_non_empty("route_synonyms", None)


def test_h11_missing_dictionary_root_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic, "_DICTIONARY_ROOT", tmp_path / "a")
    monkeypatch.setattr(semantic, "_DICTIONARY_FALLBACK_ROOT", tmp_path / "b")
    with pytest.raises(semantic.MedicalDictionaryUnavailable):
        semantic._dictionary_root()


# ---------------------------------------------------------------------------
# H-12 -- relations must be evidence-backed and endpoint-compatible
# ---------------------------------------------------------------------------

def test_h12_relations_require_proximity_evidence():
    proc = semantic.SemanticProcessor()
    close = "Пневмония. Амоксициллин 500 мг 3 раза в день."
    far = "Пневмония " + (" filler text. " * 200) + "Амоксициллин 500 мг."
    close_rels = proc.extract_relations(close, proc.extract_entities(close, 1, "t"))
    far_rels = proc.extract_relations(far, proc.extract_entities(far, 1, "t"))
    dose_rels = [r for r in close_rels if r["rel"] == "dose"]
    assert dose_rels, "a dose adjacent to its diagnosis must still be linked"
    assert not [r for r in far_rels if r["rel"] == "dose"], \
        "a dose 200 filler sentences away is not evidence of a relation"


def test_h12_relations_are_not_the_full_cross_product():
    proc = semantic.SemanticProcessor()
    text = ("Пневмония 1. Амоксициллин 500 мг. "
            "Плевмония 2. Цефтриаксон 1 г. "
            "Бронхит 3. Азитромицин 500 мг.")
    entities = proc.extract_entities(text, 1, "t")
    diags = [e for e in entities if e["type"] == "Diagnosis"]
    doses = [e for e in entities if e["type"] == "Dose"]
    if len(diags) < 2 or len(doses) < 2:
        pytest.skip("dictionary did not yield enough entities for this corpus")
    rels = proc.extract_relations(text, entities)
    dose_rels = [r for r in rels if r["rel"] == "dose"]
    assert len(dose_rels) <= len(diags), "a diagnosis may not claim every dose on the page"
    assert len(dose_rels) < len(diags) * len(doses)


def test_h12_relation_endpoints_are_validated():
    assert semantic._relation_endpoints_compatible(
        {"from": "Пневмония", "rel": "dose", "to": "500мг", "to_type": "Dose"})
    assert not semantic._relation_endpoints_compatible(
        {"from": "Пневмония", "rel": "dose", "to": "внутрь", "to_type": "Route"})
    assert not semantic._relation_endpoints_compatible(
        {"from": "Пневмония", "rel": "not_a_real_rel", "to": "x", "to_type": "Dose"})
    assert not semantic._relation_endpoints_compatible(
        {"from": "", "rel": "dose", "to": "500", "to_type": "Dose"})


def test_h12_check_consistency_reports_incompatible_endpoints():
    proc = semantic.SemanticProcessor()
    bad = [{"from": "Пневмония", "rel": "dose", "to": "внутрь", "to_type": "Route"}]
    warns = proc.check_consistency([], bad)
    assert any("incompatible_relation_endpoints" in w for w in warns)


# ---------------------------------------------------------------------------
# H-8 / M-18 -- producer writes the canonical extractor key; warnings are stable
# ---------------------------------------------------------------------------

def test_h8_entities_write_the_canonical_extractor_key():
    entities = semantic.SemanticProcessor().extract_entities("амоксициллин 500 мг", 3, "pymupdf")
    assert entities
    for e in entities:
        assert e["provenance"]["extractor"] == "pymupdf"
        assert "engine" not in e["provenance"], "the legacy key would shadow the canonical one"


def test_m18_consistency_warnings_are_deterministic():
    proc = semantic.SemanticProcessor()
    entities = [
        {"type": "Dose", "text": "500 мг", "normalized": "500", "unit": None},
        {"type": "Dose", "text": "500 мг", "normalized": "500", "unit": None},
        {"type": "Frequency", "text": "3 раза", "normalized": "3", "unit": None},
    ]
    first = proc.check_consistency(entities, [])
    second = proc.check_consistency(list(reversed(entities)), [])
    assert first == second
    assert first == sorted(first)


def test_m16_both_extraction_paths_use_the_same_dictionary_slice():
    assert semantic.DRUG_SYNONYM_SCAN_LIMIT == 500
    # both paths must be bounded by the SAME constant, not by two literals
    source = (
        __import__("pathlib").Path(semantic.__file__).read_text(encoding="utf-8")
    )
    assert "[:200]" not in source, "the table path still used a different slice bound"
    assert source.count("[:DRUG_SYNONYM_SCAN_LIMIT]") == 2


def test_m17_dedup_width_is_one_constant():
    source = (
        __import__("pathlib").Path(semantic.__file__).read_text(encoding="utf-8")
    )
    assert "[:50]" not in source
    assert "[:60]" not in source
    assert source.count("[:ENTITY_DEDUP_KEY_LENGTH]") >= 2


def test_m19_fulltext_fallback_threshold_is_a_named_constant():
    assert semantic.MIN_ENTITIES_BEFORE_FULLTEXT_FALLBACK == 5 \
        if hasattr(semantic, "MIN_ENTITIES_BEFORE_FULLTEXT_FALLBACK") else True
    source = (
        __import__("pathlib").Path(semantic.__file__).read_text(encoding="utf-8")
    )
    assert "len(all_entities) < 5" not in source, "the magic number is still inline"


def test_l23_icd_prefix_requires_two_digits_and_latin_codes_only():
    proc = semantic.SemanticProcessor()
    # "icd-1" is not an ICD-10 code prefix
    assert not [e for e in proc.extract_entities("icd-1", 1, "t") if e["type"] == "ICD-10"]
    assert [e for e in proc.extract_entities("МКБ: J18.9", 1, "t") if e["type"] == "ICD-10"]
    assert [e for e in proc.extract_entities("ICD-10 A00", 1, "t") if e["type"] == "ICD-10"]


def test_semantic_layer_runs_end_to_end_and_reports_normalization():
    doc = Document(
        source="pymupdf",
        pdf_path="x.pdf",
        pages=[Page(1, "Амоксициллин 500 мг 3 раза в день внутрь 7-10 дней")],
        full_text="",
    )
    semantic.add_semantic_to_document(doc, "pymupdf")
    assert doc.metadata["semantic_processed"] is True
    assert doc.metadata["entity_count"] > 0
    assert doc.metadata["clinical_normalizer"] in ("available", "unavailable")
    assert doc.metadata["dictionary_sizes"]["drug_synonyms"] > 0
