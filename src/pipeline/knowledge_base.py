"""P4.4 Production Knowledge Base Platform — Enterprise Release.

Immutable, versioned, fully traceable Knowledge Objects.
Append-only. Real execution only. No Clinical Engine / bundle modifications.

Every clinical fact becomes a Knowledge Object with complete:
- Stable identity + versioning
- Full source lineage (PDF, page, cell bbox, extractor, layout, semantic)
- Validation + review lifecycle
- Dedup + safe merge + impact

This is the single authoritative source for clinical knowledge.
"""

import sqlite3
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

from .extraction.base import Document, TableCell
from .knowledge_identity import build_identity, content_hash

# ============================================================
# PHASE 2: ENHANCED KNOWLEDGE OBJECT MODEL (spec compliant)
# ============================================================

@dataclass(frozen=True)
class Provenance:
    """Complete lineage for a fact (PHASE 4)."""
    pdf: str
    guideline_id: Optional[str] = None
    page: int = 0
    paragraph: Optional[str] = None
    bounding_box: Optional[Dict[str, float]] = None   # {x0,y0,x1,y1}
    extractor: str = "unknown"
    layout_engine: str = "none"                       # DocLayout-YOLO / none
    semantic_engine: str = "semantic.py"
    table_row: Optional[int] = None
    table_col: Optional[int] = None
    table_conf: Optional[float] = None                # PROVENANCE_SPECIFICATION v2 (RC-014; was dropped)
    original_text: Optional[str] = None
    normalized_value: Optional[str] = None
    timestamp: str = ""
    doc_version: str = "p4.4-2026-07"
    schema_version: int = 2                            # provenance contract version

    def to_dict(self) -> Dict:
        return asdict(self)


def _build_provenance(src: Dict, item: Dict, doc, pdf_name: str, now: str) -> "Provenance":
    """Canonical 1:1 provenance mapper (PROVENANCE_SPECIFICATION v2).

    `src` is the entity provenance dict emitted by the semantic layer, keyed by Provenance field
    names. This function ONLY maps — it never infers layout/semantic engines from `source` strings
    and never reads a field under a different name than the producer wrote (the RC-012/013/014 class
    of bugs). Builder-owned fields (timestamp, doc_version, schema_version) and the document-level
    guideline_id are stamped here.
    """
    doc_meta = getattr(doc, "metadata", {}) or {}
    # original_text: canonical key first, then the object's raw wording ("raw" is the key the
    # semantic builder uses — never "text"). Guarantees Clinical Governance "never discard wording".
    original_text = src.get("original_text") or item.get("raw") or item.get("name")
    return Provenance(
        pdf=pdf_name,
        guideline_id=src.get("guideline_id") or doc_meta.get("guideline_id"),
        page=int(src.get("page", src.get("page_num", 0)) or 0),
        paragraph=src.get("paragraph"),
        bounding_box=src.get("bounding_box") or src.get("bbox"),
        extractor=src.get("extractor") or getattr(doc, "source", None) or "router",
        layout_engine=src.get("layout_engine", "none"),
        semantic_engine=src.get("semantic_engine", "semantic.py"),
        table_row=src.get("table_row", src.get("row")),
        table_col=src.get("table_col", src.get("col")),
        table_conf=src.get("table_conf"),
        original_text=original_text,
        normalized_value=src.get("normalized_value") or item.get("normalized"),
        timestamp=now,
        doc_version="p4.4-2026-07",
        schema_version=2,
    )


@dataclass(frozen=True)
class KnowledgeObject:
    """Immutable Knowledge Object (PHASE 2 + 3).

    Append-only. Never mutate historical versions.
    """
    # Identity & Versioning (no defaults first)
    id: str
    type: str
    version: int
    status: str
    created_at: str
    updated_at: str

    # Clinical classification
    knowledge_type: str
    clinical_domain: str

    # Payload
    content: Dict[str, Any]

    # Quality & Lifecycle
    confidence: float
    validation_status: str
    review_status: str
    normalization_status: str

    # Traceability (no defaults)
    provenance: List[Provenance]
    history: List[str]

    # Optional with default last
    relationships: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["provenance"] = [p.to_dict() if hasattr(p, "to_dict") else p for p in self.provenance]
        return d

    def is_active(self) -> bool:
        return self.status in ("validated", "published") and self.validation_status == "valid"

