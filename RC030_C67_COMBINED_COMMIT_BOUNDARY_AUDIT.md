# RC-030 / C6.7 — Commit Boundary Audit: 6045eea

Audited commit: `6045eea3a4ec68c7bf2cfa9a31d0306f44a4fcae`
("P5.6 dictionary/PDF discovery and structural analysis for RC-030 ranges")
Parent: `7530b4796b924b17857b3ef7e52bb32e900d0501`

## Files changed (13 total, 1850 insertions / 6 deletions)

| File | Category | Notes |
|---|---|---|
| `RC030_C62_C63_C64_DICTIONARY_PDF_REPLAY_REPORT.md` | I (report) | prose only |
| `RC030_C64_ENHANCED_REPLAY_SUMMARY.json` | I (report/summary) | metrics, no evidence text |
| `RC030_C65_STRUCTURAL_ANALYSIS_AND_V4_REPORT.md` | I (report) | prose only |
| `RC030_C66_OWNER_REVIEW_QUEUE.json` | F (compact manifest) | 123 items, each only `{regimen_id, regimen_version, classification, old_trust, owner_review_required, clinically_approved, calculation_eligibility, authoritative_migration_allowed}` — **no source quotes, no PDF text, no clinical prose**. Confirmed by direct inspection. |
| `RC030_C66_OWNER_REVIEW_QUEUE_AND_C5_COMPATIBILITY_REPORT.md` | I (report) | prose only |
| `RC030_MULTIWORKSTREAM_BASELINE.json` / `.md` | I (report) | prose/metrics only |
| `RC030_MULTIWORKSTREAM_C6_EXACT_ALLOWLIST.md` | I (report) | prestaging allowlist documentation |
| `RC030_MULTIWORKSTREAM_C6_PRESTAGING_AUDIT.md` | I (report) | prestaging audit documentation |
| `dose_verification_sandbox/pdf_evidence.py` | B (PDF discovery/read-only tooling) | new file, pure string functions, no I/O |
| `dose_verification_sandbox/span_attribution.py` | D (attribution engine fix) | 2 deterministic fixes, +43/-6 lines |
| `tests/dose_verification_sandbox/test_pdf_evidence.py` | H (tests) | new, 76 lines |
| `tests/dose_verification_sandbox/test_span_attribution.py` | H (tests) | +18 lines added to existing suite |

No files in categories A (dictionary production data), C (page-context expansion as a *replay* pipeline), E (replay tooling), G (owner-review queue *builder* code), J (generated SQLite/PDF evidence), K (unrelated).

## Correction to the spec's assumed track list

The original architecture named five intended tracks — C6.2 dictionary reconciliation, C6.3 PDF/table recovery, C6.4 enhanced replay, C6.5 structural analysis, C6.6 owner-review queue compatibility. Direct inspection shows:

- **No dictionary code or data changed.** `medical_normalizer/dictionary.py` was not touched by this commit (its last change is an unrelated prior commit `32096af`). The commit reuses the pre-existing, already-governed `UnitNormalizer` — it does not add or edit dictionary entries. So "C6.2 dictionary reconciliation" produced no dictionary diff; it's investigative/documentation only.
- **No replay-driver code exists**, committed or otherwise — the 365-record replay that produced the 74/43 split was run as an uncommitted one-off script (confirmed in Phase 0). So "C6.4 enhanced replay" is represented here only by its *output artifact* (`RC030_C64_ENHANCED_REPLAY_SUMMARY.json`), not by any replay code.
- The actual code payload of this commit is narrower than the five-track description implies: **two deterministic bug fixes in one file** (`span_attribution.py`), **one new pure-function helper module** (`pdf_evidence.py`), and **their tests**. Everything else is documentation/reports/a compact non-evidentiary manifest.

## Import / data-flow graph

```
medical_normalizer.dictionary (DRUG_SYNONYMS, UnitNormalizer)   [pre-existing, unmodified]
        │
        ▼
dose_verification_sandbox.span_attribution.attribute()          [modified: _base_unit() fix, rejection-reason fix]
        │  (no code import — output only, via uncommitted script)
        ▼
generated/rc030_multiworkstream/replay_with_unit_fix_365.json   [uncommitted artifact, outside this commit]
        │  (no code import — data extraction only, via uncommitted script)
        ▼
RC030_C66_OWNER_REVIEW_QUEUE.json                                [committed, category F, IDs/flags only]
        │  (no code import in this commit — build_interface.py, which WOULD consume a queue like
        │   this, was not modified by 6045eea)
        ▼
generated/rc030_recovery/build_interface.py (C5)                 [untouched by this commit]

dose_verification_sandbox.pdf_evidence (find_quote_in_page_text, expand_context)
        — standalone pure-function module, imported by nothing in this commit; intended for
          use by a future replay driver, not yet wired to anything committed.
```

