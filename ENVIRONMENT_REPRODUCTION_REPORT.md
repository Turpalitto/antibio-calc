# P5.6 Environment Reproduction Report

Реально выполнено 2026-07-15:

```powershell
py -3.12 -m uv sync --extra clinical --extra tests --frozen
.\.venv\Scripts\python.exe -m pytest
```

Результаты: installation PASS; dependency check PASS; 1373 tests collected; 1371 passed, 1 skipped, 1 expected xfail, 0 failed.

External data contracts:

- corpus: `C:\clinrec_downloader`;
- normalized DB: `C:\clinrec_downloader\normalized_regimens.sqlite`;
- production KB: `C:\ANTIBIO\kb_p44.db`;
- generated review store: `review_workbench_p56.sqlite` (не Git artifact).

Fresh-clone verdict: BLOCKING. Git отслеживает только 19 файлов; canonical source/docs остаются untracked. Среда локально воспроизводима, но repository пока не воспроизводим из Git до owner-reviewed commit.