def _stable_id(type_: str, content: Dict) -> str:
    """Backward-compatible content ID helper; not a lineage key."""
    h = hashlib.sha256(f"{type_}:{content_hash(content)}".encode("utf-8")).hexdigest()[:16]
    return f"{type_[:3].lower()}_{h}"

def _content_key(type_: str, content: Dict) -> str:
    """Exact semantic-content key retained for audit compatibility."""
    return f"{type_}:{content_hash(content)}"


class LegacyIdentityError(RuntimeError):
    """Raised when code attempts writes against a legacy fuzzy-identity DB."""

class KnowledgeBase:
    """Versioned, immutable KB. Real sqlite persistence."""

    def __init__(self, db_path: str = "knowledge_base.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        table_exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='objects'"
        ).fetchone()
        if table_exists:
            columns = {row[1] for row in self.conn.execute("PRAGMA table_info(objects)")}
            row_count = self.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
            legacy_rows = row_count if "logical_key" not in columns else self.conn.execute(
                "SELECT COUNT(*) FROM objects WHERE logical_key IS NULL OR content_hash IS NULL"
            ).fetchone()[0]
            if row_count and legacy_rows:
                self._identity_ready = False
                return
        self._init_schema()
        legacy_rows = self.conn.execute(
            "SELECT COUNT(*) FROM objects WHERE logical_key IS NULL OR content_hash IS NULL"
        ).fetchone()[0]
        self._identity_ready = legacy_rows == 0

    def _init_schema(self):
        c = self.conn.cursor()
        # Base creation (for fresh DBs)
        c.executescript("""
        CREATE TABLE IF NOT EXISTS objects (
            id TEXT PRIMARY KEY,
            type TEXT,
            content TEXT,
            logical_key TEXT,
            content_hash TEXT,
            clinical_scope TEXT,
            version INTEGER,
            status TEXT,
            created_at TEXT,
            confidence REAL,
            history TEXT
        );

        CREATE TABLE IF NOT EXISTS provenance (
            obj_id TEXT,
            pdf TEXT,
            page INTEGER,
            extractor TEXT,
            semantic TEXT,
            timestamp TEXT,
            doc_version TEXT,
            FOREIGN KEY(obj_id) REFERENCES objects(id)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            obj_id TEXT,
            reason TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'open'
        );

        CREATE TABLE IF NOT EXISTS conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT,
            obj_id1 TEXT,
            obj_id2 TEXT,
            detected_at TEXT
        );
        """)
        self.conn.commit()

        # --- P4.4 schema migration (additive, safe for existing DBs) ---
        self._migrate_add_column("objects", "knowledge_type", "TEXT")
        self._migrate_add_column("objects", "clinical_domain", "TEXT")
        self._migrate_add_column("objects", "updated_at", "TEXT")
        self._migrate_add_column("objects", "validation_status", "TEXT")
        self._migrate_add_column("objects", "review_status", "TEXT")
        self._migrate_add_column("objects", "normalization_status", "TEXT")
        self._migrate_add_column("objects", "relationships", "TEXT")
        self._migrate_add_column("objects", "logical_key", "TEXT")
        self._migrate_add_column("objects", "content_hash", "TEXT")
        self._migrate_add_column("objects", "clinical_scope", "TEXT")

        self._migrate_add_column("provenance", "guideline_id", "TEXT")
        self._migrate_add_column("provenance", "paragraph", "TEXT")
        self._migrate_add_column("provenance", "bounding_box", "TEXT")
        self._migrate_add_column("provenance", "layout_engine", "TEXT")
        self._migrate_add_column("provenance", "semantic_engine", "TEXT")
        self._migrate_add_column("provenance", "table_row", "INTEGER")
        self._migrate_add_column("provenance", "table_col", "INTEGER")
        self._migrate_add_column("provenance", "original_text", "TEXT")
        self._migrate_add_column("provenance", "normalized_value", "TEXT")
        # PROVENANCE_SPECIFICATION v2 migration (RC-012/013/014/015 — one atomic change)
        self._migrate_add_column("provenance", "table_conf", "REAL")
        self._migrate_add_column("provenance", "schema_version", "INTEGER")
        # RC-018: backfill pre-existing (v1) provenance rows to schema_version=1, as the spec
        # promises. Idempotent — v2 rows always insert schema_version=2 explicitly, so only genuine
        # legacy NULLs are touched.
        self.conn.execute("UPDATE provenance SET schema_version=1 WHERE schema_version IS NULL")
        # NOTE: legacy base column `semantic` is retired (documented-dead, never written; RC-015).
        # Dropping it needs a full table rebuild (SQLite) with no functional benefit, so it is left
        # in place and ignored per PROVENANCE_SPECIFICATION §Backward compatibility.

        # Indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_status ON objects(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_type_status ON objects(type, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_identity ON objects(type, logical_key, version)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_identity_content ON objects(type, logical_key, content_hash)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_identity "
                  "ON objects(type, logical_key) WHERE status='active' AND logical_key IS NOT NULL")
        self.conn.commit()

    def _migrate_add_column(self, table: str, column: str, col_type: str):
        """Safely add a column if it does not exist (for evolving P4.4 schema on existing DBs)."""
        c = self.conn.cursor()
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            self.conn.commit()
        except sqlite3.OperationalError:
            # Column already exists or other benign error
            pass

    def _get_by_key(self, type_: str, logical_key: str) -> Optional[Dict]:
        c = self.conn.cursor()
        row = c.execute(
            "SELECT * FROM objects WHERE type=? AND logical_key=? AND status<>'superseded' "
            "ORDER BY version DESC LIMIT 1",
            (type_, logical_key),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def add_document(self, doc: Document) -> Dict[str, Any]:
        """Process doc's knowledge_objects with full P4.4 lifecycle."""
        if not self._identity_ready:
            raise LegacyIdentityError(
                "LEGACY_FUZZY_IDENTITY: non-empty database lacks canonical logical keys; "
                "writes are blocked. Rebuild into a new v2 artifact."
            )
        if not doc.knowledge_objects:
            return {"added": 0, "reviews": 0, "conflicts": 0, "superseded": 0}

        stats = {"added": 0, "reviews": 0, "conflicts": 0, "superseded": 0}
        now = datetime.now(timezone.utc).isoformat()
        pdf_name = str(getattr(doc, "pdf_path", "unknown"))

        for otype, items in doc.knowledge_objects.items():
            for item in items:
                content = {k: v for k, v in item.items() if k not in ("source", "provenance", "logical_key")}
                confidence = float(item.get("confidence", 0.7))

                # PROVENANCE_SPECIFICATION v2: 1:1 canonical mapping — no inference, no heuristics.
                # The producer (semantic layer) emits provenance keyed by Provenance field names;
                # the consumer only maps. guideline_id is a document-level constant (owner: Document
                # metadata) legitimately stamped by the builder.
                prov_list: List[Provenance] = []
                src = item.get("provenance") or item.get("source", {})
                if not isinstance(src, dict):
                    src = {}
                identity = build_identity(
                    otype, content, src, doc, pdf_name,
                    explicit_logical_key=item.get("logical_key"),
                )
                key = identity.logical_key
                obj_id = identity.object_id
                if isinstance(src, dict):
                    prov = _build_provenance(src, item, doc, pdf_name, now)
                    prov_list.append(prov)

                existing = self._get_by_key(otype, key)

                if existing:
                    if existing.get("content_hash") == identity.content_hash:
                        self._merge_provenance(existing["id"], prov_list)
                        continue
                    else:
                        # Conflict → new version
                        stats["conflicts"] += 1
                        self._record_conflict(key, existing["id"], obj_id)
                        new_ver = int(existing.get("version", 1)) + 1

                        self.conn.execute(
                            "UPDATE objects SET status='superseded', updated_at=? WHERE id=?",
                            (now, existing["id"])
                        )
                        self._insert_object(
                            id=obj_id, type=otype, knowledge_type=otype,
                            clinical_domain="antibiotic_therapy",
                            logical_key=identity.logical_key,
                            content_hash=identity.content_hash,
                            clinical_scope=identity.clinical_scope,
                            content=content, version=new_ver,
                            status="active",
                            created_at=now, updated_at=now,
                            confidence=confidence,
                            validation_status="pending",
                            review_status="queued",
                            normalization_status=item.get("normalization_status", "raw"),
                            history=json.dumps([existing["id"]]),
                            relationships=[]
                        )
                        self._add_provenance(obj_id, prov_list)
                        self._queue_review(obj_id, f"conflict/update from {pdf_name}")
                        stats["reviews"] += 1
                        stats["superseded"] += 1

                        stats["added"] += 1
                        continue

                # New object
                is_valid = self._validate_basic(content, otype)
                self._insert_object(
                    id=obj_id, type=otype, knowledge_type=otype,
                    clinical_domain="antibiotic_therapy",
                    logical_key=identity.logical_key,
                    content_hash=identity.content_hash,
                    clinical_scope=identity.clinical_scope,
                    content=content, version=1,
                    status="active" if is_valid else "draft",
                    created_at=now, updated_at=now,
                    confidence=confidence,
                    validation_status="valid" if is_valid else "pending",
                    review_status="none" if is_valid else "queued",
                    normalization_status=item.get("normalization_status", "raw"),
                    history="[]",
                    relationships=[]
                )
                self._add_provenance(obj_id, prov_list)

                if not is_valid:
                    self._queue_review(obj_id, "validation or low confidence")
                    stats["reviews"] += 1

                stats["added"] += 1

        self.conn.commit()
        return stats

    def _insert_object(self, **kwargs):
        c = self.conn.cursor()
        content_json = json.dumps(kwargs.get("content", {}), ensure_ascii=False)
        relationships_json = json.dumps(kwargs.get("relationships", []), ensure_ascii=False)
        history_json = kwargs.get("history") or "[]"

        c.execute("""
            INSERT INTO objects
            (id, type, knowledge_type, clinical_domain, logical_key, content_hash,
             clinical_scope, content, version, status,
             created_at, updated_at, confidence, validation_status, review_status,
             normalization_status, history, relationships)
            VALUES
            (:id, :type, :knowledge_type, :clinical_domain, :logical_key, :content_hash,
             :clinical_scope, :content, :version, :status,
             :created_at, :updated_at, :confidence, :validation_status, :review_status,
             :normalization_status, :history, :relationships)
        """, {
            "content": content_json,
            "knowledge_type": kwargs.get("knowledge_type", kwargs.get("type")),
            "clinical_domain": kwargs.get("clinical_domain", "antibiotic_therapy"),
            "validation_status": kwargs.get("validation_status", kwargs.get("validation_state", "pending")),
            "review_status": kwargs.get("review_status", kwargs.get("review_state", "none")),
            "normalization_status": kwargs.get("normalization_status", "raw"),
            "updated_at": kwargs.get("updated_at", kwargs.get("created_at")),
            "history": history_json,
            "relationships": relationships_json,
            **{k: v for k, v in kwargs.items() if k not in ("content", "knowledge_type", "clinical_domain",
                                                            "validation_status", "review_status",
                                                            "normalization_status", "updated_at",
                                                            "history", "relationships")}
        })

    def _add_provenance(self, obj_id: str, provs: List[Provenance]):
        c = self.conn.cursor()
        for p in provs:
            c.execute("""
                INSERT INTO provenance
                (obj_id, pdf, guideline_id, page, paragraph, bounding_box,
                 extractor, layout_engine, semantic_engine, table_row, table_col,
                 table_conf, original_text, normalized_value, timestamp, doc_version, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                obj_id,
                p.pdf, p.guideline_id, p.page, p.paragraph,
                json.dumps(p.bounding_box) if p.bounding_box else None,
                p.extractor, p.layout_engine, p.semantic_engine,
                p.table_row, p.table_col,
                p.table_conf, p.original_text, p.normalized_value,
                p.timestamp, p.doc_version, p.schema_version
            ))

    def _merge_provenance(self, obj_id: str, new_provs: List[Provenance]):
        # RC-017 fix: dedup by (pdf, page, table_row, table_col) — NOT (pdf, page) alone. The same
        # object can legitimately appear in several distinct table cells on one page; keying by page
        # only silently dropped every cell after the first, losing cell-level traceability.
        existing = self.conn.execute(
            "SELECT pdf, page, table_row, table_col FROM provenance WHERE obj_id=?", (obj_id,)
        ).fetchall()
        seen = {(r[0], r[1], r[2], r[3]) for r in existing}
        for p in new_provs:
            k = (p.pdf, p.page, p.table_row, p.table_col)
            if k not in seen:
                self._add_provenance(obj_id, [p])
                seen.add(k)

    def _record_conflict(self, key: str, id1: str, id2: str):
        self.conn.execute("""
            INSERT INTO conflicts (key, obj_id1, obj_id2, detected_at)
            VALUES (?, ?, ?, ?)
        """, (key, id1, id2, datetime.now(timezone.utc).isoformat()))

    def _queue_review(self, obj_id: str, reason: str):
        self.conn.execute("""
            INSERT INTO reviews (obj_id, reason, created_at, status)
            VALUES (?, ?, ?, 'open')
        """, (obj_id, reason, datetime.now(timezone.utc).isoformat()))

    def _validate_basic(self, content: Dict, otype: str) -> bool:
        # Extracted regimen rows are review candidates, never automatically
        # validated clinical recommendations.  They remain queued until an
        # explicit physician attestation creates a separate governed bundle.
        if otype == "RegimenCandidate":
            return False
        if otype == "Medication" and not content.get("name"):
            return False
        if otype == "Dose" and not (content.get("value") or content.get("raw")):
            return False
        return True

    def validate_all(self) -> List[str]:
        """Real validation run (PHASE 10)."""
        fails = []
        rows = self.conn.execute("SELECT id, type, content, validation_status FROM objects").fetchall()
        for r in rows:
            content = json.loads(r["content"])
            if not self._validate_basic(content, r["type"]):
                fails.append(r["id"])
                self.conn.execute("UPDATE objects SET validation_status='invalid' WHERE id=?", (r["id"],))
        self.conn.commit()
        return fails

    def get_active(self, type_: Optional[str] = None) -> List[Dict]:
        q = "SELECT * FROM objects WHERE status='active'"
        if type_:
            q += " AND type=?"
            rows = self.conn.execute(q, (type_,)).fetchall()
        else:
            rows = self.conn.execute(q).fetchall()
        return [dict(r) | {"content": json.loads(r["content"])} for r in rows]

    def get_reviews(self, status: str = "open") -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM reviews WHERE status=?", (status,)).fetchall()
        return [dict(r) for r in rows]

    def impact_analysis(self, new_doc: Document) -> Dict[str, Any]:
        """Real impact from new doc."""
        affected = []
        if not new_doc.knowledge_objects:
            return {"affected": 0, "details": []}
        for otype, items in new_doc.knowledge_objects.items():
            for item in items:
                content = {k: v for k, v in item.items() if k not in ("source", "provenance", "logical_key")}
                src = item.get("provenance") or item.get("source", {})
                if not isinstance(src, dict):
                    src = {}
                identity = build_identity(
                    otype, content, src, new_doc, str(getattr(new_doc, "pdf_path", "unknown")),
                    explicit_logical_key=item.get("logical_key"),
                )
                rows = self.conn.execute(
                    "SELECT id, type, version FROM objects "
                    "WHERE type=? AND status='active' AND logical_key=?",
                    (otype, identity.logical_key),
                ).fetchall()
                for r in rows:
                    affected.append({"id": r["id"], "type": r["type"], "version": r["version"], "reason": f"overlaps new {otype}"})
        return {"affected": len(affected), "details": affected[:10]}

    def stats(self) -> Dict[str, Any]:
        """PHASE 13 benchmark metrics."""
        c = self.conn.cursor()
        total = c.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
        active = c.execute("SELECT COUNT(*) FROM objects WHERE status IN ('validated','published','active')").fetchone()[0]
        reviews = c.execute("SELECT COUNT(*) FROM reviews WHERE status='open'").fetchone()[0]
        conflicts = c.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0]

        by_type = {}
        for row in c.execute("SELECT type, COUNT(*) FROM objects GROUP BY type"):
            by_type[row[0]] = row[1]

        by_status = {}
        for row in c.execute("SELECT status, COUNT(*) FROM objects GROUP BY status"):
            by_status[row[0]] = row[1]

        return {
            "total_objects": total,
            "active": active,
            "open_reviews": reviews,
            "conflicts": conflicts,
            "by_type": by_type,
            "by_status": by_status
        }

    def close(self):
        self.conn.close()
