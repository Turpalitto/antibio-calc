"""db.py -- persistence layer for normalized antibiotic regimens.

Responsibilities:
    - Store and retrieve NormalizedResult objects in SQLite
    - UPSERT semantics: never overwrite manual edit fields
    - Versioning: record normalizer_version + schema_version
    - Transactions for batch saves with rollback on failure

Rules:
    - NEVER parse text, normalize values, calculate confidence, or validate data
    - Only persists already normalized objects
    - No ORM, simple SQLite layer only
    - No SQL injection risks (parameterized queries)
    - No business logic, only persistence
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from medical_normalizer.models import NormalizedRegimen
from medical_normalizer.normalizer import NORMALIZER_VERSION, NormalizedResult


# ── Configuration ───────────────────────────────────────────


SCHEMA_VERSION: str = "1.0.0"


# Manual-edit fields that must survive re-normalization (UPSERT must NOT overwrite)
MANUAL_FIELDS: tuple[str, ...] = (
    "review_status",
    "reviewed_by",
    "review_date",
    "manual_notes",
    "manual_override",
    "approved",
)


_SCHEMA: str = f"""
CREATE TABLE IF NOT EXISTS normalized_regimens (
    regimen_id             TEXT    NOT NULL,
    guideline_id           TEXT    NOT NULL,
    drug_original          TEXT    DEFAULT '',
    drug_normalized        TEXT    DEFAULT '',
    drug_components        TEXT    DEFAULT '[]',
    dose                   REAL,
    dose_unit              TEXT    DEFAULT '',
    route                  TEXT    DEFAULT 'unknown',
    frequency              REAL,
    duration_min           REAL,
    duration_max           REAL,
    duration_recommended   REAL,
    therapy_line           TEXT    DEFAULT 'unknown',
    population             TEXT    DEFAULT '',
    adult                  INTEGER DEFAULT 1,
    child                  INTEGER DEFAULT 0,
    pregnancy              INTEGER,
    renal_adjustment       INTEGER DEFAULT 0,
    atc_code               TEXT    DEFAULT '',
    overall_confidence     REAL    DEFAULT 0.0,
    field_confidence       TEXT    DEFAULT '{{}}',
    parser_confidence      REAL,
    validation_verdict     TEXT    DEFAULT 'REJECT',
    validation_issues      TEXT    DEFAULT '[]',
    validation_errors      INTEGER DEFAULT 0,
    validation_reviews     INTEGER DEFAULT 0,
    validation_warnings    INTEGER DEFAULT 0,
    source_pdf             TEXT    DEFAULT '',
    source_page            TEXT    DEFAULT '',
    source_quote           TEXT    DEFAULT '',
    diagnosis              TEXT    DEFAULT '',
    mkb                    TEXT    DEFAULT '',
    normalizer_version     TEXT    DEFAULT '',
    schema_version         TEXT    DEFAULT '',
    -- Manual-edit fields (preserved across re-normalization)
    review_status          TEXT    DEFAULT 'pending',
    reviewed_by            TEXT    DEFAULT '',
    review_date            TEXT    DEFAULT '',
    manual_notes           TEXT    DEFAULT '',
    manual_override        TEXT    DEFAULT '',
    approved               INTEGER DEFAULT 0,
    created_at             TEXT    NOT NULL,
    updated_at             TEXT    NOT NULL,
    PRIMARY KEY (guideline_id, regimen_id)
);

