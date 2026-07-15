# P5.6 Clinical Data Issue Registry

Dedicated table: `review_workbench_p56.sqlite.clinical_data_issues`.

- исходные issues: 4,506 (4,504 `heuristic_flag`, 2 `pdf_confirmed`);
- dose-unit audit issues: 8,412;
- всего registry rows: 12,918;
- bulk auto-resolution: 0;
- история source payload и provenance сохранена.

Registry query доступен через `GET /issues` и локальный `/ui/issues`. Решение врача хранится отдельно в append-only review events; source clinical facts immutable.
