from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.pipeline.extraction.base import Document, Page
from src.pipeline.knowledge_base import KnowledgeBase, LegacyIdentityError
from src.pipeline.knowledge_identity import build_identity


def _doc(value: str, *, key: str, pdf: str = "guide.pdf", page: int = 1,
         quote: str | None = None) -> Document:
    return Document(
        source="test",
        pdf_path=Path(pdf),
        pages=[Page(0, "")],
        full_text="",
        metadata={"guideline_id": "g1"},
        knowledge_objects={
            "Dose": [{
                "logical_key": key,
                "value": value,
                "unit": "mg",
                "raw": f"{value} mg",
                "confidence": 0.9,
                "provenance": {
                    "page": page,
                    "original_text": quote if quote is not None else f"{value} mg",
                },
            }]
        },
    )


def test_unrelated_json_substrings_never_match():
    kb = KnowledgeBase(":memory:")
    kb.add_document(_doc("50", key="dose-50"))
    kb.add_document(_doc("500", key="dose-500"))
    assert kb.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 2
    assert kb.conn.execute("SELECT MAX(version) FROM objects").fetchone()[0] == 1


def test_same_object_is_idempotent():
    kb = KnowledgeBase(":memory:")
    first = kb.add_document(_doc("500", key="dose-slot"))
    second = kb.add_document(_doc("500", key="dose-slot"))
    assert first["added"] == 1
    assert second["added"] == 0
    assert kb.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 1


def test_new_content_creates_exactly_one_next_version():
    kb = KnowledgeBase(":memory:")
    kb.add_document(_doc("500", key="dose-slot"))
    stats = kb.add_document(_doc("750", key="dose-slot"))
    assert stats["added"] == 1
    assert [row[0] for row in kb.conn.execute("SELECT version FROM objects ORDER BY version")] == [1, 2]


def test_superseded_chain_is_linear_and_one_active():
    kb = KnowledgeBase(":memory:")
    for value in ("250", "500", "750"):
        kb.add_document(_doc(value, key="dose-slot"))
    rows = kb.conn.execute("SELECT version,status,history FROM objects ORDER BY version").fetchall()
    assert [row[0] for row in rows] == [1, 2, 3]
    assert [row[1] for row in rows] == ["superseded", "superseded", "active"]
    assert sum(row[1] == "active" for row in rows) == 1
    assert all(len(json.loads(row[2])) == 1 for row in rows[1:])


def test_fallback_scope_separates_documents_without_a_guideline_id():
    """Identity is guideline-scoped, and falls back to the DOCUMENT when unknown.

    With no `guideline_id` anywhere there is no safe way to claim two PDFs assert
    the same fact, so the document name is the scope.  This is the only place a
    document name participates in identity.
    """
    class NoGuideline:
        metadata: dict = {}  # noqa: RUF012 - a test stub, intentionally a dict

    a = build_identity("Dose", {"value": "500", "unit": "mg"}, {"page": 1}, NoGuideline(), "a.pdf")
    b = build_identity("Dose", {"value": "500", "unit": "mg"}, {"page": 1}, NoGuideline(), "b.pdf")
    assert a.logical_key != b.logical_key


def test_same_fact_in_two_documents_of_one_guideline_is_one_object():
    """Two PDF files of the SAME guideline asserting the same fact -> one identity."""
    a = build_identity(
        "Dose", {"value": "500", "unit": "mg"}, {"page": 1, "page_num": None},
        _doc("500", key="x"), "a.pdf",
    )
    b = build_identity(
        "Dose", {"value": "500", "unit": "mg"}, {"page": 9, "page_num": 9},
        _doc("500", key="x"), "b.pdf",
    )
    assert a.logical_key == b.logical_key
    assert a.clinical_scope != b.clinical_scope, "scope must still record WHERE it was seen"


