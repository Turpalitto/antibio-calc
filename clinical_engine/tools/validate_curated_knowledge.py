"""Cross-layer validator for the unified curated knowledge (P3 INT-4).

Read-only. Operates on the generated curated_knowledge.json and FAILS (req 6) on:
  APPROVED_DIAGNOSIS_MISSING_REGIMEN  approved diagnosis whose guideline has no approved regimen
  APPROVED_REGIMEN_MISSING_DIAGNOSIS  approved regimen whose guideline has no approved diagnosis
  ORPHAN_CURATED_ENTRY                link backed by neither a diagnosis nor a regimen
  PROVENANCE_CHAIN_BROKEN             approved regimen missing a provenance field
  PHYSICIAN_APPROVAL_MISSING          approved diagnosis/regimen without decided_by

Exit code 0 iff the layer is clean, else 1 (CI / pre-deploy gate).

Usage:
    python -m clinical_engine.tools.validate_curated_knowledge \
        [--knowledge clinical_engine/resources/curated_knowledge.json] \
        [--out-md curated_knowledge_validation.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_DEFAULT_KNOWLEDGE = "clinical_engine/resources/curated_knowledge.json"

_PROV_FIELDS = ("regimen_id", "guideline_id", "pdf_sha256", "pdf_path", "page_number")


def validate(doc: dict) -> dict:
    dx = doc.get("approved_diagnoses", [])
    reg = doc.get("approved_regimens", [])
    links = doc.get("links", [])

    errors: list[dict] = []
    counts: Counter = Counter()

    def err(code: str, **ctx):
        errors.append({"error": code, **ctx})
        counts[code] += 1

    dx_gids = {d["guideline_id"] for d in dx}
    reg_gids = {r["guideline_id"] for r in reg}

    # physician approval attribution
    for d in dx:
        if not d.get("decided_by"):
            err("PHYSICIAN_APPROVAL_MISSING", kind="diagnosis", ref=d.get("diagnosis"))
    for r in reg:
        if not r.get("decided_by"):
            err("PHYSICIAN_APPROVAL_MISSING", kind="regimen", ref=r.get("regimen_id"))

    # provenance completeness
    for r in reg:
        missing = [f for f in _PROV_FIELDS if not r.get(f)]
        if missing:
            err("PROVENANCE_CHAIN_BROKEN", regimen_id=r.get("regimen_id"), missing=missing)

    # cross-references
    for gid in sorted(dx_gids):
        if gid not in reg_gids:
            err("APPROVED_DIAGNOSIS_MISSING_REGIMEN", guideline_id=gid)
    for gid in sorted(reg_gids):
        if gid not in dx_gids:
            err("APPROVED_REGIMEN_MISSING_DIAGNOSIS", guideline_id=gid)

    # orphan links
    for l in links:
        if not l.get("diagnoses") and not l.get("regimen_ids"):
            err("ORPHAN_CURATED_ENTRY", guideline_id=l.get("guideline_id"))

    clean = not errors
    return {
        "clean": clean,
        "errors_by_type": dict(counts),
        "errors": errors,
        "counts": {"approved_diagnoses": len(dx), "approved_regimens": len(reg),
                   "links": len(links)},
        "status": "CURATED_VALID" if clean else "INVALID",
    }


def render_md(r: dict) -> str:
    lines = [
        "# Curated Knowledge — Cross-Layer Validation",
        "",
        f"- status: **{r['status']}**",
        f"- counts: {r['counts']}",
        f"- errors by type: {r['errors_by_type']}",
        "",
    ]
    if r["errors"]:
        lines += ["| Error | Context |", "|---|---|"]
        for e in r["errors"]:
            ctx = {k: v for k, v in e.items() if k != "error"}
            lines.append(f"| {e['error']} | {ctx} |")
    else:
        lines.append("No cross-layer errors. Every approved entry is attributed, provenanced, "
                     "and mutually referenced.")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--knowledge", default=_DEFAULT_KNOWLEDGE)
    ap.add_argument("--out-md", default="curated_knowledge_validation.md")
    args = ap.parse_args()
    doc = json.loads(Path(args.knowledge).read_text(encoding="utf-8"))
    r = validate(doc)
    Path(args.out_md).write_text(render_md(r), encoding="utf-8")
    print(f"status: {r['status']}  errors: {r['errors_by_type']}")
    sys.exit(0 if r["clean"] else 1)


if __name__ == "__main__":
    main()
