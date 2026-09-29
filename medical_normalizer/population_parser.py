"""PopulationParser — extract age group, pregnancy, lactation, renal status."""

from __future__ import annotations

import re
from typing import ClassVar

from medical_normalizer.models import MISSING_FIELD_INPUT, NormalizedRegimen


def _coerce_text(val) -> tuple[str, bool]:
    """Coerce a raw text value to a lowered, stripped string.

    Returns (text, ok). ok is False when the field is absent, empty or not a
    string (H2: int / None / list inputs must not crash the parser).
    """
    if val is None or not isinstance(val, str):
        return "", False
    text = val.strip().lower()
    return text, bool(text)


def _is_malformed(val) -> bool:
    """True when a field was supplied but is not usable text (H2).

    A genuinely ABSENT field is a modelled state (adult=True default,
    renal_adjustment=False, ...), not an input error. A field that arrives as
    an int / list / dict is a real extraction defect and is recorded.
    """
    return val is not None and not isinstance(val, str)


def _record_missing_input(regimen: NormalizedRegimen, field_name: str) -> None:
    if not regimen.warnings:
        regimen.warnings = []
    marker = f"{MISSING_FIELD_INPUT}:{field_name}"
    if marker not in regimen.warnings:
        regimen.warnings.append(marker)


class AgeParser:
    """Parse age_group field to set adult/child booleans."""

    _child_re: ClassVar[re.Pattern] = re.compile(
        r"дет|ребенок|ребенк|педиатр|младен|детск|child|children|pediatric|infant", re.IGNORECASE
    )
    _newborn_re: ClassVar[re.Pattern] = re.compile(
        r"новорожд|неонатал|neonatal|newborn", re.IGNORECASE
    )
    _premature_re: ClassVar[re.Pattern] = re.compile(
        r"недонош|преждевремен", re.IGNORECASE
    )
    _elderly_re: ClassVar[re.Pattern] = re.compile(
        r"пожил|старческ|гериатр|старческого возраста", re.IGNORECASE
    )
    _adult_re: ClassVar[re.Pattern] = re.compile(
        r"взросл|adult", re.IGNORECASE
    )

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        age_value = raw.get("age_group") if isinstance(raw, dict) else None
        age_raw, age_ok = _coerce_text(age_value)
        quote_raw, _ = _coerce_text(
            raw.get("source_quote") if isinstance(raw, dict) else None
        )

        if not age_raw and not quote_raw:
            regimen.adult = True
            regimen.child = False
            # M6: adult=True is only a default, not evidence. Keep
            # population_stated False so confidence does not score an
            # unstated population as inferred.
            regimen.population_stated = False
            if _is_malformed(age_value) or _is_malformed(
                raw.get("source_quote") if isinstance(raw, dict) else None
            ):
                _record_missing_input(regimen, "age_group")
            return regimen

        text = f"{age_raw} {quote_raw}".lower()

        is_child = bool(cls._child_re.search(text))
        is_newborn = bool(cls._newborn_re.search(text))
        is_premature = bool(cls._premature_re.search(text))
        is_elderly = bool(cls._elderly_re.search(text))
        is_adult = bool(cls._adult_re.search(text))

        # Evidence from quote (e.g. "с 3 месяцев") takes precedence for peds without explicit adult-only
        peds_evidence = is_child or is_newborn or is_premature
        adult_evidence = is_adult or is_elderly

        if peds_evidence and not adult_evidence:
            regimen.child = True
            regimen.adult = False
        elif is_newborn or is_premature:
            regimen.child = True
            regimen.adult = False
        elif is_child:
            regimen.child = True
            regimen.adult = False
        elif is_elderly:
            regimen.adult = True
            regimen.child = False
        elif is_adult:
            regimen.adult = True
            regimen.child = False
        else:
            # Only default to adult if no evidence at all for child/peds
            regimen.adult = True
            regimen.child = False

        # M6: population_stated is True only when some age/population keyword
        # was actually found in age_group or source_quote.
        regimen.population_stated = bool(
            peds_evidence or adult_evidence
        )
        if _is_malformed(age_value):
            _record_missing_input(regimen, "age_group")
        return regimen


