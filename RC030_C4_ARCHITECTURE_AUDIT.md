# RC-030 C4 — Architectural Boundary Audit (Part II)

## Import graph (from actual `import`/`from` statements, not assumed)

```
validation_unit.py      -> hashlib, json, dataclasses, typing (stdlib only)
verdict_taxonomy.py     -> validation_unit (HUMAN_FIDELITY_VERDICTS)
owner_fidelity_events.py -> validation_unit (HUMAN_FIDELITY_VERDICTS); re, dataclasses (stdlib)
precision_calculator.py -> owner_fidelity_events, verdict_taxonomy, validation_unit; math, dataclasses (stdlib)
```

Strict DAG, no cycles: `validation_unit` is the base; `verdict_taxonomy` and `owner_fidelity_events` both depend only on it; `precision_calculator` depends on all three.

Grep across all four files for `clinical_engine`, `medical_normalizer`, `sqlite3`, `open(`, `localStorage`, `requests.`, `socket.`, `subprocess.` — **zero matches**. No Clinical Engine import, no parser/normalizer import, no database import, no filesystem write, no browser/localStorage assumption, no network dependency.

Mutable global state: none. `HUMAN_FIDELITY_VERDICTS`, `UI_ACTION_TO_CANONICAL`, `CONFIRMING_VERDICTS`/etc., and `TYPES_MEETING_PRECISION_THRESHOLD` (imported by tests, not by these modules) are all module-level immutable-by-convention sets/dicts assigned once at import time and never reassigned by any function in these four files (verified: no `global` statement, no mutation of these names anywhere in the four modules).

## Module classification

| Module | Classification | Rationale |
|---|---|---|
| `validation_unit.py` | **A — pure immutable model** | Frozen-shape dataclass + deterministic hash function over its own fields. No I/O, no mutation after `__post_init__`. |
| `verdict_taxonomy.py` | **B — pure deterministic validator** | `map_ui_action_to_canonical()` is a total, deterministic dict lookup with no side effects; taxonomy groups are static sets. |
| `owner_fidelity_events.py` | **B — pure deterministic validator** | `validate_event`/`validate_events`/`filter_real_events`/`find_duplicate_event_ids`/`validate_supersession_chain` are all pure functions over `dict`/`list` inputs; return `ValidationIssue`/`bool`/`dict`/`list` — never write anywhere. |
| `precision_calculator.py` | **C — pure metric calculator** | `compute_precision`/`compute_governed_precision`/`wilson_interval` are pure functions; `PrecisionResult` is a plain dataclass returned to the caller, never persisted by this module. |

No module in C4 falls into D (event persistence), E (UI), F (database), G (Clinical Engine), H (mixed, needs split), or I (unsafe). All four are safe, pure, offline governance/QA code.

## Required boundary checks

| Requirement | Status |
|---|---|
| Verdict taxonomy may not depend on UI | **PASS** — `verdict_taxonomy.py` imports only `validation_unit`; UI action strings are input parameters to a pure function, not a UI dependency |
| Validation-unit identity may not depend on DB writes | **PASS** — `compute_identity_hash()`/`canonical_identity_payload()` read only the dataclass's own fields; no I/O |
| Owner-event validator may not depend on browser localStorage | **PASS** — `owner_fidelity_events.py` operates on plain `dict`/`list`; the word "localStorage" does not appear in the module |
| Precision calculator may not write decisions | **PASS** — returns `PrecisionResult`; no write path exists in the module |
| No C4 module may import or activate Clinical Engine | **PASS** — grep confirms zero `clinical_engine` references |
| No C4 module may alter calculation eligibility directly | **PASS** — `DoseSemanticEvidenceUnit.calculation_eligibility` is hard-constrained to `"BLOCKED"` in `__post_init__` (pre-existing, re-verified); `TYPES_MEETING_PRECISION_THRESHOLD` is never assigned to by any of the four modules (grep confirms; also regression-tested in `test_c4_governance_hardening.py`) |

## Findings and classification (Phase 15 categories)

Findings are classified A (deterministic correctness defect — fix now), B (missing validation guard — fix now), C (missing test — add now), D (documentation defect — fix now), E (backward-compat — additive versioning), F (architectural redesign — defer), G (UI concern — defer to C5), H (database concern — out of C4), I (clinical governance decision — owner required), J (no defect).

