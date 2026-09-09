"""Source-by-evidence dose verification harness.

For every disease, compare the calculator's stored regimen doses (db/antibio_db.json)
against the doses EXTRACTED FROM THE OFFICIAL PDFs (DOSA knowledge_base.json, each dose
anchored by source_quote + page_number + pdf_sha256).

Method: for each DB regimen, select the best-matching KB row for the SAME drug AND same
age-group AND (where possible) route, choosing the KB dose NEAREST to the DB value. This
answers "is there a PDF-extracted source value consistent with the calculator's dose?" —
not "does the calculator match the first KB row".

This produces OBJECTIVE machine evidence (MATCH / MISMATCH / UNCOMPARABLE). It does NOT
set any clinical-approval status, does NOT unblock any disease, and is NOT a medical
verdict. Physician attestation (P5.6/P6) stays with the owner/physician.

Usage:  python -m src.pipeline.extraction.dose_verification --db db/antibio_db.json \
            --kb /path/to/knowledge_base.json --output tmp/dose_verification.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

KB_DEFAULT = "/var/folders/vr/knn1v1l92t7b206mnw7htvvm0000gn/T/opencode/clinrec-downloader/knowledge_base.json"

_DRUG_TOKENS = {
    "амоксициллин+[клавулановая кислота]": "amoxiclav",
    "амоксициллина клавуланат": "amoxiclav",
    "амоксициллин": "amoxicillin",
    "ампициллин+[сульбактам]": "ampicillin_sulbactam",
    "ампициллин": "ampicillin",
    "цефтриаксон": "ceftriaxone",
    "цефуроксим": "cefuroxime",
    "цефиксим": "cefixime",
    "цефотаксим": "cefotaxime",
    "цефазолин": "cefazolin",
    "цефтазидим": "ceftazidime",
    "кларитромицин": "clarithromycin",
    "азитромицин": "azithromycin",
    "джозамицин": "josamycin",
    "эритромицин": "erythromycin",
    "ванкомицин": "vancomycin",
    "метронидазол": "metronidazole",
    "ципрофлоксацин": "ciprofloxacin",
    "левофлоксацин": "levofloxacin",
    "моксифлоксацин": "moxifloxacin",
    "доксициклин": "doxycycline",
    "гентамицин": "gentamicin",
    "амикацин": "amikacin",
    "меропенем": "meropenem",
    "линезолид": "linezolid",
    "клиндамицин": "clindamycin",
    "пиперациллин": "piperacillin_tazobactam",
    "ко-тримоксазол": "cotrimoxazole",
    "нитрофурантоин": "nitrofurantoin",
    "фосфомицин": "fosfomycin",
    "изониазид": "isoniazid",
    "рифампицин": "rifampicin",
    "пиразинамид": "pyrazinamide",
    "этамбутол": "ethambutol",
}


def _clean_antibiotic(raw: str) -> str:
    s = (raw or "").lower()
    for ch in ["**", "#", "[", "]", ", ", ")"]:
        s = s.replace(ch, ch if ch == ", " else "")
    s = re.sub(r"\s*\[\d+\]\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# DB drug_ref (English key) -> Russian substring for KB matching
_REF_TO_KB = {
    "amoxicillin": ["амоксициллин"],
    "amoxiclav": ["амоксициллин", "клавулан"],
    "ampicillin": ["ампициллин"],
    "ampicillin_sulbactam": ["ампициллин", "сульбактам"],
    "piperacillin_tazobactam": ["пиперациллин"],
    "ceftriaxone": ["цефтриаксон"],
    "cefuroxime": ["цефуроксим"],
    "cefixime": ["цефиксим"],
    "cefotaxime": ["цефотаксим"],
    "cefazolin": ["цефазолин"],
    "ceftazidime": ["цефтазидим"],
    "cefepime": ["цефепим"],
    "clarithromycin": ["кларитромицин"],
    "azithromycin": ["азитромицин"],
    "josamycin": ["джозамицин"],
    "erythromycin": ["эритромицин"],
    "vancomycin": ["ванкомицин"],
    "metronidazole": ["метронидазол"],
    "ciprofloxacin": ["ципрофлоксацин"],
    "levofloxacin": ["левофлоксацин"],
    "moxifloxacin": ["моксифлоксацин"],
    "doxycycline": ["доксициклин"],
    "gentamicin": ["гентамицин"],
    "amikacin": ["амикацин"],
    "meropenem": ["меропенем"],
    "linezolid": ["линезолид"],
    "clindamycin": ["клиндамицин"],
    "cotrimoxazole": ["ко-тримоксазол", "сульфаметоксазол", "триметоприм"],
    "nitrofurantoin": ["нитрофурантоин"],
    "fosfomycin": ["фосфомицин"],
    "isoniazid": ["изониазид"],
    "rifampicin": ["рифампицин"],
    "pyrazinamide": ["пиразинамид"],
    "ethambutol": ["этамбутол"],
}

def _drug_ref_token(ref: str) -> str | None:
    """Resolve a DB drug_ref (English key) to a KB match token."""
    if not ref:
        return None
    r = ref.strip()
    if r in _REF_TO_KB:
        return _REF_TO_KB[r][0]
    return r

def _kb_matches_ref(kb_r, ref):
    """Check whether a KB regimen antibiotic string (Russian) matches a DB drug_ref."""
    if not ref:
        return False
    low = (kb_r.get("antibiotic") or "").lower()
    for ru in _REF_TO_KB.get(ref, [ref]):
        if ru in low:
            return True
    return False

def _drug_token(raw: str) -> str | None:
    c = _clean_antibiotic(raw)
    for k, v in _DRUG_TOKENS.items():
        if k in c:
            return v
    return None


def _norm_mg(s: str) -> float | None:
    s = (s or "").replace(",", ".").strip()
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _norm_range(s: str) -> tuple[float | None, float | None]:
    """Parse '50-60' / '0,2-0,4' / '875/125' -> (lo, hi) in same unit, else (n, n)."""
    s = (s or "").replace(",", ".").strip()
    # split on dash/hyphen ranges (500-1000, 0,2-0,4); avoid 125/31,25 style slashes
    m = re.match(r"^(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)$", s)
    if m:
        return float(m.group(1)), float(m.group(2))
    n = re.search(r"\d+(?:\.\d+)?", s)
    v = float(n.group(0)) if n else None
    return v, v


def _kb_sources(kb_r):
    """Return (kb_kg_range, kb_fixed_range) as (lo,hi) tuples for a KB regimen row."""
    u = (kb_r.get("unit") or "").lower()
    dose = kb_r.get("dose")
    if "кг" in u:
        lo, hi = _norm_range(dose)
        return (lo, hi), None
    lo, hi = _norm_range(dose)
    if lo is None:
        return None, None
    # "г" or "гр" as unit means grams -> convert to mg; but "мг" is already mg
    if (" г " in f" {u} " or u.startswith("г ") or u.endswith(" г") or u == "г" or
        " гр" in u or u.startswith("гр") or u == "гр"):
        return None, (lo * 1000, hi * 1000 if hi is not None else lo * 1000)
    return None, (lo, hi)


def _parse_freq_per_day(text: str | None) -> float | None:
    """Parse a KB frequency string ('3 раза в сутки', 'в 2-3 приема', '2 р/д').

    Returns the upper bound of a range ('2-3' -> 3): the DB stores one regimen
    per frequency variant, so matching against the max keeps variants distinct.
    Returns None when unparsable — caller falls back to the DB freq_per_day.
    """
    if not text:
        return None
    s = str(text).replace(",", ".").lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)", s)
    if m and ("прием" in s or "приём" in s or "раз" in s or "р/д" in s or "р/д" in s or "сут" in s):
        return float(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:раз(?:а|ы)?|р/д|р/д|прием|приём)", s)
    if m:
        return float(m.group(1))
    if "однократ" in s or "один раз" in s or "1 раз" in s:
        return 1.0
    return None


def _dose_basis(reg: dict) -> str:
    """Derive the denominator_time basis of a DB regimen (RC-030).

    Returns one of: 'both_consistent' (single*freq == daily — КР пишет
    разовую, БД хранит обе формы согласованно), 'per_dose_only',
    'per_day_only', 'weight_per_day_only', 'inconsistent' (single*freq !=
    daily beyond 5%+1мг — требует разбора), 'none'.
    """
    single = reg.get("single_dose_mg")
    fixed = reg.get("dose_mg_day_fixed")
    per_kg = reg.get("dose_mg_kg_day")
    freq = reg.get("freq_per_day")
    has_single = single is not None
    has_daily = fixed is not None or per_kg is not None
    if has_single and has_daily and freq:
        daily = fixed if fixed is not None else None
        if daily is not None:
            lo = single * freq
            tol = 0.05 * abs(lo) + 1
            if abs(daily - lo) <= tol:
                return "both_consistent"
            return "inconsistent"
        return "both_consistent"  # per-kg daily + single cannot be cross-checked w/o weight
    if has_single:
        return "per_dose_only"
    if fixed is not None:
        return "per_day_only"
    if per_kg is not None:
        return "weight_per_day_only"
    return "none"


def _age_token(age_group: str) -> str:
    a = (age_group or "").lower()
    if any(t in a for t in ["дет", "ребен", "ребён", "новорож", "грудн", "младен", "школьн"]):
        return "child"
    if any(t in a for t in ["взросл", "беремен"]):
        return "adult"
    return "all"


def _route_token(route: str) -> str:
    r = (route or "").lower()
    if "в/в" in r or "инфуз" in r or "капел" in r or "внутрив" in r:
        return "iv"
    if "в/м" in r or "внутрим" in r:
        return "im"
    if "внутр" in r:
        return "per_os"
    return "all"


def _dist(a, b) -> float:
    if a is None or b is None:
        return float("inf")
    return abs(a - b) / max(abs(b), 1e-9)


def _match(db_kg, db_fixed, kb_range, db_single=None, freq=None, kb_freq=None) -> tuple[str, float, str]:
    """Compare a DB dose against a KB published range; returns (status, distance, basis).

    Freq-aware (RC-030/denominator_time): the KB wording may publish the SINGLE
    dose ('300 мг') while the DB stores the DAILY dose (1200 мг, freq=4), or
    vice versa. Candidates are therefore tried in source-faithful order:

      'single'         KB value == DB single_dose_mg (КР пишет разовую)
      'fixed'/'kg'     KB value == DB daily dose
      'single_x_freq'  KB single × freq == DB daily (разовая из КР × кратность)
      'daily_per_dose' KB value == DB daily / freq (суточная из КР ÷ кратность)

    kb_freq (parsed from the KB 'frequency' string) is preferred for the
    cross-multiplication; DB freq_per_day is the fallback.
    """
    kb_kg, kb_fixed = kb_range
    f = kb_freq or freq  # multiplications per day
    cands: list[tuple[float | None, str]] = [
        (db_single, "single"),
        (db_fixed, "fixed"),
        (db_kg, "kg"),
    ]
    if db_single is not None and f:
        cands.append((db_single * f, "single_x_freq"))
    daily = db_fixed if db_fixed is not None else None
    if daily is not None and f:
        cands.append((daily / f, "daily_per_dose"))
    if db_kg is not None and f:
        cands.append((db_kg / f, "kg_per_dose"))
    cands = [(v, b) for v, b in cands if v is not None]
    if not cands:
        return "UNCOMPARABLE", float("inf"), "none"
    # same-basis comparison first (kg vs kg-range, fixed vs fixed-range),
    # then cross-basis (single vs fixed-range etc.)
    best_mismatch: tuple[float, str] | None = None
    for v, basis in cands:
        if basis in ("kg", "kg_per_dose") and kb_kg is not None:
            kb_txt = f"{kb_kg[0]}-{kb_kg[1]}"
        elif basis not in ("kg", "kg_per_dose") and kb_fixed is not None:
            kb_txt = f"{kb_fixed[0]}-{kb_fixed[1]}"
        else:
            kv = kb_kg if kb_kg is not None else kb_fixed
            if kv is None:
                continue
            kb_txt = f"{kv[0]}-{kv[1]}"
            basis = basis + "_cross" if basis in ("single", "fixed", "kg") else basis
        st = _match_range(v, kb_txt)
        if st == "MATCH":
            return st, 0.0, basis
        d = _dist(v, _norm_range(kb_txt)[0])
        if best_mismatch is None or d < best_mismatch[0]:
            best_mismatch = (d, basis)
    if best_mismatch is not None:
        return "MISMATCH", best_mismatch[0], best_mismatch[1]
    return "UNCOMPARABLE", float("inf"), "none"


def _match_val(db_v, kb_v) -> str:
    if db_v is None or kb_v is None:
        return "UNCOMPARABLE"
    if _dist(db_v, kb_v) <= 0.05:
        return "MATCH"
    return "MISMATCH"


def _match_range(db_v, kb_text) -> str:
    """Compare a DB dose against a published range string like '50-60' mg/kg."""
    if db_v is None or kb_text is None:
        return "UNCOMPARABLE"
    lo, hi = _norm_range(kb_text)
    if lo is None:
        return "UNCOMPARABLE"
    return "MATCH" if lo - 0.05 * abs(lo) - 1 <= db_v <= hi + 0.05 * abs(lo) + 1 else "MISMATCH"


def _select_best(db_kg, db_fixed, cands_by_drug, age_tok, route_tok, db_single=None, freq=None):
    """Pick the nearest KB row among same-drug candidates, favoring same age+route."""
    best = None
    best_key = (float("inf"), float("inf"))
    for kb_r in cands_by_drug:
        kb_kg, kb_fixed = _kb_sources(kb_r)
        ka = _age_token(kb_r.get("age_group", ""))
        kr = _route_token(kb_r.get("route", ""))
        age_pen = 0 if ka == age_tok or age_tok == "all" else 1
        route_pen = 0 if kr == route_tok or route_tok == "all" or kr == "all" else 1
        kb_freq = _parse_freq_per_day(kb_r.get("frequency"))
        st, d, basis = _match(db_kg, db_fixed, (kb_kg, kb_fixed),
                              db_single=db_single, freq=freq, kb_freq=kb_freq)
        key = (age_pen + route_pen, d if st != "UNCOMPARABLE" else float("inf"))
        if key < best_key:
            best_key = key
            best = (kb_r, st, d, basis)
    return best


def verify(db_path: str, kb_path: str) -> dict:
    db = json.loads(Path(db_path).read_text(encoding="utf-8-sig"))
    kb = json.loads(Path(kb_path).read_text(encoding="utf-8-sig"))
    kb_by_cv = {}
    for g in kb:
        cv = g.get("code_version")
        if cv and cv not in kb_by_cv:
            kb_by_cv[cv] = g

    diseases = []
    total_regs = matched = mismatched = uncomparable = no_kb = 0
    for rec in db["recommendations"]:
        cr_id = rec.get("cr_id")
        kb_g = kb_by_cv.get(str(cr_id))
        if not kb_g:
            no_kb += 1
            diseases.append({"disease_id": rec["id"], "name": rec["name"], "cr_id": cr_id, "status": "NO_KB_GUIDELINE", "regimens_checked": 0})
            continue

        kb_regs = kb_g.get("regimens", [])
        checks = []
        d_total = d_match = d_mismatch = d_uncomp = 0
        for sc in rec.get("scenarios", []):
            for ln in sc.get("lines", []):
                for dr in ln.get("drugs", []):
                    ref = dr.get("drug_ref", "")
                    druktok = _drug_ref_token(ref)
                    route_tok = _route_key(dr.get("route", []))
                    for reg in dr.get("regimens", []):
                        d_total += 1
                        db_kg = reg.get("dose_mg_kg_day")
                        db_fixed = reg.get("dose_mg_day_fixed")
                        db_single = reg.get("single_dose_mg")
                        freq = reg.get("freq_per_day")
                        basis_declared = _dose_basis(reg)
                        age_tok = _age_token(reg.get("age_group") or sc.get("age_group") or "")
                        cands = [kb_r for kb_r in kb_regs if _kb_matches_ref(kb_r, ref)]
                        if not cands:
                            d_uncomp += 1
                            checks.append({"drug": druktok, "status": "UNCOMPARABLE", "reason": "no_kb_drug"})
                            continue
                        sel = _select_best(db_kg, db_fixed, cands, age_tok, route_tok,
                                           db_single=db_single, freq=freq)
                        kb_r, st, d, basis = sel
                        checks.append({
                            "drug": druktok, "status": st, "basis": basis,
                            "dose_basis": basis_declared,
                            "db_kg": db_kg, "db_fixed": db_fixed,
                            "db_single": db_single, "freq_per_day": freq,
                            "kb": f"{kb_r.get('dose')} {kb_r.get('unit')}",
                            "kb_frequency": kb_r.get("frequency"),
                            "page": kb_r.get("page_number"), "sha": kb_g.get("pdf_sha256"),
                        })
                        if st == "MATCH":
                            d_match += 1
                        elif st == "MISMATCH":
                            d_mismatch += 1
                        else:
                            d_uncomp += 1

        disease_status = ("NO_REGIMENS" if d_total == 0 else
                          "ALL_MATCH" if d_mismatch == 0 and d_uncomp == 0 else
                          "MATCH_WITH_UNCOMPARABLE" if d_mismatch == 0 else
                          "MISMATCHES" if d_mismatch > 0 else "UNCOMPARABLE")
        diseases.append({
            "disease_id": rec["id"], "name": rec["name"], "cr_id": cr_id, "status": disease_status,
            "regimens_checked": d_total, "match": d_match, "mismatch": d_mismatch, "uncomparable": d_uncomp,
            "checks": checks,
        })
        total_regs += d_total
        matched += d_match
        mismatched += d_mismatch
        uncomparable += d_uncomp

    return {
        "schema_version": "1.0.0",
        "artifact_type": "DOSE_SOURCE_VERIFICATION",
        "note": "Objective machine comparison of calculator doses vs PDF-extracted source doses (nearest same-drug/age/route KB row). NOT a medical verdict; no disease unblocked.",
        "summary": {
            "diseases_total": len(db["recommendations"]), "no_kb_guideline": no_kb,
            "regimens_total": total_regs, "matched": matched, "mismatched": mismatched, "uncomparable": uncomparable,
        },
        "diseases": diseases,
    }


def _route_key(routes) -> str:
    r = routes or []
    if any(x in ("iv", "im") for x in r):
        return "iv" if "iv" in [x for x in r] else ("im" if "im" in r else "iv")
    if "per_os" in r:
        return "per_os"
    return "all"


def _main(argv=None):
    p = argparse.ArgumentParser(description="Dose source-verification harness (evidence only).")
    p.add_argument("--db", default="db/antibio_db.json")
    p.add_argument("--kb", default=KB_DEFAULT)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    rep = verify(args.db, args.kb)
    Path(args.output).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    s = rep["summary"]
    print(json.dumps({"artifact_type": rep["artifact_type"], "diseases_total": s["diseases_total"],
                      "no_kb_guideline": s["no_kb_guideline"], "regimens_total": s["regimens_total"],
                      "matched": s["matched"], "mismatched": s["mismatched"], "uncomparable": s["uncomparable"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    _main()
