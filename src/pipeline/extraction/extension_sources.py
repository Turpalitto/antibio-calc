"""Classify unused klinrec (DOSA) guidelines as extension-source candidates.

This is a *source-prover* only. It inventories the klinrec guidelines in the
DOSA extraction that are NOT yet represented in the calculator database, and
subclassifies them by their regimen_type mix so the owner can see the real
expansion pool. It NEVER enables calculation, NEVER attests anything as
clinically approved, and never changes blocked state. The clinical gate
(P5.6 / P6) stays exclusively with the owner/physician.

Classification is based on the REGIMEN_TYPE ratio of each guideline's
regimens (not on naive keywords), because a keyword classifier proved
unreliable (it put onco/neutropenia entries into the therapeutic pool).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.pipeline.extraction.icd10 import mkb_prefix as _mkb_prefix
from src.pipeline.extraction.icd10 import normalize_mkb as _normalize_mkb

# Regimen-type ratio classes (derived from regimen_type, never keywords).
CLASS_THERAPEUTIC = "therapeutic"
CLASS_MIXED = "mixed"
CLASS_PRIMARILY_PROPHYLAXIS = "primarily_prophylaxis"

# MKB disambiguity classes for a candidate nosology.
DUP_SAME_DISEASE = "duplicate_same_disease_different_version"
NEW_NOSOLOGY = "new_nosology"


def classify_by_regimen_ratio(guideline: dict[str, Any]) -> str:
    """Classify one guideline by its regimen_type mix.

    Column counts are weighted by ''prophylaxis'' dominance:
      - no prophylaxis regimens at all        -> therapeutic
      - has prophylaxis, but >50% therapeutic  -> mixed
      - prophylaxis is the majority            -> primarily_prophylaxis
    """
    types = [str(r.get("regimen_type") or "") for r in guideline.get("regimens", [])]
    if not types:
        return CLASS_THERAPEUTIC
    counter = Counter(types)
    n = len(types)
    proph = counter.get("prophylaxis", 0)
    if proph == 0:
        return CLASS_THERAPEUTIC
    if proph / n >= 0.5:
        return CLASS_PRIMARILY_PROPHYLAXIS
    return CLASS_MIXED


def normalize_mkb(value: Any) -> list[str]:
    """Delegated to ``extraction.icd10`` (splits comma-joined code lists)."""
    return _normalize_mkb(value)


def mkb_prefix(code: str) -> str:
    """Return the 3-char MKB block prefix (e.g. 'A01', 'A69', 'C70')."""
    return _mkb_prefix(code)


def build_disease_mkb_index(diseases: list[dict[str, Any]]) -> dict[str, str]:
    """Our existing disease mkb10 codes -> owning disease id (for exact overlap)."""
    index: dict[str, str] = {}
    for d in diseases:
        for code in normalize_mkb(d.get("mkb10")):
            index.setdefault(code, str(d.get("id") or ""))
    return index


def build_extension_inventory(
    kb: list[dict[str, Any]],
    our_cr_ids: set[str],
    our_mkb_index: dict[str, str],
) -> dict[str, Any]:
    """Classify the GUIDELINES in kb that are not yet in our calculator.

    Returns the raw inventory with each guideline's class + overlap status.
    Overlap is decided by EXACT MKB code match against our diseases (a
    guideline is a duplicate when it literally codes one of our diseases).
    """
    used: list[dict[str, Any]] = []
    for g in kb:
        cv = str(g.get("code_version") or "")
        if cv in our_cr_ids:
            continue
        cls = classify_by_regimen_ratio(g)
        # Overlap by exact MKB code against our disease set.
        overlaps_ours: set[str] = set()
        for reg in g.get("regimens", []):
            for code in normalize_mkb(reg.get("mkb")):
                if code in our_mkb_index:
                    overlaps_ours.add(our_mkb_index[code])
        used.append(
            {
                "code_version": cv,
                "guideline_name": g.get("guideline_name"),
                "clinrec_id": g.get("clinrec_id"),
                "mkb": sorted({c for reg in g.get("regimens", []) for c in normalize_mkb(reg.get("mkb"))}),
                "regimen_count": len(g.get("regimens", [])),
                "regimen_types": dict(Counter(str(r.get("regimen_type") or "") for r in g.get("regimens", []))),
                "class": cls,
                "overlaps_our_disease": sorted(overlaps_ours),
                "provenance": {
                    "pdf_file": g.get("pdf_file"),
                    "pdf_sha256": g.get("pdf_sha256"),
                    "publication_date": g.get("publication_date"),
                    "extraction_model": g.get("extraction_model"),
                },
            }
        )
    return {"guidelines": used, "total": len(used)}


def flatten_nosologies(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Deduplicate the inventory into candidate nosologies.

    Two guidelines map to the SAME candidate nosology when they share an MKB
    block prefix that also overlaps one of OUR diseases (duplicate_same_disease
    _different_version) — else each guideline is a distinct new_nosology.
    This is the *source* of the expansion map, aggregated per guideline.
    """
    rows: list[dict[str, Any]] = []
    for g in inventory["guidelines"]:
        rows.append(
            {
                "code_version": g["code_version"],
                "guideline_name": g["guideline_name"],
                "class": g["class"],
                "mkb": g["mkb"],
                "regimen_count": g["regimen_count"],
                "regimen_types": g["regimen_types"],
                "cert_relation": DUP_SAME_DISEASE if g["overlaps_our_disease"] else NEW_NOSOLOGY,
                "overlaps_our_disease": g["overlaps_our_disease"],
            }
        )
    return rows


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(r["class"] for r in rows)
    dup = Counter(r["cert_relation"] for r in rows)
    # High-value expansion pool: pure-therapeutic AND truly new (no overlap).
    therapeutic_new = [
        r for r in rows
        if r["class"] == CLASS_THERAPEUTIC and r["cert_relation"] == NEW_NOSOLOGY
    ]
    therapeutic_dup = [
        r for r in rows
        if r["class"] == CLASS_THERAPEUTIC and r["cert_relation"] == DUP_SAME_DISEASE
    ]
    with_regimen_dose = [r for r in therapeutic_new if r["regimen_count"] > 0]
    return {
        "therapeutic": counter.get(CLASS_THERAPEUTIC, 0),
        "mixed": counter.get(CLASS_MIXED, 0),
        "primarily_prophylaxis": counter.get(CLASS_PRIMARILY_PROPHYLAXIS, 0),
        "duplicate_same_disease": dup.get(DUP_SAME_DISEASE, 0),
        "new_nosology": dup.get(NEW_NOSOLOGY, 0),
        "therapeutic_regimens_total": sum(r["regimen_count"] for r in rows if r["class"] == CLASS_THERAPEUTIC),
        "therapeutic_new_nosology_count": len(therapeutic_new),
        "therapeutic_new_regimens_total": sum(r["regimen_count"] for r in therapeutic_new),
        "therapeutic_dup_same_disease_count": len(therapeutic_dup),
        "therapeutic_new_with_regimens_count": len(with_regimen_dose),
    }


