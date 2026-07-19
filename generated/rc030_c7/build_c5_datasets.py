"""RC-030 C7 Part V Phase 9 -- build one C5-compatible dataset per batch,
stripping every field that must stay hidden before owner submission
(deterministic_candidate, deterministic_classification,
comparison_metadata, and any prior TRUSTWORTHY/SUSPECT/V6-inclusion
label -- none of which exist in this record shape to begin with beyond
those three fields).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BATCH_DIR = ROOT / "review_batches" / "c7"
OUT_DIR = ROOT / "generated" / "rc030_c7_owner_review"

HIDDEN_FIELDS = ("deterministic_candidate", "deterministic_classification", "comparison_metadata")

MODE_BY_CATEGORY = {
    "EXACT_LINK_CONFIRMATION": "range-exact-review",
    "GENERAL_SINGLE_CANDIDATE": "range-single-review",
    "UNIT_BASIS_REVIEW": "range-unit-basis-review",
    "TABLE_REVIEW": "range-table-review",
    "ENGINE_DISAGREEMENT": "range-engine-review",
    "SOURCE_BLOCKED": "range-blocked-evidence",
}


def strip_hidden(task: dict) -> dict:
    visible = {k: v for k, v in task.items() if k not in HIDDEN_FIELDS}
    visible["evidence_hash"] = task["unit_id"]
    visible.pop("owner_verdict", None)
    visible.pop("owner_note", None)

    # C7 field-name fix: owner_review_template.html reads r.dose/r.unit/
    # r.context_before/r.context_after/r.source_page directly -- the C7
    # review-task-model field names (structured_scalar/structured_unit/
    # sentence_context/paragraph_context) never matched, silently rendering
    # "(none)"/blank in the built interface. Found by loading the real
    # built HTML in-browser (Part VII), not by static inspection.
    visible["dose"] = visible.pop("structured_scalar", None)
    visible["unit"] = visible.pop("structured_unit", None)
    quote = visible.get("exact_quote", "") or ""
    para = visible.pop("paragraph_context", "") or ""
    visible.pop("sentence_context", None)
    idx = para.find(quote) if quote else -1
    if idx != -1:
        visible["context_before"] = para[:idx]
        visible["context_after"] = para[idx + len(quote):]
    else:
        visible["context_before"] = ""
        visible["context_after"] = ""
    visible["source_quote"] = quote
    if "source_pdf_relative_path" in visible:
        visible["source_pdf"] = visible.pop("source_pdf_relative_path")
    if "page" in visible:
        visible["source_page"] = visible.pop("page")
    if "PDF_hash" in visible:
        # C7 fix: owner_review_template.html reads r.pdf_hash (lowercase)
        # and embeds it directly into every exported owner_fidelity_event
        # -- the task model's "PDF_hash" (capitalized) key silently produced
        # undefined, which JSON.stringify drops entirely, so every exported
        # event was missing the pdf_hash field and failed C4's
        # validate_events() "missing required field" check. Found by
        # actually validating a real browser-exported event under C4
        # (Part VII Phase 18), not by static inspection.
        visible["pdf_hash"] = visible.pop("PDF_hash")
    return visible


def main() -> None:
    manifest = json.loads((BATCH_DIR / "batch_manifest.json").read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    written = []
    for b in manifest["batches"]:
        bid = b["batch_id"]
        batch_data = json.loads((BATCH_DIR / f"{bid}.json").read_text(encoding="utf-8"))
        records = [strip_hidden(t) for t in batch_data["tasks"]]
        for r in records:
            for hf in HIDDEN_FIELDS:
                assert hf not in r, f"{hf} leaked into visible dataset for {bid}"
        dataset = {"schema_version": 1, "generated_from": "generated/rc030_c7/review_tasks_ready.json",
                   "batch_id": bid, "records": records}
        out_path = OUT_DIR / f"{bid}_dataset.json"
        out_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
        category = list(b["category_counts"].keys())[0]
        written.append({"batch_id": bid, "dataset_path": str(out_path.relative_to(ROOT)),
                         "mode": MODE_BY_CATEGORY[category], "record_count": len(records)})

    (OUT_DIR / "datasets_manifest.json").write_text(
        json.dumps({"schema_version": 1, "datasets": written}, ensure_ascii=False, indent=2), encoding="utf-8")
    for w in written:
        print(w["batch_id"], "->", w["mode"], w["record_count"])


if __name__ == "__main__":
    main()
