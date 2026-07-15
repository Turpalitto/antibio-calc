# P5.6 Test Recovery Report

## Root causes

1. Collection падал: отсутствовал `clinical_engine.tools.verify_regimen_against_guideline`. Реализован read-only verifier; 3 targeted tests PASS.
2. После secret containment три LLM unit tests создавали remote provider до подмены `chat`. Тесты переключены на factory boundary; fail-fast credential contract не ослаблен.
3. API tests нашли cross-thread SQLite connection defect. Store переведён на `check_same_thread=False` + `RLock`; 5 API tests стали PASS.

## Canonical result

`python -m pytest`: **1,373 collected; 1,371 passed, 1 skipped, 1 xfailed, 0 failed**, 24.24 s. Workbench tests включены в canonical `testpaths`; targeted Workbench: **46 passed**.

Expected xfail: pre-existing `parse_llm_json` object behavior, явно документирован. Skip: real optional runtime gate, причина видна pytest.
