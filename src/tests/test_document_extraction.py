"""Basic tests for document extraction layer. Stage 8."""

import pytest
from pathlib import Path
from src.pipeline.extraction.router import ExtractorRouter
from src.pipeline.extraction.base import Document

def test_router_has_providers():
    r = ExtractorRouter()
    assert r.primary.name == "pymupdf"
    assert r.fallback.name == "mineru"
    assert isinstance(r.fallbacks, list)

def test_unified_document():
    # mock would be better, but structure check
    d = Document(source="test", pdf_path=Path("x.pdf"), pages=[], full_text="hi")
    assert d.source == "test"
    assert d.full_text == "hi"

# TODO: real tests with sample pdfs (good, scan, bad, empty, corrupt)
# pytest src/tests/ -k extraction or similar

import hashlib
import pytest
from src.pipeline.extraction.cache import get_cache, _sha256
from src.pipeline.extraction.metrics import get_metrics, reset_metrics
from src.pipeline.extraction.router import ExtractorRouter
from src.pipeline.extraction.base import Page, Document
from pathlib import Path
import fitz
import tempfile


def test_cache_hit_miss(tmp_path):
    # use a real small pdf
    pdf = Path("low_test.pdf")
    if not pdf.exists():
        pytest.skip("no low_test.pdf")
    c = get_cache()
    # force miss first by clearing? just check logic
    key = _sha256(pdf)
    # run
    r = ExtractorRouter()
    doc1 = r.extract(pdf)
    # second should hit if enabled
    doc2 = r.extract(pdf)
    assert doc1.source == doc2.source or "cache" in getattr(doc2, 'source', '')


def test_mixed_pages_provenance():
    # create synthetic mixed PDF: good page + empty page
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "mixed.pdf"
        doc = fitz.open()
        # page 0 good
        p0 = doc.new_page()
        p0.insert_text((50, 50), "Это хороший текст с кириллицей. " * 10)
        # page 1 bad
        p1 = doc.new_page()
        # empty
        doc.save(str(p))
        doc.close()

        r = ExtractorRouter()
        d = r.extract(p)
        prov = d.metadata.get("page_provenance", [])
        assert len(prov) == 2
        # at least one should have source info
        sources = {pr["source"] for pr in prov}
        assert "pymupdf" in sources or "mineru" in sources


def test_provenance_and_metrics():
    reset_metrics()
    pdf = Path("low_test.pdf")
    if not pdf.exists():
        pytest.skip()
    r = ExtractorRouter()
    d = r.extract(pdf)
    prov = d.metadata.get("page_provenance")
    assert prov is not None
    m = get_metrics()
    snap = m.snapshot()
    assert snap["documents_processed"] >= 1


def test_router_multi_fallback_config():
    r = ExtractorRouter()
    assert len(r.fallbacks) >= 1
    # registry allows future
    from src.pipeline.extraction.router import _EXTRACTOR_REGISTRY
    assert "pymupdf" in _EXTRACTOR_REGISTRY
    assert "docling" in _EXTRACTOR_REGISTRY  # P4.1


# P4.3 semantic tests - real execution
from src.pipeline.extraction.semantic import SemanticProcessor, add_semantic_to_document
from src.pipeline.extraction.base import Document, Page


def test_semantic_processor_entities():
    proc = SemanticProcessor()
    text = "При гайморите амоксициллин 500 мг 3 раза сутки 7 дней. Противопоказан при беременности."
    ents = proc.extract_entities(text, 0, "test")
    assert len(ents) >= 2
    types = {e["type"] for e in ents}
    assert "Drug" in types or "Diagnosis" in types
    assert all("provenance" in e and "page" in e["provenance"] for e in ents)


def test_semantic_knowledge_objects_and_relations():
    proc = SemanticProcessor()
    text = "Острый синусит. Препарат выбора: амоксициллин 500мг. Длительность 7 дней."
    ents = proc.extract_entities(text, 1, "t")
    rels = proc.extract_relations(text, ents)
    objs = proc.build_knowledge_objects(ents)
    assert "Medication" in objs
    assert "Diagnosis" in objs or "Dose" in objs
    assert isinstance(rels, list)


def test_semantic_consistency_checker():
    proc = SemanticProcessor()
    text = "амоксициллин 500 мг"
    ents = proc.extract_entities(text, 0, "t")
    warns = proc.check_consistency(ents, [])
    assert isinstance(warns, list)


def test_add_semantic_to_document():
    doc = Document(source="test", pdf_path=Path("x"), pages=[Page(page_num=0, text="амоксициллин 250 мг 2 раза 5 дней")], full_text="амоксициллин 250 мг 2 раза 5 дней")
    add_semantic_to_document(doc, "test")
    assert doc.metadata.get("semantic_processed") is True
    assert "entity_count" in doc.metadata
    assert len(doc.entities) >= 1
    assert "knowledge_objects" in dir(doc) or hasattr(doc, "knowledge_objects")

