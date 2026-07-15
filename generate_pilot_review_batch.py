"""Generate the first physician-review pilot batch (P5.6, owner-requested 2026-07-15).

STRICT MODE, read-only against the existing review queue:
- Does NOT approve, claim, or transition any task.
- Does NOT change any medical data, ClinicalRegimen, or TherapeuticOption.
- Selects 20 ClinicalRegimen + 10 TherapeuticOption from the ALREADY-BUILT queue
  (review_workbench_p56.sqlite, 9,153 PENDING tasks) using the owner's EXACT priority
  order, which differs from the system's default additive priority_score (see the
  discrepancy note in PILOT_REVIEW_BATCH_REPORT.md).
- For each selected task, exports the existing deterministic ReviewService.packet()
  (already implements P5.6 Phase 15's packet contract: normalized object, source
  wording, provenance, conflicts, validation failures, decision options, and an
  explicit "NOT AVAILABLE / UNSATISFIABLE" for interaction checks — never a fake PASS).

Owner's exact priority order (rank 1 = highest):
  1. pediatric
  2. pregnancy
  3. renal impairment
  4. severe allergy
  5. missing dose or unit
  6. unresolved conflict
  7. source mismatch
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from clinical_engine.review_workbench.storage import ReviewStore
from clinical_engine.review_workbench.service import ReviewService
from clinical_engine.review_workbench.reviewer_registry import ReviewerRegistry
from clinical_engine.review_workbench.models import ReviewState, TargetType

DB_PATH = "review_workbench_p56.sqlite"
OUT_DIR = Path("pilot_review_batch")
DOSE_ISSUE_TYPES = {"DOSE_NOT_EXTRACTED", "DOSE_NOT_PARSED", "DOSE_DAILY_MISREAD", "DOSE_UNIT_GROUP"}
CONFLICT_ISSUE_TYPES = {"CONFLICT_FIRST_LINE_DRUG", "CONFLICT_DOSE", "CONFLICT_DURATION"}

# Fallback keyword scan over the target's OWN text fields (indication/therapeutic_class/diagnosis/
# source_quote), used ONLY when the task carries no queue-level safety_axes/issue_type tag for a
# tier — this is a real, honest finding (see report §2): review_workbench's queue builder does not
# tag TherapeuticOption tasks with any safety axis at all (652/652 untagged, confirmed by direct
# query). Same evidence-based regex discipline as the P5.4/P5.5 audits — never guessed.
_KEYWORD_PATTERNS = {
    "pediatric": re.compile(r"детск|ребен|ребён|педиатр|новорожд", re.IGNORECASE),
    "pregnancy": re.compile(r"беремен", re.IGNORECASE),
    "renal": re.compile(r"почеч|ренал|скф", re.IGNORECASE),
    "severe_allergy": re.compile(r"аллерг", re.IGNORECASE),
}


def _text_blob(snapshot_payload: dict) -> str:
    fields = ("indication", "therapeutic_class", "diagnosis", "age_group", "source_quote",
             "antibiotic", "selection_conditions")
    return " ".join(str(snapshot_payload.get(f) or "") for f in fields)


# rank -> (label, matcher(task, payload_text) -> bool)
RANK_ORDER = [
    (1, "pediatric", lambda t, txt: "pediatric" in t.safety_axes or _KEYWORD_PATTERNS["pediatric"].search(txt)),
    (2, "pregnancy", lambda t, txt: "pregnancy" in t.safety_axes or _KEYWORD_PATTERNS["pregnancy"].search(txt)),
    (3, "renal", lambda t, txt: "renal" in t.safety_axes or _KEYWORD_PATTERNS["renal"].search(txt)),
    (4, "severe_allergy", lambda t, txt: any("allerg" in a for a in t.safety_axes) or _KEYWORD_PATTERNS["severe_allergy"].search(txt)),
    (5, "missing_dose_or_unit", lambda t, txt: "missing_unit" in t.safety_axes or t.issue_type in DOSE_ISSUE_TYPES),
    (6, "unresolved_conflict", lambda t, txt: "clinical_conflict" in t.safety_axes or t.issue_type in CONFLICT_ISSUE_TYPES),
    (7, "source_mismatch", lambda t, txt: "source_mismatch" in t.safety_axes),
]


def primary_rank(task, text_blob: str) -> tuple[int, str, int, str]:
    """Best (lowest-numbered) matching tier; ties broken by match-count, priority_score, task_id."""
    matches = [(rank, label) for rank, label, fn in RANK_ORDER if fn(task, text_blob)]
    if not matches:
        return (99, "no_owner_tier_match", -task.priority_score, task.task_id)
    best_rank, best_label = min(matches, key=lambda m: m[0])
    return (best_rank, best_label, -len(matches) - task.priority_score, task.task_id)


def select_batch(store: ReviewStore, target_type: TargetType, count: int) -> list:
    """Strict owner priority order WITH per-tier representation: fill tier 1 first, but cap each
    tier at ceil(count / number_of_tiers_present) so a numerous tier (e.g. 496 pediatric tasks)
    cannot exhaust the whole batch and leave rarer, still-high-priority tiers (renal: 5 tasks total,
    severe_allergy: 0 tagged) invisible to the pilot. Within each tier, ranked as before (match
    count, then system score, then task_id)."""
    tasks = store.list_tasks(target_type=target_type, state=ReviewState.PENDING, limit=1_000_000)
    scored = []
    for t in tasks:
        payload = store.target_snapshot(t)["payload"]
        rank = primary_rank(t, _text_blob(payload))
        scored.append((rank, t))
    scored.sort(key=lambda pair: pair[0])

    by_tier: dict[int, list] = {}
    for rank, t in scored:
        by_tier.setdefault(rank[0], []).append((rank, t))

    present_tiers = sorted(by_tier)
    n_tiers = len(present_tiers) or 1
    cap = max(1, -(-count // n_tiers))  # ceil

    selected: list = []
    for tier in present_tiers:
        take = by_tier[tier][:cap]
        selected.extend(t for _, t in take)
        if len(selected) >= count:
            break
    # fill any remainder (if some tiers had fewer than `cap`) from the next-ranked leftovers
    if len(selected) < count:
        selected_ids = {t.task_id for t in selected}
        for rank, t in scored:
            if t.task_id not in selected_ids:
                selected.append(t)
                selected_ids.add(t.task_id)
                if len(selected) >= count:
                    break
    return selected[:count]


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    store = ReviewStore(DB_PATH)
    # Read-only export (packet() only) — no reviewer action is ever performed by this
    # script, so an empty in-memory registry is sufficient and correct.
    registry = ReviewerRegistry(":memory:")
    service = ReviewService(store, registry)

    regimens = select_batch(store, TargetType.CLINICAL_REGIMEN, 20)
    options = select_batch(store, TargetType.THERAPEUTIC_OPTION, 10)

    manifest = {"clinical_regimen_batch": [], "therapeutic_option_batch": []}

    for label, batch, key in (("ClinicalRegimen", regimens, "clinical_regimen_batch"),
                             ("TherapeuticOption", options, "therapeutic_option_batch")):
        for task in batch:
            payload = store.target_snapshot(task)["payload"]
            rank, reason, _, _ = primary_rank(task, _text_blob(payload))
            packet_path = OUT_DIR / f"{task.task_id}.json"
            # RC-027 fixed in the canonical ReviewService.packet() (service.py, resolve_source_
            # wording). No export-time substitution needed or performed here.
            service.export_packet(task.task_id, packet_path)
            manifest[key].append({
                "task_id": task.task_id, "target_id": task.target_id,
                "owner_priority_rank": rank, "owner_priority_reason": reason,
                "system_priority_score": task.priority_score, "system_priority_band": task.priority.value,
                "safety_axes": list(task.safety_axes), "issue_type": task.issue_type,
                "packet_file": str(packet_path),
            })

    (OUT_DIR / "PILOT_BATCH_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"ClinicalRegimen selected: {len(regimens)}")
    print(f"TherapeuticOption selected: {len(options)}")
    for label, batch in (("ClinicalRegimen", regimens), ("TherapeuticOption", options)):
        from collections import Counter
        c = Counter(primary_rank(t, _text_blob(store.target_snapshot(t)["payload"]))[1] for t in batch)
        print(f"{label} rank-reason distribution:", dict(c))
    store.close()


if __name__ == "__main__":
    main()
