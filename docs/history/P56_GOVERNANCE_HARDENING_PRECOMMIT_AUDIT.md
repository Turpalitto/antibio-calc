# Governance Hardening — Pre-Commit Security and Diff Audit

Generated: 2026-07-15.

## Proposed allowlist

`P56_GOVERNANCE_HARDENING_PROPOSED_ALLOWLIST.txt` — **43 files**: 18 modified tracked files (17 pre-existing + `clinical_engine/terminology.py`, newly modified this closure phase), plus 25 new files (2 source, 5 new test files, 15 governance/report documents, 1 RCA doc, 1 stability report, this allowlist itself). All 43 files confirmed to exist on disk.

## Secret scan

Regex scan (provider key shapes + generic `key/secret/token/password = "<literal>"`) against every file in the allowlist: **zero matches**.

## Personal-path scan

Scan for `C:\Users\<name>`, `/Users/<name>`, `/home/<name>` across every file in the allowlist: **zero matches**.

## Forbidden-artifact scan

Filename patterns for `*.db`, `*.sqlite`, `*.pdf`, `.env`, `unknown_drugs.csv`, `crt_*.json` (pilot packets), `*.pem`, `*.key` checked against the allowlist: **zero matches**. None of these categories appear in the proposed staging set.

## Large-file scan

No file in the allowlist exceeds 1 MB.

## Clinical source database / frozen schema exclusion

- No `*.sqlite`/`*.db` file is in the allowlist (all remain gitignored, per `GITIGNORE_VALIDATION_REPORT.md`, unchanged this session).
- No pilot packet JSON (`pilot_review_batch*/crt_*.json`) is in the allowlist — still excluded per the prior owner decision.
- `medical_dictionary/unknown_drugs.csv` is **not** in the allowlist — still excluded per the prior owner decision (GENERATE DURING BUILD).
- `clinical_engine/engine.py` and all `*_bundle_manifest.json`/frozen schema files are **not** in the allowlist and were **not modified** this session (confirmed: `git diff --stat` shows only `clinical_engine/terminology.py` and `clinical_engine/review_workbench/*` changed within `clinical_engine/`).

## The one clinical_engine source-code change outside review_workbench

`clinical_engine/terminology.py` — **3 insertions, 2 deletions**. Full diff:

```diff
-        # Load if possible (future data)
+        # Load if possible (future data). load_drug_atc() is @lru_cache'd — copy
+        # before mutating below, or every instance corrupts the shared cached dict.
         try:
             from medical_dictionary.loader import load_drug_atc  # type: ignore
-            self._atc_map = load_drug_atc()
+            self._atc_map = dict(load_drug_atc())
         except Exception:
             self._atc_map = {}
```

This is the RC-029 fix (a defensive copy of an `lru_cache`d dict before mutation). **No clinical logic, dosing rule, terminology mapping, or decision path changed** — only how a cached dict reference is stored (copy vs. alias). Explicitly documented and justified in `MEDICAL_DICTIONARY_TEST_ISOLATION_RCA.md`, `P56_CANONICAL_TEST_STABILITY_REPORT.md`, and `ROOT_CAUSE_REGISTER.md` (RC-029).

## No synthetic reviewer/test data in the real review database

Confirmed (Phase 8): `review_workbench_p56.sqlite` — `review_rejected_attempts`: 0 rows, `review_decisions`: 0 rows, `review_assignments`: 0 rows, non-PENDING tasks: 0. (9 synthetic `REVIEWER_NOT_REGISTERED` rows that had accumulated from this session's earlier test runs against the real file were identified, deleted, and the causing test fixed — see `P56_CANONICAL_TEST_STABILITY_REPORT.md`.)

## No unexpected file

Diff review of the full `git status --short` output against the allowlist confirms every entry not in the allowlist falls into the previously-classified, unchanged exclusion set (60 pilot packet JSONs, `medical_dictionary/unknown_drugs.csv`, `CORPUS_MANIFEST.json`, `RECOVERY_TRACKED_FILES.txt`, `REPOSITORY_UNTRACKED_INVENTORY.json`, `SESSION_HISTORY.md`, `SESSION_SUMMARY.md`) — none of these are proposed for staging, none were modified this session.

---

## Owner approval checkpoint

Per Phase 10 instruction: the prior repository-recovery commit (`32096af`) was approved under the exact phrase **`APPROVE P5.6 REPOSITORY RECOVERY STAGING`** / **`APPROVE P5.6 REPOSITORY RECOVERY COMMIT`**, scoped explicitly to that recovery program. **This governance-hardening change set is a new, distinct commit** (source-code behavior changes to the Review Workbench's identity/blinding/approval logic, plus a Clinical Engine terminology bugfix) — the prior approval does not cover it.

**Returning: `OWNER APPROVAL REQUIRED FOR GOVERNANCE HARDENING STAGING`**

Required approval phrases (two, sequential, per the mandate's own Phase 11/12 structure):
1. To stage: **`APPROVE P5.6 GOVERNANCE HARDENING STAGING`**
2. To commit (only after staging is reviewed): **`APPROVE P5.6 GOVERNANCE HARDENING COMMIT`**

No file has been staged. `git add` has not been run.
