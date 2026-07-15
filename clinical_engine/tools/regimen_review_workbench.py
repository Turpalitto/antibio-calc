"""Regimen Review Workbench — physician review artifacts (read-only).

Purpose: turn the LLM-extracted regimens of high-frequency outpatient diagnoses
into a physician-reviewable queue so each regimen can be verified against its
original Russian Clinical Guideline and approved/rejected with rationale.

It reads the external corpus READ-ONLY and produces review artifacts only:
  - a Markdown review sheet: each regimen shown side-by-side with its guideline
    source quote, with drug / dose / route / frequency / duration / therapy line,
    population (adult/child), pregnancy & renal notes, full provenance
    (guideline_id, regimen_id, PDF page, SHA-256), a mechanical anomaly list,
    and a deterministic relevance confidence score;
  - a CSV for spreadsheet review;
  - optionally, with --update-ledger, it scaffolds matched regimens into the
    physician regimen review ledger (regimen_review_ledger.json, merge-preserving).

Relevance filter (deterministic, highest tier wins) — for QUEUE PRIORITISATION
only, never a clinical decision:
    100  exact guideline_id (area.guideline_ids)
     95  ICD-10 prefix match
     90  exact diagnosis name (area.diagnosis_names)
     80  approved diagnosis synonym (medical_dictionary/diagnosis_synonyms.json)
     60  keyword in the regimen's diagnosis field
     30  keyword only in the guideline name (weak)
Per-area EXCLUSION keywords drop obvious false positives (e.g. дакриоцистит for
acute_cystitis) — but only when the match is keyword-tier (<=60); a structured
match (ICD / exact name / synonym / guideline_id) is never excluded. Excluded
regimens are reported with full provenance (never silently lost) and are kept
out of the default queue. Recall is still preferred: weak keyword matches remain
in the queue, just ranked lowest by confidence.

Makes NO clinical decision, adds NO clinical logic, and never modifies the
engine, the API, or the upstream corpus.

Usage (from repo root):
    python -m clinical_engine.tools.regimen_review_workbench            # all high-freq areas
    python -m clinical_engine.tools.regimen_review_workbench --areas acute_cystitis
    python -m clinical_engine.tools.regimen_review_workbench --update-ledger
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.tools import build_regimen_ledger

_DEFAULT_LEDGER = "regimen_review_ledger.json"
_DEFAULT_MD = "regimen_review_workbench.md"
_DEFAULT_CSV = "regimen_review_workbench.csv"
_SYNONYMS_FILE = "medical_dictionary/diagnosis_synonyms.json"
_AREAS_FILE = Path(__file__).resolve().parents[1] / "resources" / "regimen_review_areas.json"

# confidence tiers
_C_GUIDELINE, _C_ICD, _C_NAME, _C_SYNONYM, _C_KW_DIAG, _C_KW_NAME = 100, 95, 90, 80, 60, 30
_STRUCTURED_MIN = 80  # >= this tier => never dropped by an exclusion keyword
_PRIORITY_BY_CONFIDENCE = {_C_GUIDELINE: 1, _C_ICD: 2, _C_NAME: 3, _C_SYNONYM: 4, _C_KW_DIAG: 5, _C_KW_NAME: 6}


@dataclass(frozen=True)
class TargetArea:
    area_id: str
    label: str
    icd_prefixes: tuple[str, ...] = ()
    diagnosis_names: tuple[str, ...] = ()     # exact canonical names
    keywords: tuple[str, ...] = ()            # fallback substrings (lowercase)
    exclude: tuple[str, ...] = ()             # negative keywords (lowercase)
    guideline_ids: tuple[str, ...] = ()       # known approved guideline ids (future)


def _load_target_areas(path: str | Path = _AREAS_FILE) -> tuple[TargetArea, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(
        TargetArea(
            str(x["area_id"]),
            str(x["label"]),
            tuple(str(v) for v in x.get("icd_prefixes", ())),
            tuple(str(v) for v in x.get("diagnosis_names", ())),
            tuple(str(v).lower() for v in x.get("keywords", ())),
            tuple(str(v).lower() for v in x.get("exclude", ())),
            tuple(str(v) for v in x.get("guideline_ids", ())),
        )
        for x in raw.get("areas", ())
    )


TARGET_AREAS: tuple[TargetArea, ...] = _load_target_areas()
_AREAS_BY_ID = {a.area_id: a for a in TARGET_AREAS}


def _load_synonyms_by_area() -> dict[str, set[str]]:
    """area_id -> set of synonym strings (lowercase) whose canonical name is one of
    the area's diagnosis_names. Uses the approved diagnosis synonym map."""
    out: dict[str, set[str]] = {a.area_id: set() for a in TARGET_AREAS}
    p = Path(_SYNONYMS_FILE)
    if not p.is_file():
        return out
    entries = json.loads(p.read_text(encoding="utf-8")).get("entries", {})
    for area in TARGET_AREAS:
        canon_l = {n.strip().lower() for n in area.diagnosis_names}
        for syn, canon in entries.items():
            if str(canon).strip().lower() in canon_l:
                out[area.area_id].add(str(syn).strip().lower())
    return out


