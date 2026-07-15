"""PR-001 regression tests — table-derived provenance must reach the Knowledge Base.

Root cause (fixed 2026-07-14): `layout.py::_extract_table_with_transformers` referenced `tbbox`
before assignment, raising NameError on every detected table, which a bare `except: pass`
swallowed — silently dropping ALL structured tables. Result: the Knowledge Base was built from
flat text only (0 table-origin provenance), defeating the entire P4.5 Layout milestone.

These tests lock two guarantees:
  1. (fast, no models) Table cells → semantic entities → knowledge objects → SQLite provenance,
     carrying table_row / table_col. Guards the semantic→KB contract PR-001 depends on.
  2. (real, skippable) Full layout on a real table-heavy PDF yields >0 structured tables and
     >0 table-origin provenance in the KB. Guards the exact layout stage that regressed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from src.pipeline.extraction.base import Document, Page, BoundingBox, TableCell, TableObject
from src.pipeline.extraction.semantic import SemanticProcessor
from src.pipeline.knowledge_base import KnowledgeBase


def _table_with_drug_dose_cell() -> TableObject:
    """A structured table whose cell holds an authoritative drug+dose (as in real regimen tables)."""
    cell = TableCell(
        row=2, col=1, text="амоксициллин 500 мг",
        bbox=BoundingBox(10, 20, 120, 40, page=3),
        confidence=0.9, engine="table-transformer+rapidtable", page_num=3,
    )
    return TableObject(page_num=3, bbox=BoundingBox(0, 0, 500, 700, page=3),
                       rows=3, cols=3, cells=[cell], confidence=0.9)


def test_table_cell_provenance_reaches_kb_fast():
    """Deterministic, no ML models: a table cell's row/col provenance must survive to SQLite."""
    proc = SemanticProcessor()
    tbl = _table_with_drug_dose_cell()

    # Stage: structured table -> semantic entities
    ents = proc.extract_entities_from_tables([tbl], page_num=3, engine="layout+table")
    assert ents, "table cell produced no entities (semantic table extraction broken)"
    assert any(e["type"] == "Dose" for e in ents), "dose not extracted from table cell"
    # provenance must carry the cell row/col under the canonical key (PROVENANCE_SPECIFICATION v2)
    assert any(e.get("provenance", {}).get("table_row") == 2 for e in ents), "cell row provenance lost"

    # Stage: entities -> knowledge objects
    kobjs = proc.build_knowledge_objects(ents)
    all_objs = [o for lst in kobjs.values() for o in lst]
    assert all_objs, "no knowledge objects built from table entities"

    # Stage: knowledge objects -> SQLite provenance
    doc = Document(source="test", pdf_path=Path("t.pdf"),
                   pages=[Page(3, "")], full_text="", knowledge_objects=kobjs)
    kb = KnowledgeBase(":memory:")
    kb.add_document(doc)
    with_table = kb.conn.execute(
        "SELECT COUNT(*) FROM provenance WHERE table_row IS NOT NULL").fetchone()[0]
    kb.close()
    assert with_table > 0, "table_row provenance did not reach the Knowledge Base (PR-001 regression)"


def test_merge_provenance_retains_distinct_cells():
    """RC-017 regression: the same object appearing in different table cells on the same page must
    keep BOTH cells' provenance; only truly identical (pdf,page,row,col) provenance is deduped."""
    from src.pipeline.knowledge_base import KnowledgeBase, Provenance
    kb = KnowledgeBase(":memory:")
    p_a = Provenance(pdf="x.pdf", page=5, table_row=1, table_col=2, original_text="a")
    p_b = Provenance(pdf="x.pdf", page=5, table_row=9, table_col=4, original_text="a")
    p_dup = Provenance(pdf="x.pdf", page=5, table_row=1, table_col=2, original_text="a")
    kb._add_provenance("o", [p_a])
    kb._merge_provenance("o", [p_b])   # distinct cell → must be added
    kb._merge_provenance("o", [p_dup])  # identical cell → must be ignored
    rows = kb.conn.execute(
        "SELECT table_row, table_col FROM provenance WHERE obj_id='o'").fetchall()
    kb.close()
    assert len(rows) == 2, f"expected 2 distinct cell provenances, got {len(rows)} (RC-017 regression)"


def test_layout_produces_structured_tables_real():
    """Real execution guard for the exact regressed stage. Skips if models/PDF unavailable."""
    pdf = Path(r"C:\clinrec_downloader\downloads_active\Сепсис новорождённых.pdf")
    if not pdf.exists():
        pytest.skip("real table-heavy PDF not available")
    try:
        from src.pipeline.extraction.layout import LayoutProcessor, add_layout_to_document
        proc = LayoutProcessor()
        if not (proc.table_detector and proc.table_structure):
            pytest.skip("layout table models not available")
    except Exception:
        pytest.skip("layout stack not importable")

    from src.pipeline.extraction.router import ExtractorRouter
    router = ExtractorRouter()
    doc = router.primary.extract(pdf)
    add_layout_to_document(doc, pdf)
    n_tables = len(getattr(doc, "structured_tables", []) or [])
    assert n_tables > 0, "layout produced 0 structured tables on a table-heavy PDF (PR-001 regression)"
