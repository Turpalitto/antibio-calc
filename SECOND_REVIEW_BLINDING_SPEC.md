# Second-Review Blinding Specification

Version 1.0 — 2026-07-15 (P5.6 Review Governance Hardening, closes GOV-002).

## Requirement

Reviewer B must not see Reviewer A's verdict, rationale, reason codes, or any derived consensus indicator before submitting their own independent verdict — through any channel: packet, history, metrics, exported packet, or error message.

## Implementation

`ReviewService.packet_for_reviewer(task_id, reviewer_id, role)` is the only reviewer-facing packet accessor. It first validates the caller via `_validate(..., "view_packet")`, then renders:

| Caller role | Task state | View |
|---|---|---|
| `MEDICAL_QA_LEAD` / `ADJUDICATOR` | any | Full, unredacted packet (`packet()`) — their role is exactly to see both decisions |
| `REVIEWER_A` | any | Full packet — there is no prior verdict to hide from the first reviewer |
| `REVIEWER_B` | `SECOND_REVIEW` (pre-submission) | **Redacted** via `_redact_first_reviewer_verdict()` |
| `REVIEWER_B` | any other state (post-submission) | Full packet — both decisions are now legitimately visible |

`_redact_first_reviewer_verdict()` performs redaction on a deep copy of the full packet, at the service layer — **never** as a UI-only hide:

- Blanks `task.decision`, `task.first_decision`, `task.first_comments`, `task.comments`, `task.consensus_result` to `""`.
- Empties `task.reason_codes` and `task.first_reason_codes` to `[]`.
- Rewrites every `SUBMIT_FIRST` entry in `task.audit_history` in place, blanking its `decision`, `reason_codes`, and `comments` — the event still appears (so Reviewer B can see *that* a first review happened and the task is ready for their independent second review), but carries no content.

## Where this is wired

- `ReviewService.export_packet(task_id, path, reviewer_id=None, role=None)` — when `reviewer_id`/`role` are supplied, uses `packet_for_reviewer`; only the unauthenticated internal `packet()` call (used by QA/reporting/pilot export scripts, which never carry a specific reviewer_id) bypasses redaction, by design.
- `GET /tasks/{task_id}` (`api.py::task_details`) now **requires** `reviewer_id` and `role` as query parameters — there is no unauthenticated path to a task's packet through the API. This was a required change: the previous endpoint called `service.packet()` unconditionally.
- `GET /tasks/{task_id}/export` — same requirement.

## What does not leak

- **Metrics** (`ReviewService.metrics()`) only ever returns aggregate counters (`by_type`, `by_priority`, `by_state`, `by_diagnosis`, `by_antibiotic`, `by_safety_category`, `total`, `total_pending`, `average_review_time_seconds`) — there is no per-task field, so no channel exists for a specific verdict to leak through metrics before Reviewer B submits.
- **Error messages**: no `InvalidTransition`/`ReviewerValidationError` message embeds a reviewer's decision content.

## Test coverage

`test_governance_hardening.py::test_09_10_reviewer_b_packet_omits_a_verdict_and_rationale`, `test_11_history_does_not_leak_a_verdict`, `test_12_metrics_do_not_leak_verdict_before_b_submission`; `test_pilot_safety_checks.py::test_reviewer_b_no_longer_sees_reviewer_a_verdict_before_submitting`.
