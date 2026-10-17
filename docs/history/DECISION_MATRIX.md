# DECISION_MATRIX.md
## Option Comparison — RC-019 Resolution · P5.0 · Phase 8
## Status: PROPOSED (documentation only)

## Options evaluated

- **Option A — Continue dual databases.** Do nothing; `kb_p44.db` and `normalized_regimens.sqlite`
  keep evolving independently.
- **Option B — Full migration.** Immediately swap the engine to read `kb_p44.db` directly (naive:
  atomic facts reshaped ad hoc into `RecommendationCandidate` at read time, no schema extension).
- **Option C — Adapter layer.** The path specified in this package: extend `kb_p44`'s contract with
  a `Regimen` aggregate, build a port/adapter, shadow-validate, then cut over (see
  `KNOWLEDGE_PLATFORM_MIGRATION_RFC.md`).
- **Option D — Hybrid (permanent dual-store by design).** Keep both stores permanently, each
  serving a distinct purpose (e.g. `kb_p44` = audit/traceability ledger, `normalized_regimens` =
  engine-serving store), with a defined, governed sync process between them instead of convergence.

## Evaluation

| Criterion | A: Dual (status quo) | B: Full migration (naive) | C: Adapter layer (recommended) | D: Permanent hybrid |
|---|---|---|---|---|
| **Complexity (near-term)** | Lowest — no work | Low — looks simple, but hides the granularity mismatch (§SSOT RFC) | Medium — five phases, real design work, but each phase is small and reversible | Medium-high — requires designing and maintaining a permanent sync contract, arguably more ongoing complexity than converging once |
| **Clinical safety** | **Degrading** — silent drift risk between what P4.4 "knows" and what the engine serves, no detection mechanism (EAR-1/EAR-7) | **High risk** — reshaping atomic facts into regimens ad hoc at read time, without the Migration RFC's parity validation, risks silently wrong `RecommendationCandidate`s reaching the frozen engine | **Lowest risk** — Phase 4's shadow validation requires zero unexplained divergence on the full golden set before cutover; rollback is a config flip through Phase 5 | Medium — safety depends entirely on the sync process's rigor, which does not exist today and would need the same design effort as Option C without ever reaching a single source of truth |
| **Technical debt** | **Grows** — RC-019/020/021/022 compound; P4.4's certified rigor stays orphaned indefinitely | Reduces store count but likely creates NEW debt (a rushed regimen-reshaping layer with no invariant coverage, no golden-case parity proof) | **Reduces** — one canonical contract, `kb_p44`'s existing invariant/CKY/coverage tooling extends to cover the engine-serving path too | **Does not reduce** — codifies the fragmentation permanently; every future schema change must be made twice and kept in sync by policy, not by construction |
| **Performance** | Unaffected (unmeasured baseline) | Unknown — no parity/perf testing before cutover in this option's definition | Explicitly measured before cutover (Migration RFC Phase 4/5 exit gates); Query Layer RFC's indexing avoids RC-011's substring-scan cost | Unaffected for the engine's read path; adds a sync job's ongoing compute cost |
| **Future maintenance** | Two codebases' worth of ongoing knowledge-model changes, no convergence path | Some reduction, but the reshaping logic becomes ad hoc technical debt itself | **Best** — one model, one invariant suite, one CKY/coverage measurement going forward | Two models forever, plus a sync layer to maintain — worst long-term maintenance burden |
| **Cost (engineering effort)** | Zero now, unbounded later (compounding drift risk, eventual forced migration under worse conditions) | Low now, high later (rework when the granularity mismatch surfaces in production) | Medium, upfront, bounded — five defined phases with exit gates, each independently small | Medium now (design the sync), then a permanent recurring cost |
| **Risk (of the option itself)** | Low immediate risk, **high compounding risk** | **High** — skips the parity/validation discipline this project has proven necessary (PR-001, RC-017 were both found by exactly this kind of rigor) | **Low** — every phase is additive and independently rollback-able; no phase touches production before its exit gate is met | Medium — the option's own success depends on a sync mechanism not yet designed, which is itself a project of comparable scope to Option C |

## Recommendation
**Option C (Adapter layer).** It is the only option that (a) does not leave clinical-safety-relevant
drift risk unaddressed indefinitely (rules out A and D), and (b) does not repeat this project's
own recent lesson — that skipping measured, adversarially-audited validation before trusting a
migrated pipeline produces exactly the kind of silent defect (RC-001, RC-017) this session spent
significant effort finding and fixing (rules out B, which has no analogous validation step by
design).

Option D is included for completeness because "keep both, sync them" is a legitimate architecture
in some domains, but here it does not reduce risk versus Option C — it requires designing and
permanently maintaining a sync contract with the same rigor Option C's Migration Phases 1-4 already
specify, without ever reaching the simplification (one model, one invariant suite) Option C ends
with. It is a strictly worse version of the same amount of work.