def build_extension_artifact(
    db_path: Path,
    kb_path: Path,
    created: str,
) -> dict[str, Any]:
    db = json.loads(db_path.read_text(encoding="utf-8-sig"))
    diseases = db.get("recommendations", db if isinstance(db, list) else [])
    our_cr_ids = {str(d.get("cr_id") or "") for d in diseases if d.get("cr_id")}
    our_mkb_index = build_disease_mkb_index(diseases)
    kb = json.loads(kb_path.read_text(encoding="utf-8-sig"))
    inventory = build_extension_inventory(kb, our_cr_ids, our_mkb_index)
    rows = flatten_nosologies(inventory)
    summary = build_summary(rows)
    return {
        "schema_version": "1.0.0",
        "artifact_type": "DOSA_EXTENSION_SOURCES",
        "created": created,
        "source": "dosA clinic-recommendation extraction (knowledge_base.json)",
        "scope_note": (
            "Only guidelines with antibiotics, not yet in the calculator, "
            "classified by regimen_type ratio (NOT keywords). This is a source "
            "prover — it never enables calculation or attests clinical approval."
        ),
        "our_disease_count": len(diseases),
        "our_cr_id_count": len(our_cr_ids),
        "inventory": inventory,
        "candidates": rows,
        "summary": summary,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extension_sources",
        description="Classify unused DOSA klinrec guidelines as extension-source candidates.",
    )
    parser.add_argument("--db", required=True, help="Path to db/antibio_db.json")
    parser.add_argument("--kb", required=True, help="Path to DOSA knowledge_base.json")
    parser.add_argument("--output", required=True, help="Path to write the artifact JSON")
    parser.add_argument("--created", default="2026-09-02", help="Creation timestamp string")
    args = parser.parse_args(argv)

    artifact = build_extension_artifact(Path(args.db), Path(args.kb), args.created)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"artifact_type": artifact["artifact_type"], "summary": artifact["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
