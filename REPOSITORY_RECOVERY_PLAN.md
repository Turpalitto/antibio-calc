# REPOSITORY_RECOVERY_PLAN.md
## Owner-Reviewed Repository Recovery Plan · 2026-07-15
## Status: PROPOSED — NO `git add` OR `git commit` HAS BEEN RUN. Awaiting explicit owner approval.

> Built from a fresh, current `git status --porcelain --untracked-files=all` (424 items: 14 tracked
> modified + 410 untracked), independently re-verified — not from the earlier `REPOSITORY_UNTRACKED_
> INVENTORY.json` snapshot alone. Every number below is reproducible with the commands shown.

---

## 1. Exact list of files that must be tracked

**All 410 untracked items + 14 already-tracked-modified items (424 total) should be tracked**, with
**one flagged exception requiring your decision** (§6 below). None of the 410 untracked files are a
database, model, cache, PDF, or secret — verified by direct classification (see §4).

Breakdown of the 410 untracked candidates:
| Category | Count | Examples |
|---|---:|---|
| Root-level docs (`.md`) | ~140 | All P4/P5.x reports, RFCs, governance docs, `AI_LOG.md`, `ROADMAP.md`, `PROJECT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md` — this whole session's + the recovery session's output |
| `clinical_engine/` package | 148 | Regimen assembly, review workbench, models, tests — real source, not scaffolding |
| `src/` package | 62 | Extraction/layout/semantic pipeline, tests |
| `medical_normalizer/` package | 26 | Frozen normalizer + its tests |
| `docs/` | 20 | Governance stack, RFCs, superpowers specs |
| `medical_dictionary/` | 15 | Terminology DB + loader |
| Config/build (`pyproject.toml`, `uv.lock`, `.gitleaks.toml`, `.env.example`, `config/`) | 5 | Dependency/security contracts |
| Root-level scripts (`*.py`) | ~12 | `main.py`, `build_p44_kb.py`, benchmark/report generators |
| Root-level data (`prefilter_rules.json`, `p56_queue_report.json`, `p56_review_benchmark.json`, `CORPUS_MANIFEST.json`) | 4 | Reference/evidence artifacts, small, non-sensitive |
| `db/validate_db.js` | 1 | New source file alongside existing tracked `db/` |

**14 already-tracked, modified files** (real edits, part of the historical antibiotic-calc app):
`.gitignore`, `antibiotic_calc.html(.template)`, `build_html.ps1`, `db/antibio_db.json`,
`db/build_db.ps1`, `db/diseases/*.json` (6 files), `db/index.json`.

**Full exact list** (all 424 paths, one per line, machine-reusable): generated fresh via the command
in §5 and written to `RECOVERY_TRACKED_FILES.txt` (companion file, not committed) for your review —
regenerate anytime with:
```
git status --porcelain --untracked-files=all > RECOVERY_TRACKED_FILES.txt
```

## 2. Exact list of files that must remain ignored

None of these appear in `git status` at all right now (confirmed already excluded, not merely
absent) — verified with `git check-ignore -v`:

| Path (example) | Rule that excludes it | Confirmed present on disk? |
|---|---|:---:|
| `kb_p44.db` (55 MB, certified P4.4 KB) | `.gitignore:41: *.db` | Yes |
| `review_workbench_p56.sqlite` (94 MB) | `.gitignore:39: *.sqlite` | Yes |
| `.venv/` (dependency virtualenv) | `.gitignore:35: .venv/` | Yes |
| `__pycache__/` (any location) | `.gitignore: __pycache__/` | Yes |
| Any `*.pdf` (corpus PDFs, if locally present) | `.gitignore: *.pdf` | Corpus lives at `C:\clinrec_downloader`, outside this repo entirely — not a concern here |
| `models/`, `weights/`, `*.onnx`, `*.pt`, `*.safetensors` | ML cache rules | Present under `.venv`/site-packages only, not repo-local |
| `.env` (real secrets, if ever created) | `.gitignore: .env` + `.env.*` (with `!.env.example` exception) | No live `.env` exists (verified, see §4) |
| `*_FINAL.json`, `p44_*.json`, `p45_*.json`, checkpoint files, `regimen_review_workbench.*`, etc. | Existing "generated milestone metrics" block | Historical scratch/output already excluded |
| My own session scratch files (`_gitstatus_*.txt`, `_untracked_only.txt`) | `.gitignore: /_*.txt` | Deleted after use in this session; would be excluded even if left behind |

**No production database, PDF corpus, ML model, or cache file is a candidate for tracking.**

## 3. Proposed `.gitignore`

Current `.gitignore` (already tracked, already modified — see full current content in the repo) is
**structurally sound** and already covers every category above correctly. **One real gap found**,
requiring a fix before commit:

> `.gitignore` line `~89: /unknown_drugs.csv` is **root-anchored** (leading `/`), but the real file
> is `medical_dictionary/unknown_drugs.csv` — a different path the anchored pattern does **not**
> match. This is why it appears in `git status` right now despite an apparent existing intent to
> exclude it.

**Proposed fix** (pick one — your decision, §6):
- **Option A (keep excluded, matches original intent):** change the line to
  `**/unknown_drugs.csv` (matches at any depth), OR add `medical_dictionary/unknown_drugs.csv`
  explicitly.
