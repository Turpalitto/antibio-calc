# Review Consensus State Model

Version 1.0 — 2026-07-15 (P5.6 Review Governance Hardening, closes GOV-003).

## The core separation

**REVIEW CONSENSUS ≠ PHYSICIAN APPROVAL.** These are two distinct concepts tracked in two distinct fields on `ClinicalReviewTask`:

- `consensus_result: str` — the outcome of comparing Reviewer A's and Reviewer B's (or the Adjudicator's) decisions. One of `ConsensusResult`: `NO_CONSENSUS`, `CONSENSUS_ACCEPT`, `CONSENSUS_ACCEPT_WITH_NOTE`, `CONSENSUS_REJECT_FIDELITY`, `CONSENSUS_REJECT_CLINICAL`, `NEEDS_INFO`, `NEEDS_ADJUDICATION`, `ABSTENTION_PENDING`.
- `lifecycle_state: ReviewState` — the governance state. Reaching consensus **never** sets this directly to `PHYSICIAN_APPROVED`; it sets it to `MEDICAL_QA_PENDING`.

## Lifecycle states (`ReviewState`)

`PENDING → CLAIMED → IN_REVIEW → SECOND_REVIEW → {NEEDS_ADJUDICATION | MEDICAL_QA_PENDING | NEEDS_INFO | ABSTAINED} → {PHYSICIAN_APPROVED | REJECTED | NEEDS_INFO | ABSTAINED} → CLOSED`

Compatibility table (`ReviewService._CONSENSUS_MATCH`), applied by `submit_second_review`:

| Reviewer A | Reviewer B | `consensus_result` | `lifecycle_state` |
|---|---|---|---|
| ACCEPT | ACCEPT | `CONSENSUS_ACCEPT` | `MEDICAL_QA_PENDING` |
| ACCEPT | ACCEPT_WITH_NOTE (either order) | `CONSENSUS_ACCEPT_WITH_NOTE` | `MEDICAL_QA_PENDING` |
| ACCEPT_WITH_NOTE | ACCEPT_WITH_NOTE | `CONSENSUS_ACCEPT_WITH_NOTE` | `MEDICAL_QA_PENDING` |
| REJECT_FIDELITY | REJECT_FIDELITY | `CONSENSUS_REJECT_FIDELITY` | `MEDICAL_QA_PENDING` |
| REJECT_CLINICAL | REJECT_CLINICAL | `CONSENSUS_REJECT_CLINICAL` | `MEDICAL_QA_PENDING` |
| any acceptance | any rejection (mismatch) | `NEEDS_ADJUDICATION` | `NEEDS_ADJUDICATION` |
| — | NEEDS_INFO | `NEEDS_INFO` | `NEEDS_INFO` |
| — | ABSTAIN | `ABSTENTION_PENDING` | `ABSTAINED` |

**Every compatible outcome — acceptance or rejection — lands on `MEDICAL_QA_PENDING`, never directly on a terminal state.** Adjudication (`adjudicate()`) follows the same rule: a resolved adjudication also lands on `MEDICAL_QA_PENDING` (or `NEEDS_INFO`/`ABSTAINED` for those specific adjudicator verdicts), not directly on `PHYSICIAN_APPROVED`/`REJECTED`.

## `governance_state()` — the only externally-meaningful vocabulary

```python
def governance_state(target_type: TargetType, state: ReviewState) -> str:
    if state is ReviewState.PHYSICIAN_APPROVED:
        return "MEDICALLY_REVIEWED" if target_type is TargetType.THERAPEUTIC_OPTION else "PHYSICIAN_APPROVED"
    if state is ReviewState.REJECTED:
        return "REJECTED"
    if state is ReviewState.CLOSED:
        return "CLOSED"
    return "REVIEW_REQUIRED"
```

Anything short of the `ReviewState.PHYSICIAN_APPROVED` enum value — including `MEDICAL_QA_PENDING`, `CONSENSUS_REACHED`-equivalent states, `NEEDS_ADJUDICATION` — reports `"REVIEW_REQUIRED"`. There is no code path that derives `"PHYSICIAN_APPROVED"` from consensus alone.

`TherapeuticOption` never reports `"PHYSICIAN_APPROVED"` — it maps to the distinct `"MEDICALLY_REVIEWED"` state, per the mandate that `TherapeuticOption` approval must remain a separate governance state and must never become directly consumable as executable regimen data by the Clinical Engine.

## The only path to `PHYSICIAN_APPROVED`/`REJECTED`

`ReviewService.submit_medical_qa_signoff()` (see `MEDICAL_QA_SIGNOFF_SPEC.md`) is the **only** method that can set `lifecycle_state` to `PHYSICIAN_APPROVED` or `REJECTED`. It requires the task to be in `MEDICAL_QA_PENDING`, requires a registered, authorised, non-conflicted `MEDICAL_QA_LEAD`, and runs the full governance checklist before an `APPROVE`/`APPROVE_WITH_NOTE` verdict is honored.
