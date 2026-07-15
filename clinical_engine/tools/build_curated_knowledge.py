"""Unify the physician-curated diagnosis + regimen layers (P3 INT-4).

Generates ONE canonical curated-knowledge artifact from the two EDITABLE
physician sources:
  - the diagnosis review ledger      (diagnosis_index_decisions.json)
  - the curated regimen view         (curated_regimens.json, itself generated
                                       from the regimen review ledger in INT-3)

The output links an approved diagnosis -> guideline_id -> approved regimen_ids,
carrying provenance forward. It stores ONLY identifiers, approvals, and
provenance — never drug names, doses, or source text (those stay upstream).
Deterministic: same inputs -> same entries. Generated; never hand-edited.

Upstream corpus is not touched here (this composes already-generated,
already-provenanced artifacts).

Usage (from repo root):
    python -m clinical_engine.tools.build_curated_knowledge \
        [--diagnosis-ledger diagnosis_index_decisions.json] \
        [--curated-regimens clinical_engine/resources/curated_regimens.json] \
        [--out clinical_engine/resources/curated_knowledge.json]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from clinical_engine.tools.build_curated_index import _validate as _validate_diagnosis

_DEFAULT_DX_LEDGER = "diagnosis_index_decisions.json"
_DEFAULT_CURATED_REGIMENS = "clinical_engine/resources/curated_regimens.json"
_DEFAULT_OUT = "clinical_engine/resources/curated_knowledge.json"


def _approved_diagnoses(ledger: dict) -> list[dict]:
    """One row per (diagnosis, guideline_id) for each VALID, attributed decision
    that keeps a routing. Reuses the INT-3 diagnosis validation rules."""
    out: list[dict] = []
    for rec in ledger.get("decisions", []):
        decision = rec.get("decision", "pending_review")
        if decision == "pending_review":
            continue
        if _validate_diagnosis(rec) is not None:  # invalid/unattributed -> not approved
            continue
        gids: list[str] = []
        opts = [str(g["guideline_id"]) for g in rec.get("guideline_options", [])]
        if decision in ("select_primary", "duplicate_keep_one"):
            gids = [str(rec["chosen_guideline_id"])]
        elif decision == "keep_all_complementary":
            gids = opts
        elif decision == "split":
            gids = opts  # each guideline kept (renamed) -> still an approved routing
        elif decision == "remove_diagnosis":
            gids = []  # explicitly removed -> no approved routing
        for gid in gids:
            out.append({
                "diagnosis": rec["diagnosis"],
                "guideline_id": gid,
                "decided_by": rec["decided_by"],
                "decided_at": rec["decided_at"],
                "rationale": rec["rationale"],
            })
    out.sort(key=lambda e: (e["guideline_id"], e["diagnosis"]))
    return out


def _approved_regimens(curated_regimens: dict) -> list[dict]:
    """Provenance-only regimen rows from the INT-3 curated regimen view."""
    rows = []
    for e in curated_regimens.get("approved_regimens", []):
        rows.append({
            "regimen_id": e["regimen_id"],
            "guideline_id": e["guideline_id"],
            "kr_code": e.get("kr_code"),
            "pdf_sha256": e.get("pdf_sha256"),
            "pdf_sha256_verified": e.get("pdf_sha256_verified"),
            "pdf_path": e.get("pdf_path"),
            "page_number": e.get("page_number"),
            "decided_by": e.get("decided_by"),
            "decided_at": e.get("decided_at"),
            "rationale": e.get("rationale"),
        })
    rows.sort(key=lambda e: e["regimen_id"])
    return rows


def build(dx_ledger_path: str, curated_regimens_path: str, out_path: str) -> dict:
    dx_ledger = json.loads(Path(dx_ledger_path).read_text(encoding="utf-8")) \
        if Path(dx_ledger_path).is_file() else {"decisions": []}
    curated_reg = json.loads(Path(curated_regimens_path).read_text(encoding="utf-8")) \
        if Path(curated_regimens_path).is_file() else {"approved_regimens": []}

    approved_dx = _approved_diagnoses(dx_ledger)
    approved_reg = _approved_regimens(curated_reg)

    reg_by_gid: dict[str, list[str]] = defaultdict(list)
    for r in approved_reg:
        reg_by_gid[r["guideline_id"]].append(r["regimen_id"])
    dx_by_gid: dict[str, list[str]] = defaultdict(list)
    for d in approved_dx:
        dx_by_gid[d["guideline_id"]].append(d["diagnosis"])

    # A canonical link exists only where BOTH a diagnosis AND ≥1 regimen are approved.
    guideline_ids = sorted(set(dx_by_gid) | set(reg_by_gid))
    links = []
    for gid in guideline_ids:
        links.append({
            "guideline_id": gid,
            "diagnoses": sorted(set(dx_by_gid.get(gid, []))),
            "regimen_ids": sorted(reg_by_gid.get(gid, [])),
            "complete": bool(dx_by_gid.get(gid)) and bool(reg_by_gid.get(gid)),
        })

    complete_links = [l for l in links if l["complete"]]
    out_doc = {
        "meta": {
            "status": "CURATED" if complete_links else "PARTIALLY_CURATED",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sources": {
                "diagnosis_ledger": dx_ledger_path,
                "curated_regimens": curated_regimens_path,
            },
            "note": ("GENERATED — do not hand-edit. The only editable sources are the physician "
                     "diagnosis and regimen review ledgers. Stores identifiers, approvals, and "
                     "provenance only — never medical content."),
            "counts": {
                "approved_diagnoses": len(approved_dx),
                "approved_regimens": len(approved_reg),
                "guideline_links": len(links),
                "complete_links": len(complete_links),
            },
        },
        "approved_diagnoses": approved_dx,
        "approved_regimens": approved_reg,
        "links": links,
    }
    Path(out_path).write_text(json.dumps(out_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"out": out_path, "status": out_doc["meta"]["status"], **out_doc["meta"]["counts"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnosis-ledger", default=_DEFAULT_DX_LEDGER)
    ap.add_argument("--curated-regimens", default=_DEFAULT_CURATED_REGIMENS)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    args = ap.parse_args()
    r = build(args.diagnosis_ledger, args.curated_regimens, args.out)
    print("=== curated knowledge (unified) ===")
    print(f"status: {r['status']}")
    print(f"approved_diagnoses {r['approved_diagnoses']}  approved_regimens {r['approved_regimens']}  "
          f"complete_links {r['complete_links']}/{r['guideline_links']}")
    print(f"written: {r['out']}")


if __name__ == "__main__":
    main()
