# RC-030 Six-Tool Extraction Toolchain — Availability Audit

Checked 2026-07-16, in the main dev checkout's Python environment (not the `uv.lock`-only `tests`+`clinical` extras used for portability verification — these tools live under the `extraction`/`layout`/`semantic` extras in `pyproject.toml`, which were **not** installed in the bare-clone portability test and are not required by it).

## Import-level check

| Tool | Import name | Import result | Version reported | Module path |
|---|---|---|---|---|
| PyMuPDF | `fitz` | OK | 1.24.10 | `site-packages/fitz/__init__.py` |
| MinerU | `mineru` | OK | not exposed via `__version__` | `site-packages/mineru/__init__.py` |
| Docling | `docling` | OK | not exposed via `__version__` | `site-packages/docling/__init__.py` |
| DocLayout-YOLO | `doclayout_yolo` | OK | 0.0.4 | `site-packages/doclayout_yolo/__init__.py` |
| Table Transformer | `table_transformer` | OK | not exposed via `__version__` | `site-packages/table_transformer/__init__.py` |
| RapidTable | `rapid_table` | OK | not exposed via `__version__` | `site-packages/rapid_table/__init__.py` |

All six packages import without error in this environment.

## Model-weight presence (Hugging Face cache, `~/.cache/huggingface/hub`)

Confirmed present:
- `models--docling-project--docling-layout-heron`
- `models--docling-project--docling-models`
- `models--juliozhao--DocLayout-YOLO-DocStructBench`
- `models--microsoft--table-transformer-detection`
- `models--microsoft--table-transformer-structure-recognition`
- `models--opendatalab--PDF-Extract-Kit-1.0` (MinerU's detection/recognition kit)

Model weights for all six tools appear to already be downloaded locally from a prior milestone (consistent with the P5.3/P5.4 full-corpus extraction work referenced in `pyproject.toml`'s `extraction`/`layout` extras).

## What this audit does *not* establish

Per the mission's explicit rule — "do not claim a tool was used unless a real command completed and an output artifact exists" — **a successful `import` is not evidence that a tool functions correctly end-to-end** (model loading, inference, and output parsing are separate failure points not exercised here). This audit confirms only:
1. the packages are installed and importable, and
2. their expected model weights are cached locally.

No actual extraction/layout/table-recognition command was run against a real PDF page as part of this audit. Running even a single real MinerU or Docling inference pass involves model loading (potentially tens of seconds to minutes) and produces artifacts that must be individually inspected for correctness — this is real, non-trivial compute work that has not been budgeted or executed in this turn.

## Conclusion

**Availability: plausible for all six tools** (import + cached weights). **Functional verification: not performed.** `RC030_TARGETED_MULTIENGINE_RECOVERY_REPORT.md` (Phase 13's second deliverable — actually running the toolchain against targeted pages) is **not produced** in this turn; it requires a dedicated compute session with real per-page inference runs and manual output inspection, which is out of scope for what could be responsibly completed here.
