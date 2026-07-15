"""Loader for medical_dictionary JSON terminology files.

Cached, read-only. All loaders return plain dicts/lists. No parser logic.
dictionary.py imports these to populate its module-level dicts.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))


def _path(filename: str) -> str:
    return os.path.join(_DIR, filename)


def _load_json(filename: str) -> dict[str, Any]:
    with open(_path(filename), "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_drug_synonyms() -> dict[str, str]:
    """Return alias → canonical drug name mapping."""
    data = _load_json("drug_synonyms.json")
    return dict(data["entries"])


@lru_cache(maxsize=1)
def load_drug_atc() -> dict[str, str]:
    """Return canonical drug name → ATC code. Empty until manual review."""
    data = _load_json("drug_atc.json")
    return dict(data["entries"])


@lru_cache(maxsize=1)
def load_drug_groups() -> dict[str, str]:
    """Return group name → ATC prefix. Empty until manual review."""
    data = _load_json("drug_groups.json")
    return dict(data["entries"])


@lru_cache(maxsize=1)
def load_route_synonyms() -> dict[str, str]:
    """Return route alias → canonical route."""
    data = _load_json("route_dictionary.json")
    return dict(data["entries"])


@lru_cache(maxsize=1)
def load_unit_normalization() -> dict[str, str]:
    """Return unit alias → canonical unit abbreviation."""
    data = _load_json("unit_dictionary.json")
    return dict(data["entries"])


@lru_cache(maxsize=1)
def load_metadata() -> dict[str, Any]:
    """Return metadata.json (version, counts, file inventory)."""
    return _load_json("metadata.json")


def reload_all() -> None:
    """Clear all caches. For tests / hot-reload after editing JSON."""
    load_drug_synonyms.cache_clear()
    load_drug_atc.cache_clear()
    load_drug_groups.cache_clear()
    load_route_synonyms.cache_clear()
    load_unit_normalization.cache_clear()
    load_metadata.cache_clear()
