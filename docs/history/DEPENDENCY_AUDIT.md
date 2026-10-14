# P5.6 Dependency Audit

Дата: 2026-07-15. Python: CPython 3.12.

## Результат

- Канонический манифест: `pyproject.toml`.
- Lock: `uv.lock`, 194 resolved packages; `uv lock --check` PASS.
- Группы: core, clinical, extraction, layout, semantic, tests, development.
- Lightweight clinical/test env не тянет ML stack.
- Clean env: `.venv`, `uv sync --extra clinical --extra tests --frozen` PASS.
- `uv pip check`: 36 installed packages compatible.
- Canonical import/collection: PASS.

## Разрешённые конфликты

Legacy Table Transformer метаданные требуют старые Pillow/tqdm, MinerU/Docling — новые. Lock использует документированные metadata overrides: Pillow `>=11,<13`, tqdm `>=4.67.1`. Это compatibility override, не доказательство runtime-совместимости всех ML extras; extraction/layout smoke остаётся отдельным gate при установке heavy extras.

## Статус

Dependency strategy: PASS. Heavy ML all-extras execution: WARNING, не требовался для изолированного P5.6 Workbench.
