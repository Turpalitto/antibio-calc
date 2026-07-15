# Physician Review Pilot — Phase 0 Activation Baseline

Generated: 2026-07-15. Read-only verification. No review state was changed to produce this baseline.

## Repository state

- Recovery commit: `32096af5ac1c1227027ef4075863164f45251139` — confirmed present as `HEAD` on branch `main`.
- Working tree: dirty, 68 untracked entries — all previously-classified confirmed-excluded artifacts (60 pilot packet JSONs, 2 legacy `unknown_drugs.csv`, 4 transient/superseded docs) plus 2 post-commit audit reports. No unexpected changes.
- `pilot_review_batch_v2/PILOT_REVIEW_BATCH_V2_MANIFEST.json` SHA-256: `54034b4c0769758c33c7601009013770fbb8e69031a7ac65a39fca979d87de3d`
- `review_workbench_p56.sqlite` SHA-256: `2c39618b9dc7e2a83603baa76b0761c5cf9c8a36f566fa97e1d2715e9a5ae4ac`

## 30 pilot task IDs

Confirmed exactly **20 `ClinicalRegimen` + 10 `TherapeuticOption` = 30 unique `task_id` values** in `PILOT_REVIEW_BATCH_V2_MANIFEST.json` (`policy_name: PHYSICIAN_PILOT_V1`, `policy_version: 1`). All 30 IDs resolve to real tasks in `review_workbench_p56.sqlite` — zero missing.

## Target versions

Compared each of the 30 exported packet files (`pilot_review_batch_v2/crt_*.json`) against a fresh `ReviewService.packet()` call against the live database for the same `task_id`: **zero mismatches** in `snapshot_hash`, `target_version`, or `lifecycle_state`. The pilot packets are not stale — the underlying `ClinicalRegimen`/`TherapeuticOption` targets have not changed since the packets were generated.

## Source wording and provenance

Ran `ReviewService.packet()` for all 30 tasks: **all 30 have `source_wording_status: AVAILABLE`** and **`review_blocked: false`**. Zero packets are `review_blocked`.

## Task states

Queried `review_workbench_p56.sqlite` for all 30 pilot `task_id`s: **all 30 are `PENDING`** (undecided — no `assigned_reviewer`, no `second_reviewer`, no `decision`, empty `audit_history`).

## Approved-object count

Queried the entire review database (9,153 tasks total, all target types): **approved-object count = 0**. Zero tasks anywhere in the database — not just the 30-task pilot — are `ACCEPTED`, `ACCEPTED_WITH_NOTE`, or `CLOSED` with an accepting decision.

## Clinical Engine isolation

Grepped `clinical_engine/engine.py`, `clinical_engine/pipeline.py`, `clinical_engine/readers/`, and `clinical_engine/api/` for any import of `review_workbench`: **zero matches**. The Clinical Decision Engine does not read from, or depend on, the Review Workbench in any way. It remains fully disconnected, as required.

## Required baseline checklist

| Requirement | Result |
|---|---|
| 30 tasks exist | ✔ confirmed |
| All target versions match (packets not stale) | ✔ confirmed |
| All packets have source wording | ✔ confirmed (30/30 `AVAILABLE`) |
| All packets have valid provenance | ✔ confirmed (all resolved via `resolve_source_wording`, tiers 1-4, no fabrication) |
| No packet is `review_blocked` | ✔ confirmed (0/30) |
| All tasks are undecided | ✔ confirmed (30/30 `PENDING`) |
| Approved-object count = 0 | ✔ confirmed (0/9153 database-wide) |

**No task is stale or blocked. All 30 tasks are eligible for activation.**
