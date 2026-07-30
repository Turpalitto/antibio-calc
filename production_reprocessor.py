#!/usr/bin/env python
"""
P4.5 Production Reprocessor
Enterprise-grade tool for full corpus reprocessing with Layout Intelligence.

Features:
- Checkpoint / resume (JSON state)
- Incremental metrics
- Crash recovery
- Detailed per-PDF logging
- Automatic audit data collection
- Supports full 193+ PDFs

Usage:
  python production_reprocessor.py --full
  python production_reprocessor.py --resume
  python production_reprocessor.py --limit 20
"""

import argparse
import json
import time
import logging
import traceback
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import sys
import glob

sys.path.insert(0, str(Path(__file__).parent))
from src.pipeline.extraction.router import ExtractorRouter
from src.pipeline.extraction.base import Document
from clinical_engine.corpus.locator import resolve_corpus_dir

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('p45_reprocess.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

CHECKPOINT_FILE = Path("p45_reprocess_checkpoint.json")
METRICS_FILE = Path("p45_full_corpus_metrics.json")  # default, can be overridden by --out
AUDIT_FILE = Path("P4.5_PRODUCTION_AUDIT.md")

def load_contributing_pdfs(corpus_dir: str | Path | None = None) -> list[Path]:
    """Load all unique contributing PDFs from knowledge_base."""
    corpus_root = Path(corpus_dir) if corpus_dir is not None else resolve_corpus_dir()
    kb_path = corpus_root / "knowledge_base.json"
    if not kb_path.exists():
        logger.warning("knowledge_base.json not found, scanning downloads_active")
        return [
            Path(p)
            for p in glob.glob(str(corpus_root / "downloads_active" / "*.pdf"))
        ]

    with open(kb_path, encoding="utf-8") as f:
        kb = json.load(f)

    pdf_set = set()
    for g in kb:
        pf = g.get("pdf_file")
        if pf:
            pdf_set.add(pf)

    located = []
    for name in sorted(pdf_set):
        for root in [
            corpus_root / "downloads_active",
            corpus_root / "archive_review",
        ]:
            p = Path(root) / name
            if p.exists():
                located.append(p)
                break
    logger.info(f"Found {len(located)} contributing PDFs")
    return located

def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"processed": [], "metrics": {"per_pdf": [], "aggregate": {}}, "start_time": None}

def save_checkpoint(state: dict):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def collect_metrics(doc: Document, pdf_path: Path, elapsed: float) -> dict:
    """Collect detailed metrics from a processed Document."""
    structured = getattr(doc, 'structured_tables', []) or []
    n_tables = len(structured)
    n_cells = sum(len(t.cells) for t in structured)

    dose_cells = sum(1 for t in structured for c in t.cells if c.text and any(kw in c.text.lower() for kw in ['мг', 'г ', 'мг/кг']))
    strat_cells = sum(1 for t in structured for c in t.cells if c.text and any(kw in c.text.lower() for kw in ['мг/кг', 'масса', 'вес']))

    return {
        "pdf": pdf_path.name,
        "pages": len(doc.pages),
        "tables": n_tables,
        "cells": n_cells,
        "dose_cells": dose_cells,
        "strat_cells": strat_cells,
        "entities": doc.metadata.get("entity_count", 0),
        "table_used": doc.metadata.get("table_entities_used", False),
        "elapsed_s": round(elapsed, 1),
        "layout_processed": doc.metadata.get("layout_processed", False),
        "errors": len(doc.errors) if hasattr(doc, 'errors') else 0,
        "warnings": len(doc.warnings) if hasattr(doc, 'warnings') else 0,
    }

