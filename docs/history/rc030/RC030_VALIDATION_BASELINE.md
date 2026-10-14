# RC030_VALIDATION_BASELINE.md

Status: RC-030 Evidence Validation, Phase 0. Frozen baseline recorded before any validation work
begins. Read-only — no files listed below were modified to produce this snapshot.

## Git state

```
HEAD: 6e26aebce77d3d5c3ecb0a0b8689c766437d3636
Parent: 32096af5ac1c1227027ef4075863164f45251139
Committed: 2026-07-15 22:55:39 +0500
Branch: main
```

`git status --short` at baseline: 84 untracked (`??`) entries, 5 modified (`M`) tracked files
(`AI_LOG.md`, `NEXT_TASK.md`, `PROJECT_STATE.md`, `ROOT_CAUSE_REGISTER.md`, `.gitignore`). All 84
untracked entries are either P5.6-sandbox-related new files, or pre-existing untracked repository
content unrelated to this work (`pilot_review_batch/`, `CORPUS_MANIFEST.json`, etc. — present before
this session started, per the conversation's initial `gitStatus`). **Nothing has been staged or
committed.**

## Source database hashes (SHA-256, unchanged since RC-030 work began)

```
assembled_regimens.sqlite    9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9
kb_p44.db                    2ff88154bbedefc37f2331bb6c5d25258f5daaa188ba525d76ea996e076a3be9
kb_final.db                  16c31fba2ecafbb9d6bf7c5bc54afee5b46e41d6088cc0ac10492c852abd67dd
review_workbench_p56.sqlite  3e479ee70e59ce9aafa6ba44718dda68d867dbcc660796b81ff63d2b19ca0f29
```

These four hashes are the reference point. Every phase of this validation re-checks them at the end
(Phase 13) and any change would be a hard stop.

## Classifier / rule version (SHA-256 of the modules that decide semantic_type)

```
dose_verification_sandbox/semantics_parser.py   c516a86be05fdf10ce3904a0d92563efb117196b74affe0539bf058cec00b778
dose_verification_sandbox/parser.py             6322bec22ce6b7d397072894f61bc6fce736533c147dfd655452f5e6fc09c4f0
dose_verification_sandbox/calculator.py         8f11e90d2abe92322686fb49925e28f90a9361614e1c3181879caf2a756130e7
```

Any change to `semantics_parser.py` during this validation pass invalidates prior row-level
classifications computed against the old hash; the corrected full-corpus report (Phase 12) will note
if the hash changed between the original RC-030 report and this validation.

## Row counts by `semantic_type`, as originally reported (unvalidated, parser output only)

| semantic_type | count |
|---|---:|
| MISSING | 658 |
| FIXED_PER_DOSE | 579 |
| AMBIGUOUS | 202 |
| WEIGHT_PER_DAY | 461 |
| FIXED_PER_DAY | 525 |
| UNPARSED | 74 |
| WEIGHT_PER_DOSE | 80 |
| NOT_APPLICABLE | 96 |
| **Total** | **2,675** |

**Terminology correction, effective immediately for the rest of this validation**: these counts
describe **parser output**, not validated dose semantics. Per this task's instruction, they will be
referred to as `PARSER_CANDIDATE` counts from Phase 12 onward, not "resolved."

## Test baseline

```
python -m pytest tests/dose_verification_sandbox/ -q
66 passed in 0.37s
```

## Confirmation

Source databases have not changed since the RC-030 work that produced the above counts. This
baseline is the reference for all hash re-checks performed later in this validation pass.
