# RC030_SCHEMA_RESPONSIBILITY_DECISION.md

Status: RC-030 Evidence Validation, Phase 10. Decision-support document, not an implemented
migration. **No change made to `assembled_regimens.sqlite` or any other source database by this
document or by RC-030 generally.**

## Question

Where should `denominator_time` (per-dose vs per-day) originate, long-term?

## Options assessed

**A. Extraction layer** (raw PDF → atomic objects, e.g. `kb_p44.db`'s `Dose` objects)
- Source fidelity: highest possible — closest to the original text, one extraction pass captures it
  once, correctly, for every downstream consumer.
- Rebuild requirement: full re-extraction of 24,705 `Dose` objects in `kb_p44.db` — expensive, and
  per `DOSE_VERIFICATION_SANDBOX_AUDIT.md`, `kb_p44.db`'s `Dose` objects are not even what
  `assembled_regimens.sqlite` is built from today (RC-019: engine/assembly reads `normalized_regimens`,
  not `kb_p44` directly) — so this option requires resolving RC-019's disconnect first, a much larger
  undertaking than RC-030 itself.
- Versioning/provenance: excellent — extraction-layer provenance is already the most granular in the
  system.
- **Verdict: correct long-term home, wrong place to start** — blocked on RC-019.

**B. Normalizer layer** (`medical_normalizer`, frozen package)
- Source fidelity: good — this is where `DoseNormalizer`/`UnitNormalizer` already live.
- Rebuild requirement: `medical_normalizer` is explicitly frozen per project convention (`AGENTS.md`,
  `PROJECT_STATE.md`) — changing it is a larger governance decision than RC-030's scope.
- Backward compatibility: adding a field here would require re-running normalization + all downstream
  consumers, and this package's frozen status exists specifically to prevent incidental scope creep.
- **Verdict: not appropriate for RC-030 to touch.**

**C. Canonical assembly layer** (`clinical_engine/regimen/store.py`, writes `assembled_regimens.sqlite`)
- Source fidelity: this is where the `dose`/`unit`/`frequency` columns already live — adding
  `denominator_time` here is the smallest structural change that fixes the root cause at its actual
  location (the P5.3 Regimen Assembly Engine already reads `source_quote`; it currently just doesn't
  extract this one additional field from it).
- Rebuild requirement: re-run the assembly engine (`assembly_engine.py`) once against existing
  `normalized_regimens`/`kb_p44` inputs — no new extraction pass needed, since `source_quote` is
  already carried through.
- Backward compatibility: additive column, `NULL`-able, does not break the 2,675 existing rows —
  can be backfilled by running the *same* text-window logic this RC-030 validation built
  (`semantics_parser.py`), just moved into the assembly engine instead of a downstream sandbox layer.
- Versioning: `assembled_regimens` already has `version`/`snapshot_version`/`assembly_ruleset_version`
  columns — a new `assembly_ruleset_version` bump would cleanly version this change.
- Conflict handling: the existing `needs_review_reasons` mechanism already exists for exactly this
  kind of "extracted but uncertain" flagging.
- Effect on the 2,675 existing rows: fully backfillable non-destructively (additive column).
- Effect on future extraction: none — this only changes what the *assembly* step derives from
  already-available `source_quote` text, not what gets extracted from PDFs in the first place.
- **Verdict: correct, minimal, actionable target.**

**D. Additive semantic enrichment layer** (what RC-030 actually built —
`dose_verification_sandbox/semantics_*.py`)
- Source fidelity: same underlying logic as option C, just running downstream of the source-of-truth
  table instead of inside it.
- Rebuild requirement: none — this is exactly why it was the right choice *for a QA sandbox that must
  never mutate `assembled_regimens.sqlite`* (per the sandbox's own hard constraint).
- Backward compatibility: perfect — by construction, since it never touches the table it reads from.
- Versioning/provenance/conflict handling: implemented (`semantics_store.py`'s idempotent,
  content-hash-deduplicated append-only store).
- Effect on the 2,675 existing rows: none (read-only).
- Effect on future extraction: none.
- **Verdict: correct for a read-only QA tool. Wrong as the permanent home for this data** — every
  other consumer of `assembled_regimens.sqlite` (a future Clinical Engine cutover, a future physician
  review UI, a future golden-dataset build) would have to independently re-derive or import this
  sandbox's enrichment layer to get the same benefit, which does not scale as a permanent
  architecture.

## Decision

**Short term (already done): Option D.** The sandbox's enrichment layer is the correct, safe way to
demonstrate and validate the fix without touching production data, and is where RC-030's evidence
(precision metrics, risk audit, 12-case revalidation) was generated.

**Long term (recommended, not implemented here): Option C.** Add `denominator_time` (and,
separately, `max_daily_dose`/`max_single_dose`) as new nullable columns to `assembled_regimens`,
populated by porting `semantics_parser.py`'s logic (already proven against real data in this
validation) into `clinical_engine/regimen/assembly_engine.py`, gated behind a new
`assembly_ruleset_version`. This requires:

1. Owner/governance sign-off (Architecture Change, per `ROOT_CAUSE_REGISTER.md` RC-030's Resolution
   column) — not something this validation pass can authorize on its own.
2. A migration plan analogous to `MIGRATION_PLAN_NORMALIZED_REGIMENS.md`'s existing pattern.
3. Re-running the *same* precision validation this document's sibling reports performed, against the
   assembly-engine's version of the logic, before treating its output as more trustworthy than the
   sandbox's (moving code into the assembly engine does not itself increase precision — the 99%
   threshold gate from `RC030_PRECISION_METRICS.md` still applies).

**Not recommended**: Option A/B until RC-019 (engine/assembly disconnect from `kb_p44`) and the
`medical_normalizer` freeze are separately resolved — both are larger, already-tracked efforts outside
RC-030's scope.
