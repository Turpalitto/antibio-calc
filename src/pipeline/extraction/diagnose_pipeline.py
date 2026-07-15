#!/usr/bin/env python
"""
Extraction → Knowledge pipeline stage tracer (PR-001 diagnostic).

Reusable production diagnostic: runs a single PDF through every stage and reports
where table-derived information is present or lost:

    PDF → Layout(structured_tables) → Document.pages → Semantic(entities) →
    Knowledge Objects → SQLite provenance

For each stage it prints: tables, cells, table-sourced entities, knowledge objects,
and table-origin provenance counts. It also surfaces layout exceptions that the
production path deliberately swallows (so silent failures become visible).

Usage:
    python -m src.pipeline.extraction.diagnose_pipeline "<pdf_path>"
"""
from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path


def trace(pdf_path: Path) -> dict:
    from src.pipeline.extraction.router import ExtractorRouter
    from src.pipeline.extraction.layout import LayoutProcessor, add_layout_to_document
    from src.pipeline.extraction.semantic import add_semantic_to_document
    from src.pipeline.knowledge_base import KnowledgeBase

    report: dict = {"pdf": pdf_path.name}
    print(f"\n=== PR-001 STAGE TRACE: {pdf_path.name} ===")

    # STAGE 0 — primary extraction (flat text)
    router = ExtractorRouter()
    doc = router.primary.extract(pdf_path)
    report["pages"] = len(doc.pages)
    print(f"[0] primary extract ({router.primary.name}): pages={len(doc.pages)}")

    # STAGE 1 — layout: surface swallowed exceptions by probing directly
    proc = LayoutProcessor()
    print(f"[1] layout models: detector={bool(proc.table_detector)} "
          f"structure={bool(proc.table_structure)} rapid={bool(proc.rapid_table)}")

    # Probe the Table Transformer path on the first signalful page WITH errors surfaced
    import fitz
    from PIL import Image
    import io
    fdoc = fitz.open(str(pdf_path))
    probe_err = None
    probed_page = None
    for pn in range(len(fdoc)):
        txt = (fdoc[pn].get_text("text") or "").lower()
        if any(k in txt for k in ["мг", "таблиц", "мг/кг", "сутки"]):
            probed_page = pn
            page = fdoc[pn]
            pix = page.get_pixmap(dpi=100)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            try:
                # Re-run the *inner* logic with exceptions surfaced (bypass the bare except)
                _probe_table_transformer(proc, image, page, pn, page.rect)
            except Exception:
                probe_err = traceback.format_exc()
            break
    fdoc.close()
    report["probed_page"] = probed_page
    report["layout_probe_exception"] = probe_err
    if probe_err:
        print(f"[1] !!! Table Transformer path RAISES on page {probed_page} "
              f"(swallowed in production):")
        print("    " + probe_err.strip().splitlines()[-1])

    # STAGE 1b — real production layout call
    add_layout_to_document(doc, pdf_path)
    n_tables = len(getattr(doc, "structured_tables", []) or [])
    n_cells = sum(len(t.cells) for t in getattr(doc, "structured_tables", []) or [])
    report["structured_tables"] = n_tables
    report["table_cells"] = n_cells
    report["layout_error"] = doc.metadata.get("layout_error")
    print(f"[1b] add_layout_to_document: structured_tables={n_tables} cells={n_cells} "
          f"layout_error={doc.metadata.get('layout_error')}")

    # STAGE 2 — semantic
    add_semantic_to_document(doc, "diagnostic")
    ents = getattr(doc, "knowledge_objects", {})
    all_ents = [e for lst in ents.values() for e in lst] if isinstance(ents, dict) else []
    table_ents = [e for e in all_ents
                  if "table" in str((e.get("provenance") or {}).get("source", "")).lower()
                  or (e.get("provenance") or {}).get("row") is not None]
    report["knowledge_objects"] = len(all_ents)
    report["table_sourced_entities"] = len(table_ents)
    print(f"[2] semantic: knowledge_objects={len(all_ents)} "
          f"table_sourced={len(table_ents)}")

    # STAGE 3 — knowledge base (temp DB)
    tmpdb = Path(tempfile.gettempdir()) / "pr001_probe.db"
    if tmpdb.exists():
        tmpdb.unlink()
    kb = KnowledgeBase(str(tmpdb))
    kb.add_document(doc)
    total = kb.conn.execute("select count(*) from objects").fetchone()[0]
    with_table = kb.conn.execute(
        "select count(*) from provenance where table_row is not null").fetchone()[0]
    non_none_engine = kb.conn.execute(
        "select count(*) from provenance where layout_engine != 'none'").fetchone()[0]
    report["kb_objects"] = total
    report["kb_provenance_with_table_row"] = with_table
    report["kb_provenance_layout_engine_set"] = non_none_engine
    print(f"[3] knowledge base: objects={total} "
          f"provenance_with_table_row={with_table} layout_engine_set={non_none_engine}")
    kb.close()

    # VERDICT — first stage where table info is lost
    print("\n--- VERDICT ---")
    if probe_err and n_tables == 0:
        print("FIRST LOSS: STAGE 1 (Layout). Table Transformer raises and is swallowed; "
              "0 structured tables produced. Downstream stages are starved.")
    elif n_tables > 0 and len(table_ents) == 0:
        print("FIRST LOSS: STAGE 2 (Semantic). Tables exist but produce no table entities.")
    elif len(table_ents) > 0 and with_table == 0:
        print("FIRST LOSS: STAGE 3 (Knowledge Base). Table entities exist but provenance dropped.")
    elif with_table > 0:
        print("OK: table-origin provenance reaches the Knowledge Base.")
    else:
        print("No table signal at any stage (PDF may genuinely have no structured tables).")
    return report


def _probe_table_transformer(proc, image, page, page_num, page_rect):
    """Runs the real production Table Transformer path with exceptions surfaced (the production
    caller swallows them). Reports how many structured tables the method actually returns, so a
    silent regression in the table path becomes visible here."""
    tables = proc._extract_table_with_transformers(image, page, page_num, page_rect)
    print(f"    [probe] Table Transformer returned {len(tables)} table(s) on page {page_num}")
    if not tables:
        # Surface why: re-run detection-only to report detected regions vs produced tables.
        import torch
        inputs = proc.table_detector_processor(images=image, return_tensors="pt")
        outputs = proc.table_detector(**inputs)
        results = proc.table_detector_processor.post_process_object_detection(
            outputs, threshold=0.7, target_sizes=torch.tensor([image.size[::-1]]))[0]
        n = sum(1 for lbl in results["labels"] if lbl.item() == 0)
        print(f"    [probe] detector found {n} table region(s) but 0 became TableObjects "
              f"(possible regression in table-cell construction)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.pipeline.extraction.diagnose_pipeline <pdf_path>")
        sys.exit(2)
    trace(Path(sys.argv[1]))
