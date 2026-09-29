"""Map DOSA klinrec extraction to db/diseases records (source-anchored only).

This is a *source prover* mapper. It turns source-anchored DOSA regimen data
(raw LLM extraction with source_quote / page / pdf_sha256) into calculator
disease records (db/diseases/*.json shape), WITHOUT enabling calculation.
Any new disease is left calculation_blocked=True by the fail-closed source
gate at build time, and every drug must resolve to an existing drug_reference
key (else validate_db.js exits non-zero). Drugs that cannot be resolved are
skipped, never registered blindly. The clinical gate (P5.6/P6) remains with
the owner/physician.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

from src.pipeline import config as pipeline_config

# ---- drug resolution ------------------------------------------------------

# Normalized drug name -> drug_reference key. ATC_MAP maps Russian name ->
# (canonical_english, ATC). We invert it and map canonical -> drug_ref key so
# that the raw drug name (after stripping markers) resolves to one of the 40
# registered drug_reference keys in db/index.json. Drugs NOT resolvable here
# are SKIPPED (never registered, validate_db.js would fail otherwise).

# Additional name aliases -> drug_ref key (for names not covered by ATC_MAP's
# canonical english). Keys are normalized (lower, no markers/brackets).
_DRUG_REF_ALIAS: dict[str, str] = {
    "амоксициллин/клавуланат": "amoxiclav",
    "амоксициллина клавуланат": "amoxiclav",
    "бензилпенициллин": "benzylpenicillin_na",
    "пиперациллин/тазобактам": "piperacillin_tazobactam",
    "пиперациллин+тазобактам": "piperacillin_tazobactam",
    "ко-тримоксазол": "cotrimoxazole",
    "ко тримоксазол": "cotrimoxazole",
    "сульфаметоксазол/триметоприм": "cotrimoxazole",
    "триметоприм/сульфаметоксазол": "cotrimoxazole",
}

# Whole-class / group names that are NOT a single drug -> must be skipped.
_GROUP_NAMES = frozenset(
    [
        "фторхинолоны",
        "макролиды",
        "цефалоспорины",
        "бета-лактамы",
        "другие бета-лактамные",
        "аминогликозиды",
        "нитроимидазолы",
        "тетрациклины",
        "пенициллины",
        "карбапенемы",
        "гликопептиды",
    ]
)

# Composite combos (cleaned, lower) whose BOTH components must be present ->
# drug_ref. E.g. 'амоксициллин+клавулановая кислота' -> amoxiclav.
_COMPOSITE: list[tuple[tuple[str, ...], str]] = [
    (("амоксициллин", "клавулан"), "amoxiclav"),
    (("пиперациллин", "тазобактам"), "piperacillin_tazobactam"),
    (("ампициллин", "сульбактам"), "ampicillin"),
    (("триметоприм", "сульфаметоксазол"), "cotrimoxazole"),
    (("сульфаметоксазол", "триметоприм"), "cotrimoxazole"),
]


def _clean_drug_name(raw: Any) -> str:
    """Strip Voedarev '**', prefixed '#', brackets, whitespace from a drug name."""
    if not raw:
        return ""
    text = str(raw).strip()
    text = re.sub(r"[*#]+", " ", text)
    text = re.sub(r"\s*\+\s*", "+", text)
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"[\[\]\(\)]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def resolve_drug_ref(raw_name: Any) -> str | None:
    """Resolve a raw antibiotic name to a drug_reference key, or None if unknown.

    Drugs that are whole-class names, or that resolve to nothing in the
    registered drug_reference namespace, return None so the caller SKIPS the
    regimen (never registers an unknown drug).
    """
    norm = _clean_drug_name(raw_name)
    if not norm:
        return None

    if norm in _GROUP_NAMES:
        return None

    # Direct ATC_MAP Russian-key match.
    if norm in pipeline_config.ATC_MAP:
        canonical, _atc = pipeline_config.ATC_MAP[norm]
        return _canonical_to_ref(canonical)

    # Alias map.
    if norm in _DRUG_REF_ALIAS:
        return _DRUG_REF_ALIAS[norm]

    # De-inflect common Russian case endings (genitive/instrumental) to recover
    # the nominative stem, then retry the ATC_MAP match. Only keep stems >= 4.
    for stem in _de_inflect(norm):
        if stem in pipeline_config.ATC_MAP:
            canonical, _atc = pipeline_config.ATC_MAP[stem]
            return _canonical_to_ref(canonical)
        if stem in _DRUG_REF_ALIAS:
            return _DRUG_REF_ALIAS[stem]

    # Composite combos: if the name carries two matching component stems treat
    # the whole string as that combination (e.g. амоксициллин+клавулановая).
    for tokens, ref in _COMPOSITE:
        if all(tok in norm for tok in tokens):
            return ref

    return None


_RU_ENDINGS = ("ами", "ями", "ая", "яя", "ем", "ом", "ой", "ей", "ые", "ие", "у", "а", "я", "ы", "и", "е", "о")
_DE_INFLECT_ROUNDS = 3


def _de_inflect(text: str) -> list[str]:
    """Yield shorter nominative candidates of a Russian drug name.

    Non-destructive: always returns a list that starts with the input unchanged.
    Iteratively re-applies the suffix rule (up to ``_DE_INFLECT_ROUNDS`` times) so
    a two-ending form such as "метронидазола" -> "метронидазол" resolves in one call
    instead of requiring a caller retry.  Previously ONE ending was stripped and the
    candidate was never retried, so "<stem>а<ending>" forms silently failed to resolve.
    """
    candidates: list[str] = []
    current = text
    for _ in range(_DE_INFLECT_ROUNDS):
        candidates.append(current)
        nxt = ""
        for end in _RU_ENDINGS:
            if current.endswith(end) and len(current) - len(end) >= 4:
                nxt = current[: -len(end)]
                break
        if not nxt or nxt in candidates:
            break
        current = nxt
    return candidates


def _canonical_to_ref(canonical: str) -> str | None:
    m = {
        "amoxicillin": "amoxicillin",
        "amoxicillin_clavulanate": "amoxiclav",
        "ampicillin": "ampicillin",
        "oxacillin": "oxacillin",
        "benzylpenicillin": "benzylpenicillin_na",
        "cefazolin": "cefazolin",
        "cefalexin": "cephalexin",
        "cefuroxime": "cefuroxime",
        "cefixime": "cefixime",
        "ceftriaxone": "ceftriaxone",
        "cefotaxime": "cefotaxime",
        "ceftazidime": "ceftazidime",
        "cefepime": "cefepime",
        "meropenem": "meropenem",
        "piperacillin_tazobactam": "piperacillin_tazobactam",
        "azithromycin": "azithromycin",
        "clarithromycin": "clarithromycin",
        "erythromycin": "erythromycin",
        "josamycin": "josamycin",
        "doxycycline": "doxycycline",
        "levofloxacin": "levofloxacin",
        "ciprofloxacin": "ciprofloxacin",
        "moxifloxacin": "moxifloxacin",
        "amikacin": "amikacin",
        "gentamicin": "gentamicin",
        "linezolid": "linezolid",
        "vancomycin": "vancomycin",
        "clindamycin": "clindamycin",
        "metronidazole": "metronidazole",
        "rifampicin": "rifampicin",
        "cotrimoxazole": "cotrimoxazole",
        "nitrofurantoin": "nitrofurantoin",
        "fosfomycin": "fosfomycin",
        "tetracycline": "tetracycline",
        "ofloxacin": "ofloxacin",
        "tobramycin": "tobramycin",
        "netilmicin": "netilmicin",
        "tinidazole": "tinidazole",
        "rifaximin": "rifaximin",
        "furazidin": "furazidin",
    }
    return m.get(canonical)


# ---- dose semantics ------------------------------------------------------
#
# A guideline dose string is written per-ADMINISTRATION unless the denominator
# explicitly says "per day".  The single most safety-critical defect this module
# used to have was writing a per-dose amount into a field whose name says DAY,
# so a calculator reading `dose_mg_day_fixed` showed 1 g/day for a 1 g TID
# regimen -- a 3x underdose.  The contract is now:
#
#   dose_mg_day_fixed      mg administered PER DAY  (only when the source says so)
#   dose_mg_day_fixed_max  upper bound of the same per-day amount / range
#   single_dose_mg         mg administered PER DOSE (guideline default)
#   single_dose_mg_max     upper bound of the same per-dose amount / range
#   dose_mg_kg_day         mg/kg administered PER DAY (only when the source says so)
#   dose_mg_kg_day_max     upper bound of the same per-day weight amount
#   dose_mg_kg_per_dose    mg/kg administered PER DOSE (never a *_day field)
#   dose_mg_kg_per_dose_max
#   max_daily_mg           the TRUE daily ceiling: (max per-day | max per-dose) * freq
#   dose_basis             "per_day" | "per_dose" -- what the source actually said
#   dose_escalated         True when an "затем/после" escalation was collapsed to its MAX
#   dose_range_wording     the verbatim source wording, so a range is never silent
#
# A `_day` field is written ONLY for a genuinely daily value.  A per-dose value
# never lands in a `_day` field.

_MG_KG_EXPR = re.compile(r"(?:мг|mg|mcg|мкг)\s*/\s*(?:кг|kg)", re.IGNORECASE)
_PER_DAY_EXPR = re.compile(
    r"(?:\s*[/в]\s*(?:сут(?:к(?:и|и))?|день|дн\b)|per[\s_-]*day|/\s*day|\bday\b)",
    re.IGNORECASE,
)
_PER_DOSE_EXPR = re.compile(
    r"(?:введени\w*|инфуз\w*|раз\w*|при[её]м\w*|однократно|per[\s_-]*dose|/\s*dose|\bdose\b|infil)",
    re.IGNORECASE,
)
_ESCALATION_EXPR = re.compile(
    r"(?:затем|после|далее|переход|при\s+(?:недостаточн|отсутств\w*)\w*|повыси\w*|увелич\w*|довест\w*)",
    re.IGNORECASE,
)
# A dose token: an unsigned number (a leading '-' is a RANGE dash, not a sign) with
# an optional mass/weight unit attached.
_DOSE_TOKEN = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*"
    r"(мг\s*/\s*кг|mg\s*/\s*kg|мкг\s*/\s*кг|мг|mg|мкг|mcg|г|g|мл|ме|м\.?е\.?)?",
    re.IGNORECASE,
)
_BARE_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

_FIXED_UNIT_SCALE = {
    "мг": 1.0, "mg": 1.0, "мкг": 0.001, "mcg": 0.001,
    "г": 1000.0, "g": 1000.0,
}


def _to_float(text: str) -> float:
    return float(text.replace(",", ".").replace(" ", ""))


def _canon_unit(unit: str | None) -> str:
    return re.sub(r"\s+", "", str(unit or "")).lower().rstrip(".")


def _fixed_scale(unit: str) -> float | None:
    """Return the mg-per-unit scale for a mass unit, or None if not a mass."""
    return _FIXED_UNIT_SCALE.get(_canon_unit(unit))


def _is_weight_unit(unit: str) -> bool:
    return bool(_MG_KG_EXPR.search(unit or ""))


def _dose_basis_of(unit: str) -> str:
    """Classify the denominator of a dose unit/expression.

    Returns "per_day", "per_dose" or "unspecified".  "unspecified" is resolved by
    the caller per the Russian clinical-guideline convention (per administration),
    which is the safe direction: the value is then multiplied by the frequency by
    the consumer instead of being silently read as a daily total.
    """
    if not unit:
        return "unspecified"
    per_day = bool(_PER_DAY_EXPR.search(unit))
    per_dose = bool(_PER_DOSE_EXPR.search(unit))
    if per_day and not per_dose:
        return "per_day"
    if per_dose and not per_day:
        return "per_dose"
    if per_day and per_dose:
        # "мг/кг/введение в сутки" -- a single dose whose ceiling is a daily one;
        # the per-dose form is the amount actually administered, so keep per_dose.
        return "per_dose"
    return "unspecified"


def _split_escalation(text: str) -> tuple[str, bool]:
    """Split text at the first escalation marker.

    Returns (head, escalated).  A guideline that escalates ("500 мг 3 раза в день,
    затем 1 г") publishes a MAXIMUM, so the caller must use the larger arm and
    record that it did so.
    """
    match = _ESCALATION_EXPR.search(text)
    if not match:
        return text, False
    return text[: match.start()], True


def _dose_arms(text: str) -> list[tuple[float, str | None, bool]]:
    """Extract (value, unit, escalated) arms from a free-text dose expression.

    A dose cell may carry a range ("500-1000 мг"), a bare leading number
    ("0,5-1 г") or an escalation ladder ("500 мг, затем 1 г").  Ranges become
    several arms with the SAME basis; an escalation marks every arm after the
    marker so the caller can keep the MAX.  A token without its own unit inherits
    the last unit seen, so "0,5-1 г" is a 500-1000 mg range, not a single 1000 mg.
    """
    raw: list[tuple[float, str | None, bool]] = []
    seen_escalation = False
    last_unit: str | None = None
    for match in _DOSE_TOKEN.finditer(text):
        if match.start() > 0 and _ESCALATION_EXPR.search(text[: match.start()]):
            seen_escalation = True
        value = _to_float(match.group(1))
        unit = match.group(2)
        if unit:
            last_unit = unit
        raw.append((value, unit, seen_escalation))
    # A number without its own unit inherits the nearest one: the unit that came
    # before it ("500 мг - 1000") or, for a leading bare number, the one that
    # follows ("0,5-1 г").
    arms: list[tuple[float, str | None, bool]] = []
    for index, (value, unit, esc) in enumerate(raw):
        if not unit:
            unit = last_unit
        if not unit:
            for _v, later_unit, _e in raw[index + 1:]:
                if later_unit:
                    unit = later_unit
                    break
        arms.append((value, unit, esc))
    return arms


def _effective_basis(dose: str, unit: str) -> str:
    """Basis of the most specific denominator available.

    A bare unit column ("г") carries no denominator, but a dose cell written as
    "1 г/сут" does.  The more specific expression wins.
    """
    text_basis = _dose_basis_of(dose)
    if text_basis != "unspecified":
        return text_basis
    return _dose_basis_of(unit)


def _normalize_dose(raw_dose: Any, raw_unit: Any, freq: int) -> dict[str, Any]:
    """Convert a raw dose/unit/freq into basis-explicit regimen dose fields.

    Returns a partial regimen-covering dict, possibly empty if unparseable.  An
    empty dict is a FAIL-CLOSED signal: the caller must not emit a regimen that
    carries no dose at all (see ``map_guideline``).

    The unit/expression decides the BASIS, not the numeric field it used to be
    crammed into:

      "1 г"              3/day  -> single_dose_mg=1000, max_daily_mg=3000
      "7 мг/кг/введение" 3/day  -> dose_mg_kg_per_dose=7  (NOT dose_mg_kg_day)
      "30 мг/кг/сут"     3/day  -> dose_mg_kg_day=30,      max_daily_mg_per_kg=90
      "30 мг/кг/день"    2/day  -> dose_mg_kg_day=30,      max_daily_mg_per_kg=60
      "500-1000 мг"      3/day  -> single_dose_mg=500, single_dose_mg_max=1000,
                                     max_daily_mg=3000 (the true ceiling, not 1500)
      "500 мг, затем 1 г"      -> single_dose_mg=1000, dose_escalated=True
    """
    out: dict[str, Any] = {}
    dose = str(raw_dose or "").strip()
    unit = str(raw_unit or "").strip()
    if not dose:
        return out

    _head, escalated = _split_escalation(dose)
    weight_basis = _effective_basis(dose, unit) if _is_weight_unit(unit) else None
    if weight_basis is None and _is_weight_unit(dose):
        weight_basis = _dose_basis_of(dose)

    if weight_basis is not None:
        return _normalize_weight_dose(dose, unit, freq, escalated)

    # Fixed mass dose.  The unit COLUMN is authoritative when it names a mass;
    # otherwise the unit has to be carried by the dose text itself.
    column_scale = _fixed_scale(unit)
    if column_scale is None and unit:
        # мл, МЕ, таблетки, ... — not a mass this schema can represent.
        return out
    cell_basis = _effective_basis(dose, unit)
    arms = _dose_arms(dose)
    scaled: list[tuple[float, str, bool]] = []
    for value, arm_unit, arm_escalated in arms:
        scale = column_scale if column_scale is not None else _fixed_scale(arm_unit or "")
        if scale is None:
            continue
        if _is_weight_unit(arm_unit or ""):
            # A mg/kg token inside a fixed-mass cell: handled by the weight branch.
            return _normalize_weight_dose(dose, unit, freq, escalated)
        basis = _effective_basis(arm_unit or "", unit) if arm_unit else cell_basis
        if basis == "unspecified":
            # The arm's own unit carries no denominator ("г"); the cell expression
            # ("1 г/сут") is the more specific statement.
            basis = cell_basis
        scaled.append((value * scale, basis, arm_escalated or escalated))
    if not scaled:
        return out

    # RANGE: both ends of the same interval share a basis, so keep the min as the
    # base value and the max as the ceiling.  The range is never silently dropped.
    per_day = any(basis == "per_day" for _v, basis, _e in scaled)
    values = [v for v, _b, _e in scaled]
    low, high = min(values), max(values)
    prefix = "dose_mg_day_fixed" if per_day else "single_dose_mg"
    out[prefix] = low
    if high > low:
        out[f"{prefix}_max"] = high
    out["dose_basis"] = "per_day" if per_day else "per_dose"
    if escalated or any(e for _v, _b, e in scaled):
        out["dose_escalated"] = True
    if high > low:
        out["dose_range_wording"] = dose
    if freq:
        out["max_daily_mg"] = high * freq
    return out


def _normalize_weight_dose(dose: str, unit: str, freq: int, escalated: bool) -> dict[str, Any]:
    """Normalize a mg/kg dose into the weight-specific, basis-explicit fields."""
    out: dict[str, Any] = {}
    basis = _effective_basis(dose, unit)
    per_day = basis == "per_day"
    values = [v for v, arm_unit, _e in _dose_arms(dose) if _is_weight_unit(arm_unit or unit or dose)]
    if not values:
        values = [_to_float(m) for m in _BARE_NUMBER.findall(dose)]
    if not values:
        return out
    low, high = min(values), max(values)
    prefix = "dose_mg_kg_day" if per_day else "dose_mg_kg_per_dose"
    out[prefix] = low
    if high > low:
        out[f"{prefix}_max"] = high
    out["dose_basis"] = "per_day" if per_day else "per_dose"
    if escalated:
        out["dose_escalated"] = True
    if high > low:
        out["dose_range_wording"] = dose
    if freq and per_day:
        out["max_daily_mg_per_kg"] = high * freq
    return out


def _first_number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def _number_range(text: str) -> tuple[float, float] | None:
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None


def _first_number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def _number_range(text: str) -> tuple[float, float] | None:
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None


def _route_to_schema(raw_route: Any) -> list[str] | None:
    r = str(raw_route or "").lower()
    if "в/в" in r or "вв" in r or "инфуз" in r or "внутрив" in r:
        return ["iv"]
    if "в/м" in r or "вм" in r or "внутримыш" in r or "внутрь или в/в" in r or "в/м или в/в" in r:
        return ["im"]
    if "внутрь" in r or "per os" in r or "пероральн" in r:
        return ["per_os"]
    return None


# ---- public mapping ------------------------------------------------------

def normalize_mkb(value: Any) -> list[str]:
    if value is None:
        return []
    codes = value if isinstance(value, list) else [value]
    return [str(c).strip().upper() for c in codes if c is not None and str(c).strip()]


# Cyrillic -> latin transliteration for building stable ascii slugs/id's.
_CYRILLIC: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "iu", "я": "ia",
}


def _translit(text: str) -> str:
    return "".join(_CYRILLIC.get(ch, ch) for ch in text.lower())


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", _translit(text)).strip("_")
    return s or "nosology"


def _parse_age(raw_age: Any) -> str | None:
    """Resolve a guideline age group.

    Returns ``None`` when the source states no age at all.  Callers MUST NOT
    silently read that as ``"adult"``: doing so put ``"adult"`` into every
    guideline's ``age_groups`` list and stamped ``GUIDELINE_SCOPE_ADULT`` on
    child-only guidelines via ``scenario_bindings._linkage``.
    """
    a = str(raw_age or "").lower()
    if not a.strip():
        return None
    if "новорож" in a or "неонат" in a:
        return "neonate"
    if "дет" in a or "ребен" in a:
        return "child"
    if "взросл" in a or "беремен" in a or "подрост" in a:
        return "adult"
    return None


_FREQ_WORDS: dict[str, int] = {
    "один": 1, "одна": 1, "одно": 1,
    "два": 2, "две": 2,
    "три": 3,
    "четыре": 4, "четыр": 4,
    "пять": 5,
    "шесть": 6,
    "дважды": 2,
}


def parse_freq(raw_freq: Any) -> int | None:
    """Resolve a DOSA free-text frequency into frequency-per-day.

    Handles digit forms ('2 раза в день', '3 раза/сут'), Russian word-numerals
    ('два раза в день'), and common daily idioms ('в сутки', 'ежедневно',
    'один раз в день'). Returns None when the frequency cannot be determined
    unambiguously, so the caller silently drops the regimen (validate_db.js
    rejects null freq_per_day).
    """
    if not raw_freq:
        return None
    if isinstance(raw_freq, (int, float)):
        return int(raw_freq)
    s = str(raw_freq).strip().lower()
    if s == "none" or not s:
        return None

    # digit + ' раз(a)/р' patterns: '2 раза в день', '3 раза/сут', '1 р/сут'
    m = re.search(r"(\d+)\s*(?:раз|раза|р)\b", s)
    if m:
        return int(m.group(1))

    # 'затем один раз в день' -> 1
    m = re.search(r"(\d+)\s+раз", s)
    if m:
        return int(m.group(1))

    # Word-numeral before 'раз'/'прием': 'два раза в день', 'в два приема'
    m = re.search(r"(один|одна|одно|два|две|три|четыре|пять|шесть|дважды)\s+(?:раз|раза|раза|прием)", s)
    if m:
        return _FREQ_WORDS[m.group(1)]

    # 'в три приема' (numeral without 'раз')
    m = re.search(r"\b(в два|в три|в четыре|в пять|в шесть) приема", s)
    if m:
        w = m.group(1).split()[-1]
        return _FREQ_WORDS[w]

    # daily idioms -> once/day
    for kw in ("ежедневно", "в сутки", "в день", "сутки"):
        if kw in s:
            return 1

    # single-dose forms -> once
    for kw in ("однократно", "однократн", "за одно введение", "за одно применение"):
        if kw in s:
            return 1

    fallback = re.search(r"(\d+)", s)
    return int(fallback.group(1)) if fallback else None


def map_guideline(
    guideline: dict[str, Any],
    all_regimens: list[dict[str, Any]],
    notes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one db/diseases recommendation record from a DOSA guideline.

    ``notes`` (optional out-parameter) collects every skip decision with a reason
    so a dropped regimen is auditable instead of vanishing silently.

    The scenario grouping key is ``(regimen_type, age_group)`` -- NOT
    ``regimen_type`` alone.  Grouping by line alone merged an adult fixed dose
    with a child mg/kg dose into one "adult" scenario, and
    ``scenario_bindings._linkage`` then stamped ``GUIDELINE_SCOPE_ADULT`` on a
    child regimen.
    """
    scenarios: list[dict[str, Any]] = []
    # group regimens by (regimen_type, age_group) -> scenario lines
    by_line: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for reg in all_regimens:
        rt = str(reg.get("regimen_type") or "first_line").strip()
        age = _parse_age(reg.get("age_group"))
        by_line.setdefault((rt, age), []).append(reg)

    for (rt, age), regs in by_line.items():
        line_number = 2 if rt == "alternative" else 1
        drugs: dict[str, dict[str, Any]] = {}
        for reg in regs:
            drug_ref = resolve_drug_ref(reg.get("antibiotic"))
            if not drug_ref:
                _note(notes, "unresolvable_drug", reg, drug_ref=None)
                continue
            freq = parse_freq(reg.get("frequency"))
            if freq is None:
                _note(notes, "frequency_not_determined", reg, drug_ref=drug_ref)
                continue
            dose_fields = _normalize_dose(reg.get("dose"), reg.get("unit"), freq)
            if not dose_fields:
                # H-25: a regimen with no parseable dose must never reach the
                # patient-facing DB.  A "500 мл" or "2 МЕ" regimen is kept by the
                # old code purely because the name existed.
                _note(notes, "no_usable_dose", reg, drug_ref=drug_ref)
                continue
            entry = drugs.setdefault(
                drug_ref,
                {"drug_ref": drug_ref, "route": [], "regimens": []},
            )
            route = _route_to_schema(reg.get("route"))
            for r in route or []:
                if r not in entry["route"]:
                    entry["route"].append(r)
            scheme: dict[str, Any] = {}
            _apply_age(scheme, age or "adult")
            scheme["age_group_declared"] = age is not None
            scheme.update(dose_fields)
            scheme["freq_per_day"] = freq
            scheme.update(_duration_fields(reg))
            src = str(reg.get("source_quote") or "").strip()
            if src:
                # H-26: the traceability anchor belongs in the field a consumer
                # reads.  It used to be parked in `duration_note`, which nothing
                # looks at, while `duration_days` held free text.
                scheme["source_quote"] = src
            entry["regimens"].append(scheme)

        drugs_list = [d for d in drugs.values() if d["regimens"]]
        if not drugs_list:
            continue
        ages_in_line = {a for (_rt, a) in by_line if _rt == rt and a is not None}
        # Stable scenario id: keep the historical single-age form, disambiguate
        # only when one therapy line genuinely carries several age groups.
        scenario_id = f"{rt}_line" if len(ages_in_line) <= 1 else f"{rt}_{age or 'unspecified'}_line"
        scenarios.append(
            {
                "id": scenario_id,
                "name": rt,
                "age_group": age or "adult",
                "age_group_declared": age is not None,
                "lines": [
                    {
                        "line_number": line_number,
                        "line_label": _line_label(rt),
                        "drugs": drugs_list,
                    }
                ],
            }
        )

    # L-12: only age groups the source ACTUALLY states; a child-only guideline
    # must not advertise "adult".
    age_groups: list[str] = []
    for reg in all_regimens:
        a = _parse_age(reg.get("age_group"))
        if a and a not in age_groups:
            age_groups.append(a)

    record: dict[str, Any] = {
        "id": _slug(str(guideline.get("diagnosis") or guideline.get("guideline_name") or "nosology")),
        "mkb10": normalize_mkb(guideline.get("mkb")),
        "name": guideline.get("guideline_name") or guideline.get("diagnosis") or "",
        "synonyms": [],
        "cr_id": str(guideline.get("code_version") or ""),
        "cr_year": _guideline_year(guideline),
        "cr_updated": _guideline_year(guideline),
        "source_url": _source_url(guideline),
        "antibiotics_indicated": True,
        "indications": [],
        "age_groups": age_groups or ["adult"],
        "scenarios": scenarios,
    }
    return record


def _note(notes: list[dict[str, Any]] | None, reason: str, reg: dict[str, Any], drug_ref: str | None) -> None:
    if notes is None:
        return
    notes.append({
        "reason": reason,
        "antibiotic": reg.get("antibiotic"),
        "drug_ref": drug_ref,
        "dose": reg.get("dose"),
        "unit": reg.get("unit"),
        "frequency": reg.get("frequency"),
        "age_group": reg.get("age_group"),
        "regimen_type": reg.get("regimen_type"),
    })


def _guideline_year(guideline: dict[str, Any]) -> int | None:
    """Read the approval year from whichever field the DOSA payload carries."""
    for key in ("cr_year", "approval_year", "year", "PublishDateStr", "publication_date", "publish_date"):
        value = guideline.get(key)
        if value in (None, ""):
            continue
        match = re.search(r"(19|20)\d{2}", str(value))
        if match:
            return int(match.group(0))
    return None


def _source_url(guideline: dict[str, Any]) -> str:
    """Build a usable rubricator URL, never a dangling ``.../view-cr/`` fragment."""
    code_version = str(guideline.get("code_version") or "").strip()
    explicit = str(guideline.get("source_url") or "").strip()
    if explicit:
        return explicit
    if not code_version:
        return ""
    return f"https://cr.minzdrav.gov.ru/view-cr/{code_version}"


def _duration_fields(reg: dict[str, Any]) -> dict[str, Any]:
    """Split a free-text duration into day numbers plus the verbatim wording.

    ``duration_days`` used to receive "7-10 дней" (free text in a field named
    after a number) and the source quote was parked in ``duration_note``.
    """
    raw = str(reg.get("duration") or "").strip()
    fields: dict[str, Any] = {}
    if not raw:
        fields["duration_days"] = ""
        return fields
    numbers = re.findall(r"\d+", raw)
    if numbers:
        values = [int(n) for n in numbers]
        fields["duration_days"] = min(values)
        if len(set(values)) > 1:
            fields["duration_days_max"] = max(values)
    else:
        fields["duration_days"] = ""
    fields["duration_text"] = raw
    return fields


def _apply_age(scheme: dict[str, Any], age: str) -> None:
    scheme["age_group"] = age


def _line_label(rt: str) -> str:
    if rt == "alternative":
        return "Альтернативная схема"
    if rt == "prophylaxis":
        return "Профилактика"
    return "Первая линия"


def build_mapped_db(kb: list[dict[str, Any]], targets: set[str]) -> dict[str, Any]:
    """Return {recommendations, coverage, skipped} for the given target code_versions.

    M-28: ``_gmeta`` was an O(n) scan per guideline, i.e. O(n^2) over the corpus.
    The guideline metadata is now indexed once by ``code_version``.
    """
    recommendations: list[dict[str, Any]] = []
    by_cv: dict[str, list[dict[str, Any]]] = {}
    meta_by_cv: dict[str, dict[str, Any]] = {}
    for g in kb:
        cv = g.get("code_version")
        if cv not in targets:
            continue
        by_cv.setdefault(str(cv), g.get("regimens", []))
        meta_by_cv.setdefault(str(cv), _gmeta(g))

    total_symbols = 0
    mapped_symbols = 0
    skipped_drug = 0
    skipped: list[dict[str, Any]] = []
    for cv, regs in by_cv.items():
        total_symbols += len(regs)
        notes: list[dict[str, Any]] = []
        rec = map_guideline({"code_version": cv, **meta_by_cv[cv]}, regs, notes=notes)
        for note in notes:
            skipped.append({"code_version": cv, **note})
        produced = (
            sum(len(sc["lines"][0]["drugs"]) for sc in rec["scenarios"])
            if rec["scenarios"] else 0
        )
        mapped_symbols += produced
        skipped_drug += total_symbols - mapped_symbols if rec["scenarios"] else total_symbols
        if rec["scenarios"]:
            recommendations.append(rec)
    return {
        "recommendations": recommendations,
        "total_symbols": total_symbols,
        "mapped_symbols": mapped_symbols,
        "skipped_drug": skipped_drug,
        "skipped": skipped,
    }


def _gmeta(guideline: dict[str, Any]) -> dict[str, Any]:
    return {
        "guideline_name": guideline.get("guideline_name"),
        "diagnosis": guideline.get("diagnosis"),
        "mkb": guideline.get("mkb"),
        "cr_year": guideline.get("cr_year") or guideline.get("approval_year"),
        "source_url": guideline.get("source_url"),
    }
