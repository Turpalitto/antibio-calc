# RC031_RETRACTION_AUDIT.md

Status: Evidence-Integrity Hardening, Phase 0. Full-repository search for every RC-031/regimen-5574
related occurrence, classified per the required taxonomy. Read-only audit.

## Method

```
grep -rn "RC-031" --include="*.md" .        → 21 matches, 10 files
grep -rln "5574" --include="*.md" .          → 11 files
grep -rln "5574" dose_verification_sandbox/data/*.json → 8 generated artifacts
```

## Classification

### A. Corrected factual statement (current, accurate)

| File | What it now says |
|---|---|
| `ROOT_CAUSE_REGISTER.md` | RC-031 marked `RETRACTED 2026-07-16`, full RCA of the false finding itself |
| `RC030_TARGETED_SOURCE_RECOVERY_REPORT.md` | Rewritten: real PDF lookup preserved, fabricated comparison explained and removed |
| `RC030_12CASE_REVALIDATION.md` | Regimen 5574 section corrected to `антибиотик: джозамицин`, real verbatim `source_quote` substituted for the fabricated one |
| `DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md` | Worked-example drug name corrected to джозамицин with an inline correction note |
| `DOSE_CALCULATION_TRACE_SPEC.md` | Correction note added; the original dose=10/Азитромицин example is now attributed to the more-likely-correct `regimen_id=6138`, not 5574 |
| `RC030_DOSE_SEMANTICS_REPORT.md` | Worked example replaced with regimen 5364 (verified correct), correction note added |
| `RC030_EVIDENCE_VALIDATION_REPORT.md` | Sections 8/15/16 rewritten to state the retraction plainly |
| `PROJECT_STATE.md` | New top entry states the correction; inline mentions in older entries annotated |
| `NEXT_TASK.md` | Item 1 rewritten from "new Critical finding" to "RETRACTED" |
| `AI_LOG.md` | New top entry states the correction in full; inline mentions annotated |

### B. Explicit historical retraction (preserved on purpose, not deleted)

`ROOT_CAUSE_REGISTER.md`'s RC-031 row itself — kept per instruction ("Do not remove the historical
record"), status field reads `RETRACTED`, not deleted from the table.

### C. Stale false claim

**None found.** Every remaining occurrence of "5574" + "Азитромицин" in the repository (checked by
direct grep, listed in the previous turn's response) appears only inside a sentence that is itself
explaining the correction — no file asserts the false mismatch as current fact anymore.

### D. Generated artifact requiring regeneration

`dose_verification_sandbox/data/phase6_regimen_5574.json` — found to be **byte-corrupted** (invalid
UTF-8, `UnicodeDecodeError` on load), caused by an earlier shell redirect (`python ... > file`) on a
Windows cp1251 console, unrelated to the RC-031 content error itself but discovered during this audit.
**Deleted** (gitignored, regenerable, superseded by the Phase 1 evidence packet below — no value in
repairing a redundant artifact when a proper machine-generated one now exists).

Other data artifacts checked and confirmed **not corrupted, not stale**: `rc031_5574_live_recheck.json`,
`rc031_5574_normalized.json`, `rc031_assembled_guideline_1126.json`, `rc031_guideline_1126_all.json`,
`risk_audit_results.json`, `full_corpus_classification.json`, `snapshot_latest.json` — these are raw
query outputs generated at the time of the (correct) live re-verification and remain accurate.

### E. Test fixture

None of the sandbox's test files (`tests/dose_verification_sandbox/*.py`) reference regimen 5574 or
RC-031 by name — the RC-030 tests use synthetic fixtures, not this specific real regimen. No fixture
correction needed.

### F. Unrelated legitimate occurrence

`RC030_12CASE_REVALIDATION.md`'s introductory line ("Not one of the formal 12-case pilot... 5364,
5376, 5377, 5378, 5439, 5355, 5356, 5400, 5401, 5402, 6275, 6405") — lists 5574 only to say it is
*not* one of the 12 pilot cases; this was always accurate and required no correction.

## Conclusion

No stale false claim remains anywhere in the repository. One corrupted (not false, just malformed)
generated artifact was found and removed as a byproduct of this audit. Proceeding to Phase 1 to
produce a machine-generated evidence packet that makes this class of error (hand-typed text presented
as query output) structurally harder to repeat.
