## 2026-09-11: Длительность курса унифицирована

- **Исправлено:** панели результата и история печатали сырое `duration_days`
  (459 из 638 режимов = 71,9% расходились с блоком комбинации). Все три точки переведены
  на `formatDuration`. Терялась не только единица, но и семантика: «однократно» и
  «пожизненно» становились числами.
- **Исправлено в истории:** `computeDose` вызывался без единицы препарата и без проверки
  `noDose` — сохранил бы «0 мг» вместо отсутствующей дозы.
- **Проверка:** 638 режимов, 0 голых чисел без единицы.
- **Валидатор:** EXIT=0, 0 errors / 264 warnings. `antibiotic_calc.html` = 828 208 байт.
- **Тесты:** `pytest -q` → **2273 passed, 32 skipped, 1 xfailed**.
- **Открыто:** 27 режимов без числовой дозы; 59 пар «препарат × возраст» без схемы;
  82 блочные связи ждут врача; 119/120 нозологий без расчёта.
## 2026-09-11: Концентрация флакона консолидирована

- **Исправлено:** `||`-фолбэк концентрации был продублирован в трёх местах (подсказка
  «на дозу», блок разведения, латинская форма). Введены `vialConcentrationPerMl`,
  `vialStrengthLabel`, `vialConcentrationLabel`, `injectableMlForDose`; убрана мёртвая
  переменная `isUnits` в `computeInjectableMl`.
- **Своя регрессия поймана до фиксации:** `formatUnits` на `vial_mg` дал бы «1 тыс мг»
  вместо «1000 мг» (в БД есть 1000/1500/2000/4000). Сокращение оставлено только для ЕД.
- **Доказано сохраняющим поведение:** 162 пары «флакон × режим», 0 расхождений со старым
  рендером.
- **Валидатор:** EXIT=0, 0 errors / 264 warnings. `antibiotic_calc.html` = 827 821 байт.
- **Тесты:** `pytest -q` → **2269 passed, 32 skipped, 1 xfailed**.
- **Открыто:** 27 режимов без числовой дозы; 59 пар «препарат × возраст» без схемы;
  82 блочные связи ждут врача; 119/120 нозологий без расчёта.
## 2026-09-11: Подсказка о таблетках исправлена

- **Исправлен собственный дефект из `a1290cb`:** `formatTablets` брал последнее число
  перед «мг» и для «875+125 мг» делил на 125 (клавуланат) вместо 875 — подсказка
  печатала «7 таб 125 мг» на дозу 875 мг, при том что рецепт на том же экране считал
  одну таблетку. Затронуты все 4 композитные формы (амоксиклав, ко-тримоксазол).
- **Новое:** единственный источник `tabletStrengthMg(form)`; на него переведены
  `formatTablets` и оба места печати рецепта.
- **Проверка:** 53 таблеточные формы, 0 расхождений; `formatTablets(875,"875+125 мг")`
  → «(1 таб 875 мг)».
- **Валидатор:** EXIT=0, 0 errors / 264 warnings. `antibiotic_calc.html` = 826 767 байт.
- **Тесты:** `pytest -q` → **2265 passed, 32 skipped, 1 xfailed**.
- **Открыто:** 27 режимов без числовой дозы; 59 пар «препарат × возраст» без схемы;
  82 блочные связи ждут врача; 119/120 нозологий без расчёта.
## 2026-09-11: Найден дефект базиса дозы у композитных таблеток

- **Найдено:** `uti_prophylaxis` / ко-тримоксазол / 480 мг против формы «400+80 мг» →
  калькулятор печатает «1.2 таб», хотя 480 мг — ровно одна таблетка. Причина: доза в
  данных хранится как сумма компонентов, а делитель — первый компонент
  (``parseFloat`` останавливается на «+»).
- **Новое:** точная проверка базиса в `db/validate_db.js` — доза кратна сумме (A+B), но не
  кратна первому компоненту A. WARN на закрытой нозологии, ERROR на открытой.
- **Отброшено:** правило «не кратно 1/4 таблетки» (749 из 2324 = 32% шума).
- **Валидатор:** EXIT=0, 0 errors / **264** warnings (было 263; +1 — новый случай).
- **Тесты:** `pytest -q` → **2262 passed, 32 skipped, 1 xfailed**.
- **Открыто:** 27 режимов без числовой дозы; 59 пар «препарат × возраст» без схемы;
  82 блочные связи ждут врача; 119/120 нозологий без расчёта.
## 2026-09-11: Единицы разведения под контролем валидатора

- **Новое:** раздел 4 в `db/validate_db.js` — обход `drugs_reference`: оба поля
  концентрации одновременно, расхождение концентрации с `dose_unit` препарата,
  неположительная концентрация. Все ветки доказаны на синтетическом дрейфе.
- **Валидатор принимает путь аргументом** (`node db/validate_db.js <db.json>`), иначе
  проверки нельзя было проверить на испорченных данных.
- **Замер данных:** 81 опция с концентрацией, 0 флаконов с обоими полями, 0 расхождений
  единиц — дефекта нет, инвариант закреплён на будущее.
- **Валидатор:** EXIT=0, 0 errors / 263 warnings (без изменений).
- **Тесты:** `pytest -q` → **2259 passed, 32 skipped, 1 xfailed**.
- **Открыто:** 27 режимов без числовой дозы; 59 пар «препарат × возраст» без схемы;
  82 блочные связи ждут врача; 119/120 нозологий без расчёта.
## 2026-09-11: Единицы действия и отсутствие дозы больше не искажаются

- **Исправлено:** `build_label()` учитывает `dose_unit` — метки бензилпенициллина больше
  не говорят «мг» (было 10 неверных, стало 0; корректных 16). В HTML четыре места с жёстким
  «мг» (signa рецепта, текст для копирования, история) переведены на `fmtDose()`.
- **Исправлено:** `computeDose()` возвращает явный `noDose`; 27 режимов без числовой дозы
  (доза только в тексте КР) больше не рендерятся как «0 мг».
- **Проверка:** сплошной проход shipped-JS — 1914 вычислений, 0 препаратов в ЕД в «мг»,
  0 молчаливых нулей.
- **Сборка:** `db/antibio_db.json` SHA-256 `51d16641760b7046…` (детерминированно);
  `antibiotic_calc.html` = 658 193 байт. Кроссволк `sha256:4318bca59cd5feb9…`, in_sync.
  Очередь проверки детерминирована (`88360a1483b69033…`).
- **Валидатор:** EXIT=0, 0 errors / 263 warnings.
- **Тесты:** `pytest -q` → **2253 passed, 32 skipped, 1 xfailed**.
  Окружение пересоздано после сброса песочницы: Python 3.11.2 + pytest 9.1.1,
  fastapi 0.141.1, pydantic 2.13.5, PyMuPDF 1.24.10, Node v22.22.3.
- **Открыто:** 59 пар «препарат × возраст» без схемы; 27 режимов без числовой дозы
  (нужны схемы из КР); 82 блочные связи ждут врача; 119/120 нозологий без расчёта.
## 2026-09-11: Усечение дозы по `max_daily_mg` исправлено

- **Исправлено:** `computeDose()` пересчитывает разовую дозу вместе с суточной при
  срабатывании потолка. Раньше рецепт мог печатать «1500 мг 4 р/д» при максимуме
  4000 мг/сут. В текущей БД таких режимов 0 из 638 — баг был латентным.
- **Проверка:** сплошной проход shipped-JS 638 режимов × 6 весов = 3828 вычислений,
  **0 нарушений** потолка.
- **Сборка:** `antibiotic_calc.html` = 657 410 байт; `db/antibio_db.json` SHA-256
  `7500889606abe711…` (не менялась — правка только в шаблоне).
- **Валидатор:** EXIT=0, 0 errors / 263 warnings.
- **Тесты:** `pytest -q` → **2238 passed, 32 skipped, 1 xfailed**.
- **Открыто:** 59 пар «препарат × возраст» без схемы дозирования; 60 режимов с
  `age_group` вне сценария; 82 блочные связи ждут врача; 119/120 нозологий без расчёта.
## 2026-09-11: Убрана тихая подстановка дозы чужой возрастной группы

- **Исправлено:** `getActiveRegimen()` больше не откатывается на режим другой возрастной
  группы — возвращает `null`, а UI показывает панель `#res-no-regimen` с причиной.
  Три вызова (`fillPrescriptionForm`, `copyPrescription`, `saveToHistory`) защищены от `null`.
  Сплошная проверка по всей БД: **0** режимов чужой возрастной группы (было 59 достижимых
  случаев, все в заблокированных нозологиях).
- **Валидатор:** `node db/validate_db.js` → EXIT=0, **0 errors / 263 warnings** (было 505,
  из них 360 — устаревший шум про free-text длительности). Состав: 60 `age_group` вне
  сценария, 59 без режима на возраст, 47 без `duration_days`, 29 без `route`,
  27 без `regimen_label`, 27 без дозы, 12 неразбираемых длительностей, 2 `topical`.
- **Сборка:** `antibiotic_calc.html` = 657 137 байт; `db/antibio_db.json` SHA-256
  `7500889606abe711…` (не менялась — правки только в шаблоне и валидаторе).
- **Тесты:** `pytest -q` → **2232 passed, 32 skipped, 1 xfailed**.
- **Открыто:** 59 пар «препарат × возраст» без схемы дозирования (данные КР, не код);
  60 режимов с `age_group` вне возрастного диапазона сценария; 82 блочные связи ждут
  решения врача; 119/120 нозологий без расчёта.
## 2026-09-11: Очередь врачебной проверки блочных связей

- **Новое:** `clinical_engine/crosswalk/review_queue.py` +
  `clinical_engine/resources/calculator_crosswalk_review_queue.json` — ранжированная очередь
  на все **82** связи `ICD10_BLOCK` (38 нозологий / 68 КР). Категории:
  `EXTERNAL_CAUSE_ONLY 1`, `AGE_DIRECTION_CONFLICT 4`, `BLOCK_ONLY_DISEASE 19`,
  `COARSE_SHARED_BLOCK 15`, `ROUTINE 43`; `HIGH 5 / MEDIUM 34 / LOW 43`.
  `purpose: PHYSICIAN_REVIEW_ONLY` — инструмент клиническую релевантность не решает.
- **Пересборка:** `python -m clinical_engine.crosswalk.review_queue --write`.
  Импорт в review workbench: `to_issue_records()` → `ReviewStore.import_issue`.
- **Тесты:** `pytest -q` → **2226 passed, 32 skipped, 1 xfailed**.
- **Открыто:** 82 блочные связи ждут решения врача; 95 КР корпуса без нозологии;
  22 нозологии без связи с корпусом; 119/120 нозологий без расчёта.
## 2026-09-11: Перепись корпуса КР исправлена, добавлено зеркальное покрытие

- **Кроссволк:** `clinical_engine/resources/calculator_crosswalk.json`,
  `content_sha256: sha256:4318bca59cd5feb9…`, 263 связи, 98/120 нозологий.
  Покрытие: **294 КР корпуса** (193 уникальных названия, 81 название делят несколько КР) →
  **199 связано + 95 не связано = 294** ровно. Новое поле `unlinked_guidelines`.
- **Сборка:** `db/antibio_db.json` SHA-256 `7500889606abe711…` (детерминировано);
  `antibiotic_calc.html` = 655 020 байт. 120 recs / 10 cats / 48 drugs / 98 с `guideline_links`.
- **Семантика режимов:** `duration_parsed` на 638/638, `regimen_label` на 611/638.
- **Валидация БД:** `node db/validate_db.js` → EXIT=0, 0 errors / 505 warnings.
- **Тесты:** `pytest -q` → **2194 passed, 32 skipped, 1 xfailed**.
- **Открыто:** 95 КР корпуса без нозологии в калькуляторе (кандидаты на добавление,
  большинство не про антибиотики); 22 нозологии без связи с корпусом; 82 связи
  `ICD10_BLOCK` ждут врачебной проверки; 119/120 нозологий без расчёта.
## 2026-09-11: Семантика режимов выводится на сборке (`duration_parsed` / `regimen_label`)

- **Новое:** `db/regimen_semantics.py` — build-time вывод семантики курса. `duration_parsed` проставлен
  на все **638** режимов, `regimen_label` — на **611** (было 153). Прогон: `python db/build_db.py`
  (отключается флагом `--skip-semantics`).
- **Классы длительности (13):** `RANGE 232, FIXED 150, SINGLE_DOSE 76, AT_MOST 61, MISSING 47,
  INFUSION_CONSTRAINT 29, CONDITION_DEPENDENT 12, NOT_FIXED 12, NOT_STATED 9, LIFELONG 6,
  INTERMITTENT 2, AT_LEAST 1, DOSE_COUNT 1`. Скорость введения и число приёмов больше не путаются
  с длительностью курса.
