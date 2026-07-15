"""PopulationParser — extract age group, pregnancy, lactation, renal status."""

from __future__ import annotations

import re
from typing import ClassVar

from medical_normalizer.models import NormalizedRegimen


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
        age_raw = (raw.get("age_group", "") or "").strip()
        quote_text = (raw.get("source_quote", "") or "").lower()
        combined = f"{age_raw} {quote_text}".lower()

        if not age_raw and not quote_text:
            regimen.adult = True
            regimen.child = False
            return regimen

        text = combined
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

        return regimen


class PregnancyParser:
    """Detect pregnancy and lactation from extraction fields and text."""

    _pregnancy_re: ClassVar[re.Pattern] = re.compile(
        r"беремен|pregnan|гестаци", re.IGNORECASE
    )
    _lactation_re: ClassVar[re.Pattern] = re.compile(
        r"лактаци|грудн\w* вскарм|breastfeed|lactat", re.IGNORECASE
    )

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        # Check extraction field first (may already be boolean)
        preg_field = raw.get("pregnancy", None)
        if isinstance(preg_field, bool):
            regimen.pregnancy = preg_field
            return regimen

        # Check age_group and source_quote for pregnancy mentions
        age_text = (raw.get("age_group", "") or "").lower()
        quote_text = (raw.get("source_quote", "") or "").lower()

        combined = f"{age_text} {quote_text}"

        if cls._pregnancy_re.search(combined):
            regimen.pregnancy = True
        elif "не рекоменд" in combined and "беремен" in combined:
            regimen.pregnancy = False
        else:
            regimen.pregnancy = None

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
        renal_field = raw.get("renal_adjustment", None)
        if isinstance(renal_field, bool):
            regimen.renal_adjustment = renal_field
            return regimen

        # Check source_quote and age_group for renal mentions
        quote_text = (raw.get("source_quote", "") or "").lower()
        age_text = (raw.get("age_group", "") or "").lower()
        combined = f"{age_text} {quote_text}"

        has_hemo = bool(cls._hemodialysis_re.search(combined))
        has_peritoneal = bool(cls._peritoneal_re.search(combined))
        has_renal = bool(cls._renal_re.search(combined))

        regimen.renal_adjustment = has_hemo or has_peritoneal or has_renal

        return regimen