CREATE INDEX IF NOT EXISTS idx_guideline_id     ON normalized_regimens (guideline_id);
CREATE INDEX IF NOT EXISTS idx_drug_normalized  ON normalized_regimens (drug_normalized);
CREATE INDEX IF NOT EXISTS idx_therapy_line     ON normalized_regimens (therapy_line);
CREATE INDEX IF NOT EXISTS idx_val_verdict      ON normalized_regimens (validation_verdict);
CREATE INDEX IF NOT EXISTS idx_confidence       ON normalized_regimens (overall_confidence);
CREATE INDEX IF NOT EXISTS idx_atc_code         ON normalized_regimens (atc_code);
CREATE INDEX IF NOT EXISTS idx_drug_original    ON normalized_regimens (drug_original);
CREATE INDEX IF NOT EXISTS idx_diagnosis        ON normalized_regimens (diagnosis);
CREATE INDEX IF NOT EXISTS idx_pregnancy        ON normalized_regimens (pregnancy);
CREATE INDEX IF NOT EXISTS idx_renal            ON normalized_regimens (renal_adjustment);
CREATE INDEX IF NOT EXISTS idx_review_status    ON normalized_regimens (review_status);
"""


# Columns written by normalization (excludes manual fields + PKs + timestamps handled separately)
_WRITE_COLUMNS: tuple[str, ...] = (
    "drug_original", "drug_normalized", "drug_components",
    "dose", "dose_unit", "route", "frequency",
    "duration_min", "duration_max", "duration_recommended",
    "therapy_line", "population", "adult", "child",
    "pregnancy", "renal_adjustment", "atc_code",
    "overall_confidence", "field_confidence", "parser_confidence",
    "validation_verdict", "validation_issues",
    "validation_errors", "validation_reviews", "validation_warnings",
    "source_pdf", "source_page", "source_quote",
    "diagnosis", "mkb",
    "normalizer_version", "schema_version",
)


# ── Result container ────────────────────────────────────────


@dataclass(frozen=True)
class SaveResult:
    """Outcome of a save operation."""

    saved: int
    skipped: int
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"saved": self.saved, "skipped": self.skipped, "errors": list(self.errors)}


@dataclass(frozen=True)
class RegimenRecord:
    """A row loaded from the database."""

    regimen_id: str
    guideline_id: str
    drug_normalized: str
    dose: float | None
    dose_unit: str
    route: str
    frequency: float | None
    duration_min: float | None
    duration_max: float | None
    duration_recommended: float | None
    therapy_line: str
    adult: bool
    child: bool
    pregnancy: bool | None
    renal_adjustment: bool
    atc_code: str
    overall_confidence: float
    validation_verdict: str
    validation_errors: int
    validation_reviews: int
    validation_warnings: int
    source_pdf: str
    source_page: str
    diagnosis: str
    mkb: str
    normalizer_version: str
    schema_version: str
    review_status: str
    reviewed_by: str
    review_date: str
    manual_notes: str
    manual_override: str
    approved: bool
    created_at: str
    updated_at: str
    raw: dict[str, Any] = field(default_factory=dict)


# ── NormalizerDB ────────────────────────────────────────────


class NormalizerDB:
    """SQLite persistence layer for normalized regimens.

    No ORM, no business logic. Only store/retrieve.
    Uses parameterized queries (no SQL injection).
    UPSERT preserves manual-edit fields.
    """

    schema_version: str = SCHEMA_VERSION

    # ── Connection management ────────────────────────────

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path: str = str(db_path)
        self._conn: sqlite3.Connection | None = None

    @classmethod
    def connect(cls, db_path: str | Path = ":memory:") -> "NormalizerDB":
        db = cls(db_path)
        db._open()
        return db

    def _open(self) -> None:
        if self._conn is not None:
            return
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._open()
        assert self._conn is not None
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "NormalizerDB":
        self._open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ── Schema introspection ─────────────────────────────

    def table_exists(self) -> bool:
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='normalized_regimens'"
        )
        return cur.fetchone() is not None

    def index_exists(self, index_name: str) -> bool:
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        )
        return cur.fetchone() is not None

    def column_names(self) -> list[str]:
        cur = self.conn.execute("PRAGMA table_info(normalized_regimens)")
        return [row["name"] for row in cur.fetchall()]

    def count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) AS c FROM normalized_regimens")
        row = cur.fetchone()
        return int(row["c"]) if row else 0

    # ── Save (UPSERT) ────────────────────────────────────

    def save(
        self,
        result: NormalizedResult,
        guideline_id: str,
        regimen_id: str,
        source_pdf: str = "",
        source_page: str = "",
        source_quote: str = "",
        diagnosis: str = "",
        mkb: str = "",
    ) -> None:
        """UPSERT a single normalized result. Manual fields preserved."""
        row = self._to_row(result, guideline_id, regimen_id,
                           source_pdf, source_page, source_quote, diagnosis, mkb)
        self._upsert(row)
        self.conn.commit()

    def save_many(
        self,
        items: Iterable[dict[str, Any]],
    ) -> SaveResult:
        """Batch UPSERT within a transaction. Rollback on failure.

        Each item is a dict with keys:
            result, guideline_id, regimen_id,
            source_pdf?, source_page?, source_quote?, diagnosis?, mkb?
        """
        saved = 0
        skipped = 0
        errors: list[str] = []
        conn = self.conn
        try:
            conn.execute("BEGIN")
            for item in items:
                try:
                    result = item["result"]
                    guideline_id = item["guideline_id"]
                    regimen_id = item["regimen_id"]
                    row = self._to_row(
                        result, guideline_id, regimen_id,
                        item.get("source_pdf", ""),
                        item.get("source_page", ""),
                        item.get("source_quote", ""),
                        item.get("diagnosis", ""),
                        item.get("mkb", ""),
                    )
                    self._upsert(row, commit=False)
                    saved += 1
                except KeyError as exc:
                    skipped += 1
                    errors.append(f"Missing key {exc} in item")
                except Exception as exc:
                    skipped += 1
                    errors.append(str(exc))
            # No partial commits: if any item failed, rollback the whole batch
            if errors:
                conn.execute("ROLLBACK")
                saved = 0
            else:
                conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return SaveResult(saved=saved, skipped=skipped, errors=errors)

    def _upsert(self, row: dict[str, Any], commit: bool = True) -> None:
        """UPSERT using ON CONFLICT DO UPDATE. Manual fields NOT overwritten."""
        cols = list(_WRITE_COLUMNS)
        placeholders = ", ".join("?" for _ in cols)
        col_list = ", ".join(cols)
        # UPDATE only non-manual columns + updated_at
        update_cols = [c for c in cols if c not in MANUAL_FIELDS]
        update_set = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
        update_set += ", updated_at=excluded.updated_at"
        sql = (
            f"INSERT INTO normalized_regimens (regimen_id, guideline_id, "
            f"{col_list}, created_at, updated_at) "
            f"VALUES (?, ?, {placeholders}, ?, ?) "
            f"ON CONFLICT(guideline_id, regimen_id) DO UPDATE SET {update_set}"
        )
        params = (
            row["regimen_id"], row["guideline_id"],
            *[row[c] for c in cols],
            row["created_at"], row["updated_at"],
        )
        self.conn.execute(sql, params)
        if commit:
            self.conn.commit()

    def _to_row(
        self,
        result: NormalizedResult,
        guideline_id: str,
        regimen_id: str,
        source_pdf: str,
        source_page: str,
        source_quote: str,
        diagnosis: str,
        mkb: str,
    ) -> dict[str, Any]:
        """Convert NormalizedResult to a row dict for SQL."""
        reg = result.regimen
        conf = result.confidence
        val = result.validation
        now = self._now()
        existing_created = self._get_created_at(guideline_id, regimen_id)
        return {
            "regimen_id": regimen_id,
            "guideline_id": guideline_id,
            "drug_original": reg.drug_original,
            "drug_normalized": reg.drug_normalized,
            "drug_components": json.dumps(
                [c.__dict__ for c in reg.drug_components], ensure_ascii=False
            ),
            "dose": reg.dose_value,
            "dose_unit": reg.dose_unit or "",
            "route": reg.route,
            "frequency": reg.frequency_per_day,
            "duration_min": reg.duration_days_min,
            "duration_max": reg.duration_days_max,
            "duration_recommended": reg.duration_days_recommended,
            "therapy_line": reg.therapy_line,
            "population": self._population_str(reg),
            "adult": 1 if reg.adult else 0,
            "child": 1 if reg.child else 0,
            "pregnancy": None if reg.pregnancy is None else (1 if reg.pregnancy else 0),
            "renal_adjustment": 1 if reg.renal_adjustment else 0,
            "atc_code": reg.atc_code or "",
            "overall_confidence": conf.overall_confidence,
            "field_confidence": json.dumps(conf.field_confidence, ensure_ascii=False),
            "parser_confidence": conf.parser_confidence,
            "validation_verdict": val.verdict.value,
            "validation_issues": json.dumps(
                [i.to_dict() for i in val.issues], ensure_ascii=False
            ),
            "validation_errors": len(val.errors),
            "validation_reviews": len(val.reviews),
            "validation_warnings": len(val.warnings),
            "source_pdf": source_pdf,
            "source_page": source_page,
            "source_quote": source_quote,
            "diagnosis": diagnosis,
            "mkb": mkb,
            "normalizer_version": result.normalizer_version,
            "schema_version": self.schema_version,
            "created_at": existing_created or now,
            "updated_at": now,
        }

    def _get_created_at(self, guideline_id: str, regimen_id: str) -> str | None:
        """Fetch created_at for existing record (preserved on UPSERT)."""
        cur = self.conn.execute(
            "SELECT created_at FROM normalized_regimens "
            "WHERE guideline_id=? AND regimen_id=?",
            (guideline_id, regimen_id),
        )
        row = cur.fetchone()
        return row["created_at"] if row else None

    # ── Load ──────────────────────────────────────────────

    def load(
        self,
        guideline_id: str,
        regimen_id: str,
    ) -> RegimenRecord | None:
        """Load a single record by PK."""
        cur = self.conn.execute(
            "SELECT * FROM normalized_regimens "
            "WHERE guideline_id=? AND regimen_id=?",
            (guideline_id, regimen_id),
        )
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def load_by_guideline(self, guideline_id: str) -> list[RegimenRecord]:
        """Load all regimens for a guideline."""
        cur = self.conn.execute(
            "SELECT * FROM normalized_regimens WHERE guideline_id=? "
            "ORDER BY regimen_id",
            (guideline_id,),
        )
        return [self._row_to_record(r) for r in cur.fetchall()]

    def load_by_drug(self, drug_normalized: str) -> list[RegimenRecord]:
        """Load all regimens for a drug (exact match)."""
        cur = self.conn.execute(
            "SELECT * FROM normalized_regimens WHERE drug_normalized=? "
            "ORDER BY guideline_id, regimen_id",
            (drug_normalized,),
        )
        return [self._row_to_record(r) for r in cur.fetchall()]

    def load_failed(self) -> list[RegimenRecord]:
        """Load all records with REJECT verdict."""
        cur = self.conn.execute(
            "SELECT * FROM normalized_regimens WHERE validation_verdict='REJECT' "
            "ORDER BY guideline_id, regimen_id"
        )
        return [self._row_to_record(r) for r in cur.fetchall()]

    def load_by_verdict(self, verdict: str) -> list[RegimenRecord]:
        """Load all records with a given verdict."""
        cur = self.conn.execute(
            "SELECT * FROM normalized_regimens WHERE validation_verdict=? "
            "ORDER BY guideline_id, regimen_id",
            (verdict,),
        )
        return [self._row_to_record(r) for r in cur.fetchall()]

    def load_all(self, limit: int | None = None) -> list[RegimenRecord]:
        """Load all records (optionally limited)."""
        sql = "SELECT * FROM normalized_regimens ORDER BY guideline_id, regimen_id"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        cur = self.conn.execute(sql)
        return [self._row_to_record(r) for r in cur.fetchall()]

    # ── Search ────────────────────────────────────────────

    def search(
        self,
        drug: str | None = None,
        atc_code: str | None = None,
        diagnosis: str | None = None,
        therapy_line: str | None = None,
        verdict: str | None = None,
        pregnancy: bool | None = None,
        renal_adjustment: bool | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int | None = None,
    ) -> list[RegimenRecord]:
        """Multi-criteria search. All filters optional (AND logic)."""
        clauses: list[str] = []
        params: list[Any] = []
        if drug is not None:
            clauses.append("drug_normalized = ?")
            params.append(drug)
        if atc_code is not None:
            clauses.append("atc_code = ?")
            params.append(atc_code)
        if diagnosis is not None:
            clauses.append("diagnosis LIKE ?")
            params.append(f"%{diagnosis}%")
        if therapy_line is not None:
            clauses.append("therapy_line = ?")
            params.append(therapy_line)
        if verdict is not None:
            clauses.append("validation_verdict = ?")
            params.append(verdict)
        if pregnancy is not None:
            clauses.append("pregnancy = ?")
            params.append(1 if pregnancy else 0)
        if renal_adjustment is not None:
            clauses.append("renal_adjustment = ?")
            params.append(1 if renal_adjustment else 0)
        if min_confidence is not None:
            clauses.append("overall_confidence >= ?")
            params.append(float(min_confidence))
        if max_confidence is not None:
            clauses.append("overall_confidence <= ?")
            params.append(float(max_confidence))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM normalized_regimens{where} ORDER BY guideline_id, regimen_id"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        cur = self.conn.execute(sql, params)
        return [self._row_to_record(r) for r in cur.fetchall()]

    # ── Manual edit support ──────────────────────────────

    def update_manual_field(
        self,
        guideline_id: str,
        regimen_id: str,
        field_name: str,
        value: Any,
    ) -> None:
        """Update a manual-edit field. Only allows fields in MANUAL_FIELDS."""
        if field_name not in MANUAL_FIELDS:
            raise ValueError(
                f"Field '{field_name}' is not a manual-edit field. "
                f"Allowed: {MANUAL_FIELDS}"
            )
        if field_name == "approved":
            value = 1 if value else 0
        sql = (
            f"UPDATE normalized_regimens SET {field_name}=?, updated_at=? "
            f"WHERE guideline_id=? AND regimen_id=?"
        )
        self.conn.execute(sql, (value, self._now(), guideline_id, regimen_id))
        self.conn.commit()

    def get_manual_field(
        self,
        guideline_id: str,
        regimen_id: str,
        field_name: str,
    ) -> Any:
        """Read a manual-edit field."""
        if field_name not in MANUAL_FIELDS:
            raise ValueError(f"Field '{field_name}' is not a manual-edit field.")
        cur = self.conn.execute(
            f"SELECT {field_name} FROM normalized_regimens "
            f"WHERE guideline_id=? AND regimen_id=?",
            (guideline_id, regimen_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        val = row[field_name]
        if field_name == "approved":
            return bool(val)
        return val

    # ── Stats ─────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Aggregate stats for the table."""
        cur = self.conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN validation_verdict='PASS' THEN 1 ELSE 0 END) AS pass_count, "
            "  SUM(CASE WHEN validation_verdict='REVIEW' THEN 1 ELSE 0 END) AS review_count, "
            "  SUM(CASE WHEN validation_verdict='REJECT' THEN 1 ELSE 0 END) AS reject_count, "
            "  AVG(overall_confidence) AS avg_confidence, "
            "  SUM(CASE WHEN approved=1 THEN 1 ELSE 0 END) AS approved_count "
            "FROM normalized_regimens"
        )
        row = cur.fetchone()
        if row is None:
            return {}
        return {
            "total": int(row["total"] or 0),
            "pass": int(row["pass_count"] or 0),
            "review": int(row["review_count"] or 0),
            "reject": int(row["reject_count"] or 0),
            "avg_confidence": float(row["avg_confidence"]) if row["avg_confidence"] else 0.0,
            "approved": int(row["approved_count"] or 0),
        }

    # ── Internal helpers ─────────────────────────────────

    @staticmethod
    def _population_str(reg: NormalizedRegimen) -> str:
        parts: list[str] = []
        if reg.adult:
            parts.append("adult")
        if reg.child:
            parts.append("child")
        if reg.pregnancy is True:
            parts.append("pregnancy")
        if reg.renal_adjustment:
            parts.append("renal")
        return "|".join(parts) if parts else ""

    @staticmethod
    def _now() -> str:
        """UTC timestamp for created_at/updated_at columns (DB metadata, not normalized data)."""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _row_to_record(self, row: sqlite3.Row) -> RegimenRecord:
        d = dict(row)
        return RegimenRecord(
            regimen_id=d["regimen_id"],
            guideline_id=d["guideline_id"],
            drug_normalized=d["drug_normalized"],
            dose=d["dose"],
            dose_unit=d["dose_unit"],
            route=d["route"],
            frequency=d["frequency"],
            duration_min=d["duration_min"],
            duration_max=d["duration_max"],
            duration_recommended=d["duration_recommended"],
            therapy_line=d["therapy_line"],
            adult=bool(d["adult"]),
            child=bool(d["child"]),
            pregnancy=None if d["pregnancy"] is None else bool(d["pregnancy"]),
            renal_adjustment=bool(d["renal_adjustment"]),
            atc_code=d["atc_code"],
            overall_confidence=float(d["overall_confidence"]),
            validation_verdict=d["validation_verdict"],
            validation_errors=int(d["validation_errors"]),
            validation_reviews=int(d["validation_reviews"]),
            validation_warnings=int(d["validation_warnings"]),
            source_pdf=d["source_pdf"],
            source_page=d["source_page"],
            diagnosis=d["diagnosis"],
            mkb=d["mkb"],
            normalizer_version=d["normalizer_version"],
            schema_version=d["schema_version"],
            review_status=d["review_status"],
            reviewed_by=d["reviewed_by"],
            review_date=d["review_date"],
            manual_notes=d["manual_notes"],
            manual_override=d["manual_override"],
            approved=bool(d["approved"]),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            raw=d,
        )