- **Сборка:** `db/antibio_db.json` SHA-256 `a8600ad540081ec2…` (детерминировано, два прогона подряд);
  `antibiotic_calc.html` = 655 020 байт. 120 recs / 10 cats / 48 drugs / 98 с `guideline_links` — без изменений.
- **Валидация БД:** `node db/validate_db.js` → EXIT=0, **0 errors / 505 warnings**
  (360 free-text длительностей, 60 age_group вне сценария, 29 без route, 27 без `regimen_label`
  под блокировкой, 27 без дозы под блокировкой, 2 × route `topical`). Дублей `regimen_label` — 0.
- **Тесты:** `pytest -q` → **2188 passed, 32 skipped, 1 xfailed**. Окружение: Python 3.11.2 + pytest 9.1.1,
  Node v22.22.3.
- **Открыто:** 27 режимов без дозы и без метки (все в заблокированных нозологиях); 4 уникальные
  неразбираемые строки длительности; 22 нозологии без связи с корпусом; 82 связи `ICD10_BLOCK`
  ждут врачебной проверки.
## 2026-09-10: Калькулятор связан с корпусом КР (навигационный слой)

- **Кроссволк:** `clinical_engine/resources/calculator_crosswalk.json` — 263 связи, 98/120 нозологий,
  199 guideline_id корпуса, `content_sha256: sha256:c6fe9aa1a457…`, `purpose: NAVIGATION_ONLY`.
  Пересборка: `python -m clinical_engine.crosswalk --write`; проверка: без `--write`.
- **Сборка:** `db/antibio_db.json` = 120 recs / 10 cats / 48 drugs, из них 98 с `guideline_links`,
  SHA-256 `cec19cb8bc830d0c…`. `antibiotic_calc.html` = 723 381 байт, совпадает с template+db байт-в-байт.
- **Статус расчёта не изменился:** 1 открыт (`aom_child`, КР 314_3, `CALCULATOR_BOUND_VERIFIED`),
  119 заблокированы. Worklist: `python db/source_gate_report.py`.
- **Валидация БД:** `node db/validate_db.js` → 0 errors / 478 warnings
  (360 free-text длительностей, 60 age_group вне сценария, 29 без route, 27 без дозы под блокировкой,
  2 × route `topical`).
- **Тесты:** `pytest -q` → **2126 passed, 32 skipped, 1 xfailed** за ~18 с.
  Окружение проверки: Python 3.11.2 + pytest 9.1.1, fastapi 0.141.1, pydantic 2.13.5, PyMuPDF 1.24.10,
  Node v22.22.3.
- **Открыто:** 22 нозологии без связи с корпусом; 82 связи `ICD10_BLOCK` ждут врачебной проверки
  на клиническую релевантность; 109 нозологий ждут `SOURCE_SPEC`.
## 2026-09-02: Dose source-verification across 120 nosologies

- Run dose_verification.py over db/antibio_db.json (120 recs) vs DOSA KB -> 243 matched / 113 mismatched /
  123 uncomparable / 41 no-kb. 23 fully verified, 18 partly verified, 38 have discrepancies to adjudicate
  (mostly daily-vs-single-dose representation, not errors). Report tmp/dose_verification_report_2026-09-02.md.
  Evidence-only; only aom_child(314_3) unblocked (unchanged). No commit.
## 2026-09-02: aom_child — added severe/IV amoxiclav tier

- aom_child now has 2 scenarios: aom_child_standard (amoxicillin 60/50/90, amoxiclav 45, cefixime 8,
  cefuroxime 30, clarithromycin 15 — all mg/kg/day, duration 7-10) + aom_child_complicated (amoxiclav IV
  90 mg/kg/day x3, children 4-40kg / 60mg/kg <4kg, adults 3.6g/day). Source-anchored to КР 314_3 table 4.
- Rebuilt db (120 recs/10 cats/48 drugs) + antibiotic_calc.html (520349). Suite 1624 passed. Only
  aom_child(314_3) unblocked. No commit.
## 2026-09-02: Coverage raised — 120 nosologies / 48 drugs (all-antibiotic-KB)

- Registered-drug namespace expanded 41 -> 48 (tetracycline, ofloxacin, tobramycin, netilmicin, tinidazole,
  rifaximin, furazidin). DOSA extension now **48*** records (all 294 KB guidelines processed, degenerate
  conjunctivitis 629_2 excluded). db = 120 recs / 10 cats / 48 drugs; 119 blocked / 1 unblocked (aom_child 314_3).
  antibiotic_calc.html rebuilt (519478). Suite 1624 passed. No commit.
## 2026-09-02: Dose source-verification harness added (evidence-only)

- dose_verification.py compares app doses vs PDF-extracted KB doses; 242/454 matched, 113 mismatch
  (mostly variants not errors), 99 uncomparable, 41 no-KB-guideline. Never sets verification status.
- Full suite 1624 passed. Data unchanged (119 recs/10 cats/41 drugs).
## 2026-09-02: Calculator verified against КР (only aom_child computes)

- Real-run verification: only aom_child (cr 314_3) computes; 118 blocked (fail-closed source gate).
  aom_child 7/7 PASS vs КР 314_3; suspension mL correct across all forms/weights. Report
  tmp/calculator_real_run_2026-09-02.md. DB unchanged (119 recs/10 cats/41 drugs). Suite 1619 passed.
## 2026-09-02: Calculation bug fixed (cefuroxime Infinity) — render-path only

- `computeDose` math verified CORRECT; bug was the child liquid-default form selection in renderFormChips
  picking a parenteral vial (no concentration_mg_per_ml) for cefuroxime → Infinity.
- Fix requires concentration_mg_per_ml != null for child liquid default. antibiotic_calc.html rebuilt (509655).
- DB unchanged (119 recs / 10 cats / 41 drugs; only aom_child 314_3 unblocked). Suite 1619 passed.
# PROJECT STATE — ANTIBIO (antibio-calc + pipeline)

## 2026-09-02: Route-dedup fix + extension regenerated to 47 + triage refined

- **DB:** db/antibio_db.json = **119 recs / 10 categories / 41 drugs** (72 original + 47 DOSA
  extension). Verified 118 blocked / 1 unblocked (aom_child 314_3).
- **Fixes:** duplicate-route bug in dosa_to_db_mapper.py (64→0 duplicates); regenerated extension
  against the original 72 base → 47 records; triage surgical `"перелом"/"глазниц"` keyword +
  amanitin override id corrected → 0 unclassified (surgical 10, infection 17, onco 6, id-pjp 8,
  metabolic 3, cardiac 3). HTML rebuilt 509368 bytes. Suite **1619 passed**.
- All 47 extension records display-only (calculation_blocked, SOURCE_SPEC_MISSING). No commit.

## 2026-09-02: Triage of the 46 DOSA extension nosologies (engineering classification)

Split the 46 DOSA-added records into 7 clinical categories for physician review. Source-prover
only; all records stay calculation-blocked. New module
`src/pipeline/extraction/dosa_extension_triage.py`, artifact
`tmp/dosa_extension_triage_2026-09-02.json` (46 recs: congenital_cardiac_prophylaxis 3,
surgical_prophylaxis 9, oncology 6, immunodeficiency_pjp 8, metabolic_genetic 3, infection 16,
unclassified 1). 9 new tests. Full suite 1617 passed. This is engineering triage, NOT a medical
verdict; the physician gate P5.6/P6 remains owner-only. No commit.

## 2026-09-02: Pulled ALL remaining antibiotic guidelines (46 new nosologies)

Expanded the calculator to consume every unused DOSA guideline that carries antibiotics,
staying source-layer-only (all new records are display-only, calculation blocked).

- **DB:** db/antibio_db.json now `{recommendations 118, categories 10, drugs_reference 41}`
  (was 75/10/41). 118 = 75 prior + 43 newly built (46 new candidates, some overwrote prior 3).
- **Source of the 46:** scoped target = ALL 267 unused DOSA guidelines (not just the 128
  therapeutic-new subset). `dosa_to_db_mapper.build_mapped_db` over all 267 → 181 candidate
  records / 561 mapped_symbols / 2351 total. After `deduplicate_mapped` (vs existing DB) →
  124 new / 57 dropped. After `deduplicate_among` (collapse cross-version dupes) →
  **46 kept**.
- **Written:** db/diseases/extended_dosa.json (category «КР с антибиотиками (расширение из DOSA,
  source-слой)», recommendations:[46]) overwriting the prior 3-record file.
- **Verification after build (calculator_source_gate, fail-closed):** 117 blocked /
  **1 unblocked (aom_child 314_3)** — unchanged governance. source_verification_status dist:
  SOURCE_SPEC_MISSING 107, SOURCE_SPEC_PENDING_CALCULATOR_BINDING 6,
  CURRENT_WEB_CONFIRMED_PDF_PENDING 2, EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW 2,
  CALCULATOR_BOUND_VERIFIED 1.
- **Rebuild commands run:** `.venv/bin/python db/build_db.py --db db/antibio_db.json`
  → `{"recommendations": 118, "categories": 10, "drugs_reference": 41}`; then
  `.venv/bin/python db/build_html.py` → `antibiotic_calc.html (509160 bytes)`.
- **Full suite:** `.venv/bin/python -m pytest -q` → 1608 passed, 29 skipped, 1 xfailed, 6 warnings.
- **Content note:** many of the 46 are peri-op surgical prophylaxis, oncological
  (febrile neutropenia, leukaemia), congenital-cardiac endocarditis-prophylaxis, and rare
  metabolic/metaphylaxis (PJP prophylaxis) — all legitimately carry antibiotics but are NOT
  classic acute-infection dosing. They appear in the app but calculate-blocked until a
  physician/spec binds them. minzdrav network still UNREACHABLE; physician gate P5.6/P6 owner-only.
- No commit (user never asked).

## 2026-09-02: DOSA extension (3 new nosologies) + Python build pipeline + disclaimer

Extended the calculator DB from the DOSA source-layer (source-prover only,
calculation stays blocked). Full build pipeline is now cross-platform Python.

- `src/pipeline/extraction/dosa_to_db_mapper.py` + `dosa_db_dedup.py` added;
  after the frequency gate only 3 genuinely-new nosologies survive
  (perioralnyi_dermatit 781_1, travma_nosa 815_1, botulizm 911_1).
- `db/diseases/extended_dosa.json` added; **db/antibio_db.json** regenerated
  -> 75 recommendations, 10 categories, 41 drugs_reference (validate green).
- `db/build_db.py` and `db/build_html.py` (Python ports of the deleted
  .ps1 scripts) build both the DB and the single-page HTML calculator.
- `antibiotic_calc.html` rebuilt (334,659 bytes) with a "not a final medical
  conclusion" disclaimer banner.
- Test command (macOS): `.venv/bin/python -m pytest -q` -> 1608 passed,
  29 skipped, 1 xfailed, 0 failed.

New DOSA nosologies are display-only (calculation_blocked=True,
SOURCE_SPEC_MISSING) until a physician binds a verified spec. Physician gate
P5.6/P6 = owner only; no commit.


`src/pipeline/extraction/extension_sources.py` classifies the unused DOSA
guidelines (those with antibiotics, not yet in the calculator) and identifies
the high-value expansion pool: **128 pure-therapeutic NEW nosologies with 840
proof-anchored regimens**. Split: therapeutic 137 / primarily_prophylaxis 80 /
mixed 50 / duplicate_same_disease 16. All 251 mkb-disjoint guidelines are
`new_nosology`; 128 of these are pure `therapeutic` (the rest are prophylaxis or
mixed). `tmp/extension_sources_2026-09-02.json` holds the full
inventory/candidates/summary. Source-prover only — never enables calculation;
clinical gate P5.6/P6 stays owner/physician.

TEST STATUS: `.venv/bin/python -m pytest -q` → **1593 passed, 29 skipped,
1 xfailed, 0 failed** (1586 + 7 new tests in test_extension_sources.py).

## 2026-09-02: DOSA klinrec source-layer contracts for calculator diseases

