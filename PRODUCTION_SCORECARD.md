# ANTIBIO — Production Scorecard

## P5.6 acceptance addendum — 2026-07-15

| Category | Verdict | Evidence |
|---|---|---|
| Secrets in working tree | PASS | pattern scan 0; env contract/fail-fast |
| Credential rotation | **BLOCKING** | owner action not completed |
| Repository reproducibility | **BLOCKING** | only 19 tracked files; fresh clone cannot reproduce source |
| Dependencies | PASS | uv lock 194; pip check 36 compatible |
| Canonical pytest | PASS | 1373 collected; 1371 passed, 0 failed |
| Golden Dataset | WARNING | 0/7; all 7 fixture-invalid RCA proven |
| KB identity/lineage | PASS/WARNING | fuzzy writes blocked; exact v2 code/tests PASS; clean migration not run |
| Dose-unit safety | PASS | 8,412 classified; 0 silent unit insertion |
| Corpus | PASS/WARNING | 250 explicit states; 58 REVIEW_REQUIRED |
| Clinical issue registry | PASS | 12,918 rows; original 4,506 preserved |
| Review Workbench | PASS | 9,153 tasks; 46 targeted tests PASS |
| Physician approval | **BLOCKING FOR P6** | 0 approved, 0 completed reviews |
| Governance | PASS/WARNING | canonical current truth created; history retained |
| Clinical Engine isolation | PASS | disconnected; no engine logic changes |
| Performance | WARNING | queue p95 21.061 ms; metrics median 1,157.222 ms |

**P5.6 overall: BLOCKING / NOT COMPLETE. P6: BLOCKED.** Historical P4.4 certification follows unchanged.

---
## P4.4 Production Knowledge Base · STRICT · evidence-based · FINAL

> Every category is **PASS / WARNING / FAIL**, backed by a measured artifact. No optimism, no
> assumptions, no interpretation — evidence only, per the Release Readiness Review Board mandate.
> Scope: this scorecard certifies the **Production Knowledge Base build** (`kb_p44.db`). It does
> NOT certify the Clinical Decision Engine's consumption of it — see RC-019 below.

**Status:** FINAL — full corpus rebuild complete (192/192), all audits executed on the finished KB.

---

## Scorecard

| Category | Verdict | Evidence / metric | Source |
|----------|:-------:|-------------------|--------|
| Architecture | **PASS** | Layered Extraction→Layout→Semantic→Knowledge preserved; no layer bypass; provenance contract now canonical (spec + 1:1 mapper). **WARNING flag:** the Knowledge layer is not yet consumed by the Clinical Decision Engine layer (RC-019) — an inter-milestone integration gap, not an internal defect. | code review + `ENTERPRISE_ARCHITECTURE_REVIEW.md` |
| Clinical Governance | **PASS** | RC-012 (original wording) FIXED & verified: INV-09 = 0/100,854 violations (was 1,442). No blocking governance invariant fails. Advisory: INV-05 dose-unit (RC-08, tracked). | `inv_report_FINAL.json` |
| Knowledge Integrity | **PASS** | 31,336 objects (28,368 active / 2,968 superseded, correctly versioned); 6,574 reviews correctly queued (not silently dropped); 0 duplicate (id,version) rows; RC-017 cell-collapse regression test green at full scale (0 same-page multi-cell collapses found). | `inv_report_FINAL.json`, DB query, regression suite |
| CKY (yield) | **PASS (baseline established)** | `CKY.overall=10.3%`; per-axis + per-source captured; dominant loss = Duplicate 86.5% (expected at corpus density); `CKY.tables=1.1%` confirms RC-009 as measured fact. Baseline is the deliverable here, not a threshold — gate is "established," met. | `pr008_yield_FINAL.json` |
| Coverage (capability) | **PASS (baseline established)** | dose/route/contraindications/evidence=100%; drug=97.9%; alternatives/diagnosis/first_line/renal/pregnancy partial; duration/frequency/pediatric=0% (real gap, registered). Baseline established as required. | `coverage_FINAL.json` |
| Architectural Invariants | **PASS** | 0 blocking failures across INV-01/02/03/08/09/10/12. INV-05 advisory-WARN only. | `knowledge_invariants.py` → `inv_report_FINAL.json` |
| Regression | **PASS** | 72 passed, 1 xfailed (expected), 0 failed. Includes RC-017 regression guard and the real-execution table-provenance test. | `regression_FINAL.log` |
| Performance | **WARNING** | Full rebuild is multi-hour, single-process, CPU-bound (per-PDF up to ~1500s on table-dense guidelines). Functionally fine for the current milestone; flagged as a P7 bottleneck (`ENTERPRISE_ARCHITECTURE_REVIEW.md` EAR-5) — not a P4.4 blocker. | build log |
| Security | **WARNING** | Not independently re-audited this cycle; no new findings surfaced. Hardcoded local paths (`C:\clinrec_downloader`) noted as a portability/security-posture item for P7 packaging, not a P4.4 defect. | code review (light) |
| Documentation | **PASS** | `P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md` regenerated with real final numbers (was stale 116/204-object claims); `ROOT_CAUSE_REGISTER.md`, `AI_LOG.md`, `NEXT_TASK.md`, `DECISIONS.md` synchronized this cycle. | doc audit (this pass) |
| Technical Debt | **WARNING** | Register active and current; RC-002/004/005/007/010/011 open (non-blocking); RC-019/020/021/022 newly registered (architecture-level, scoped to P5+). | `ROOT_CAUSE_REGISTER.md` |
| Root Causes | **PASS (process)** | RC-001/012/013/014/015/016/017/018 FIXED & VERIFIED at full scale. Every discovered issue has exactly one state (Fixed / Open / Tracked) — none undefined. | register |
| **Overall Readiness (P4.4 Knowledge Base scope)** | **PASS — CERTIFIED** | All blocking gates measured PASS. See Closure Gates below for the exact evaluation. | — |

