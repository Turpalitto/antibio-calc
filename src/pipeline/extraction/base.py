"""Base for document extraction. Unified format so Parser stays untouched."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class BoundingBox:
    """Pixel coordinates (top-left origin from page render)."""
    x0: float
    y0: float
    x1: float
    y1: float
    page: int = 0


@dataclass
class TableCell:
    """Single cell with provenance. Used for cell-level traceability."""
    row: int
    col: int
    text: str = ""
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.0
    # lineage
    engine: str = "unknown"
    source_pdf: str = ""
    page_num: int = 0


@dataclass
class TableObject:
    """Structured table. Primary for P4.5. Backward compatible via .to_dict()."""
    page_num: int
    bbox: BoundingBox
    rows: int
    cols: int
    cells: List[TableCell] = field(default_factory=list)
    header_rows: int = 0
    confidence: float = 0.0
    engine: str = "table-transformer+rapidtable"
    source_pdf: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_num": self.page_num,
            "bbox": [self.bbox.x0, self.bbox.y0, self.bbox.x1, self.bbox.y1],
            "rows": self.rows,
            "cols": self.cols,
            "header_rows": self.header_rows,
            "confidence": self.confidence,
            "engine": self.engine,
            "cells": [
                {
                    "row": c.row,
                    "col": c.col,
                    "text": c.text,
                    "bbox": [c.bbox.x0, c.bbox.y0, c.bbox.x1, c.bbox.y1] if c.bbox else None,
                    "confidence": c.confidence,
                    "engine": c.engine,
                }
                for c in self.cells
            ],
        }


@dataclass
class Page:
    page_num: int
    text: str
    tables: List[Dict[str, Any]] = field(default_factory=list)  # legacy dict form for compat
    # P4.2 / P4.5 Layout + structured tables (additive, does not remove old)
    layout_blocks: List[Dict[str, Any]] = field(default_factory=list)
    structured_tables: List[TableObject] = field(default_factory=list)
    # P4.3 Semantic
    entities: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_objects: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)


@dataclass
class Document:
    """Unified output. Parser sees only this. Extended for multi-engine (P4.1)."""
    source: str
    pdf_path: Path
    pages: List[Page]
    full_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    tables: List[Dict[str, Any]] = field(default_factory=list)  # legacy aggregate
    structured_tables: List[TableObject] = field(default_factory=list)  # P4.5 primary structured form
    # Standardized fields for P4.1 multi-engine
    markdown: str = ""
    images: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    elapsed_time_ms: float = 0.0
    # provenance kept in metadata for backward
    # P4.3 Semantic entities
    entities: List[Dict[str, Any]] = field(default_factory=list)
    # P4.4 Knowledge Base
    knowledge_objects: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)


class DocumentExtractor:
    """Interface. All extractors implement this."""

    def extract(self, pdf_path: Path) -> Document:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError
