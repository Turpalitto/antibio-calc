"""Build a PRODUCTION_CURATED diagnosis_index from physician decisions.

Milestone 11 — Physician Validation. Applies ONLY explicit, attributed
physician decisions from the ledger (build_decision_ledger.py). Never selects
a guideline itself. Refuses to stamp PRODUCTION_CURATED while any conflict is
unresolved (pending or invalid) — fail-safe against claiming curation that a
physician did not complete.

Reversibility & audit:
  - Reads the draft index + the decisions ledger; writes a NEW curated file.
  - NEVER modifies the draft index or the ledger.
  - Deterministic: change a decision in the ledger and rebuild to reverse it.
  - Emits an audit file recording every applied decision (who / when / why /
    what changed).

Decision semantics (validated before applying):
  keep_all_complementary — keep all mappings unchanged.
  select_primary / duplicate_keep_one — keep only chosen_guideline_id; drop others.
  split — rename each guideline's diagnosis via renames{guideline_id: new_name}.
  remove_diagnosis — drop the diagnosis entirely.
  pending_review — NOT applied (stays ambiguous, blocks PRODUCTION_CURATED).

A non-pending decision MUST carry decided_by, decided_at, rationale — an
unattributed clinical decision is treated as INVALID and not applied.

Usage (from repo root):
    python -m clinical_engine.tools.build_curated_index \
        [--draft clinical_engine/resources/diagnosis_index.json] \
        [--ledger diagnosis_index_decisions.json] \
        [--out clinical_engine/resources/diagnosis_index.curated.json] \
        [--audit diagnosis_index_curation_audit.json]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DRAFT = "clinical_engine/resources/diagnosis_index.json"
_DEFAULT_LEDGER = "diagnosis_index_decisions.json"
_DEFAULT_OUT = "clinical_engine/resources/diagnosis_index.curated.json"
_DEFAULT_AUDIT = "diagnosis_index_curation_audit.json"

_APPLYABLE = {"keep_all_complementary", "select_primary", "duplicate_keep_one", "split", "remove_diagnosis"}


def _load_entries(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("entries", data) if isinstance(data, dict) else data


def _validate(rec: dict) -> str | None:
    """Return an error string if the decision is invalid, else None."""
    decision = rec.get("decision", "pending_review")
    if decision == "pending_review":
        return None  # not an error, just unresolved
    if decision not in _APPLYABLE:
        return f"unknown decision '{decision}'"
    if not rec.get("decided_by") or not rec.get("decided_at") or not rec.get("rationale"):
        return "non-pending decision missing decided_by/decided_at/rationale (audit trail incomplete)"
    gids = {g["guideline_id"] for g in rec["guideline_options"]}
    if decision in ("select_primary", "duplicate_keep_one"):
        if rec.get("chosen_guideline_id") not in gids:
            return "chosen_guideline_id is not one of the conflict's guideline_options"
    if decision == "split":
        renames = rec.get("renames") or {}
        if not isinstance(renames, dict) or set(renames) != gids:
            return "split requires 'renames' covering exactly all guideline_ids of the conflict"
        if any(not str(v).strip() for v in renames.values()):
            return "split renames contain an empty new name"
    return None


def build(draft_path: str, ledger_path: str, out_path: str, audit_path: str) -> dict:
    entries = _load_entries(draft_path)
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    decisions = ledger.get("decisions", [])

    # Index decisions by diagnosis; validate each.
    by_dx: dict[str, dict] = {}
    errors: list[dict] = []
    pending: list[str] = []
    valid_decided: list[dict] = []
    for rec in decisions:
        err = _validate(rec)
        by_dx[rec["diagnosis"]] = rec
        if rec.get("decision", "pending_review") == "pending_review":
            pending.append(rec["diagnosis"])
        elif err:
            errors.append({"diagnosis": rec["diagnosis"], "error": err})
        else:
            valid_decided.append(rec)

    conflict_diagnoses = set(by_dx)
    # Group entries by diagnosis to transform conflicts as a unit.
    entries_by_dx: dict[str, list[dict]] = defaultdict(list)
    passthrough: list[dict] = []
    for e in entries:
        if e["diagnosis_name"] in conflict_diagnoses:
            entries_by_dx[e["diagnosis_name"]].append(e)
        else:
            passthrough.append(e)  # non-conflict entries unchanged

    curated: list[dict] = list(passthrough)
    audit_records: list[dict] = []

    for dx, group in entries_by_dx.items():
        rec = by_dx[dx]
        decision = rec.get("decision", "pending_review")
        err = _validate(rec)

        if decision == "pending_review" or err:
            # Unresolved -> pass through UNCHANGED (still ambiguous).
            curated.extend(group)
            continue

        before = len(group)
        kept: list[dict]
        dropped_gids: list[str] = []
        if decision == "keep_all_complementary":
            kept = list(group)
        elif decision in ("select_primary", "duplicate_keep_one"):
            chosen = rec["chosen_guideline_id"]
            kept = [e for e in group if e["guideline_id"] == chosen]
            dropped_gids = sorted({e["guideline_id"] for e in group if e["guideline_id"] != chosen})
        elif decision == "split":
            renames = rec["renames"]
            kept = []
            for e in group:
                e2 = dict(e)
                e2["diagnosis_name"] = renames[e["guideline_id"]]
                kept.append(e2)
        elif decision == "remove_diagnosis":
            kept = []
            dropped_gids = sorted({e["guideline_id"] for e in group})
        else:  # pragma: no cover - guarded by _validate
            kept = list(group)

        curated.extend(kept)
        audit_records.append({
            "diagnosis": dx,
            "conflict_id": rec.get("conflict_id"),
            "decision": decision,
            "chosen_guideline_id": rec.get("chosen_guideline_id"),
            "renames": rec.get("renames"),
            "decided_by": rec["decided_by"],
            "decided_at": rec["decided_at"],
            "rationale": rec["rationale"],
            "entries_before": before,
            "entries_after": len(kept),
            "dropped_guideline_ids": dropped_gids,
        })

    curated.sort(key=lambda e: (e["guideline_id"], e["diagnosis_name"]))
    unresolved = len(pending) + len(errors)
    fully_curated = unresolved == 0 and len(conflict_diagnoses) > 0

    status = "PRODUCTION_CURATED" if fully_curated else "PARTIALLY_CURATED"
    out_doc = {
        "meta": {
            "status": status,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_draft": draft_path,
            "source_ledger": ledger_path,
            "guideline_set_version": (
                f"curated-{datetime.now(timezone.utc).date().isoformat()}"
                if fully_curated else "partially-curated"
            ),
            "conflicts_total": len(conflict_diagnoses),
            "conflicts_resolved": len(valid_decided),
            "conflicts_pending": len(pending),
            "conflicts_invalid": len(errors),
            "note": (
                "Applied only explicit, attributed physician decisions. "
                "PRODUCTION_CURATED requires zero pending and zero invalid decisions."
                if fully_curated else
                "PARTIALLY_CURATED — physician review incomplete. NOT for production. "
                "Unresolved conflicts pass through unchanged (still ambiguous)."
            ),
        },
        "entries": curated,
    }
    Path(out_path).write_text(json.dumps(out_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit_doc = {
        "generated_at": out_doc["meta"]["generated_at"],
        "status": status,
        "source_draft": draft_path,
        "source_ledger": ledger_path,
        "conflicts_total": len(conflict_diagnoses),
        "conflicts_resolved": len(valid_decided),
        "conflicts_pending": len(pending),
        "conflicts_invalid": len(errors),
        "pending_diagnoses": sorted(pending),
        "invalid_decisions": errors,
        "applied_decisions": audit_records,
    }
    Path(audit_path).write_text(json.dumps(audit_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "out": out_path, "audit": audit_path, "status": status,
        "total_conflicts": len(conflict_diagnoses), "resolved": len(valid_decided),
        "pending": len(pending), "invalid": len(errors),
        "entries_in": len(entries), "entries_out": len(curated),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", default=_DEFAULT_DRAFT)
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    ap.add_argument("--audit", default=_DEFAULT_AUDIT)
    args = ap.parse_args()
    r = build(args.draft, args.ledger, args.out, args.audit)
    print("=== curated diagnosis_index build ===")
    print(f"status:    {r['status']}")
    print(f"conflicts: total {r['total_conflicts']}  resolved {r['resolved']}  "
          f"pending {r['pending']}  invalid {r['invalid']}")
    print(f"entries:   {r['entries_in']} -> {r['entries_out']}")
    print(f"written:   {r['out']}")
    print(f"audit:     {r['audit']}")
    if r["status"] != "PRODUCTION_CURATED":
        print("NOTE: NOT production. Physician must resolve all conflicts in the ledger.")


if __name__ == "__main__":
    main()
