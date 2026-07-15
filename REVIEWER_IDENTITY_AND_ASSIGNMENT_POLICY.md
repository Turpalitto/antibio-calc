# Reviewer Identity and Assignment Policy

Version 1.0 — 2026-07-15 (P5.6 Review Governance Hardening, closes GOV-001).

## Canonical identity system

`clinical_engine/review_workbench/reviewer_registry.py::ReviewerRegistry` is the **single, canonical** reviewer identity system. `ReviewService` has no other way to know who a reviewer is — it depends on the registry directly (constructor: `ReviewService(store, registry)`).

Every `ReviewerRecord` carries:

| Field | Purpose |
|---|---|
| `reviewer_id` | The only identity key. Never a display name. |
| `display_name` | Human-readable label, never used for authorization. |
| `professional_role` | Free-text professional title (e.g. "physician"). |
| `credential_reference` | Optional pointer to a licence/credential record — no credential document content is stored here. |
| `organisation` | Required. |
| `authorised_scope` | Tuple of `ReviewRole` values this reviewer_id may act as. |
| `target_type_scope` | Optional restriction to specific `TargetType`s. Empty = all types authorised. |
| `active` | Deactivation flag. |
| `registered_at` / `registered_by` | Audit trail of who registered whom, when. |
| `credential_expires_at` | Optional ISO-8601 expiry. Empty = does not expire. |
| `version` | Incremented on every mutation (deactivation, etc.). |

No credential *document* or sensitive personal data beyond what's listed above is ever stored, per the pilot mandate's Phase 2 instruction.

## Validation contract

`ReviewerRegistry.validate_reviewer_action(reviewer_id, required_role, target_type, action) -> ReviewerActionResult` is deterministic and never raises — every caller inspects `.allowed`/`.reason_code`. `ReviewService._validate()` calls this before every write and, on denial, logs a `review_rejected_attempts` row (task_id, actor, role, action, reason_code, timestamp) **without changing task state**, then raises `ReviewerValidationError(reason_code)`.

Deterministic reason codes: `REVIEWER_NOT_REGISTERED`, `REVIEWER_INACTIVE`, `ROLE_NOT_AUTHORISED`, `SCOPE_NOT_AUTHORISED`, `CREDENTIAL_EXPIRED`, `SELF_REVIEW_FORBIDDEN` (task-context, raised as `InvalidTransition` since it depends on which reviewers are already assigned to *this* task, not on registry state alone), `ADMIN_CLINICAL_ACTION_FORBIDDEN`.

`ReviewRole.ADMINISTRATOR` is explicitly not a clinical reviewer: `validate_reviewer_action` rejects it outright for any action in `CLINICAL_ACTIONS = {claim, submit_first, submit_second, adjudicate, qa_signoff, close, waive}`, regardless of registration state.

Additionally, `ReviewService._SINGLE_ROLE_ACTIONS` maps each single-reviewer action to the one role legitimately allowed to perform it (`submit_first`→`REVIEWER_A`, `submit_second`→`REVIEWER_B`, `adjudicate`→`ADJUDICATOR`, `qa_signoff`/`close`/`waive`→`MEDICAL_QA_LEAD`). This prevents a reviewer from reusing a role they legitimately hold on their own account (e.g. `REVIEWER_A`) to perform an action reserved for a different role.

## Task-level assignment (Phase 3)

Registration alone never grants task access. `ReviewAssignment` (assignment_id, task_id, reviewer_id, assigned_role, assigned_by, assigned_at, active, revoked_at, reason) is a separate, append-only, revocable governance record (`review_assignments` table).

- `claim()` self-assigns (creates the `ReviewAssignment` row automatically) when a reviewer claims a `PENDING`/`SECOND_REVIEW` task.
- `assign_reviewer()` lets an authority (e.g. a QA Lead) pre-assign a reviewer explicitly, with the same self-review checks.
- `revoke_assignment()` deactivates an assignment; `submit_first_review`/`submit_second_review` re-check `active_assignment_for_role()` at submission time, so a revoked assignment cannot be used to submit a decision even if the task's scalar `assigned_reviewer`/`second_reviewer` field still names that reviewer.
- Reviewer A and Reviewer B must always be distinct `reviewer_id`s on the same task — enforced both at `assign_reviewer()` time and at `claim()`/`submit_second_review()` time (`SELF_REVIEW_FORBIDDEN`).

## What the owner must do

No reviewer is pre-registered. To begin real review, the owner (or a delegated administrator acting only in the `"assign"`/registration capacity, never in a clinical capacity) must call `ReviewerRegistry.register(...)` with real professional information for each real Reviewer A, Reviewer B, Adjudicator, and Medical QA Lead. Until at least one distinct Reviewer A and one distinct Reviewer B are registered, `reviewer_registry.pilot_status()` returns `WAITING_FOR_REVIEWERS`.