Merged DOSA `clinrec-downloader` extraction as a source-prover (scope: source
layer only, calculation stays blocked). New module
`src/pipeline/extraction/dosa_source_contract.py` maps 72 calculator diseases to
DOSA guideline evidence (exact cr_id → MKB → name keyword), emitting provenance
(pdf_sha256, page_number, source_quote, dose) without enabling calculation.
Artifact `tmp/dosa_source_contracts_2026-09-02.json`: 40 matched
(31 exact_cr_id / 6 mkb / 3 name), 32 no_match (mostly declared_cr_id `«—»`).
Match breakdown recorded. Tests `src/tests/test_dosa_source_contract.py` (6).
Suite `1586 passed, 29 skipped, 1 xfailed, 0 failed`. minzdrav network still
unreachable (live PDF/registry work blocked); no commit made.

Added `src/pipeline/extraction/source_fetch_verify.py`: bridge to download an
official minzdrav guideline PDF by `CodeVersion` and pin-verify it against a
source spec's `expected_pdf_sha256` (fail-closed, never approves regimens).
Offline mode reuses the local PDF pin check. Injectable `downloader`/opener for
offline unit tests (network to minzdrav is still unreachable from this
machine). CLI:
`.venv/bin/python -m src.pipeline.extraction.source_fetch_verify
--spec <spec.json> --output <report.json> [--local-pdf <path>] [--outdir <dir>]`.

Tests: `src/tests/test_source_fetch_verify.py` (8). Suite: `.venv/bin/python
-m pytest -q` → 1580 passed, 29 skipped, 1 xfailed, 0 failed.

## 2026-09-02: CAP scenario-to-dose-row bindings built and verified; calculation stays blocked

On a fresh macOS clone (`/Users/turpal/Documents/antibiocalc/antibio-calc`,
Python 3.12.14 venv): every cap_adult regimen (11, CR `654_2`) and cap_child
regimen (6, CR `714_2`) now has a fail-closed binding to one verified
dose-table row. Artifacts:
`clinical_sources/scenario_bindings/654_2.json`,
`clinical_sources/scenario_bindings/714_2.json`; tooling
`src/pipeline/extraction/scenario_bindings.py`; tests
`src/tests/test_scenario_bindings.py` (17 tests). Verification recomputes
sha256 pins (disease record + spec row_groups), enforces blocked status, ATC
identity and full coverage, and reports route/duration/age_weight/severity
linkage. `unblock_eligible=0` for all 17 rows: severity linkage requires a
stratified dose table, which the current generic CAP reference tables are
not. Calculation remains blocked; no owner attestation.

Environment notes: minzdrav endpoints are unreachable from this machine
(network-level block), postponing source work for `898_1`, `912_1`, `629_2`
and the CR `313_3` full PDF. Canonical test command on macOS:
`.venv/bin/python -m pytest -q` → 1572 passed, 29 skipped, 1 xfailed,
0 failed (Windows baseline 1584 passed included machine-local corpus tests).

## 2026-08-02: official registry current; CAP contracts pinned

Official registry snapshot contains 746 current cards. The calculator now has
33 unique officially applicable revisions covering 37/72 disease records.
Thirteen invalid/stale mappings are quarantined (8 semantic numeric-code
collisions, 5 codes absent from the current registry); 35 disease records have
no currently valid declared CR and remain blocked.

Source coverage: 72 diseases, 7 unique hash-pinned specs covering 9 disease
records, 71 source-blocked, zero unblocked without a spec. Only pediatric AOM
`314_3` is `CALCULATOR_BOUND_VERIFIED`. Adult CAP `654_2` has 32 extracted
reference-dose candidates and pediatric CAP `714_2` has 19; all CAP candidates
remain blocked pending scenario and age/weight binding. No owner attestation,
production activation, or clinical auto-approval occurred. Canonical tests:
1584 passed, 1 xfailed, 0 failed.

## 2026-08-02: UTI source batch verified; CR 9_3 candidates pinned

Current official IDs: cystitis `14_3`, adult acute pyelonephritis `9_3`, UTI
in pregnancy `719_2`, urolithiasis `7_2`. CR 9_3 has a hash-pinned PDF and 21
source candidates; seven are structurally parseable, but calculator binding is
not complete and the disease remains blocked. Cystitis cefixime duration is
corrected to 5 days while the entire disease remains source-gated.

Coverage: 72 diseases, 3 unique pinned guideline specs covering 4 disease
records, 71 calculation-blocked, zero unblocked missing-spec records. Only AOM
CR 314 is marked `CALCULATOR_BOUND_VERIFIED`. No owner attestation or bundle
activation occurred. DB/HTML rebuilt; canonical tests: 1569 passed, 1 xfailed,
0 failed. Production P5.6/P6 remains unchanged.

## 2026-08-02: all unverified calculator records now fail closed

The complete 72-disease source inventory is tracked at
`clinical_sources/source_inventory_2026-08-02.json`: 50 declared CR IDs, 48
local metadata matches, 43 local PDFs, and 22 records without a usable CR ID.
The generated calculator now applies a mandatory source gate: 67 records are
automatically blocked for missing source specs, 4 retain existing explicit
blocks, and only CR 314 remains unblocked.

Official cards were checked for `654_2` adult CAP (2024), `714_2` pediatric CAP
(2025), `898_1` adult sepsis (2024), and `912_1` neonatal sepsis (2025). Their
IDs/URLs are corrected, but calculations remain blocked pending exact PDF
candidate extraction and binding. No owner attestation or bundle activation
occurred. Generated DB/HTML: 72 diseases, 40 drugs, 287 regimens. Tests: 1568
passed, 1 xfailed, 0 failed. Production P5.6/P6 status is unchanged.

## 2026-08-02: CR 306_3 pinned; tonsillopharyngitis calculation blocked

Official CR `306_3`/2024 is confirmed for adults and children. Its current
55-page PDF and deterministic 16-candidate pediatric extraction are hash-pinned
in `clinical_sources/regimen_candidate_specs/306_3.json`. Six candidates are
structurally parseable; ten remain explicitly blocked. No owner attestation or
bundle activation occurred.

The old adult and pediatric calculator records contain material source
disagreements and are blocked in UI and server binding. Source audit: 72
diseases; 3 covered by pinned specs, 4 calculation-blocked, 67 unblocked
missing-spec. CR 313_3 sinusitis remains blocked pending a complete PDF.
Generated DB/HTML: 72 diseases, 40 drugs, 287 regimens, eight pre-existing age
warnings. Canonical tests: 1566 passed, 1 xfailed, 0 failed. Production P5.6/P6
status remains unchanged.

## 2026-08-02: current sinusitis revision identified; stale calculation blocked

The Ministry rubricator confirms current acute sinusitis CR `313_3`, approval
year 2024, adults and children, revision no later than 2026. Both calculator
records previously referenced CR 313/2021. Their static regimens are now
blocked at UI and server binding boundaries until the complete 313_3 PDF is
hash-pinned and candidates are extracted.

Current source audit: 72 diseases total; 1 `VERIFIED_SPEC` (CR 314 pediatric
AOM), 2 `SOURCE_BLOCKED` (adult and pediatric sinusitis), and 69 unblocked
`MISSING_SPEC`. The current CR 313_3 PDF download remains incomplete and is
not registered. No owner attestation or personal bundle activation occurred.

Generated DB/HTML builds pass with 72 diseases, 40 drugs, 287 regimens and the
eight pre-existing age warnings. Canonical tests: 1564 passed, 1 xfailed,
0 failed. Production P5.6/P6 status remains unchanged.

## 2026-08-01: verified source coverage is explicit and fail-closed

The tracked source registry currently covers 1 of 72 calculator diseases:
`aom_child` / CR 314. Its source contract pins PDF SHA-256
`6022928b4138f2a2ab9319c34e2a3b2c13bb53f2d08add5eb3fa83eed296665d`
and candidate-payload SHA-256
`48a240e3abbab90762ca93c9f7dd3f4e7c09edc3d14cdc3bbc9fc47e9c73ca13`.
The other 71 disease records remain `MISSING_SPEC`; this is not full-corpus
clinical verification.

The personal API checks this tracked contract on every extracted-candidate
read and attestation. Local artifact edits and extraction-code drift are
blocked. The official rubricator indicates sinusitis revision `313_3`, while
the local calculator still references CR 313/2021; its official PDF snapshot
has not yet downloaded completely and therefore is not registered or used.

No owner attestation or active personal bundle exists. Production P5.6/P6
status is unchanged. Preview is running at `http://127.0.0.1:8980/personal`;
live API/UI QA passed for eight CR 314 cards, four fail-closed. Canonical
tests: 1563 passed, 1 xfailed, 0 failed.

## 2026-08-01: PDF-extracted dosing path active for pediatric AOM

The personal calculator now consumes queued, source-linked regimen candidates
derived from structured PDF tables instead of requiring dose JSON to be typed
by hand. The first live source is current CR 314 (`Отит средний острый`, 2024),
official PDF SHA-256
`6022928b4138f2a2ab9319c34e2a3b2c13bb53f2d08add5eb3fa83eed296665d`.

Eight pediatric table schemes are extracted with page/row/column/bbox/source
wording. Six are semantically parseable; two fail closed. Four candidates have
five exact compatible calculator/form options: amoxicillin (two allowed
calculation policies within 50-60 mg/kg/day and 2-3 administrations), oral
amoxicillin/clavulanate, cefixime and clarithromycin. Cefuroxime is intentionally
not offered because its required under-3 oral suspension concentration is not
verified in `drugs_reference`.

Versioned-KB objects remain `draft/pending/queued`; no automatic clinical
approval occurs. Owner registration exists, but there are still zero owner
attestations and no active personal bundle. Production P5.6/P6 status is
unchanged. Canonical tests: 1558 passed, 1 xfailed, 0 failed.

## 2026-08-01: personal owner registered; bundle still inactive

Local owner `khatiev_turpal` is registered as physician
`Хатиев Турпал Хусаинович`, organisation `МЕГИ`. The application accepts the
owner ID and one-time token. Recommendation eligibility is still false because
zero exact regimens have been owner-attested and no personal bundle is active.
No production approval state changed.

Lost-token recovery is available only for a pristine owner state and is
permanently refused after any attestation, bundle, active pointer, or request
audit exists. Canonical test result: 1552 passed, 1 skipped, 1 xfailed,
0 failed.

## 2026-08-01: PERSONAL_PHYSICIAN_MODE implemented; clinical activation gated

The owner explicitly accepted `PERSONAL_PHYSICIAN_MODE_RFC.md`. Branch
`codex/personal-physician-mode` now contains the additive implementation:

- `clinical_engine/personal/`: immutable bundle contracts, hash validation,
  external guard, recommender, local runtime, one-time owner token,
  append-only attestation ledger and minimized request audit;
- `clinical_engine/api/v2_contract.py` and API routes under `/v2/`;
- `antibiotic_calc.html.template` and generated `antibiotic_calc.html`:
  explicit personal-mode UI, owner workflow, full patient safety inputs,
  source/trace display and exact calculator binding;
- `.local/personal_physician/` is gitignored; production DB/PDF and production
  approval states are untouched.

Canonical verification: `.venv\Scripts\python.exe -m pytest -q` -> 1550
passed, 1 skipped, 1 xfailed, 0 failed. Browser QA on
`http://127.0.0.1:8980/personal` verified the ordinary calculator, pediatric
suspension output, amoxicillin/clavulanate forms, visible non-dismissible
banner, and fail-closed state without an active owner bundle.

The real local owner is now registered; no regimen was registered or attested
automatically. Personal clinical activation still requires explicit
per-regimen source attestation and bundle build.
Production approved clinical objects remain zero; P5.6 remains
ACCEPTANCE/NOT COMPLETE and P6 remains BLOCKED.

## 2026-08-01: fail-closed Engine developer API running

Engine/regimen/Review Workbench scope: 595 passed, 0 failed under Python
3.12.10. The local API is available at `http://127.0.0.1:8980/docs` with no
curated recommender. `/v1/recommend` returns explicit
`REVIEW_REQUIRED / KNOWLEDGE_UNAVAILABLE` and an empty recommendation list.

The real review DB is unchanged and contains zero approved objects. This is a
developer preview, not P6 entry and not Clinical Engine authorization over
real unapproved regimens.

## 2026-08-01: physician-pilot store ready; reviewers not registered

Read-only pilot preflight passed: authoritative review DB SHA-256
`3e479ee70e59ce9aafa6ba44718dda68d867dbcc660796b81ff63d2b19ca0f29`,
integrity `ok`, 9,153/9,153 tasks `PENDING`, 30 unique pilot task IDs,
0 decisions, 0 assignments, 0 rejected attempts, and 0 approved objects.

No `reviewer_registry.sqlite` exists. Pilot status remains
`WAITING_FOR_REVIEWERS` until the owner supplies real identity and
professional metadata for distinct Reviewer A and Reviewer B, plus an
Adjudicator and Medical QA Lead. Clinical Engine remains disconnected.