- **Reverse dependency check**: none found — `dictionary.py` does not import `span_attribution`; `span_attribution.py` does not import `pdf_evidence.py`; neither imports `clinical_engine` or `review_workbench` (confirmed by grep and by two dedicated regression tests already present in this same commit: `test_module_has_no_file_write_or_network_or_clinical_engine()` in `test_pdf_evidence.py:71`, `test_module_has_no_io_or_network_or_clinical_engine_imports()` in `test_span_attribution.py:239`).
- **DB write dependency**: none — no `sqlite3.connect`/`open(` call in either new/modified module (asserted by the same two tests, and independently confirmed by direct grep in this audit).
- **Clinical Engine dependency**: none, in the same two modules; confirmed independently in this audit pass (Part I) that `clinical_engine/engine.py`, `pipeline.py`, `readers/`, `api/` still contain zero `review_workbench` imports as of HEAD.
- **Threshold dependency**: none — `TYPES_MEETING_PRECISION_THRESHOLD` is not referenced anywhere in this commit's diff.
- **Secret/personal-path scan**: clean. One personal path (`C:\Users\TURPAL\...python.exe`) was found and *already fixed before this commit landed*, per `RC030_MULTIWORKSTREAM_C6_PRESTAGING_AUDIT.md`'s own "Secret / API key / token scan" section (included in this same commit) — re-verified present and worded as a self-correction, not a leak. `C:\clinrec_downloader` appears throughout but contains no username/credential and is retained as factual root-cause content per the project's own established policy.

## Independent testability

- `pdf_evidence.py` ⟷ `test_pdf_evidence.py`: fully independent, no shared fixtures with `span_attribution` tests.
- `span_attribution.py` fix ⟷ `test_span_attribution.py`: the two fixes (unit-script canonicalization, rejection-reason bug) are each exercised by dedicated new test cases within the same file, distinguishable by diff (+18 lines, additive only — no existing test was modified or deleted).
- The 9 report/manifest files carry no executable code and cannot break a test run.
- **Conclusion: yes, each track (B and D) is independently testable today**, without needing to unwind the commit.

## Rollback-by-path feasibility

Because the changes are file-disjoint (no single file mixes code from two different "tracks" except `span_attribution.py`, which itself contains one coherent logical fix set from one investigation, not multiple bundled fixes from different tracks), any individual file can be reverted in isolation via `git checkout 7530b47 -- <path>` without affecting the others. No history rewrite is needed to achieve this. Verified mechanically:

```
git diff 7530b47 6045eea --name-only   # 13 disjoint paths, no overlapping hunks across "tracks"
```

## Cohesion assessment

The commit message accurately describes the work as a **single investigation** ("Multi-track investigation (C6.2-C6.6)") that happened to *conclude* several things (dictionary already sufficient, PDF corpus location was previously misdiagnosed, two real engine bugs found and fixed, replay re-run, V4 rebuilt, C5 compatibility reconfirmed) — it is not five independently-scoped units of work artificially glued together; it is one root-cause chase whose narrative spans several previously-numbered sub-phases. The *code* payload is small, coherent, and tested. The *documentation* payload is large but inert.

The original architecture's request for five separate commits was not honored, and that is a real process deviation worth recording — but it does not create hidden coupling, untestable state, undocumented reverse dependencies, or an unrevertable unit. The five-way split existed in planning, not in the actual work performed.

## Boundary conclusion

**BOUNDARY_ACCEPTABLE_WITH_DOCUMENTED_COUPLING**

Rationale: no safety-relevant coupling exists (no DB writes, no Clinical Engine import, no threshold mutation, no reverse dependency, per-file rollback is mechanical, both code changes are independently tested). The coupling that *does* exist is procedural — narrative/report files for five planned sub-phases were committed together with the one real code change and its tests, rather than as five separate commits as originally specified. No follow-up modularization commit is required; no history rewrite is warranted. Recommend only that future turns honor the requested commit granularity going forward (documented here, not enforced retroactively).
