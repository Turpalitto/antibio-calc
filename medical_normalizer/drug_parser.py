"""DrugParser — normalize drug names, extract components, map to ATC."""

from __future__ import annotations

import math
import re
from typing import ClassVar

from medical_normalizer.dictionary import (
    DRUG_ATC,
    DrugNormalizer,
    UnitNormalizer,
)
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


def _coerce_text(val) -> tuple[str, bool]:
    """Coerce a raw text value to a stripped string.

    Returns (text, ok). ``ok`` is False when the field was absent, empty or
    not a string — callers record a MISSING_FIELD_INPUT ParserError (H2)
    instead of silently treating garbage as "no information".
    """
    if val is None:
        return "", False
    if not isinstance(val, str):
        return "", False
    text = val.strip()
    return text, bool(text)


class DrugParser:
    """Parse and normalize drug information from raw regimen."""

    _component_sep_re: ClassVar[re.Pattern] = re.compile(r"\s*[+/]\s*")
    _dose_ratio_sep_re: ClassVar[re.Pattern] = re.compile(r"\s*[/÷]\s*")
    _or_block_re: ClassVar[re.Pattern] = re.compile(r"\s+или\s+|\s+or\s+|\bor\b")

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        """Set drug_original, drug_normalized, drug_components, atc_code."""
        drug_raw = _coerce_str(raw.get("antibiotic", "") or raw.get("drug", "") or "")
        dose_raw = _coerce_str(raw.get("dose", "") or "")
        unit_raw = _coerce_str(raw.get("unit", "") or "")

        regimen.drug_original = drug_raw.strip()
        regimen.drug_normalized = DrugNormalizer.normalize(drug_raw)
        # L1: atc_code is populated from the governed DRUG_ATC mapping
        # (canonical drug name -> ATC code). The mapping is empty until
        # manual review, so this is a no-op today but the field is no longer
        # a permanently-dead claim in the docstring.
        regimen.atc_code = cls._lookup_atc(regimen.drug_normalized)

        # Parse components
        components = cls._parse_components(drug_raw, dose_raw, unit_raw)
        regimen.drug_components = components

        # Deterministic detection of OR blocks (for combos without per-option dosing)
        drug_lower = drug_raw.lower()
        if cls._or_block_re.search(drug_lower):
            if not regimen.warnings:
                regimen.warnings = []
            if "STRUCTURED_OPTION_LIST" not in regimen.warnings:
                regimen.warnings.append("STRUCTURED_OPTION_LIST")

        return regimen

    @classmethod
    def _lookup_atc(cls, drug_normalized: str) -> str | None:
        """Canonical-drug-name -> ATC code lookup. None when unmapped."""
        if not drug_normalized:
            return None
        for candidate in (drug_normalized, drug_normalized.lower()):
            code = DRUG_ATC.get(candidate)
            if code:
                return code
        return None

    @classmethod
    def _parse_components(
        cls, drug_raw: str, dose_raw: str, unit_raw: str
    ) -> list[DrugComponent]:
        """Split combination drugs into components with individual doses.

        M17: "+" AND "/" are both component separators, because Russian
        combination strengths are written both ways ("амоксициллин +
        клавулановая кислота" and "амоксициллин/клавулановая кислота").
        """
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
        """Parse '875/125', '500/50' or 'a/b/c' into [875.0, 125.0, ...].

        Generalised to an arbitrary number of components (M17): the old
        two-group regex silently dropped the 3rd+ component dose.
        """
        dose_raw = _coerce_str(dose_raw)
        if not dose_raw or not dose_raw.strip():
            return None
        parts = [p for p in cls._dose_ratio_sep_re.split(dose_raw.strip()) if p.strip()]
        if len(parts) < 2:
            return None
        values: list[float] = []
        for part in parts:
            value = DoseNormalizer.parse_number(part)
            if value is None:
                return None
            values.append(value)
        return values


