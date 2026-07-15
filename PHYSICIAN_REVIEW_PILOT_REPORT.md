# Physician Review Pilot Report — P5.6

Generated: 2026-07-15. Covers Phases 0-13 of the Physician Review Pilot Execution mandate.

## 1. Pilot baseline

See [PHYSICIAN_PILOT_ACTIVATION_BASELINE.md](PHYSICIAN_PILOT_ACTIVATION_BASELINE.md) in full. Summary: recovery commit `32096af` confirmed present; pilot manifest (`PILOT_REVIEW_BATCH_V2_MANIFEST.json`, SHA-256 `54034b4c...`) and review database (`review_workbench_p56.sqlite`, SHA-256 `2c39618b...`) hashed; all 30 pilot tasks (20 `ClinicalRegimen` + 10 `TherapeuticOption`) confirmed to exist, be non-stale (target version/snapshot hash match exported packets exactly), have available source wording, be unblocked, and be `PENDING`. Approved-object count confirmed 0 database-wide (9,153 tasks total). Clinical Engine confirmed to have zero import dependency on `review_workbench` — fully disconnected.

## 2. Registered reviewer roles

**Zero real reviewers registered.** A reviewer-registration workflow (`clinical_engine/review_workbench/reviewer_registry.py`) was built per Phase 2 — `ReviewerRecord`/`ReviewerRegistry` with the required fields (`reviewer_id`, `display_name`, `professional_role`, `credential_reference`, `organisation`, `authorised_scope`, `active`, `registered_at`, `registered_by`), a `pilot_status()` function, and 10 passing unit tests using synthetic fixture data only. **No reviewer identity was invented or registered as if real.** The registry is empty in this repository.

**`pilot_status = WAITING_FOR_REVIEWERS`.**

## 3. Activated tasks

All 30 pilot tasks pass every Phase 3 technical activation check (task_id exists, target_id exists, target_version matches, target unchanged, packet canonical, source wording present, provenance valid, validation failures/conflicts surfaced via `packet()`, interaction status correctly `NOT AVAILABLE`, decision vocabulary matches governance). **Activation result for all 30 tasks: `READY_FOR_REVIEW`.** Zero `NEEDS_INFO`/`SOURCE_MISSING`/`STALE_VERSION`/`PROVENANCE_INVALID`/`GOVERNANCE_BLOCKED`. Activation is a technical readiness classification only — it does not constitute or imply acceptance of any task.

## 4. Completed first reviews

**0.** No Reviewer A decision has been recorded for any of the 30 tasks (or any of the 9,153 tasks database-wide). No decision was fabricated.

## 5. Completed second reviews

**0.** Same reason.

## 6. Consensus results

**0.** No consensus is possible without two independent first/second reviews.

## 7. Adjudications

**0.**

## 8. Corrections proposed

**0.** No `ClinicalCorrectionProposal` mechanism exists in the codebase yet (Phase 9 of the pilot mandate) — not built in this session, since no reviewer exists yet to identify an error requiring one, and building a data-mutation-adjacent workflow without a concrete first use is premature relative to this session's actual blocker (no reviewers).

## 9. Approved objects

**0 ClinicalRegimen, 0 TherapeuticOption.** Approved-object count is unchanged from baseline.

## 10. Rejected objects

**0.**

## 11. Needs-info objects

**0.**

## 12. Workflow defects (found during Phase 12 safety testing)

Three real defects were found while proving the Phase 12 negative-test scenarios, all evidenced by a passing test that documents the *current, unsafe* behavior rather than a safe rejection (`clinical_engine/review_workbench/tests/test_pilot_safety_checks.py`). None of these were fixed in this session — they are governance-workflow decisions warranting explicit owner/architect sign-off, not incidental bugs safe to patch silently:

1. **No registry enforcement at the service layer.** `ReviewService.claim()`/`submit_first_review()`/etc. accept any string as `reviewer` — there is no dependency on `ReviewerRegistry`. An invented identity is not rejected by the API/service today (`test_fake_reviewer_identity_not_rejected_by_service_layer`). Practical impact today: none, because the registry is empty and no real workflow will be run against it. **Must be wired before Phase 4 begins for real** (either `ReviewService` takes a registry dependency, or the API layer validates `reviewer_id` against the registry before calling the service).
2. **Second reviewer can see the first reviewer's verdict.** `ReviewService.packet()` (called directly by `GET /tasks/{id}` in `api.py`) returns the full task dict, including `task.decision` and `audit_history`, unconditionally — once a task reaches `SECOND_REVIEW`, calling `packet()` reveals Reviewer A's decision (`test_reviewer_b_can_see_reviewer_a_verdict_via_packet_before_submitting`). This breaks the independence requirement in Phase 5 ("Reviewer B must not see Reviewer A's final verdict before submitting their own verdict"). **Must be fixed (role/state-aware redaction of `decision`/`audit_history` while `SECOND_REVIEW` is pending and the caller is not Medical QA Lead/Adjudicator) before any real second review is performed through the existing API.**
3. **Consensus ACCEPT reports PHYSICIAN_APPROVED before Medical QA Lead sign-off.** `governance_state(ReviewState.ACCEPTED)` and `governance_state(ReviewState.ACCEPTED_WITH_NOTE)` both already return `"PHYSICIAN_APPROVED"` — there is no requirement that a Medical QA Lead has performed the Phase 8 final governance check (`close()`, restricted to `MEDICAL_QA_LEAD`) first (`test_consensus_accept_reports_physician_approved_before_qa_close`). This directly contradicts the pilot mandate: "A consensus review result is not automatically PHYSICIAN_APPROVED... Only after this gate may an eligible ClinicalRegimen transition to PHYSICIAN_APPROVED." **This is the most important of the three findings and must be resolved (e.g., `governance_state` should require `CLOSED` with an accepting `decision`, not `ACCEPTED`/`ACCEPTED_WITH_NOTE` alone) before any real approval is trusted to reflect actual Medical QA sign-off.**

