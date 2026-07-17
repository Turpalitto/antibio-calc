# RC-030 Range Loss — Exact Stage RCA

Traced 20 rows whose `source_quote` contains a genuine numeric range, through both `normalized_regimens` and `assembled_regimens`, plus the actual normalizer source code.

## Trace results (20/20 rows)

`normalized_regimens.dose` and `assembled_regimens.dose` are **identical, scalar, in all 20 sampled rows** — `already_collapsed_by_normalization = True` for every row. `assembled_regimens.dose` is a verbatim passthrough of `normalized_regimens.dose`; **no additional information is lost at the assembly stage** because there was nothing left to lose by the time assembly ran.

This rules out **Stage D (canonical assembly)** conclusively: assembly cannot be responsible for dropping data that was already gone before it ran.

## Exact responsible code

`medical_normalizer/drug_parser.py:103-148`, class `DoseNormalizer`, method `parse()`:

```python
_dose_re: ClassVar[re.Pattern] = re.compile(
    r"(\d[\d\s,.]*)(?:\s*[-–—]\s*(\d[\d\s,.]*))?\s*"
)
...
match = cls._dose_re.match(dose_raw)
if match:
    try:
        val = float(match.group(1).replace(",", "."))
        regimen.dose_value = val
        ...
```

**The regex itself has a second capture group for the upper bound of a range** (`(?:\s*[-–—]\s*(\d[\d\s,.]*))?`) — the range *is* being parsed, syntactically. But the code only ever reads `match.group(1)`. **`match.group(2)` (the upper bound) is computed by the regex match and then never referenced anywhere in the function.** This is not a missing feature — it's a capture group that exists in the pattern and is silently discarded in the code that consumes the match.

## Direct reproduction

Ran `DoseNormalizer.parse()` directly, isolated from the database, with synthetic raw input:

| Input `raw["dose"]` | `regimen.dose_value` after parse |
|---|---|
| `"20-50"` | `20.0` |
| `"20–50"` (en-dash) | `20.0` |
| `"500 - 1000"` | `500.0` |
| `"50-80"` | `50.0` |

These match the real database values traced for regimens 5660 (`20-50` → `20.0`), 5671 (`500-1000` → `500.0`), 5683 (`50-80` → `50.0`) exactly — confirming this function, this line, is the precise and complete explanation for the observed data.

## Corroborating evidence at the dataclass level

`medical_normalizer.models.NormalizedRegimen` has `duration_days_min: float | None` **and** `duration_days_max: float | None` as a proper pair, but only a single `dose_value: float | None`. The asymmetry exists at the very first structured representation in the pipeline, not just in the SQLite schema derived from it — `DurationParser` (dispatched the same way as `DoseNormalizer` in `normalizer.py:296`) was built to preserve both bounds; `DoseNormalizer` was not.

## Classification

**Stage C: normalization**, and more precisely than the mission's classification options require: **`DoseNormalizer.parse()`, medical_normalizer/drug_parser.py line 139** (`val = float(match.group(1)...)`, `match.group(2)` never read). Not Stage A (extraction — the raw string handed to `DoseNormalizer` already contains the full "N-M" range text, confirmed by the regex successfully matching a group 2 on it) and not Stage E (RC-030 parser — RC-030 never sees the range at all; by the time its input reaches it, `dose` is already a lone scalar, which is exactly what `dose_verification_sandbox/parser.py`'s `numeric_min = numeric_max = dose` reflects, correctly, given what it's handed).

## What RC-030 can and cannot do about this

RC-030's semantics layer is additive and read-only against `assembled_regimens`; it cannot recover `match.group(2)` because that value was never written to any database RC-030 reads from — it only ever existed transiently inside one regex match object during a `medical_normalizer` run that already completed. The only ways to recover it are: (a) re-run `medical_normalizer` with a fixed `DoseNormalizer` that keeps both bounds (a normalizer-layer fix, out of RC-030's scope and not implemented here), or (b) have RC-030 independently re-derive a range from `source_quote` text via its own regex (a sandbox-layer enhancement, proposed but not implemented — see `RC030_DOSE_SEMANTICS_ARCHITECTURE_DECISION.md` and `RC030_RANGE_EXPRESSION_RCA.md`'s recommendation).
