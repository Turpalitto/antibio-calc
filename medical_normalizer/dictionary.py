"""Synonym dictionaries for drug, route, and unit normalization.

Data source: JSON files in medical_dictionary/ (source of truth).
Loaded once at import time via medical_dictionary.loader.
Class logic (DrugNormalizer / RouteNormalizer / UnitNormalizer) unchanged.

To add terminology: edit medical_dictionary/*.json, then reimport this module.
Never hardcode dictionaries here.
"""

from __future__ import annotations

import re
from typing import ClassVar

from medical_dictionary import loader

# ── Module-level dictionaries (populated from JSON at import) ──
# These names are imported by validator.py and confidence.py — preserve them.

DRUG_SYNONYMS: dict[str, str] = loader.load_drug_synonyms()
ROUTE_SYNONYMS: dict[str, str] = loader.load_route_synonyms()
UNIT_NORMALIZATION: dict[str, str] = loader.load_unit_normalization()

# New terminology resources (empty until manual review of dictionary_candidates.json)
DRUG_ATC: dict[str, str] = loader.load_drug_atc()
DRUG_GROUPS: dict[str, str] = loader.load_drug_groups()


class DrugNormalizer:
    """Normalize drug names using synonym dictionary."""

    _strip_paren_re: ClassVar[re.Pattern] = re.compile(r"\s*\([^)]*\)\s*")
    _strip_marker_re: ClassVar[re.Pattern] = re.compile(r"^[#*]+|[#*]+$")

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        if not raw or not raw.strip():
            return ""
        cleaned = cls.clean(raw)
        # Direct lookup
        if cleaned.lower() in DRUG_SYNONYMS:
            return DRUG_SYNONYMS[cleaned.lower()]
        # Case-insensitive fallback
        for alias, canonical in DRUG_SYNONYMS.items():
            if cleaned.lower() == alias:
                return canonical
        # No synonym found — return cleaned original
        return cleaned

    _normalize_spaces_re: ClassVar[re.Pattern] = re.compile(r"\s*\+\s*")

    @classmethod
    def clean(cls, raw: str) -> str:
        """Strip extraction markers like **, #, normalize spaces around +."""
        result = raw.strip()
        result = cls._strip_marker_re.sub("", result)
        result = cls._normalize_spaces_re.sub(" + ", result)
        return result.strip()


class RouteNormalizer:
    """Normalize route strings to controlled vocabulary."""

    _compound_sep_re: ClassVar[re.Pattern] = re.compile(r"\s*(?:,|\s+или\s+)\s*")

    @classmethod
    def _match_single_route(cls, text: str) -> str | None:
        """Match a single route str (possibly containing /). Exact match only."""
        if text in ROUTE_SYNONYMS:
            return ROUTE_SYNONYMS[text]
        return None

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        if not raw or not raw.strip():
            return "unknown"
        cleaned = raw.strip().lower()
        # Try exact match first
        result = cls._match_single_route(cleaned)
        if result:
            return result
        # Check if it's a compound route (contains или or comma)
        if "или" in cleaned or "," in cleaned:
            parts = [p.strip() for p in cls._compound_sep_re.split(cleaned) if p.strip()]
            normalized_parts = []
            for part in parts:
                matched = cls._match_single_route(part)
                if matched:
                    normalized_parts.append(matched)
            if len(normalized_parts) >= 2:
                return "|".join(dict.fromkeys(normalized_parts))
            if normalized_parts:
                return normalized_parts[0]
        # Unknown
        return "unknown"


class UnitNormalizer:
    """Normalize dose units to standard abbreviations."""

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        if not raw or not raw.strip():
            return ""
        cleaned = raw.strip().lower()
        if cleaned in UNIT_NORMALIZATION:
            return UNIT_NORMALIZATION[cleaned]
        # Remove trailing period
        cleaned = cleaned.rstrip(".")
        if cleaned in UNIT_NORMALIZATION:
            return UNIT_NORMALIZATION[cleaned]
        return raw.strip()

    @classmethod
    def convert_to_mg(cls, value: float, unit: str) -> float:
        """Convert common units to mg for uniform comparison."""
        unit_norm = cls.normalize(unit)
        if unit_norm == "g":
            return value * 1000.0
        elif unit_norm == "mcg":
            return value / 1000.0
        elif unit_norm == "mg":
            return value
        elif unit_norm == "ml":
            # Can't reliably convert volume to mass — return as-is
            return value
        return value