12 of 15 Phase-12 negative-test scenarios already fail closed correctly (self-review forbidden, administrator cannot submit/close/adjudicate, stale target version rejected, missing source wording flagged `review_blocked`, non-adjudicator cannot adjudicate, target snapshot immutable at the database level, `TherapeuticOption` approval stays isolated from the disconnected Clinical Engine, interaction-check status is a hardcoded literal with no override path). Full results in `test_pilot_safety_checks.py` (15/15 tests pass — 12 documenting genuinely safe behavior, 3 documenting the gaps above).

## 13. Provenance defects

**0 among the 30 pilot tasks** — all have `source_wording_status: AVAILABLE` and `review_blocked: false` (see baseline).

## 14. Review-time metrics

Not applicable — no review has started.

## 15. Reviewer feedback

Not applicable — no reviewer has been registered or has interacted with the system.

## 16. Golden Dataset eligibility

See [GOLDEN_DATASET_APPROVED_ELIGIBILITY.md](GOLDEN_DATASET_APPROVED_ELIGIBILITY.md). All 7 cases: `APPROVED_DATA_NOT_AVAILABLE` (approved-object count is 0). None run. No expected answer changed.

## 17. Remaining P5.6 blockers

1. **No real Reviewer A / Reviewer B registered.** The owner must register real, named physicians with real professional information via `ReviewerRegistry` before any decision can be legitimately recorded.
2. **Registry enforcement gap** (finding 1 above) — should be wired into the service/API layer before real review begins.
3. **Second-reviewer blinding gap** (finding 2 above) — should be fixed before real second review begins.
4. **Consensus/QA-gate governance gap** (finding 3 above) — should be fixed before any real approval is trusted.
5. Two post-recovery-commit audit documents (`P56_STAGED_CONTENT_AUDIT.md`, `FRESH_CLONE_REPRODUCIBILITY_REPORT.md`) remain uncommitted, per [POST_RECOVERY_EVIDENCE_CLASSIFICATION.md](POST_RECOVERY_EVIDENCE_CLASSIFICATION.md) — classified as governance evidence to track in a future documentation-only commit, deliberately not created during this pilot session.
6. `ClinicalCorrectionProposal` (Phase 9 mechanism) does not yet exist — needed once real reviewers start identifying errors, not before.

## 18. P6 status

**BLOCKED.** Unchanged. Approved-object count remains 0. Clinical Decision Engine remains disconnected. No object has become `PHYSICIAN_APPROVED`. P6 requires separate, explicit authorization after all entry gates (including a real completed pilot) are independently verified — none of that has happened yet.

---

## Pilot start gate — verified

| Gate | Status |
|---|---|
| Repository recovery complete | ✔ |
| Fresh clone complete | ✔ |
| Technical packet line complete | ✔ (30/30 `READY_FOR_REVIEW`) |
| Real Reviewer A registered | ✘ — **not met** |
| Real Reviewer B registered | ✘ — **not met** |
| Reviewer identities distinct | N/A (none registered) |
| Pilot packets immutable and version-pinned | ✔ |
| Audit logging active | ✔ (append-only `AuditEvent` history, verified by existing test suite) |
| No task is `review_blocked` | ✔ (0/30) |
| Approved-object count initially 0 | ✔ |
| Clinical Engine disconnected | ✔ |

## Final verdict

**A) PILOT WAITING FOR REAL REVIEWERS**

The technical activation line is fully complete and verified (baseline, task readiness, audit logging, isolation). No clinical review can begin, and none was simulated or fabricated, because no real Reviewer A or Reviewer B has been registered. Three workflow/governance gaps were found during Phase 12 negative testing and must be addressed before real review proceeds through the existing API — most importantly the consensus-to-`PHYSICIAN_APPROVED` gap, which currently bypasses the mandated Medical QA Lead sign-off.

P6 remains BLOCKED.
