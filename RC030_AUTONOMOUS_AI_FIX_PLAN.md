# RC-030 Autonomous AI Audit — Proposed Parser Fix Plan

**Design only. No fix is implemented in this task.** Fix-class legend:
1. code-only future-extraction fix (new records benefit; no touch to existing artifacts)
2. current-artifact improvement (re-run parser over existing `source_quote`, sandbox-side, no DB change)
3. historical-corpus improvement after reprocessing (normalizer/assembly change + reprocess)
4. full corpus rebuild required

Ordered by priority (highest-value / most-defensible first).

| # | Defect | Records | Fix class | Deterministic? | Notes |
|---|---|---|---|---|---|
| 1 | **frequency==1 shortcut on markerless dose** | 9 (mgkg 4 + fixed 5) | 2 | Partial | Stop classifying a dose with no textual per-day/per-dose marker purely because frequency==1. Require an explicit marker (`/сут`, `/сутки`, `в сутки`, `каждые N ч`, `N раз(а)`, `однократно`, `разовая доза`) before returning a CORRECT_* type; otherwise `AMBIGUOUS`. Highest-impact, biggest cluster, and re-runnable over existing `source_quote` with no DB change. |
| 2 | **range collapse** | 9 | 3 (real fix) or 2 (workaround) | Yes | `medical_normalizer/drug_parser.py:139` reads only `match.group(1)`; `group(2)` (upper bound) discarded. Real fix = keep both bounds at normalizer + reprocess (class 3). Interim = additive sandbox re-derivation of `dose_min`/`dose_max` from `source_quote` (class 2, `RC030_ADDITIVE_RANGE_SCHEMA_PROPOSAL.md`). All range rows stay BLOCKED regardless until a `dose_max` exists. |
| 3 | **"однократно" misclassified** | 3 | 2 | Yes | Add "однократно" as an explicit single-administration marker in `semantics_parser.py`. Re-runnable over existing quotes. |
| 4 | **"р/сут" abbreviation not tokenized** | 2 | 2 | Yes | Extend the frequency-marker regex to cover "р/сут", "р/д" (spelled "раза в сутки" already works). |
| 5 | **"дважды"/"трижды" not tokenized** | 1 | 2 | Yes | Add single-word "дважды"/"трижды" alongside the "N раз(а)" forms. |
| 6 | **weekly schedule collapse** | 1 | 3 | Partial | `medical_normalizer` FrequencyParser has no schedule-period concept; "3 раза в неделю" collapses to frequency=1. Needs a schedule-period field + reprocess. Dose basis itself (per-day) is already explicit. |
| 7 | **table-header inheritance / flattened rows** | 2 | 4 (targeted) | No | Flattened Цефтриаксон rows need layout-aware re-extraction (targeted pages only, not full 192-PDF rebuild). Method proven in `RC030_TABLE_CLIPPED_TEXT_RECOVERY_REPORT.md`. |
| 8 | markerless surgical prophylaxis (subset of #1) | (within #1) | 2 | Partial | Same root cause as #1; listed separately in the mission but resolved by the same fix. |
| 9 | loading/maintenance & "в N приема" alone | 2 | — | No | Parser already correctly returns AMBIGUOUS; no fix needed, genuinely needs table/maintenance context. |

## Sequencing recommendation

Do #1, #3, #4, #5 together as one sandbox-side re-classification pass (all class 2, all re-runnable over `source_quote`, no DB change, no corpus rebuild) — this is the cheapest, highest-yield batch and touches nothing governed. Treat #2 (range) and #6 (weekly) as separate normalizer-layer changes gated behind their own validation. Treat #7 as targeted re-extraction. **None of these is implemented here**, and none would move any row out of `BLOCKED` on its own — eligibility remains governed solely by `TYPES_MEETING_PRECISION_THRESHOLD` (empty).
