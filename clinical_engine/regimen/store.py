"""AssembledRegimenStore — immutable, INSERT-only storage (P5.3 Phase 6).

Design authority: VERSIONING_GOVERNANCE.md, P5.3_DECISION_RECORD.md.

Writes a NEW sqlite file (assembled_regimens.sqlite) — never touches kb_p44.db or
normalized_regimens.sqlite. Immutability contract: a PUBLISHED (regimen_id, version)
can never be updated; a change is a new version (INSERT). Attempting to overwrite a
published row raises.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from clinical_engine.regimen.clinical_regimen import ClinicalRegimen, LifecycleState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS assembled_regimens (
    regimen_id      TEXT NOT NULL,
    version         INTEGER NOT NULL,
    status          TEXT NOT NULL,
    diagnosis       TEXT, icd_mkb TEXT, age_group TEXT, pregnancy INTEGER, renal_adjustment INTEGER,
    therapy_line    TEXT, antibiotic TEXT, dose REAL, unit TEXT, frequency REAL,
    duration_recommended REAL, route TEXT,
    guideline_id    TEXT, evidence_level TEXT, contraindications TEXT,
    review_status   TEXT, approved_by TEXT, approved_at TEXT,
    validation_verdict TEXT, confidence REAL,
    source_pdf TEXT, source_page TEXT, source_quote TEXT,
    field_provenance TEXT, needs_review_reasons TEXT,
    snapshot_version TEXT, assembly_ruleset_version TEXT,
    created_at TEXT,
    PRIMARY KEY (regimen_id, version)
);
CREATE INDEX IF NOT EXISTS idx_ar_guideline ON assembled_regimens(guideline_id);
CREATE INDEX IF NOT EXISTS idx_ar_status ON assembled_regimens(status);
CREATE INDEX IF NOT EXISTS idx_ar_verdict ON assembled_regimens(validation_verdict);
"""


class ImmutabilityViolation(Exception):
    pass


class AssembledRegimenStore:
    def __init__(self, path: str):
        self._path = str(path)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def insert(self, r: ClinicalRegimen, created_at: str = "") -> None:
        # immutability: refuse to write over an existing PUBLISHED (regimen_id, version)
        existing = self._conn.execute(
            "SELECT status FROM assembled_regimens WHERE regimen_id=? AND version=?",
            (r.regimen_id, r.version)).fetchone()
        if existing is not None:
            if existing["status"] == LifecycleState.PUBLISHED.value:
                raise ImmutabilityViolation(
                    f"regimen {r.regimen_id} v{r.version} is PUBLISHED — cannot overwrite; "
                    f"create a new version")
            # non-published existing row: still INSERT-only semantics -> treat as violation
            raise ImmutabilityViolation(
                f"regimen {r.regimen_id} v{r.version} already exists — versions are immutable")
        self._conn.execute(
            """INSERT INTO assembled_regimens
               (regimen_id, version, status, diagnosis, icd_mkb, age_group, pregnancy,
                renal_adjustment, therapy_line, antibiotic, dose, unit, frequency,
                duration_recommended, route, guideline_id, evidence_level, contraindications,
                review_status, approved_by, approved_at, validation_verdict, confidence,
                source_pdf, source_page, source_quote, field_provenance, needs_review_reasons,
                snapshot_version, assembly_ruleset_version, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r.regimen_id, r.version, r.status.value, r.diagnosis, r.icd_mkb, r.age_group,
             (None if r.pregnancy is None else int(r.pregnancy)), int(r.renal_adjustment),
             r.therapy_line, r.antibiotic, r.dose, r.unit, r.frequency, r.duration_recommended,
             r.route, r.guideline_id, r.evidence_level, json.dumps(list(r.contraindications), ensure_ascii=False),
             r.review_status, r.approved_by, r.approved_at, r.validation_verdict, r.confidence,
             r.source_pdf, r.source_page, r.source_quote,
             json.dumps([(n, asdict(p)) for n, p in r.field_provenance], ensure_ascii=False),
             json.dumps(list(r.needs_review_reasons), ensure_ascii=False),
             r.snapshot_version, r.assembly_ruleset_version, created_at))
        self._conn.commit()

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM assembled_regimens").fetchone()[0]

    def by_guideline(self, guideline_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM assembled_regimens WHERE guideline_id=?", (guideline_id,)).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()
