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

# Audit 2026-10-14 (E-2): the end-to-end router tests below used to look for a
# `low_test.pdf` in the current directory and were skipped everywhere but on one
# machine. They now run on the synthetic three-page guideline fixture
# (`synthetic_guideline_pdf`: text page, dosing table, image-only "scan").

from src.pipeline.extraction import cache as cache_module
from src.pipeline.extraction.cache import ExtractionCache, get_cache
from src.pipeline.extraction.metrics import get_metrics, reset_metrics
from src.pipeline.extraction.base import Page
import fitz
import tempfile


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """A fresh extraction cache under tmp_path, visible through get_cache()."""
    monkeypatch.setattr(cache_module.get_config(), "cache_path", str(tmp_path / "cache"))
    fresh = ExtractionCache()
    monkeypatch.setattr(cache_module, "_cache", fresh)
    assert get_cache() is fresh
    return fresh


def test_router_extracts_the_synthetic_guideline_end_to_end(synthetic_guideline_pdf, isolated_cache):
    router = ExtractorRouter()
    doc = router.extract(synthetic_guideline_pdf)

    assert len(doc.pages) == 3
    # page 1 narrative and page 2 table come straight from the text layer
    assert "амоксициллин" in doc.pages[0].text.lower()
    assert "500 мг" in doc.pages[0].text
    assert "J01DD04" in doc.pages[1].text
    assert "45 мг/кг/сут" in doc.full_text

    prov = doc.metadata.get("page_provenance")
    assert prov is not None and [p["page"] for p in prov] == [0, 1, 2]
    assert prov[0]["fallback_reason"] is None and prov[1]["fallback_reason"] is None
    # the image-only page is detected as bad and routed to the fallback engines
    assert prov[2]["fallback_reason"], "the scanned page must be flagged for fallback"
    if prov[2]["source"] == "pymupdf":
        # no OCR engine on this machine: the failure is recorded, never hidden
        assert prov[2].get("fallback_failed") == "all_ocr_engines_failed"
        assert doc.source == "pymupdf"
    else:
        assert prov[2]["ocr_time"] >= 0.0 and doc.source in ("mixed", prov[2]["source"])


def test_router_serves_the_second_extraction_from_cache(synthetic_guideline_pdf, isolated_cache):
    router = ExtractorRouter()
    first = router.extract(synthetic_guideline_pdf)
    assert "cache" not in (router._last_source or "")
    assert isolated_cache.get(synthetic_guideline_pdf) is not None, "first extraction must be cached"

    second = router.extract(synthetic_guideline_pdf)
    assert router._last_source == first.source + "+cache"
    assert second.metadata.get("cache_hit") is True
    assert second.full_text == first.full_text
    assert [p.text for p in second.pages] == [p.text for p in first.pages]
    assert second.metadata["page_provenance"] == first.metadata["page_provenance"]


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


def test_provenance_and_metrics(synthetic_guideline_pdf, isolated_cache):
    reset_metrics()
    r = ExtractorRouter()
    d = r.extract(synthetic_guideline_pdf)
    prov = d.metadata.get("page_provenance")
    assert prov is not None and len(prov) == 3
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

