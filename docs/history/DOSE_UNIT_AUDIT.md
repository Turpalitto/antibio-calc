# P5.6 Dose Unit Audit

Real audit `kb_p44.db`: 8,412 unitless Dose objects.

| Категория | Count |
|---|---:|
| E — frequency/route misclassified as Dose | 2,009 |
| H — invalid/noise | 1,651 |
| J — requires physician review | 4,752 |

- automatically recoverable: 0;
- review required: 4,752;
- invalid/noise aggregate: 3,660;
- blocked/unclassified: 0;
- inserted units: 0.

Политика: `DOSE_UNIT_NORMALIZATION_POLICY.md`. Запрещена подстановка unit из drug defaults. Любое восстановление требует точного source-backed значения и provenance.