---

## Closure gates (all must be ✔ to close P4.4)

| Gate | State | Evidence |
|------|:-----:|----------|
| rebuild complete (192/192) | ✔ | checkpoint 192/192, report JSON written, 0 tracebacks |
| regression green | ✔ | 72 passed, 1 xfailed, 0 failed |
| CKY baseline established | ✔ | `pr008_yield_FINAL.json` |
| Coverage baseline established | ✔ | `coverage_FINAL.json` |
| no blocking invariant | ✔ | 0 blocking violations (`inv_report_FINAL.json`) |
| Root Cause Register updated | ✔ | every finding has exactly one state |
| RC-012 (+013/014/015) resolved | ✔ | verified at full scale: INV-09 0 violations, 0 nulls across all provenance fields |
| documentation synchronized | ✔ | report regenerated, register/AI_LOG/NEXT_TASK/DECISIONS updated this pass |
| production audit passed | ✔ | this scorecard (Phases 2–10 of the Release Readiness Review) |
| engineering audit passed | ✔ | Independent Auditor pass (2026-07-14, found+fixed RC-017/018) + this final measured pass |
| production scorecard PASS | ✔ | all rows above PASS or non-blocking WARNING |

**Current determination: P4.4 (Production Knowledge Base) is CERTIFIED — all closure gates ✔.**

**Explicit non-blocking caveat (do not lose this in the closure):** RC-019 — the Clinical Decision
Engine does not yet read `kb_p44.db`. This does not fail P4.4's own definition of done (build a
reproducible, versioned, provenance-complete Knowledge Base — which is what was measured), but it
means closing P4.4 does **not** yet mean patients/physicians receive traceable recommendations end
to end. That integration is explicitly P5/P6 scope (`ANTIBIO_ROADMAP_P5_P10.md`,
`P5_KNOWLEDGE_PLATFORM_RFC.md`) and RC-019 is the highest-ranked open item in the register.

---

## Notes
- Scorecard was regenerated from measured artifacts produced in this final audit pass, not
  hand-waved: `inv_report_FINAL.json`, `pr008_yield_FINAL.json`, `coverage_FINAL.json`,
  `regression_FINAL.log`, `p44_kb_rebuild_FINAL_20260714.json`.
- A single FAIL in Clinical Governance or Invariants would have blocked closure regardless of other
  PASSes (safety-overrides-all, per `docs/governance/CLINICAL_GOVERNANCE.md`); none occurred.
- WARNING rows (Performance, Security, Technical Debt) are non-blocking by definition but are not
  discarded — they feed the Root Cause Register ranking for the next work cycle.
