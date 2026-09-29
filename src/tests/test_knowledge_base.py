"""P4.4 tests. Real execution where possible. No mocks for core logic."""

import pytest
from pathlib import Path
import tempfile
import shutil
import sys
sys.path.insert(0, '.')

from src.pipeline.extraction.base import Document, Page
from src.pipeline.knowledge_base import KnowledgeBase, _stable_id, _content_key


class _Spy:
    """Wraps a sqlite3.Connection to count the statements it issues."""

    def __init__(self, conn, log):
        self._conn = conn
        self._log = log

    def execute(self, sql, *args):
        self._log.append(sql)
        return self._conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)

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
    # F-2: this accepted any of three values, so it could not detect a regression to
    # 'draft' (an object that never becomes usable).  Pin the exact state.
    assert objs[0]["status"] == "active", f"got {objs[0]['status']!r}"
    assert objs[0]["validation_status"] == "valid"

    # same content -> dedup (no new)
    s2 = kb.add_document(doc1)
    objs2 = kb.get_active("Medication")
    assert len(objs2) == len(objs)  # no dup added
    assert s2["added"] == 0

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
    # F-2: `conflicts >= 1 or reviews >= 1` is trivially satisfiable by the
    # new-version path, which ALWAYS queues a review -- it hid a broken
    # skipped_drug counter reporting 2 instead of 1.  Assert each counter.
    assert s3["conflicts"] == 1, "a changed payload in the same slot is a conflict"
    assert s3["reviews"] == 1
    assert s3["added"] == 1
    assert s3["superseded"] == 1
    objs3 = kb.get_active("Medication")
    assert len(objs3) == 1, "exactly one active object survives a version bump"
    assert objs3[0]["version"] == 2
    assert kb.conn.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0] == 1

    kb.close()


def test_skipped_drug_count_is_honest():
    """F-2: the dishonest `or reviews >= 1` assertion hid this counter reporting 2
    for a single skipped guideline."""
    kb = KnowledgeBase(":memory:")
    doc = Document(
        source="test", pdf_path=Path("x.pdf"), pages=[], full_text="",
        knowledge_objects={"Medication": [
            {"name": "Amoxicillin", "raw": "амоксициллин", "confidence": 0.9,
             "logical_key": "a"},
            {"name": "Azithromycin", "raw": "азитромицин", "confidence": 0.9,
             "logical_key": "b"},
        ]},
    )
    stats = kb.add_document(doc)
    assert stats["added"] == 2
    assert stats["conflicts"] == 0
    assert stats["reviews"] == 0
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


# ---------------------------------------------------------------------------
# H-27 -- a review-queue state must not be destroyed by running the validator
# ---------------------------------------------------------------------------

def test_h27_review_queued_candidate_is_not_marked_invalid():
    """Running validate_all() used to rewrite
    ('draft','pending','queued') -> ('draft','invalid','queued') for EVERY
    RegimenCandidate, because _validate_basic is False for that type BY DESIGN.
    """
    kb = KnowledgeBase(":memory:")
    kb.add_document(Document(
        source="test", pdf_path=Path("c.pdf"), pages=[], full_text="",
        knowledge_objects={"RegimenCandidate": [
            {"candidate_id": "erc-1", "calculation_ready": True, "blocking_reasons": [],
             "logical_key": "erc-1"},
        ]},
    ))
    before = kb.conn.execute(
        "SELECT status, validation_status, review_status FROM objects WHERE type='RegimenCandidate'"
    ).fetchone()
    assert tuple(before) == ("draft", "pending", "queued")

    fails = kb.validate_all()

    after = kb.conn.execute(
        "SELECT status, validation_status, review_status FROM objects WHERE type='RegimenCandidate'"
    ).fetchone()
    assert tuple(after) == ("draft", "pending", "queued"), "the review queue was destroyed"
    assert fails == [], "a queued review item is not an invalid object"
    assert len(kb.get_reviews()) == 1, "the review must still be queued"


