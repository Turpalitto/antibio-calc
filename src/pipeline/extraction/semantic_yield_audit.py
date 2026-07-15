#!/usr/bin/env python
"""
PR-008 — Production Semantic Yield Audit + Loss Classification.

PR-001 proved structured tables now REACH the semantic layer. This audit answers the harder
question the project owner requires: for every table-derived candidate, WHY is it lost — or
accepted — classified into exactly ONE reason, producing a ranked loss histogram that becomes
part of the permanent benchmark.

Instead of only "29 tables → 4 objects", this yields e.g.:

    tables → cells → candidate entities →
        Accepted / Duplicate / Deduplication / Knowledge Builder unsupported /
        Normalization failed / Validation failure / Confidence threshold /
        Unsupported entity type / Parser failure / Other

Each candidate gets exactly one terminal reason (first-loss-wins). The classifier mirrors the
real production decision points (cited inline) — it does not re-implement divergent logic:

  * Deduplication            → semantic.add_semantic_to_document merge `seen_keys` (semantic.py ~400)
  * Knowledge Builder unsupported → build_knowledge_objects if/elif has no else; drops
                                    AlternativeTherapy / FirstLineTherapy / AgeRestriction (~239-261)
  * Duplicate                → KnowledgeBase._content_key match on existing active (knowledge_base.py ~253)
  * Validation failure       → KnowledgeBase._validate_basic False (Medication needs name; Dose needs value/raw)
  * Confidence threshold     → NO active gate exists in production → expected 0 (documented, not assumed)
  * Normalization failed     → entity of a value-bearing type whose `normalized` is empty
  * Parser failure           → candidate malformed (missing type / build raised)
  * Accepted                 → inserted as active + valid with table provenance
  * Unsupported entity type  → type unknown to the whole taxonomy (distinct from KB-builder gap)
  * Other                    → fallthrough (should be ~0; presence signals a classifier gap)

Usage:
    python -m src.pipeline.extraction.semantic_yield_audit --sample
    python -m src.pipeline.extraction.semantic_yield_audit --pdfs "<p1>" "<p2>" --out pr008.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

# Reasons — ranked for the histogram legend (order is presentation only; each candidate still
# receives exactly one reason from the classifier below).
REASONS = [
    "Accepted",
    "Deduplication",
    "Knowledge Builder unsupported",
    "Duplicate",
    "Validation failure",
    "Normalization failed",
    "Confidence threshold",
    "Unsupported entity type",
    "Parser failure",
    "Other",
]

# Entity types build_knowledge_objects accepts (mirror of the if/elif chain).
_KB_BUILDER_TYPES = {
    "Drug", "Diagnosis", "Dose", "Frequency", "Duration", "Route",
    "Contraindication", "Pregnancy", "Breastfeeding", "RenalAdjustment",
    "EvidenceLevel", "StrengthOfRecommendation", "SourceReference",
}
# Types the semantic layer legitimately emits (taxonomy). Anything outside → "Unsupported entity type".
_KNOWN_TAXONOMY = _KB_BUILDER_TYPES | {"AlternativeTherapy", "FirstLineTherapy", "AgeRestriction"}
# Value-bearing types that require a normalized value to be usable downstream.
_VALUE_TYPES = {"Dose", "Frequency", "Duration", "Drug"}

# Entity type → Clinical Knowledge Yield dimension (see CLINICAL_KNOWLEDGE_YIELD.md).
_CKY_DIMENSION = {
    "Drug": "antibiotics",
    "Dose": "dose",
    "Duration": "duration",
    "Frequency": "frequency",
    "Route": "route",
    "AlternativeTherapy": "alternatives",
    "FirstLineTherapy": "first_line",
    "AgeRestriction": "pediatric",
    "Pregnancy": "pregnancy",
    "RenalAdjustment": "renal",
    "Contraindication": "contraindications",
    "EvidenceLevel": "evidence",
    "StrengthOfRecommendation": "evidence",
    "SourceReference": "evidence",
}

# Optional confidence gate — production currently has NONE. Kept configurable so the audit can
# report how many candidates a hypothetical gate would cost. Default 0.0 = no gate (matches prod).
CONFIDENCE_GATE = 0.0

SAMPLE_PDFS = [
    r"C:\clinrec_downloader\downloads_active\Сепсис новорождённых.pdf",
    r"C:\clinrec_downloader\downloads_active\Туберкулез у детей.pdf",
    r"C:\clinrec_downloader\archive_review\Неспецифический аортоартериит.pdf",
]


def _classify(entity: Dict, deduped: bool, kb_content_keys: set, kb_add) -> Tuple[str, set]:
    """Return (reason, updated_kb_content_keys) for one table-derived candidate.
    first-loss-wins order mirrors the production pipeline sequence."""
    # 1. Parser failure — malformed candidate
    etype = entity.get("type")
    if not etype:
        return "Parser failure", kb_content_keys

    # 2. Unsupported entity type — outside the whole taxonomy
    if etype not in _KNOWN_TAXONOMY:
        return "Unsupported entity type", kb_content_keys

    # 3. Confidence threshold (production gate is 0 → normally skipped)
    if CONFIDENCE_GATE > 0.0 and float(entity.get("confidence", 1.0)) < CONFIDENCE_GATE:
        return "Confidence threshold", kb_content_keys

    # 4. Deduplication — dropped at semantic merge vs flat text
    if deduped:
        return "Deduplication", kb_content_keys

    # 5. Knowledge Builder unsupported — type not handled by build_knowledge_objects
    if etype not in _KB_BUILDER_TYPES:
        return "Knowledge Builder unsupported", kb_content_keys

    # 6. Normalization failed — value-bearing type with empty normalized value
    if etype in _VALUE_TYPES and not (entity.get("normalized") or entity.get("text")):
        return "Normalization failed", kb_content_keys

    # 7. Map to KB object + content key (mirror build_knowledge_objects + _content_key)
    otype, content = kb_add(etype, entity)
    from src.pipeline.knowledge_base import _content_key
    key = _content_key(otype, content)
    if key in kb_content_keys:
        return "Duplicate", kb_content_keys
    kb_content_keys = kb_content_keys | {key}

    # 8. Validation (mirror _validate_basic)
    if otype == "Medication" and not content.get("name"):
        return "Validation failure", kb_content_keys
    if otype == "Dose" and not (content.get("value") or content.get("raw")):
        return "Validation failure", kb_content_keys

    return "Accepted", kb_content_keys


def _kb_map(etype: str, e: Dict) -> Tuple[str, Dict]:
    """Mirror build_knowledge_objects type→object mapping for accepted types."""
    base = {"raw": e.get("text"), "normalized": e.get("normalized"),
            "confidence": e.get("confidence", 0.7)}
    if etype == "Drug":
        return "Medication", {**base, "name": e.get("normalized") or e.get("text")}
    if etype == "Diagnosis":
        return "Diagnosis", {**base, "name": e.get("normalized") or e.get("text")}
    if etype in ("Dose", "Frequency", "Duration", "Route"):
        return "Dose", {**base, "value": e.get("normalized"), "unit": e.get("unit"), "subtype": etype}
    if etype in ("Contraindication", "Pregnancy", "Breastfeeding", "RenalAdjustment"):
        return "Contraindication", {**base, "condition": e.get("normalized") or e.get("text")}
    return "Evidence", {**base, "level": e.get("normalized")}


def audit_pdf(pdf_path: Path) -> Dict:
    from src.pipeline.extraction.router import ExtractorRouter
    from src.pipeline.extraction.layout import add_layout_to_document
    from src.pipeline.extraction.semantic import SemanticProcessor

    router = ExtractorRouter()
    doc = router.primary.extract(pdf_path)
    add_layout_to_document(doc, pdf_path)
    proc = SemanticProcessor()

    funnel = Counter()
    reasons = Counter()
    reason_by_type: Dict[str, Counter] = {}
    cky_total: Counter = Counter()      # candidates per CKY dimension (entity-type axis)
    cky_accepted: Counter = Counter()   # accepted per CKY dimension
    src_total: Counter = Counter()      # candidates per source axis (tables / free_text)
    src_accepted: Counter = Counter()
    kb_keys: set = set()

    def account(entity: Dict, reason: str, source: str):
        reasons[reason] += 1
        reason_by_type.setdefault(entity.get("type", "?"), Counter())[reason] += 1
        dim = _CKY_DIMENSION.get(entity.get("type"))
        if dim:
            cky_total[dim] += 1
            cky_total["overall"] += 1
            src_total[source] += 1
            if reason == "Accepted":
                cky_accepted[dim] += 1
                cky_accepted["overall"] += 1
                src_accepted[source] += 1

    for page in doc.pages:
        stabs = getattr(page, "structured_tables", None) or []
        funnel["structured_tables"] += len(stabs)
        for t in stabs:
            funnel["table_cells"] += len(getattr(t, "cells", []))

        # Free-text candidates first (production order: text entities populate the KB, then tables
        # dedup against them). These give CKY.free_text.
        text_ents = proc.extract_entities(page.text, getattr(page, "page_num", 0), "flat")
        funnel["free_text_candidates"] += len(text_ents)
        seen = {(e["type"], e.get("text", "")[:60].lower()) for e in text_ents}
        for e in text_ents:
            reason, kb_keys = _classify(e, False, kb_keys, _kb_map)
            account(e, reason, "free_text")

        # Table candidates (dedup vs the flat-text set) — CKY.tables.
        if stabs:
            candidates = proc.extract_entities_from_tables(stabs, getattr(page, "page_num", 0), "layout+table")
            funnel["table_candidates"] += len(candidates)
            for c in candidates:
                deduped = (c.get("type"), c.get("text", "")[:60].lower()) in seen
                reason, kb_keys = _classify(c, deduped, kb_keys, _kb_map)
                account(c, reason, "tables")

    cky = {d: {"candidates": cky_total[d], "accepted": cky_accepted[d],
               "cky_pct": round(100 * cky_accepted[d] / cky_total[d], 1) if cky_total[d] else None}
           for d in sorted(cky_total)}
    cky_by_source = {s: {"candidates": src_total[s], "accepted": src_accepted[s],
                         "cky_pct": round(100 * src_accepted[s] / src_total[s], 1) if src_total[s] else None}
                     for s in sorted(src_total)}

    return {
        "pdf": pdf_path.name,
        "funnel": dict(funnel),
        "loss_histogram": {r: reasons.get(r, 0) for r in REASONS if reasons.get(r, 0)},
        "reason_by_entity_type": {k: dict(v) for k, v in reason_by_type.items()},
        "cky": cky,
        "cky_by_source": cky_by_source,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", nargs="*", default=None)
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--out", default="pr008_yield_audit.json")
    args = ap.parse_args()

    pdfs = [Path(p) for p in (args.pdfs or (SAMPLE_PDFS if args.sample else []))]
    pdfs = [p for p in pdfs if p.exists()]
    if not pdfs:
        print("No PDFs to audit (use --sample or --pdfs). Missing files skipped.")
        return

    reports, agg_funnel, agg_reasons = [], Counter(), Counter()
    agg_cky_total, agg_cky_acc = Counter(), Counter()
    agg_src_total, agg_src_acc = Counter(), Counter()
    for p in pdfs:
        print(f"\n--- auditing {p.name} ---")
        r = audit_pdf(p)
        reports.append(r)
        agg_funnel.update(r["funnel"])
        agg_reasons.update(r["loss_histogram"])
        for d, v in r["cky"].items():
            agg_cky_total[d] += v["candidates"]
            agg_cky_acc[d] += v["accepted"]
        for s, v in r["cky_by_source"].items():
            agg_src_total[s] += v["candidates"]
            agg_src_acc[s] += v["accepted"]
        print("funnel:", json.dumps(r["funnel"], ensure_ascii=False))
        print("loss  :", json.dumps(r["loss_histogram"], ensure_ascii=False))

    total = sum(agg_reasons.values()) or 1
    ranked = sorted(agg_reasons.items(), key=lambda kv: kv[1], reverse=True)
    cky = {d: {"candidates": agg_cky_total[d], "accepted": agg_cky_acc[d],
               "cky_pct": round(100 * agg_cky_acc[d] / agg_cky_total[d], 1) if agg_cky_total[d] else None}
           for d in sorted(agg_cky_total)}
    cky_by_source = {s: {"candidates": agg_src_total[s], "accepted": agg_src_acc[s],
                         "cky_pct": round(100 * agg_src_acc[s] / agg_src_total[s], 1) if agg_src_total[s] else None}
                     for s in sorted(agg_src_total)}

    out = {
        "pdfs_audited": len(pdfs),
        "aggregate_funnel": dict(agg_funnel),
        "loss_histogram_ranked": [{"reason": k, "count": v, "pct": round(100 * v / total, 1)}
                                  for k, v in ranked],
        "clinical_knowledge_yield": cky,
        "cky_by_source": cky_by_source,
        "per_pdf": reports,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== PR-008 AGGREGATE FUNNEL ===")
    print(json.dumps(dict(agg_funnel), ensure_ascii=False, indent=2))
    print("\n=== RANKED LOSS HISTOGRAM (why every candidate is lost/accepted) ===")
    for k, v in ranked:
        bar = "#" * min(40, v * 40 // total)
        print(f"  {k:32s} {v:6d}  {100*v/total:5.1f}%  {bar}")
    print("\n=== CLINICAL KNOWLEDGE YIELD (CKY) ===")
    if "overall" in cky:
        o = cky["overall"]
        print(f"  CKY.overall = {o['cky_pct']}%  ({o['accepted']}/{o['candidates']})")
    for d in sorted(cky):
        if d == "overall":
            continue
        v = cky[d]
        print(f"    CKY.{d:20s} {str(v['cky_pct'])+'%':>7s}  ({v['accepted']}/{v['candidates']})")
    print("  -- by source --")
    for s in sorted(cky_by_source):
        v = cky_by_source[s]
        print(f"    CKY.{s:20s} {str(v['cky_pct'])+'%':>7s}  ({v['accepted']}/{v['candidates']})")
    print(f"\nReport: {args.out}")


if __name__ == "__main__":
    main()
