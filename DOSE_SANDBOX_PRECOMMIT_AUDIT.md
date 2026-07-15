# DOSE_SANDBOX_PRECOMMIT_AUDIT.md

Status: Phase 0 of RC-030 work. Read-only audit of the currently uncommitted P5.6 sandbox changes.
No `git add` / `git commit` performed by this audit — staging requires explicit owner approval,
requested at the end of this document.

## Scope of uncommitted changes

```
 M AI_LOG.md
 M NEXT_TASK.md
 M PROJECT_STATE.md
 M ROOT_CAUSE_REGISTER.md
?? DOSE_CALCULATION_TRACE_SPEC.md
?? DOSE_ROUNDING_POLICY.md
?? DOSE_VERIFICATION_SANDBOX_AUDIT.md
?? DOSE_VERIFICATION_SANDBOX_REPORT.md
?? DOSE_VERIFICATION_SANDBOX_SPEC.md
?? DOSE_VERIFICATION_USER_GUIDE.md
?? dose_verification_sandbox/
?? tests/dose_verification_sandbox/
```

(plus this file, `DOSE_SANDBOX_PRECOMMIT_AUDIT.md`, and a `.gitignore` update made as part of this
audit — see below.)

## Checks

| Check | Result |
|---|---|
| No Clinical Engine integration | ✔ — `test_sandbox_module_never_imports_clinical_engine` passes; no `import clinical_engine` anywhere in `dose_verification_sandbox/` |
| No source DB mutation | ✔ — `snapshot.py` opens `assembled_regimens.sqlite` with `mode=ro`; `test_sandbox_never_opens_source_db_for_write` confirms no INSERT/UPDATE/DELETE in that module; no other module opens a source DB at all |
| No approval mutation | ✔ — `DoseVerificationResult.clinical_approval` is hard-locked to `NOT_APPROVED` in `models.py.__post_init__`; nothing in the sandbox writes to `status`/`review_status`/`approved_by` columns |
| No runtime DB committed | Found and fixed — see "Generated artifacts" below |
| No generated QA issue database committed | Found and fixed — `data/issues.json` (12 KB, 12 filed pilot issues) is generated, not source; now gitignored |
| No browser/download artifacts committed | ✔ — the UI's "download defect report" button saves to the browser's Downloads folder, outside the repo tree; nothing found in `dose_verification_sandbox/` matching a browser download |
| No secrets | ✔ — `grep` across the new tree for path/credential patterns found nothing; the module uses only `Path(__file__)`-relative paths, no hardcoded credentials, no API keys |
| No personal paths | ✔ — no `C:\Users\...` or other user-specific absolute paths in any committed-intended file (checked via grep, see command below) |
| All 45 sandbox tests pass | ✔ — re-run immediately before this audit: `45 passed in 0.27s` |

