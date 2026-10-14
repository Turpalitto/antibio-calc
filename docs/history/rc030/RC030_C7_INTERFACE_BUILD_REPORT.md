# RC-030 / C7 Part V-VI — C5 Interface Finalization and Deterministic Build

## C5 modes (Phase 8)

Required modes checked against the existing set (`range-exact-review`, `range-single-review`, `range-unit-basis-review`, `range-table-review` already existed from C6.7/C6.8). **2 missing modes added**: `range-engine-review`, `range-blocked-evidence` — each with dedicated, non-generic banner text, added to the single shared `build_interface.py`/`owner_review_template.html` implementation (no duplicate HTML path created). Full C5 suite: **44/44 passing** (was 37/37 before C7).

## Real bug found and fixed: printed build hash didn't match actual file bytes

While running Phase 16's build-check, `sha256sum` on the built HTML disagreed with the hash `build_interface.py` printed in its own "built ..." message. Root cause: `content_hash` was computed from a pre-write, LF-only Python string, then the file was written via `Path.write_text()` without pinning `newline`, which applies platform newline translation (LF → CRLF on Windows) — the actual on-disk bytes differed from what was hashed. `--check` still reported OK because it re-read the file through the *same* translation, comparing two LF-normalized strings to each other rather than to the true file bytes — so the bug was invisible to the tool's own self-check, only visible to an external hash tool.

**Fixed**: template read via `read_bytes().decode("utf-8")` (no translation), output written via `write_text(..., newline="\n")` (pinned), `--check` now compares against `read_bytes()` directly, and a build-time assertion (`written_hash == content_hash`) makes any future regression fail loudly rather than silently. Verified: all 11 batch builds + the control build now have `sha256sum`-verified hashes identical to the tool's own printed hash. New regression test `test_printed_hash_matches_actual_file_bytes`. Full C5 suite re-run clean: 44/44.

## Strict blinding (Phase 9)

`generated/rc030_c7/build_c5_datasets.py` strips `deterministic_candidate`, `deterministic_classification`, `comparison_metadata` from every task before it enters a C5 dataset — asserted programmatically (`assert hf not in r`) at build time, not just intended. Prior TRUSTWORTHY/SUSPECT labels, V6-inclusion status, and expected-agreement fields don't exist in this record shape to begin with (nothing to strip). Visible fields match the spec's list exactly: PDF, page, quote, context, antibiotic, diagnosis, route, frequency, duration, structured scalar/unit, source range/unit. For unit-basis tasks, both the raw source unit and the structured unit are shown, but no field indicates which the engine "preferred" — the reviewer sees only evidence, never a hint.

## Deterministic build (Phase 14-16)

- Batch sources: `review_batches/c7/batch_NN_*.json` (11 files) + `batch_manifest.json` — compact (short exact quote + bounded sentence/paragraph context, source hashes, page; no full PDF text, no table pixel coordinates since no table-layout tooling ran).
- C5 datasets: `generated/rc030_c7_owner_review/batch_NN_*_dataset.json` (blinded, per Phase 9).
- Built interfaces: `generated/rc030_c7_owner_review/c7_batch_NN_*.html` (11 batches) + `c7_controls.html` (4 synthetic controls, `--mode control`).
- All builds: deterministic output confirmed (`--check` OK on all 11 batches + controls), no external resources (re-verified via the existing `test_template_has_zero_network_code`/`test_template_has_no_external_urls`), no backend, no embedded owner events, no embedded AI events as owner data (asserted at build time), no absolute paths (`_ABS_PATH_RE` check unchanged, re-verified clean).

Per the owner's explicit policy, **generated HTML is not committed** — kept local-only under `generated/rc030_c7_owner_review/`, matching the C6.7/C6.8 precedent of never committing built interface HTML.
