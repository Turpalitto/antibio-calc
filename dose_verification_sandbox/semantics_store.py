"""Phase 8 — Semantic enrichment store (RC-030).

An additive, append-only SQLite store for DoseSemantics, entirely separate
from assembled_regimens.sqlite. Never opens the source database for writing.
Rebuilds are idempotent: re-running against unchanged source data and an
unchanged parser produces no new rows (content-hash deduplication on
(regimen_id, regimen_version, content_hash)); a genuine change in
classification logic or source data adds a new row without deleting the old
one, preserving full history. "Current" semantics for a regimen is always the
most recently computed row for that (regimen_id, regimen_version).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .semantics_models import DoseSemantics

SCHEMA_VERSION = 1
STORE_PATH = Path(__file__).parent / "data" / "dose_semantics_store.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS dose_semantics (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    semantics_id TEXT NOT NULL,
    regimen_id TEXT NOT NULL,
    regimen_version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    semantic_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE(regimen_id, regimen_version, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_dose_semantics_regimen ON dose_semantics(regimen_id, regimen_version);
"""


def _content_hash(ds: DoseSemantics) -> str:
    d = ds.to_dict()
    d.pop("semantics_id", None)
    d.pop("created_at", None)
    canonical = json.dumps(d, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    cur = conn.execute("SELECT COUNT(*) FROM schema_meta")
    if cur.fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_meta (schema_version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    return conn


def rebuild_store(semantics: Iterable[DoseSemantics], path: Path = STORE_PATH) -> dict:
    """Idempotent: unchanged (regimen_id, regimen_version, content) pairs are
    skipped via UNIQUE constraint; only genuinely new/changed rows are added."""
    conn = _connect(path)
    inserted = 0
    skipped = 0
    try:
        for ds in semantics:
            content_hash = _content_hash(ds)
            payload = json.dumps(ds.to_dict(), ensure_ascii=False)
            try:
                conn.execute(
                    "INSERT INTO dose_semantics "
                    "(semantics_id, regimen_id, regimen_version, content_hash, semantic_type, payload, computed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ds.semantics_id, ds.regimen_id, ds.regimen_version, content_hash,
                     ds.semantic_type, payload, ds.created_at),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    finally:
        conn.close()
    return {"inserted": inserted, "skipped_unchanged": skipped}


def get_current(regimen_id: str, regimen_version: int, path: Path = STORE_PATH) -> dict | None:
    """Most recently computed semantics for a (regimen_id, regimen_version)."""
    if not path.exists():
        return None
    conn = _connect(path)
    try:
        cur = conn.execute(
            "SELECT payload FROM dose_semantics WHERE regimen_id=? AND regimen_version=? "
            "ORDER BY row_id DESC LIMIT 1",
            (str(regimen_id), regimen_version),
        )
        row = cur.fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def history(regimen_id: str, regimen_version: int, path: Path = STORE_PATH) -> list[dict]:
    if not path.exists():
        return []
    conn = _connect(path)
    try:
        cur = conn.execute(
            "SELECT payload FROM dose_semantics WHERE regimen_id=? AND regimen_version=? ORDER BY row_id ASC",
            (str(regimen_id), regimen_version),
        )
        return [json.loads(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()
