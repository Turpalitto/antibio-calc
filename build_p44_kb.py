#!/usr/bin/env python
"""
P4.4 Production Knowledge Base Builder

Builds the authoritative, immutable, versioned KnowledgeBase from the full
layout-enhanced extraction pipeline (P4.1–P4.5).

- Uses ExtractorRouter (full DocLayout-YOLO + Table Transformer + semantic)
- Feeds doc.knowledge_objects into KnowledgeBase (dedup, versioning, provenance, review queue)
- Resume-safe via checkpoint + existing KB
- Rich table cell provenance captured (via P4.5 entities)

Usage:
  python build_p44_kb.py --limit 5
  python build_p44_kb.py --full --out p44_build_report.json

After run:
- kb_p44.db contains the production objects
- Review queue + conflicts + impact ready for physician curation
- Ready to feed curated bundles / clinical engine

This is the canonical step after P4.5 audit (PASSED).
"""

import argparse
import json
import time
import glob
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline.extraction.router import ExtractorRouter
from src.pipeline.knowledge_base import KnowledgeBase
from src.pipeline.extraction.base import Document

DEFAULT_DB = "kb_p44.db"
REPORT = "p44_kb_build_report.json"


def checkpoint_path_for(db_path: str) -> Path:
    """Derive a per-DB checkpoint path so each build's resume state stays bound
    to its own database. Prevents checkpoint/DB drift (a build appending to one
    DB can never advance another DB's checkpoint)."""
    return Path(db_path).with_suffix(".checkpoint.json")

def load_contributing_pdfs(limit: int = None) -> list[Path]:
    kb_path = Path("C:/clinrec_downloader/knowledge_base.json")
    pdf_set = set()

    if kb_path.exists():
        with open(kb_path, encoding="utf-8") as f:
            data = json.load(f)
        for g in data:
            if g.get("pdf_file"):
                pdf_set.add(g["pdf_file"])
    else:
        pdf_set = {Path(p).name for p in glob.glob("C:/clinrec_downloader/downloads_active/*.pdf")}

    located = []
    for name in sorted(pdf_set):
        for root in ["C:/clinrec_downloader/downloads_active", "C:/clinrec_downloader/archive_review"]:
            p = Path(root) / name
            if p.exists():
                located.append(p)
                break

    if limit and limit > 0:
        located = located[:limit]
    return located

def load_guideline_id_map() -> dict:
    """pdf filename -> clinrec_id, so provenance can carry guideline_id (PROVENANCE_SPECIFICATION,
    RC-013). Owner of guideline_id is Document metadata; stamped before add_document."""
    kb_path = Path("C:/clinrec_downloader/knowledge_base.json")
    m = {}
    if kb_path.exists():
        with open(kb_path, encoding="utf-8") as f:
            for g in json.load(f):
                if g.get("pdf_file") and g.get("clinrec_id"):
                    m[g["pdf_file"]] = g["clinrec_id"]
    return m

def load_checkpoint(checkpoint: Path) -> dict:
    if checkpoint.exists():
        return json.load(open(checkpoint, encoding="utf-8"))
    return {"processed": [], "start_time": None}

def save_checkpoint(checkpoint: Path, state: dict):
    json.dump(state, open(checkpoint, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def main(full: bool = False, limit: int = None, resume: bool = True, db_path: str = DEFAULT_DB, out: str = REPORT):
    router = ExtractorRouter()
    kb = KnowledgeBase(db_path)
    pdfs = load_contributing_pdfs(limit=limit if not full else None)
    guideline_map = load_guideline_id_map()

    checkpoint = checkpoint_path_for(db_path)
    state = load_checkpoint(checkpoint) if resume else {"processed": [], "start_time": datetime.now(timezone.utc).isoformat()}
    processed = set(state.get("processed", []))
    remaining = [p for p in pdfs if p.name not in processed]

    print(f"P4.4 KB Builder")
    print(f"  DB: {db_path}")
    print(f"  Total contributing: {len(pdfs)}")
    print(f"  Already processed: {len(processed)}")
    print(f"  Remaining this run: {len(remaining)}")
    print()

    if not state.get("start_time"):
        state["start_time"] = datetime.now(timezone.utc).isoformat()

    aggregate = defaultdict(int)
    per_pdf = []
    t0_global = time.time()

    for i, pdf in enumerate(remaining):
        print(f"[{i+1}/{len(remaining)}] {pdf.name} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            doc: Document = router.extract(pdf)
            elapsed = time.time() - t0

            # PROVENANCE_SPECIFICATION: stamp document-level guideline_id (RC-013) before ingest.
            if not getattr(doc, "metadata", None):
                doc.metadata = {}
            doc.metadata["guideline_id"] = guideline_map.get(pdf.name)

            # Feed to versioned KB (P4.4)
            kb_stats = kb.add_document(doc)

            # Collect rich metrics (PHASE 13)
            n_tables = len(getattr(doc, "structured_tables", []) or [])
            n_cells = sum(len(t.cells) for t in getattr(doc, "structured_tables", []) or [])
            n_ents = doc.metadata.get("entity_count", 0)
            used_table = bool(doc.metadata.get("table_entities_used", False))

            kb_current = kb.stats()

            rec = {
                "pdf": pdf.name,
                "pages": len(doc.pages),
                "structured_tables": n_tables,
                "table_cells": n_cells,
                "entities": n_ents,
                "table_entities_used": used_table,
                "kb_added": kb_stats.get("added", 0),
                "kb_reviews": kb_stats.get("reviews", 0),
                "kb_conflicts": kb_stats.get("conflicts", 0),
                "kb_superseded": kb_stats.get("superseded", 0),
                "elapsed_s": round(elapsed, 1),
            }
            per_pdf.append(rec)

            aggregate["pdfs"] += 1
            aggregate["tables"] += n_tables
            aggregate["entities"] += n_ents
            aggregate["kb_added"] += kb_stats.get("added", 0)
            aggregate["kb_reviews"] += kb_stats.get("reviews", 0)
            aggregate["kb_conflicts"] += kb_stats.get("conflicts", 0)

            state["processed"].append(pdf.name)
            save_checkpoint(checkpoint, state)

            print(f"tables={n_tables} ents={n_ents} added={kb_stats.get('added',0)} reviews={kb_stats.get('reviews',0)} {round(elapsed,1)}s | KB total={kb_current['total_objects']}")

        except Exception as e:
            print(f"ERROR: {e}")
            continue

    # Final stats
    final_kb = kb.stats()
    total_time = time.time() - t0_global

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db": db_path,
        "pdfs_targeted": len(remaining),
        "processed_this_run": aggregate["pdfs"],
        "aggregate": dict(aggregate),
        "final_kb_stats": final_kb,
        "open_reviews": len(kb.get_reviews("open")),
        "conflicts_total": final_kb.get("conflicts", 0),
        "per_pdf": per_pdf,
        "total_wall_time_min": round(total_time / 60, 1),
        "phase": "P4.4 Production Knowledge Base Platform"
    }

    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("\n=== P4.4 KB BUILD COMPLETE (this run) ===")
    print("KB Stats:", json.dumps(final_kb, indent=2))
    print(f"Open reviews: {report['open_reviews']}")
    print(f"Report saved to: {out}")
    print(f"Checkpoint: {checkpoint}")

    kb.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--out", default=REPORT)
    args = parser.parse_args()

    main(
        full=args.full,
        limit=args.limit,
        resume=not args.no_resume,
        db_path=args.db,
        out=args.out,
    )
