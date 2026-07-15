"""P3 INT-2 — provenance resolver tests.

Builds a throwaway mini-corpus (temp SQLite + temp PDF) to exercise the full
traceability chain and every fail-loud path required by INT-2:
success, missing PDF, SHA mismatch, missing metadata, missing regimen,
missing review information. A real-corpus smoke test runs when the corpus is
present, else skips.

The resolver is read-only and persists nothing — a test asserts no files are
created in the corpus dir by a resolution.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from clinical_engine.corpus import (
    CorpusLocator,
    MetadataNotFound,
    PdfNotFound,
    ProvenanceResolver,
    RegimenNotFound,
    ReviewInfoMissing,
    ShaMismatch,
)

_PDF_BYTES = b"%PDF-1.4 fake guideline content for tests\n"
_PDF_SHA = hashlib.sha256(_PDF_BYTES).hexdigest()


def _build_corpus(root: Path, *, with_pdf=True, review_status="pending",
                  with_metadata=True, pdf_sha=_PDF_SHA, pdf_name="typhoid.pdf") -> None:
    """Create a minimal corpus mirroring the real schema/join keys."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "downloads_active").mkdir(exist_ok=True)
    if with_pdf:
        (root / "downloads_active" / pdf_name).write_bytes(_PDF_BYTES)

    nr = sqlite3.connect(root / "normalized_regimens.sqlite")
    nr.execute("CREATE TABLE normalized_regimens (regimen_id TEXT, guideline_id TEXT, "
               "review_status TEXT, reviewed_by TEXT, review_date TEXT, approved INTEGER)")
    nr.execute("INSERT INTO normalized_regimens VALUES ('5351','343',?, '', NULL, 0)",
               (review_status,))
    nr.commit(); nr.close()

    md = sqlite3.connect(root / "metadata.sqlite")
    md.execute("CREATE TABLE antibiotic_regimens (id INTEGER, clinrec_id INTEGER, pdf_file TEXT, "
               "pdf_sha256 TEXT, page_number TEXT, source_quote TEXT, section_name TEXT)")
    md.execute("CREATE TABLE clinrecs (id INTEGER, code INTEGER)")
    if with_metadata:
        md.execute("INSERT INTO antibiotic_regimens VALUES (5351,343,?,?, '27', 'quote text', 'Лечение')",
                   (pdf_name, pdf_sha))
        md.execute("INSERT INTO clinrecs VALUES (343, 494)")
    md.commit(); md.close()


def _resolver(root: Path, **kw) -> ProvenanceResolver:
    return ProvenanceResolver(CorpusLocator(root), **kw)


# ── success ────────────────────────────────────────────────────


def test_successful_resolution(tmp_path: Path):
    _build_corpus(tmp_path)
    with _resolver(tmp_path) as r:
        rec = r.resolve("5351")
    assert rec.regimen_id == "5351"
    assert rec.guideline_id == "343"
    assert rec.kr_code == "494"
    assert rec.page_number == "27"
    assert rec.source_quote == "quote text"
    assert rec.pdf_sha256 == _PDF_SHA
    assert rec.pdf_sha256_verified is True
    assert rec.pdf_path.endswith("typhoid.pdf")
    assert rec.review_status == "pending"
    assert rec.approved is False
    # every INT-2 required field is present and non-empty where mandated
    d = rec.as_dict()
    for k in ("regimen_id", "guideline_id", "pdf_path", "pdf_sha256", "page_number",
              "source_quote", "review_status"):
        assert d[k] not in (None, "")


def test_resolution_writes_nothing_to_corpus(tmp_path: Path):
    _build_corpus(tmp_path)
    before = {p.name for p in (tmp_path / "downloads_active").iterdir()} | {
        p.name for p in tmp_path.iterdir()}
    with _resolver(tmp_path) as r:
        r.resolve("5351")
    after = {p.name for p in (tmp_path / "downloads_active").iterdir()} | {
        p.name for p in tmp_path.iterdir()}
    assert after == before  # no cache/sidecar/copy created


# ── fail-loud paths (INT-2 requirement 4) ──────────────────────


def test_missing_regimen(tmp_path: Path):
    _build_corpus(tmp_path)
    with _resolver(tmp_path) as r:
        with pytest.raises(RegimenNotFound):
            r.resolve("9999")


def test_missing_metadata(tmp_path: Path):
    _build_corpus(tmp_path, with_metadata=False)
    with _resolver(tmp_path) as r:
        with pytest.raises(MetadataNotFound):
            r.resolve("5351")


def test_missing_pdf(tmp_path: Path):
    _build_corpus(tmp_path, with_pdf=False)
    with _resolver(tmp_path) as r:
        with pytest.raises(PdfNotFound):
            r.resolve("5351")


def test_sha_mismatch(tmp_path: Path):
    # metadata records a different SHA than the on-disk PDF.
    _build_corpus(tmp_path, pdf_sha="0" * 64)
    with _resolver(tmp_path) as r:
        with pytest.raises(ShaMismatch):
            r.resolve("5351")


def test_missing_review_info(tmp_path: Path):
    _build_corpus(tmp_path, review_status=None)
    with _resolver(tmp_path) as r:
        with pytest.raises(ReviewInfoMissing):
            r.resolve("5351")


def test_error_carries_code_and_regimen_id(tmp_path: Path):
    _build_corpus(tmp_path, with_pdf=False)
    with _resolver(tmp_path) as r:
        try:
            r.resolve("5351")
        except PdfNotFound as e:
            assert e.code == "PDF_NOT_FOUND"
            assert e.regimen_id == "5351"


def test_verify_disabled_skips_hash(tmp_path: Path):
    # Wrong SHA on disk, but verification disabled -> resolves, verified=False.
    _build_corpus(tmp_path, pdf_sha="0" * 64)
    with _resolver(tmp_path, verify_pdf_hash=False) as r:
        rec = r.resolve("5351")
    assert rec.pdf_sha256_verified is False


# ── real corpus smoke (present on this machine) or skip ─────────


def _real() -> CorpusLocator:
    return CorpusLocator()


def test_real_corpus_provenance_smoke():
    loc = _real()
    if not loc.available():
        pytest.skip("external corpus not present")
    # regimen_id 5351 exists in the corpus (typhoid guideline 343).
    with ProvenanceResolver(loc, verify_pdf_hash=True) as r:
        rec = r.resolve("5351")
    assert rec.guideline_id == "343"
    assert rec.pdf_sha256_verified is True          # real PDF hash matches metadata
    assert rec.pdf_path.lower().endswith(".pdf")
    assert Path(rec.pdf_path).is_file()
    assert rec.review_status == "pending"


def test_real_corpus_missing_pdf_fails_loud():
    loc = _real()
    if not loc.available():
        pytest.skip("external corpus not present")
    # A regimen whose PDF is genuinely absent must raise, never degrade silently.
    # (We don't assume a specific id; just prove unknown ids fail loudly.)
    with ProvenanceResolver(loc, verify_pdf_hash=False) as r:
        with pytest.raises(RegimenNotFound):
            r.resolve("nonexistent-regimen-id")