def test_same_fact_on_two_pages_produces_one_object_with_two_provenance_rows():
    """H-6: the fact is one object; both pages are recorded as evidence."""
    kb = KnowledgeBase(":memory:")
    kb.add_document(_doc("500", key="dose-slot", page=5))
    stats = kb.add_document(_doc("500", key="dose-slot", page=9))
    assert stats["added"] == 0, "the same fact on another page must not duplicate"
    assert kb.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 1
    assert kb.conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0] == 2
    assert [row[0] for row in kb.conn.execute(
        "SELECT page FROM provenance ORDER BY page"
    )] == [5, 9]


def test_a_moved_fact_supersedes_rather_than_duplicating():
    """Same slot, changed value, new page: exactly one new version, one active."""
    kb = KnowledgeBase(":memory:")
    kb.add_document(_doc("500", key="dose-slot", page=5))
    kb.add_document(_doc("750", key="dose-slot", page=9))
    rows = kb.conn.execute("SELECT version,status FROM objects ORDER BY version").fetchall()
    assert [r[0] for r in rows] == [1, 2]
    assert [r[1] for r in rows] == ["superseded", "active"]
    assert sum(r[1] == "active" for r in rows) == 1
    assert sum(r[1] == "superseded" for r in rows) == 1


def test_two_distinct_writings_of_one_fact_on_one_page_both_survive():
    """H-6: free-text entities carry no table_row/table_col, so the old
    (pdf, page, None, None) key collapsed every occurrence onto one row."""
    kb = KnowledgeBase(":memory:")
    kb.add_document(_doc("500", key="dose-slot", page=5, quote="500 мг"))
    kb.add_document(_doc("500", key="dose-slot", page=5, quote="0,5 г"))
    assert kb.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 1
    assert kb.conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0] == 2


def test_a_repeated_identical_mention_still_dedups():
    kb = KnowledgeBase(":memory:")
    kb.add_document(_doc("500", key="dose-slot", page=5, quote="500 мг"))
    kb.add_document(_doc("500", key="dose-slot", page=5, quote="500 мг"))
    assert kb.conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0] == 1


def test_provenance_reads_the_legacy_engine_key_as_the_entity_extractor():
    """H-8: the producer wrote 'engine'; the mapper read 'extractor' -> always None."""
    from src.pipeline.knowledge_base import _build_provenance

    class D:
        source = "MinerU-OCR"
        metadata: dict = {}  # noqa: RUF012 - a test stub

    prov = _build_provenance(
        {"page": 3, "engine": "pymupdf-native-table"}, {}, D(), "x.pdf", "now",
    )
    assert prov.extractor == "pymupdf-native-table", "entity extractor was overwritten by the document source"


def test_provenance_page_distinguishes_absent_from_zero():
    """H-9: `page: 0` must be honoured and `page: None` must fall back to page_num."""
    from src.pipeline.knowledge_base import _build_provenance

    class D:
        source = "x"
        metadata: dict = {}  # noqa: RUF012 - a test stub

    def _page(src):
        return _build_provenance(src, {}, D(), "x.pdf", "now").page

    assert _page({"page": None, "page_num": 7}) == 7
    assert _page({"page": 0}) == 0
    assert _page({}) == 0
    assert _page({"page_num": 7}) == 7


def test_legacy_database_is_write_blocked_without_byte_mutation(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE objects(id TEXT PRIMARY KEY,type TEXT,content TEXT,version INTEGER,status TEXT)")
    connection.execute("INSERT INTO objects VALUES('x','Dose','{}',1986,'active')")
    connection.commit()
    connection.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    kb = KnowledgeBase(str(path))
    with pytest.raises(LegacyIdentityError, match="LEGACY_FUZZY_IDENTITY"):
        kb.add_document(_doc("500", key="dose-slot"))
    kb.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_identity_columns_and_indexes_exist():
    kb = KnowledgeBase(":memory:")
    columns = {row[1] for row in kb.conn.execute("PRAGMA table_info(objects)")}
    indexes = {row[1] for row in kb.conn.execute("PRAGMA index_list(objects)")}
    assert {"logical_key", "content_hash", "clinical_scope"} <= columns
    assert {"idx_identity", "idx_identity_content", "idx_one_active_identity"} <= indexes