## 2026-08-01: repository publication gate closed

Validated commits through `bab018fac400acfe5731c3157a6f547473631f9c`
were pushed to `origin/main`; the pre-push divergence was 0 behind / 38 ahead.
No untracked local artifacts were included.

The next gate is clinical governance: register real Reviewer A, Reviewer B,
Adjudicator, and Medical QA Lead, then run the governed physician pilot.
P5.6 remains ACCEPTANCE/NOT COMPLETE. P6 remains BLOCKED, Clinical Engine
remains disconnected, and physician-approved clinical objects remain zero.

## 2026-07-30: locked fresh-clone verification passed

Commit `5817a60ae63c581d6b1fe23f77b2105bf210783b` passed isolated
fresh-clone validation with temporary uv 0.11.32, Python 3.12.10, and frozen
dependencies from `uv.lock`.

Results: `uv lock --check` PASS; 1511 collected; canonical suite
1499 passed / 11 skipped / 1 xfailed / 0 failed; focused C7/portability
392 passed / 4 expected optional-artifact skips / 0 failed. Forbidden
DB/PDF/key/env files and secret-pattern hits: zero. Imports resolve only from
the clone.

Remaining repository gate: publication. P6 remains BLOCKED, Clinical Engine
remains disconnected, and physician-approved clinical objects remain zero.

## 2026-07-30: C7 acceptance boundary committed

Commit `60e603387a7132ff2aa6a736c869e5b9a7c6903a` contains exactly the
94-file audited boundary. Committed tree
`2b94cb7bad374bf2f3da7a0a2aa10785942a22a1` matches the isolated tested tree.
Staged security/artifact checks passed with zero findings.

Remaining P5.6 work: locked-dependency fresh-clone validation of `60e6033`
and publication; `main` is ahead of `origin/main`. P6 remains
BLOCKED, Clinical Engine remains disconnected, and approved clinical objects
remain zero.

## 2026-07-30: P5.6 C7 acceptance boundary prepared

C7 source-fidelity review remains closed: 182 valid append-only events,
113/113 regimens, zero validation issues, 105 exact owner/AI matches,
8 governed per-administration label equivalents, zero substantive
mismatches, and zero quarantined defects.

An exact 94-file, 3,753,863-byte proposed Git boundary is recorded in
`P56_C7_ACCEPTANCE_PROPOSED_ALLOWLIST.txt`. It excludes 283 unrelated local
changes/artifacts, all production DB/PDF files, machine-local corpus
manifests, pilot packets, and local owner exports.

Corpus-dependent executable tools now honor `ANTIBIO_CORPUS_DIR` /
`CorpusLocator` or explicit `--corpus-dir`; regression tests cover the
portable selection contract. C7 finalizer provenance is machine-independent
(file name + SHA-256, no developer home path).

Current tests: isolated proposed boundary 1499 passed, 11 skipped, 1 xfailed,
0 failed (1511 collected); focused C7/portability is 396 passed in the local
tree and 392 passed / 4 expected optional-artifact skips in the isolated
boundary. Secret pattern scan found zero current/history hits. Proposed
boundary contains zero forbidden DB/PDF/credential/private-key files.

P5.6 remains ACCEPTANCE/NOT COMPLETE until the exact boundary is reviewed,
committed, revalidated from an isolated locked environment, and published.
`main` remains ahead of `origin/main`. P6 and Clinical Engine integration
remain BLOCKED. Approved clinical objects remain zero.

## 2026-07-30: C7 owner review fully reconciled

Final state: 182 valid append-only events, 113/113 regimens, zero validation
issues, and one terminal event per regimen. Owner-vs-AI comparison: 105 exact
canonical matches, 8 explicitly accepted per-administration label
equivalents, zero substantive mismatches, and zero quarantined defects.
`6068` is closed against repaired evidence as `CORRECT_RANGE_SINGLE`.

Targeted suites: 392 passed. C7 source-fidelity review is complete. This does
not grant clinical approval or calculation eligibility. P5.6 remains
ACCEPTANCE/NOT COMPLETE under the broader governance gates; P6 remains
BLOCKED. Production DB/PDF and Clinical Engine were not changed.

## 2026-07-30: 6068 repaired evidence awaiting owner verdict

The visual PDF repair is implemented as an additive, derived validation
unit. Regimen `6068` now displays `500¹-1000² мг` and validates the numeric
range `500-1000 мг` per administration, frequency 3/day. Its repaired
evidence identity is
`dc0778152ff3053db9cdf4cb9d74e6759bb7ea09f27b6497148ccbc94a4886a0`.
The owner page `correction_07_source_repair.html` is open at 0/1. Targeted
tests: 391 passed. P5.6 remains ACCEPTANCE/NOT COMPLETE until the owner
exports the superseding event and final consolidation is rerun. P6 remains
BLOCKED; no production or Clinical Engine state changed.

## 2026-07-30: C7 owner correction reconciliation complete

Final consolidated state: 181 valid append-only events, 113/113 unique
regimens, one terminal event per regimen, and zero validation issues.
Comparison result: 104 exact matches, 8 table-label equivalents, zero
substantive owner/AI disagreements, and quarantined source-extraction defect
`6068`.

Owner correction work is complete. P5.6 remains ACCEPTANCE/NOT COMPLETE only
because `6068` still requires governed source repair/revalidation and the
eight-label metric-equivalence rule remains a documented governance choice.
P6 remains BLOCKED. No production or Clinical Engine state changed.

## 2026-07-30: 5528 remains the final substantive correction

The latest single-mode export is structurally valid but still terminates
`5528` in `CORRECT_RANGE_SINGLE`. A dedicated retry page with explicit
ethambutol/rifabutin comparison is required. Final reconciliation is not yet
closed. The retry page is open at `0/1`; targeted suites are 390 passed.

## 2026-07-30: One substantive owner correction remains

`5824` is corrected to `CORRECT_RANGE_SINGLE`. `5528` remains incorrectly
classified as a per-administration range; it requires
`WRONG_DOSE_ANCHOR`. `correction_05_wrong_anchor.html` is open at `0/1`;
three prior events remain preserved. Latest targeted verification: 390
passed.

## 2026-07-30: Final record 5824 clarification

For `5824`, `10-20 mg/kg` is treated as a per-administration range and
`1 or 2 times/day` as frequency. Final correction page remains active.

## 2026-07-30: Only two substantive corrections remain

Validated terminal correction for `5441` is `CORRECT_RANGE_DAILY`. Only
`5528` and `5824` remain. `correction_04_single.html` is open at `0/2`.

## 2026-07-30: Engine corrections complete

Validated terminal corrections for `5475` and `5478` are
`CORRECT_RANGE_SINGLE`. Remaining checks: `5441`, `5528`, and `5824`.
`correction_03_unit_basis.html` is open at `0/1`.

## 2026-07-30: Engine correction still pending

The latest supplied file was a repeat exact-mode export. It did not contain
`5475` or `5478`; engine correction remains `0/2`. Exact-link terminal
verdicts remain correct despite the redundant superseding events.

## 2026-07-30: Exact-link corrections complete

Corrections `6296` and `6550` passed event validation and now terminate in
`CORRECT_RANGE_SINGLE`. Five substantive checks remain:
`5475`, `5478`, `5441`, `5528`, and `5824`.

`correction_02_engine.html` is open at `0/2`.

## 2026-07-30: Exact-link correction page open

`correction_01_exact.html` is open at `0/2` for records `6296` and `6550`.
Seven substantive owner checks remain in total.

## 2026-07-30: Three unit-basis corrections accepted

The supplied unit-basis export passed validation with zero issues. New
superseding verdicts corrected `7519`, `7629`, and `7644` to
`CORRECT_RANGE_DAILY`. Seven substantive owner checks remain:
`6296`, `6550`, `5475`, `5478`, `5441`, `5528`, and `5824`.

See `RC030_C7_CORRECTION_INTAKE_REPORT.md`. `6068` remains quarantined.
Latest targeted verification: 390 passed.

## 2026-07-30: Correction page 1 awaiting saved clicks

Live state remains `0/2` for `correction_01_exact.html`. Both records still
have only their original historical event; no superseding corrections have
been written. Do not advance until the UI reports `2/2`.

## 2026-07-30: Correction mini-batch active

Four correction-only pages now cover the ten substantive C7 disagreements
without deleting or rewriting any of the 157 validated owner events. The
first page is open at `correction_01_exact.html` with progress `0/2`.

Correction pages use the original review-mode stores, append superseding
events, and maintain a separate correction progress marker. `6068` remains
excluded and quarantined pending governed source repair. P5.6 remains
ACCEPTANCE/NOT COMPLETE; P6 remains BLOCKED.

Latest targeted verification: 390 passed.

## 2026-07-30: C7 governed export intake valid; reconciliation open

The browser-local C7 history was recovered and preserved as 157 append-only
events covering 113/113 regimens. Schema, identity, and supersession
validation returned zero issues; every regimen has exactly one terminal
owner event.

Owner-vs-AI/PDF reconciliation produced 94 exact label matches, 8
label-only per-administration equivalences, 10 substantive disagreements,
and one confirmed extraction defect (`regimen_id=6068`). See
`RC030_C7_OWNER_VS_AI_COMPARISON_REPORT.md`.

P5.6 remains ACCEPTANCE/NOT COMPLETE: immutable owner corrections and a
governed repair of `6068` are still required. P6 remains BLOCKED. No
production data, calculation eligibility, or Clinical Engine state changed.

Latest targeted verification:
`.\.venv\Scripts\python.exe -m pytest tests\rc030_owner_interface tests\dose_verification_sandbox -q`
→ 387 passed.

## 2026-07-30: C7 owner UI review complete; intake pending

All 11 C7 owner-review batches reached full live counters: 113/113 records.
Export actions were triggered, but downloaded bytes have not yet entered
governed validation/consolidation. Therefore P5.6 remains
ACCEPTANCE/NOT COMPLETE and P6 remains BLOCKED.

Owner-observed extraction defect `regimen_id=6068` is confirmed as flattened
footnote markers (`500¹–1000² мг`, not `5001–10002 мг`) and remains blocked
from automatic use. See `RC030_C7_OWNER_REVIEW_COMPLETION_REPORT.md`.

## 2026-07-30: C7 batch 10 complete; final batch 11 open

Single-candidate batch 10 completed at `12/12` and its export action was
triggered. Final batch 11 is open at `0/3`. No authoritative intake or
clinical activation occurred.

## 2026-07-30: C7 batch 09 complete; batch 10 open

Table-context batch 09 completed at `8/8` and its export action was
triggered. Single-candidate batch 10 is open at `0/12`; only batch 11 remains
after it. No authoritative intake or clinical activation occurred.

## 2026-07-30: C7 batch 08 complete; batch 09 open

Final unit-basis batch 08 completed at `7/7` and its export action was
triggered. Table-context batch 09 is open at `0/8`. No authoritative intake
or clinical activation occurred.

## 2026-07-30: C7 batch 07 complete; batch 08 open

Unit-basis batch 07 completed at `12/12` and its export action was triggered.
Final unit-basis batch 08 is open at `0/7`. No authoritative intake or
clinical activation occurred.

## 2026-07-30: C7 batch 06 complete; batch 07 open

Unit-basis batch 06 completed at `12/12` and its export action was triggered.
Unit-basis batch 07 is open at `0/12`. No authoritative intake or clinical
activation occurred.

## 2026-07-30: C7 batch 05 complete; batch 06 open

Unit-basis batch 05 completed at `12/12` and its export action was triggered.
Unit-basis batch 06 is open at `0/12`. No authoritative intake or clinical
activation occurred.

## 2026-07-30: Daily-basis helper covers `/день`

Choice `2` in every C7 owner-review batch now explicitly covers `/день`,
`мг/кг/день`, and `в день` as daily totals over 24 hours, alongside `/сут`.
All interfaces rebuilt; targeted suites remain 385 passed.

## 2026-07-30: C7 batch 04 complete; batch 05 open

Live owner-review state: engine-disagreement batch 04 completed at `11/11`
and its export action was triggered. Unit-basis batch 05 is open at `0/12`.
No export has entered governed intake.

## 2026-07-30: C7 batch 03 complete; batch 04 open

Live owner-review state: batch 03 exact-link review completed at `12/12`;
its export action was triggered. Batch 04 engine-disagreement review is open
at `0/11`. Export bytes remain outside governed intake.

## 2026-07-30: Owner review resumed at batch 03

Local review server is running again on `127.0.0.1:8977`. Batch 03 is open
and currently reports `0/12` in the new browser session. Previous package
exports must be preserved separately; no export has been ingested or
approved.