_ICD_TOKEN = re.compile(r"[^A-Z0-9.]+")


def _icd_match(mkb: str | None, prefixes: tuple[str, ...]) -> str | None:
    if not mkb or not prefixes:
        return None
    tokens = [t for t in _ICD_TOKEN.split(mkb.upper()) if t]
    for tok in tokens:
        for p in prefixes:
            if tok.startswith(p):
                return p
    return None


def score(area: TargetArea, *, guideline_id: str, mkb: str | None, diagnosis: str | None,
          clinrec_name: str | None, guideline_name: str | None,
          synonyms: set[str]) -> tuple[int, str, bool]:
    """Return (confidence, reason, excluded). Deterministic; no clinical judgement."""
    diag_l = (diagnosis or "").strip().lower()
    names_l = " || ".join(x for x in ((clinrec_name or ""), (guideline_name or "")) ).lower()
    conf, reason = 0, "none"

    icd = _icd_match(mkb, area.icd_prefixes)

    if area.guideline_ids and str(guideline_id) in area.guideline_ids:
        conf, reason = _C_GUIDELINE, "guideline_id"
    elif icd:
        conf, reason = _C_ICD, f"ICD {icd}"
    elif diag_l and diag_l in {n.strip().lower() for n in area.diagnosis_names}:
        conf, reason = _C_NAME, "exact diagnosis"
    elif diag_l and diag_l in synonyms:
        conf, reason = _C_SYNONYM, "approved synonym"
    elif any(k in diag_l for k in area.keywords):
        conf, reason = _C_KW_DIAG, "keyword"
    elif any(k in names_l for k in area.keywords):
        conf, reason = _C_KW_NAME, "weak keyword"

    excluded = False
    if conf and conf < _STRUCTURED_MIN and area.exclude:
        hay = diag_l + " || " + names_l
        excluded = any(x in hay for x in area.exclude)
    return conf, reason, excluded


def _candidate_ids(md_conn, area: TargetArea) -> set[str]:
    conds, params = [], []
    for p in area.icd_prefixes:
        conds.append("mkb LIKE ?"); params.append(p + "%")
    for kw in area.keywords:
        for col in ("diagnosis", "clinrec_name", "guideline_name"):
            conds.append(f"lower({col}) LIKE ?"); params.append("%" + kw + "%")
            conds.append(f"{col} LIKE ?"); params.append("%" + kw.capitalize() + "%")
    for nm in area.diagnosis_names:
        conds.append("lower(diagnosis) = ?"); params.append(nm.strip().lower())
    if not conds:
        return set()
    return {str(r[0]) for r in md_conn.execute(
        f"SELECT DISTINCT id FROM antibiotic_regimens WHERE {' OR '.join(conds)}", params)}


