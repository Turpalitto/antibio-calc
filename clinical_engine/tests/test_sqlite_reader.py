"""Milestone 2: SQLiteReader — normalized_regimens -> RecommendationCandidate."""

from __future__ import annotations

from pathlib import Path

import pytest

from clinical_engine.models import EngineError, EngineErrorCode, ValidationPolicy
from clinical_engine.readers.sqlite_reader import SQLiteReader


class TestConnectionErrors:
    def test_missing_file_raises_engine_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.sqlite"
        with pytest.raises(EngineError) as exc_info:
            SQLiteReader(missing)
        assert exc_info.value.code is EngineErrorCode.SQLITE_NOT_FOUND
        assert exc_info.value.stage == "RegimenLoad"

    def test_corrupt_file_raises_engine_error(self, tmp_path: Path) -> None:
        # Not a valid SQLite file at all (NormalizerDB.connect() always
        # self-heals a missing *table* via CREATE TABLE IF NOT EXISTS, so the
        # only way to hit SQLITE_CORRUPT is a file sqlite3 can't open at all).
        corrupt = tmp_path / "corrupt.sqlite"
        corrupt.write_bytes(b"this is not a sqlite database file")
        with pytest.raises(EngineError) as exc_info:
            SQLiteReader(corrupt)
        assert exc_info.value.code is EngineErrorCode.SQLITE_CORRUPT


class TestLoadRegimens:
    def test_strict_policy_loads_pass_only(self, sqlite_path: Path) -> None:
        reader = SQLiteReader(sqlite_path)
        candidates = reader.load_regimens(("g_cap_adult",), policy=ValidationPolicy.STRICT)
        assert len(candidates) == 1
        assert candidates[0].validation_verdict == "PASS"
        assert candidates[0].regimen_id == "r1"
        reader.close()

    def test_allow_review_loads_pass_and_review(self, sqlite_path: Path) -> None:
        reader = SQLiteReader(sqlite_path)
        candidates = reader.load_regimens(
            ("g_cap_adult",), policy=ValidationPolicy.ALLOW_REVIEW
        )
        verdicts = {c.validation_verdict for c in candidates}
        assert verdicts == {"PASS", "REVIEW"}
        assert len(candidates) == 2
        reader.close()

    def test_debug_policy_loads_everything(self, sqlite_path: Path) -> None:
        reader = SQLiteReader(sqlite_path)
        candidates = reader.load_regimens(("g_cap_adult",), policy=ValidationPolicy.DEBUG)
        verdicts = {c.validation_verdict for c in candidates}
        assert verdicts == {"PASS", "REVIEW", "REJECT"}
        assert len(candidates) == 3
        reader.close()

    def test_audit_policy_also_loads_everything(self, sqlite_path: Path) -> None:
        reader = SQLiteReader(sqlite_path)
        candidates = reader.load_regimens(("g_cap_adult",), policy=ValidationPolicy.AUDIT)
        assert len(candidates) == 3
        reader.close()

    def test_multiple_guideline_ids(self, sqlite_path: Path) -> None:
        reader = SQLiteReader(sqlite_path)
        candidates = reader.load_regimens(
            ("g_cap_adult", "g_cystitis"), policy=ValidationPolicy.STRICT
        )
        guideline_ids = {c.guideline_id for c in candidates}
        assert guideline_ids == {"g_cap_adult", "g_cystitis"}
        assert len(candidates) == 2
        reader.close()

    def test_unknown_guideline_id_returns_empty(self, sqlite_path: Path) -> None:
        reader = SQLiteReader(sqlite_path)
        candidates = reader.load_regimens(("does_not_exist",), policy=ValidationPolicy.DEBUG)
        assert candidates == []
        reader.close()

    def test_empty_guideline_ids_returns_empty(self, sqlite_path: Path) -> None:
        reader = SQLiteReader(sqlite_path)
        assert reader.load_regimens((), policy=ValidationPolicy.STRICT) == []
        reader.close()


class TestCandidateShape:
    def test_candidate_fields_populated(self, sqlite_path: Path) -> None:
        reader = SQLiteReader(sqlite_path)
        candidates = reader.load_regimens(("g_cap_adult",), policy=ValidationPolicy.STRICT)
        c = candidates[0]
        assert c.drug_normalized == "Амоксициллин"
        assert c.dose == 500.0
        assert c.dose_unit == "mg"
        assert c.route == "oral"
        assert c.frequency == 3.0
        assert c.source_pdf == "cr654.pdf"
        assert c.source_quote == "Amoxicillin 500mg 3x/day 5-7 days"
        assert c.diagnosis == "CAP"
        assert c.mkb == "J18"
        reader.close()

    def test_drug_ref_and_guideline_year_deferred(self, sqlite_path: Path) -> None:
        """Per spec: drug_ref (bridge lives in DrugReferenceReader) and
        guideline_year (comes from DiagnosisEntry, not SQLite) are always
        None straight out of SQLiteReader — filled in later by stage code."""
        reader = SQLiteReader(sqlite_path)
        candidates = reader.load_regimens(("g_cap_adult",), policy=ValidationPolicy.DEBUG)
        assert all(c.drug_ref is None for c in candidates)
        assert all(c.guideline_year is None for c in candidates)
        reader.close()

    def test_context_manager_closes(self, sqlite_path: Path) -> None:
        with SQLiteReader(sqlite_path) as reader:
            assert reader.load_regimens(("g_cap_adult",), policy=ValidationPolicy.STRICT)