class PregnancyParser:
    """Detect pregnancy and lactation from extraction fields and text.

    Semantics of ``regimen.pregnancy``:
        True  — the regimen is stated as applicable to pregnant patients
        False — pregnancy is mentioned AND the text contraindicates /
                 does not recommend use in pregnancy
        None  — no information
    """

    _pregnancy_re: ClassVar[re.Pattern] = re.compile(
        r"беремен|pregnan|гестаци", re.IGNORECASE
    )
    _lactation_re: ClassVar[re.Pattern] = re.compile(
        r"лактаци|грудн\w* вскарм|breastfeed|lactat", re.IGNORECASE
    )
    # M13: a contraindication / non-recommendation in pregnancy. Checked
    # BEFORE the plain "беремен" match, otherwise "при беременности применение
    # не рекомендовано" was recorded as pregnancy=True — a contraindication
    # recorded as applicability.
    _contraindication_re: ClassVar[re.Pattern] = re.compile(
        r"не\s+рекоменд|противопоказ|не\s+допущ|не\s+примен|запрещ",
        re.IGNORECASE,
    )
    _applicable_re: ClassVar[re.Pattern] = re.compile(
        r"разреш|допустим|применени\w*\s+допущ|можно\s+примен",
        re.IGNORECASE,
    )

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        # Check extraction field first (may already be boolean)
        preg_field = raw.get("pregnancy", None) if isinstance(raw, dict) else None
        if isinstance(preg_field, bool):
            regimen.pregnancy = preg_field
            return regimen

        # Check age_group and source_quote for pregnancy mentions
        age_text, _ = _coerce_text(
            raw.get("age_group") if isinstance(raw, dict) else None
        )
        quote_text, _ = _coerce_text(
            raw.get("source_quote") if isinstance(raw, dict) else None
        )

        combined = f"{age_text} {quote_text}"

        if not combined.strip():
            regimen.pregnancy = None
            if _is_malformed(preg_field) or _is_malformed(
                raw.get("age_group") if isinstance(raw, dict) else None
            ) or _is_malformed(
                raw.get("source_quote") if isinstance(raw, dict) else None
            ):
                _record_missing_input(regimen, "pregnancy")
            return regimen

        if not cls._pregnancy_re.search(combined):
            regimen.pregnancy = None
            return regimen

        # M13: negation wins over plain mention.
        if cls._contraindication_re.search(combined):
            regimen.pregnancy = False
            return regimen
        if cls._applicable_re.search(combined) and not cls._contraindication_re.search(combined):
            regimen.pregnancy = True
            return regimen

        regimen.pregnancy = True
        return regimen


class GFRParser:
    """Detect renal adjustment, dialysis from extraction fields and text."""

    _renal_re: ClassVar[re.Pattern] = re.compile(
        r"почечн|ренальн|crcl|кк|клиренс|gfr|скорость клубочков|creatinine",
        re.IGNORECASE,
    )
    _hemodialysis_re: ClassVar[re.Pattern] = re.compile(
        r"гемодиализ|hemodialysis|гд\b", re.IGNORECASE
    )
    _peritoneal_re: ClassVar[re.Pattern] = re.compile(
        r"перитонеальн.*диализ|peritoneal.*dialysis|пд\b", re.IGNORECASE
    )

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        # Check extraction field first
        renal_field = raw.get("renal_adjustment", None) if isinstance(raw, dict) else None
        if isinstance(renal_field, bool):
            regimen.renal_adjustment = renal_field
            return regimen

        # Check source_quote and age_group for renal mentions
        quote_text, _ = _coerce_text(
            raw.get("source_quote") if isinstance(raw, dict) else None
        )
        age_text, _ = _coerce_text(
            raw.get("age_group") if isinstance(raw, dict) else None
        )
        combined = f"{age_text} {quote_text}"

        if not combined.strip():
            regimen.renal_adjustment = False
            if _is_malformed(renal_field) or _is_malformed(
                raw.get("age_group") if isinstance(raw, dict) else None
            ) or _is_malformed(
                raw.get("source_quote") if isinstance(raw, dict) else None
            ):
                _record_missing_input(regimen, "renal_adjustment")
            return regimen

        has_hemo = bool(cls._hemodialysis_re.search(combined))
        has_peritoneal = bool(cls._peritoneal_re.search(combined))
        has_renal = bool(cls._renal_re.search(combined))

        regimen.renal_adjustment = has_hemo or has_peritoneal or has_renal

        return regimen
