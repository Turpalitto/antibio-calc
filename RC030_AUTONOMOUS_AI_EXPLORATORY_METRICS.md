# RC-030 Autonomous AI Audit — Exploratory Metrics

**EXPLORATORY_AI_REFERENCE_ONLY.** These are NOT validated precision. They must not be used to activate any semantic type or to modify TYPES_MEETING_PRECISION_THRESHOLD (which remains empty). They compare parser output against a single AI analyst reading the same source text — that measures apparent agreement, not correctness.

| Metric | Value |
|---|---|
| Records where both parser and AI confirm a day/dose family | 46 |
| Of those, same family (apparent agreement) | 40 |
| Apparent parser direction-agreement | 87.0% |
| Parser over-confirmations (AI says ambiguous/table/freq-error) | 14 |
| Overall AI-vs-parser disagreement rate (of 60) | 33.3% |

## Cluster prevalence

| Cluster | Records |
|---|---|
| freq1_shortcut_markerless_mgkg | 4 |
| freq1_shortcut_markerless_fixed | 5 |
| odnokratno_misclassified | 3 |
| r_sut_tokenization | 2 |
| dvazhdy_tokenization | 1 |
| weekly_schedule_collapse | 1 |
| range_not_captured | 9 |
| table_flattened_headers_lost | 2 |
| loading_maintenance_ambiguity | 1 |
| v_n_priema_alone | 1 |

**Interpretation guardrail:** the 87% apparent direction-agreement is on the subset where the parser confirmed *something* AND the AI also confirmed a family. It excludes the 14 parser over-confirmations (where the AI would not confirm at all), which are the safety-relevant cases. Read together: of all 60, the AI declines to endorse the parser on 20 (33%), and 9 of those are the single frequency==1-shortcut root cause.