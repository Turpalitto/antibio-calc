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

    _strip_marker_re: ClassVar[re.Pattern] = re.compile(r"^[#*]+|[#*]+$")

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        if not raw or not raw.strip():
            return ""
        cleaned = cls.clean(raw)
        # Direct lookup (DRUG_SYNONYMS keys are lowercase by governance —
        # see medical_dictionary tests — so there is no case-insensitive
        # fallback loop: it could never fire. L2)
        return DRUG_SYNONYMS.get(cleaned.lower(), cleaned)

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

    # Compound separators: "," and the Russian "или". "/" is NOT listed here
    # because it is part of the Russian abbreviations themselves ("в/в", "в/м")
    # — slash-joined sequences are resolved by _resolve_slash_sequence.
    _compound_sep_re: ClassVar[re.Pattern] = re.compile(r"\s*(?:,|\s+или\s+)\s*")
    _slash_re: ClassVar[re.Pattern] = re.compile(r"\s*/\s*")

    # Real route aliases only — the dictionary also contains separator
    # entries ("или", ",", "/") whose value is "|"; those must never be
    # tokenized as a route.
    _route_aliases: ClassVar[tuple[str, ...]] = tuple(sorted(
        (a for a, v in ROUTE_SYNONYMS.items() if v != "|"),
        key=len,
        reverse=True,
    ))

    @classmethod
    def _match_single_route(cls, text: str) -> str | None:
        """Match a single route str (possibly containing /). Exact match only."""
        return ROUTE_SYNONYMS.get(text)

    @classmethod
    def _resolve_slash_sequence(cls, text: str) -> list[str] | None:
        """Resolve a slash-joined route sequence such as "в/в/в/м".

        Matches known route aliases left to right, longest alias first, and
        requires them to be separated by "/" with no other text in between.
        Returns None when the string is not such a sequence, or when only a
        single alias matched (that case is handled by exact lookup).
        """
        matched: list[str] = []
        rest = text.strip()
        while rest:
            for alias in cls._route_aliases:
                if rest.startswith(alias):
                    matched.append(alias)
                    rest = rest[len(alias):].strip()
                    if rest.startswith("/"):
                        rest = cls._slash_re.sub("", rest, count=1)
                    elif rest:
                        return None  # trailing junk -> not a clean sequence
                    break
            else:
                return None
        return matched if len(matched) >= 2 else None

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        if not raw or not raw.strip():
            return "unknown"
        cleaned = raw.strip().lower()
        # Try exact match first
        result = cls._match_single_route(cleaned)
        if result:
            return result
        # Compound route: "в/в или в/м", "в/в, в/м"
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
        # Slash-joined sequence: "в/в/в/м" -> iv|im
        sequence = cls._resolve_slash_sequence(cleaned)
        if sequence:
            normalized_parts = [cls._match_single_route(alias) for alias in sequence]
            if all(normalized_parts):
                return "|".join(dict.fromkeys(normalized_parts))
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
        # Unmapped: return the CLEANED value, not the original casing. Keeping
        # "МГ/КГ" uppercase guaranteed a DOSE_UNIT_UNKNOWN review downstream
        # (L5).
        return cleaned

    # Mass units that convert to mg. Volume (ml) and activity (IU,
    # thousand_IU) units and weight/time-qualified doses (mg/kg, mg/kg/day)
    # are NOT mass — converting them would silently conflate dimensions.
    _MASS_TO_MG: ClassVar[dict[str, float]] = {"g": 1000.0, "mg": 1.0, "mcg": 0.001}

    @classmethod
    def is_mass_unit(cls, unit: str | None) -> bool:
        """True when the unit is a pure mass unit convertible to mg."""
        return cls.normalize(unit) in cls._MASS_TO_MG

    @classmethod
    def convert_to_mg(cls, value: float, unit: str) -> float:
        """Convert a pure mass unit to mg for uniform comparison.

        Raises ValueError for any unit that is not a mass unit (ml, IU,
        thousand_IU, mg/kg, mg/kg/day, unmapped units). Previously ml was
        returned as-is, which conflated volume with mass (L4).
        """
        unit_norm = cls.normalize(unit)
        factor = cls._MASS_TO_MG.get(unit_norm)
        if factor is None:
            raise ValueError(
                f"Cannot convert unit '{unit}' to mg: not a pure mass unit. "
                f"Convertible units: {sorted(cls._MASS_TO_MG)}."
            )
        return value * factor