## 2026-07-29: C7 batch 02 complete; batch 03 open

Live owner-review state: batch 02 exact-link review is complete (`12/12`) and
its export action was triggered. Batch 03 is open at `0/12`. Export bytes
have not yet been supplied for validation/intake; no authoritative clinical
state changed.

## 2026-07-29: C7 batch 02 is 11/12, not complete

Live UI verification found record 1 still unreviewed despite a completion
report. Batch 02 remains open at `11/12`; no export or transition to batch 03
was performed.

## 2026-07-29: C7 owner review progress

Live UI state: batch 01 exact-link review is complete (`12/12`); batch 02 is
open and unreviewed (`0/12`). The batch-01 export action was triggered, but
the resulting file has not been supplied for governed validation/intake.
Therefore this is local owner-review progress only, not an approved or
ingested clinical state.

## 2026-07-29: C7 dose-basis wording corrected

The owner UI now distinguishes a dose's numeric basis from administration
frequency. `1 раз в сутки` no longer appears as a reason to choose daily
total. Choice `2` explicitly means total over 24 hours and requires direct
daily-unit wording. The target card displays the full source range through
`source_range_text` where present.

Targeted RC-030/C7 suites: 385 passed. No genuine owner event was generated.

## 2026-07-29: C7 owner review simplified for direct use

The live interface at `127.0.0.1:8977` now presents one plain Russian
question with a visible target antibiotic/dose and four large answers:
one administration, whole day, unclear, or dose belongs to another drug.
All technical/rare-case sections are collapsed by default. PDF viewing,
blinding, append-only events, and governance restrictions are unchanged.

Targeted RC-030/C7 suites: 385 passed. Browser visual QA passed; no genuine
owner event was generated by the assistant.

## 2026-07-29: C7 PDF opening fixed and live

The owner-review interface now opens source PDFs through the same local
server instead of a browser-blocked `file:///` URL. The server is running on
`127.0.0.1:8977` (PID 26020) with four explicitly configured local PDF roots;
all 39 unique PDFs referenced by the 11 C7 batches resolve across those
roots. Browser verification opened `ВИЧ-инфекция у взрослых.pdf#page=47`.

Targeted RC-030/C7 suites: 384 passed. No owner verdict, clinical approval,
production database write, or Clinical Engine connection occurred.

## 2026-07-29: C7 quick owner-review UI ready

The 11-batch owner source-fidelity interface now supports deliberate
one-click confirmation for per-administration range, daily-total range, and
ambiguous source. It writes a standardized PDF/page note and automatically
advances to the next unreviewed record. Error and unusual outcomes continue
to require the detailed form and custom note. Blinding, append-only storage,
local-only operation, control-mode `test_event=true`, and the prohibition on
clinical/calculation activation are unchanged.

Live synthetic browser validation passed. Targeted RC-030/C7 suites:
382 passed. See `RC030_C7_QUICK_REVIEW_REPORT.md`.

## 2026-07-29: C7 AI PRE-REVIEW COMPLETE (advisory only)

All 113 `READY_FOR_OWNER_REVIEW` C7 source-fidelity tasks now have a separate
AI advisory classification in `RC030_C7_AI_PRE_REVIEW_EVENTS.json`: 64
`CORRECT_RANGE_SINGLE`, 48 `CORRECT_RANGE_DAILY`, 1
`WRONG_DOSE_ANCHOR` (`regimen_id=5528`). Ten records used visual table
evidence, three additional records used targeted visual PDF evidence, and 100
used direct quote plus context.

This does not satisfy owner or physician review. Every event remains
`owner_verified=false`, `human_validated=false`,
`clinically_approved=false`, and `calculation_eligibility=BLOCKED`.
Approved objects remain 0; Clinical Engine remains disconnected; P6 remains
BLOCKED. See `RC030_C7_AI_PRE_REVIEW_REPORT.md`.

Latest verification:
- targeted RC-030/C7: 379 passed;
- canonical suites: 1357 passed, 1 skipped, 1 xfailed, 1 warning.

## 2026-07-16: CORRECTION — RC-031 retracted, filed in error

The "RC-031" drug-name misattribution finding described below (regimen 5574: DB said "Азитромицин,"
PDF said джозамицин) **was false and has been retracted.** Re-verification against the live,
hash-confirmed `assembled_regimens.sqlite` shows regimen 5574's `antibiotic` field is actually
`"джозамицин"`, matching the source PDF exactly; `normalized_regimens.sqlite` (upstream) independently
agrees. The original PyMuPDF PDF lookup was genuine and found the correct source document, but the
"database quote" it was compared against was written by hand during report drafting rather than
copied from a live query, and did not match the real row. Root cause: an earlier, differently-
identified regimen (a genuine Азитромицин 10 mg/kg case, likely `regimen_id=6138`) was mislabeled as
"regimen 5574" in an early worked example, and the label propagated into later reports without being
re-checked. This is a citation/reporting defect in this project's own documentation, not a defect in
the extraction/normalization/assembly pipeline. **No corpus-wide drug-attribution audit was performed
as a result** — the request that would have triggered one was answered with this correction instead.
See `ROOT_CAUSE_REGISTER.md` (RC-031, retracted) and `RC030_TARGETED_SOURCE_RECOVERY_REPORT.md`
(corrected) for the full trace. This does not change RC-030's own verdict (below) — the sub-daily-
frequency and dose-token-location bugs found during that validation were real and remain fixed.

## 2026-07-16: RC-030 Evidence Validation — VERDICT B, CALCULATIONS BLOCKED (supersedes below)

Independent validation of the RC-030 semantics parser (below), per explicit instruction not to treat
parser output as validated truth. Found and fixed three more real bugs: (1) the frequency=1 algebraic
shortcut was applying even when the dose token wasn't locatable in `source_quote` at all (regimen
7951 — zero textual evidence); (2) `frequency < 1` (e.g. "3×/week" stored as 3/7) broke the
daily÷frequency formula, producing a single-dose value **larger than** the daily total (regimen 5376:
210 mg single from 90 mg daily) — now blocked with `SUB_DAILY_FREQUENCY`; (3) the validation's own
independent risk-audit script had a gap-measurement bug inflating false-positive flags from 18.7% to
a spurious 60.4%, also fixed. Computed Wilson 95% confidence intervals on a 135-row manual sample
(smaller than the 380 requested, stated plainly): point precision was 93–100% across six strata, but
**no stratum's lower bound reaches the required 99% threshold** — small-sample statistics cap the
provable bound near 80% even at a perfect score. Per the task's own rule, **every semantic type
remains below the automated-calculation threshold**; `calculation_eligibility = BLOCKED` for all
2,675 rows, enforced in code (`dose_verification_sandbox/validation_status.py`).

**Byproduct finding, later retracted (see correction entry above)**: targeted PDF cross-verification
of regimen 5574 was performed and correctly identified the real source PDF, but the follow-up claim
that its drug name was misattributed ("RC-031") was based on a fabricated comparison and did not
hold up — the database is correct. All 26 max-dose extractions in the corpus were separately,
exhaustively (not sampled) re-verified — all correctly attributed; this part stands. Source DB hashes
reconfirmed byte-identical throughout; approved objects still 0; canonical pytest still passes; 83/83
sandbox tests pass.
**Final verdict: B) RC-030 PARSER IMPLEMENTED BUT NOT VALIDATED — CALCULATIONS BLOCKED.** Nothing
staged or committed. See `RC030_EVIDENCE_VALIDATION_REPORT.md` for full detail. P6 remains BLOCKED.

## 2026-07-16: RC-030 Dose Semantic Reconstruction — PARTIALLY CLOSED (superseded above)

Built an additive, read-only source-text semantics layer (`dose_verification_sandbox/semantics_*.py`)
that resolves the per-dose-vs-per-day ambiguity RC-030 identified, by scanning `source_quote` for
explicit Russian/English signals ("в сутки", "N раз в сутки", "каждые N часов", etc.) instead of
relying on the missing schema column. Full-corpus run on all 2,675 `assembled_regimens` rows:
**1,645 (61.5%; 87.6% of the 1,543 `REVIEW_REQUIRED` rows) now resolve to an explicit dose
semantic** — up from 0 before this work. 202 rows (7.6%) remain genuinely `AMBIGUOUS` (no textual
signal, correctly fails closed), 74 (2.8%) remain `UNPARSED` (compound unit strings — separate open
defect). The original 12-case pilot re-run: 10/12 now calculate correctly (e.g. regimen 5364,
Пиперациллин+тазобактам: 250 mg/kg × 18 kg ÷ 3/day = 1500 mg/dose), 2/12 correctly still blocked.
*(Correction: this line previously cited "regimen 5574, Азитромицин" — that attribution was wrong;
see the RC-031 retraction entry above.)* This is a
**reconstruction layer, not a schema fix** — `assembled_regimens.sqlite` itself still has no
`denominator_time` column; the real fix (Architecture Change, tracked in RC-030) remains open. 21 new
tests, 66/66 total pass. Precommit audit (`DOSE_SANDBOX_PRECOMMIT_AUDIT.md`) done for both this and
the underlying P5.6 sandbox — **nothing staged or committed**, awaits owner approval. Final verdict:
**B) RC-030 PARTIALLY CLOSED — AMBIGUOUS DATA REMAINS**. See `RC030_DOSE_SEMANTICS_REPORT.md`. P6
remains BLOCKED, unaffected.

## 2026-07-16: Dose Calculation Verification Sandbox (P5.6) — READY WITH BLOCKED DATA CASES

New, isolated, read-only QA tool at `dose_verification_sandbox/` (+ `tests/dose_verification_sandbox/`)
lets the owner pick a diagnosis/antibiotic/regimen from `assembled_regimens.sqlite` and inspect the
full dose calculation trace. Never imports `clinical_engine`, never writes to any source database,
`clinical_approval` is hard-locked `NOT_APPROVED`. 45/45 tests pass. Phase 0 audit corrected an
inaccurate earlier claim: `kb_p44.db` has **no** `ClinicalRegimen`/`TherapeuticOption` rows — those
live only in `assembled_regimens.sqlite` (2,675 rows, live-verified, statuses only `REJECTED`/
`REVIEW_REQUIRED`, 0 `APPROVED`). Real-data pilot (Phase 15, 12 cases) found every case legitimately
`BLOCKED`: the source schema cannot distinguish per-dose from per-day dosing, and has no max-dose or
formulation-concentration columns at all — filed as **RC-030** in `ROOT_CAUSE_REGISTER.md`, 12 open
`DoseCalculationIssue` records in `dose_verification_sandbox/data/issues.json`. A live browser-UI
smoke test caught and fixed a real bug (BLOCKED traces reporting `max_dose`/`rounding` as `PASS`
instead of `NOT_AVAILABLE`) before landing. Final verdict: **B) SANDBOX READY WITH BLOCKED DATA
CASES**. See `DOSE_VERIFICATION_SANDBOX_AUDIT.md`, `DOSE_VERIFICATION_SANDBOX_SPEC.md`,
`DOSE_CALCULATION_TRACE_SPEC.md`, `DOSE_ROUNDING_POLICY.md`, `DOSE_VERIFICATION_USER_GUIDE.md`,
`DOSE_VERIFICATION_SANDBOX_REPORT.md`. P6 remains BLOCKED, unaffected by this work.

## 2026-07-15: Review Governance Hardening (GOV-001/002/003 FIXED)

Repository recovery is complete (commit `32096af`, fresh clone validated). Physician pilot
activation found three governance defects before any real reviewer was registered: (1) no
reviewer-registry enforcement in `ReviewService`, (2) Reviewer B could see Reviewer A's verdict
before submitting, (3) two-reviewer consensus alone reported `PHYSICIAN_APPROVED` with no Medical
QA Lead gate. All three are now fixed — see `ROOT_CAUSE_REGISTER.md` (GOV-001/002/003),
`P56_REVIEW_GOVERNANCE_HARDENING_REPORT.md`, `REVIEWER_IDENTITY_AND_ASSIGNMENT_POLICY.md`,
`SECOND_REVIEW_BLINDING_SPEC.md`, `REVIEW_CONSENSUS_STATE_MODEL.md`, `MEDICAL_QA_SIGNOFF_SPEC.md`.
Reviewer registry exists but is intentionally **empty** — `pilot_status = WAITING_FOR_REVIEWERS`.
No real reviewer has been registered, no real clinical decision exists, approved-object count
remains 0 (verified against all 9,153 tasks, not just the 30-task pilot). Clinical Engine remains
disconnected. P6 remains BLOCKED.

## Current authoritative state — 2026-07-15

