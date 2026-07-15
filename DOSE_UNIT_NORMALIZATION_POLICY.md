# Dose Unit Normalization Policy

- Never infer unit from drug defaults.
- Never insert a unit solely because a common regimen uses it.
- Automatic recovery requires exact unit token in source-backed wording.
- Table-header/surrounding-context inheritance requires explicit cell/header provenance; otherwise physician review.
- Compound units remain exact strings until supported parser contract exists.
- Every recovery is additive, reversible and retains original wording.
- Current P5.6 audit classifies only. It does not mutate Knowledge Objects.

Classification A may be automatically recoverable after dedicated normalization tests. Categories B/C are not assigned without source context evidence. D–J require normalization correction, invalidation or physician review according to recorded category.