| # | Finding | Class | Action taken |
|---|---|---|---|
| 1 | `validation_unit.py` had a `unit_id` string field but no deterministic identity-hash function or documented identity contract (parser_version in/out of identity was undecided) | A | **Fixed.** Added `compute_identity_hash()`/`canonical_identity_payload()` over a fixed `_IDENTITY_FIELDS` tuple; documented the identity contract in the module docstring (parser_version excluded — travels as provenance, not identity; see rationale in-file). Additive `validation_unit_schema_version` field added, default preserves existing construction calls. |
| 2 | `owner_fidelity_events.validate_event()` never checked `reviewer_id` against any expected value | B | **Fixed.** Added `GENUINE_OWNER_REVIEWER_ID = "OWNER_LOCAL"` constant and an explicit equality check. |
| 3 | No check rejected AI-provenanced records (`review_origin`, `owner_verified`, `clinically_approved`, `human_validated`) even if `reviewer_id` were spoofed to `OWNER_LOCAL` | B | **Fixed.** Added `_AI_PROVENANCE_MARKER_FIELDS` presence check (checked *before* the reviewer_id check, and short-circuits further checks) plus an explicit `_REJECTED_REVIEW_ORIGINS` value check. Regression-tested with 5 parametrized cases including a reviewer_id-spoofed AI event. |
| 4 | `test_event` field type was never validated — `validate_event()` only checked presence, not that it was a JSON boolean; `filter_real_events()` used `not e.get("test_event", True)`, which silently mis-handled `test_event=0` (falsy int, would have been **included** as a real event) | A | **Fixed.** `validate_event()` now requires `isinstance(event["test_event"], bool)`. `filter_real_events()` now requires `isinstance(..., bool) and ... is False` — strict, no int/str coercion. Regression-tested against `"false"`, `"true"`, `0`, `1`, `None`, `"False"`. |
| 5 | No duplicate `event_id` detection existed | B | **Fixed.** Added `find_duplicate_event_ids()` and wired it into `validate_events()`. |
| 6 | No append-only/supersession guards existed at all (`previous_event_id`/`supersedes_event_id` were schema fields but never validated) | B (minimal), F (full DAG resolution deferred) | **Partially fixed.** Added `validate_supersession_chain()` covering the three unambiguous violations explicitly named in the mission: self-supersession, a 2-cycle, and a dangling reference to a non-existent `event_id`. **Deferred (F):** full N-length cycle detection and "two active terminal events for one validation unit must be resolved deterministically" — this requires a real supersession-graph resolution policy design, which is a genuine architectural decision, not a bug fix; flagged for a dedicated future turn rather than improvised here. |
| 7 | `precision_calculator.compute_precision()` trusted its `verdicts` argument completely — no defense if a caller forgot to run `owner_fidelity_events.validate_events`/`filter_real_events` first | B | **Fixed.** Added `compute_governed_precision()` as a safe entry point that runs full validation internally and returns `STATUS_GOVERNANCE_BLOCKED` for any structurally invalid batch (including AI-provenanced or non-owner events) rather than silently scoring whatever survived. `compute_precision()` itself is kept as the low-level pure function (still useful for tests / already-filtered pipelines) — not removed, per "prefer minimal additive hardening." |
| 8 | `verdict_taxonomy.py` had no `CONFIRMING_VERDICTS`/`ERROR_VERDICTS`/`UNRESOLVED_VERDICTS`/`SOURCE_BLOCKED_VERDICTS`/`PRECISION_SCORABLE_VERDICTS` groups; `precision_calculator.py` duplicated its own private copies of the same buckets, risking drift | A (duplication is a latent correctness risk), D | **Fixed.** Canonical groups added to `verdict_taxonomy.py` with a disjointness+coverage assertion; `precision_calculator.py` now imports them instead of re-declaring. |
| 9 | `PrecisionResult` had no status-code field and no metric name — the result was an unlabeled float that could be mistaken for a different kind of accuracy metric | A, D | **Fixed.** Added `metric_name` (`"OWNER_SOURCE_FIDELITY_PRECISION"`, module constant `METRIC_NAME`) and a `status` field populated from the seven required status constants (`NO_EVENTS`, `INSUFFICIENT_SCORABLE_EVENTS`, `BELOW_MINIMUM_SAMPLE`, `BELOW_PRECISION_THRESHOLD`, `MEETS_EXPLORATORY_THRESHOLD`, `GOVERNANCE_BLOCKED`, `ELIGIBLE_FOR_OWNER_GATE_REVIEW`). `ELIGIBLE_FOR_OWNER_GATE_REVIEW` is defined but never auto-assigned — reaching it is an owner decision (**I**), not something this module can compute unilaterally. |
| 10 | No test existed proving `TYPES_MEETING_PRECISION_THRESHOLD` cannot be modified by any C4 code path | C | **Fixed.** Four dedicated regression tests in `test_c4_governance_hardening.py` (import, high-synthetic-precision, writing owner events, invalid events). |
| 11 | Exact `event_id`s scored by a precision calculation were not tracked/reportable | F | **Deferred.** Would require restructuring the calling convention (verdict dicts would need to carry their source `event_id` end-to-end); not a safety defect, a reporting nicety. Left for a future turn if the owner wants full per-calculation audit trails. |
| 12 | Regimen 6657's real owner-event export file does not exist anywhere in this worktree | F/documentation | **Handled.** `RC030_C4_BASELINE.md` documents the absence; a schema-compliant *synthetic* reproduction of the documented facts is used in tests instead, clearly labeled as synthetic, not a copy of a real file. |
| 13 | `dose_verification_sandbox/data/*.json` real precision/metrics files (`full_corpus_metrics.json`, etc.) are outside the four C4 modules | H (database/data concern) | **Out of scope**, correctly untouched — these are generated artifacts under `.gitignore`, not part of the governance-code layer. |
| 14 | Owner-review HTML interface and localStorage export format | G | **Deferred to C5** per owner authorization — not included in C4. |

## Result

All four candidate modules classify as pure governance/QA code (A/B/C — no D/E/F/G/H/I architecture concerns requiring a split). All six required import-boundary checks pass. 14 findings recorded; 9 fixed now (categories A/B/C/D), 1 partially fixed with the remainder explicitly deferred (6), 2 fully deferred as out-of-scope architectural/reporting work (11, 13/14 are policy, not defects), 1 handled as a documentation/fixture decision (12). No redesign was performed beyond what each finding required — additive hardening only, consistent with "prefer minimal additive hardening; do not redesign modules without a proven need."