P5.6 stage: **ACCEPTANCE / NOT COMPLETE**. Review Workbench validated on 1,556 ClinicalRegimen + 652 TherapeuticOption candidates; total queue 9,153, all PENDING, approved=0. Canonical pytest 1,373 collected / 1,371 PASS / 0 FAIL. P6 remains BLOCKED; Clinical Engine disconnected.

Blocking owner actions: credential rotation/revocation; recover canonical source into Git and reproduce from fresh clone. See `GOVERNANCE_SOURCE_OF_TRUTH.md` and `P5.6_PRODUCTION_RECOVERY_REPORT.md`. Historical content below retained.

**2026-07-14: ROLE CHANGE.** Agent role is now defined by `ANTIBIO_PROJECT_CONSTITUTION.md`
(Production Architecture Lead + Senior Implementation Engineer + Medical Software QA + Production
Auditor). AGENTS.md §0.1 "Reviewer-only" is superseded/historical. Frozen scope (Clinical Engine,
medical content, bundle schemas, validated data) unchanged. See constitution §3 for exact frozen
list and §6 for the Definition of Done now required to close any milestone, including the
already-claimed-but-unverified P4.4.

**P5.3 (2026-07-15): Clinical Regimen Assembly Engine IMPLEMENTED** (additive `clinical_engine/
regimen/` package). Sources regimen structure from `normalized_regimens`, enriches from kb_p44 on
deterministic guideline_id linkage (`P5.3_DECISION_RECORD.md`). Measured: 2,675 regimens, 100%
explainable-to-source-line, enrichment coverage 81.6%, 5,615 conflicts (all UNRESOLVED), 0 shadow
divergence vs normalized_regimens (non-breaking), 14 tests pass. Engine NOT switched (shadow only).
Open: RC-023 (kb_p44 atomic linkage), RC-024 (reject-rate governance). See
`P5.3_IMPLEMENTATION_REPORT.md`. Next: RC-024 decision + approval-workflow population before P6.

---

**RESOLVED 2026-07-15.** The open discrepancy below is closed: P4.4 was rebuilt clean on the full
192-PDF corpus (checkpoint 192/192, 0 tracebacks) on a pipeline that also fixed PR-001 (table-loss)
and the full provenance contract (RC-012…018). Full audit executed on the finished KB: 0 blocking
invariant violations (INV-09 was 1,442 violations pre-fix, now 0), 0 silent nulls across 100,854
provenance rows, regression 72 passed/0 failed, CKY + Coverage baselines established. **P4.4
Production Knowledge Base is CERTIFIED** — see `PRODUCTION_SCORECARD.md` and
`PROVENANCE_CERTIFICATION.md` for the full evidence trail, and `P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md`
for regenerated real numbers (31,336 objects, not the stale 116/204 previously claimed).
**Scope caveat:** certification covers the KB build; it does NOT mean the Clinical Decision Engine
serves recommendations from this KB yet (RC-019, `ENTERPRISE_ARCHITECTURE_REVIEW.md` — P5/P6 scope).

*(Prior open-discrepancy text, preserved for history):* ROADMAP.md said P4.4 "✅ COMPLETE (real
exec)"; this section said P4.4 "ACTIVE + IN PROGRESS"; `p44_kb_checkpoint.json` showed only 2/193
corpus PDFs processed. Resolved above by real full-corpus execution + audit re-derivation.

**Версия:** 1.0.2-clinical-engine-perf-audited
**База:** КР МЗ РФ (cr.minzdrav.gov.ru)
**Статус:** Clinical Decision Engine — реализация завершена (M1-8) + аудит устранён (M9) + **Performance Audit пройден на реальных 2675 схемах, все цели §9.1 выполнены** ✅. `Engine.recommend()` — полный pipeline из 10 стадий.
**Базовая документация (принята 2026-07-10):** `ARCHITECTURE_V3.md` + `ENGINEERING_MASTER_PLAN.md` + `DEVELOPMENT_BACKLOG.md` — официальный план проекта. Design-фаза закрыта; изменения архитектуры — только по реальной инженерной причине (RFC).

**Фаза:** P1 Terminology Binding — Clinical Product Focus.

**P0 Status:** OFFICIALLY COMPLETE + FROZEN. See P0_COMPLETION_REPORT.md. Infrastructure locked.

**Process phase complete.** No more new rules. Focus: clinical product. Physician value, real cases, Golden validation.

**P1 Status:** P1-A COMPLETE + FROZEN. P1-B CLOSED (ACCEPTED + FROZEN). Genuine PASS after independent repro of 4 findings + minimal additive fixes only. P0 fixture pure. P1 dedicated. 0 failed. Golden PASS. No P1-A reg. Negative Golden now assert both guideline_id (present) and not_guideline_id (absent) to fully prove incorrect guideline exclusion.

**P2 Status:** P2-1 Conformance Validator — COMPLETE + FROZEN. Golden now proves incorrect guideline exclusion (not_guideline_id + trace_code). All audit medical findings addressed in data scope.

**P3 Status:** Clinical Data Curation — ACTIVE. Medical content only. Resolve 101 diagnosis conflicts, expand synonyms (incl. peds), structure renal, fill ATC, build 300+ Golden Cases. Target: PRODUCTION_CURATED. No engine changes.

**P4 Status (2026-07-13):** P4 — Document Intelligence Platform ✅ COMPLETE + Production Ready

P4.1 Multi-Engine Extraction ✅
P4.2 Layout Intelligence ✅ (P4.5 PRODUCTION RELEASE COMPLETE)
P4.3 Medical Semantic Layer ✅

**P4.5 FINAL CLINICAL ACCEPTANCE AUDIT (2026-07-13):** STRICT AUDIT COMPLETE — **A) P4.5 PASSED**.

- Full 12-step production audit executed (real corpus, reprocessor on 193 contributing PDFs, clinical field extraction measured via cells, before/after vs table_dependency_audit baseline, completeness table, table impact quantified, 0 FPs).
- Representative: 20 structured_tables on table-heavy PDF (dose/alt/ped/dur signals recovered from cells); 0 on non-table (correct).
- Reprocessor validated (checkpoint, resume, metrics: tables/cells/dose_cells/table_used/layout_processed).
- Regression: extraction/layout/semantic suites 11 passed (no regression).
- Engineering audit: code/arch/docs/benchmarks/clinical/consistent — PASS.
- **P4.4 Production Knowledge Base Platform — ✅ CERTIFIED 2026-07-15 (STRICT, real exec).**
  - Enhanced immutable KnowledgeObject + rich Provenance v2 (layout_engine, table_row/col/bbox,
    table_conf, original_text/normalized_value, guideline_id, schema_version) — canonical contract
    per `PROVENANCE_SPECIFICATION.md`.
  - `build_p44_kb.py` (production rebuild tool) + `kb_p44.db`.
  - Real measured (final, 192/192 corpus): **31,336 objects** (Dose 24,705, Medication 2,788,
    Evidence 2,190, Contraindication 841, Recommendation 381, Diagnosis 431); 100,854 provenance
    rows, 0 blocking invariant violations, 0 silent nulls.
  - Comprehensive reports: `P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md`, `PRODUCTION_SCORECARD.md`,
    `PROVENANCE_CERTIFICATION.md`.
  - **Next milestone (P5)** must resolve RC-019 (engine reads a different DB) as a first-class
    deliverable — see `ANTIBIO_ROADMAP_P5_P10.md`, `docs/rfc/P5_KNOWLEDGE_PLATFORM_RFC.md`.
  - See build_p44_kb.py, src/pipeline/knowledge_base.py.

See P4.5_PRODUCTION_AUDIT.md and table_dependency_audit.

All verified real (mechanics):
- 10/10 tests
- Router/Cache/Provenance/Semantic/Normalization/Knowledge Objects/Consistency
- Real PDFs (300+ ents, fallback paths)
- No raw text downstream

**TABLE DEPENDENCY AUDIT (2026-07-13, STRICT):** 963 PDFs corpus, 193 → 2675 regimens analyzed. 8-14% regimens + 13.6% stratified dosing + 55.9% peds facts table-origin (PyMuPDF verified + heuristics on source_quote/section). Critical dose/dur/alt loss measurable (real sepsis 4-col table → partial KB). **Verdict: P4.5 Layout before P4.4 data freeze.** See table_dependency_audit_2026-07-13.md + AI_LOG + DECISIONS.

**Next:** P4.5 Layout Intelligence productionization (enable full table extraction fidelity) **then** P4.4 content production / freeze on improved data. Mechanics of P4.4 complete; authoritative KB population gated per audit measurements. See ROADMAP + audit.

Big release strategy + paired validation rule active.

No Clinical Engine / bundle changes. Frozen preserved.

**Regimen Review Workbench (2026-07-11):** refined as physician-review tooling only. Default mode is read-only against upstream corpus and writes only `.md`/`.csv` artifacts; `regimen_review_ledger.json` updates require explicit `--update-ledger`. Target-area matching config moved to `clinical_engine/resources/regimen_review_areas.json`; deterministic confidence/match_reason/needs_manual_review/priority emitted. Rows sort by area → priority → diagnosis → regimen_id. Dry run: queue 438 → 305, 138 false positives excluded. Full tests: `python -m pytest -q` → 1266 passed, 1 xfailed, 1 warning.

**Frozen Components**
- Architecture v3
- BundleManifest + schema + validator
- Provider Ports + adapters
- Bundle Loader + wrapping
- Engine invariants
- Medical Normalizer
- SQLite schema
- Medical Dictionary
- Clinical Traceability Rule
- Optimization Rule
- P1-A Drug Terminology (TerminologyProvider)

**Current Milestone**
P2-1 Conformance Validator (Phase 2 Eval & Assurance)

**Active Issue**
P2-1 CLOSED (additive complete, frozen per workflow)

**Workflow Stage**
P2-1 full workflow complete: Analysis (enhanced) → RFC (light) → Impl (additive) → Tests (real 298 passed) → Review (PASS) → Freeze → Docs. Next: handoff + next item ANALYSIS ONLY.

**Current Test Status**
- Extraction/layout/router/semantic/document: **11 passed** (latest run).
- Reprocessor validated on real PDF (layout_processed, metrics collected).
- P4.5: representative + mechanism complete (20 tables on table-heavy PDF; 192 PDFs supported).

**Next Implementation Step**
P2-1 CLOSED. P2-2 Analysis ONLY (doc). STOP. No impl.

**Permanent laws:**
- Clinical value primary.
- Clinical Evidence Rule.
- Clinical Traceability Rule (law): 7 questions per rec. No black box.
- Optimization Rule (permanent): Never optimize infrastructure unless it directly improves clinical decision quality, safety, maintainability, or measurable performance.

If no measurable benefit exists, do not change it.

**DoD P1+:** Clinical Justification + Acceptance Criteria + traceability. Demonstrate physician benefit. No pure infra justification. No unmeasured opts.

**Текущий статус (2026-07-10):**
- P0-1 BundleManifest — **CLOSED + FROZEN**.
- P0-2 Provider Ports — **CLOSED + FROZEN**.
- P0-3 Bundle Loader — **CLOSED + FROZEN**.
- P0-4 Bundle Wrapping — **COMPLETE** (checklist migration).
- Все компоненты P0 заморожены. Изменения только по новому RFC.
- BundleManifest, JSON Schema, validator, Providers, Loader, Wrapping — **ЗАМОРОЖЕНЫ**.
- Введено постоянное правило проекта (ANTIBIO Development Workflow):

  1. Analysis (понять текущую реализацию, без кода)
  2. RFC / Design (только если требуется; лёгкий impl RFC, без редизайна архитектуры)
  3. Review (проверить assumptions)
  4. Implementation (инкрементально, additive, feature-flagged, без изменения поведения без approval)
  5. Tests (positive, negative, regression)
  6. Acceptance Review (DoD, RFC compliance, no feature creep)
  7. Freeze (контракты при завершении)
  8. Documentation (обновить все handoff docs, consistency audit, cross-IDE handoff)
  9. Close Issue

  Правило зафиксировано в DECISIONS.md, HANDOFF.md, AI_LOG.md. Репозиторий — единственный источник истины. AI Memory Rule: предполагать нулевую память в каждой новой сессии.

**P0 Status:** COMPLETE + FROZEN. See P0_COMPLETION_REPORT.md.

**Current Active:** P1 — Terminology Binding (per ENGINEERING_MASTER_PLAN). Analysis phase.

**P0-2 Provider Ports (2026-07-10):** CLOSED (frozen).

**P0-3 Bundle Loader (2026-07-10):** CLOSED + FROZEN. Pure generic loader.

