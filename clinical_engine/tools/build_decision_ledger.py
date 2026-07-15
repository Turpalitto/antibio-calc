"""Build the physician decision ledger for diagnosis_index conflicts.

Milestone 11 — Physician Validation. This tool NEVER selects a guideline.
It emits one PENDING record per conflict for a physician to decide, mirroring
the project's `dictionary_candidates.json` "never auto-accept" policy.

Reversibility & audit: the ledger is the editable source of truth. Re-running
this tool PRESERVES any decisions a physician already made (matched by a stable
conflict_id) — it only adds newly-appeared conflicts as `pending_review` and
reports decisions whose conflict no longer exists (orphaned) instead of
silently dropping them. The draft index is never modified.

Usage (from repo root):
    python -m clinical_engine.tools.build_decision_ledger \
        [--review diagnosis_index_review.json] \
        [--ledger diagnosis_index_decisions.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_REVIEW = "diagnosis_index_review.json"
_DEFAULT_LEDGER = "diagnosis_index_decisions.json"

# Controlled decision vocabulary — a physician sets `decision` to one of these.
DECISION_VOCABULARY = {
    "pending_review": "не решено (значение по умолчанию — конфликт ждёт врача)",
    "keep_all_complementary": "все guideline валидны/комплементарны — сохранить все сопоставления",
    "select_primary": "выбрать один primary guideline_id (заполнить chosen_guideline_id)",
    "duplicate_keep_one": "это дубликат — оставить один guideline_id (заполнить chosen_guideline_id)",
    "split": "метка диагноза неоднозначна — переименовать по guideline (заполнить renames {guideline_id: новое_имя})",
    "remove_diagnosis": "строка диагноза некорректна — удалить её целиком",
}

# Physician-editable fields carried over on regeneration (the audit trail).
_CARRIED_FIELDS = ("decision", "chosen_guideline_id", "renames", "decided_by", "decided_at", "rationale")


def _conflict_id(diagnosis: str) -> str:
    return "c_" + hashlib.sha1(diagnosis.encode("utf-8")).hexdigest()[:12]


def _blank_decision() -> dict:
    return {
        "decision": "pending_review",
        "chosen_guideline_id": None,
        "renames": None,
        "decided_by": None,
        "decided_at": None,
        "rationale": None,
    }


def build(review_path: str, ledger_path: str) -> dict:
    review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    conflicts = review["conflicts"]

    existing: dict[str, dict] = {}
    if Path(ledger_path).exists():
        prev = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
        for rec in prev.get("decisions", []):
            existing[rec["conflict_id"]] = rec

    records: list[dict] = []
    current_ids: set[str] = set()
    for c in conflicts:
        cid = _conflict_id(c["diagnosis"])
        current_ids.add(cid)
        rec = {
            "conflict_id": cid,
            "diagnosis": c["diagnosis"],
            "severity": c["severity"],
            "conflict_type": c["conflict_type"],
            "guideline_options": [
                {"guideline_id": g["guideline_id"], "icd10": g["icd10"], "title": " / ".join(g["titles"])}
                for g in c["guidelines"]
            ],
        }
        # Carry over an existing physician decision verbatim (reversibility/audit).
        prior = existing.get(cid)
        if prior:
            for f in _CARRIED_FIELDS:
                rec[f] = prior.get(f)
        else:
            rec.update(_blank_decision())
        records.append(rec)

    orphaned = [
        r for cid, r in existing.items()
        if cid not in current_ids and r.get("decision", "pending_review") != "pending_review"
    ]

    pending = sum(1 for r in records if r["decision"] == "pending_review")
    doc = {
        "meta": {
            "status": "PENDING_PHYSICIAN_REVIEW" if pending else "PHYSICIAN_REVIEW_COMPLETE",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_review": review_path,
            "policy": (
                "НИКОГДА не выбирать guideline автоматически. Каждое решение принимает врач: "
                "установить `decision`, при необходимости `chosen_guideline_id`/`renames`, "
                "обязательно заполнить `decided_by`, `decided_at`, `rationale`. Все решения "
                "обратимы (изменить и пересобрать). Черновой индекс не модифицируется."
            ),
            "decision_vocabulary": DECISION_VOCABULARY,
            "total_conflicts": len(records),
            "pending": pending,
            "decided": len(records) - pending,
            "orphaned_decisions": len(orphaned),
        },
        "decisions": records,
        "orphaned_decisions": orphaned,
    }
    Path(ledger_path).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ledger": ledger_path, "total": len(records), "pending": pending,
            "decided": len(records) - pending, "orphaned": len(orphaned)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", default=_DEFAULT_REVIEW)
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER)
    args = ap.parse_args()
    r = build(args.review, args.ledger)
    print("=== physician decision ledger ===")
    print(f"written:  {r['ledger']}")
    print(f"conflicts:{r['total']}  pending:{r['pending']}  decided:{r['decided']}  orphaned:{r['orphaned']}")
    if r["pending"]:
        print("NOTE: physician must set decisions before a PRODUCTION_CURATED index can be built.")


if __name__ == "__main__":
    main()
