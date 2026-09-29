"""TherapyLineParser — map regimen_type to normalized therapy line."""

from __future__ import annotations

from typing import ClassVar

from medical_normalizer.models import MISSING_FIELD_INPUT, NormalizedRegimen


class TherapyLineParser:
    """Map extraction's regimen_type to normalized therapy_line.

    Maps:
        first_line   -> first
        alternative  -> alternative
        reserve      -> reserve
        prophylaxis  -> prophylaxis
        (other/none) -> unknown

    Fuzzy matching (M12): only for inputs of at least MIN_FUZZY_LENGTH
    characters, and the LONGEST matching key wins. The previous bidirectional
    ``key in rt or rt in key`` loop let a 1-character input such as "а" match
    "первая" and returned whichever key happened to come first in dict
    insertion order.
    """

    #: Below this length an input is far too short to be matched
    #: fuzzily — a 1-3 character fragment matching inside an unrelated word
    #: is worse than admitting "unknown".
    MIN_FUZZY_LENGTH: ClassVar[int] = 4

    _MAPPING: dict[str, str] = {
        "first_line": "first",
        "first-line": "first",
        "firstline": "first",
        "первая": "first",
        "первая линия": "first",
        "первой линии": "first",
        "первой линии терапии": "first",
        "препарат первой линии": "first",
        "первый выбор": "first",
        "empiric": "first",
        "эмпирическая": "first",
        "эмпирическая терапия": "first",
        "эмпирический": "first",

        "alternative": "alternative",
        "альтернатива": "alternative",
        "альтернативный": "alternative",
        "альтернативная": "alternative",
        "альтернативной линии": "alternative",

        "reserve": "reserve",
        "резерв": "reserve",
        "резервный": "reserve",
        "резервный препарат": "reserve",
        "препарат резерва": "reserve",
        "второй линии": "reserve",
        "вторая линия": "reserve",
        "второй выбор": "reserve",

        "prophylaxis": "prophylaxis",
        "профилактика": "prophylaxis",
        "профилактическая": "prophylaxis",
        "профилактический": "prophylaxis",
    }

    #: Keys sorted longest-first, computed once (M12: longest match wins).
    _MAPPING_LONGEST_FIRST: ClassVar[tuple[tuple[str, str], ...]] = tuple(
        sorted(_MAPPING.items(), key=lambda kv: len(kv[0]), reverse=True)
    )

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        rt_value = raw.get("regimen_type") if isinstance(raw, dict) else None
        # H2: a non-string regimen_type used to raise AttributeError from
        # .strip(). Recorded as a ParserError and the pipeline continues.
        # Absent / null stays "unknown" — a modelled state.
        if rt_value is not None and not isinstance(rt_value, str):
            regimen.therapy_line = "unknown"
            if not regimen.warnings:
                regimen.warnings = []
            marker = f"{MISSING_FIELD_INPUT}:regimen_type"
            if marker not in regimen.warnings:
                regimen.warnings.append(marker)
            return regimen

        rt = rt_value.strip().lower() if rt_value else ""

        # Direct mapping
        if rt in cls._MAPPING:
            regimen.therapy_line = cls._MAPPING[rt]
            return regimen

        # Fuzzy match: too-short inputs are not matchable (M12)
        if len(rt) >= cls.MIN_FUZZY_LENGTH:
            for key, value in cls._MAPPING_LONGEST_FIRST:
                if key in rt or rt in key:
                    regimen.therapy_line = value
                    return regimen

        regimen.therapy_line = "unknown"
        return regimen
