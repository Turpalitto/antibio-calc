# ANTIBIO — Engineering Retrospectives
## Permanent artifact · started 2026-07-14

> After every non-trivial Root Cause fix, a retrospective is written here. The goal is to convert a
> single bug fix into a **systemic** improvement: not just "we fixed it" but "this class of bug can
> no longer reach production." Each retrospective answers five questions:
> 1. What let this reach production? 2. Why didn't tests catch it? 3. What invariants were missing?
> 4. What tests/guards were added? 5. How is the whole class prevented going forward?

---

## RC-001 — Structured tables silently never reached the Knowledge Base

**Fix summary:** `layout.py::_extract_table_with_transformers` referenced `tbbox` before assigning
it → `NameError` on every detected table → swallowed by a bare `except: pass` → 0 structured
tables → KB built from flat text only. Fixed the ordering; made the swallow-points log. Verified
structured_tables 0→29 and KB table_row 0→4 on a real table-heavy PDF; regression tests added.

**1. What let this reach production?**
- A **bare `except Exception: pass`** around the entire table-extraction body turned a hard,
  deterministic `NameError` into a silent "no tables found." The failure was indistinguishable from
  a legitimately table-free page.
- The metric that *would* have exposed it (`structured_tables` count, `layout_engine` provenance)
  was collected but **never asserted or monitored** — the P4.4/P4.5 reports quoted object counts
  and "0 conflicts", not table-origin provenance. Reports trusted their own summaries instead of
  querying raw provenance.
- Layout is CPU-expensive, so nobody re-ran it critically; the cost created a disincentive to
  verify, and the swallowed error meant it "worked" (produced a KB) every time.

**2. Why didn't tests catch it?**
- There were **no tests for the layout table path at all** (`src/tests/` had no layout/table test).
- The existing `test_real_pdf_if_available` asserted only `stats["added"] >= 0` and
  `"total_objects" in stats` — it would pass with a 100% flat-text KB. No test asserted that
  **table-derived provenance reaches the KB**.
- No test exercised `_extract_table_with_transformers` with a detection present, so the
  unbound-variable path was never executed in CI.

**3. What invariants were missing?**
- **"Layout must not fail silently"** — a swallowed exception in an expensive, value-critical stage
  must at minimum be logged and counted.
- **"If P4.5 layout ran, table-origin provenance must be present for table-heavy input"** — a
  pipeline-level yield invariant, not just a unit assertion.
- **"Reports are derived from raw artifacts, not self-reported summaries"** — a governance
  invariant (now in `docs/governance/` truth order + Definition of Done).

**4. What tests/guards were added?**
- `src/tests/test_layout_table_provenance.py`:
  - fast deterministic: table cell → semantic → KB → SQLite `table_row` present (no models).
  - real: layout on a table-heavy PDF yields >0 structured tables.
- Observability: the two `except: pass` in `layout.py` now `logger.warning(...)`.
- Reusable diagnostics retained: `diagnose_pipeline.py` (stage tracer) + `semantic_yield_audit.py`
  (yield + loss classification + CKY).

**5. How is the whole class prevented?**
- **Ban silent swallowing in value stages:** bare `except: pass` in extraction/layout/semantic is
  now a review red flag; failures must log + increment a metric. (Candidate lint rule — see RCR.)
- **Yield invariants over count invariants:** CKY (`CLINICAL_KNOWLEDGE_YIELD.md`) is now the
  headline metric; a change that drops CKY on any axis is a regression even if object counts rise.
- **CI gate (RC-007):** once CI exists, the fast provenance test + a CKY-floor check run on every
  change, so a future "tables silently stop flowing" regression fails the build.
- **Governance:** milestone closure now requires re-deriving numbers from raw artifacts (DB/logs),
  which is exactly what surfaced this defect.

*(Next retrospective appended here after the next Root Cause fix.)*