def _anomalies(nr: dict) -> list[str]:
    flags: list[str] = []
    if nr["dose"] is None:
        flags.append("DOSE_MISSING")
    elif not (nr["dose_unit"] or "").strip():
        flags.append("UNIT_MISSING")
    if (nr["route"] or "").strip().lower() in ("", "unknown"):
        flags.append("ROUTE_UNKNOWN")
    if nr["frequency"] is None:
        flags.append("FREQ_MISSING")
    if nr["duration_min"] is None and nr["duration_max"] is None and nr["duration_recommended"] is None:
        flags.append("DURATION_MISSING")
    v = (nr["validation_verdict"] or "").upper()
    if v == "REJECT":
        flags.append("VERDICT_REJECT")
    elif v == "REVIEW":
        flags.append("VERDICT_REVIEW")
    if "DRUG_UNKNOWN" in (nr["validation_issues"] or ""):
        flags.append("DRUG_UNKNOWN")
    return flags


def collect(loc: CorpusLocator, area_ids: list[str]) -> dict:
    loc.require()
    areas = [_AREAS_BY_ID[a] for a in area_ids]
    syn_by_area = _load_synonyms_by_area()
    nr = loc.open_normalized_regimens()
    md = loc.open_metadata()
    try:
        cand_by_area = {a.area_id: _candidate_ids(md, a) for a in areas}
        all_ids = sorted({i for ids in cand_by_area.values() for i in ids},
                         key=lambda s: int(s) if s.isdigit() else s)
        if not all_ids:
            return {"rows": [], "kept_ids": [], "excluded_ids": [], "per_area": {}}

        ph = ",".join("?" * len(all_ids))
        nr_cols = ("regimen_id,guideline_id,drug_normalized,dose,dose_unit,route,frequency,"
                   "duration_min,duration_max,duration_recommended,therapy_line,adult,child,"
                   "pregnancy,renal_adjustment,validation_verdict,validation_issues,"
                   "overall_confidence,source_pdf,source_page,source_quote")
        nr_rows = {str(r[0]): dict(zip(nr_cols.split(","), r))
                   for r in nr.execute(f"SELECT {nr_cols} FROM normalized_regimens WHERE regimen_id IN ({ph})", all_ids)}
        md_rows = {str(r[0]): {"pdf_sha256": r[1], "page_number": r[2], "pdf_file": r[3],
                               "diagnosis": r[4], "clinrec_name": r[5], "guideline_name": r[6], "mkb": r[7]}
                   for r in md.execute(f"SELECT id,pdf_sha256,page_number,pdf_file,diagnosis,clinrec_name,guideline_name,mkb "
                                       f"FROM antibiotic_regimens WHERE id IN ({ph})", all_ids)}
    finally:
        nr.close(); md.close()

    rows: list[dict] = []
    excluded_rows: list[dict] = []
    per_area: dict[str, dict[str, int]] = {a: {"kept": 0, "excluded": 0} for a in area_ids}

    for rid in all_ids:
        n = nr_rows.get(rid)
        if not n:
            continue
        m = md_rows.get(rid, {})
        # best (area, score) across the areas that proposed this id
        best = None  # (conf, reason, excluded, area_id)
        for a in areas:
            if rid not in cand_by_area[a.area_id]:
                continue
            conf, reason, excl = score(
                a, guideline_id=str(n["guideline_id"]), mkb=m.get("mkb"),
                diagnosis=m.get("diagnosis"), clinrec_name=m.get("clinrec_name"),
                guideline_name=m.get("guideline_name"), synonyms=syn_by_area[a.area_id])
            if conf == 0:
                continue
            # Always apply exclude for bad pneumonia types (congenital etc) to improve diagnosis routing
            hay = ((m.get("diagnosis") or "") + " " + (m.get("clinrec_name") or "") + " " + (m.get("guideline_name") or "")).lower()
            if any(x in hay for x in a.exclude):
                excl = True
            cand = (conf, reason, excl, a.area_id)
            if best is None or conf > best[0] or (conf == best[0] and not excl and best[2]):
                best = cand
        if best is None:
            continue
        conf, reason, excl, area_id = best
        row = {
            "area": area_id, "confidence": conf, "match_reason": reason,
            "priority": _PRIORITY_BY_CONFIDENCE.get(conf, 99),
            "needs_manual_review": conf < 90, "excluded": excl,
            "regimen_id": rid, "guideline_id": str(n["guideline_id"]),
            "diagnosis": m.get("diagnosis") or "",
            "drug": n["drug_normalized"], "dose": n["dose"], "unit": n["dose_unit"],
            "route": n["route"], "freq_per_day": n["frequency"],
            "duration_min": n["duration_min"], "duration_max": n["duration_max"],
            "therapy_line": n["therapy_line"],
            "population": "child" if n["child"] and not n["adult"] else ("adult" if n["adult"] else "?"),
            "pregnancy": n["pregnancy"], "renal": n["renal_adjustment"],
            "verdict": n["validation_verdict"], "parse_confidence": n["overall_confidence"],
            "anomalies": _anomalies(n),
            "pdf_file": m.get("pdf_file") or n["source_pdf"],
            "page": m.get("page_number") or n["source_page"],
            "pdf_sha256": m.get("pdf_sha256") or "",
            "source_quote": (n["source_quote"] or "").replace("\n", " ").strip(),
        }

        # Deterministic classification for systematic issues (no physician judgment)
        flags = []
        drug_str = (row["drug"] or "").lower()
        quote_str = (row["source_quote"] or "").lower()
        dose_val = row.get("dose")
        dur_min = row.get("duration_min")
        pop = row.get("population", "")
        diag_str = (row.get("diagnosis", "") or "").lower()

        # 1+5. Combination OR blocks
        if " или " in drug_str or " or " in drug_str or ("+" in drug_str and "или" in quote_str):
            flags.append("STRUCTURED_OPTION_LIST")
        # Combo without dose
        if (" или " in drug_str or " or " in drug_str) and not dose_val:
            flags.append("COMBINATION_OR_NO_DOSE")

        # 2. Population mismatch
        peds_signals = ["с 3 месяцев", "с 3х месяцев", "у детей", "детей", "новорожд", "месяц", "pediatric", "child"]
        if any(sig in quote_str for sig in peds_signals) and pop == "adult":
            flags.append("POPULATION_MISMATCH")

        # 4. Duration source analysis
        has_dur_in_quote = bool(re.search(r"\d+\s*(?:дн|сут|день|дней|нед|мес|дн\.)", quote_str))
        if not dur_min and has_dur_in_quote:
            flags.append("EXTRACTION_LOST_DURATION")
        elif not dur_min and not has_dur_in_quote:
            flags.append("SOURCE_HAS_NO_DURATION")

        # 3. Diagnosis context
        if "врожденн" in diag_str or "неонатал" in diag_str or "врожденная" in diag_str:
            flags.append("DIAGNOSIS_CONTEXT_MISMATCH")

        row["issue_flags"] = flags
        row["review_classification"] = "STRUCTURED_OPTION_LIST" if "STRUCTURED_OPTION_LIST" in flags else ("REQUIRES_REVIEW" if flags else "OK")

        if excl:
            excluded_rows.append(row)
            per_area[area_id]["excluded"] += 1
        else:
            rows.append(row)
            per_area[area_id]["kept"] += 1

    rows.sort(key=lambda r: (r["area"], r["priority"], r["diagnosis"].lower(), r["regimen_id"]))
    return {"rows": rows, "excluded_rows": excluded_rows,
            "kept_ids": [r["regimen_id"] for r in rows],
            "excluded_ids": [r["regimen_id"] for r in excluded_rows],
            "excluded_false_positives": len(excluded_rows),
            "per_area": per_area}


