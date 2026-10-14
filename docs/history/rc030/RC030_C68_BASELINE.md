# RC-030 / C6.8 — Phase 0 Baseline Freeze

Machine-readable twin: [RC030_C68_BASELINE.json](RC030_C68_BASELINE.json)

## Git state

- HEAD: `fe7782d86e5b63ce9d574b86278d1b14d028bb13` — matches expected (C6.7 final report commit).
- Parent: `a01c9bf695c479583fbb67a0597dd5156692b5e5` (C7-ENTRY).
- `origin/main`: `2908343d1be1bc7e10dc14b4a8a13ca0c4fc3711` — local 24 ahead, 0 behind.
- Staging area: empty.
- Full C6.7 chain re-verified in order: `c27febe` (C6.7-A) → `ed4c87c` (C6.7-B) → `2f80d2c` (C6.7-C) → `a01c9bf` (C7-ENTRY) → `fe7782d` (final report). Matches exactly.
- Untracked files: unchanged category (prior-session generated reports/artifacts) — not a reason to stop, per owner's instruction.

## Code / artifact hashes (sha256, first 16 shown; full in JSON twin)

| File | Hash |
|---|---|
| `uv.lock` | `40512b98d7a3a754` |
| `dose_verification_sandbox/span_attribution.py` | `c253b30833bb9a1b` |
| `medical_normalizer/dictionary.py` | `9d1449b9bd3a6646` |
| `generated/rc030_recovery/build_interface.py` | `e7e8199c53880450` |
| `generated/rc030_recovery/owner_review_template.html` | `d29e209e168fb31c` |
| `tests/dose_verification_sandbox/test_c67_unit_basis_adversarial.py` | `6d48a6667e17a602` |
| `clinical_engine/tests/test_review_workbench_isolation.py` | `8d861cbef9d5d212` |
| `generated/rc030_multiworkstream/replay_with_unit_fix_365.json` | `0d7ca1a95e7203f4` |
| `generated/rc030_c67/candidate_117_manifest.json` | `c31050e13dcb841e` |
| `RC030_C67_EXACT_LINK_OWNER_QUEUE.json` | `7524bdd37bb5693e` |
| `RC030_C67_SINGLE_CANDIDATE_OWNER_QUEUE.json` | `36fffdf03ad7ff88` |

Note: `dose_verification_sandbox/span_attribution.py` hash is unchanged since the C6.7 baseline — C6.7 characterized the unit-basis defect but did not fix it; C6.8's job starts from this exact same file.

## Database state

| DB | Hash | State |
|---|---|---|
| `assembled_regimens.sqlite` | `9f505d08428cd284...` | 2675 rows, 0 approved — identical to C6.7 baseline |
| `review_workbench_p56.sqlite` | `3e479ee70e59ce9a...` | 9153/9153 tasks PENDING, 0 decisions — identical to C6.7 baseline |
| `kb_final.db` | `16c31fba2ecafbb9...` | identical to C6.7 baseline |

**No authoritative database changed between the C6.7 and C6.8 programs.**

## C6.7 verified result (carried forward as C6.8's starting point)

- Initial pool: 74 SAFE_EXACT_LINK + 43 SAFE_SINGLE_CANDIDATE = 117 candidates.
- After independent audit: 53 retained, 18 downgraded, 2 rejected, 1 engine-review-required.
- Two source-quote defects: regimens 5688 and 6052 (quote not found anywhere in cited PDF).
- One unit-basis defect: `_base_unit()` conflates absolute/per-kg/per-day dose bases — 14/117 records affected, 6 of them in the 53-retained exact-link pool.

## Governance invariants — all required to match, verified directly (not inferred)

| Invariant | Required | Observed | Status |
|---|---|---|---|
| assembled = 2675 | 2675 | 2675 | ✅ |
| eligible = 0 | 0 | 0 | ✅ |
| approved = 0 | 0 | 0 | ✅ |
| threshold = set() | empty | empty | ✅ |
| review_decisions = 0 | 0 | 0 | ✅ |
| review_tasks PENDING | 9153 | 9153 | ✅ |
| Clinical Engine disconnected | yes | yes (0 `review_workbench` imports in engine core, re-verified, now with the automated gate added in C6.7) | ✅ |
| staging area empty | yes | yes | ✅ |

## Invariant check result

**ALL_BASELINE_INVARIANTS_MATCH_EXPECTED.** No mismatch. Proceeding to Part II (dose unit model).
