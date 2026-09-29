"""Extraction config loader. Loads from config/document_processing.yaml."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any
import yaml
import os

logger = logging.getLogger(__name__)


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


# L-31: `here.parents[3]` is silently wrong if the file moves; anchor on a marker
# that must exist instead of on a fixed depth.
_CONFIG_MARKER = Path("src") / "pipeline" / "extraction" / "config.py"


def project_root() -> Path:
    """Repository root, resolved by walking up to the marker path."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / _CONFIG_MARKER) == here:
            return candidate
    # the marker check above only holds for this exact file; fall back to depth
    return here.parents[3]


def load_config() -> ExtractionConfig:
    """Load from project config/document_processing.yaml if it exists, else defaults.

    L-30: ``min_quality`` and ``max_empty_pages_ratio`` were set here but never
    READ by any consumer, and a malformed YAML was swallowed by a bare
    ``except Exception: pass`` -- so a typo in the config file silently changed
    nothing at all.  Malformed YAML now raises.
    """
    cfg_path = project_root() / "config" / "document_processing.yaml"

    cfg = ExtractionConfig()
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{cfg_path} must contain a YAML mapping, got {type(data).__name__}")
        unknown = [k for k in data if not hasattr(cfg, k)]
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        if unknown:
            # L-30: unread keys were assigned and then ignored.
            logger.warning(
                "%s sets keys with no ExtractionConfig field: %s (ignored)",
                cfg_path, ", ".join(sorted(unknown)),
            )
    return cfg


CONFIG = load_config()


def get_config() -> ExtractionConfig:
    return CONFIG
