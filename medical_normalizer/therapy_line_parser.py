"""TherapyLineParser — map regimen_type to normalized therapy line."""

from __future__ import annotations

from medical_normalizer.models import NormalizedRegimen


class TherapyLineParser:
    """Map extraction's regimen_type to normalized therapy_line.

    Maps:
        first_line   -> first
        alternative  -> alternative
        reserve      -> reserve
        (other/none) -> unknown
    """

    _MAPPING: dict[str, str] = {
        "first_line": "first",
        "first-line": "first",
        "firstline": "first",
        "первая": "first",
        "первой линии": "first",
        "препарат первой линии": "first",
        "первый выбор": "first",
        "empiric": "first",
        "эмпирическая": "first",
        "эмпирическая терапия": "first",
        "эмпирический": "first",

        "alternative": "alternative",
        "альтернатива": "alternative",
        "альтернативный": "alternative",
        "альтернативной линии": "alternative",

        "reserve": "reserve",
        "резерв": "reserve",
        "резервный": "reserve",
        "резервный препарат": "reserve",
        "препарат резерва": "reserve",
        "второй линии": "reserve",
        "второй выбор": "reserve",

        "prophylaxis": "prophylaxis",
        "профилактика": "prophylaxis",
        "профилактическая": "prophylaxis",
        "профилактический": "prophylaxis",
    }

    @classmethod
    def parse(cls, regimen: NormalizedRegimen, raw: dict) -> NormalizedRegimen:
        rt = (raw.get("regimen_type", "") or "").strip().lower()
        if not rt:
            regimen.therapy_line = "unknown"
            return regimen

        # Direct mapping
        if rt in cls._MAPPING:
            regimen.therapy_line = cls._MAPPING[rt]
            return regimen

        # Fuzzy match: check if any key is substring of rt
        for key, value in cls._MAPPING.items():
            if key in rt or rt in key:
                regimen.therapy_line = value
                return regimen

        regimen.therapy_line = "unknown"
        return regimen
