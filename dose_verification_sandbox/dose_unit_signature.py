"""RC-030 C6.8 — structured dose-unit model and compatibility logic.

Replaces the C6/C6.5 `_base_unit()` flat-string comparison (which only
compared the token before the first '/', silently discarding weight/time/
administration qualifiers -- see RC030_C67_UNIT_NORMALIZATION_AUDIT.md)
with an explicit `DoseUnitSignature` that keeps numerator, weight
denominator, time denominator, administration basis, and concentration
denominator as separate evidence dimensions, and a `compare_dose_units()`
function that never silently treats two different dose bases as
equivalent.

Read-only, pure text analysis. No PDF is opened, no database is written,
no calculation is activated, the Clinical Engine is never imported.
Every comparison result stays EXPERIMENTAL / NOT_OWNER_VERIFIED /
CALCULATION_BLOCKED -- this module only classifies evidence, it does not
approve anything.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from medical_normalizer.dictionary import UnitNormalizer

DOSE_UNIT_SIGNATURE_SCHEMA_VERSION = 1

# ── Administration basis vocabulary ────────────────────────────────────────
UNSPECIFIED = "UNSPECIFIED"
UNSPECIFIED_WEIGHT_BASED = "UNSPECIFIED_WEIGHT_BASED"
PER_DAY = "PER_DAY"
PER_DOSE = "PER_DOSE"
SINGLE_DOSE = "SINGLE_DOSE"
CONTINUOUS_RATE = "CONTINUOUS_RATE"
CONCENTRATION = "CONCENTRATION"
UNKNOWN_BASIS = "UNKNOWN"

ADMINISTRATION_BASES = frozenset({
    UNSPECIFIED, UNSPECIFIED_WEIGHT_BASED, PER_DAY, PER_DOSE, SINGLE_DOSE,
    CONTINUOUS_RATE, CONCENTRATION, UNKNOWN_BASIS,
})

# ── Parse status ────────────────────────────────────────────────────────────
PARSE_OK = "OK"
PARSE_UNKNOWN_NUMERATOR = "UNKNOWN_NUMERATOR"
PARSE_UNKNOWN_TOKEN = "UNKNOWN_TOKEN"
PARSE_MALFORMED = "MALFORMED"
PARSE_EMPTY = "EMPTY"

# ── Governed numerator units (mass/activity/volume/count) ─────────────────
# Sourced from the already-governed medical_normalizer.dictionary.UNIT_NORMALIZATION
# (mg, g, mcg, ml, IU, thousand_IU) plus mmol/ng/tablet/vial, which are named
# explicitly in the C6.8 spec's canonical component list but have zero
# observed occurrences in the 365-record corpus (see
# RC030_C68_UNIT_VOCABULARY_AUDIT.md) -- included as governed scaffolding,
# not fabricated synonyms, and covered by their own "unobserved" test note.
GOVERNED_NUMERATOR_UNITS = frozenset({
    "mg", "g", "mcg", "ng", "iu", "thousand_iu", "mmol", "ml", "tablet", "vial",
})

# Raw (pre-UnitNormalizer) numerator tokens recognized before normalization,
# for cases UnitNormalizer.normalize() doesn't cover (tablet/vial have no
# Cyrillic synonym governed today).
_RAW_NUMERATOR_ALIASES = {
    "таб": "tablet", "таблетка": "tablet", "таблетки": "tablet",
    "флакон": "vial", "фл": "vial",
}

_WEIGHT_TOKENS = {
    "kg": "kg", "кг": "kg",
    "m2": "m2", "m²": "m2", "м2": "m2", "м²": "m2",
}
_TIME_TOKENS = {
    "day": "day", "daily": "day", "сутки": "day", "сут": "day", "сут.": "day",
    "день": "day", "дня": "day", "d": "day",
    "hour": "hour", "hr": "hour", "ч": "hour", "час": "hour",
    "minute": "minute", "min": "minute", "мин": "minute",
}
_ADMINISTRATION_TOKENS = {
    "dose": PER_DOSE, "доза": PER_DOSE, "введение": PER_DOSE,
    "прием": PER_DOSE, "приём": PER_DOSE,
    "однократно": SINGLE_DOSE, "single": SINGLE_DOSE, "разовая": SINGLE_DOSE,
}
_CONCENTRATION_TOKENS = {"ml": "ml", "мл": "ml", "l": "l", "л": "l"}

_SUPERSCRIPT_2_RE = re.compile(r"[²]")  # ²
_WS_RE = re.compile(r"\s+")
_SLASH_SPACING_RE = re.compile(r"\s*/\s*")

# "X на кг (массы тела) (в сутки)" -> "X/кг(/сутки)" -- a spelled-out Russian
# per-kilogram(-per-day) construction, normalized to the compact slash form
# *before* tokenization, never inferred from clinical knowledge: this only
# fires on the literal "на кг" wording already present in the source text
# (Phase 3's "'per' constructions" requirement; matches the real defect in
# RC030_C68_UNIT_VOCABULARY_AUDIT.md).
_SPELLED_OUT_PER_KG_RE = re.compile(
    r"^(мг|г)\s+на\s+кг(?:\s+массы\s+тела)?(?:\s+в\s+сутки)?$"
)


def _normalize_spelled_out_constructions(text: str) -> str:
    m = _SPELLED_OUT_PER_KG_RE.match(text)
    if not m:
        return text
    numerator = m.group(1)
    has_per_day = "в сутки" in text
    return f"{numerator}/кг/сутки" if has_per_day else f"{numerator}/кг"


@dataclass(frozen=True)
class DoseUnitSignature:
    raw_unit: str
    normalized_unit: str
    numerator_unit: Optional[str]
    numerator_multiplier: float
    weight_denominator: Optional[str]
    time_denominator: Optional[str]
    administration_basis: str
    concentration_denominator: Optional[str]
    rate_basis: Optional[str]
    unknown_tokens: tuple[str, ...] = field(default_factory=tuple)
    parse_status: str = PARSE_OK
    schema_version: int = DOSE_UNIT_SIGNATURE_SCHEMA_VERSION


def _canonicalize_raw(raw: str) -> str:
    """Deterministic pre-tokenization canonicalization: NFC, lowercase,
    superscript-2 -> '2', collapsed whitespace, normalized slash spacing.
    Never discards a denominator -- only touches whitespace/case/script."""
    text = unicodedata.normalize("NFC", raw or "")
    text = _SUPERSCRIPT_2_RE.sub("2", text)
    text = text.strip().lower()
    text = _WS_RE.sub(" ", text)
    text = _normalize_spelled_out_constructions(text)
    text = _SLASH_SPACING_RE.sub("/", text)
    return text


def _classify_numerator(token: str) -> tuple[Optional[str], float, bool]:
    """Returns (numerator_unit, multiplier, recognized). multiplier is
    relative to the unit's own governed canonical form (informational only
    -- compatibility comparison never auto-converts across multipliers, to
    stay fail-closed per Phase 4)."""
    if token in _RAW_NUMERATOR_ALIASES:
        return _RAW_NUMERATOR_ALIASES[token], 1.0, True
    normalized = UnitNormalizer.normalize(token).lower()
    if normalized in GOVERNED_NUMERATOR_UNITS:
        return normalized, 1.0, True
    if normalized == "thousand_iu":
        return "thousand_iu", 1000.0, True
    return None, 1.0, False


def parse_dose_unit(raw: str) -> DoseUnitSignature:
    """Deterministic, evidence-preserving dose-unit parser. Never infers a
    missing basis from clinical knowledge -- an absent denominator stays
    absent (None), it is not guessed."""
    if raw is None or not raw.strip():
        return DoseUnitSignature(
            raw_unit=raw or "", normalized_unit="", numerator_unit=None,
            numerator_multiplier=1.0, weight_denominator=None, time_denominator=None,
            administration_basis=UNKNOWN_BASIS, concentration_denominator=None,
            rate_basis=None, unknown_tokens=(), parse_status=PARSE_EMPTY,
        )

    normalized = _canonicalize_raw(raw)

    # Reject compound multi-unit strings (e.g. "г; мг/кг") outright rather
    # than silently picking the first token -- a real observed case in the
    # structured corpus (see RC030_C68_UNIT_VOCABULARY_AUDIT.md).
    if ";" in normalized or "," in normalized:
        return DoseUnitSignature(
            raw_unit=raw, normalized_unit=normalized, numerator_unit=None,
            numerator_multiplier=1.0, weight_denominator=None, time_denominator=None,
            administration_basis=UNKNOWN_BASIS, concentration_denominator=None,
            rate_basis=None, unknown_tokens=(normalized,), parse_status=PARSE_MALFORMED,
        )

    parts = [p for p in normalized.split("/") if p != ""]
    if not parts or normalized.startswith("/") or normalized.endswith("/") or "//" in normalized:
        return DoseUnitSignature(
            raw_unit=raw, normalized_unit=normalized, numerator_unit=None,
            numerator_multiplier=1.0, weight_denominator=None, time_denominator=None,
            administration_basis=UNKNOWN_BASIS, concentration_denominator=None,
            rate_basis=None, unknown_tokens=tuple(parts), parse_status=PARSE_MALFORMED,
        )

    numerator_token, *denom_tokens = parts
    numerator_unit, multiplier, recognized = _classify_numerator(numerator_token)
    if not recognized:
        return DoseUnitSignature(
            raw_unit=raw, normalized_unit=normalized, numerator_unit=None,
            numerator_multiplier=1.0, weight_denominator=None, time_denominator=None,
            administration_basis=UNKNOWN_BASIS, concentration_denominator=None,
            rate_basis=None, unknown_tokens=(numerator_token,), parse_status=PARSE_UNKNOWN_NUMERATOR,
        )

    weight_denominator: Optional[str] = None
    time_denominator: Optional[str] = None
    concentration_denominator: Optional[str] = None
    admin_marker: Optional[str] = None
    unknown_tokens: list[str] = []

    for tok in denom_tokens:
        if tok in _WEIGHT_TOKENS:
            weight_denominator = _WEIGHT_TOKENS[tok]
        elif tok in _TIME_TOKENS:
            time_denominator = _TIME_TOKENS[tok]
        elif tok in _CONCENTRATION_TOKENS:
            concentration_denominator = _CONCENTRATION_TOKENS[tok]
        elif tok in _ADMINISTRATION_TOKENS:
            admin_marker = _ADMINISTRATION_TOKENS[tok]
        else:
            unknown_tokens.append(tok)

    if unknown_tokens:
        return DoseUnitSignature(
            raw_unit=raw, normalized_unit=normalized, numerator_unit=numerator_unit,
            numerator_multiplier=multiplier, weight_denominator=weight_denominator,
            time_denominator=time_denominator, administration_basis=UNKNOWN_BASIS,
            concentration_denominator=concentration_denominator, rate_basis=None,
            unknown_tokens=tuple(unknown_tokens), parse_status=PARSE_UNKNOWN_TOKEN,
        )

    # A concentration denominator (ml/l) combined with a weight/time/
    # administration denominator is an impossible token combination in this
    # model (a dose cannot simultaneously be "per ml" and "per kg") --
    # reject as malformed rather than silently picking one basis over the
    # other (found by the Phase 8 test matrix's "impossible token order" case).
    if concentration_denominator is not None and (
        weight_denominator is not None or time_denominator is not None or admin_marker is not None
    ):
        return DoseUnitSignature(
            raw_unit=raw, normalized_unit=normalized, numerator_unit=numerator_unit,
            numerator_multiplier=multiplier, weight_denominator=weight_denominator,
            time_denominator=time_denominator, administration_basis=UNKNOWN_BASIS,
            concentration_denominator=concentration_denominator, rate_basis=None,
            unknown_tokens=tuple(denom_tokens), parse_status=PARSE_UNKNOWN_TOKEN,
        )

    # ── administration basis derivation (Phase 1 worked examples) ─────────
    rate_basis: Optional[str] = None
    if concentration_denominator is not None and weight_denominator is None and time_denominator is None:
        basis = CONCENTRATION
    elif weight_denominator is not None and time_denominator in ("minute", "hour"):
        basis = CONTINUOUS_RATE
        rate_basis = time_denominator
    elif admin_marker == SINGLE_DOSE:
        basis = SINGLE_DOSE
    elif time_denominator == "day":
        basis = PER_DAY
    elif admin_marker == PER_DOSE:
        basis = PER_DOSE
    elif weight_denominator is not None:
        basis = UNSPECIFIED_WEIGHT_BASED
    else:
        basis = UNSPECIFIED

    return DoseUnitSignature(
        raw_unit=raw, normalized_unit=normalized, numerator_unit=numerator_unit,
        numerator_multiplier=multiplier, weight_denominator=weight_denominator,
        time_denominator=time_denominator, administration_basis=basis,
        concentration_denominator=concentration_denominator, rate_basis=rate_basis,
        unknown_tokens=(), parse_status=PARSE_OK,
    )


# ── Phase 4: compatibility outcomes ────────────────────────────────────────
EXACT_EQUIVALENT = "EXACT_EQUIVALENT"
COMPATIBLE_BASIS_UNSPECIFIED = "COMPATIBLE_BASIS_UNSPECIFIED"
INCOMPATIBLE_NUMERATOR = "INCOMPATIBLE_NUMERATOR"
INCOMPATIBLE_WEIGHT_BASIS = "INCOMPATIBLE_WEIGHT_BASIS"
INCOMPATIBLE_TIME_BASIS = "INCOMPATIBLE_TIME_BASIS"
INCOMPATIBLE_ADMINISTRATION_BASIS = "INCOMPATIBLE_ADMINISTRATION_BASIS"
CONCENTRATION_NOT_DOSE = "CONCENTRATION_NOT_DOSE"
RATE_NOT_DOSE = "RATE_NOT_DOSE"
UNKNOWN_UNIT = "UNKNOWN_UNIT"
MALFORMED_UNIT = "MALFORMED_UNIT"

_UNSPECIFIED_BASES = frozenset({UNSPECIFIED, UNSPECIFIED_WEIGHT_BASED})


def compare_dose_units(a: DoseUnitSignature, b: DoseUnitSignature) -> str:
    """Structured replacement for `_base_unit(a) == _base_unit(b)`. Never
    treats two different dose bases as equivalent merely because they share
    a leading numerator token -- weight/time/administration/concentration
    denominators are compared as separate, independent evidence dimensions,
    per Phase 4's explicit requirement."""
    if a.parse_status == PARSE_MALFORMED or b.parse_status == PARSE_MALFORMED:
        return MALFORMED_UNIT
    if a.parse_status in (PARSE_UNKNOWN_NUMERATOR, PARSE_UNKNOWN_TOKEN, PARSE_EMPTY) or \
       b.parse_status in (PARSE_UNKNOWN_NUMERATOR, PARSE_UNKNOWN_TOKEN, PARSE_EMPTY):
        return UNKNOWN_UNIT

    if a.numerator_unit != b.numerator_unit:
        return INCOMPATIBLE_NUMERATOR

    a_is_conc = a.administration_basis == CONCENTRATION
    b_is_conc = b.administration_basis == CONCENTRATION
    if a_is_conc != b_is_conc:
        return CONCENTRATION_NOT_DOSE

    a_is_rate = a.administration_basis == CONTINUOUS_RATE
    b_is_rate = b.administration_basis == CONTINUOUS_RATE
    if a_is_rate != b_is_rate:
        return RATE_NOT_DOSE

    if a.weight_denominator != b.weight_denominator:
        return INCOMPATIBLE_WEIGHT_BASIS

    both_unspecified = a.administration_basis in _UNSPECIFIED_BASES and b.administration_basis in _UNSPECIFIED_BASES
    either_unspecified = a.administration_basis in _UNSPECIFIED_BASES or b.administration_basis in _UNSPECIFIED_BASES

    if not both_unspecified and either_unspecified:
        # one side states an explicit basis (PER_DAY/PER_DOSE/SINGLE_DOSE/
        # CONTINUOUS_RATE/CONCENTRATION), the other doesn't -- compatible,
        # not exact, per Phase 4: COMPATIBLE_BASIS_UNSPECIFIED must not
        # automatically yield SAFE_EXACT_LINK.
        return COMPATIBLE_BASIS_UNSPECIFIED

    if both_unspecified:
        return EXACT_EQUIVALENT if a.administration_basis == b.administration_basis else COMPATIBLE_BASIS_UNSPECIFIED

    # both explicit from here on
    if a.time_denominator != b.time_denominator:
        return INCOMPATIBLE_TIME_BASIS
    if a.administration_basis != b.administration_basis:
        return INCOMPATIBLE_ADMINISTRATION_BASIS
    if a.concentration_denominator != b.concentration_denominator:
        return INCOMPATIBLE_ADMINISTRATION_BASIS

    return EXACT_EQUIVALENT
