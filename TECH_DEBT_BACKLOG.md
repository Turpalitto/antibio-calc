# ANTIBIO — Technical Debt Backlog

> Mandated by `ANTIBIO_REPOSITORY_INTELLIGENCE_PROTOCOL.md` ("Always maintain a prioritized
> technical debt backlog"). Evidence-based only — every item cites what was actually observed in
> the repository. Priority: **P0** blocks production integrity · **P1** high maintenance cost ·
> **P2** hygiene/clarity. Status: OPEN / IN PROGRESS / RESOLVED.
>
> Created 2026-07-14 during governance onboarding + P4.4 audit. This is a living document.

---

## P0 — Production integrity

### TD-001 — `kb_p44.db` was a non-reproducible accumulation — IN PROGRESS
**Evidence:** at audit (2026-07-14) the DB held 1836 objects / 138 conflicts / 138 open reviews
while its checkpoint recorded only 3 processed PDFs; report claimed 116–204 objects, 0/0
conflicts/reviews. DB was the union of many untracked experimental runs → not a deterministic
function of the corpus. Violates reproducibility/auditability mission.
**Action:** old DB archived (`kb_p44_ARCHIVED_accumulated_20260714.db`); clean full-corpus rebuild
running into fresh `kb_p44.db`. **Closes when** rebuild completes + report regenerated from measured
data + audited.

### TD-002 — KnowledgeObject schema drift, no migration path — OPEN
**Evidence:** 204 of 1836 objects in the archived DB had `knowledge_type = NULL`; the model was
enhanced mid-stream (added knowledge_type/clinical_domain/validation_status/etc.) without migrating
existing rows. Real table is `objects`; several docs/report snippets call it `knowledge_objects`.
**Proposed fix:** a versioned schema + one idempotent migration tool (not ad-hoc ALTERs); a single
documented schema-of-record in `src/pipeline/knowledge_base.py`. Aligns with protocol "manual
migration → migration tool."

---

## P1 — High maintenance cost

### TD-003 — Checkpoint/DB coupling defect in build_p44_kb.py — RESOLVED (2026-07-14)
**Evidence:** `CHECKPOINT` was a hardcoded module constant independent of `--db`; root cause of
TD-001's drift and a blocker to parallel/independent builds.
**Fix applied:** `checkpoint_path_for(db_path)` → `<db>.checkpoint.json`, threaded through
load/save/main; also removed a deprecated `datetime.utcnow()`. Compile-checked.

### TD-004 — Repo root cluttered with throwaway scripts + run artifacts — OPEN
**Evidence (measured 2026-07-14):** repo root contains 20 `_p44_*.py`/`_p45_*.py`/`_kb_*.py`-style
one-off scripts, 19 `*.log` files, 12 `p44_*/p45_*.json` artifacts, 3 overlapping `kb_*.db` files.
Violates protocol "avoid one-time scripts" + "obsolete files." Makes the real entry points
(`build_p44_kb.py`, `production_reprocessor.py`, `main.py`) hard to find.
**Proposed fix:** (a) move run artifacts (logs/json/db) to an ignored `artifacts/` or `runs/` dir;
(b) delete or fold the `_*.py` probes into a proper `tools/` package or tests; (c) extend
`.gitignore`. **Do not delete blindly** — inventory first, confirm nothing is an entry point.

### TD-005 — Overlapping knowledge DBs with unclear ownership — OPEN
**Evidence:** `kb_final.db`, `kb_p44.db`, plus the archived DB coexist at root with no documented
authority order. Clinical Governance requires a single authoritative source.
**Proposed fix:** declare `kb_p44.db` (post clean rebuild) the single source; document `kb_final.db`
status (archive/deprecated) in PROJECT_STATE; move non-authoritative DBs out of root.

---

## P2 — Hygiene / clarity

### TD-006 — Documentation drift across audit reports — OPEN
**Evidence:** P4.4 report internally contradicts itself (116 vs 204 objects); ROADMAP said P4.4
"COMPLETE" while PROJECT_STATE said "IN PROGRESS" (now reconciled via constitution addendum). Four
`P4*.md` audit reports at root with overlapping scope.
**Proposed fix:** regenerate the P4.4 report from measured rebuild data; add a doc-sync check
(protocol "manual documentation updates → documentation synchronizer") that greps milestone status
across ROADMAP/PROJECT_STATE/NEXT_TASK for disagreement.

### TD-007 — No automated milestone doc-consistency gate — OPEN
**Evidence:** the P4.4 status contradiction survived because nothing enforces agreement between the
five handoff docs. Constitution §8 asks for it manually; protocol asks to automate it.
**Proposed fix:** small `tools/doc_consistency.py` that fails if a milestone has conflicting
COMPLETE/IN-PROGRESS status across governing docs. Run in the milestone-closure gate.

---

## Notes
- Items are addressed opportunistically, respecting the frozen scope (Clinical Engine, medical
  content, bundle schemas — never touched without RFC).
- TD-004/005 involve deleting/moving files that predate this session and were not created by me →
  per repo-safety rules, inventory and confirm before removal; prefer move-to-archive over delete.