- **Option B (track it):** this file is real curated data (441 unknown-drug candidates ranked by
  occurrence, an input to the pending manual-review workflow noted in `ROADMAP.md`) — arguably
  valuable to version like the other reference JSON/CSV files already proposed for tracking (§1).
  Remove any exclusion for it.

No other `.gitignore` changes are proposed — every other exclusion rule was verified to correctly
match a real, currently-ignored artifact (§2).

## 4. Secret scan result

**Method:** (a) direct grep for literal secret-shaped strings in `src/pipeline/config.py` (the
file named in `SECURITY_INCIDENT_REPORT.md`); (b) a broader pattern scan (API key assignment,
`sk-`-prefixed keys, AWS keys, PEM private-key blocks, Bearer tokens) across **all 424** files that
are candidates for tracking (untracked + tracked-modified), source and non-source extensions alike;
(c) confirmed no live `.env` file exists anywhere in the repo (only the placeholder `.env.example`).

**Result: 0 matches** across all 424 files, all pattern classes.

**Caveat, stated honestly:** the repository ships a `.gitleaks.toml` configuration, but the
`gitleaks` binary itself is **not installed in this environment**, so the actual configured scanner
has not been executed here — only an equivalent manual pattern scan. This manual scan is broad but
not a substitute for running the real tool. **Recommend running the actual `gitleaks` scan (or
equivalent CI secret-scanner) once available**, before or immediately after the recovery commit, as
a second, independent confirmation.

The two credentials documented in `SECURITY_INCIDENT_REPORT.md` (fingerprints `36a82f27fc71`,
`ba7b83283119`) are confirmed **already removed** from the working tree (that finding is historical,
already remediated) — owner rotation/revocation of those two credentials remains a separate,
outstanding action item, unrelated to whether this commit is safe to make.

## 5. Database/artifact exclusion list

Explicit list of what must **never** be staged, with live confirmation each is currently absent
from the tracking candidate set:
```
kb_p44.db                              (55,476,224 bytes — confirmed absent from git status)
kb_p44_*.db                            (archived rebuild snapshots — confirmed absent)
review_workbench_p56.sqlite            (93,868,032 bytes — confirmed absent)
.venv/                                 (dependency virtualenv — confirmed absent)
**/__pycache__/                        (confirmed absent)
C:\clinrec_downloader\**               (external PDF corpus — outside repo root entirely, N/A)
*.onnx / *.pt / *.safetensors           (ML model weights, live only under .venv — confirmed absent)
.env                                    (no live file exists — confirmed absent)
```
Verification command used:
```
git status --porcelain --untracked-files=all | grep -iE "\.db$|\.sqlite|\.pdf$|\.onnx$|\.pt$|\.bin$|__pycache__|\.venv"
```
→ zero matches (already run, confirmed).

## 6. Staged-file preview command

**Already run safely** (`git add -n` is a dry run — it inspects and reports what WOULD be staged
without modifying the index; nothing was staged):
```
git add -n -A
```
Output (last lines shown; full output covers all 424 candidate paths):
```
add 'src/tests/test_progress.py'
add 'src/tests/test_section_detector.py'
add 'table_dependency_audit_2026-07-13.md'
add 'uv.lock'
add 'validate_full_corpus.py'
```
**Recommended actual staging command once you approve** (excludes DB/sqlite/venv/pycache defensively
even though `.gitignore` already excludes them — belt and suspenders):
```
git add -A -- . ':!*.db' ':!*.sqlite' ':!*.sqlite3' ':!.venv' ':!**/__pycache__'
```
**Two open decisions before this command is final** (§3, §1-exception):
`medical_dictionary/unknown_drugs.csv` — track it or fix the `.gitignore` gap to exclude it. Whichever
you choose, tell me and I'll adjust the pathspec/`.gitignore` accordingly before staging.

## 7. Fresh-clone verification plan

To be run **after** you approve and I make the recovery commit (not yet executed):
```
1. git clone <this repo> /tmp/antibio_fresh_clone_verify
2. cd /tmp/antibio_fresh_clone_verify
3. Confirm NO kb_p44.db, review_workbench_p56.sqlite, .venv/, or __pycache__/ exist in the clone
4. uv sync   (or: pip install -e . per pyproject.toml/uv.lock — installs the locked 194 packages)
5. python -m pytest --collect-only -q
   → expect exactly 1,373 tests collected (matches the number verified in this session)
6. python -m pytest -q
   → expect 1,371 passed, 1 skipped, 1 xfailed, 0 failed (matches the number verified in this session)
7. Confirm clinical_engine/engine.py has zero references to kb_p44/KnowledgeBase (Clinical Engine
   still disconnected in the fresh clone, same as the working copy)
8. Record the fresh-clone verification result in GOVERNANCE_SOURCE_OF_TRUTH.md / PROJECT_STATE.md
```
This directly satisfies the P5.6 exit-gate requirement: "repository reproducible from Git" — right
now that gate is BLOCKING because git tracks only 19 files; after this recovery commit and the
fresh-clone run above, it can move to PASS (contingent on step 5/6 numbers matching).

---

## What I have NOT done
No `git add`, `git commit`, `git push`, or `.gitignore` edit has been performed. `git add -n` (dry
run, non-mutating) was run to produce §6's preview. Awaiting your decision on the one open item
(§3/§6 — `unknown_drugs.csv`) and your explicit go-ahead before staging or committing anything.
