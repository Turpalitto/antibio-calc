# RC-030 / C6.8 Part VIII-IX — Owner Queue Rebuild, C5 Modes, Taxonomy Check

## Queue rebuild (Phase 17-18)

The old (C6.7) generated exact-link/single-candidate queues are **discarded as current authority** — new queues built from scratch from the C6.8-reconciled 117-candidate pool (`generated/rc030_c68/final_117_buckets.json`):

| Queue | File | Size | Selection criteria |
|---|---|---|---|
| Exact-link confirmation | `RC030_C68_EXACT_LINK_OWNER_QUEUE.json` | **36** | Survives both C6.7's independent Pass A audit AND C6.8's deterministic basis repair |
| Single-candidate | `RC030_C68_SINGLE_CANDIDATE_QUEUE.json` | **15** | SAFE_SINGLE_CANDIDATE, not otherwise routed |
| Unit-basis review | `RC030_C68_UNIT_BASIS_QUEUE.json` | **43** | `COMPATIBLE_BASIS_UNSPECIFIED` — basis genuinely ambiguous, needs a human to read the source |
| Table review | `RC030_C68_TABLE_REVIEW_QUEUE.json` | **8** | Table-derived source text, needs table-layout tooling not available here |
| Engine-review-required | `RC030_C68_ENGINE_REVIEW_QUEUE.json` | **11** | Engine says exact post-repair, but the independent Pass A audit separately flagged a structural concern (competing range/table-shape/wrong-anchor) unrelated to dose basis |
| Source-defect | `RC030_C68_SOURCE_DEFECT_QUEUE.json` | **0** | Both known defects (5688, 6052) fixed in Part IV; empty by construction, not silently omitted |
| **Total** | | **113** | + 4 rejected (not queued anywhere) = 117 |

Every record: `evidence_hash` unique (verified, 0 duplicates across all 6 files), `pdf_hash`, `context_before`/`context_after` where applicable, `calculation_eligibility: BLOCKED`, `clinically_approved: false`, `authoritative_migration_allowed: false`. **0 forbidden/preloaded verdict keys** (`owner_verdict`, `canonical_verdict`, `ui_action`, `human_fidelity_verdict`) in any record — verified by direct key-scan before this report was written. Queues are not mixed silently — each is its own file with its own `queue` name and `selection_criteria`.

## C5 compatibility (Phase 19)

Two new modes added, only where a real, non-empty queue needed one (per the owner's "add modes only where needed" — no mode was added for the empty source-defect queue):

- `range-unit-basis-review` — dedicated banner explicitly warning the reviewer not to assume PER_DAY/PER_DOSE unless the source states it.
- `range-table-review` — dedicated banner warning the reviewer this is a flattened table row, not prose.

Verified, not assumed: isolated localStorage keys (inherited for free via the existing `${MODE}`-parametrized `STORE_KEY`/`CURRENT_IDX_KEY` template literals — no template change needed beyond the banner text), no verdict preselection (unchanged builder-level refusal check), C4-valid events (unchanged `UI_ACTION_TO_CANONICAL` mirror), append-only corrections (unchanged), deterministic export (unchanged), no owner data committed (unchanged), generated HTML excluded (unchanged `.gitignore`), no external requests (re-verified: `test_template_has_zero_network_code`/`test_template_has_no_external_urls` still pass), no Clinical Engine dependency (unchanged).

4 new test cases (parametrized ×2 modes across 3 existing parametrized tests, i.e. 8 additional test executions) extending the existing C6.7 range-review-mode test coverage. **Full C5 suite: 37/37 passing** (was 31/31 before this program), 0 regressions.

## Verdict taxonomy sufficiency (Phase 20)

Re-checked `dose_verification_sandbox/validation_unit.HUMAN_FIDELITY_VERDICTS` and `verdict_taxonomy.py` against the C6.8-specific concerns:

| Required capability | Existing verdict | Sufficient? |
|---|---|---|
| Range correct, explicitly per-day | `CORRECT_RANGE_DAILY` | ✅ |
| Range correct, explicitly per-dose | `CORRECT_RANGE_SINGLE` | ✅ |
| Wrong unit/dose-basis anchor | `WRONG_DOSE_ANCHOR` | ✅ (already covers a range linked to the wrong basis, same as wrong drug/wrong clause) |
| Range correct but basis unresolved | `REMAINS_AMBIGUOUS` | ✅ (already governed, already excluded from the scorable-precision denominator — exactly the right semantics for "I can't tell if this is per-day or per-dose from the source") |
| Source quote missing/corrupted | `SOURCE_INCOMPLETE` / `SOURCE_CORRUPTED` | ✅ |
| Table required | `TABLE_CONTEXT_REQUIRED` | ✅ |

**No taxonomy change applied.** This confirms and extends C6.7's own conclusion (`RC030_C67_OWNER_QUEUES_AND_C5_MODES_REPORT.md`), which had already flagged this exact scenario and recommended `REMAINS_AMBIGUOUS` as the correct existing verdict for basis-unresolved records rather than inventing `CORRECT_RANGE_BASIS_UNRESOLVED`/`WRONG_DOSE_BASIS`. C6.8's `RC030_C68_UNIT_BASIS_QUEUE.json` reviewers should use `REMAINS_AMBIGUOUS` when the source genuinely doesn't state a basis, and `WRONG_DOSE_ANCHOR` when it does state one that conflicts with the structured field — both already exist, already scored correctly, and require zero schema/migration/UI-mapping work, per the owner's explicit prohibition on taxonomy changes made merely for convenience.
