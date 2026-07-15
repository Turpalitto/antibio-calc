"""Extraction config loader. Loads from config/document_processing.yaml."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any
import yaml
import os


@dataclass
class ExtractionConfig:
    primary: str = "pymupdf"
    fallbacks: List[str] = field(default_factory=lambda: ["mineru"])
    min_quality: float = 0.65
    min_cyrillic_ratio: float = 0.1
    max_empty_pages_ratio: float = 0.3
    per_page_fallback: bool = True
    cache_enabled: bool = True
    cache_path: str = "cache/extraction"
    metrics_enabled: bool = True
    quality_threshold: float = 0.65
    bad_page_text_threshold: int = 50


def load_config() -> ExtractionConfig:
    """Load from project config/document_processing.yaml if exists, else defaults."""
    # project root relative to this file: ../../..
    here = Path(__file__).resolve()
    project_root = here.parents[3]  # src/pipeline/extraction -> project
    cfg_path = project_root / "config" / "document_processing.yaml"

    cfg = ExtractionConfig()
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
        except Exception:
            pass  # silent fallback to defaults
    return cfg


CONFIG = load_config()


def get_config() -> ExtractionConfig:
    return CONFIG
