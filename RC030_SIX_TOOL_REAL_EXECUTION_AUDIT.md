# RC-030 Six-Tool Real Execution Audit

Smoke page: regimen 5574's source PDF, `Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf` (SHA-256 `b8a525c56b01e63620e20e7c07a9899e74ba1d0f5ec1f31dd7215f675228eade`, matching `evidence/regimen_5574_verified_evidence.json`), page index 15 (page 16). All outputs preserved under `generated/rc030_recovery/page_5574_p16/` (gitignored-by-convention, not staged, not committed).

All six tools were **actually invoked**, not just imported. All six produced parseable output artifacts.

| Tool | Status | Load/Init | Runtime | Model source | Output |
|---|---|---|---|---|---|
| PyMuPDF (`fitz` 1.24.10) | **EXECUTED** | n/a | 0.006 s | none (native parser) | `raw_text.txt` — 513 chars, byte-identical in content to `evidence/regimen_5574_verified_evidence.json`'s `SOURCE_PDF_EXTRACT` block |
| DocLayout-YOLO 0.0.4 | **EXECUTED** | 0.14 s | 2.16 s (CPU) | local `.pt` checkpoint (`DocLayout-YOLO-DocStructBench`, HF cache) | 9 regions detected (6 plain-text, 3 title), confidences 0.39–0.91 |
| Table Transformer (via `transformers`, offline HF cache) | **EXECUTED** | 0.31 s | 0.20 s (CPU) | `microsoft/table-transformer-detection` safetensors, HF cache | 3 "table" detections, scores 0.63–0.87 — **flagged: this page has no real table**, so these are false positives on this smoke page. The installed `table_transformer` pip package's own `TableExtractionPipeline` expects a different (non-HF) checkpoint format and was not directly runnable with the cached weights; the equivalent HF-format model was used instead — noted as a real, load-bearing finding, not glossed over. |
| RapidTable (SLANet-plus + RapidOCR, ONNX/CPU) | **EXECUTED** | 0.64 s | 0.91 s | local `.onnx` files, already cached | 1 table structure detected (`table_0.html`) — same caveat as Table Transformer: RapidTable's structure-recognition model was run against the *whole page* rather than a pre-cropped table region, so a "table" result on a non-table page should not be trusted without a real detected table region feeding it first |
| Docling (offline HF cache) | **EXECUTED** | 0.04 s | 4.14 s | `docling-layout-heron`/`docling-models`, HF cache | `page16.md` — 560 chars, correct content (matches PyMuPDF/known evidence), section headers `## 3.2`/`## 3.3` correctly recovered |
| MinerU (pipeline backend, local FastAPI orchestration) | **EXECUTED** | ~5 s model init + ~15 s server startup | ~5 s actual page processing | `PDF-Extract-Kit-1.0`, HF cache | 8 output files including `input_page16.md` (523 chars, correct content), `_content_list.json`, `_middle.json`, `_model.json`, layout/span visualization PDFs |

## Honest findings

1. **No tool failed to execute.** All six ran to completion with real, inspectable output on a real page, contradicting the prior turn's conservative assumption that execution would require a dedicated compute session. On CPU, a single page took at most ~25 seconds end-to-end (MinerU, including its local API server cold-start).
2. **Not all output was trustworthy.** Table Transformer and RapidTable both reported table-like structures on a page that is plain prose — this is a real methodological gap: table-structure recognition should only run on regions a layout/table-*detection* step has already flagged, not on a whole page indiscriminately. This matters for Phase 4 (structural evidence reconstruction) — table detections on this page should be discarded, and future targeted-recovery runs should pipe layout detection output into table recognition rather than running both independently.
3. **`table_transformer` (pip package) vs. `transformers.TableTransformerForObjectDetection`**: the originally-audited package name is importable but its own inference pipeline needs a different checkpoint format than what's cached locally. The equivalent model is usable through `transformers` instead — this is the practical invocation path for future recovery work, not the standalone `table_transformer` package.
4. **MinerU's default backend is `hybrid-engine`**, which the CLI help states needs local compute for high accuracy; `pipeline` (used here) is described as "more general" and worked correctly on CPU without requiring GPU.

## Conclusion

All six tools: **EXECUTED**. Zero `INSTALLED_BUT_FAILED`, `MODEL_MISSING`, `DEPENDENCY_CONFLICT`, or `UNAVAILABLE`. This single-page smoke test is not yet the full 20–30 page targeted recovery set (Phase 2/3) — it establishes that the toolchain is genuinely usable, at the runtimes measured above, before committing to a larger run.
