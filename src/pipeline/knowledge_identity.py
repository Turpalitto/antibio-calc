"""Deterministic identity contract for immutable Knowledge Objects."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_VOLATILE_FIELDS = frozenset({
    "confidence", "created_at", "history", "logical_key", "normalization_status",
    "provenance", "relationships", "review_status", "source", "timestamp", "updated_at",
})


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return _normalize(str(value))


def canonical_json(value: Any) -> str:
    return json.dumps(_normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_content(content: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in content.items() if key not in _VOLATILE_FIELDS}


def content_hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(semantic_content(content)).encode("utf-8")).hexdigest()


def clinical_scope(type_: str, source: dict[str, Any], doc: Any, pdf_name: str) -> dict[str, Any]:
    metadata = getattr(doc, "metadata", {}) or {}
    return {
        "type": type_,
        "guideline_id": source.get("guideline_id") or metadata.get("guideline_id"),
        "pdf": Path(pdf_name).name,
        "page": source.get("page", source.get("page_num", 0)),
        "paragraph": source.get("paragraph"),
        "bounding_box": source.get("bounding_box") or source.get("bbox"),
        "table_row": source.get("table_row", source.get("row")),
        "table_col": source.get("table_col", source.get("col")),
    }


@dataclass(frozen=True, slots=True)
class ObjectIdentity:
    logical_key: str
    content_hash: str
    clinical_scope: str
    object_id: str


def build_identity(type_: str, content: dict[str, Any], source: dict[str, Any], doc: Any, pdf_name: str,
                   explicit_logical_key: str | None = None) -> ObjectIdentity:
    scope = clinical_scope(type_, source, doc, pdf_name)
    scope_json = canonical_json(scope)
    digest = content_hash(content)
    if explicit_logical_key and explicit_logical_key.strip():
        logical_payload = {"type": type_, "producer_key": explicit_logical_key.strip()}
    else:
        logical_payload = {"type": type_, "scope": scope, "semantic_content": semantic_content(content)}
    logical = "lk_" + hashlib.sha256(canonical_json(logical_payload).encode("utf-8")).hexdigest()
    version_id = hashlib.sha256(f"{type_}:{logical}:{digest}".encode("utf-8")).hexdigest()[:24]
    return ObjectIdentity(logical, digest, scope_json, f"{type_[:3].lower()}_{version_id}")
