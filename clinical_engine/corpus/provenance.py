"""Deterministic provenance resolver for the external corpus (P3 INT-2).

Given a ``regimen_id`` (the identity the engine already carries on every
``RecommendationCandidate``), assemble the FULL traceability chain by reading the
upstream corpus READ-ONLY:

    regimen_id
      → normalized_regimens (guideline_id, physician review status)
      → metadata.antibiotic_regimens (pdf_file, pdf_sha256, page, source quote)
      → metadata.clinrecs (КР code)
      → the original PDF on disk (located by filename, SHA-256 verified)

Guarantees:
  - **Read-only.** Uses ``CorpusLocator.open_*`` (mode=ro&immutable=1). Never
    writes to, copies, or caches upstream content. The returned record is a
    transient in-memory object; this module persists nothing.
  - **Deterministic.** Same upstream bytes → same record. No timestamps, no
    randomness.
  - **Fails loudly.** Any break in the chain raises a specific
    :class:`ProvenanceError` subclass — never a silent partial result.

Scope (INT-2): a standalone reference resolver. It does NOT touch the engine,
the pipeline, routing, recommendation logic, or the safety stages.

Note on join keys (verified against the corpus):
  normalized_regimens.regimen_id  == metadata.antibiotic_regimens.id
  normalized_regimens.guideline_id == metadata.antibiotic_regimens.clinrec_id
                                   == metadata.clinrecs.id
  clinrecs.pdf_path is STALE (points at an emptied dir) — the PDF is located by
  ``pdf_file`` name across the corpus PDF dirs instead.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from clinical_engine.corpus.locator import CorpusLocator


class ProvenanceError(RuntimeError):
    """Base: a recommendation could not be fully traced to its source."""
    code = "PROVENANCE_ERROR"

    def __init__(self, message: str, *, regimen_id: str | None = None) -> None:
        self.regimen_id = regimen_id
        super().__init__(f"[{self.code}] {message}")


class RegimenNotFound(ProvenanceError):
    code = "REGIMEN_NOT_FOUND"


class MetadataNotFound(ProvenanceError):
    code = "METADATA_NOT_FOUND"


class PdfNotFound(ProvenanceError):
    code = "PDF_NOT_FOUND"


class ShaMismatch(ProvenanceError):
    code = "SHA_MISMATCH"


class ReviewInfoMissing(ProvenanceError):
    code = "REVIEW_INFO_MISSING"


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Complete, transient traceability chain for one recommendation.

    Referencing (not copying): identifies the upstream record by key and points
    at the on-disk PDF. ``source_quote`` is read live for display/audit and is
    never persisted by this module.
    """
    regimen_id: str
    guideline_id: str
    kr_code: str | None
    antibiotic_regimens_id: int
    clinrec_id: int | None
    section_name: str | None
    pdf_path: str
    pdf_sha256: str
    pdf_sha256_verified: bool
    page_number: str | None
    source_quote: str | None
    review_status: str
    reviewed_by: str | None
    review_date: str | None
    approved: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ProvenanceResolver:
    """Resolves a regimen_id to its full provenance chain, read-only.

    Reuses two SQLite connections for the resolver's lifetime (connection reuse,
    not content caching). Use as a context manager or call :meth:`close`.
    """

    def __init__(self, locator: CorpusLocator | None = None, *, verify_pdf_hash: bool = True) -> None:
        self._loc = locator or CorpusLocator()
        self._verify = verify_pdf_hash
        self._nr: sqlite3.Connection | None = None
        self._md: sqlite3.Connection | None = None

    # -- lifecycle -------------------------------------------------
    def __enter__(self) -> "ProvenanceResolver":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        for con in (self._nr, self._md):
            if con is not None:
                con.close()
        self._nr = self._md = None

    def _nr_conn(self) -> sqlite3.Connection:
        if self._nr is None:
            self._nr = self._loc.open_normalized_regimens()  # fails loudly if absent
        return self._nr

    def _md_conn(self) -> sqlite3.Connection:
        if self._md is None:
            self._md = self._loc.open_metadata()  # fails loudly if absent
        return self._md

    # -- resolution ------------------------------------------------
    def resolve(self, regimen_id: str) -> ProvenanceRecord:
        rid = str(regimen_id)

        # 1. normalized_regimens: engine's regimen + physician review status.
        nr = self._nr_conn()
        row = nr.execute(
            "SELECT guideline_id, review_status, reviewed_by, review_date, approved "
            "FROM normalized_regimens WHERE regimen_id = ?",
            (rid,),
        ).fetchone()
        if row is None:
            raise RegimenNotFound(f"regimen_id {rid} not in normalized_regimens", regimen_id=rid)
        guideline_id, review_status, reviewed_by, review_date, approved = row

        # Review information must be present (a value like 'pending' is valid;
        # a NULL/blank status means the review field is absent -> fail loudly).
        if review_status is None or str(review_status).strip() == "":
            raise ReviewInfoMissing(
                f"regimen_id {rid} has no review_status (review information missing)",
                regimen_id=rid,
            )

        # 2. metadata.antibiotic_regimens: provenance authority.
        md = self._md_conn()
        mrow = md.execute(
            "SELECT id, clinrec_id, pdf_file, pdf_sha256, page_number, source_quote, section_name "
            "FROM antibiotic_regimens WHERE id = ?",
            (rid,),
        ).fetchone()
        if mrow is None:
            raise MetadataNotFound(
                f"regimen_id {rid} not in metadata.antibiotic_regimens", regimen_id=rid
            )
        ar_id, clinrec_id, pdf_file, pdf_sha256, page_number, source_quote, section_name = mrow
        if not pdf_file or not pdf_sha256:
            raise MetadataNotFound(
                f"regimen_id {rid} metadata missing pdf_file/pdf_sha256", regimen_id=rid
            )

        # 3. clinrecs: КР code (best-effort; not fatal if absent).
        kr_code = None
        crow = md.execute("SELECT code FROM clinrecs WHERE id = ?", (clinrec_id,)).fetchone()
        if crow is not None:
            kr_code = str(crow[0]) if crow[0] is not None else None

        # 4. Locate the original PDF by filename across the corpus PDF dirs
        #    (clinrecs.pdf_path is stale). Fail loudly if not found.
        pdf_path = self._locate_pdf(pdf_file)
        if pdf_path is None:
            raise PdfNotFound(
                f"PDF '{pdf_file}' for regimen_id {rid} not found under corpus PDF dirs",
                regimen_id=rid,
            )

        # 5. Integrity: verify the on-disk PDF matches the recorded SHA-256.
        verified = False
        if self._verify:
            actual = _sha256_of(pdf_path)
            if actual.lower() != str(pdf_sha256).lower():
                raise ShaMismatch(
                    f"PDF SHA-256 mismatch for regimen_id {rid}: "
                    f"recorded {pdf_sha256}, on-disk {actual} ({pdf_path})",
                    regimen_id=rid,
                )
            verified = True

        return ProvenanceRecord(
            regimen_id=rid,
            guideline_id=str(guideline_id),
            kr_code=kr_code,
            antibiotic_regimens_id=int(ar_id),
            clinrec_id=int(clinrec_id) if clinrec_id is not None else None,
            section_name=section_name,
            pdf_path=str(pdf_path),
            pdf_sha256=str(pdf_sha256),
            pdf_sha256_verified=verified,
            page_number=str(page_number) if page_number is not None else None,
            source_quote=source_quote,
            review_status=str(review_status),
            reviewed_by=(reviewed_by or None),
            review_date=(review_date or None),
            approved=bool(approved),
        )

    def _locate_pdf(self, pdf_file: str) -> Path | None:
        for d in self._loc.pdf_dirs():
            candidate = d / pdf_file
            if candidate.is_file():
                return candidate
        return None
