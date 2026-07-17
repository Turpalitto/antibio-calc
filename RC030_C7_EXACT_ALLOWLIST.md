# RC-030 C7-PREP — Exact Allowlist

## C61-TESTS

| Path | Size (bytes) | SHA-256 |
|---|---|---|
| `tests/dose_verification_sandbox/test_c7_precision_simulation.py` | 7330 | `c74557e0d8d52a69c6e62322b9bb01a817c648be09d15b9d3c6bed9e4a86ea42` |

17 synthetic-fixture tests exercising the already-committed C4 precision pipeline (`dose_verification_sandbox.precision_calculator`) — zero owner/AI data used, purely readiness simulation.

## C61-DOCS

| Path | Size (bytes) | SHA-256 |
|---|---|---|
| `RC030_C7_ENTRY_CRITERIA.md` | 3686 | `feb28a50797888a4fdcbbdb06c90c912f3d23a79ebaa1ff9da8062e54a7d7892` |
| `RC030_C7_PRECISION_SIMULATION_REPORT.md` | 3305 | `8bb3cad490ba58ab6f9e1521ff5f69c0d6dc1f75fa8fa92684b113bcf69f66b5` |
| `RC030_C7_OWNER_VALIDATION_PLAN.md` | 4853 | `a34bddd040dc0289595e2ef9786d5b4b4c5bebd8a7348cf20df70ff99a7c4d02` |
| `RC030_C7_GATE_MATRIX.md` | 3647 | `819c3301175175e269f01387d32778b0b2e4994dd6731f4ac0e91aeb8d2b2632` |
| `RC030_C7_EXACT_ALLOWLIST.md` (this file) | — | — |
| `RC030_C7_PRESTAGING_AUDIT.md` (written next) | — | — |

## Excluded

None generated for this track — C7-PREP is pure documentation/simulation with no clinical data dependency, so there is nothing to exclude beyond the standard C1-C6.6 exclusions (unchanged).

## Totals

- 1 test file (17 new tests) + up to 6 doc files = 7 tracked paths
- 0 SQLite, 0 PDF, 0 clinical-evidence dump, 0 owner export, 0 AI event store, 0 threshold write
