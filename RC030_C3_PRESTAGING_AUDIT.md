# RC-030 C3 — Prestaging Scans (Phase 8)

All scans below were run for real against the exact 42-file allowlist in `RC030_C3_EXACT_ALLOWLIST.md` (`.rc030_final_list.tmp`, a scratch file listing the 42 paths, deleted before staging). Commands and raw results recorded; false positives documented with the actual matched line.

## Secret / API key / token scan

Pattern: `(api[_-]?key|secret|password|token)\s*[:=]\s*['"][A-Za-z0-9+/_.-]{12,}['"]`, plus AWS/GitHub/OpenAI key-shape patterns and PEM private-key headers.

**Result: 0 matches.** Clean.

## Absolute Windows path scan

Pattern: `C:\[A-Za-z_]+\...` across all 42 files, excluding the documented `C:\clinrec_downloader\` references (see below).

**Result: 0 matches** other than `C:\clinrec_downloader\` (3 files: `RC030_TARGETED_RECOVERY_BASELINE.md`, `RC030_PDF_COVERAGE_GAP_REPORT.md`, `RC030_TARGETED_RECOVERY_AND_OWNER_PILOT_REPORT.md`).

**Documented false positive:** `C:\clinrec_downloader\` is a project-level local source-PDF storage root, not a personal path — no username, no home directory. It is factual RCA content (which storage folders were searched for source PDFs) and redacting it would misrepresent the RCA per the instruction not to alter historical meaning. Retained; flagged for owner visibility in the classification matrix.

One additional match in `RC030_TEST_PORTABILITY_POSTCOMMIT_REPORT.md` line 23 is a **meta-reference** ("scan of `tests/` found 0 matches for `C:\Users\<name>`...") describing a *different* scan's result, not an actual leaked path.

## Absolute Unix path scan

Pattern: `/home/[a-z]+`, `/Users/[A-Za-z]+`.

**Result: 0 matches** in file content (one meta-reference in `RC030_TEST_PORTABILITY_POSTCOMMIT_REPORT.md` describing that a prior scan found 0 matches — not an actual path).

## Username scan

Pattern: `TURPAL` (the local machine username).

**Result: 0 matches** across all 42 files.

## localhost / 127.0.0.1 URL scan

**Result: 0 matches** across all 42 files. (Note: `RC030_OWNER_PILOT_GUIDE.md` and `RC030_OWNER_PILOT_CONSOLIDATION_REPORT.md` do contain `localhost` references but both are excluded from C3 — see classification matrix, category H.)

## DB / PDF / model / cache reference scan

Pattern: literal filenames ending in `.sqlite`, `.db`, `.pdf`, `.pt`, `.pth`, `.onnx`, `.safetensors`.

**Result:** ~25 matches, all prose references to database/PDF *names* inside governance text (e.g. "Authoritative DBs unchanged (sha256 before==after)", "target: `normalized_regimens.sqlite`"), which is expected and necessary content for hash-verification reports. **No binary `.sqlite`/`.db`/`.pdf`/model file is among the 42 staged paths** — confirmed by the binary scan below and by the allowlist itself (all 42 entries are `.md`/`.json`).

## Large-file scan

Largest staged file: `RC030_RANGE_REPROCESS_MANIFEST_SUMMARY.json` at 5332 bytes. Combined total: 145,300 bytes (~142 KB) across 42 files. **No file exceeds a few KB.** Clean.

## Generated-clinical-data scan

Checked every staged JSON for per-row clinical payloads (source quotes, full regimen objects). `RC030_FULL_REPAIR_BASELINE.json` and `RC030_FULL_REPAIR_CORPUS_IMPACT.json` contain only counts/hashes/distributions. `RC030_RANGE_REPROCESS_MANIFEST_SUMMARY.json` contains only counts, hashes, and a flat list of 365 integer regimen IDs — no quotes, no offsets, no drug names. **Clean per Phase 4 minimization.**

## Raw-source-quote density scan

Grepped all 39 `.md` files for Cyrillic text runs longer than ~40 characters (a proxy for embedded full source quotes vs. short illustrative excerpts). Longest matches are single dose-expression fragments (e.g. `"20-50 мг/кг/сутки 2-3 приема"`, `"Суточные дозы и режим введения антибиотиков при ОСО"` as a table caption) — all under one sentence, consistent with the "short evidence excerpts" allowance in Phase 4. No multi-sentence guideline excerpts found.

## Binary scan

`file` run against all 42 paths: 100% report as ASCII/UTF-8/Unicode/JSON text. **0 binaries.**

## Line-ending scan

21 of 42 files are CRLF, 21 are LF (mixed, expected on this Windows checkout with `core.autocrlf=true`, no `.gitattributes` override). Not a blocker — same handling as C1/C2, git normalizes on checkout.

## Encoding scan

All 42 files decode successfully as UTF-8 (Python `open(f, encoding='utf-8').read()` on every file, 0 failures).

## Malformed JSON scan

All 3 `C3-MANIFEST` JSON files (`RC030_FULL_REPAIR_BASELINE.json`, `RC030_FULL_REPAIR_CORPUS_IMPACT.json`, `RC030_RANGE_REPROCESS_MANIFEST_SUMMARY.json`) parse successfully with `json.load()`. **0 malformed.**

## Duplicate-report scan

SHA-256 of all 42 files compared; **0 duplicate content hashes.**

## Stale-hash scan

Checked all 40-character hex strings across the 39 `.md` files against known commit/DB/code hashes. All resolve to real, previously-recorded hashes (base commit `394818675b0ed199e03cae1d89e38a488f5102ce`, `assembled_regimens.sqlite` hash `9f505d08...`, `normalized_regimens.sqlite` hash `c7b67354...`, parser/normalizer content hashes, `review_workbench_p56.sqlite` hash `3e479ee7...`). None of these reports predates or postdates a DB mutation — all DB hashes referenced match the current, unmutated authoritative databases (see Phase 11 verification). No report references the C2 commit hash (`35d432e...`) because all 39 reports were written before C2 existed; this is historically accurate, not stale, and is not corrected (would misrepresent when each report was written).

## Stale test-count scan

Found and corrected one stale claim: `RC030_FULL_REPAIR_IMPLEMENTATION_REPORT.md` originally stated "Canonical suite: 1455 passed, 1 xfailed, 0 failures" without separating skipped tests, inconsistent with the formally verified C1/C2 counts (1444/11/1 and 1446/11/1 respectively). Corrected in Phase 3 with an added clarification paragraph; original claim preserved with context rather than deleted (see the file's "Correction (C3 content audit)" paragraph). No other stale test-count claims found in the remaining 38 `.md` files (none of the others assert canonical pytest totals).

## Summary

All scans ran for real against the actual file contents (not assumed clean). Two categories of findings were documented as informed false positives (the `C:\clinrec_downloader\` local-storage-root references, and prose mentions of DB/PDF filenames), and one genuine stale-content defect was found and corrected. No secrets, no personal paths, no binaries, no malformed JSON, no duplicate content. Allowlist is clear to stage.
