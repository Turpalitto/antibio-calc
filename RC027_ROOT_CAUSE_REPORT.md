# RC027_ROOT_CAUSE_REPORT.md
## Phase 1 — Root Cause Reproduction, Full 9,153-Task Population
## 2026-07-15 · Measured against the unmodified production `ReviewService`/`ReviewStore`

## Exact root cause (traced, not inferred)

**Producer** (`clinical_engine/review_workbench/queue_builder.py`):
- `_regimen_provenance(regimen)` (line 100-101) and the `TherapeuticOption` provenance builder
  (line 138) both spread `FieldProvenance` dataclass instances into dicts:
  `{"field": name, **_jsonable(provenance)}` → real keys produced:
  **`field, source_object_id, source_document, source_location, source_store, scope`**
  (`clinical_engine/regimen/clinical_regimen.py:39-45` — `FieldProvenance` was designed to carry a
  *reference* to the source, never the literal quoted text; it has no `original_text` field and
  never did).
- The `GoldenCase` producer (line 162) passes `case.get("provenance", {})` straight through — the
  golden-case JSON schema's provenance shape is `{author, verified_at, source}`
  (`clinical_engine/golden_cases/schema.json`), again never `original_text`/`source_quote`.

**Consumer** (`clinical_engine/review_workbench/service.py:229`):
```python
"original_source_wording": [item.get("original_text") or item.get("source_quote")
                            for item in snapshot["provenance"]]
```
Reads exactly two key names. Neither producer above ever writes either one → **guaranteed `None`
for every entry**, deterministically, not intermittently.

## First point where original wording disappears
Not at storage, not at serialization — **at packet-construction time**, in `service.py`'s
`packet()` method, because it assumes a provenance-dict key vocabulary
(`original_text`/`source_quote`) that the two richest producers (`ClinicalRegimen`,
`TherapeuticOption`) never use. The data is NOT lost upstream: `regimen.source_quote` /
`option.source_quote` (the object's own field, not its `field_provenance` entries) is populated
100% of the time — confirmed in the pilot batch and reconfirmed here. `packet()` simply never looks
there.

## Measured across all 9,153 tasks (not the 30-task pilot alone)

| target_type | total tasks | packets with populated `original_source_wording` | % |
|---|---:|---:|---:|
| **ClinicalRegimen** | 1,556 | **0** | **0%** |
| **TherapeuticOption** | 652 | **0** | **0%** |
| **GoldenCase** | 7 | **0** | **0%** |
| ClinicalDataIssue | 1,265 | 1,182 | 93.4% |
| CorpusExclusionDecision | 58 | 0 | 0% (by design, see below — distinct issue) |
| ConflictRecord | 5,615 | 0 | 0% (by design, see below — distinct issue) |

**By issue_type** (explains the ClinicalDataIssue split): `DOSE_NOT_EXTRACTED` (638/638),
`DOSE_NOT_PARSED` (116/116), `DOSE_DAILY_MISREAD` (61/61), `DOSE_UNIT_GROUP` (367/367) — all
**populated**, because their producers pass `provenance=[{"source_quote": ...}]` directly (the
correct key, by coincidence of a different, simpler code path in `queue_builder.py`'s
`issue`/`dose_groups` loops). `EXTRACTION_GAP_CANDIDATE` (0/83 populated) is **not** a mapping bug —
these 83 specific source records have a genuinely **empty `kr_quote` field in the underlying issues
JSON** (verified: the key is present, correctly read by `packet()`, but the value is `""`) — a real
data gap, not a code defect. Correctly reported as `MISSING`, not silently hidden.

## Scope decision: what RC-027 covers and what it does NOT

**RC-027 (this fix) covers:** `ClinicalRegimen` (1,556), `TherapeuticOption` (652), `GoldenCase` (7)
— **2,215 tasks** where rich per-field provenance genuinely exists (as `FieldProvenance` records or
a golden-case provenance dict) but under a different key vocabulary than `packet()` reads. This is a
pure **producer/consumer key-mapping bug** — fixable by making `packet()` read the real field names,
with zero data loss.

**Explicitly OUT of RC-027's scope** (a different, separate root cause — not touched here, per the
Phase 7 instruction "do not fix it unless it is a direct part of RC-027"):
- **`ConflictRecord` (5,615 tasks)** — `provenance=[]` always, by explicit design
  (`queue_builder.py` line ~208). No per-field provenance concept was ever implemented for
  conflicts; `source_references` (guideline A/B ids) still reaches the packet, so a reviewer sees
  *which guidelines* conflict, just not a quoted excerpt from either. Register separately if this
  gap should be closed (candidate: a future RC, not RC-027).
- **`CorpusExclusionDecision` (58 tasks)** — same pattern, `provenance=[]` always; `source_references`
  (pdf + locations) still reaches the packet.

## Backward compatibility impact
The fix (Phase 3) must accept the CURRENT provenance dict shapes for the already-working producers
(`ClinicalDataIssue`'s `{"source_quote": ...}` shape) **and** the `FieldProvenance`-derived shape
(`ClinicalRegimen`/`TherapeuticOption`) **and** the golden-case shape (`{author, verified_at,
source}`) without requiring any producer to change its output format — a precedence-ordered lookup
(Phase 2) that tries each known shape in a fixed, documented order. No schema migration, no
re-ingestion of the 9,153 already-stored `review_targets` rows is required — the fix is entirely in
the read path (`packet()`), which is why it is backward-compatible by construction.