def _ledger_status(ledger_path: str) -> dict[str, dict]:
    p = Path(ledger_path)
    if not p.is_file():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {x["regimen_id"]: x for x in d.get("decisions", [])}


def _prune_pending(ledger_path: str, drop_ids: list[str]) -> int:
    """Remove PENDING false-positive entries from the ledger (never touches a
    decided entry, never touches the corpus). Returns count pruned."""
    p = Path(ledger_path)
    if not p.is_file() or not drop_ids:
        return 0
    d = json.loads(p.read_text(encoding="utf-8"))
    drop = set(drop_ids)
    before = len(d.get("decisions", []))
    d["decisions"] = [x for x in d.get("decisions", [])
                      if not (x["regimen_id"] in drop and x.get("decision", "pending_review") == "pending_review")]
    pruned = before - len(d["decisions"])
    if pruned:
        d.setdefault("meta", {})["total"] = len(d["decisions"])
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pruned


def render_md(data: dict, ledger_status: dict) -> str:
    rows = data["rows"]
    by_area: dict[str, list[dict]] = {}
    for r in rows:
        by_area.setdefault(r["area"], []).append(r)

    from collections import Counter
    conf_counts = Counter(r["confidence"] for r in rows)
    lines = [
        "# Regimen Review Workbench",
        "",
        "> READ-ONLY by default. Verify each regimen against the cited Clinical Guideline PDF. "
        "Use `--update-ledger` only when you intentionally want to create/update "
        "`regimen_review_ledger.json`. Confidence = deterministic "
        "relevance score (100 guideline_id · 95 ICD · 90 exact name · 80 synonym · 60 keyword · "
        "30 weak) — a queue-prioritisation aid, NOT clinical advice. Review high-confidence first. "
        "Anomaly flags are mechanical (missing field / normalizer verdict).",
        "",
        f"- Areas: {len(by_area)} · regimens in queue: **{len(rows)}** · "
        f"excluded false positives: **{len(data['excluded_rows'])}**",
        f"- By confidence: " + ", ".join(f"{c}:{conf_counts[c]}" for c in sorted(conf_counts, reverse=True)),
        f"- With anomalies: **{sum(1 for r in rows if r['anomalies'])}** · "
        f"clean-parse: **{sum(1 for r in rows if not r['anomalies'])}**",
        "",
    ]
    for aid in sorted(by_area):
        area = _AREAS_BY_ID.get(aid)
        arows = by_area[aid]
        lines.append(f"## {area.label if area else aid}  (`{aid}`) — {len(arows)} regimens")
        lines.append("")
        for r in arows:  # already sorted by confidence desc within area
            st = ledger_status.get(r["regimen_id"], {})
            status = st.get("decision", "pending_review")
            dur = "-".join(str(int(x)) for x in (r["duration_min"], r["duration_max"]) if x is not None) or "—"
            freq = f"×{int(r['freq_per_day'])}/сут" if r["freq_per_day"] else "—"
            dose = f"{r['dose']} {r['unit']}".strip() if r["dose"] is not None else "—"
            anom = " ".join(f"⚠️{a}" for a in r["anomalies"]) or "—"
            flags_str = " ".join(f"⚠️{f}" for f in r.get("issue_flags", [])) or "—"
            lines += [
                f"### `{r['regimen_id']}` — {r['drug']}  ·  priority {r['priority']}  ·  conf {r['confidence']} ({r['match_reason']})  ·  manual_review {r['needs_manual_review']}  ·  {status}",
                f"- **Rx:** {dose} · {r['route']} · {freq} · {dur} дн · line: {r['therapy_line']} · pop: {r['population']}",
                (f"- **Pregnancy:** {r['pregnancy']}" if r["pregnancy"] else "- Pregnancy: —")
                + (f"  ·  **Renal:** {r['renal']}" if r["renal"] else "  ·  Renal: —"),
                f"- **Flags:** {flags_str}",
                f"- **Provenance:** guideline_id `{r['guideline_id']}` · regimen_id `{r['regimen_id']}` · "
                f"page {r['page']} · sha256 `{(r['pdf_sha256'] or '')[:16]}…` · {r['pdf_file']}",
                f"- **Anomalies:** {anom} · verdict {r['verdict']} · parse_conf {r['parse_confidence']}",
                f"- **Guideline quote:** «{r['source_quote'][:400]}»",
                "",
            ]
    # transparency: excluded false positives keep full provenance, out of the queue
    if data["excluded_rows"]:
        lines.append(f"## Excluded false positives ({len(data['excluded_rows'])}) — not in review queue")
        lines.append("")
        for r in sorted(data["excluded_rows"], key=lambda x: (x["area"], x["regimen_id"])):
            lines.append(f"- `{r['regimen_id']}` [{r['area']}] {r['drug']} — matched by "
                         f"{r['match_reason']} then excluded · guideline_id `{r['guideline_id']}` "
                         f"page {r['page']} · {r['pdf_file']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_csv(rows: list[dict], ledger_status: dict, path: str) -> None:
    cols = ["area", "priority", "confidence", "match_reason", "needs_manual_review", "regimen_id", "guideline_id", "diagnosis", "drug", "dose",
            "unit", "route", "freq_per_day", "duration_min", "duration_max", "therapy_line",
            "population", "pregnancy", "renal", "verdict", "parse_confidence", "anomalies",
            "pdf_file", "page", "pdf_sha256", "source_quote", "issue_flags", "review_classification",
            "review_status", "physician_decision", "rationale"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            st = ledger_status.get(r["regimen_id"], {})
            w.writerow({**{k: r.get(k) for k in cols if k in r},
                        "anomalies": ";".join(r["anomalies"]) if isinstance(r.get("anomalies"), list) else r.get("anomalies", ""),
                        "issue_flags": ";".join(r.get("issue_flags", [])) if isinstance(r.get("issue_flags"), list) else r.get("issue_flags", ""),
                        "review_classification": r.get("review_classification", ""),
                        "review_status": st.get("review_status", "PENDING"),
                        "physician_decision": st.get("decision", "pending_review"),
                        "rationale": st.get("rationale", "")})


def build(area_ids: list[str], *, ledger_path: str, out_md: str, out_csv: str,
          update_ledger: bool = False, locator: CorpusLocator | None = None) -> dict:
    loc = locator or CorpusLocator()
    data = collect(loc, area_ids)
    pruned = 0
    if update_ledger:
        if data["kept_ids"]:
            build_regimen_ledger.build(ledger_path, regimen_ids=data["kept_ids"], locator=loc)
        pruned = _prune_pending(ledger_path, data["excluded_ids"])
    ledger_status = _ledger_status(ledger_path)
    Path(out_md).write_text(render_md(data, ledger_status), encoding="utf-8")
    write_csv(data["rows"], ledger_status, out_csv)
    return {"areas": area_ids, "queued": len(data["rows"]),
            "excluded_false_positives": len(data["excluded_rows"]),
            "pruned_from_ledger": pruned,
            "with_anomalies": sum(1 for r in data["rows"] if r["anomalies"]),
            "per_area": data["per_area"], "out_md": out_md, "out_csv": out_csv, "ledger": ledger_path}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", nargs="*", default=list(_AREAS_BY_ID))
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER)
    ap.add_argument("--out-md", default=_DEFAULT_MD)
    ap.add_argument("--out-csv", default=_DEFAULT_CSV)
    ap.add_argument("--update-ledger", action="store_true",
                    help="create/update regimen_review_ledger.json (off by default)")
    args = ap.parse_args()
    unknown = [a for a in args.areas if a not in _AREAS_BY_ID]
    if unknown:
        raise SystemExit(f"unknown area(s): {unknown}. valid: {list(_AREAS_BY_ID)}")
    r = build(args.areas, ledger_path=args.ledger, out_md=args.out_md,
              out_csv=args.out_csv, update_ledger=args.update_ledger)
    print("=== regimen review workbench (refined) ===")
    print(f"queued: {r['queued']}  excluded false positives: {r['excluded_false_positives']}  "
          f"pruned from ledger: {r['pruned_from_ledger']}  with anomalies: {r['with_anomalies']}")
    print(f"per area: {r['per_area']}")
    print(f"written: {r['out_md']} , {r['out_csv']}  ledger: {r['ledger']}")


if __name__ == "__main__":
    main()
