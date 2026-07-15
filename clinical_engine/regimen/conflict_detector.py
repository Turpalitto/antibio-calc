"""RegimenConflictDetector — deterministic multi-source conflict detection (P5.3 Phase 3).

Design authority: REGIMEN_ASSEMBLY_ENGINE_RFC.md §5, REVIEW_WORKFLOW_RFC.md §2.6.

Detects when two regimens that share a clinical slot disagree on a clinical field
(dose, duration, first-line drug, age restriction). NEVER resolves silently — it
emits a ConflictRecord and the affected regimens are routed to review
(P5.3_DECISION_RECORD.md rule 3; the whole project's "no autonomous conflict
resolution" governance).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable

from clinical_engine.regimen.clinical_regimen import ClinicalRegimen


@dataclass(frozen=True)
class ConflictRecord:
    conflict_id: str
    field: str                 # dose | duration | first_line_drug | age_group
    regimen_a: str
    regimen_b: str
    value_a: str
    value_b: str
    guideline_a: str
    guideline_b: str
    severity: str              # HIGH | MEDIUM | LOW
    resolution_status: str = "UNRESOLVED"


# Clinical slot = the identity within which two regimens are "the same thing" and so may conflict.
def _slot_key(r: ClinicalRegimen) -> tuple:
    return (r.icd_mkb or r.diagnosis, r.age_group)


def _cid(field_: str, a: str, b: str) -> str:
    h = hashlib.sha256(f"{field_}|{a}|{b}".encode("utf-8")).hexdigest()[:16]
    return f"conf_{h}"


def _sev(field_: str) -> str:
    # dose/first-line disagreements are the most clinically dangerous
    return {"dose": "HIGH", "first_line_drug": "HIGH", "duration": "MEDIUM",
            "age_group": "MEDIUM"}.get(field_, "LOW")


class RegimenConflictDetector:
    """Pure, deterministic. Same input set -> same ConflictRecords (sorted)."""

    def detect(self, regimens: Iterable[ClinicalRegimen]) -> list[ConflictRecord]:
        regs = sorted(regimens, key=lambda r: (r.regimen_id, r.version))
        out: list[ConflictRecord] = []
        # group by clinical slot
        slots: dict[tuple, list[ClinicalRegimen]] = {}
        for r in regs:
            slots.setdefault(_slot_key(r), []).append(r)

        for _slot, members in sorted(slots.items(), key=lambda kv: str(kv[0])):
            # same drug -> compare dose/duration; different first-line drug -> first_line conflict
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    if a.antibiotic == b.antibiotic:
                        if a.dose is not None and b.dose is not None and a.dose != b.dose:
                            out.append(self._mk("dose", a, b, f"{a.dose}{a.unit}", f"{b.dose}{b.unit}"))
                        if (a.duration_recommended is not None and b.duration_recommended is not None
                                and a.duration_recommended != b.duration_recommended):
                            out.append(self._mk("duration", a, b,
                                                str(a.duration_recommended), str(b.duration_recommended)))
                    else:
                        # different drugs for the same slot, both first-line -> first-line conflict
                        if a.therapy_line == b.therapy_line == "first":
                            out.append(self._mk("first_line_drug", a, b, a.antibiotic, b.antibiotic))
                        if a.age_group != b.age_group and a.antibiotic == b.antibiotic:
                            out.append(self._mk("age_group", a, b, a.age_group, b.age_group))
        # deterministic order
        return sorted(out, key=lambda c: (c.field, c.regimen_a, c.regimen_b))

    def _mk(self, field_: str, a: ClinicalRegimen, b: ClinicalRegimen, va: str, vb: str) -> ConflictRecord:
        return ConflictRecord(
            conflict_id=_cid(field_, f"{a.regimen_id}:{va}", f"{b.regimen_id}:{vb}"),
            field=field_, regimen_a=a.regimen_id, regimen_b=b.regimen_id,
            value_a=va, value_b=vb, guideline_a=a.guideline_id, guideline_b=b.guideline_id,
            severity=_sev(field_),
        )
