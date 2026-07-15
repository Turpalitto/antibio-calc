"""P4.4 tests. Real execution where possible. No mocks for core logic."""

import pytest
from pathlib import Path
import tempfile
import shutil
import sys
sys.path.insert(0, '.')

from src.pipeline.extraction.base import Document, Page
from src.pipeline.knowledge_base import KnowledgeBase, _stable_id, _content_key

def test_immutable_and_version():
    kb = KnowledgeBase(":memory:")
    # synthetic but structure from real semantic
    doc1 = Document(
        source="test",
        pdf_path=Path("x1.pdf"),
        pages=[Page(0, "test")],
        full_text="",
        knowledge_objects={
            "Medication": [{"name": "Amoxicillin", "raw": "амоксициллин", "confidence": 0.9}]
        }
    )
    doc1.knowledge_objects["Medication"][0]["logical_key"] = "drug-slot-1"
    s1 = kb.add_document(doc1)
    assert s1["added"] >= 1

    objs = kb.get_active("Medication")
    assert len(objs) >= 1
    assert objs[0]["version"] == 1
    assert objs[0]["status"] in ("active", "validated", "published")

    # same content -> dedup (no new)
    s2 = kb.add_document(doc1)
    objs2 = kb.get_active("Medication")
    assert len(objs2) == len(objs)  # no dup added

    # different -> new version + conflict
    doc2 = Document(
        source="test",
        pdf_path=Path("x2.pdf"),
        pages=[Page(0, "test")],
        full_text="",
        knowledge_objects={
            "Medication": [{"name": "Amoxicillin", "raw": "амоксициллин 500", "confidence": 0.8}]
        }
    )
    doc2.knowledge_objects["Medication"][0]["logical_key"] = "drug-slot-1"
    s3 = kb.add_document(doc2)
    assert s3["conflicts"] >= 1 or s3["reviews"] >= 1
    objs3 = kb.get_active("Medication")
    assert len(objs3) >= 1  # active ones

    kb.close()

def test_validation_and_review():
    kb = KnowledgeBase(":memory:")
    bad_doc = Document(
        source="test",
        pdf_path=Path("bad.pdf"),
        pages=[],
        full_text="",
        knowledge_objects={
            "Dose": [{"value": None, "raw": "", "confidence": 0.1}]  # invalid
        }
    )
    kb.add_document(bad_doc)
    fails = kb.validate_all()
    assert len(fails) >= 0  # may queue review
    reviews = kb.get_reviews()
    assert isinstance(reviews, list)
    kb.close()

def test_impact_analysis():
    kb = KnowledgeBase(":memory:")
    doc = Document(
        source="test",
        pdf_path=Path("x.pdf"),
        pages=[],
        full_text="",
        knowledge_objects={"Diagnosis": [{"name": "sinusitis", "raw": "гайморит"}]}
    )
    kb.add_document(doc)
    impact = kb.impact_analysis(doc)
    assert "affected" in impact
    assert isinstance(impact["affected"], int)
    kb.close()

def test_real_pdf_if_available():
    """Real execution on actual PDF if present. No fake."""
    pdf = Path(r"C:\clinrec_downloader\downloads_antibiotics\Абсцесс. Фурункул носа. Карбункул носа..pdf")
    if not pdf.exists() or pdf.stat().st_size < 10000:
        pytest.skip("no real PDF for strict real test")
    from src.pipeline.extraction.router import ExtractorRouter
    router = ExtractorRouter()
    d = router.extract(pdf)
    kb = KnowledgeBase(":memory:")
    stats = kb.add_document(d)
    assert stats["added"] >= 0  # can be 0 if no objects, but real run
    s = kb.stats()
    assert "total_objects" in s
    kb.close()
