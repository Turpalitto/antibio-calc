"""Read-only validator + progress reporter for regimen curation (P3 INT-3).

Reuses the SAME validation rules as build_curated_regimens (imported, not
reimplemented) so the report can never disagree with the build. Makes no
clinical decision and does not write the curated view — only a progress report.

Exit code 0 iff the ledger would produce PRODUCTION_CURATED (0 unresolved, 0
invalid), else 1 — usable as a CI / pre-deploy gate.

Usage (from repo root):
    python -m clinical_engine.tools.validate_regimen_curation \
        [--ledger regimen_review_ledger.json] \
        [--out-md regimen_curation_progress.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.tools.build_curated_regimens import _validate_row


def validate(ledger_path: str, *, locator: CorpusLocator | None = None) -> dict:
    loc = locator or CorpusLocator()
    loc.require()
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    decisions = ledger.get("decisions", [])

    nr = loc.open_normalized_regimens()
    md = loc.open_metadata()
    try:
        up_gid = {str(a): str(b) for a, b in nr.execute(
            "SELECT regimen_id, guideline_id FROM normalized_regimens")}
        up_sha = {str(a): b for a, b in md.execute(
            "SELECT id, pdf_sha256 FROM antibiotic_regimens")}
    finally:
        nr.close(); md.close()

    errors: Counter = Counter()
    unresolved = 0
    approved = 0
    rejected = 0

    dup = Counter(d["regimen_id"] for d in decisions)
    for rid, n in dup.items():
        if n > 1:
            errors["DUPLICATE_DECISION"] += 1

    for rec in decisions:
        rid = rec["regimen_id"]
        upstream = {"guideline_id": up_gid[rid], "pdf_sha256": up_sha.get(rid)} if rid in up_gid else None
        err = _validate_row(rec, upstream)
        if err == "UNRESOLVED_DECISION":
            unresolved += 1
        elif err:
            errors[err] += 1
        elif rec["decision"] == "reject":
            rejected += 1
        else:
            approved += 1

    total = len(decisions)
    invalid = sum(errors.values())
    production_ready = total > 0 and invalid == 0 and unresolved == 0
    pct = round(100.0 * (approved + rejected) / total, 1) if total else 0.0
    return {"ledger": ledger_path, "total": total, "approved": approved, "rejected": rejected,
            "unresolved": unresolved, "invalid": invalid, "errors_by_type": dict(errors),
            "percent_resolved": pct, "production_ready": production_ready,
            "would_be_status": "PRODUCTION_CURATED" if production_ready else "PARTIALLY_CURATED"}


def render_md(r: dict) -> str:
    bar = int(30 * r["percent_resolved"] / 100)
    lines = [
        "# Regimen Curation — Progress",
        "",
        "> Read-only. Same validation rules as `build_curated_regimens`. No clinical decision here.",
        "",
        f"`{'█'*bar}{'░'*(30-bar)}` **{r['percent_resolved']}%** "
        f"({r['approved']+r['rejected']}/{r['total']} resolved)",
        "",
        f"- Would-be status: **{r['would_be_status']}**",
        f"- approved **{r['approved']}** · rejected **{r['rejected']}** · "
        f"unresolved **{r['unresolved']}** · invalid **{r['invalid']}**",
        f"- errors by type: {r['errors_by_type']}",
        "",
        ("**Production-ready.** Run `build_curated_regimens`."
         if r["production_ready"] else
         "**NOT production-ready.** Resolve all pending and fix all invalid decisions."),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="regimen_review_ledger.json")
    ap.add_argument("--out-md", default="regimen_curation_progress.md")
    args = ap.parse_args()
    r = validate(args.ledger)
    Path(args.out_md).write_text(render_md(r), encoding="utf-8")
    print(f"resolved {r['approved']+r['rejected']}/{r['total']} ({r['percent_resolved']}%)  "
          f"unresolved {r['unresolved']}  invalid {r['invalid']}  -> {r['would_be_status']}")
    sys.exit(0 if r["production_ready"] else 1)


if __name__ == "__main__":
    main()
