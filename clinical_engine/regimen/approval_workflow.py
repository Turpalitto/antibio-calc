"""ApprovalWorkflow — lifecycle state machine (P5.3 Phase 5).

Design authority: CLINICAL_KNOWLEDGE_LIFECYCLE.md, REGIMEN_APPROVAL_MODEL.md.

Enforces legal transitions ONLY. Hard rule: no automated jump to PHYSICIAN_APPROVED
or PUBLISHED, and NEVER DRAFT->PUBLISHED. PHYSICIAN_APPROVED / PUBLISHED require a
named human actor. Illegal transitions raise; they are never silently allowed.
"""
from __future__ import annotations

from clinical_engine.regimen.clinical_regimen import ClinicalRegimen, LifecycleState

S = LifecycleState

# legal transitions (from -> allowed set). System-only vs human-only enforced separately.
_LEGAL: dict[LifecycleState, set[LifecycleState]] = {
    S.DRAFT: {S.EXTRACTED, S.REJECTED},
    S.EXTRACTED: {S.ASSEMBLED, S.REJECTED},
    S.ASSEMBLED: {S.VALIDATED, S.REJECTED},
    S.VALIDATED: {S.REVIEW_REQUIRED, S.REJECTED},
    S.REVIEW_REQUIRED: {S.PHYSICIAN_APPROVED, S.REJECTED},
    S.PHYSICIAN_APPROVED: {S.PUBLISHED, S.REJECTED},
    S.PUBLISHED: {S.SUPERSEDED, S.DEPRECATED},
    S.SUPERSEDED: set(),
    S.DEPRECATED: set(),
    S.REJECTED: set(),
}

# transitions that REQUIRE a named human actor
_HUMAN_REQUIRED = {S.PHYSICIAN_APPROVED, S.PUBLISHED}


class IllegalTransition(Exception):
    pass


class ApprovalWorkflow:
    def can_transition(self, frm: LifecycleState, to: LifecycleState) -> bool:
        return to in _LEGAL.get(frm, set())

    def transition(self, r: ClinicalRegimen, to: LifecycleState,
                   actor: str = "system") -> ClinicalRegimen:
        frm = r.status
        if not self.can_transition(frm, to):
            raise IllegalTransition(f"{frm.value} -> {to.value} is not a legal transition")
        if to in _HUMAN_REQUIRED and (not actor or actor == "system"):
            raise IllegalTransition(
                f"{to.value} requires a named human actor (got '{actor}') — "
                f"no automated approval/publication (CLINICAL_KNOWLEDGE_LIFECYCLE.md §3)")
        kw = {}
        if to == S.PHYSICIAN_APPROVED:
            kw = {"review_status": "reviewed", "approved_by": actor}
        if to == S.PUBLISHED:
            kw = {"approved_by": actor}
        return r.with_state(to, **kw)

    def advance_automated(self, r: ClinicalRegimen, verdict: str) -> ClinicalRegimen:
        """System-driven progression ASSEMBLED -> VALIDATED -> REVIEW_REQUIRED based on a gate
        verdict. Stops at REVIEW_REQUIRED — a human must take it further."""
        if r.status != S.ASSEMBLED:
            return r
        if verdict == "REJECT":
            return self.transition(r, S.REJECTED)
        r = self.transition(r, S.VALIDATED)
        # everything goes through review (no auto fast-path, REGIMEN_APPROVAL_MODEL.md §2)
        return self.transition(r, S.REVIEW_REQUIRED)
