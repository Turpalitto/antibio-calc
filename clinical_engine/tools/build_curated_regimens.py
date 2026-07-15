"""Deterministic curated regimen view from corpus + physician ledger (P3 INT-3).

Reads the external corpus READ-ONLY and the repo-side regimen review ledger, then
emits a curated view containing ONLY physician-approved regimens, each carrying
full provenance back to the upstream source (via the INT-2 resolver). It never
writes to the corpus, never copies clinical regimen content into the repo (only
provenance keys + integrity hashes + review attribution), and is deterministic:
same corpus + same ledger -> same entries.

Validation FAILS (blocks PRODUCTION_CURATED) on any of — INT-3 requirement 5:
  DUPLICATE_DECISION    same regimen_id decided more than once
  MISSING_REGIMEN       ledger regimen_id absent upstream
  SHA_MISMATCH          ledger pdf_sha256 != upstream metadata pdf_sha256
  UNRESOLVED_DECISION   pending, or non-pending missing attribution/review_status
  ORPHAN_REVIEW         ledger guideline_id != upstream regimen's guideline_id,
                        or an approved regimen whose provenance cannot resolve

Generated artifacts are never hand-edited.

Usage (from repo root):
    python -m clinical_engine.tools.build_curated_regimens \
        [--ledger regimen_review_ledger.json] \
        [--out clinical_engine/resources/curated_regimens.json] \
        [--audit regimen_curation_audit.json] [--no-verify-pdf]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.corpus.provenance import ProvenanceError, ProvenanceResolver

_DEFAULT_LEDGER = "regimen_review_ledger.json"
_DEFAULT_OUT = "clinical_engine/resources/curated_regimens.json"
_DEFAULT_AUDIT = "regimen_curation_audit.json"

_APPLYABLE = {"approve", "reject", "needs_revision"}
_REQUIRED_STATUS = {"approve": "APPROVED", "reject": "REJECTED", "needs_revision": "NEEDS_REVISION"}


def _validate_row(rec: dict, upstream: dict | None) -> str | None:
    """Return an error code string if invalid/unresolved, else None. `upstream`
    is the regimen's upstream facts {guideline_id, pdf_sha256} or None if absent."""
    decision = rec.get("decision", "pending_review")
    if decision == "pending_review":
        return "UNRESOLVED_DECISION"
    if decision == "needs_revision":
        return "UNRESOLVED_DECISION"
    if decision not in _APPLYABLE:
        return "UNRESOLVED_DECISION"
    if not (rec.get("decided_by") and rec.get("decided_at") and rec.get("rationale")
            and rec.get("review_status")):
        return "UNRESOLVED_DECISION"
    if rec.get("review_status") != _REQUIRED_STATUS.get(decision):
        return "UNRESOLVED_DECISION"
    if upstream is None:
        return "MISSING_REGIMEN"
    if str(rec.get("guideline_id")) != str(upstream["guideline_id"]):
        return "ORPHAN_REVIEW"
    if str(rec.get("pdf_sha256") or "").lower() != str(upstream["pdf_sha256"] or "").lower():
        return "SHA_MISMATCH"
    return None


