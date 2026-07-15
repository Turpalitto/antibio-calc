"""Clinical Data Quality Audit — read-only. Fills the Clinical Data Issues registry.

Milestone: Clinical Content Phase. Compares ANTIBIO data (raw extraction ↔
normalized) against itself and against source-quote signals, classifies every
discrepancy by source (Extraction / Normalizer / Dictionary / DiagnosisIndex),
and writes a machine-readable registry + a human report. It CHANGES NOTHING.

Attribution principle (key): for each regimen field (dose/frequency/duration/
route), compare presence in the RAW extraction vs the NORMALIZED row:
  - raw EMPTY  + normalized MISSING → Extraction (field never captured from КР)
  - raw PRESENT + normalized MISSING → Normalizer (captured but not parsed)
Plus dose-specific normalizer signals (alternative dosing collapsed; daily-dose
taken as per-administration when freq>=2), dictionary unknowns, guideline-level
extraction-gap candidates and duplicate-title guidelines.

Every entry is status=pending_review. Automated findings are verification=
heuristic_flag; PDF-confirmed findings (e.g. guideline 1638) are enriched
verification=pdf_confirmed.

Usage (from repo root):
    python -m clinical_engine.tools.clinical_data_audit \
        [--raw C:/clinrec_downloader/metadata.sqlite] \
        [--norm C:/clinrec_downloader/normalized_regimens.sqlite] \
        [--registry clinical_data_issues.json] \
        [--report clinical_data_audit_report.md]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_RAW = r"C:\clinrec_downloader\metadata.sqlite"
_DEFAULT_NORM = r"C:\clinrec_downloader\normalized_regimens.sqlite"
_DEFAULT_REGISTRY = "clinical_data_issues.json"
_DEFAULT_REPORT = "clinical_data_audit_report.md"

_DAILY_RE = re.compile(r"/\s*сут|в\s*сут|сутк", re.IGNORECASE)

# issue_code -> (problem_type, severity, human description template)
_ISSUE_META = {
    "DOSE_DAILY_MISREAD":      ("Normalizer", "High",   "Суточная доза, вероятно, взята как разовая (freq>=2) — риск завышения суточной дозы"),
    "DOSE_ALTERNATIVE_COLLAPSED":("Normalizer","Medium", "В КР несколько вариантов дозы ('или') — нормализатор оставил один"),
    "DOSE_NOT_PARSED":         ("Normalizer", "High",   "Доза присутствует в сыром извлечении, но не нормализована (NULL)"),
    "FREQ_NOT_PARSED":         ("Normalizer", "Medium", "Кратность есть в сыром извлечении, но не нормализована (NULL)"),
    "DURATION_NOT_PARSED":     ("Normalizer", "Low",    "Длительность есть в сыром извлечении, но не нормализована (NULL)"),
    "DOSE_NOT_EXTRACTED":      ("Extraction", "High",   "Доза отсутствует и в сыром извлечении (не захвачена из КР)"),
    "FREQ_NOT_EXTRACTED":      ("Extraction", "Medium", "Кратность отсутствует в сыром извлечении"),
    "ROUTE_NOT_EXTRACTED":     ("Extraction", "Medium", "Путь введения отсутствует в сыром извлечении"),
    "EXTRACTION_GAP_CANDIDATE":("Extraction", "High",   "В КР упомянуто существенно больше препаратов, чем извлечено схем"),
    "DRUG_UNKNOWN":            ("Dictionary", "Medium", "Препарат не распознан словарём (DRUG_UNKNOWN)"),
    "DUPLICATE_GUIDELINE_TITLE":("DiagnosisIndex","Low", "Одна и та же КР (title) под несколькими guideline_id"),
}


def _ne(s) -> bool:
    return s is not None and str(s).strip() != ""


def _iid(*parts) -> str:
    return "cdi_" + hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _entry(issue_code, guideline_id, diagnosis, regimen_id, kr_quote, antibio_data,
           suspected_cause, verification="heuristic_flag", severity_override=None,
           description_override=None):
    ptype, sev, desc = _ISSUE_META[issue_code]
    return {
        "issue_id": _iid(issue_code, guideline_id, regimen_id or ""),
        "guideline_id": guideline_id,
        "diagnosis": diagnosis,
        "regimen_id": regimen_id,
        "problem_type": ptype,
        "issue_code": issue_code,
        "description": description_override or desc,
        "kr_quote": kr_quote,
        "antibio_data": antibio_data,
        "suspected_cause": suspected_cause,
        "severity": severity_override or sev,
        "verification": verification,
        "status": "pending_review",
    }


def audit(raw_path, norm_path):
    raw = sqlite3.connect(raw_path); raw.row_factory = sqlite3.Row
    nd = sqlite3.connect(norm_path); nd.row_factory = sqlite3.Row
    ar = {str(r["id"]): r for r in raw.execute("SELECT * FROM antibiotic_regimens").fetchall()}
    nr = list(nd.execute("SELECT * FROM normalized_regimens").fetchall())
    clinrecs = {str(r["id"]): r for r in raw.execute("SELECT id,name,abx_drugs FROM clinrecs").fetchall()}

    issues = []
    # per-guideline extracted drug set + diagnosis + PASS-clean tracking
    extracted_drugs = defaultdict(set)
    gid_diagnosis = {}
    gid_has_pass = defaultdict(bool)
    gid_normalizer_flag = defaultdict(bool)

    for rid, r in ar.items():
        extracted_drugs[str(r["clinrec_id"])].add((r["antibiotic"] or "").strip())
        gid_diagnosis.setdefault(str(r["clinrec_id"]), r["diagnosis"] or "")

    for n in nr:
        rid = n["regimen_id"]; gid = n["guideline_id"]
        r = ar.get(rid)
        diagnosis = (r["diagnosis"] if r else n["diagnosis"]) or ""
        quote = (r["source_quote"] if r else "") or ""
        adata = {"drug": n["drug_normalized"], "dose": n["dose"], "dose_unit": n["dose_unit"],
                 "frequency": n["frequency"], "duration_recommended": n["duration_recommended"],
                 "route": n["route"], "verdict": n["validation_verdict"]}
        if n["validation_verdict"] == "PASS":
            gid_has_pass[gid] = True

        if r is not None:
            raw_dose, raw_freq, raw_dur, raw_route = r["dose"], r["frequency"], r["duration"], r["route"]
            dtext = str(raw_dose or "").lower()
            # DOSE
            if n["dose"] is None:
                code = "DOSE_NOT_EXTRACTED" if not _ne(raw_dose) else "DOSE_NOT_PARSED"
                issues.append(_entry(code, gid, diagnosis, rid, quote, adata,
                                     f"raw dose={raw_dose!r}"))
                if code == "DOSE_NOT_PARSED": gid_normalizer_flag[gid] = True
            else:
                if "или" in dtext:
                    issues.append(_entry("DOSE_ALTERNATIVE_COLLAPSED", gid, diagnosis, rid, quote, adata,
                                         f"raw dose has alternatives: {raw_dose!r}"))
                    gid_normalizer_flag[gid] = True
                if _DAILY_RE.search(dtext) and (n["frequency"] or 0) >= 2:
                    issues.append(_entry("DOSE_DAILY_MISREAD", gid, diagnosis, rid, quote, adata,
                                         f"raw dose daily-unit: {raw_dose!r}; normalized {n['dose']}{n['dose_unit']} x{n['frequency']}"))
                    gid_normalizer_flag[gid] = True
            # FREQUENCY
            if n["frequency"] is None:
                code = "FREQ_NOT_EXTRACTED" if not _ne(raw_freq) else "FREQ_NOT_PARSED"
                issues.append(_entry(code, gid, diagnosis, rid, quote, adata, f"raw freq={raw_freq!r}"))
                if code == "FREQ_NOT_PARSED": gid_normalizer_flag[gid] = True
            # DURATION
            if n["duration_recommended"] is None and _ne(raw_dur):
                issues.append(_entry("DURATION_NOT_PARSED", gid, diagnosis, rid, quote, adata, f"raw duration={raw_dur!r}"))
                gid_normalizer_flag[gid] = True
            # ROUTE
            if (n["route"] or "unknown") == "unknown" and not _ne(raw_route):
                issues.append(_entry("ROUTE_NOT_EXTRACTED", gid, diagnosis, rid, quote, adata, f"raw route={raw_route!r}"))
        # DICTIONARY
        if "DRUG_UNKNOWN" in (n["validation_issues"] or ""):
            issues.append(_entry("DRUG_UNKNOWN", gid, diagnosis, rid, quote, adata,
                                 f"drug_original={n['drug_original']!r}"))

    # Guideline-level: extraction gap + duplicate title
    guidelines = set(str(r["clinrec_id"]) for r in ar.values())
    for gid in guidelines:
        c = clinrecs.get(gid)
        detected = [x for x in ((c["abx_drugs"].split(",") if c and c["abx_drugs"] else [])) if x.strip()]
        ex = extracted_drugs[gid]
        if len(detected) >= 3 and len(ex) * 2 <= len(detected):
            issues.append(_entry("EXTRACTION_GAP_CANDIDATE", gid, gid_diagnosis.get(gid, ""), None,
                                 "", {"drugs_detected_in_pdf": len(detected), "regimens_extracted_distinct_drugs": len(ex),
                                      "detected_examples": [d.strip() for d in detected[:12]]},
                                 f"PDF упоминает {len(detected)} препаратов, извлечено схем с {len(ex)} препаратами"))

    title_to_gids = defaultdict(set)
    for gid in guidelines:
        c = clinrecs.get(gid)
        if c and c["name"]:
            title_to_gids[c["name"].strip()].add(gid)
    for title, gids in title_to_gids.items():
        if len(gids) > 1:
            for gid in sorted(gids):
                issues.append(_entry("DUPLICATE_GUIDELINE_TITLE", gid, gid_diagnosis.get(gid, ""), None,
                                     "", {"title": title, "guideline_ids": sorted(gids)},
                                     f"КР '{title[:60]}' под guideline_ids {sorted(gids)}"))

    # PDF-confirmed enrichment for guideline 1638 (verified against source PDF)
    for it in issues:
        if it["guideline_id"] == "1638" and it["issue_code"] in ("DOSE_DAILY_MISREAD", "EXTRACTION_GAP_CANDIDATE"):
            it["verification"] = "pdf_confirmed"
            if it["issue_code"] == "DOSE_DAILY_MISREAD":
                it["severity"] = "High"
                it["description"] = ("КР Табл.1: амоксициллин 1,5 г/сут в 3 приёма ИЛИ 1,0 г/сут в 2 приёма; "
                                     "ANTIBIO нормализовал в 1,5 г × 2 = 3 г/сут (не совпадает ни с одним вариантом, 2× сут. дозы)")
            if it["issue_code"] == "EXTRACTION_GAP_CANDIDATE":
                it["description"] = "КР Табл.1 содержит ~14 пероральных схем (первая линия + альтернативы + при аллергии); извлечена только 1 (амоксициллин)"

    raw.close(); nd.close()

    # Golden Ready: has PASS, no normalizer flag, not extraction-gap
    gap_gids = {it["guideline_id"] for it in issues if it["issue_code"] == "EXTRACTION_GAP_CANDIDATE"}
    golden_ready = sorted(gid for gid in guidelines
                          if gid_has_pass[gid] and not gid_normalizer_flag[gid] and gid not in gap_gids)

    return {"issues": issues, "guidelines": sorted(guidelines), "golden_ready": golden_ready,
            "gid_has_pass": gid_has_pass, "gid_normalizer_flag": gid_normalizer_flag, "gap_gids": gap_gids}


def render_report(a) -> str:
    issues = a["issues"]
    by_code = Counter(it["issue_code"] for it in issues)
    by_type = Counter(it["problem_type"] for it in issues)
    by_sev = Counter(it["severity"] for it in issues)
    guidelines = a["guidelines"]
    gids_with_norm = {it["guideline_id"] for it in issues if it["problem_type"] == "Normalizer"}
    gids_with_extr = {it["guideline_id"] for it in issues if it["problem_type"] == "Extraction"}
    gids_with_dict = {it["guideline_id"] for it in issues if it["problem_type"] == "Dictionary"}

    def line(c): return f"| `{c}` | {_ISSUE_META[c][0]} | {_ISSUE_META[c][1]} | {by_code.get(c,0)} |"

    lines = [
        "# Clinical Data Quality Audit — отчёт",
        "",
        f"> Read-only. Ничего не изменено. Сгенерировано {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}.",
        f"> Источники: raw `antibiotic_regimens` (2675) ↔ `normalized_regimens` (2675) + `clinrecs.abx_drugs` (PDF-скан).",
        "> Атрибуция Extraction/Normalizer — по присутствию поля в сыром извлечении vs нормализованном. Все записи `pending_review`.",
        "",
        "## Методологическая оговорка",
        "- **PDF-подтверждено** только для guideline **1638** (сверено с исходной Табл.1 КР).",
        "- Остальные записи — **heuristic_flag** (сигналы из сохранённых данных/цитат), требуют выборочной сверки с PDF.",
        "- Полная построчная сверка КР↔ANTIBIO по каждому из 294 guideline (чтение всех PDF) — рекомендуемый следующий шаг.",
        "",
        "## 1. Готовность к Golden Cases",
        f"- Всего guideline: **{len(guidelines)}**",
        f"- **Golden-Ready (кандидаты)**: **{len(a['golden_ready'])}** — есть PASS-схема, нет normalizer-флагов, нет extraction-gap.",
        f"- Имеют ошибки **Extraction**: **{len(gids_with_extr)}** guideline",
        f"- Имеют ошибки **Normalizer**: **{len(gids_with_norm)}** guideline",
        f"- Имеют пробелы **Dictionary**: **{len(gids_with_dict)}** guideline",
        f"- Кандидаты на **ручную переэкстракцию** (extraction-gap): **{len(a['gap_gids'])}** guideline",
        "",
        "## 2. Всего записей в реестре по типам",
        "| Тип | Записей |", "|---|---:|",
        *[f"| {t} | {n} |" for t, n in by_type.most_common()],
        "",
        f"По критичности: " + ", ".join(f"{s}={by_sev.get(s,0)}" for s in ("Critical","High","Medium","Low")),
        "",
        "## 3. Частота проблем (issue_code)",
        "| issue_code | Тип | Критичность | Кол-во |", "|---|---|---|---:|",
        *[line(c) for c, _ in by_code.most_common()],
        "",
        "## 4. Какие исправления дадут максимальный прирост качества",
        f"1. **Расширить словарь (Dictionary)** → снимет `DRUG_UNKNOWN` у **{by_code.get('DRUG_UNKNOWN',0)}** схем (самый массовый, REVIEW→PASS).",
        f"2. **Парсер длительности (Normalizer)** → `DURATION_NOT_PARSED` у **{by_code.get('DURATION_NOT_PARSED',0)}** схем.",
        f"3. **Парсер суточной дозы (Normalizer, SAFETY)** → `DOSE_DAILY_MISREAD` у **{by_code.get('DOSE_DAILY_MISREAD',0)}** схем — приоритет по безопасности (риск 2× дозы).",
        f"4. **Обработка альтернативной дозы 'или'** → `DOSE_ALTERNATIVE_COLLAPSED` у **{by_code.get('DOSE_ALTERNATIVE_COLLAPSED',0)}** схем.",
        f"5. **Переэкстракция многорядных таблиц** → **{len(a['gap_gids'])}** guideline с потерянными схемами (в т.ч. альтернативы при аллергии — High).",
        "",
        "## 5. Самое важное (SAFETY-приоритет)",
        f"- `DOSE_DAILY_MISREAD` ({by_code.get('DOSE_DAILY_MISREAD',0)}) и `DOSE_NOT_PARSED` ({by_code.get('DOSE_NOT_PARSED',0)}) — прямое влияние на дозу. Разбирать первыми.",
        f"- `EXTRACTION_GAP_CANDIDATE` ({by_code.get('EXTRACTION_GAP_CANDIDATE',0)}) — отсутствие альтернатив (напр. для пациента с аллергией на пенициллины).",
        "",
        "## 6. Подтверждённый пример (guideline 1638 — PDF)",
        "- КР «Острый тонзиллит и фарингит» (306_3, «Действует»), Табл.1: первая линия — амоксициллин **1,5 г/сут в 3 приёма или 1,0 г/сут в 2 приёма**, 10 дней.",
        "- ANTIBIO: 1 схема, нормализована в **1,5 г × 2 = 3 г/сут** (Normalizer, High) + потеряно ~13 схем (Extraction, High).",
        "- Решение: Golden Case НЕ создавать; занесено в реестр.",
        "",
        "> Полный машиночитаемый реестр — `clinical_data_issues.json` (каждая запись со статусом `pending_review`).",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=_DEFAULT_RAW)
    ap.add_argument("--norm", default=_DEFAULT_NORM)
    ap.add_argument("--registry", default=_DEFAULT_REGISTRY)
    ap.add_argument("--report", default=_DEFAULT_REPORT)
    args = ap.parse_args()

    a = audit(args.raw, args.norm)
    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": "READ-ONLY audit. No data changed. All issues pending_review. "
                  "Nothing to be fixed until physician/pipeline decision.",
        "total_issues": len(a["issues"]),
        "total_guidelines": len(a["guidelines"]),
        "golden_ready_candidates": a["golden_ready"],
    }
    Path(args.registry).write_text(
        json.dumps({"meta": meta, "issues": a["issues"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    Path(args.report).write_text(render_report(a), encoding="utf-8")

    from collections import Counter as _C
    bc = _C(it["issue_code"] for it in a["issues"])
    print("=== Clinical Data Quality Audit (read-only) ===")
    print(f"guidelines: {len(a['guidelines'])} | golden-ready candidates: {len(a['golden_ready'])}")
    print(f"issues total: {len(a['issues'])}")
    for c, n in bc.most_common():
        print(f"  {c}: {n}")
    print(f"registry: {args.registry} | report: {args.report}")


if __name__ == "__main__":
    main()
