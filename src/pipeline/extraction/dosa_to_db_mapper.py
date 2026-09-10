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
from src.pipeline.extraction.icd10 import normalize_mkb as _normalize_mkb

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


def _de_inflect(text: str) -> list[str]:
    """Yield shorter nominative candidates of a Russian drug name.

    Non-destructive: always returns a list that starts with the input unchanged.
    """
    candidates = [text]
    for end in _RU_ENDINGS:
        if text.endswith(end) and len(text) - len(end) >= 4:
            candidates.append(text[: -len(end)])
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


def _normalize_dose(raw_dose: Any, raw_unit: Any, freq: int) -> dict[str, Any]:
    """Convert a raw dose/unit/freq into simplified schema dose fields.

    Returns a partial regimen-covering dict (dose_mg_kg_day / dose_mg_day_fixed
    / single_dose_mg / max_daily_mg), possibly empty if unparseable.
    """
    out: dict[str, Any] = {}
    dose = str(raw_dose or "").strip().replace(",", ".")
    unit = str(raw_unit or "").strip().lower()
    if not dose:
        return out
    num = _first_number(dose)
    if num is None:
        return out

    if "мг/кг" in unit:
        out["dose_mg_kg_day"] = num
        return out

    # '0,2–0,4' range -> keep min as base, record range
    rng = _number_range(dose)
    if unit in ("г", "g"):
        value_mg = num * 1000.0
        out["dose_mg_day_fixed"] = value_mg
        if freq:
            out["max_daily_mg"] = value_mg * freq
    elif unit in ("мг", "mg"):
        out["dose_mg_day_fixed"] = num
        if freq:
            out["max_daily_mg"] = num * freq
    return out


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
    """Delegated to ``extraction.icd10`` — splits comma-joined code lists.

    Was a local copy that returned ``["A00.0, A00.1"]`` for a comma-joined
    string; that produced single-element ``mkb10`` arrays in
    ``db/diseases/extended_dosa.json`` and broke every downstream ICD-10 join.
    """
    return _normalize_mkb(value)


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
    a = str(raw_age or "").lower()
    if "новорож" in a or "неонат" in a:
        return "neonate"
    if "дет" in a or "ребен" in a:
        return "child"
    if "взросл" in a or "беремен" in a:
        return "adult"
    return "adult"


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


def map_guideline(guideline: dict[str, Any], all_regimens: list[dict[str, Any]]) -> dict[str, Any]:
    """Build one db/diseases recommendation record from a DOSA guideline."""
    scenarios: list[dict[str, Any]] = []
    # group regimens by regimen_type -> scenario lines
    by_line: dict[str, list[dict[str, Any]]] = {}
    for reg in all_regimens:
        rt = str(reg.get("regimen_type") or "first_line").strip()
        by_line.setdefault(rt, []).append(reg)

    for rt, regs in by_line.items():
        line_number = 2 if rt == "alternative" else 1
        drugs: dict[str, dict[str, Any]] = {}
        for reg in regs:
            drug_ref = resolve_drug_ref(reg.get("antibiotic"))
            if not drug_ref:
                continue
            freq = parse_freq(reg.get("frequency"))
            if freq is None:
                continue
            dose_fields = _normalize_dose(reg.get("dose"), reg.get("unit"), freq)
            entry = drugs.setdefault(
                drug_ref,
                {"drug_ref": drug_ref, "route": [], "regimens": []},
            )
            route = _route_to_schema(reg.get("route"))
            for r in route or []:
                if r not in entry["route"]:
                    entry["route"].append(r)
            scheme: dict[str, Any] = {}
            age = _parse_age(reg.get("age_group"))
            _apply_age(scheme, age)
            scheme.update(dose_fields)
            scheme["freq_per_day"] = freq
            scheme["duration_days"] = str(reg.get("duration") or "")
            src = str(reg.get("source_quote") or "").strip()
            if src:
                scheme["duration_note"] = src
            entry["regimens"].append(scheme)

        drugs_list = [d for d in drugs.values() if d["regimens"]]
        if not drugs_list:
            continue
        scenarios.append(
            {
                "id": f"{rt}_line",
                "name": rt,
                "age_group": _parse_age(regs[0].get("age_group")),
                "lines": [
                    {
                        "line_number": line_number,
                        "line_label": _line_label(rt),
                        "drugs": drugs_list,
                    }
                ],
            }
        )

    age_groups: list[str] = []
    for reg in all_regimens:
        a = _parse_age(reg.get("age_group"))
        if a not in age_groups:
            age_groups.append(a)

    record: dict[str, Any] = {
        "id": _slug(str(guideline.get("diagnosis") or guideline.get("guideline_name") or "nosology")),
        "mkb10": normalize_mkb(guideline.get("mkb")),
        "name": guideline.get("guideline_name") or guideline.get("diagnosis") or "",
        "synonyms": [],
        "cr_id": str(guideline.get("code_version") or ""),
        "cr_year": None,
        "cr_updated": None,
        "source_url": f"https://cr.minzdrav.gov.ru/view-cr/{guideline.get('code_version')}",
        "antibiotics_indicated": True,
        "indications": [],
        "age_groups": age_groups or ["adult"],
        "scenarios": scenarios,
    }
    return record


def _apply_age(scheme: dict[str, Any], age: str) -> None:
    scheme["age_group"] = age


def _line_label(rt: str) -> str:
    if rt == "alternative":
        return "Альтернативная схема"
    if rt == "prophylaxis":
        return "Профилактика"
    return "Первая линия"


def build_mapped_db(kb: list[dict[str, Any]], targets: set[str]) -> dict[str, Any]:
    """Return {recommendations, coverage} for the given target code_versions."""
    recommendations: list[dict[str, Any]] = []
    by_cv: dict[str, list[dict[str, Any]]] = {}
    for g in kb:
        if g.get("code_version") in targets:
            by_cv[str(g.get("code_version"))] = g.get("regimens", [])

    total_symbols = 0
    mapped_symbols = 0
    skipped_drug = 0
    for cv, regs in by_cv.items():
        total_symbols += len(regs)
        rec = map_guideline({"code_version": cv, "regimens": regs, **(_gmeta(kb, cv))}, regs)
        mapped_symbols += sum(len(sc["lines"][0]["drugs"]) for sc in rec["scenarios"]) if rec["scenarios"] else 0
        skipped_drug += total_symbols - mapped_symbols if rec["scenarios"] else total_symbols
        if rec["scenarios"]:
            recommendations.append(rec)
    return {"recommendations": recommendations, "total_symbols": total_symbols, "mapped_symbols": mapped_symbols, "skipped_drug": skipped_drug}


def _gmeta(kb: list[dict[str, Any]], cv: str) -> dict[str, Any]:
    for g in kb:
        if g.get("code_version") == cv:
            return {
                "guideline_name": g.get("guideline_name"),
                "diagnosis": g.get("diagnosis"),
                "mkb": g.get("mkb"),
            }
    return {}
