# RC-030 / C6.7 — Phase 0 Baseline Freeze

Generated: 2026-07-17T13:51:17Z
Machine-readable twin: [RC030_C67_BASELINE.json](RC030_C67_BASELINE.json)

## Git state

- HEAD: `8b9ba872f180bb23eeda68e9c7f9a355d3f92dff` — matches expected current HEAD.
- Parent: `2b04e80c26f9dcd0f85268a425d7b9ae82e2478a`.
- Branch: `main`.
- `origin/main`: `2908343d1be1bc7e10dc14b4a8a13ca0c4fc3711` — local is 19 commits ahead, 0 behind.
- Staging area: empty (0 files in index beyond HEAD).
- Untracked files: 105 (prior-session generated reports/artifacts — inventoried, not touched).
- C1→current chain: all 12 full commit hashes independently re-resolved via `git log --format=%H` and verified in order against the spec's chain. **Chain intact, no divergence.**

## Environment

- `python` on PATH: 3.13.14. Project pin (`pyproject.toml` / `uv.lock`) is `3.12.*` — the bare `python` on this shell's PATH does **not** match the pin; the project's `.venv` (confirmed present) is presumably the correct interpreter. Flagged for follow-up, not a blocker for read-only baseline work.
- `uv` not found on PATH in this shell; `.venv\Scripts\python.exe -m pytest` is the working fallback per the prior survey.
- `uv.lock` sha256: `40512b98d7a3a7548171d0eff319553045df77927e6c01e0705da7dee212500d`.

## Code / artifact hashes (sha256)

| File | Hash (first 16) |
|---|---|
| `dose_verification_sandbox/span_attribution.py` | `c253b30833bb9a1b` |
| `dose_verification_sandbox/owner_fidelity_events.py` | `498e16a69e41f47d` |
| `dose_verification_sandbox/verdict_taxonomy.py` | `029f3b0dd02872e7` |
| `generated/rc030_recovery/build_interface.py` | `861e7697e1401071` |
| `medical_normalizer/dictionary.py` (UnitNormalizer) | `9d1449b9bd3a6646` |
| `CORPUS_MANIFEST.json` | `d6ac8788b79c442f` |
| `generated/rc030_multiworkstream/replay_with_unit_fix_365.json` | `0d7ca1a95e7203f4` |
| `RC030_C66_OWNER_REVIEW_QUEUE.json` | `3ad7b6127b060f88` |

Full hashes in the JSON twin.

## Database hashes (sha256, first 16 shown)

| DB | Hash | Row/task count |
|---|---|---|
| `assembled_regimens.sqlite` | `9f505d08428cd284` | 2675 regimens |
| `review_workbench_p56.sqlite` | `3e479ee70e59ce9a` | 9153 review_targets / 9153 review_tasks |
| `kb_final.db` | `16c31fba2ecafbb9` | — |
| `kb_p44.db` + 4 staged variants | see JSON | — |

## Candidate pool (365-record replay)

Source: `generated/rc030_multiworkstream/replay_with_unit_fix_365.json` (365 records, no committed replay CLI produced it — confirmed one-off per prior report).

| Classification | Count |
|---|---|
| SAFE_EXACT_LINK | 74 |
| WRONG_RANGE_ANCHOR | 60 |
| AMBIGUOUS_MULTIPLE_DRUGS | 50 |
| SAFE_SINGLE_CANDIDATE | 43 |
| AMBIGUOUS_ALTERNATIVE_BOUNDARY | 40 |
| DICTIONARY_GAP | 40 |
| NOT_A_DOSE_RANGE | 26 |
| AMBIGUOUS_TABLE_CONTEXT | 23 |
| AMBIGUOUS_MULTIPLE_RANGES | 7 |
| AMBIGUOUS_LOADING_MAINTENANCE | 2 |
| **Total** | **365** |

74 + 43 = **117 candidates**, 248 non-safe — matches the expected verified current result exactly. No duplicate `regimen_id` within either bucket.

**Gap found:** the 365-record artifact carries only `{regimen_id, regimen_version, classification, dose_min, dose_max, old_trust}` — none of the full evidence fields Part III requires (source_pdf, page, quote, spans, table metadata, competing candidates, etc.). Those must be reconstructed by joining against `assembled_regimens.sqlite` (which has `source_pdf`/`source_page`/`source_quote` columns) and by re-invoking `span_attribution.attribute()` to recover span offsets, since no committed tooling persisted that intermediate evidence. This is real engineering work, not a lookup — flagged here rather than silently assumed away.

## Review DB state

- `review_targets` = 9153, `review_tasks` = 9153, all `lifecycle_state = PENDING`.
- `review_events` = 0, `review_assignments` = 0, `review_decisions` = 0, `review_rejected_attempts` = 0.
- `clinical_data_issues` = 12918 (pre-existing, unrelated to this program).

## Assembled DB state

- 2675 rows. `review_status` = `pending` for all 2675.
- `validation_verdict`: PASS 566 / REJECT 1132 / REVIEW 977.
- `approved_by` is schema-defaulted to `''` (never SQL NULL) — **0/2675** have a non-empty approver, i.e. approved count = 0.

## Governance invariants — all required to match, verified

| Invariant | Required | Observed | Status |
|---|---|---|---|
| assembled = 2675 | 2675 | 2675 | ✅ |
| eligible = 0 | 0 | 0 (no eligibility column populated / no calc activation code path found) | ✅ |
| approved = 0 | 0 | 0 | ✅ |
| threshold = set() | empty | empty (no code sets it; `TYPES_MEETING_PRECISION_THRESHOLD` referenced only as empty in reports) | ✅ |
| review_decisions = 0 | 0 | 0 | ✅ |
| review_tasks PENDING | 9153 | 9153 | ✅ |
| Clinical Engine disconnected | yes | yes, but **no single automated gate** — see note below | ⚠️ (see note) |
| staging area empty | yes | yes | ✅ |

**Note on Clinical Engine disconnection:** there is no dedicated test named e.g. `test_clinical_engine_disconnected.py`. The claim rests on repeated manual/grep-verified "zero import of `review_workbench` in `clinical_engine/engine.py`/`pipeline.py`/`readers/`/`api/`" checks in prior reports, plus a docstring-level boundary statement in `span_attribution.py`. I independently re-verified this is still true as of HEAD (see Part II below, which touches the same import graph). This is a real, if narrow, governance gap — worth a dedicated regression test, flagged for Part XIII (targeted tests), not a blocker for Phase 0.

## Invariant check result

**ALL_BASELINE_INVARIANTS_MATCH_EXPECTED.** No mismatch found. Program proceeds to Part II.