def main(
    full: bool = False,
    limit: int = None,
    resume: bool = False,
    out_file: str = "p45_full_corpus_metrics.json",
    corpus_dir: str | Path | None = None,
):
    global METRICS_FILE
    METRICS_FILE = Path(out_file)
    router = ExtractorRouter()
    all_pdfs = load_contributing_pdfs(corpus_dir=corpus_dir)

    if limit:
        all_pdfs = all_pdfs[:limit]
        logger.info(f"Limited to {limit} PDFs for this run")

    state = load_checkpoint() if resume else {"processed": [], "metrics": {"per_pdf": [], "aggregate": defaultdict(int)}, "start_time": datetime.now().isoformat()}

    processed_set = set(state["processed"])
    remaining = [p for p in all_pdfs if p.name not in processed_set]

    logger.info(f"Total PDFs: {len(all_pdfs)}, Already processed: {len(processed_set)}, Remaining: {len(remaining)}")

    if not state.get("start_time"):
        state["start_time"] = datetime.now().isoformat()

    t_global = time.time()

    for i, pdf in enumerate(remaining):
        logger.info(f"[{i+1}/{len(remaining)}] Processing {pdf.name}")
        t0 = time.time()
        try:
            doc: Document = router.extract(pdf)
            elapsed = time.time() - t0

            metrics = collect_metrics(doc, pdf, elapsed)

            state["processed"].append(pdf.name)
            state["metrics"]["per_pdf"].append(metrics)

            # Update aggregate
            agg = state["metrics"]["aggregate"]
            agg["pdfs"] = agg.get("pdfs", 0) + 1
            agg["tables"] = agg.get("tables", 0) + metrics["tables"]
            agg["cells"] = agg.get("cells", 0) + metrics["cells"]
            agg["dose_cells"] = agg.get("dose_cells", 0) + metrics["dose_cells"]
            agg["strat_cells"] = agg.get("strat_cells", 0) + metrics["strat_cells"]
            agg["entities"] = agg.get("entities", 0) + metrics["entities"]
            if metrics.get("table_used"):
                agg["table_used_count"] = agg.get("table_used_count", 0) + 1
            agg["total_elapsed_s"] = agg.get("total_elapsed_s", 0) + elapsed

            save_checkpoint(state)

            logger.info(f"  tables={metrics['tables']} cells={metrics['cells']} dose_cells={metrics['dose_cells']} strat={metrics['strat_cells']} time={metrics['elapsed_s']}s")

            # Periodic full metrics save
            if (i + 1) % 5 == 0:
                with open(METRICS_FILE, "w", encoding="utf-8") as f:
                    json.dump(state["metrics"], f, ensure_ascii=False, indent=2)
                logger.info(f"  Intermediate metrics saved to {METRICS_FILE}")

        except Exception as e:
            logger.error(f"  FAILED on {pdf.name}: {e}")
            logger.error(traceback.format_exc()[:500])
            # Record failure but continue for production resilience
            state["processed"].append(pdf.name)
            fail_metrics = {
                "pdf": pdf.name,
                "error": str(e)[:200],
                "elapsed_s": round(time.time() - t0, 1)
            }
            state["metrics"]["per_pdf"].append(fail_metrics)
            save_checkpoint(state)
            continue

    # Finalize
    total_time = time.time() - t_global
    agg = state["metrics"]["aggregate"]
    if agg.get("pdfs", 0) > 0:
        agg["avg_tables"] = round(agg["tables"] / agg["pdfs"], 2)
        agg["avg_cells"] = round(agg["cells"] / agg["pdfs"], 2)

    state["end_time"] = datetime.now().isoformat()
    state["total_wall_time_min"] = round(total_time / 60, 1)

    with open(METRICS_FILE, "w", encoding="utf-8") as f:
        json.dump(state["metrics"], f, ensure_ascii=False, indent=2)

    save_checkpoint(state)

    logger.info("=== P4.5 REPROCESS COMPLETE ===")
    logger.info(json.dumps({k: v for k, v in agg.items() if not k.startswith("_")}, indent=2))
    logger.info(f"Full metrics: {METRICS_FILE}")
    logger.info(f"Checkpoint: {CHECKPOINT_FILE}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Process entire corpus")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of PDFs")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--out", default="p45_full_corpus_metrics.json", help="Output metrics JSON file")
    parser.add_argument(
        "--corpus-dir",
        default=None,
        help="External corpus root; defaults to ANTIBIO_CORPUS_DIR/config.",
    )
    args = parser.parse_args()

    limit = None if args.full else (args.limit or 10)
    main(
        full=args.full,
        limit=limit,
        resume=args.resume,
        out_file=args.out,
        corpus_dir=args.corpus_dir,
    )
