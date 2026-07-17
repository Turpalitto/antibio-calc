# RC-030 Repair — Impact Classification Matrix

Classes: (1) improves future extraction/normalization only; (2) improves current QA artifacts immediately; (3) improves historical corpus after reprocessing; (4) requires authoritative SQLite rebuild; (5) requires Clinical Engine adaptation; (6) requires physician review.

| Change | Class | Touches authoritative DB? | Notes |
|---|---|---|---|
| freq==1 shortcut removal (parser) | 2 | No | sandbox re-classification, re-runnable over source_quote |
| token normalization (однократно/р.сут/дважды/трижды) | 2 | No | sandbox only |
| weekly / interval / every-other-day guards | 2 | No | schedule risk flags only; stays BLOCKED |
| range-loss guard (RANGE_VALUE_COLLAPSED_UPSTREAM) | 2 | No | reads source_quote, adds risk + min/max; no write |
| normalizer range preservation (dose_min/dose_max) | 1 | No (future normalization) | additive fields; dose_value byte-identical; to_dict() unchanged |
| experimental range rebuild artifact | 3 | No (writes to generated/) | non-authoritative; 179/365 attributions SUSPECT |
| table-context guard | 2 → 3 | No | full recovery needs targeted re-extraction |
| loading/maintenance guard | 2 | No | risk flag only |
| max-dose protection | 2 | No | never attaches an unverified max |
| authoritative range migration | 4, 5, 6 | YES (proposed only) | NOT executed; gated behind owner approval |