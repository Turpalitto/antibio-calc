# Extraction Architecture

**P4 — Production Document Intelligence context (see ROADMAP.md).**

## Engines (Multi-Engine)

- **Primary:** PyMuPDF — fast, accurate text extraction for digital PDFs.
- **Fallback 1:** MinerU — OCR + layout for scanned / low-text PDFs.
- **Engine 3 (normalization):** Docling (v2.112.0) — unified document representation, advanced parsing, future layout/table support. Installed as additional capability. Does NOT replace PyMuPDF or MinerU.

**Why Docling (not replacement):**
- Provides normalization layer and structured output (text + markdown + objects).
- Supports future layout intelligence (headings, columns, tables).
- Complements existing engines; router decides.
- Keeps existing PyMuPDF + MinerU + per-page fallback + cache + metrics + provenance intact.

## Responsibilities
- PyMuPDF: primary fast text.
- MinerU: OCR fallback when quality low.
- Docling: normalization, unified model, future advanced features.
- Router: quality/per-page decisions, engine selection, unified output.
- Unified Document Model: single `Document` / `Page` (source, pages, full_text, metadata incl. provenance/confidence, tables). Parser / clinical layers see only this. Never bypass.

## Flow (mandatory)
Digital PDF
↓
PyMuPDF (primary)
↓ (if insufficient quality / per-page bad)
MinerU (OCR)
↓ (normalization / future layout)
Docling
↓
Unified Document Model (engine-agnostic)
↓
Clinical Extraction / Knowledge Base

**Agents must never bypass the unified document model.**

## Router + Config
See router.py, config/document_processing.yaml (primary, fallbacks list, per_page_fallback, etc.).

Extensible: register new engines (PaddleOCR etc.) via registry.

## Provenance v2 (P4.7)
page_provenance in metadata: page, source (engine), quality, fallback_reason, ocr_time, etc.

## Current Status (P4.2)
PyMuPDF + MinerU + Docling + Layout (DocLayout-YOLO, Table Transformer, RapidTable).

Layout module added, Unified Layout Model via layout_blocks in Page.

Router extended: extraction -> layout -> unified.

Benchmark and corpus validation done.

See README for matrix and stats.

P4.2 complete.

## P4.2 Layout Intelligence

Added layout.py:

- Uses DocLayout-YOLO for page regions (headings, paragraphs, tables, figures, lists, columns).

- Table Transformer for table detection.

- RapidTable for table structure recognition.

## P4 — Document Intelligence Platform ✅ COMPLETE + Production Ready (2026-07-13)

P4.1 Multi-Engine ✅ | P4.2 Layout ✅ | P4.3 Semantic ✅

Verified real:
- 10/10 tests
- 300+ ents on real PDFs
- Router always applies semantic
- Knowledge Objects + consistency + quality + provenance
- Fallbacks work (flag always set)

P4 goal achieved: PDF → Extraction+Semantic → Objects. No raw text downstream.

Next: P4.4 (Versioned KB, dedup, review, lineage).

Flow:
PDF → Multi-Engine + Layout + Semantic → Versioned KB (P4.4) → Clinical Engine

Agents: use KB. No direct PDF/objects to engine.

KG not default — only if versioning/dedup/consistency prove insufficient.
- 58p clinrec (94k chars, pymupdf): 338 ents via semantic, norm 0.70
- processor: 0.004s on 20k head (16 ents)
- mixed router path can degrade if OCR; fixed to preserve primary text when better for semantic yield.

No Clinical Engine / bundle touch. Frozen preserved.

STEP 3 research: domain dicts + normalizer (823 tests) superior to general NER for this. No install.

Production Ready. See audit.

- Unified Layout Model: layout_blocks in Page as list of dicts {type, bbox, confidence, page, ...}

- Integrated in router after extraction.

- Tables merged into Document/Page.

## Table Pipeline

Layout detects table regions.

Table Transformer + RapidTable for structured tables (HTML-like).

Added to unified model.

## Router Extension

Extended flow:

PDF -> PyMuPDF (primary) -> (OCR?) MinerU -> (Layout?) DocLayout-YOLO -> (Tables?) Table Transformer + RapidTable -> Unified Document

Config extensible.

## Benchmark & Validation

Real runs on project PDFs (low_test, clinrec 58p).

Layout adds time but provides structure.

Full corpus (947 unique) validated via script + samples.

## Capability Matrix (extended)

See README.

## Limitations

- First run model downloads (YOLO, HF models).

- CPU fallback (no GPU assumed).

- Layout on very complex PDFs may need tuning.

- Per-page text from Docling uses .texts + prov.

See ROADMAP for future (P4.3+).
