"""Map calculator diseases to klinrec (DOSA) source-layer evidence contracts.

This is a *source prover* only. It does NOT enable calculation, does NOT
attest anything as clinically approved, and never changes the blocked state.
For every calculator disease it tries to anchor the declared CR (by
code_version), or to recover a CR by MKB overlap or by name-keyword matching,
then records the DOSA extraction evidence (pdf_sha256, page, source_quote,
dose) as provenance. The clinical gate (P5.6 / P6) remains exclusively with
the owner/physician.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Sequence

MATCH_BY_CR_ID = "EXACT_CR_ID"
MATCH_BY_MKB = "MKB_OVERLAP"
MATCH_BY_NAME = "NAME_KEYWORD"
NO_MATCH = "NO_MATCH"


def normalize_mkb(value: Any) -> list[str]:
    if value is None:
        return []
    codes = value if isinstance(value, list) else [value]
    return [str(c).strip().upper() for c in codes if c is not None and str(c).strip()]


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"[^а-яёa-z0-9]+", text.lower()) if len(t) >= 4]


def _name_score(needle: str, haystack: str) -> int:
    toks = _tokenize(needle)
    if not toks:
        return 0
    hs = haystack.lower()
    return sum(1 for t in toks if t in hs)


def build_dosa_index(kb: list[dict[str, Any]]) -> dict[str, Any]:
    by_cv: dict[str, dict[str, Any]] = {}
    by_mkb: dict[str, set[str]] = {}
    for g in kb:
        cv = str(g.get("code_version") or "")
        if cv:
            by_cv[cv] = g
        for reg in g.get("regimens", []):
            for code in normalize_mkb(reg.get("mkb")):
                by_mkb.setdefault(code, set()).add(cv)
    return {"by_code_version": by_cv, "by_mkb": by_mkb, "kb": kb}


def match_disease_to_dosa(disease: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    cr_id = str(disease.get("cr_id") or "")
    mkb_codes = normalize_mkb(disease.get("mkb10"))
    kb = index["kb"]

    if cr_id and cr_id not in ("—", "-") and cr_id in index["by_code_version"]:
        g = index["by_code_version"][cr_id]
        return {"basis": MATCH_BY_CR_ID, "guideline": g}

    mkb_hits: set[str] = set()
    for code in mkb_codes:
        mkb_hits |= index["by_mkb"].get(code, set())
    mkb_hits.discard("")
    if mkb_hits:
        # prefer the one with the most regimen evidence
        best = max(mkb_hits, key=lambda cv: len(index["by_code_version"][cv].get("regimens", [])))
        return {"basis": MATCH_BY_MKB, "guideline": index["by_code_version"][best]}

    name = disease.get("name") or ""
    best_name: tuple[int, dict[str, Any]] | None = None
    for g in kb:
        score = _name_score(name, g.get("guideline_name") or "")
        if score >= 2 and (best_name is None or score > best_name[0]):
            best_name = (score, g)
    if best_name:
        return {"basis": MATCH_BY_NAME, "guideline": best_name[1]}

    return {"basis": NO_MATCH, "guideline": None}


def _evidence_rows(guideline: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for reg in guideline.get("regimens", []):
        rows.append({
            "antibiotic": reg.get("antibiotic"),
            "dose": reg.get("dose"),
            "unit": reg.get("unit"),
            "frequency": reg.get("frequency"),
            "route": reg.get("route"),
            "duration": reg.get("duration"),
            "age_group": reg.get("age_group"),
            "page_number": reg.get("page_number"),
            "section_name": reg.get("section_name"),
            "source_quote": reg.get("source_quote"),
        })
    return rows


def build_source_contract(db_path: str | Path, kb_path: str | Path) -> dict[str, Any]:
    db = json.loads(Path(db_path).read_text(encoding="utf-8-sig"))
    kb = json.loads(Path(kb_path).read_text(encoding="utf-8"))
    index = build_dosa_index(kb)

    rows: list[dict[str, Any]] = []
    for disease in db.get("recommendations", []):
        match = match_disease_to_dosa(disease, index)
        g = match["guideline"]
        rows.append({
            "disease_id": disease.get("id"),
            "name": disease.get("name"),
            "mkb10": disease.get("mkb10"),
            "declared_cr_id": disease.get("cr_id"),
            "cr_year": disease.get("cr_year"),
            "calculation_blocked": bool(disease.get("calculation_blocked")),
            "match_basis": match["basis"],
            "guideline": None if g is None else {
                "code_version": g.get("code_version"),
                "guideline_name": g.get("guideline_name"),
                "clinrec_id": g.get("clinrec_id"),
                "pdf_file": g.get("pdf_file"),
                "pdf_sha256": g.get("pdf_sha256"),
                "publication_date": g.get("publication_date"),
                "extraction_model": g.get("extraction_model"),
            },
            "evidence_count": 0 if g is None else len(g.get("regimens", [])),
            "evidence": [] if g is None else _evidence_rows(g),
        })

    counts = {"total": len(rows), MATCH_BY_CR_ID: 0, MATCH_BY_MKB: 0, MATCH_BY_NAME: 0, NO_MATCH: 0}
    for r in rows:
        counts[r["match_basis"]] += 1

    return {
        "schema_version": "1.0.0",
        "artifact_type": "DOSA_SOURCE_LAYER_CONTRACTS",
        "disease_count": counts["total"],
        "matched_count": counts[MATCH_BY_CR_ID] + counts[MATCH_BY_MKB] + counts[MATCH_BY_NAME],
        "match_breakdown": {
            "exact_cr_id": counts[MATCH_BY_CR_ID],
            "mkb_overlap": counts[MATCH_BY_MKB],
            "name_keyword": counts[MATCH_BY_NAME],
            "no_match": counts[NO_MATCH],
        },
        "rows": rows,
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to db/antibio_db.json")
    parser.add_argument("--kb", required=True, help="path to clinrec-downloader knowledge_base.json")
    parser.add_argument("--output", required=True, help="path to write the contract artifact")
    parser.add_argument("--ident", default="2", help="json indentation")
    args = parser.parse_args(argv)

    report = build_source_contract(args.db, args.kb)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=int(args.ident)), encoding="utf-8")
    print(json.dumps({
        "disease_count": report["disease_count"],
        "matched_count": report["matched_count"],
        "match_breakdown": report["match_breakdown"],
    }, ensure_ascii=False, indent=int(args.ident)))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
