#!/usr/bin/env python
"""
P4.5 Production Layout Reprocessing Script
Reprocesses the full contributing corpus with the new Layout Intelligence pipeline.
Records quantitative metrics for BEFORE / AFTER comparison.

The layout step is expensive on CPU. The underlying LayoutProcessor now skips
low-signal pages for practicality.

Usage (recommended for full):
  python reprocess_p45_layout.py --limit 0   # 0 or omit for all 193 (long running)
  python reprocess_p45_layout.py --limit 20 --out p45_reprocess_report.json
"""

import json
import time
import glob
from pathlib import Path
from collections import Counter, defaultdict
import sys

# project
sys.path.insert(0, str(Path(__file__).parent))
from src.pipeline.extraction.router import ExtractorRouter
from src.pipeline.extraction.base import Document

def load_contributing_pdfs(limit: int = None) -> list[Path]:
    kb_path = Path("C:/clinrec_downloader/knowledge_base.json")
    if not kb_path.exists():
        # fallback: scan downloads_active
        pdfs = [Path(p) for p in glob.glob("C:/clinrec_downloader/downloads_active/*.pdf")]
        if limit:
            pdfs = pdfs[:limit]
        return pdfs

    with open(kb_path, encoding="utf-8") as f:
        kb = json.load(f)

    pdf_set = set()
    for g in kb:
        pf = g.get("pdf_file")
        if pf:
            pdf_set.add(pf)

    located = []
    for name in sorted(pdf_set):
        for root in ["C:/clinrec_downloader/downloads_active", "C:/clinrec_downloader/archive_review"]:
            p = Path(root) / name
            if p.exists():
                located.append(p)
                break
    if limit:
        located = located[:limit]
    return located

def main(limit: int = 10, out: str = "p45_reprocess_metrics.json"):
    router = ExtractorRouter()
    pdfs = load_contributing_pdfs(limit=limit)
    print(f"Reprocessing {len(pdfs)} PDFs with P4.5 Layout...")

    stats = {
        "processed": 0,
        "total_structured_tables": 0,
        "total_cells": 0,
        "pdfs_with_tables": 0,
        "avg_tables_per_pdf": 0.0,
        "entity_counts": [],
        "table_entities_flags": 0,
        "elapsed_total": 0.0,
        "per_pdf": [],
    }

    t_global = time.time()
    for i, pdf in enumerate(pdfs):
        print(f"[{i+1}/{len(pdfs)}] {pdf.name} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            doc: Document = router.extract(pdf)
            elapsed = time.time() - t0

            n_tables = len(getattr(doc, 'structured_tables', []))
            n_cells = sum(len(t.cells) for t in getattr(doc, 'structured_tables', []))
            n_ents = doc.metadata.get("entity_count", 0)
            used_table = bool(doc.metadata.get("table_entities_used"))

            stats["processed"] += 1
            stats["total_structured_tables"] += n_tables
            stats["total_cells"] += n_cells
            if n_tables > 0:
                stats["pdfs_with_tables"] += 1
            stats["entity_counts"].append(n_ents)
            if used_table:
                stats["table_entities_flags"] += 1
            stats["elapsed_total"] += elapsed

            stats["per_pdf"].append({
                "pdf": pdf.name,
                "pages": len(doc.pages),
                "tables": n_tables,
                "cells": n_cells,
                "entities": n_ents,
                "table_used": used_table,
                "elapsed_s": round(elapsed, 1),
            })
            print(f"tables={n_tables} cells={n_cells} ents={n_ents} {round(elapsed,1)}s")
        except Exception as e:
            print(f"ERROR {e}")
            continue

    if stats["processed"] > 0:
        stats["avg_tables_per_pdf"] = round(stats["total_structured_tables"] / stats["processed"], 2)
        stats["avg_entities"] = round(sum(stats["entity_counts"]) / len(stats["entity_counts"]), 1)
    stats["total_elapsed_min"] = round((time.time() - t_global) / 60, 1)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print("\n=== P4.5 Reprocess Summary ===")
    print(json.dumps({k: v for k, v in stats.items() if k != "per_pdf"}, indent=2))
    print(f"\nReport written to {out}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10, help="Limit PDFs for practical run (full corpus = 193)")
    ap.add_argument("--out", default="p45_reprocess_metrics.json")
    args = ap.parse_args()
    main(limit=args.limit, out=args.out)
