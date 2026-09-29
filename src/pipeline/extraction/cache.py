"""Transparent extraction cache.

Two defects are addressed here:

* **M-20 -- stale entries.**  The key was the PDF's sha256 alone, so changing the
  extractor (or any of its dependencies) left every cached document permanently
  stale with no way to invalidate it.  The key now includes an extractor code
  fingerprint: change any extraction module and every entry misses.
* **M-20 -- half-serialised documents.**  ``_doc_to_dict`` dropped entities,
  knowledge_objects, structured_tables, markdown and warnings, so a cache HIT
  still re-ran the expensive semantic stage while the cheap text stage was saved.
  Those fields now round-trip.

Writes are staged and moved into place with ``os.replace`` (atomic), so a crash
cannot leave a truncated cache entry that later reads as a hit.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional
import time

from .base import BoundingBox, Document, Page, TableCell, TableObject
from .config import get_config

# Bump when the serialised shape changes, so old entries are ignored rather than
# misread.
CACHE_SCHEMA_VERSION = 2

# Files whose content participates in the cache key: any change to the extraction
# logic must invalidate every entry.
_EXTRACTOR_SOURCES = (
    "base.py", "pymupdf.py", "router.py", "layout.py", "semantic.py",
    "quality.py", "metrics.py", "docling.py", "mineru.py", "config.py",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extractor_fingerprint() -> str:
    """SHA256 over the extraction source files.

    M-20: without this the cache key was the PDF hash alone, so a fixed extractor
    bug stayed invisible behind a permanent cache hit.
    """
    here = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    digest.update(f"schema={CACHE_SCHEMA_VERSION}\n".encode())
    for name in sorted(_EXTRACTOR_SOURCES):
        path = here / name
        digest.update(name.encode())
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
    return digest.hexdigest()[:16]


def _bbox_to_dict(bbox: Optional[BoundingBox]) -> Optional[list]:
    return [bbox.x0, bbox.y0, bbox.x1, bbox.y1] if bbox else None


def _bbox_from_dict(data: Optional[list]) -> Optional[BoundingBox]:
    if not data or len(data) != 4:
        return None
    return BoundingBox(data[0], data[1], data[2], data[3])


def _table_to_dict(table: TableObject) -> dict:
    return {
        "page_num": table.page_num,
        "bbox": [table.bbox.x0, table.bbox.y0, table.bbox.x1, table.bbox.y1],
        "rows": table.rows,
        "cols": table.cols,
        "header_rows": table.header_rows,
        "confidence": table.confidence,
        "engine": table.engine,
        "source_pdf": table.source_pdf,
        "cells": [
            {
                "row": c.row, "col": c.col, "text": c.text,
                "bbox": _bbox_to_dict(c.bbox), "confidence": c.confidence,
                "engine": c.engine, "source_pdf": c.source_pdf, "page_num": c.page_num,
            }
            for c in table.cells
        ],
    }


def _table_from_dict(data: dict) -> TableObject:
    return TableObject(
        page_num=data["page_num"],
        bbox=_bbox_from_dict(data.get("bbox")) or BoundingBox(0, 0, 0, 0),
        rows=data["rows"], cols=data["cols"],
        cells=[
            TableCell(
                row=c["row"], col=c["col"], text=c.get("text", ""),
                bbox=_bbox_from_dict(c.get("bbox")),
                confidence=c.get("confidence", 0.0), engine=c.get("engine", "unknown"),
                source_pdf=c.get("source_pdf", ""), page_num=c.get("page_num", 0),
            )
            for c in data.get("cells", [])
        ],
        header_rows=data.get("header_rows", 0),
        confidence=data.get("confidence", 0.0),
        engine=data.get("engine", "table-transformer+rapidtable"),
        source_pdf=data.get("source_pdf", ""),
    )


def _doc_to_dict(doc: Document) -> dict:
    return {
        "source": doc.source,
        "pdf_path": str(doc.pdf_path),
        "full_text": doc.full_text,
        "confidence": doc.confidence,
        "metadata": doc.metadata,
        # M-20: these were all dropped, so the expensive stages re-ran on a hit.
        "markdown": doc.markdown,
        "images": doc.images,
        "warnings": doc.warnings,
        "errors": doc.errors,
        "elapsed_time_ms": doc.elapsed_time_ms,
        "entities": doc.entities,
        "knowledge_objects": doc.knowledge_objects,
        "tables": doc.tables,
        "structured_tables": [_table_to_dict(t) for t in doc.structured_tables],
        "pages": [
            {
                "page_num": p.page_num,
                "text": p.text,
                "tables": p.tables,
                "layout_blocks": p.layout_blocks,
                "entities": p.entities,
                "structured_tables": [_table_to_dict(t) for t in p.structured_tables],
            }
            for p in doc.pages
        ],
    }


def _dict_to_doc(d: dict) -> Document:
    pages = [
        Page(
            page_num=p["page_num"],
            text=p["text"],
            tables=p.get("tables", []),
            layout_blocks=p.get("layout_blocks", []),
            entities=p.get("entities", []),
            structured_tables=[_table_from_dict(t) for t in p.get("structured_tables", [])],
        )
        for p in d.get("pages", [])
    ]
    return Document(
        source=d["source"],
        pdf_path=Path(d["pdf_path"]),
        pages=pages,
        full_text=d["full_text"],
        metadata=d.get("metadata", {}),
        confidence=d.get("confidence", 0.8),
        markdown=d.get("markdown", ""),
        images=d.get("images", []),
        warnings=d.get("warnings", []),
        errors=d.get("errors", []),
        elapsed_time_ms=d.get("elapsed_time_ms", 0.0),
        entities=d.get("entities", []),
        knowledge_objects=d.get("knowledge_objects", {}),
        tables=d.get("tables", []),
        structured_tables=[_table_from_dict(t) for t in d.get("structured_tables", [])],
    )


class ExtractionCache:
    def __init__(self):
        self.cfg = get_config()
        self.enabled = getattr(self.cfg, "cache_enabled", True)
        self.root = Path(getattr(self.cfg, "cache_path", "cache/extraction"))
        self.root.mkdir(parents=True, exist_ok=True)
        # Recomputed per process so an edited extractor invalidates immediately.
        self._fingerprint: Optional[str] = None

    @property
    def fingerprint(self) -> str:
        if self._fingerprint is None:
            self._fingerprint = extractor_fingerprint()
        return self._fingerprint

    def _path(self, key: str) -> Path:
        return self.root / key / "document.json"

    def _key(self, pdf_path: Path) -> str:
        """M-20: PDF hash AND extractor fingerprint, never the PDF hash alone."""
        return f"{_sha256(pdf_path)}-{self.fingerprint}"

    def get(self, pdf_path: Path) -> Optional[Document]:
        if not self.enabled:
            return None
        try:
            p = self._path(self._key(pdf_path))
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
                    return None
                if data.get("extractor_fingerprint") != self.fingerprint:
                    return None
                doc = _dict_to_doc(data)
                doc.metadata.setdefault("cache_hit", True)
                doc.metadata["cache_hit_time"] = time.time()
                return doc
        except Exception:
            pass
        return None

    def put(self, pdf_path: Path, doc: Document) -> None:
        if not self.enabled:
            return
        try:
            key = self._key(pdf_path)
            d = self.root / key
            d.mkdir(parents=True, exist_ok=True)
            data = _doc_to_dict(doc)
            data["cached_at"] = time.time()
            data["cache_schema_version"] = CACHE_SCHEMA_VERSION
            data["extractor_fingerprint"] = self.fingerprint
            target = self._path(key)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(d), prefix=target.name + ".", suffix=".tmp"
            )
            tmp = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, target)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
        except Exception:
            pass  # cache miss is not fatal


_cache = ExtractionCache()


def get_cache() -> ExtractionCache:
    return _cache
