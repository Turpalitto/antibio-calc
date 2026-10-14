# RC-030 C7 — Migration and Engine Gate Matrix (Phase 28)

> **Historical pre-execution matrix.** C7 source-fidelity review subsequently
> closed on 2026-07-30. The unmet gates below describe the state before owner
> execution and are not current. See
> `RC030_C7_OWNER_VS_AI_COMPARISON_REPORT.md`.

| Gate | Description | Status | Evidence | Blocker | Owner approval required | Physician review required | Code dependency | Data dependency | P6 blocked by this gate? |
|---|---|---|---|---|---|---|---|---|---|
| **A** | Source attribution | **PARTIAL** | 117/365 (32%) reach `SAFE_EXACT_LINK`/`SAFE_SINGLE_CANDIDATE` after C6.5's unit-normalization fix | 248 records remain ambiguous/wrong/dictionary-gap/table-blocked | No (engine work) | No | `span_attribution.py` (committed) | `source_quote` text, real PDF corpus (available) | Yes |
| **B** | Owner source-fidelity validation | **NOT MET** | 0 genuine owner events exist | No owner review has occurred; also, supersession-chain resolution in `compute_governed_precision()` is incomplete (see C7 simulation report) | Yes | No | `owner_fidelity_events.py`/C5 interface (both committed, both tested) | Real owner review sessions (not performed) | Yes |
| **C** | Minimum sample | **NOT MET** | `MIN_SAMPLE_SIZE=30` defined in code, never exercised against real data | No real events to sample | Yes (ratify the 30 default) | No | `precision_calculator.py` (committed) | Real owner events | Yes |
| **D** | Precision threshold | **NOT MET** | `_EXPLORATORY_PRECISION_THRESHOLD=0.95` is informational only; no governed activation threshold exists | No owner-ratified clinical threshold | Yes | Likely yes | `precision_calculator.py` (committed) | Real owner events | Yes |
| **E** | Confidence bound | **PARTIAL** | Wilson lower bound implemented and tested; not yet chosen as the *governing* method by the owner | Method choice not ratified (see `RC030_C7_OWNER_VALIDATION_PLAN.md`) | Yes | No | `precision_calculator.wilson_interval()` (committed) | None (method choice only) | Yes |
| **F** | Authoritative data migration | **NOT AUTHORIZED** | 0 rows migrated; `RC030_C66_...md` documents 117 candidate rows exist but none written to any authoritative table | Explicit non-authorization by every turn's owner instructions to date | Yes (separate, explicit) | Yes | Migration script design exists (`RC030_AUTHORITATIVE_RANGE_MIGRATION_PROPOSAL.md`), not implemented as executable code | Gates A-E must all clear first | Yes |
| **G** | Adapter compatibility | **UNCHANGED FROM C2/C3** | `CanonicalRegimenProviderAdapter` remains validation-only; live pipeline wired to legacy `SQLiteReader` | None new this turn | No (already documented) | No | `clinical_engine/readers/canonical_regimen_provider.py` (pre-existing) | None | No (informational) |
| **H** | Clinical Engine integration | **NOT STARTED** | Clinical Engine disconnected throughout this entire program (re-verified every turn) | Gates A-G must clear first; explicit non-authorization | Yes | Yes | None yet | None yet | Yes |
| **I** | End-to-end clinical QA | **NOT STARTED** | No calculation has ever been activated in this program | Gates A-H must clear first | Yes | Yes | Depends on final Clinical Engine integration design | Real clinical review | Yes |
| **J** | Release approval | **NOT STARTED** | N/A | All prior gates | Yes | Yes | N/A | N/A | Yes |

## Summary

**Gate A (source attribution) made real, evidence-backed progress this turn** — from 0 to 117 candidate rows via a genuine engine defect fix, not a relaxed rule. **No other gate advanced.** Gates B-J all remain blocked on real owner (and eventually physician) review activity that is explicitly outside this turn's — and every prior turn's — authorization. **P6 remains BLOCKED** by gates B through J regardless of Gate A's progress; Gate A alone is necessary but nowhere near sufficient.