**P0 COMPLETE (2026-07-10):** See P0_COMPLETION_REPORT.md + P0_Phase_Gate_Review.md (accepted). Infrastructure Foundation frozen. All P0 contracts stable. Per Master Plan: P1 Terminology next.

**Test status:** 1159+ baseline + P0 infra tests. 0 regression.


**Clinical Data Quality Audit (2026-07-10, read-only, ничего не изменено):** реестр `clinical_data_issues.json` (4506 записей, `pending_review`) + `clinical_data_audit_report.md` + инструмент `clinical_engine/tools/clinical_data_audit.py`. Из 294 guideline: **41 Golden-Ready кандидат**; Extraction-ошибки 235 / Normalizer 166 / Dictionary 224 / дубли title 182 gid; переэкстракция 83. SAFETY: DOSE_DAILY_MISREAD 61, DOSE_NOT_PARSED 116. PDF-подтверждён только 1638 (амоксициллин 1,5г/сут→норм. 1,5г×2=3г/сут). **Golden Case 1638 НЕ создан.**

**Milestone 13 — Release Readiness (done ✅):** Production Guard (`Engine` под `strict_mode=True` отказывается стартовать на `AUTO_GENERATED_DRAFT`/`PARTIALLY_CURATED` индексе → `EngineError(RESOURCE_NOT_CURATED)`; non-strict → warning). Test discovery: дефолтный `pytest` покрывает все подсистемы (**1141 passed, 1 xfailed** — extractor помечен xfail, не исправлялся). RFC H1 (§7.5) переоценён → рекомендация закрыть для v1 без изменений. Git-рекомендации: `RELEASE_READINESS.md` (не коммитил). Медицинская логика/алгоритмы не менялись.

**Milestone 12 — инфраструктура Golden Clinical Cases (done ✅, кейсы за врачом):** `clinical_engine/golden_cases/` (`runner.py`, `schema.json`, `_TEMPLATE.json`, `README.md`) + `clinical_engine/tests/test_golden_runner.py` (13). Раннер: кейс → `Engine.recommend()` → PASS/FAIL, read-only. Формат: `query` + `expect{13 опциональных ассертов}` + `provenance`. Реальных кейсов НЕ поставлено (guard-тест проверяет). Запуск: `python -m clinical_engine.golden_cases.runner --sqlite <normalized.sqlite>`.

**Milestone 11 — механизм врачебной курации (done ✅, ждёт врача):** `clinical_engine/tools/build_decision_ledger.py` + `build_curated_index.py` + 17 тестов + `PHYSICIAN_VALIDATION_GUIDE.md`. Никакого авто-выбора; каждый конфликт отдельно; решение врача с обязательным `decided_by`/`decided_at`/`rationale`; полный аудит-трейл; обратимость (ledger — источник истины, черновик не трогается); `PRODUCTION_CURATED` только при 0 pending и 0 invalid. Сейчас: 101 конфликт pending → `PARTIALLY_CURATED`. Ledger: `diagnosis_index_decisions.json` (редактирует врач).

**Milestone 10 — анализ конфликтов diagnosis_index (задача 1, done ✅):** `diagnosis_index_review.md` + `.json`. Из 101 конфликта: 🔴 51 critical (ICD-10 различаются) / 🟡 2 medium (ICD совпадают, КР разные) / 🟢 48 safe (вероятные дубликаты) + 28 near-dup имён (регистр/пробелы). Классификация только по фактам, БЕЗ авто-объединения/эвристик/клинических допущений — разрешение конфликтов за врачом. Data-cleanliness fix: `_split_icd10` теперь корректно парсит JSON-array-string mkb (33/265 значений). Индекс остаётся AUTO_GENERATED_DRAFT. Инструмент: `clinical_engine/tools/analyze_diagnosis_conflicts.py`.

> **Протокол хендоффа (см. `AGENTS.md` секция 0):** в конце каждой задачи любой агент/IDE обязан обновлять `AI_LOG.md` / `PROJECT_STATE.md` / `NEXT_TASK.md` / `DECISIONS.md`. Работа продолжается из любой IDE только по этим MD-файлам.

**Performance Audit (реальные данные, STRICT):** init ~29ms (<100), recommend() max 14.6ms adult / 17.4ms heavy (<50 ✅), P95 ~8ms, ~2540 recs/sec, SQL 1.23/call, peak 2.2MB. Bottleneck: `RegimenLoad` ~69% (SQL + drug_ref resolve + повторный lookup L7). Оптимизация НЕ проводилась (ждёт review). Отчёт: `performance_audit_engine.md`. Инструменты: `clinical_engine/tools/`. Draft `diagnosis_index.json` (AUTO_GENERATED_DRAFT, 895 записей, 101 конфликт) — требует врачебной курации.