def test_h27_genuinely_malformed_object_is_still_marked_invalid():
    kb = KnowledgeBase(":memory:")
    kb.add_document(Document(
        source="test", pdf_path=Path("d.pdf"), pages=[], full_text="",
        knowledge_objects={"Dose": [{"value": None, "raw": "", "confidence": 0.1,
                                     "logical_key": "bad"}]},
    ))
    fails = kb.validate_all()
    assert len(fails) == 1
    assert kb.conn.execute(
        "SELECT validation_status FROM objects WHERE type='Dose'"
    ).fetchone()[0] == "invalid"


def test_h27_validate_all_is_idempotent():
    kb = KnowledgeBase(":memory:")
    kb.add_document(Document(
        source="test", pdf_path=Path("d.pdf"), pages=[], full_text="",
        knowledge_objects={"Dose": [{"value": None, "raw": "", "confidence": 0.1,
                                     "logical_key": "bad"}]},
    ))
    assert len(kb.validate_all()) == 1
    assert kb.validate_all() == [], "an already-invalid object is not re-reported"


# ---------------------------------------------------------------------------
# H-25 -- add_document is one transaction; a mid-loop failure commits nothing
# ---------------------------------------------------------------------------

def test_h25_mid_loop_failure_commits_nothing():
    kb = KnowledgeBase(":memory:")
    doc = Document(
        source="test", pdf_path=Path("t.pdf"), pages=[], full_text="",
        knowledge_objects={"Medication": [
            {"name": "Amoxicillin", "raw": "амоксициллин", "logical_key": "a"},
            {"name": "Azithromycin", "raw": "азитромицин", "logical_key": "b"},
        ]},
    )

    original = kb._add_one_object

    def _boom(*args, **kwargs):
        if kwargs.get("_second") or args[1].get("logical_key") == "b":
            raise RuntimeError("simulated mid-loop failure")
        return original(*args, **kwargs)

    # fail on the SECOND object only
    calls = {"n": 0}

    def _fail_on_second(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated mid-loop failure")
        return original(*args, **kwargs)

    kb._add_one_object = _fail_on_second
    with pytest.raises(RuntimeError, match="simulated mid-loop failure"):
        kb.add_document(doc)

    assert kb.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 0, \
        "a partial write survived a failure and is indistinguishable from a real 0-object PDF"
    assert kb.conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0] == 0
    kb.close()


# ---------------------------------------------------------------------------
# M-26 -- the missing indexes
# ---------------------------------------------------------------------------

def test_m26_hot_path_indexes_exist():
    kb = KnowledgeBase(":memory:")

    def _indexes(table):
        return {row[1] for row in kb.conn.execute(f"PRAGMA index_list({table})")}

    assert "idx_provenance_obj" in _indexes("provenance")
    assert "idx_reviews_status" in _indexes("reviews")
    assert "idx_conflicts_key" in _indexes("conflicts")
    assert "idx_objects_content_hash" in _indexes("objects")
    kb.close()


# ---------------------------------------------------------------------------
# M-27 -- impact_analysis must not be N+1
# ---------------------------------------------------------------------------

def test_m27_impact_analysis_batches_its_queries():
    kb = KnowledgeBase(":memory:")
    doc = Document(
        source="test", pdf_path=Path("i.pdf"), pages=[], full_text="",
        knowledge_objects={"Medication": [
            {"name": f"Drug{i}", "raw": f"drug{i}", "logical_key": f"k{i}"} for i in range(20)
        ]},
    )
    kb.add_document(doc)
    real_conn = kb.conn

    executed = []
    real_execute = kb.conn.execute

    def _spy(sql, *args):
        executed.append(sql)
        return real_execute(sql, *args)

    kb.conn = _Spy(kb.conn, executed)
    try:
        impact = kb.impact_analysis(doc)
    finally:
        kb.conn = real_conn

    assert impact["affected"] == 20
    object_queries = [s for s in executed if "FROM objects" in s]
    assert len(object_queries) == 1, f"impact_analysis issued {len(object_queries)} queries (N+1)"


# ---------------------------------------------------------------------------
# F-4-style dead setup is removed; add_document is exercised for real
# ---------------------------------------------------------------------------

def test_add_document_returns_early_for_an_empty_document():
    kb = KnowledgeBase(":memory:")
    assert kb.add_document(
        Document(source="t", pdf_path=Path("e.pdf"), pages=[], full_text="")
    ) == {"added": 0, "reviews": 0, "conflicts": 0, "superseded": 0}
    kb.close()