def build(ledger_path: str, out_path: str, audit_path: str, *,
          verify_pdf: bool = True, locator: CorpusLocator | None = None) -> dict:
    loc = locator or CorpusLocator()
    loc.require()  # fail loudly if corpus absent
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    decisions = ledger.get("decisions", [])

    # Upstream facts (read-only): regimen_id -> {guideline_id, pdf_sha256}
    nr = loc.open_normalized_regimens()
    md = loc.open_metadata()
    try:
        up_gid = {str(a): str(b) for a, b in nr.execute(
            "SELECT regimen_id, guideline_id FROM normalized_regimens")}
        up_sha = {str(a): b for a, b in md.execute(
            "SELECT id, pdf_sha256 FROM antibiotic_regimens")}
    finally:
        nr.close(); md.close()

    def upstream_of(rid: str):
        if rid not in up_gid:
            return None
        return {"guideline_id": up_gid[rid], "pdf_sha256": up_sha.get(rid)}

    errors: list[dict] = []
    error_counts: Counter = Counter()

    # DUPLICATE_DECISION
    seen: Counter = Counter(d["regimen_id"] for d in decisions)
    for rid, n in seen.items():
        if n > 1:
            errors.append({"regimen_id": rid, "error": "DUPLICATE_DECISION",
                           "detail": f"decided {n} times"})
            error_counts["DUPLICATE_DECISION"] += 1

    approved: list[dict] = []
    rejected: list[str] = []
    unresolved: list[str] = []

    resolver = ProvenanceResolver(loc, verify_pdf_hash=verify_pdf)
    try:
        for rec in decisions:
            rid = rec["regimen_id"]
            err = _validate_row(rec, upstream_of(rid))
            if err == "UNRESOLVED_DECISION":
                unresolved.append(rid)
                continue
            if err:
                errors.append({"regimen_id": rid, "error": err})
                error_counts[err] += 1
                continue
            # valid, attributed decision
            if rec["decision"] == "reject":
                rejected.append(rid)
                continue
            # approve -> must preserve full provenance (else ORPHAN_REVIEW)
            try:
                prov = resolver.resolve(rid)
            except ProvenanceError as exc:
                errors.append({"regimen_id": rid, "error": "ORPHAN_REVIEW",
                               "detail": exc.code})
                error_counts["ORPHAN_REVIEW"] += 1
                continue
            approved.append({
                "regimen_id": prov.regimen_id,
                "guideline_id": prov.guideline_id,
                "kr_code": prov.kr_code,
                "pdf_sha256": prov.pdf_sha256,
                "pdf_sha256_verified": prov.pdf_sha256_verified,
                "pdf_path": prov.pdf_path,
                "page_number": prov.page_number,
                "review_status": rec["review_status"],
                "decided_by": rec["decided_by"],
                "decided_at": rec["decided_at"],
                "rationale": rec["rationale"],
            })
    finally:
        resolver.close()

    approved.sort(key=lambda e: e["regimen_id"])
    total = len(decisions)
    invalid = len(errors)
    unresolved_n = len(unresolved)
    production_ready = total > 0 and invalid == 0 and unresolved_n == 0
    status = "PRODUCTION_CURATED" if production_ready else "PARTIALLY_CURATED"

    out_doc = {
        "meta": {
            "status": status,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_ledger": ledger_path,
            "corpus_root": str(loc.root),
            "note": ("GENERATED — do not hand-edit. Physician-approved regimens only, each with "
                     "provenance to the read-only upstream corpus. Clinical regimen content stays "
                     "upstream; this view stores only references + integrity hashes + attribution."),
            "total_decisions": total,
            "approved": len(approved),
            "rejected": len(rejected),
            "unresolved": unresolved_n,
            "invalid": invalid,
        },
        "approved_regimens": approved,
    }
    Path(out_path).write_text(json.dumps(out_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit_doc = {
        "generated_at": out_doc["meta"]["generated_at"],
        "status": status,
        "source_ledger": ledger_path,
        "counts": {"total": total, "approved": len(approved), "rejected": len(rejected),
                   "unresolved": unresolved_n, "invalid": invalid},
        "errors_by_type": dict(error_counts),
        "errors": errors,
        "rejected_regimen_ids": sorted(rejected),
        "unresolved_regimen_ids": sorted(unresolved),
    }
    Path(audit_path).write_text(json.dumps(audit_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"out": out_path, "audit": audit_path, "status": status, "total": total,
            "approved": len(approved), "rejected": len(rejected),
            "unresolved": unresolved_n, "invalid": invalid,
            "errors_by_type": dict(error_counts)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    ap.add_argument("--audit", default=_DEFAULT_AUDIT)
    ap.add_argument("--no-verify-pdf", action="store_true")
    args = ap.parse_args()
    r = build(args.ledger, args.out, args.audit, verify_pdf=not args.no_verify_pdf)
    print("=== curated regimen view ===")
    print(f"status:   {r['status']}")
    print(f"decisions: total {r['total']}  approved {r['approved']}  rejected {r['rejected']}  "
          f"unresolved {r['unresolved']}  invalid {r['invalid']}")
    if r["errors_by_type"]:
        print(f"errors:   {r['errors_by_type']}")
    print(f"written:  {r['out']}")
    if r["status"] != "PRODUCTION_CURATED":
        print("NOTE: NOT production. Resolve all pending and fix all invalid decisions.")


if __name__ == "__main__":
    main()
