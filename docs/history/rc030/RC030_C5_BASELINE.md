# RC-030 C5 — Baseline and Inventory (Phase 0-1)

## HEAD / branch

- HEAD before C5 work: `c41efb52ab6ae9cba20d09d046f9738566e7260a` (C4)
- Branch: `main`
- Parent chain: C4 → C3 (`d79bb3c9...`) → C2 (`35d432ed...`) → C1 (`aa753317...`)

## Staging area / tracked files

`git status --short` shows zero `M`/`MM`/`AM` entries for any C1-C4 tracked file. **Staging area empty, C1-C4 clean: PASS.**

## Discovered `generated/rc030_recovery/` inventory (before any C5 change)

| Path | Size | Classification (Phase 1) |
|---|---|---|
| `build_interface.py` | 1190 B | B — deterministic builder (main 60-record set) |
| `build_control_sample_interface.py` | 1277 B | B — deterministic builder (30-record control sample), near-duplicate of the above |
| `owner_review_template.html` | 22570 B | A — source template, **NOT blind**: showed parser semantic type, risk flags, validation status, calculation eligibility, and rule fragment before submission (real defect, see `RC030_C5_ARCHITECTURE_AUDIT` findings below) |
| `owner_control_sample_template.html` | 22039 B | A — source template, **correctly blind** (post-submit reveal panel with AI comparison), near-duplicate of the above with better blinding discipline |
| `owner_review_data.json` | 89437 B | C — compact governed input dataset, 60 records, contained a real absolute-path leak (`pdf_local_path`, see findings) |
| `owner_control_sample_data.json` | 53705 B | C/F(H) — 30-record dataset, contains `ai_proposed_verdict`/`ai_confidence`/`ai_evidence_explanation`/`ai_risk_flags` per record — bundled AI-audit output, treated conservatively as AI-audit-adjacent (owner authorization explicitly excludes "AI event stores") |
| `RC030_OWNER_REVIEW_INTERFACE.html` | 100798 B | D — generated final HTML |
| `RC030_OWNER_CONTROL_SAMPLE_INTERFACE.html` | 69397 B | D — generated final HTML |
| `clipped_table_recovery.json` | 7222 B | D — generated table-recovery evidence (3 records), not wired into either template |
| `_ai_audit_blinded_input.json` | 59896 B | F — AI-audit workspace artifact |

No localStorage exports, no genuine owner-event exports, no PDF crops, no browser screenshots/logs, no temporary HTTP-server files were found anywhere in this directory or elsewhere in the untracked inventory.

## Regimen 6657 real export

No real owner-event export file for regimen 6657 (or any regimen) exists anywhere in this worktree (re-confirmed; same finding as C4's baseline). `RC030_FULL_REPAIR_BASELINE.json` records `"owner_events": 1` as a historical fact with no corresponding file on disk.

## Placement decision (Phase 1)

Repository convention (established by C1-C4 and `.gitignore`): `*.sqlite`/`*.db`/`*.pdf` and everything genuinely generated/derived stays untracked; small deterministic source (code, templates, compact governed data, tests, docs) is tracked. Applying this to C5:

- **Track:** one consolidated builder, one consolidated template, the 60-record dataset (after removing the absolute-path leak — see architecture audit), the test suite, and the C5 governance docs.
- **Exclude:** both generated final HTML files (policy default — builder/template/data tracked, generated HTML excluded, consistent with `.gitignore`'s general-artifact philosophy; no explicit repository convention tracks generated HTML anywhere else), the 30-record AI-bearing dataset, the two now-superseded builder/template files (left on disk, unused, for history — not deleted), `clipped_table_recovery.json`, `_ai_audit_blinded_input.json`.

Full reasoning per file in `RC030_C5_EXACT_ALLOWLIST.md`.
