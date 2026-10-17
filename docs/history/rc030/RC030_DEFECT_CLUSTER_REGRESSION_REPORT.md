# RC-030 Defect Cluster Regression Report

Full-corpus (2,675) replay per known AI-audit defect cluster. 'affected' = rows matching the cluster's source pattern; 'changed/flagged' = rows whose semantic type changed or gained a risk flag under the repaired parser. Every cluster remains calculation BLOCKED.

| Cluster | Affected | Changed/flagged | Behaviour | Status | Corpus-rebuild dependency |
|---|---|---|---|---|---|
| markerless frequency=1 | 316 | 301 | markerless dose → AMBIGUOUS + EXPLICIT_DOSE_BASIS_MISSING | FIXED (sandbox re-classify) | no |
| однократно | 163 | 122 | → per-dose (FIXED_SINGLE/WEIGHT_PER_DOSE) | FIXED | no |
| р/сут | 26 | 24 | → per-dose | FIXED | no |
| дважды/трижды | 6 | 6 | → per-dose | FIXED | no |
| weekly schedule | 110 | 47 | WEEKLY period + WEEKLY_SCHEDULE_UNSUPPORTED; stays BLOCKED | PARTIAL (schedule risk only) | normalizer schedule field for full fix |
| range collapse | 373 | 332 | RANGE_VALUE_COLLAPSED_UPSTREAM + dose_min/dose_max recovered | FIXED (guard) / normalizer fix lands upper bound | corpus reprocess for authoritative |
| flattened table | 2 | 2 | TABLE_CONTEXT_REQUIRED (pilot); broader corpus needs layout recovery | PARTIAL | targeted re-extraction |
| loading/maintenance | 57 | 16 | LOADING_MAINTENANCE_UNRESOLVED where both phases present | PARTIAL (guard) | no |
| wrong dose anchor | — | — | handled by existing nearest-anchor + alternative-boundary logic; no regression introduced | UNCHANGED | no |
| alternative boundary | — | — | existing overlap/nearest logic retained; range regex excludes 'или' | UNCHANGED | no |
| max-dose attribution | 104 | 104 | 104 candidates flagged; 52 overlap a true range (RANGE_UPPER_BOUND_NOT_MAXIMUM), 41 alternative-conflict | GUARDED (never attached) | no |

## False-positive risk notes

- **markerless_freq1** intentionally over-triggers toward AMBIGUOUS (fail-closed). Some of the 316 may have a marker just outside the 90-char window; that only costs a (safe) AMBIGUOUS, never a wrong confirmation.
- **однократно** 163 affected / 122 changed: the 41 unchanged were already per-dose (no regression).
- **weekly** 110 affected / 47 flagged: many 'недел' mentions are duration ('в течение N недель'), correctly NOT flagged as WEEKLY schedule.
- **range** 373 affected / 332 flagged: gap = rows whose scalar isn't locatable in the window or whose range belongs to another drug (see RC030_RANGE_REBUILD_INTEGRITY_REPORT.md — 179/365 SUSPECT attributions).