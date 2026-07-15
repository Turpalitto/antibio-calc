# P5.6 Phase 10 — Staged Content Audit

Generated: 2026-07-15, after owner approval **`APPROVE P5.6 REPOSITORY RECOVERY STAGING`**.

## Staging method

`git add --pathspec-from-file=P56_PROPOSED_TRACKED_FILES.txt` — the exact 453-file approved allowlist, **not** `git add .` and no wildcard/glob staging.

## Reconciliation: allowlist vs. staged

- Allowlist: **453 files**
- `git diff --cached --name-status`: **448 files** (434 `A`, 14 `M`)
- Difference (5 files) explained: `.claude/launch.json`, `db/diseases/gastrointestinal.json`, `db/diseases/systemic.json`, `db/schema.json`, `server.js` were already committed at HEAD with **byte-identical** content (`git diff HEAD -- <these 5 paths>` returns empty) — `git add` correctly staged nothing for them because there was nothing to change. They are part of the repository at HEAD already and will be included in any commit regardless. 448 + 5 = 453. Reconciled, no discrepancy.
- The 14 `M` entries are exactly the 14 tracked files that were modified before this program began (`git status` at session start): `.gitignore`, `antibiotic_calc.html`, `antibiotic_calc.html.template`, `build_html.ps1`, `db/antibio_db.json`, `db/build_db.ps1`, `db/diseases/{adult_specific,neonatal,prophylaxis,respiratory,skin_soft_tissue,urogenital,zoonotic_specific}.json`, `db/index.json`.

## `git status --short`

514 total lines (staged entries + still-untracked/excluded files, which is expected — the 66 confirmed-excluded files plus this audit report itself remain untracked by design).

## `git diff --cached --stat`

```
448 files changed, 117696 insertions(+), 113 deletions(-)
```

## `git diff --cached --name-status`

```
434 A
 14 M
```

## Secret re-scan of staged content

Regex scan (provider key shapes: `sk-…`, `AKIA…`, `AIza…`, `ghp_…`, `xox[baprs]-…`, PEM headers, generic `key/secret/token/password = "<literal>"`) re-run against the full content of every staged file (equivalent to the staged index content, since staging captured working-tree content unchanged): **zero matches**.

## Forbidden-artifact check on staged file list

`git diff --cached --name-only` scanned for `*.db`, `*.sqlite`/`*.sqlite3`, `*.pdf`, `.env`, `unknown_drugs.csv`, `pilot_review_batch*/crt_*.json`, `*.pem`, `*.key`, `credentials*.json`, `secrets*.json`: **zero matches**. Confirmed absent:
- Databases: none staged
- PDFs: none staged
- Models/caches: none staged
- `.env`: none staged (only `.env.example`, which is the intended template)
- `unknown_drugs.csv` (either copy): none staged
- Pilot review packet JSONs (`crt_*.json`): none staged

## Large-file check

No staged file exceeds 1 MB. Total staged content size: **6,881,783 bytes (6.88 MB)** across 448 changed files (the discrepancy from the previously reported 6.96 MB reflects that 5 files needed no restaging, so their size isn't counted as a "change" — their bytes are already in HEAD).

## Line endings / encoding

Git printed CRLF-normalization notices for `.gitignore`, `.env.example`, `.gitleaks.toml`, and most `.md`/text files during `git add` (`LF will be replaced by CRLF the next time Git touches it`) — this is Git's standard `core.autocrlf` behavior on Windows and is not a content defect; no manual encoding changes were made.

## Unexpected files

None found. No file outside the approved allowlist was staged.

---

**Result: clean. Stopping before commit, per instruction.**

Waiting for the exact phrase **`APPROVE P5.6 REPOSITORY RECOVERY COMMIT`** before any commit is created.