class DoseNormalizer:
    """Extract numeric dose value and normalize unit.

    dose_value semantics (all three cases documented in models.py):
      * plain scalar "500"    -> 500.0   (verbatim)
      * range "1,0-2,0"       -> 1.0     (LOWER bound; upper in dose_max)
      * combination "875/125" -> 1000.0  (TOTAL strength, dose_component_count=2)
    """

    _dose_re: ClassVar[re.Pattern] = re.compile(
        r"(\d[\d\s,.]*)(?:\s*[-–—]\s*(\d[\d\s,.]*))?\s*"
    )
    _comma_re: ClassVar[re.Pattern] = re.compile(r",")
    _space_re: ClassVar[re.Pattern] = re.compile(r"\s+")
    # A dose token may only contain digits, spaces, commas and dots. This
    # whitelist is what rejects "nan" / "inf" / "1e9" before float() is ever
    # called (C1) — float("nan") is accepted by Python but poisons every
    # downstream comparison.
    _numeric_only_re: ClassVar[re.Pattern] = re.compile(r"\A\d[\d\s,.]*\Z")
    _component_sep_re: ClassVar[re.Pattern] = re.compile(r"\s*[/÷]\s*")
    _digits_re: ClassVar[re.Pattern] = re.compile(r"\d+")

    #: Confidence for a dose derived by SUMMING component strengths — it is a
    #: derived total, not a verbatim source value, so it must not claim 1.0.
    COMBINATION_CONFIDENCE: ClassVar[float] = 0.8

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
            regimen.dose_component_count = None
            return regimen

        # Combination strength ("875/125", "a/b/c") — checked BEFORE the
        # scalar path so the leading number is never mistaken for the whole
        # dose (C3).
        components = cls._parse_combination(dose_raw)
        if components is not None:
            total = math.fsum(components)
            regimen.dose_value = total
            regimen.dose_unit = cls._normalize_unit(unit_raw)
            regimen.dose_min = total
            regimen.dose_max = total
            # A multi-component strength is NOT a range, but it is also not a
            # verbatim scalar — the components live in drug_components.
            regimen.dose_is_range = False
            regimen.dose_range_raw = dose_raw
            regimen.dose_source_start = 0
            regimen.dose_source_end = len(dose_raw)
            regimen.dose_range_confidence = cls.COMBINATION_CONFIDENCE
            regimen.dose_component_count = len(components)
            if "DOSE_COMBINATION_STRENGTH" not in regimen.warnings:
                regimen.warnings.append("DOSE_COMBINATION_STRENGTH")
            return regimen

        # Try as single number first
        scalar = cls.parse_number(dose_raw)
        if scalar is not None:
            regimen.dose_value = scalar
            regimen.dose_unit = cls._normalize_unit(unit_raw)
            regimen.dose_min = regimen.dose_max = regimen.dose_value
            regimen.dose_is_range = False
            regimen.dose_range_raw = dose_raw
            regimen.dose_range_confidence = 1.0
            regimen.dose_component_count = None
            return regimen

        # Try to parse range: "1,0-2,0"
        match = cls._dose_re.match(dose_raw)
        # The range pattern is permissive by design (leading digits, optional
        # dash group). Require that it consumed the WHOLE token: otherwise
        # "1e9" would degrade to 1.0 mg and a long scientific-notation dose
        # would become a massive underdose. Fail closed instead.
        if match is not None and match.end() == len(dose_raw):
            val = cls.parse_number(match.group(1))
            if val is not None:
                regimen.dose_value = val  # legacy scalar remains the LOWER bound
                regimen.dose_unit = cls._normalize_unit(unit_raw)
                regimen.dose_min = val
                # Preserve group(2) upper bound (previously discarded).
                upper_raw = match.group(2)
                if upper_raw is None:
                    regimen.dose_max = val
                    regimen.dose_is_range = False
                    regimen.dose_range_raw = dose_raw
                    regimen.dose_range_confidence = 1.0
                    regimen.dose_source_start, regimen.dose_source_end = match.span()
                else:
                    upper = cls.parse_number(upper_raw)
                    if upper is None:
                        regimen.dose_max = val
                        regimen.dose_is_range = None  # RANGE_PARSE_AMBIGUOUS
                        regimen.dose_range_raw = dose_raw
                        regimen.dose_range_confidence = 0.0
                    elif upper > val:
                        regimen.dose_max = upper
                        regimen.dose_is_range = True
                        regimen.dose_range_raw = dose_raw
                        regimen.dose_range_confidence = 1.0
                        regimen.dose_source_start, regimen.dose_source_end = match.span()
                    else:
                        # Malformed / reversed range ("2,0-1,0"): keep the
                        # value recoverable but never claim a usable range
                        # (M4). dose_range_raw is now set on this branch too.
                        regimen.dose_max = val
                        regimen.dose_is_range = False
                        regimen.dose_range_raw = dose_raw
                        regimen.dose_range_confidence = 0.5  # malformed range
                        regimen.dose_source_start, regimen.dose_source_end = match.span()
                regimen.dose_component_count = None
                return regimen

        regimen.dose_value = None
        regimen.dose_unit = cls._normalize_unit(unit_raw) if unit_raw else None
        regimen.dose_is_range = None  # RANGE_PARSE_AMBIGUOUS
        regimen.dose_component_count = None
        return regimen

    @classmethod
    def _parse_combination(cls, dose_raw: str) -> list[float] | None:
        """Return the component doses of a "A/B(/C)" strength, or None.

        None means "not a combination strength" OR "not fully parseable" —
        both cases fall through to the scalar/range paths, which is the
        pre-existing behaviour.
        """
        if not cls._component_sep_re.search(dose_raw):
            return None
        parts = [p for p in cls._component_sep_re.split(dose_raw) if p.strip()]
        if len(parts) < 2:
            return None
        values: list[float] = []
        for part in parts:
            value = cls.parse_number(part)
            if value is None:
                return None
            values.append(value)
        return values

    @classmethod
    def parse_number(cls, raw: str) -> float | None:
        """Parse a single numeric dose token, or None.

        Handles the Russian comma in BOTH roles (C2):
          * thousands separator — exactly 3 digits followed by a non-digit or
            end of string: "1,000" -> 1000.0, "1,000,5" -> 1000.5
          * decimal separator — 1-2 digits followed by a non-digit or end:
            "1,5" -> 1.5, "0,5" -> 0.5
        Anything else (e.g. "1,0000", "nan", "inf", "-5") returns None so the
        caller can fail closed instead of guessing.
        """
        token = cls._space_re.sub("", _coerce_str(raw))
        if not token or not cls._numeric_only_re.match(token):
            return None
        if not cls._digits_re.search(token):
            return None
        out: list[str] = []
        index = 0
        while index < len(token):
            char = token[index]
            if char != ",":
                out.append(char)
                index += 1
                continue
            run = 0
            probe = index + 1
            while probe < len(token) and token[probe].isdigit():
                run += 1
                probe += 1
            boundary = probe >= len(token) or not token[probe].isdigit()
            if run == 3 and boundary:
                # thousands separator: drop the comma, keep the digits
                # ("1,000" -> 1000.0, "1,000,5" -> 1000.5)
                out.append(token[index + 1:probe])
            elif 1 <= run <= 2 and boundary:
                out.append(".")  # decimal separator -> keep the digits
                out.append(token[index + 1:probe])
            else:
                return None  # ambiguous grouping -> refuse to guess
            index = probe
        try:
            value = float("".join(out))
        except (ValueError, TypeError):
            return None
        if not math.isfinite(value):
            return None
        return value

    @classmethod
    def _normalize_unit(cls, unit: str) -> str | None:
        from medical_normalizer.dictionary import UnitNormalizer

        result = UnitNormalizer.normalize(unit)
        return result if result else None