Grep used: `grep -rn "C:\\Users\\TURPAL\|/home/\|C:\\ANTIBIO" dose_verification_sandbox/ tests/dose_verification_sandbox/` — zero matches in source files. (Generated JSON data files under `data/` do embed the machine's absolute export path indirectly through `Path(__file__)`-derived values in some fields — this is exactly why those files are excluded below, not committed.)

## Generated artifacts found (excluded, not committed)

`dose_verification_sandbox/data/` contained five generated files at audit time, none of which are
source — all are reproducible outputs of running the sandbox's own scripts against the live
(read-only) source database:

| File | Size | Generator | Committed? |
|---|---|---|---|
| `snapshot_latest.json` | 12 MB | `python -m dose_verification_sandbox.snapshot` | **No** — full denormalized dump of `assembled_regimens.sqlite`; regenerable in seconds, too large and too volatile to track |
| `pilot_report.json` / `.md` | 24 KB / 2 KB | `python -m dose_verification_sandbox.pilot` | **No** — reproducible pilot run output |
| `issues.json` | 12 KB | `dose_verification_sandbox.issues.record_issue` (invoked once from the pilot run) | **No** — a QA issue log is operational state, not source; regenerating the pilot will recreate equivalent issues |
| `golden_calculation_dataset.json` | 4 KB | `python -m dose_verification_sandbox.golden` | **No** — mechanical dump of the `CASES` list already defined in `golden.py`; the Python source is the actual deliverable, the JSON is a derived export |

Action taken: added a `.gitignore` rule (`/dose_verification_sandbox/data/*.json`,
`*.md`, `*.sqlite`) so these never get staged by an unqualified `git add -A`. Regeneration commands
are documented in `DOSE_VERIFICATION_USER_GUIDE.md`.

## Proposed allowlist for staging (when owner approves)

```
.gitignore                                   (modified — new sandbox-data ignore rule)
AI_LOG.md                                    (modified)
NEXT_TASK.md                                 (modified)
PROJECT_STATE.md                             (modified)
ROOT_CAUSE_REGISTER.md                       (modified — RC-030 entry)
DOSE_CALCULATION_TRACE_SPEC.md               (new)
DOSE_ROUNDING_POLICY.md                      (new)
DOSE_SANDBOX_PRECOMMIT_AUDIT.md              (new, this file)
DOSE_VERIFICATION_SANDBOX_AUDIT.md           (new)
DOSE_VERIFICATION_SANDBOX_REPORT.md          (new)
DOSE_VERIFICATION_SANDBOX_SPEC.md            (new)
DOSE_VERIFICATION_USER_GUIDE.md              (new)
dose_verification_sandbox/__init__.py        (new)
dose_verification_sandbox/models.py          (new)
dose_verification_sandbox/snapshot.py        (new)
dose_verification_sandbox/parser.py          (new)
dose_verification_sandbox/calculator.py      (new)
dose_verification_sandbox/verify.py          (new)
dose_verification_sandbox/issues.py          (new)
dose_verification_sandbox/pilot.py           (new)
dose_verification_sandbox/golden.py          (new)
dose_verification_sandbox/ui/dose_verification_sandbox.html   (new)
tests/dose_verification_sandbox/test_parser.py       (new)
tests/dose_verification_sandbox/test_calculator.py   (new)
tests/dose_verification_sandbox/test_verify.py       (new)
tests/dose_verification_sandbox/test_golden.py       (new)
tests/dose_verification_sandbox/test_invariants.py   (new)

EXCLUDED (gitignored, not staged):
dose_verification_sandbox/data/*.json
dose_verification_sandbox/data/*.md
dose_verification_sandbox/__pycache__/           (already globally ignored)
```

## Addendum (RC-030 Evidence Validation Phase 1): confirmed two-commit split

Verified mechanically, not just asserted: none of `models.py`, `parser.py`, `calculator.py`,
`verify.py`, `snapshot.py`, `issues.py`, `pilot.py`, `golden.py` import anything from the
`semantics_*`/`ambiguity_workflow` modules (`grep -l "semantics_" ...` → no matches). Confirmed live:
calling the base P5.6 path (`parser.parse_dose_expression` → `calculator.calculate`) directly, with
no semantics layer involved at all, still returns `calculation_status = BLOCKED` on an ambiguous
`mg/kg` case — i.e. **the sandbox is safe and usable on its own, failing closed exactly as it did
before RC-030, if Commit B is never applied or is later reverted.**

**COMMIT A — Dose Verification Sandbox only** (as listed in the original allowlist above, unchanged):
`dose_verification_sandbox/{__init__,models,snapshot,parser,calculator,verify,issues,pilot,golden}.py`,
`ui/dose_verification_sandbox.html`, `tests/dose_verification_sandbox/{test_parser,test_calculator,
test_verify,test_golden,test_invariants}.py`, the six `DOSE_VERIFICATION_*`/`DOSE_CALCULATION_*`/
`DOSE_ROUNDING_POLICY.md` docs, plus the `AI_LOG.md`/`NEXT_TASK.md`/`PROJECT_STATE.md`/
`ROOT_CAUSE_REGISTER.md` hunks describing only the P5.6 sandbox (not the RC-030 sections added later).

**COMMIT B — RC-030 DoseSemantics enrichment and validation**:
`dose_verification_sandbox/{semantics_models,semantics_parser,semantics_integration,semantics_store,
ambiguity_workflow}.py`, `tests/dose_verification_sandbox/{test_semantics_parser,
test_ambiguity_workflow}.py`, all `RC030_*.md` / `DOSE_SEMANTICS_*.md` / `DOSE_SANDBOX_RC030_*.md` /
`FORMULATION_DATA_GAP_REPORT.md` docs, plus the RC-030 hunks in the four handoff files.

**One file straddles the boundary**: `dose_verification_sandbox/calculator.py` gained two changes for
Commit B's use — the `apply_max_dose()` optional `source_max_single_dose=None` parameter, and the
`SUB_DAILY_FREQUENCY` block (both backward-compatible; Commit-A's own test suite passes unchanged
either way). Both diffs physically live inside a Commit-A file. **Recommendation unchanged: ship both
in Commit B**, not A — neither has a caller/trigger until Commit B exists, keeping Commit A's diff
100% free of RC-030-motivated changes.

## Final reconfirmation (post RC-031 retraction and evidence-integrity hardening)

**COMMIT A — BASE SANDBOX** (final, complete list):
```
dose_verification_sandbox/__init__.py
dose_verification_sandbox/models.py
dose_verification_sandbox/snapshot.py
dose_verification_sandbox/parser.py
dose_verification_sandbox/calculator.py          (WITHOUT the two Commit-B diffs above)
dose_verification_sandbox/verify.py
dose_verification_sandbox/issues.py
dose_verification_sandbox/pilot.py
dose_verification_sandbox/golden.py
dose_verification_sandbox/ui/dose_verification_sandbox.html
tests/dose_verification_sandbox/test_parser.py
tests/dose_verification_sandbox/test_calculator.py
tests/dose_verification_sandbox/test_verify.py
tests/dose_verification_sandbox/test_golden.py
tests/dose_verification_sandbox/test_invariants.py
DOSE_VERIFICATION_SANDBOX_SPEC.md
DOSE_VERIFICATION_SANDBOX_AUDIT.md
DOSE_VERIFICATION_SANDBOX_REPORT.md
DOSE_VERIFICATION_USER_GUIDE.md
DOSE_CALCULATION_TRACE_SPEC.md                    (the RC-031 correction note stays — it documents a
                                                    real historical error, not RC-030 functionality)
DOSE_ROUNDING_POLICY.md
DOSE_SANDBOX_PRECOMMIT_AUDIT.md                   (this file)
.gitignore                                        (sandbox-data ignore rule)
```
Plus only the P5.6-sandbox-describing hunks of `AI_LOG.md` / `NEXT_TASK.md` / `PROJECT_STATE.md` /
`ROOT_CAUSE_REGISTER.md` — the RC-030/RC-031 hunks in those same files belong to Commit B (see below);
splitting a single file across two commits by hunk is a `git add -p` operation, not by-file.

**COMMIT B — RC-030 EXPERIMENTAL SEMANTICS + EVIDENCE-INTEGRITY HARDENING** (final, complete list):
```
dose_verification_sandbox/semantics_models.py
dose_verification_sandbox/semantics_parser.py
dose_verification_sandbox/semantics_integration.py
dose_verification_sandbox/semantics_store.py
dose_verification_sandbox/semantics_risk_audit.py
dose_verification_sandbox/validation_status.py
dose_verification_sandbox/ambiguity_workflow.py
dose_verification_sandbox/evidence_model.py
dose_verification_sandbox/calculator.py           (the two diffs: source_max_single_dose param,
                                                     SUB_DAILY_FREQUENCY block)
evidence/generate_regimen_5574_evidence.py
evidence/regimen_5574_verified_evidence.json       (hashes + extracted text only — no raw DB/PDF copy)
tests/dose_verification_sandbox/test_semantics_parser.py
tests/dose_verification_sandbox/test_ambiguity_workflow.py
tests/dose_verification_sandbox/test_sub_daily_frequency.py
tests/dose_verification_sandbox/test_validation_status.py
tests/dose_verification_sandbox/test_false_positive_hardening.py
tests/dose_verification_sandbox/test_evidence_integrity.py
DOSE_SEMANTICS_MODEL.md
DOSE_SEMANTICS_PARSER_SPEC.md
DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md
FORMULATION_DATA_GAP_REPORT.md
RC030_VALIDATION_BASELINE.md
RC030_RULE_CATALOG.md
RC030_FALSE_POSITIVE_AUDIT.md
RC030_PRECISION_METRICS.md
RC030_12CASE_REVALIDATION.md
RC030_TARGETED_SOURCE_RECOVERY_REPORT.md
RC030_MAX_DOSE_VALIDATION.md
RC030_SCHEMA_RESPONSIBILITY_DECISION.md
RC030_CORRECTED_FULL_CORPUS_REPORT.md
RC030_EVIDENCE_VALIDATION_REPORT.md
RC030_DOSE_SEMANTICS_AUDIT.md
RC030_DOSE_SEMANTICS_REPORT.md
RC031_RETRACTION_AUDIT.md
REGIMEN_5574_VERIFICATION_REPORT.md
```
Plus the RC-030/RC-031 hunks of `AI_LOG.md` / `NEXT_TASK.md` / `PROJECT_STATE.md` /
`ROOT_CAUSE_REGISTER.md`.

**Required labels on Commit B** (commit message and/or a top-of-tree marker file, owner's choice):
`UNVALIDATED`, `CALCULATION_BLOCKED`, `NOT CLINICALLY APPROVED` — matching
`dose_verification_sandbox/validation_status.py`'s actual enforced runtime state
(`calculation_eligibility = BLOCKED` for all 2,675 rows, `TYPES_MEETING_PRECISION_THRESHOLD` empty).

**Not staged.** This remains a plan, not an action, pending an explicit owner approval command.

## Stop point

**Staging and committing require explicit owner approval and are not performed by this audit or by
the RC-030 work that follows it.** Per instruction, this sandbox commit is also kept separate from
the RC-030 semantic-reconstruction implementation that follows — they will be two distinct,
owner-approved commits if/when approved, not one combined commit.
