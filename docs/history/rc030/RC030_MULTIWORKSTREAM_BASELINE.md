# RC-030 Multi-Workstream Program — Baseline (Phase 0)

## HEAD / parent / chain

- HEAD: `7530b4796b924b17857b3ef7e52bb32e900d0501` (C6.1 final report)
- Parent: `549016c6b9fc8330eb93b509664db26ee42d8980` (C6.1 main)
- `origin/main`: `2908343d1be1bc7e10dc14b4a8a13ca0c4fc3711` — 16 commits ahead, 0 behind
- Full chain: C6.1-report → C6.1-main → C6 → C5-fix → C5 → C4 → C3 → C2 → C1 → base
- `git status --short`: 104 untracked entries, zero tracked modifications. **C1-C6.1 clean: PASS.**

## Toolchain

- Python: 3.12.10 (local interpreter; path omitted — machine-specific, not repository-relevant)
- `uv`: available via `python -m uv` (0.11.28)
- `uv.lock` present at repo root (unchanged)

## Source DB hashes (re-verified)

| Database | SHA-256 |
|---|---|
| `assembled_regimens.sqlite` | `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9` |
| `kb_final.db` | `16c31fba2ecafbb9d6bf7c5bc54afee5b46e41d6088cc0ac10492c852abd67dd` |
| `review_workbench_p56.sqlite` | `3e479ee70e59ce9aafa6ba44718dda68d867dbcc660796b81ff63d2b19ca0f29` |

All unchanged since C1. **PASS.**

## Safety state (directly measured)

Assembled rows 2675, calculation eligible 0, approved objects 0, `TYPES_MEETING_PRECISION_THRESHOLD = set()`, `review_decisions = 0`, 9153 `review_tasks` PENDING, Clinical Engine disconnected. **All required preconditions hold.**

## 365-candidate range set (C6.1 result, unchanged as of this baseline)

Total 365; old labels 186 TRUSTWORTHY / 179 SUSPECT; C6.1 strict classification: `WRONG_RANGE_ANCHOR` 223, `AMBIGUOUS_ALTERNATIVE_BOUNDARY` 48, `DICTIONARY_GAP` 40, `AMBIGUOUS_TABLE_CONTEXT` 23, `NOT_A_DOSE_RANGE` 26, `AMBIGUOUS_MULTIPLE_DRUGS` 3, `AMBIGUOUS_LOADING_MAINTENANCE` 2. 0 SAFE_* in any category.

## MAJOR CORRECTION — PDF corpus is real and available

C6's baseline (prior turn) concluded "`C:\clinrec_downloader` resolves to the repository root — no PDF corpus exists in this environment," based on a shallow `ls` that happened to show scaffolding files (`AGENTS.md`, `__pycache__`, debug scripts) resembling the ANTIBIO repo layout. **This was checked more thoroughly this turn and found to be wrong**: `C:\clinrec_downloader` is a **separate, sibling project directory** — a PDF-scraping/classification tool with its own similar-looking scaffolding — that additionally contains real PDF corpus subdirectories: `downloads_active` (477 files), `downloads_antibiotics` (566 files), `downloads_other` (395 files), `archive_no_antibiotics`, `archive_review`, `quarantine` (2 files), plus its own `clinrecs.sqlite`/`clinrecs.json`/`knowledge_base.json` artifacts.

**Full re-verification this turn, all 365 range-candidate records:**
- PDF found: **365/365** (100%)
- SHA-256 hash matched against `CORPUS_MANIFEST.json`'s recorded expected hash: **365/365** (100%)
- PyMuPDF page-text extraction succeeded: **363/365** (2 failures — page-index-out-of-range or non-numeric page field, not corpus-availability failures)

This materially changes what is achievable in this program compared to C6/C6.1's stated environmental constraint. Part IV (PDF discovery) and Part VI (enhanced-evidence replay using real page text) are genuinely executed this turn using real PDF content. Part V (full six-tool table-layout bbox/row/column reconstruction) is **not** attempted this turn — not because the corpus is unavailable (it now demonstrably is), but as an explicit scope decision given the size of the remaining program (documented in `RC030_C63_C64_PDF_AND_REPLAY_REPORT.md`).

## Result

All Phase 0 preconditions hold, plus a significant positive correction to the environmental constraint recorded by prior turns. Proceeding with genuine dictionary, PDF-discovery, and enhanced-evidence replay work (Parts II-VI), followed by structural analysis, owner-queue construction, and C7 readiness preparation.