**Аудит (Milestone 9):** 1 HIGH + 5 MEDIUM + 8 LOW. Кодом исправлено: M1 (allergy hardening — регистронезависимость + `ALLERGY_UNVERIFIABLE`), M3 (package-anchored пути), M5 (типизация reader'ов), L1/L2/L4/L8 (coupling/dead-code/consistency). Документацией: M2 (неточная запись), H1+M4 (per-recommendation trace/Evidence §7.5 → задокументированный gap с RFC, ждёт approval — требует изменения frozen-моделей). См. `DECISIONS.md`.

---

## Clinical Decision Engine (`clinical_engine/`)

| Milestone | Статус | Содержимое |
|-----------|--------|-----------|
| M1 — skeleton | ✅ done (2026-07-10) | `models.py` (enums + frozen dataclasses), `config.py` (EngineConfig + Profiles), `pipeline.py` (PipelineStage Protocol, PluginHook, StageContext/State/Result, ScoreWeights, ClinicalConstants). 40 тестов. |
| M2 — readers | ✅ done (2026-07-10) | `readers/sqlite_reader.py` (обёртка над `medical_normalizer.db.NormalizerDB`), `readers/drug_reference_reader.py` (`db/index.json` + pregnancy keyword-классификатор), `readers/diagnosis_reader.py` (`DiagnosisProvider` Protocol + `JsonDiagnosisProvider`), программные fixtures. 39 тестов. |
| M3 — Stages 1-2 + engine.py | ✅ done (2026-07-10) | `stages/diagnosis_match.py`, `stages/regimen_load.py` (join drug_ref + guideline_year), `engine.py` (`Engine.recommend()`, EngineMetadata/ClinicalConstants/ScoreWeights как placeholder до M5/M8/M9). 20 тестов. |
| M4 — Stages 3-4 + invariants | ✅ done (2026-07-10) | `stages/population_filter.py` (жёсткий фильтр, neonate→child flag), `stages/therapy_line_select.py` (pass-through, не фильтр — см. DECISIONS.md), `tests/test_invariants.py` (15 тестов на конституцию §12 + 2 skip-плейсхолдера для Milestone 8). 24 теста. |
| M5 — Stage 5 HardSafetyFilter | ✅ done (2026-07-10) | `stages/hard_safety_filter.py` (allergy/pregnancy/age ABSOLUTE excludes, contraindications всегда degraded WARNING — 0/40 препаратов имеют это поле), первый реальный ресурс `resources/clinical_constants.json` (allergy_class_map курирован вручную из 34→17 классов, draft, требует врачебной верификации). **Движок впервые может окончательно исключить препарат.** 21 тест. |
| M6 — Stages 6-7 DoseCalculation/DoseAdjustment | ✅ done (2026-07-10) | `stages/dose_calculation.py` (adult fixed / peds mg/kg×weight, asymmetric ambiguous-population fallback только для adult), `stages/dose_adjustment.py` (renal/hepatic — **только WARNING в v1**, hepatic-эскалация до exclude сознательно НЕ реализована — см. DECISIONS.md "never infer contraindications from free text"). 25 тестов. |
| M7 — Stage 8 InteractionCheck | ✅ done (2026-07-10) | `stages/interaction_check.py` (free-text match → всегда `UNKNOWN`, никогда не угадывается severity; CONTRAINDICATED/MAJOR/MODERATE/MINOR ветки реализованы и протестированы через monkeypatch, недостижимы без структурированных данных — но, в отличие от hepatic, это ограничение самой спеки, не наше отклонение от неё). 18 тестов. |
| M8 — Stage 9-10 RankRecommendations/Trace (финальный) | ✅ done (2026-07-10) | `stages/rank_recommendations.py` (7-компонентный скоринг, только на `state.candidates`, Invariant #3), `stages/trace.py` (outcome labeling), `resources/score_profiles/default.json`, `engine.py` — реальный `EngineMetadata` (не placeholder), `Engine.build_report()`. **Движок теперь возвращает полностью ранжированный `RecommendationSet`.** 30 тестов, 0 skip. |
| M9 — Audit remediation | ✅ done (2026-07-10) | Устранены замечания независимого аудита: M1 (allergy hardening), M3 (package-anchored пути), M5 (типизация reader'ов), L1/L2/L4/L8. H1+M4 → задокументированный gap с RFC. +3 теста. `clinical_engine/_population.py` (нейтральный helper). |
| Perf Audit | ⏳ next | `Engine.recommend()` на реальной `metadata.sqlite` (2675 схем), цель <50ms (§9.1) |
| Golden cases | ⏳ | Doctor-reviewed golden cases, production `diagnosis_index.json`, врачебная верификация `allergy_class_map` |
| Flutter | ⏳ | интеграция после verification |

**Известный риск (подтверждён проверкой всех 40 препаратов в Milestone 2, не блокирует — degraded-mode принят как решение):** `renal_adjustment`/`interactions` — свободный текст (передаётся как есть, не парсится). `contraindications` и `pediatric_dosing` отсутствуют у **всех** 40 препаратов. Generic `age_restriction_max` тоже отсутствует. `pregnancy_category` — свободный текст, но приведён к enum узким keyword-классификатором в `DrugReferenceReader` (см. DECISIONS.md). Итог: HardSafetyFilter (CI-проверка), DoseCalculation (peds mg/kg) будут в degraded WARNING mode для этих полей в v1 — ожидаемо, задокументировано.

**Известный риск (Milestone 5, задокументирован):** `allergy_class_map` в `resources/clinical_constants.json` — ручная курация 34 узких `class`-строк из `db/index.json` в 17 канонических аллергенных классов (объединены только generation/route-подварианты одного семейства — пенициллины, цефалоспорины, макролиды, фторхинолоны). Черновик, требует врачебной верификации перед production-использованием (см. DECISIONS.md).

**Известный пробел (Milestone 6, задокументирован):** `pediatric_dosing` отсутствует у всех 40 препаратов → пед. дозирование всегда `PEDS_DOSING_UNKNOWN` на реальных данных. `hepatic_adjustment`/`renal_adjustment` — свободный текст у всех препаратов, где присутствуют (15/40 и 29/40 соответственно) → Stage 7 всегда в degraded WARNING-режиме, дозу численно не корректирует, hepatic никогда не исключает препарат в v1 (сознательное решение, не пробел реализации — см. DECISIONS.md).

**Известный пробел (Milestone 7, задокументирован):** `interactions` — свободный текст у 32/40 препаратов, структурированного поля нет вообще. InteractionCheck поэтому всегда даёт `UNKNOWN` severity при текстовом совпадении, никогда MAJOR/MODERATE/MINOR/CONTRAINDICATED на реальных данных — это ограничение самой спецификации (§6.4 явно резервирует классификацию severity для preparation-time structured данных), не наше решение отступить от неё.

**Осознанно не реализовано (Milestone 8, задокументировано, не архитектурный пробел):**
- Confidence propagation (§7.3) — `Recommendation.confidence`/`confidence_breakdown` на дефолтах
- Plugin hooks — enum существует, registry нет
- 4 из 5 score profiles (ent/urology/icu/pediatrics) — content-задача
- `guideline_version` в `EngineMetadata` — `"unversioned"`, ждёт production `diagnosis_index.json`

**Тесты:** дефолтный `pytest` → **1159 passed, 1 xfailed** (0 регрессий после P0-1 тестов). Пре-existing xfailed только в extractor.

---

## Компоненты

### Приложение (antibio-calc)
| Компонент | Статус |
|-----------|--------|
| База препаратов (28 шт) | ✅ 85% |
| База нозологий (46 шт) | ✅ 85% |
| Схема БД (schema.json) | ✅ 100% |
| Build-скрипт c валидацией (build_db.ps1 + build_html.ps1) | ✅ 100% |
| Валидация целостности БД (validate_db.js) | ✅ 100% |
| Сборка БД (db/build_db.ps1) | ✅ 100% |
| UI — поиск нозологий | ✅ |
| UI — выбор препарата/формы/дозы | ✅ |
| UI — расчёт доз (мг/мл) | ✅ |
| UI — разведение инъекций | ✅ |
| UI — печать рецепта (латынь) | ✅ 100% |
| Клиентская валидация БД (validateDB в init()) | ✅ 100% |
| UI — история расчётов | ✅ |
| UI — тёмная тема | ✅ |
| UI — адаптив (мобильный/десктоп) | ✅ |
| Копирование назначения | ✅ |
| Тесты | ❌ Нет |
| CI/CD | ❌ Нет |
| Документация разработчика | ✅ Создана |

### Pipeline (извлечение КР → knowledge_base.json)
| Компонент | Статус |
|-----------|--------|
| Загрузчик PDF (clinrec_downloader) | ✅ 2000+ PDF |
| Классификатор (antibiotic_gate) | ✅ A/B/C/D уровни |
| LLM-экстракция (extract_raw) | ✅ 294/361 A+B (81.4%) — 67 осталось |
| Валидация LLM (validate) | ✅ mock (реальная: ждёт API) |
| Сборка knowledge_base.json | ✅ 294 guidelines, 2675 regimens |
| SQLite (metadata.sqlite) | ✅ 2675 regimens (без дубликатов) |
| Prefilter (prefilter.py) | ✅ классификация 2000 PDF за 0.17с |
| Audit no_antibiotics | ✅ 305 → 298 (7 перемещены) |
| Дубликаты-конфликты | ✅ 17 decisions унифицированы (11 filenames) |
| Sync (misplaced PDFs) | ✅ 0 misplaced, 1893 manifest entries |
| Quarantine | ✅ 2 orphans → quarantine/ |
| Crash safety (fsync + checkpoint) | ✅ per-PDF + every-10 checkpoint |
| Restore_archived_pdfs.py | ✅ создан |
| Deep audit | ✅ PASS (0 issues, 4 warnings) |

### Medical Normalizer (`medical_normalizer/`)
| Модуль | Статус | Тесты |
|--------|--------|-------|
| models.py | ✅ | — |
| dictionary.py | ✅ | ✅ |
| drug_parser.py | ✅ | ✅ |
| dose_parser.py | ✅ | ✅ |
| route_parser.py | ✅ | ✅ |
| frequency_parser.py | ✅ | ✅ |
| duration_parser.py | ✅ | ✅ |
| population_parser.py | ✅ | ✅ |
| therapy_line_parser.py | ✅ | ✅ |
| confidence.py | ✅ 100% coverage | ✅ 130 тестов |
| validator.py | ✅ 100% coverage | ✅ 164 теста |
| normalizer.py | ✅ 100% coverage | ✅ 134 теста |
| db.py | ✅ 99% coverage | ✅ 121 тест |
| **Итого medical_normalizer** | **✅ COMPLETE** | **726 тестов** |

**Тесты medical_normalizer:** 726/726 pass (`pytest medical_normalizer/tests/ -q`)

**Integration test (80 regimens из knowledge_base.json):**
- PASS: 24 (30.0%), REVIEW: 10 (12.5%), REJECT: 46 (57.5%)
- Confidence: min=0.200, max=0.919, mean=0.615, median=0.704
- Главные REJECT: REQUIRED_MISSING (route/frequency/dose не извлечены LLM)
- Главные REVIEW: DRUG_UNKNOWN (препарат не в словаре)
- Все 80 regimens сохранены в SQLite через NormalizerDB.save_many()

---

## Рабочие папки

- `downloads_active/` — 477 PDF для LLM-экстракции
- `archive_review/` — 361 PDF требующие ручного просмотра
- `archive_no_antibiotics/` — 123 PDF без антибиотиков
- `quarantine/` — 2 orphan PDF (неопознанные)
- `downloads_all/` — пусто (все PDF распределены)

## LLM-провайдер

- **Активный:** DeepSeek V4 Flash через opencode.ai/zen (opengo tariff). Работает (HTTP 200).
- **Резервный:** Anthropic claude-sonnet-4-20250514 через vip.j3gb.com (429 daily quota).
- **Неактивные:** openrouter, openai, gemini, ollama, vllm, local — без API-ключа.
- **Модели:** extraction=deepseek-v4-flash, validation=deepseek-v4-flash.
- **max_tokens:** 8192 (для reasoning model).

## Команды main.py

| Команда | Назначение |
|---------|-----------|
| `python main.py doctor` | Health check (read-only) |
| `python main.py sync` | Fix misplaced PDFs, rebuild manifest |
| `python main.py dedup` | Resolve conflicting duplicates in dry_run_manifest |
| `python main.py quarantine` | Move orphan PDFs to quarantine/ |

## Deep Audit (2026-07-09)

**Результат:** V PASS — 0 issues, 27 checks passed

**Предупреждения (4, все приемлемы):**
1. 747 regimen pairs с одинаковым (antibiotic,dose,route,freq) — разные duration/age — не ошибка
2. Quarantine: 2 orphan PDFs (unknown origin)
3. 67 A+B items не экстрагированы (нет релевантного текста или LLM не может обработать)
4. 133/2675 regimens без section_name (5%)

## Quality Audit (2026-07-09)

**Полный аудит 2675 regimens через MedicalNormalizer:**

| Метрика | Значение |
|---------|----------|
| Total regimens | 2675 |
| Total guidelines | 294 |
| PASS | 880 (32.9%) |
| REVIEW | 320 (12.0%) |
| REJECT | 1475 (55.1%) |
| Confidence mean | 0.6312 |
| Confidence median | 0.7044 |
| Performance | 8800 regimens/s |
| Parser errors | 20/2675 (0.7%) |

**Field completeness (после нормализации):**
| Поле | % |
|------|---|
| Drug | 100% |
| Dose | 71.1% |
| Route | 65.1% |
| Frequency | 56.6% |
| Duration | 41.0% |
| Therapy line | 60.1% |
| Pregnancy | 2.6% |
| Renal adjustment | 2.8% |
| ATC code | 0% |

**Сгенерированные файлы:**
- `quality_report.md` — полный отчёт
- `quality_root_cause.md` — Root Cause Analysis (3 отчёта + рекомендация)
- `field_statistics.csv` — статистика по полям
- `unknown_drugs.csv` — 441 неизвестный препарат
- `dictionary_expansion.md` — рекомендации (~160 записей)
- `production_readiness.md` — оценка готовности

## Root Cause Analysis (2026-07-09)

**Per-regimen нормализация 2675 regimens + классификация origin/recoverability.** См. `quality_root_cause.md`.

### Главные выводы (приоритеты пересмотрены)

| Источник | Доля REJECT-причин | Что нужно |
|----------|-------------------:|-----------|
| **LLM extraction** | 75% (2153/2869 required-missing) | LLM re-extraction (high cost) |
| **Normalization** | 25% (716/2869 required-missing) | Parser expansion (low cost) |
| Dictionary | 0% REJECT (1166 REVIEW) | Dictionary expansion (REVIEW only) |

### REJECT breakdown (per-regimen overlap анализ, baseline)

| Группа | Regimens | Recoverability |
|--------|---------:|----------------|
| Parser-only flippable | 403 | parser fix (low cost) |
| Partial (norm + llm) | 281 | parser fix + LLM re-extract |
| LLM-only | 791 | только LLM re-extraction |

## Parser Improvements (Tasks 1-4) — MEASURED (2026-07-09)

**TDD, 4 задачи, 803/803 тестов (+77 new).** См. `quality_audit_after_parsers.md` для полного comparison.

### Verdicts — baseline vs after

| Verdict | Baseline | After | Δ |
|---------|---------:|------:|---:|
| PASS | 880 (32.9%) | 1039 (38.8%) | **+159** |
| REVIEW | 320 (12.0%) | 443 (16.6%) | +123 (REJECT→REVIEW, drug_unknown exposed) |
| REJECT | 1475 (55.1%) | 1193 (44.6%) | **-282** |
| Confidence mean | 0.6312 | 0.7188 | **+0.0876 (+13.9%)** |
| Parser errors | 20 | **0** ✅ | -20 |

### Fields recovered

| Поле | Baseline missing | After missing | Recovered |
|------|----------------:|--------------:|----------:|
| frequency | 1160 | 706 | **454** |
| duration | 1578 | 951 | **627** |
| therapy_line | 1067 | 0 | **1067** |
| dose | 774 | 754 | 20 |
| **Total** | — | — | **2168** |

### Per-task (TDD, measured)

| # | Task | Файл | +Tests | Recovered | ΔREJECT | ΔConf |
|---|------|------|-------:|-----------:|--------:|------:|
| 1 | FrequencyParser | frequency_parser.py | 42 | freq -454 | -274 | +0.0254 |
| 2 | DurationParser | duration_parser.py | 19 | dur -627 | 0 | +0.0174 |
| 3 | TherapyLineParser | therapy_line_parser.py | 7 | tl -1067 | 0 | +0.0437 |
| 4 | Type guards | drug_parser.py | 9 | errors -20, dose -20 | -8 | +0.0011 |

### REJECT breakdown — after

| Группа | Baseline | After | Δ |
|--------|---------:|------:|---:|
| Parser-only flippable | 403 | 118 | -285 |
| Partial | 281 | 111 | -170 |
| LLM-only | 791 | 961 | +170 (reclassified) |
| No required-missing | 0 | 3 | +3 |

**Parser improvements исчерпаны на ~71% (285/403).** Оставшиеся 118 — hard edge cases, diminishing returns.

### Origin shift

| Источник | Baseline | After | Δ |
|----------|---------:|------:|---:|
| Normalization | 772 | 298 | **-474 (-61%)** |
| LLM extraction | 3055 | 3055 | 0 |
| Dictionary | 3848 | 3842 | -6 |
| Missing source | 5206 | 5206 | 0 |

## Medical Dictionary subsystem (2026-07-09) ✅

**Independent terminology database.** См. `medical_dictionary/metadata.json`.

| Файл | Schema | Entries | Loaded by |
|------|--------|--------:|-----------|
| drug_synonyms.json | synonym→canonical | 152 | dictionary.py |
| drug_atc.json | canonical→ATC | 0 (pending review) | dictionary.py |
| drug_groups.json | group→ATC prefix | 0 (pending review) | dictionary.py |
| route_dictionary.json | synonym→canonical | 41 | dictionary.py |
| unit_dictionary.json | synonym→canonical | 28 | dictionary.py |
| frequency_dictionary.json | pattern descriptors | 41 | none (reference) |
| duration_dictionary.json | pattern descriptors | 33 | none (reference) |
| pregnancy_dictionary.json | keyword patterns | — | none (reference) |
| renal_dictionary.json | keyword patterns | — | none (reference) |
| metadata.json | inventory | — | — |
| unknown_drugs.csv | ranked unknowns | 441 | — |
| dictionary_candidates.json | review candidates | 441 (all pending_review) | — |

**dictionary.py rewrite:** hardcoded dicts removed, loads via `medical_dictionary.loader`. Module-level names preserved (DRUG_SYNONYMS, ROUTE_SYNONYMS, UNIT_NORMALIZATION + new DRUG_ATC, DRUG_GROUPS). Class logic unchanged. No parser logic changes.

**Measured (STEP 5, no regression):** PASS 1039, REVIEW 443, REJECT 1193, confidence 0.7188 — identical to pre-refactor.

**Тесты:** 823/823 medical_normalizer (+20 loader tests). Pipeline 55 pass / 1 pre-existing fail (extraction, unrelated).

**Review policy:** never auto-accept. All 441 candidates `pending_review`. Человек ревьюит → accepted/rejected → entries в drug_synonyms.json / drug_atc.json.

## Оставшиеся задачи (приоритет пересмотрен per measured results)

### Critical (REVIEW↓ + PASS↑, low cost) — next
1. **DRUG_SYNONYMS expansion** (~60 synonyms) — REVIEW 443→~5-50, 438 drug-only flippable → PASS
2. **DRUG_ATC mapping** (~75 drugs → ATC codes) — ATC 0%→~80%, confidence↑

### High (REJECT↓, high cost)
3. **LLM re-extraction** (improve prompt, re-run 294 PDF) — 961 LLM-only REJECT, единственный путь к REJECT 25%

### Medium/Low
4. Remaining parser edge cases (118 parser-flippable REJECT, diminishing returns)
5. Drug groups handling (фторхинолоны → ATC group)
6. Combination drug normalization ([...] brackets)
7. Typo correction
8. Real LLM validation (replace mock, 130 IDs)
9. Golden case tests (app)
10. PostgreSQL migration (for >10k)
11. Multiprocessing (for >50k)
12. CI/CD pipeline
