# P5.6 C7 Acceptance Audit — 2026-07-30

## Verdict

**P5.6 remains ACCEPTANCE / NOT COMPLETE. P6 remains BLOCKED.**

## Post-commit status

The exact 94-file boundary was committed on `main` as
`60e603387a7132ff2aa6a736c869e5b9a7c6903a`. Its committed tree
`2b94cb7bad374bf2f3da7a0a2aa10785942a22a1` exactly matches the independently
materialized and tested temporary-index tree. No amend and no push were
performed. Clinical Engine remains disconnected.

C7 source-fidelity review itself is closed. The remaining acceptance work is
repository reproducibility: approve an exact file boundary, commit it without
local/production artifacts, validate that boundary from an isolated checkout,
and publish it so `origin/main` is no longer behind.

Nothing in this audit grants clinical approval, calculation eligibility, or
permission to connect the Clinical Engine.

## Confirmed C7 result

- 182 valid append-only owner events;
- 113/113 unique regimens;
- zero schema, identity, or supersession issues;
- one terminal event per regimen;
- 105 exact owner/AI canonical matches;
- 8 explicitly governed per-administration label equivalents;
- zero substantive mismatches;
- zero quarantined defects;
- repaired evidence for regimen `6068` remains additive and source-fidelity
  only; production DB/PDF were not modified.

External final evidence is identified by file name and SHA-256:

- `RC030_C7_FINAL_OWNER_EVENTS_2026-07-30.json`:
  `1A54B24F55A2677402246486F0624ACA8E3CA716B28C29EB025B4BF7AF86D885`;
- `RC030_C7_FINAL_COMPARISON_2026-07-30.json`:
  `2214A211E98D6206CDC76E4927EF6A1354A44EFAF8C5EA2BF51035763C57D80C`.

The external owner exports are evidence inputs, not production medical data
and not part of the proposed repository boundary.

## Test evidence

- proposed-boundary collection: 1511 tests, zero collection errors;
- proposed-boundary canonical run:
  1499 passed, 11 skipped, 1 xfailed, 0 failed in 34.10 s;
- focused C7 + portability suite in the working tree:
  396 passed, 0 failed;
- the same suite in the isolated proposed boundary:
  392 passed, 4 expected optional-artifact skips, 0 failed;
- all changed Python entry points compile successfully.

`uv lock --check` was not rerun locally because no `uv` executable/module is
installed in this shell. The historical isolated-clone run at `6e26aeb`
did run `uv lock --check` and passed. A new isolated-boundary check remains
required after the proposed files are committed.

## Security and artifact audit

- plaintext provider/private-key patterns in current tracked + untracked text:
  zero;
- known-secret patterns in reachable Git history: zero;
- real `.env`, credential JSON, or private key files: zero;
- tracked production DB/PDF: zero;
- untracked, non-ignored DB/PDF: zero;
- ignored DB/PDF: 104; `.gitignore` protection is active;
- `.gitleaks.toml` exists, but the `gitleaks` binary is unavailable, so the
  current scan is a redacted manual-regex substitute rather than a full
  gitleaks execution.

## Reproducibility defects fixed in this audit

Executable tools no longer hard-code the workstation corpus root. They now
use the governed `ANTIBIO_CORPUS_DIR` / `CorpusLocator` contract or an explicit
`--corpus-dir` argument:

- `build_review_workbench.py`;
- `build_p44_kb.py`;
- `production_reprocessor.py`;
- `reprocess_p45_layout.py`;
- `validate_full_corpus.py`;
- `clinical_engine/tools/build_normalized_sqlite.py`;
- `clinical_engine/tools/clinical_data_audit.py`.

Regression coverage is in
`clinical_engine/tests/test_tool_corpus_portability.py`.

The C7 finalizer now records source export file names and SHA-256 hashes
instead of embedding a developer home-directory path.

## Governance drift corrected

Current-state headers now record that:

- credential rotation is closed by owner attestation;
- historical fresh-clone verification passed;
- C7 source-fidelity review is closed;
- the current blocker is the new uncommitted/unpublished boundary;
- current tests are green;
- P6 and Clinical Engine integration remain blocked.

Historical C7 execution documents carry explicit supersession banners so
their earlier OWNER_ACTION_REQUIRED text cannot be mistaken for current
state.

## Proposed boundary

`P56_C7_ACCEPTANCE_PROPOSED_ALLOWLIST.txt` is the only permitted staging
source. It contains C7 source/build/test/evidence files, the current
governance synchronization, reproducibility fixes, and this audit.

Explicitly excluded:

- `CORPUS_MANIFEST.json` and other machine-local corpus manifests;
- `pilot_review_batch/` and `pilot_review_batch_v2/`;
- `medical_dictionary/unknown_drugs.csv`;
- production or backup DB/SQLite files;
- all PDF files;
- local owner export files from `%USERPROFILE%\Downloads`;
- unrelated historical RC-030 generated trees and session scratch files;
- ignored caches, logs, models, and temporary directories.

Never use `git add .` for this boundary.

## Remaining gates

1. Validate commit `60e6033` from an isolated checkout with locked
   dependencies.
2. Push the accepted commit(s); current `main` is 35 commits ahead of
   `origin/main`.
3. Keep P6 blocked until real reviewer registration, pilot completion,
   physician-approved objects, approved-data Golden pass, shadow/safety
   gates, request audit snapshot, and explicit owner authorization.
