"""DrugParser — normalize drug names, extract components, map to ATC."""

from __future__ import annotations

import re
from typing import ClassVar

from medical_normalizer.dictionary import DrugNormalizer, UnitNormalizer
from medical_normalizer.models import DrugComponent, NormalizedRegimen


def _coerce_str(val) -> str:
    """Coerce a raw extraction value to a string.

    None/falsy (0, None, "", [], False) -> "".
    int/float -> str(val). str -> as-is.
    Protects downstream .strip() / regex from non-string inputs.
    """
    if not val:
        return ""
    if isinstance(val, str):
        return val
    return str(val)


class DrugParser:
    """Parse and normalize drug information from raw regimen."""

    _component_sep_re: ClassVar[re.Pattern] = re.compile(r"\s*\+\s*")
    _dose_ratio_re: ClassVar[re.Pattern] = re.compile(r"(\d[\d,.]*)\s*[/÷]\s*(\d[\d,.]*)")

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        """Set drug_original, drug_normalized, drug_components, atc_code."""
        drug_raw = _coerce_str(raw.get("antibiotic", "") or raw.get("drug", "") or "")
        dose_raw = _coerce_str(raw.get("dose", "") or "")
        unit_raw = _coerce_str(raw.get("unit", "") or "")

        regimen.drug_original = drug_raw.strip()
        regimen.drug_normalized = DrugNormalizer.normalize(drug_raw)

        # Parse components
        components = cls._parse_components(drug_raw, dose_raw, unit_raw)
        regimen.drug_components = components

        # Deterministic detection of OR blocks (for combos without per-option dosing)
        drug_lower = drug_raw.lower()
        if " или " in drug_lower or " or " in drug_lower or re.search(r"\bor\b", drug_lower):
            if not regimen.warnings:
                regimen.warnings = []
            if "STRUCTURED_OPTION_LIST" not in regimen.warnings:
                regimen.warnings.append("STRUCTURED_OPTION_LIST")

        return regimen

    @classmethod
    def _parse_components(
        cls, drug_raw: str, dose_raw: str, unit_raw: str
    ) -> list[DrugComponent]:
        """Split combination drugs into components with individual doses."""
        cleaned = DrugNormalizer.clean(drug_raw)
        drug_names = cls._component_sep_re.split(cleaned)
        drug_names = [d.strip() for d in drug_names if d.strip()]

        if len(drug_names) <= 1:
            return []

        # Try to split dose by / or ÷ into per-component doses
        doses = cls._parse_component_doses(dose_raw)

        components: list[DrugComponent] = []
        for i, name in enumerate(drug_names):
            dose_val = None
            dose_u = unit_raw if unit_raw else None
            if doses and i < len(doses):
                dose_val = doses[i]
            components.append(
                DrugComponent(
                    name=DrugNormalizer.normalize(name),
                    dose_value=dose_val,
                    dose_unit=UnitNormalizer.normalize(unit_raw) if dose_u else None,
                )
            )
        return components

    @classmethod
    def _parse_component_doses(cls, dose_raw: str) -> list[float] | None:
        """Parse '875/125' or '500/50' into [875.0, 125.0]."""
        dose_raw = _coerce_str(dose_raw)
        if not dose_raw or not dose_raw.strip():
            return None
        match = cls._dose_ratio_re.search(dose_raw.strip())
        if match:
            try:
                v1 = float(match.group(1).replace(",", "."))
                v2 = float(match.group(2).replace(",", "."))
                return [v1, v2]
            except (ValueError, TypeError):
                return None
        return None


class DoseNormalizer:
    """Extract numeric dose value and normalize unit."""

    _dose_re: ClassVar[re.Pattern] = re.compile(
        r"(\d[\d\s,.]*)(?:\s*[-–—]\s*(\d[\d\s,.]*))?\s*"
    )
    _comma_re: ClassVar[re.Pattern] = re.compile(r",")
    _space_re: ClassVar[re.Pattern] = re.compile(r"\s+")

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        """Extract dose_value and dose_unit from raw regimen.

        RC-030 repair Phase 9: `dose_value` is preserved byte-for-byte as the
        LOWER bound (unchanged legacy behavior). Additionally, when the raw
        dose is an explicit range ("1,0-2,0"), the UPPER bound — which was
        previously read by the regex's group(2) and then silently discarded —
        is now preserved in dose_max, with dose_is_range=True so scalar-only
        consumers know they are incomplete.
        """
        dose_raw = _coerce_str(raw.get("dose", "")).strip()
        unit_raw = _coerce_str(raw.get("unit", "")).strip()

        if not dose_raw:
            regimen.dose_value = None
            regimen.dose_unit = cls._normalize_unit(unit_raw) if unit_raw else None
            regimen.dose_is_range = None
            return regimen

        # Normalize decimal comma to decimal point
        cleaned = cls._comma_re.sub(".", dose_raw)
        cleaned = cls._space_re.sub("", cleaned)

        # Try as single number first
        try:
            regimen.dose_value = float(cleaned)
            regimen.dose_unit = cls._normalize_unit(unit_raw)
            regimen.dose_min = regimen.dose_max = regimen.dose_value
            regimen.dose_is_range = False
            regimen.dose_range_raw = dose_raw
            regimen.dose_range_confidence = 1.0
            return regimen
        except (ValueError, TypeError):
            pass

        # Try to parse range: "1,0-2,0"
        match = cls._dose_re.match(dose_raw)
        if match:
            try:
                val = float(match.group(1).replace(",", "."))
                regimen.dose_value = val  # legacy scalar remains the LOWER bound
                regimen.dose_unit = cls._normalize_unit(unit_raw)
                regimen.dose_min = val
                # Preserve group(2) upper bound (previously discarded).
                upper_raw = match.group(2)
                if upper_raw is not None:
                    try:
                        upper = float(upper_raw.replace(",", "."))
                        if upper > val:
                            regimen.dose_max = upper
                            regimen.dose_is_range = True
                            regimen.dose_range_raw = dose_raw
                            regimen.dose_source_start, regimen.dose_source_end = match.span()
                            regimen.dose_range_confidence = 1.0
                        else:
                            regimen.dose_max = val
                            regimen.dose_is_range = False
                            regimen.dose_range_confidence = 0.5  # malformed range (upper<=lower)
                    except (ValueError, TypeError):
                        regimen.dose_max = val
                        regimen.dose_is_range = None  # RANGE_PARSE_AMBIGUOUS
                else:
                    regimen.dose_max = val
                    regimen.dose_is_range = False
                    regimen.dose_range_raw = dose_raw
                    regimen.dose_range_confidence = 1.0
                return regimen
            except (ValueError, TypeError):
                pass

        regimen.dose_value = None
        regimen.dose_unit = cls._normalize_unit(unit_raw) if unit_raw else None
        regimen.dose_is_range = None  # RANGE_PARSE_AMBIGUOUS
        return regimen

    @classmethod
    def _normalize_unit(cls, unit: str) -> str | None:
        from medical_normalizer.dictionary import UnitNormalizer

        result = UnitNormalizer.normalize(unit)
        return result if result else None
