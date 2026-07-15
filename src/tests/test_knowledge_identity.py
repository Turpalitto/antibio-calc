from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.pipeline.extraction.base import Document, Page
from src.pipeline.knowledge_base import KnowledgeBase, LegacyIdentityError
from src.pipeline.knowledge_identity import build_identity


def _doc(value: str, *, key: str, pdf: str = "guide.pdf") -> Document:
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
                "provenance": {"page": 1, "original_text": f"{value} mg"},
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


def test_fallback_scope_separates_documents():
    class Doc:
        metadata = {"guideline_id": "g1"}

    a = build_identity("Dose", {"value": "500", "unit": "mg"}, {"page": 1}, Doc(), "a.pdf")
    b = build_identity("Dose", {"value": "500", "unit": "mg"}, {"page": 1}, Doc(), "b.pdf")
    assert a.logical_key != b.logical_key


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
