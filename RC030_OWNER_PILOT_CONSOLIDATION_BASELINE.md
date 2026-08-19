# RC-030 Owner Pilot Consolidation — Baseline

Recorded 2026-07-16 before Phase 1+ work.

- HEAD: `394818675b0ed199e03cae1d89e38a488f5102ce` (`3948186`)
- `git status`: nothing staged. Untracked Part III artifacts accumulate across turns (this turn's baseline + prior turns' reports, `dose_verification_sandbox/validation_unit.py`, `precision_calculator.py`, `generated/rc030_recovery/`, etc.) — none committed.
- Source DB hashes: `assembled_regimens.sqlite` = `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9`; `normalized_regimens.sqlite` = `c7b67354b0723ad538a185e561ed94d09b11c019279be9c4c6412c4f1eaa4237` — unchanged.
- Review DB hash: `review_workbench_p56.sqlite` = `3e479ee70e59ce9aafa6ba44718dda68d867dbcc660796b81ff63d2b19ca0f29`; `review_decisions` = 0 rows.
- Approved-object count: 0.
- Active calculation-eligibility count: **0 / 2,675** (live re-derivation).
- Real owner-verdict count: **0** — the owner-review interface is a static HTML file with browser-`localStorage`-only persistence; the previous turn's dry-run test verdicts were explicitly cleared via `localStorage.removeItem(...)` after verification (confirmed in that turn's transcript), and no server-side store of any kind exists for it to have accumulated real data in between turns.
- PDF availability: 125/193 distinct referenced PDFs present locally (65%), 68 missing.
- Generated recovery artifacts present: `generated/rc030_recovery/page_5574_p16/` (smoke test), `generated/rc030_recovery/batch1/` (12-page pilot batch) — both from the prior turn, untouched.

## Required baseline check

- Real owner verdicts = 0 — ✅
- Calculation eligible = 0 — ✅
- Approved objects = 0 — ✅
