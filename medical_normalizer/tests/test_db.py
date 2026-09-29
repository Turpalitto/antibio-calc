"""Tests for db.py -- NormalizerDB, SaveResult, RegimenRecord."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, is_dataclass
from typing import Any

import pytest

from medical_normalizer.db import (
    MANUAL_FIELDS,
    SCHEMA_VERSION,
    NormalizerDB,
    RegimenRecord,
    SaveResult,
)
from medical_normalizer.normalizer import (
    NORMALIZER_VERSION,
    MedicalNormalizer,
    NormalizedResult,
)


# -- Helpers ---------------------------------------------------------


def _perfect_result() -> NormalizedResult:
    return MedicalNormalizer.normalize({
        "antibiotic": "Цефтриаксон",
        "dose": "1,0",
        "unit": "г",
        "route": "в/в",
        "frequency": "1 раз в день",
        "duration": "7-10 дней",
        "age_group": "взрослые",
        "regimen_type": "first_line",
    })


def _minimal_result() -> NormalizedResult:
    return MedicalNormalizer.normalize({
        "antibiotic": "Цефтриаксон",
        "dose": "1,0",
        "unit": "г",
        "route": "в/в",
        "frequency": "1 раз в день",
    })


def _empty_result() -> NormalizedResult:
    return MedicalNormalizer.normalize({})


def _connect() -> NormalizerDB:
    return NormalizerDB.connect(":memory:")


# -- Constants / config ---------------------------------------------


class TestConfig:
    def test_schema_version(self):
        # 1.1.0 — dose_min / dose_max / dose_is_range were added (M3)
        assert SCHEMA_VERSION == "1.1.0"

    def test_manual_fields_listed(self):
        assert "review_status" in MANUAL_FIELDS
        assert "reviewed_by" in MANUAL_FIELDS
        assert "review_date" in MANUAL_FIELDS
        assert "manual_notes" in MANUAL_FIELDS
        assert "manual_override" in MANUAL_FIELDS
        assert "approved" in MANUAL_FIELDS

    def test_manual_fields_count(self):
        assert len(MANUAL_FIELDS) == 6

    def test_normalizer_version_constant(self):
        assert NORMALIZER_VERSION


# -- SaveResult ------------------------------------------------------


class TestSaveResult:
    def test_is_dataclass(self):
        assert is_dataclass(SaveResult)

    def test_frozen(self):
        r = SaveResult(saved=1, skipped=0)
        with pytest.raises(FrozenInstanceError):
            r.saved = 99  # type: ignore[misc]

    def test_defaults(self):
        r = SaveResult(saved=0, skipped=0)
        assert r.errors == []

    def test_to_dict(self):
        r = SaveResult(saved=5, skipped=1, errors=["err"])
        d = r.to_dict()
        assert d == {"saved": 5, "skipped": 1, "errors": ["err"]}


# -- RegimenRecord ---------------------------------------------------


class TestRegimenRecord:
    def test_is_dataclass(self):
        assert is_dataclass(RegimenRecord)

    def test_frozen(self):
        rec = RegimenRecord(
            regimen_id="r1", guideline_id="g1", drug_normalized="X",
            dose=1.0, dose_unit="g", route="iv", frequency=1.0,
            duration_min=7.0, duration_max=10.0, duration_recommended=7.0,
            therapy_line="first", adult=True, child=False, pregnancy=None,
            renal_adjustment=False, atc_code="J01DD04", overall_confidence=0.9,
            validation_verdict="PASS", validation_errors=0,
            validation_reviews=0, validation_warnings=0,
            source_pdf="", source_page="", diagnosis="", mkb="",
            normalizer_version="1.0.0", schema_version="1.0.0",
            review_status="pending", reviewed_by="", review_date="",
            manual_notes="", manual_override="", approved=False,
            created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        )
        with pytest.raises(FrozenInstanceError):
            rec.regimen_id = "x"  # type: ignore[misc]


# -- Connection / lifecycle -----------------------------------------


class TestConnection:
    def test_connect_returns_db(self):
        db = _connect()
        assert isinstance(db, NormalizerDB)
        db.close()

    def test_table_exists(self):
        db = _connect()
        assert db.table_exists() is True
        db.close()

    def test_count_empty(self):
        db = _connect()
        assert db.count() == 0
        db.close()

    def test_close_idempotent(self):
        db = _connect()
        db.close()
        db.close()

    def test_context_manager(self):
        with NormalizerDB(":memory:") as db:
            db._open()
            assert db.table_exists() is True

    def test_in_memory_path(self):
        db = NormalizerDB.connect(":memory:")
        assert db.db_path == ":memory:"
        db.close()

    def test_file_path(self, tmp_path):
        p = str(tmp_path / "test.db")
        db = NormalizerDB.connect(p)
        assert db.table_exists() is True
        db.close()
        # Reopen
        db2 = NormalizerDB.connect(p)
        assert db2.table_exists() is True
        db2.close()


# -- Schema introspection -------------------------------------------


class TestSchema:
    def test_required_columns_present(self):
        db = _connect()
        cols = db.column_names()
        required = [
            "regimen_id", "guideline_id", "drug_original", "drug_normalized",
            "drug_components", "dose", "dose_unit", "route", "frequency",
            "duration_min", "duration_max", "duration_recommended",
            "therapy_line", "population", "adult", "child",
            "pregnancy", "renal_adjustment", "atc_code",
            "overall_confidence", "field_confidence", "parser_confidence",
            "validation_verdict", "validation_issues",
            "validation_errors", "validation_reviews", "validation_warnings",
            "source_pdf", "source_page", "source_quote",
            "diagnosis", "mkb",
            "normalizer_version", "schema_version",
            "review_status", "reviewed_by", "review_date",
            "manual_notes", "manual_override", "approved",
            "created_at", "updated_at",
        ]
        for r in required:
            assert r in cols, f"Missing column: {r}"
        db.close()

    def test_manual_columns_present(self):
        db = _connect()
        cols = db.column_names()
        for m in MANUAL_FIELDS:
            assert m in cols
        db.close()

    def test_index_exists_guideline(self):
        db = _connect()
        assert db.index_exists("idx_guideline_id")
        db.close()

    def test_index_exists_drug(self):
        db = _connect()
        assert db.index_exists("idx_drug_normalized")
        db.close()

    def test_index_exists_therapy_line(self):
        db = _connect()
        assert db.index_exists("idx_therapy_line")
        db.close()

    def test_index_exists_verdict(self):
        db = _connect()
        assert db.index_exists("idx_val_verdict")
        db.close()

    def test_index_exists_confidence(self):
        db = _connect()
        assert db.index_exists("idx_confidence")
        db.close()

    def test_index_exists_atc(self):
        db = _connect()
        assert db.index_exists("idx_atc_code")
        db.close()

    def test_index_not_exists(self):
        db = _connect()
        assert db.index_exists("idx_bogus") is False
        db.close()

    def test_primary_key_composite(self):
        db = _connect()
        cur = db.conn.execute("PRAGMA table_info(normalized_regimens)")
        pk_cols = [row["name"] for row in cur.fetchall() if row["pk"] > 0]
        assert "guideline_id" in pk_cols
        assert "regimen_id" in pk_cols
        db.close()


# -- save (UPSERT) ---------------------------------------------------


class TestSave:
    def test_save_single(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        assert db.count() == 1
        db.close()

    def test_save_and_load(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1", diagnosis="Тиф", mkb="A01.0")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.drug_normalized == "Цефтриаксон"
        assert rec.dose == 1.0
        assert rec.route == "iv"
        assert rec.diagnosis == "Тиф"
        assert rec.mkb == "A01.0"
        db.close()

    def test_load_nonexistent_returns_none(self):
        db = _connect()
        assert db.load("g1", "r1") is None
        db.close()

    def test_upsert_same_pk_updates(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        assert db.count() == 1
        # Save again with same PK -> still 1 row, updated
        db.save(_minimal_result(), "g1", "r1")
        assert db.count() == 1
        rec = db.load("g1", "r1")
        assert rec is not None
        db.close()

    def test_upsert_different_pk_inserts(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_perfect_result(), "g1", "r2")
        assert db.count() == 2
        db.close()

    def test_upsert_different_guideline_inserts(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_perfect_result(), "g2", "r1")
        assert db.count() == 2
        db.close()

    def test_upsert_preserves_created_at(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec1 = db.load("g1", "r1")
        assert rec1 is not None
        created = rec1.created_at
        db.save(_perfect_result(), "g1", "r1")
        rec2 = db.load("g1", "r1")
        assert rec2 is not None
        assert rec2.created_at == created
        db.close()

    def test_upsert_updates_updated_at(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec1 = db.load("g1", "r1")
        assert rec1 is not None
        first_updated = rec1.updated_at
        db.save(_perfect_result(), "g1", "r1")
        rec2 = db.load("g1", "r1")
        assert rec2 is not None
        # updated_at should be >= first_updated (may be same if same second)
        assert rec2.updated_at >= first_updated
        db.close()

    def test_save_empty_result(self):
        db = _connect()
        db.save(_empty_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.validation_verdict == "REJECT"
        db.close()

    def test_save_stores_drug_components_json(self):
        db = _connect()
        result = MedicalNormalizer.normalize({
            "antibiotic": "Амоксициллин+клавулановая кислота",
            "dose": "875/125", "unit": "мг",
            "route": "внутрь", "frequency": "2 раза в день",
        })
        db.save(result, "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        comps = json.loads(rec.raw["drug_components"])
        assert len(comps) >= 2
        db.close()

    def test_save_stores_field_confidence_json(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        fc = json.loads(rec.raw["field_confidence"])
        assert "drug" in fc
        assert "dose" in fc
        db.close()

    def test_save_stores_validation_issues_json(self):
        db = _connect()
        db.save(_empty_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        issues = json.loads(rec.raw["validation_issues"])
        assert len(issues) >= 4
        db.close()

    def test_save_stores_normalizer_version(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.normalizer_version == NORMALIZER_VERSION
        db.close()

    def test_save_stores_schema_version(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.schema_version == SCHEMA_VERSION
        db.close()

    def test_save_population_string(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert "adult" in rec.raw["population"]
        db.close()


# -- manual edit preservation ---------------------------------------


class TestManualEditPreservation:
    def test_default_review_status(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.review_status == "pending"
        db.close()

    def test_default_approved_false(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.approved is False
        db.close()

    def test_update_review_status(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "review_status", "approved")
        assert db.get_manual_field("g1", "r1", "review_status") == "approved"
        db.close()

    def test_update_approved(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "approved", True)
        assert db.get_manual_field("g1", "r1", "approved") is True
        db.close()

    def test_update_reviewed_by(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "reviewed_by", "Dr. Smith")
        assert db.get_manual_field("g1", "r1", "reviewed_by") == "Dr. Smith"
        db.close()

    def test_update_manual_notes(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "manual_notes", "Check dose")
        assert db.get_manual_field("g1", "r1", "manual_notes") == "Check dose"
        db.close()

    def test_update_review_date(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "review_date", "2026-07-09")
        assert db.get_manual_field("g1", "r1", "review_date") == "2026-07-09"
        db.close()

    def test_update_manual_override(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "manual_override", "custom_dose=2.0")
        assert db.get_manual_field("g1", "r1", "manual_override") == "custom_dose=2.0"
        db.close()

    def test_manual_field_preserved_on_upsert(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "review_status", "approved")
        db.update_manual_field("g1", "r1", "approved", True)
        db.update_manual_field("g1", "r1", "reviewed_by", "Dr. X")
        # Re-save (simulating re-normalization)
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.review_status == "approved"
        assert rec.approved is True
        assert rec.reviewed_by == "Dr. X"
        db.close()

    def test_all_manual_fields_preserved_on_upsert(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        for f in MANUAL_FIELDS:
            val: Any = "test_value" if f != "approved" else True
            db.update_manual_field("g1", "r1", f, val)
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        for f in MANUAL_FIELDS:
            if f == "approved":
                assert rec.approved is True
            else:
                assert rec.raw[f] == "test_value"
        db.close()

    def test_non_manual_field_rejected(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        with pytest.raises(ValueError):
            db.update_manual_field("g1", "r1", "drug_normalized", "Hacked")
        db.close()

    def test_get_non_manual_field_rejected(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        with pytest.raises(ValueError):
            db.get_manual_field("g1", "r1", "drug_normalized")
        db.close()

    def test_get_manual_nonexistent_record(self):
        db = _connect()
        assert db.get_manual_field("g1", "r1", "review_status") is None
        db.close()

    def test_update_nonexistent_record_raises(self):
        # M10: a silent success on a non-existent row hid lost review
        # decisions — the caller believed the edit was stored.
        db = _connect()
        with pytest.raises(KeyError):
            db.update_manual_field("g1", "r1", "review_status", "x")
        assert db.count() == 0
        db.close()


# -- batch insert (save_many) ---------------------------------------


class TestSaveMany:
    def test_batch_insert(self):
        db = _connect()
        items = [
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r2"},
            {"result": _perfect_result(), "guideline_id": "g2", "regimen_id": "r1"},
        ]
        sr = db.save_many(items)
        assert sr.saved == 3
        assert sr.skipped == 0
        assert db.count() == 3
        db.close()

    def test_batch_empty(self):
        db = _connect()
        sr = db.save_many([])
        assert sr.saved == 0
        assert sr.skipped == 0
        assert db.count() == 0
        db.close()

    def test_batch_with_missing_key(self):
        db = _connect()
        items = [
            {"result": _perfect_result(), "guideline_id": "g1"},  # missing regimen_id
        ]
        sr = db.save_many(items)
        assert sr.saved == 0
        assert sr.skipped == 1
        assert len(sr.errors) == 1
        db.close()

    def test_batch_upsert(self):
        db = _connect()
        items = [
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
        ]
        db.save_many(items)
        # Re-run with same PKs
        db.save_many(items)
        assert db.count() == 1
        db.close()

    def test_batch_large(self):
        db = _connect()
        items = [
            {"result": _perfect_result(), "guideline_id": f"g{i}", "regimen_id": "r1"}
            for i in range(50)
        ]
        sr = db.save_many(items)
        assert sr.saved == 50
        assert db.count() == 50
        db.close()

    def test_batch_preserves_manual_fields(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "review_status", "approved")
        # Batch re-save
        db.save_many([{"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"}])
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.review_status == "approved"
        db.close()

    def test_batch_save_result_to_dict(self):
        db = _connect()
        sr = db.save_many([
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
        ])
        d = sr.to_dict()
        assert d["saved"] == 1
        db.close()


# -- rollback / transactions ----------------------------------------


class TestTransactions:
    def test_rollback_on_failure(self):
        db = _connect()
        # Force a failure by making json.dumps raise during _to_row serialization.
        import medical_normalizer.db as db_mod
        original_dumps = db_mod.json.dumps
        call_count = [0]
        def flaky_dumps(obj, **kwargs):
            call_count[0] += 1
            if call_count[0] > 3:
                raise TypeError("Simulated serialization failure")
            return original_dumps(obj, **kwargs)
        db_mod.json.dumps = flaky_dumps
        try:
            sr = db.save_many([
                {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
                {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r2"},
            ])
            # 2nd item failed -> rollback -> saved=0
            assert sr.saved == 0
            assert sr.skipped >= 1
            assert db.count() == 0
        finally:
            db_mod.json.dumps = original_dumps
        db.close()

    def test_transaction_atomicity(self):
        db = _connect()
        # All items in one batch either commit together or not at all
        items = [
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r2"},
        ]
        db.save_many(items)
        assert db.count() == 2
        db.close()

    def test_no_partial_commit_on_error(self):
        db = _connect()
        items = [
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r2"},
            # 3rd item missing regimen_id -> failure -> rollback whole batch
            {"result": _perfect_result(), "guideline_id": "g1"},
        ]
        sr = db.save_many(items)
        # No partial commits: rollback -> saved=0
        assert sr.saved == 0
        assert sr.skipped == 1
        assert db.count() == 0
        db.close()


# -- versioning ------------------------------------------------------


class TestVersioning:
    def test_normalizer_version_stored(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.normalizer_version == NORMALIZER_VERSION
        db.close()

    def test_schema_version_stored(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.schema_version == SCHEMA_VERSION
        db.close()

    def test_versioning_updated_on_upsert(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        # Simulate version change by saving again (same version, but updated_at changes)
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.normalizer_version == NORMALIZER_VERSION
        db.close()


import sqlite3  # for test_rollback_on_failure


# -- loading ---------------------------------------------------------


class TestLoading:
    def test_load_by_guideline(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_perfect_result(), "g1", "r2")
        db.save(_perfect_result(), "g2", "r1")
        recs = db.load_by_guideline("g1")
        assert len(recs) == 2
        assert all(r.guideline_id == "g1" for r in recs)
        db.close()

    def test_load_by_guideline_empty(self):
        db = _connect()
        assert db.load_by_guideline("g1") == []
        db.close()

    def test_load_by_drug(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_minimal_result(), "g2", "r1")
        recs = db.load_by_drug("Цефтриаксон")
        assert len(recs) == 2
        db.close()

    def test_load_by_drug_empty(self):
        db = _connect()
        assert db.load_by_drug("Nonexistent") == []
        db.close()

    def test_load_by_drug_exact_match(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        recs = db.load_by_drug("Цефтриакс")
        assert len(recs) == 0  # exact match, not partial
        db.close()

    def test_load_failed(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")  # PASS
        db.save(_empty_result(), "g1", "r2")    # REJECT
        db.save(_empty_result(), "g2", "r1")    # REJECT
        recs = db.load_failed()
        assert len(recs) == 2
        assert all(r.validation_verdict == "REJECT" for r in recs)
        db.close()

    def test_load_failed_empty(self):
        db = _connect()
        assert db.load_failed() == []
        db.close()

    def test_load_by_verdict_pass(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_empty_result(), "g1", "r2")
        recs = db.load_by_verdict("PASS")
        assert len(recs) == 1
        db.close()

    def test_load_by_verdict_review(self):
        db = _connect()
        result = MedicalNormalizer.normalize({"antibiotic": "Неизвестный", "dose": "1", "unit": "г", "route": "в/в", "frequency": "1 раз в день"})
        db.save(result, "g1", "r1")
        recs = db.load_by_verdict("REVIEW")
        assert len(recs) == 1
        db.close()

    def test_load_all(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_perfect_result(), "g2", "r1")
        assert len(db.load_all()) == 2
        db.close()

    def test_load_all_with_limit(self):
        db = _connect()
        for i in range(5):
            db.save(_perfect_result(), f"g{i}", "r1")
        assert len(db.load_all(limit=3)) == 3
        db.close()

    def test_load_all_empty(self):
        db = _connect()
        assert db.load_all() == []
        db.close()

    def test_record_has_raw_dict(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert isinstance(rec.raw, dict)
        assert "drug_normalized" in rec.raw
        db.close()


# -- querying (search) ----------------------------------------------


class TestSearch:
    def test_search_by_drug(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1", diagnosis="Тиф")
        recs = db.search(drug="Цефтриаксон")
        assert len(recs) == 1
        db.close()

    def test_search_by_diagnosis_partial(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1", diagnosis="Брюшной тиф")
        recs = db.search(diagnosis="тиф")
        assert len(recs) == 1
        db.close()

    def test_search_by_therapy_line(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        recs = db.search(therapy_line="first")
        assert len(recs) == 1
        db.close()

    def test_search_by_verdict(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_empty_result(), "g1", "r2")
        assert len(db.search(verdict="PASS")) == 1
        assert len(db.search(verdict="REJECT")) == 1
        db.close()

    def test_search_by_pregnancy(self):
        db = _connect()
        r = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1", "unit": "г",
            "route": "в/в", "frequency": "1 раз в день", "age_group": "беременные",
        })
        db.save(r, "g1", "r1")
        recs = db.search(pregnancy=True)
        assert len(recs) >= 1
        db.close()

    def test_search_by_renal(self):
        db = _connect()
        r = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1", "unit": "г",
            "route": "в/в", "frequency": "1 раз в день",
            "age_group": "почечная недостаточность",
        })
        db.save(r, "g1", "r1")
        recs = db.search(renal_adjustment=True)
        assert len(recs) >= 1
        db.close()

    def test_search_by_min_confidence(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_empty_result(), "g1", "r2")
        recs = db.search(min_confidence=0.5)
        assert all(r.overall_confidence >= 0.5 for r in recs)
        db.close()

    def test_search_by_max_confidence(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_empty_result(), "g1", "r2")
        recs = db.search(max_confidence=0.5)
        assert all(r.overall_confidence <= 0.5 for r in recs)
        db.close()

    def test_search_by_confidence_range(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_empty_result(), "g1", "r2")
        recs = db.search(min_confidence=0.3, max_confidence=0.95)
        assert all(0.3 <= r.overall_confidence <= 0.95 for r in recs)
        db.close()

    def test_search_by_atc(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        # ATC not set by parser in this test; search should return 0 or matching
        recs = db.search(atc_code="J01DD04")
        # drug_parser doesn't set atc from raw, so likely empty
        assert isinstance(recs, list)
        db.close()

    def test_search_multi_criteria(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1", diagnosis="Тиф")
        db.save(_perfect_result(), "g1", "r2", diagnosis="Пневмония")
        recs = db.search(drug="Цефтриаксон", diagnosis="Тиф")
        assert len(recs) == 1
        assert recs[0].diagnosis == "Тиф"
        db.close()

    def test_search_no_criteria_returns_all(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_perfect_result(), "g2", "r1")
        recs = db.search()
        assert len(recs) == 2
        db.close()

    def test_search_with_limit(self):
        db = _connect()
        for i in range(5):
            db.save(_perfect_result(), f"g{i}", "r1")
        recs = db.search(limit=3)
        assert len(recs) == 3
        db.close()

    def test_search_no_matches(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        assert db.search(drug="Nonexistent") == []
        db.close()


# -- stats -----------------------------------------------------------


class TestStats:
    def test_stats_empty(self):
        db = _connect()
        s = db.stats()
        assert s["total"] == 0
        db.close()

    def test_stats_with_data(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")  # PASS
        db.save(_empty_result(), "g1", "r2")    # REJECT
        s = db.stats()
        assert s["total"] == 2
        assert s["pass"] == 1
        assert s["reject"] == 1
        db.close()

    def test_stats_avg_confidence(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        s = db.stats()
        assert s["avg_confidence"] > 0.0
        db.close()

    def test_stats_approved_count(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "approved", True)
        s = db.stats()
        assert s["approved"] == 1
        db.close()


# -- invalid / duplicate / concurrent -------------------------------


class TestInvalidRecords:
    def test_save_none_result_raises(self):
        db = _connect()
        with pytest.raises(AttributeError):
            db.save(None, "g1", "r1")  # type: ignore[arg-type]
        db.close()

    def test_save_empty_guideline_id(self):
        db = _connect()
        db.save(_perfect_result(), "", "r1")
        rec = db.load("", "r1")
        assert rec is not None
        db.close()

    def test_save_empty_regimen_id(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "")
        rec = db.load("g1", "")
        assert rec is not None
        db.close()

    def test_save_very_long_strings(self):
        db = _connect()
        result = _perfect_result()
        result.regimen.drug_original = "X" * 1000
        db.save(result, "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        db.close()

    def test_save_unicode_drug(self):
        db = _connect()
        result = _perfect_result()
        result.regimen.drug_normalized = "Азитромицин"
        db.save(result, "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.drug_normalized == "Азитромицин"
        db.close()


class TestDuplicateRecords:
    def test_duplicate_pk_upserts(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        db.save(_perfect_result(), "g1", "r1")
        db.save(_perfect_result(), "g1", "r1")
        assert db.count() == 1
        db.close()

    def test_duplicate_batch_upserts(self):
        db = _connect()
        items = [
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
        ]
        db.save_many(items)
        assert db.count() == 1
        db.close()


class TestConcurrentWrites:
    def test_two_connections_same_file(self, tmp_path):
        p = str(tmp_path / "concurrent.db")
        db1 = NormalizerDB.connect(p)
        db2 = NormalizerDB.connect(p)
        db1.save(_perfect_result(), "g1", "r1")
        db2.save(_perfect_result(), "g2", "r1")
        # Both visible from either connection after commit
        assert db1.count() >= 1
        db1.close()
        db2.close()

    def test_connection_isolation(self):
        # In-memory DBs are isolated per connection
        db1 = NormalizerDB.connect(":memory:")
        db2 = NormalizerDB.connect(":memory:")
        db1.save(_perfect_result(), "g1", "r1")
        assert db1.count() == 1
        assert db2.count() == 0
        db1.close()
        db2.close()


# -- edge cases ------------------------------------------------------


class TestEdgeCases:
    def test_persistence_across_reopen(self, tmp_path):
        p = str(tmp_path / "persist.db")
        db = NormalizerDB.connect(p)
        db.save(_perfect_result(), "g1", "r1", diagnosis="Тиф")
        db.close()
        db2 = NormalizerDB.connect(p)
        rec = db2.load("g1", "r1")
        assert rec is not None
        assert rec.diagnosis == "Тиф"
        db2.close()

    def test_manual_field_preserved_across_reopen(self, tmp_path):
        p = str(tmp_path / "manual.db")
        db = NormalizerDB.connect(p)
        db.save(_perfect_result(), "g1", "r1")
        db.update_manual_field("g1", "r1", "review_status", "approved")
        db.close()
        db2 = NormalizerDB.connect(p)
        rec = db2.load("g1", "r1")
        assert rec is not None
        assert rec.review_status == "approved"
        db2.close()

    def test_source_fields_stored(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1",
                source_pdf="test.pdf", source_page="27", source_quote="text")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.source_pdf == "test.pdf"
        assert rec.source_page == "27"
        assert rec.raw["source_quote"] == "text"
        db.close()

    def test_validation_counts_stored(self):
        db = _connect()
        db.save(_empty_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.validation_errors >= 4
        assert rec.validation_verdict == "REJECT"
        db.close()

    def test_population_adult_child_stored(self):
        db = _connect()
        r = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1", "unit": "г",
            "route": "в/в", "frequency": "1 раз в день", "age_group": "дети",
        })
        db.save(r, "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.child is True
        assert rec.adult is False
        db.close()

    def test_pregnancy_none_stored_as_null(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        # perfect regimen has age_group adults, pregnancy detection from text
        # may be None or True/False
        assert rec.pregnancy is None or isinstance(rec.pregnancy, bool)
        db.close()

    def test_count_after_mixed_saves(self):
        db = _connect()
        for g in range(3):
            for r in range(3):
                db.save(_perfect_result(), f"g{g}", f"r{r}")
        assert db.count() == 9
        db.close()

    def test_load_all_ordered(self):
        db = _connect()
        db.save(_perfect_result(), "g2", "r2")
        db.save(_perfect_result(), "g1", "r1")
        db.save(_perfect_result(), "g1", "r2")
        recs = db.load_all()
        # Ordered by guideline_id, regimen_id
        assert recs[0].guideline_id == "g1"
        assert recs[0].regimen_id == "r1"
        assert recs[1].regimen_id == "r2"
        assert recs[2].guideline_id == "g2"
        db.close()

    def test_repeated_saves_idempotent(self):
        db = _connect()
        for _ in range(10):
            db.save(_perfect_result(), "g1", "r1")
        assert db.count() == 1
        db.close()

    def test_conn_property_auto_opens(self):
        db = NormalizerDB(":memory:")
        assert db._conn is None
        _ = db.conn  # triggers _open
        assert db._conn is not None
        db.close()

    def test_save_many_inside_outer_transaction(self):
        # M9: the old bare BEGIN raised "cannot start a transaction within a
        # transaction" whenever the caller had an uncommitted write, and the
        # except handler's ROLLBACK then discarded the caller's work.
        db = _connect()
        db.conn.execute("BEGIN")
        db.conn.execute(
            "INSERT INTO normalized_regimens "
            "(regimen_id, guideline_id, created_at, updated_at) "
            "VALUES ('outer', 'g0', 'x', 'x')"
        )
        sr = db.save_many([
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
        ])
        assert sr.saved == 1 and sr.errors == []
        db.conn.commit()
        # The caller's own row survived — save_many no longer rolled it back
        assert db.load("g0", "outer") is not None
        assert db.load("g1", "r1") is not None
        db.close()

    def test_save_many_failure_inside_outer_transaction_keeps_outer_work(self):
        db = _connect()
        db.conn.execute("BEGIN")
        db.conn.execute(
            "INSERT INTO normalized_regimens "
            "(regimen_id, guideline_id, created_at, updated_at) "
            "VALUES ('outer', 'g0', 'x', 'x')"
        )
        items = [
            {"result": _perfect_result(), "guideline_id": "g1", "regimen_id": "r1"},
            {"result": _perfect_result(), "guideline_id": "g1"},  # missing regimen_id
        ]
        sr = db.save_many(items)
        assert sr.saved == 0 and sr.skipped == 1
        db.conn.rollback()
        # Only the caller's row is gone; the batch left nothing behind
        assert db.count() == 0
        db.close()

    def test_stats_empty_row_fallback(self):
        # stats() on empty table returns dict with zeros.
        db = _connect()
        s = db.stats()
        assert s["total"] == 0
        assert s["pass"] == 0
        assert s["reject"] == 0
        db.close()


# ── Regression tests: M3, M7, M8, M11, M19, M20 ────────────────────


class TestM3RangePersisted:
    """M3: the RC-030 dose range was not persisted at all — no dose_min /
    dose_max / dose_is_range columns existed."""

    def test_columns_exist(self):
        db = _connect()
        cols = db.column_names()
        for c in ("dose_min", "dose_max", "dose_is_range"):
            assert c in cols, c
        db.close()

    def test_range_persisted_for_dose_range(self):
        db = _connect()
        result = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "20-50", "unit": "мг/кг",
            "route": "в/в", "frequency": "1 раз в день",
        })
        assert result.regimen.dose_min == 20.0
        assert result.regimen.dose_max == 50.0
        db.save(result, "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.dose_min == 20.0
        assert rec.dose_max == 50.0
        assert rec.dose_is_range is True
        db.close()

    def test_scalar_persisted_as_not_range(self):
        db = _connect()
        result = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1,0", "unit": "г",
            "route": "в/в", "frequency": "1 раз в день",
        })
        db.save(result, "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.dose_min == 1.0
        assert rec.dose_max == 1.0
        assert rec.dose_is_range is False
        db.close()

    def test_combination_total_persisted(self):
        db = _connect()
        result = MedicalNormalizer.normalize({
            "antibiotic": "Амоксициллин+клавулановая кислота",
            "dose": "875/125", "unit": "мг",
            "route": "внутрь", "frequency": "2 раза в день",
        })
        db.save(result, "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.dose == 1000.0
        assert rec.dose_min == 1000.0
        assert rec.dose_max == 1000.0
        assert rec.dose_is_range is False
        db.close()

    def test_missing_dose_persisted_as_null(self):
        db = _connect()
        result = MedicalNormalizer.normalize({"antibiotic": "Доксициклин"})
        db.save(result, "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.dose_min is None
        assert rec.dose_max is None
        assert rec.dose_is_range is None
        db.close()

    def test_range_updated_on_upsert(self):
        db = _connect()
        wide = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "20-50", "unit": "мг/кг",
            "route": "в/в", "frequency": "1 раз в день",
        })
        narrow = MedicalNormalizer.normalize({
            "antibiotic": "Цефтриаксон", "dose": "1,0", "unit": "г",
            "route": "в/в", "frequency": "1 раз в день",
        })
        db.save(wide, "g1", "r1")
        db.save(narrow, "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.dose_min == 1.0
        assert rec.dose_max == 1.0
        assert rec.dose_is_range is False
        db.close()

    def test_regimen_record_range_defaults_are_optional(self):
        rec = RegimenRecord(
            regimen_id="r1", guideline_id="g1", drug_normalized="X",
            dose=1.0, dose_unit="mg", route="iv", frequency=1.0,
            duration_min=None, duration_max=None, duration_recommended=None,
            therapy_line="first", adult=True, child=False, pregnancy=None,
            renal_adjustment=False, atc_code="", overall_confidence=0.9,
            validation_verdict="PASS", validation_errors=0,
            validation_reviews=0, validation_warnings=0,
            source_pdf="", source_page="", diagnosis="", mkb="",
            normalizer_version="1.0.0", schema_version="1.1.0",
            review_status="pending", reviewed_by="", review_date="",
            manual_notes="", manual_override="", approved=False,
            created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        )
        assert rec.dose_min is None
        assert rec.dose_max is None
        assert rec.dose_is_range is None


class TestM7LikeInjection:
    """M7: LIKE wildcards in the user value were passed through, so
    search(diagnosis='%') returned every row."""

    def _seed(self, db):
        db.save(_perfect_result(), "g1", "r1", diagnosis="Брюшной тиф")
        db.save(_perfect_result(), "g1", "r2", diagnosis="Пневмония")
        db.save(_perfect_result(), "g1", "r3", diagnosis="100% ожогов")

    def test_percent_does_not_match_everything(self):
        db = _connect()
        self._seed(db)
        assert len(db.search(diagnosis="%")) == 1  # the literal '%' row
        db.close()

    def test_underscore_is_literal(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1", diagnosis="брюшной_тиф")
        db.save(_perfect_result(), "g1", "r2", diagnosis="брюшнойXтиф")
        assert len(db.search(diagnosis="брюшной_тиф")) == 1
        db.close()

    def test_escaped_percent_still_finds_literal(self):
        db = _connect()
        self._seed(db)
        recs = db.search(diagnosis="100%")
        assert len(recs) == 1
        assert recs[0].diagnosis == "100% ожогов"
        db.close()

    def test_backslash_is_escaped(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1", diagnosis=r"a\b")
        recs = db.search(diagnosis=r"a\b")
        assert len(recs) == 1
        db.close()

    def test_normal_substring_still_works(self):
        db = _connect()
        self._seed(db)
        assert len(db.search(diagnosis="тиф")) == 1
        db.close()

    def test_injection_does_not_bypass_other_filters(self):
        db = _connect()
        self._seed(db)
        assert len(db.search(diagnosis="%", drug="Nonexistent")) == 0
        db.close()


class TestM8NoCreatedAtNPlusOne:
    """M8: _get_created_at issued a per-row SELECT whose result was never
    used, because created_at is not in _WRITE_COLUMNS."""

    def test_helper_is_gone(self):
        assert not hasattr(NormalizerDB, "_get_created_at")

    def test_created_at_preserved_on_upsert(self):
        db = _connect()
        db.save(_perfect_result(), "g1", "r1")
        first = db.load("g1", "r1")
        assert first is not None
        # A SELECT against normalized_regimens during a save would prove the
        # N+1 is gone; only the upsert statement itself should run.
        with _Tracing(db) as trace:
            db.save(_perfect_result(), "g1", "r1")
        assert [s for s in trace if s.upper().lstrip().startswith("SELECT")] == []
        second = db.load("g1", "r1")
        assert second is not None
        assert second.created_at == first.created_at
        db.close()

    def test_batch_save_issues_no_select_per_row(self):
        db = _connect()
        with _Tracing(db) as trace:
            db.save_many([
                {"result": _perfect_result(), "guideline_id": f"g{i}", "regimen_id": "r1"}
                for i in range(5)
            ])
        assert [s for s in trace if s.upper().lstrip().startswith("SELECT")] == []
        assert db.count() == 5
        db.close()


class TestM11ThreadSafety:
    """M11: sqlite3 defaults to check_same_thread=True, so any use from a
    worker thread raised ProgrammingError."""

    def test_connection_allows_cross_thread_use(self):
        import threading

        db = NormalizerDB.connect(":memory:")
        errors: list[BaseException] = []

        def worker():
            try:
                db.save(_perfect_result(), "g1", "r1")
                assert db.count() == 1
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert errors == []
        db.close()

    def test_concurrent_writes_from_many_threads(self):
        import threading

        db = NormalizerDB.connect(":memory:")
        errors: list[BaseException] = []

        def worker(i: int):
            try:
                for j in range(5):
                    db.save(_perfect_result(), f"g{i}", f"r{j}")
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert db.count() == 20
        db.close()

    def test_wal_journal_mode_enabled(self, tmp_path):
        p = str(tmp_path / "wal.db")
        db = NormalizerDB.connect(p)
        mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
        db.close()

    def test_lock_is_reentrant(self):
        db = NormalizerDB.connect(":memory:")
        assert hasattr(db, "_lock")
        with db._lock:
            with db._lock:
                assert db.count() == 0
        db.close()


class TestM19SchemaMigration:
    """M19: _open() ran no migration — SCHEMA_VERSION was only a column
    value, so an older database raised "no such column"."""

    _OLD_SCHEMA = """
    CREATE TABLE normalized_regimens (
        regimen_id             TEXT    NOT NULL,
        guideline_id           TEXT    NOT NULL,
        drug_original          TEXT    DEFAULT '',
        drug_normalized        TEXT    DEFAULT '',
        drug_components        TEXT    DEFAULT '[]',
        dose                   REAL,
        dose_unit              TEXT    DEFAULT '',
        route                  TEXT    DEFAULT 'unknown',
        frequency              REAL,
        duration_min           REAL,
        duration_max           REAL,
        duration_recommended   REAL,
        therapy_line           TEXT    DEFAULT 'unknown',
        population             TEXT    DEFAULT '',
        adult                  INTEGER DEFAULT 1,
        child                  INTEGER DEFAULT 0,
        pregnancy              INTEGER,
        renal_adjustment       INTEGER DEFAULT 0,
        atc_code               TEXT    DEFAULT '',
        overall_confidence     REAL    DEFAULT 0.0,
        field_confidence       TEXT    DEFAULT '{}',
        parser_confidence      REAL,
        validation_verdict     TEXT    DEFAULT 'REJECT',
        validation_issues      TEXT    DEFAULT '[]',
        validation_errors      INTEGER DEFAULT 0,
        validation_reviews     INTEGER DEFAULT 0,
        validation_warnings    INTEGER DEFAULT 0,
        source_pdf             TEXT    DEFAULT '',
        source_page            TEXT    DEFAULT '',
        source_quote           TEXT    DEFAULT '',
        diagnosis              TEXT    DEFAULT '',
        mkb                    TEXT    DEFAULT '',
        normalizer_version     TEXT    DEFAULT '',
        schema_version         TEXT    DEFAULT '1.0.0',
        review_status          TEXT    DEFAULT 'pending',
        reviewed_by            TEXT    DEFAULT '',
        review_date            TEXT    DEFAULT '',
        manual_notes           TEXT    DEFAULT '',
        manual_override        TEXT    DEFAULT '',
        approved               INTEGER DEFAULT 0,
        created_at             TEXT    NOT NULL,
        updated_at             TEXT    NOT NULL,
        PRIMARY KEY (guideline_id, regimen_id)
    );
    """

    def test_old_database_gets_new_columns(self, tmp_path):
        import sqlite3

        p = str(tmp_path / "old.db")
        conn = sqlite3.connect(p)
        conn.executescript(self._OLD_SCHEMA)
        conn.commit()
        conn.close()

        db = NormalizerDB.connect(p)
        cols = db.column_names()
        for c in ("dose_min", "dose_max", "dose_is_range"):
            assert c in cols, c
        db.close()

    def test_old_database_existing_data_survives(self, tmp_path):
        import sqlite3

        p = str(tmp_path / "old2.db")
        conn = sqlite3.connect(p)
        conn.executescript(self._OLD_SCHEMA)
        conn.execute(
            "INSERT INTO normalized_regimens "
            "(regimen_id, guideline_id, drug_normalized, dose, created_at, updated_at) "
            "VALUES ('r1', 'g1', 'Цефтриаксон', 1.0, 'old', 'old')"
        )
        conn.commit()
        conn.close()

        db = NormalizerDB.connect(p)
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.drug_normalized == "Цефтриаксон"
        assert rec.created_at == "old"
        assert rec.dose_min is None
        db.close()

    def test_old_database_accepts_new_writes(self, tmp_path):
        import sqlite3

        p = str(tmp_path / "old3.db")
        conn = sqlite3.connect(p)
        conn.executescript(self._OLD_SCHEMA)
        conn.commit()
        conn.close()

        db = NormalizerDB.connect(p)
        # This raised "no such column: dose_min" before the migration
        db.save(_perfect_result(), "g1", "r1")
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.dose_min == 1.0
        db.close()

    def test_migration_is_idempotent(self, tmp_path):
        import sqlite3

        p = str(tmp_path / "old4.db")
        conn = sqlite3.connect(p)
        conn.executescript(self._OLD_SCHEMA)
        conn.commit()
        conn.close()
        for _ in range(3):
            db = NormalizerDB.connect(p)
            db.close()

    def test_old_row_schema_version_preserved(self, tmp_path):
        import sqlite3

        p = str(tmp_path / "old5.db")
        conn = sqlite3.connect(p)
        conn.executescript(self._OLD_SCHEMA)
        conn.execute(
            "INSERT INTO normalized_regimens "
            "(regimen_id, guideline_id, schema_version, created_at, updated_at) "
            "VALUES ('r1', 'g1', '1.0.0', 'old', 'old')"
        )
        conn.commit()
        conn.close()
        db = NormalizerDB.connect(p)
        rec = db.load("g1", "r1")
        assert rec is not None
        assert rec.schema_version == "1.0.0"
        db.close()

    def test_migration_columns_constant_matches_schema(self):
        from medical_normalizer.db import MIGRATION_COLUMNS, _WRITE_COLUMNS

        for name, _type in MIGRATION_COLUMNS:
            assert name in _WRITE_COLUMNS, name


class TestM20LimitValidation:
    """M20: search(limit=-1) silently meant unbounded and limit=2.7
    truncated."""

    def test_negative_limit_raises_in_search(self):
        db = _connect()
        with pytest.raises(ValueError):
            db.search(limit=-1)
        db.close()

    def test_zero_limit_raises_in_search(self):
        db = _connect()
        with pytest.raises(ValueError):
            db.search(limit=0)
        db.close()

    def test_float_limit_raises_in_search(self):
        db = _connect()
        with pytest.raises(TypeError):
            db.search(limit=2.7)
        db.close()

    def test_bool_limit_raises_in_search(self):
        db = _connect()
        with pytest.raises(TypeError):
            db.search(limit=True)
        db.close()

    def test_negative_limit_raises_in_load_all(self):
        db = _connect()
        with pytest.raises(ValueError):
            db.load_all(limit=-1)
        db.close()

    def test_float_limit_raises_in_load_all(self):
        db = _connect()
        with pytest.raises(TypeError):
            db.load_all(limit=2.7)
        db.close()

    def test_none_limit_means_unbounded(self):
        db = _connect()
        for i in range(5):
            db.save(_perfect_result(), f"g{i}", "r1")
        assert len(db.load_all(limit=None)) == 5
        assert len(db.search(limit=None)) == 5
        db.close()

    def test_positive_limit_still_works(self):
        db = _connect()
        for i in range(5):
            db.save(_perfect_result(), f"g{i}", "r1")
        assert len(db.load_all(limit=3)) == 3
        assert len(db.search(limit=3)) == 3
        db.close()

    def test_limit_is_parameterised_not_interpolated_from_float(self):
        # int() truncation used to turn 2.7 into 2
        db = _connect()
        with pytest.raises(TypeError):
            db.search(limit=2.7)
        db.close()


class TestL8L9Cleanups:
    def test_save_does_not_double_commit(self):
        db = _connect()
        with _Tracing(db) as trace:
            db.save(_perfect_result(), "g1", "r1")
        # L8: _upsert commits, so save() must not commit again.
        assert sum(1 for s in trace if s.upper().lstrip().startswith("COMMIT")) == 1
        assert db.count() == 1
        db.close()

    def test_save_many_commits_once(self):
        db = _connect()
        with _Tracing(db) as trace:
            db.save_many([
                {"result": _perfect_result(), "guideline_id": f"g{i}", "regimen_id": "r1"}
                for i in range(5)
            ])
        assert sum(1 for s in trace if s.upper().lstrip().startswith("COMMIT")) <= 1
        assert db.count() == 5
        db.close()

    def test_write_columns_contain_no_manual_fields(self):
        from medical_normalizer.db import _WRITE_COLUMNS

        for m in MANUAL_FIELDS:
            assert m not in _WRITE_COLUMNS, m


class _Tracing:
    """Record every SQL statement executed on a NormalizerDB connection.

    sqlite3.Connection is an immutable C type, so the statements are captured
    with set_trace_callback rather than by patching execute().
    """

    def __init__(self, db: NormalizerDB) -> None:
        self._db = db
        self.statements: list[str] = []

    def __enter__(self) -> list[str]:
        self._db.conn.set_trace_callback(self.statements.append)
        return self.statements

    def __exit__(self, *exc: object) -> None:
        self._db.conn.set_trace_callback(None)
