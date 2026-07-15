"""Transparent OCR result cache. Keyed by SHA256 of PDF bytes."""

import hashlib
import json
from pathlib import Path
from typing import Optional
import time

from .base import Document, Page
from .config import get_config


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _doc_to_dict(doc: Document) -> dict:
    return {
        "source": doc.source,
        "pdf_path": str(doc.pdf_path),
        "full_text": doc.full_text,
        "confidence": doc.confidence,
        "metadata": doc.metadata,
        "pages": [
            {"page_num": p.page_num, "text": p.text, "tables": p.tables}
            for p in doc.pages
        ],
    }


def _dict_to_doc(d: dict) -> Document:
    pages = [Page(page_num=p["page_num"], text=p["text"], tables=p.get("tables", [])) for p in d.get("pages", [])]
    return Document(
        source=d["source"],
        pdf_path=Path(d["pdf_path"]),
        pages=pages,
        full_text=d["full_text"],
        metadata=d.get("metadata", {}),
        confidence=d.get("confidence", 0.8),
    )


class ExtractionCache:
    def __init__(self):
        self.cfg = get_config()
        self.enabled = getattr(self.cfg, "cache_enabled", True)
        self.root = Path(getattr(self.cfg, "cache_path", "cache/extraction"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key / "document.json"

    def get(self, pdf_path: Path) -> Optional[Document]:
        if not self.enabled:
            return None
        try:
            key = _sha256(pdf_path)
            p = self._path(key)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
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
            key = _sha256(pdf_path)
            d = self.root / key
            d.mkdir(parents=True, exist_ok=True)
            data = _doc_to_dict(doc)
            data["cached_at"] = time.time()
            with open(self._path(key), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # cache miss is not fatal


_cache = ExtractionCache()


def get_cache() -> ExtractionCache:
    return _cache