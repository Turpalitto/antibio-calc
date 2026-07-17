# RC-030 Maximum vs Range Disambiguation

104 max-dose candidate rows audited. **No maximum becomes usable** — every candidate is annotated with a fail-closed risk and remains BLOCKED.

- Candidates whose quote ALSO contains a true numeric range (RANGE_UPPER_BOUND_NOT_MAXIMUM risk): 52
- Candidates in an "или" alternative context (MAXIMUM_ALTERNATIVE_CONFLICT): 41
- Remaining (MAXIMUM_ATTRIBUTION_UNCERTAIN): 11

The overlap between max-dose signals and true ranges (52 rows) is the key safety finding: a range upper bound (e.g. "50-80 мг/кг") can be mis-read as a maximum. These are flagged, never attached as a max. Full list: (machine copy generated alongside this report).

| regimen | max signal | has true range | risk |
|---|---|---|---|
| 5590 | максимальная разовая доза | False | MAXIMUM_ALTERNATIVE_CONFLICT |
| 5631 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5624 | не более | True | RANGE_UPPER_BOUND_NOT_MAXIMUM |
| 5625 | не более | True | RANGE_UPPER_BOUND_NOT_MAXIMUM |
| 5626 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5627 | не более | True | RANGE_UPPER_BOUND_NOT_MAXIMUM |
| 5628 | не более | True | RANGE_UPPER_BOUND_NOT_MAXIMUM |
| 5629 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5646 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5746 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5745 | не более | True | MAXIMUM_ALTERNATIVE_CONFLICT |
| 5806 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5809 | не более | False | MAXIMUM_ALTERNATIVE_CONFLICT |
| 5877 | не более | True | MAXIMUM_ALTERNATIVE_CONFLICT |
| 5878 | не более | True | MAXIMUM_ALTERNATIVE_CONFLICT |
| 5879 | не более | True | MAXIMUM_ALTERNATIVE_CONFLICT |
| 5949 | не более | True | MAXIMUM_ALTERNATIVE_CONFLICT |
| 5979 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5980 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5981 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5982 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 5985 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 6169 | не более | False | MAXIMUM_ATTRIBUTION_UNCERTAIN |
| 6232 | не более | True | RANGE_UPPER_BOUND_NOT_MAXIMUM |
| 6233 | не более | True | RANGE_UPPER_BOUND_NOT_MAXIMUM |