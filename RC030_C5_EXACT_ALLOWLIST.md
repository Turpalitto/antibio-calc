# RC-030 C5 — Exact Path Allowlist (Phase 23)

Frozen allowlist. Nothing outside this list is staged for C5. Every path is added individually with `git add <exact-path>` — no wildcard or directory staging.

## C5-SOURCE

| Path | Category | Size (bytes) | SHA-256 | Reason |
|---|---|---|---|---|
| `generated/rc030_recovery/build_interface.py` | C5-SOURCE (deterministic builder) | 8359 | `861e7697e140107c4f966cc90a0123a03dbeb7190e0c3b1f59b374378feecf2e` | Consolidated builder: `--dataset`/`--template`/`--output`/`--mode {all,control}`/`--check`, atomic write, refuses duplicate `evidence_hash`, refuses preloaded verdicts, refuses embedded absolute paths, repository-relative I/O only, no network |
| `generated/rc030_recovery/owner_review_template.html` | C5-SOURCE (template) | 29605 | `3631e2c1228b4fd4fdb00f26c5a7d64a479a91c6630bf56e15a282ed68d80c93` | Consolidated blind-then-reveal template (adopts and hardens the previously-correct control-sample blinding pattern); zero network code; owner-local PDF-root resolution instead of embedded paths |
| `generated/rc030_recovery/owner_review_data.json` | C5-SOURCE (compact governed dataset) | 81867 | `e476ed2dec9460d7d0294fa7d6c3db05af65216707f55d4164d0c329334917e0` | 60-record dataset, sanitized (absolute `pdf_local_path` removed), no preloaded verdicts, no AI fields |

## C5-TESTS

| Path | Category | Size (bytes) | SHA-256 |
|---|---|---|---|
| `tests/rc030_owner_interface/test_c5_owner_interface.py` | C5-TESTS | 11350 | `6c81e898b6be71dfc2438970cac73cc8384047367f65b6537e20f4077508446a` |

## C5-DOCS

| Path | Category |
|---|---|
| `RC030_C5_BASELINE.md` | C5-DOCS |
| `RC030_C5_ARCHITECTURE_AUDIT.md` | C5-DOCS |
| `RC030_C5_EXACT_ALLOWLIST.md` | C5-DOCS (this file) |
| `RC030_C5_PRESTAGING_AUDIT.md` | C5-DOCS |
| `RC030_C5_OWNER_INTERFACE_REPORT.md` | C5-DOCS |

## Explicitly excluded (with reason)

| Path | Reason |
|---|---|
| `generated/rc030_recovery/RC030_OWNER_REVIEW_INTERFACE.html` | Generated final HTML — policy default is builder/template/data tracked, generated HTML excluded (see `RC030_C5_BASELINE.md` Phase 1). Regenerate via the documented build command. |
| `generated/rc030_recovery/RC030_OWNER_CONTROL_SAMPLE_INTERFACE.html` | Same as above |
| `generated/rc030_recovery/owner_control_sample_data.json` | Contains `ai_proposed_verdict`/`ai_confidence`/`ai_evidence_explanation`/`ai_risk_flags` per record — bundled AI-audit output. Owner authorization explicitly excludes "committing AI event stores"; treated conservatively as within that exclusion even though it is comparison metadata rather than a full AI event record. |
| `generated/rc030_recovery/build_control_sample_interface.py` | Superseded by the consolidated builder (`--mode control`); left on disk unused, not deleted, not staged |
| `generated/rc030_recovery/owner_control_sample_template.html` | Superseded by the consolidated template; left on disk unused, not deleted, not staged |
| `generated/rc030_recovery/clipped_table_recovery.json` | Generated table-recovery evidence, not wired into any tracked code path |
| `generated/rc030_recovery/_ai_audit_blinded_input.json` | AI-audit workspace artifact |
| Any `localStorage` content | Never touches disk outside the browser profile; nothing to stage |
| Any genuine owner-event export | None exists in this worktree (verified) |
| C1-C4 code | Untouched — verified via `git status --short` showing zero modifications to any previously-committed path |
| Clinical Engine | Untouched — zero references added anywhere in C5 |

## Totals

- 3 source files + 1 test file + 5 doc files = 9 tracked paths
- 0 SQLite, 0 PDF, 0 localStorage export, 0 AI event store, 0 genuine owner event
