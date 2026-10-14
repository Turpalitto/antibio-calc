# RC-030 Full Repair — Pre-Staging Audit

**Nothing staged. Nothing committed. `git add` not run.** Proposed separate commits below; generated SQLite/replay artifacts are EXCLUDED from all of them.

## Commit C1 — deterministic fail-closed parser fixes + tests
```
dose_verification_sandbox/semantics_parser.py
dose_verification_sandbox/semantics_models.py
tests/dose_verification_sandbox/test_semantics_parser.py
tests/dose_verification_sandbox/test_deterministic_repair.py
```
Verified standalone: with C2 stashed back to HEAD (old `medical_normalizer`), C1's test files pass 43/43 on their own — C1 does not depend on C2 landing first.

## Commit C2 — normalizer additive range preservation + tests
```
medical_normalizer/drug_parser.py
medical_normalizer/models.py
medical_normalizer/tests/test_drug_parser.py
```
Correction from the prior draft of this audit: two normalizer-specific tests (`test_normalizer_preserves_range_upper_bound`, `test_normalizer_scalar_backward_compatible`) were found living inside C1's `test_deterministic_repair.py`, which meant C1 would ship a test that depends on C2's not-yet-committed code. Moved to `medical_normalizer/tests/test_drug_parser.py` as `test_dose_range_preserves_upper_bound` / `test_dose_scalar_backward_compatible`, alongside the existing `test_dose_range` (which already asserts the legacy scalar behavior). Full normalizer suite: 825 passed.
## Commit C3 — governed reports + reprocess manifest (NO generated clinical SQLite)
```
RC030_FULL_REPAIR_BASELINE.md
RC030_FULL_REPAIR_BASELINE.json
RC030_FULL_REPAIR_IMPLEMENTATION_REPORT.md
RC030_FULL_REPAIR_PILOT_REPLAY_REPORT.md
RC030_FULL_REPAIR_CORPUS_IMPACT.md
RC030_DEFECT_CLUSTER_REGRESSION_REPORT.md
RC030_RANGE_REBUILD_INTEGRITY_REPORT.md
RC030_MAXIMUM_RANGE_DISAMBIGUATION_REPORT.md
RC030_AUTHORITATIVE_RANGE_MIGRATION_PROPOSAL.md
RC030_FULL_REPAIR_IMPACT_MATRIX.md
RC030_FULL_REPAIR_PRESTAGING_AUDIT.md
RC030_RANGE_REPROCESS_MANIFEST.json
```

## Excluded from every commit (class J/G/F)
- `generated/rc030_range_rebuild/*.sqlite` — experimental non-authoritative DB (also `*.sqlite`-gitignored)
- `generated/rc030_recovery/**` — replay/interface artifacts
- `*.sqlite`, `*.db`, `*.pdf` — never committed
- `RC030_FULL_REPAIR_PILOT_REPLAY.json`, `RC030_FULL_REPAIR_CORPUS_IMPACT.json`, `RC030_RANGE_REBUILD_DIFF.json`, `RC030_MAXIMUM_RANGE_DISAMBIGUATION.json` — generated replay artifacts (reports summarize them)
- All prior-turn Part III artifacts (owner interface, AI audit files) — unrelated to this repair, owner decision K

## Scans (run over C1+C2+C3 allowlist)
- secret scan: 0 matches
- personal-path / C:\ANTIBIO / C:\clinrec_downloader / C:\Users scan: 0 matches (verified below)
- DB/PDF/model/cache in allowlist: 0
- large-file (>500KB) in allowlist: 0
- clinical source-value diff (experimental vs authoritative): 0 clinical-field changes (RC030_RANGE_REBUILD_INTEGRITY_REPORT.md)
- synthetic-data leakage: none (reports reference real regimen IDs only)

Stop before staging — owner approval required for each commit.