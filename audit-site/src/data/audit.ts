// Данные аудита репозитория Turpalitto/antibio-calc
// Собраны на основе публичного кода, README, git-истории и ~360 markdown-отчётов
// самого репозитория (по состоянию на коммит 0cf8e33, 2026-09-29).

export const repo = {
  owner: "Turpalitto",
  name: "antibio-calc",
  url: "https://github.com/Turpalitto/antibio-calc",
  auditDate: "2026-09-29",
  description:
    "Клинический калькулятор доз антибиотиков + пайплайн извлечения знаний из клинических рекомендаций Минздрава РФ (LLM-экстракция, нормализация, decision engine).",
};

export const quickStats = [
  { label: "Строк Python", value: "75 515", note: "358 файлов" },
  { label: "Строк документации (.md)", value: "46 561", note: "360 файлов" },
  { label: "Строк HTML-калькулятора", value: "19 306", note: "включая шаблон" },
  { label: "Коммитов", value: "54", note: "07.07 – 29.09.2026 (~85 дней)" },
  { label: "Тестов (заявлено)", value: "1 373", note: "1371 pass / 1 skip / 1 xfail" },
  { label: "REJECT в валидации данных", value: "55.1%", note: "1475 из 2675 схем" },
];

export const timeline = [
  { date: "2026-07-07", event: "Первый коммит. Старт пайплайна извлечения КР Минздрава." },
  { date: "2026-07-09", event: "Medical Normalizer объявлен COMPLETE: 726 тестов, 99.9% coverage." },
  { date: "2026-07-15", event: "Обнаружена утечка API-ключей провайдеров LLM; запущен P5.6 Production Recovery." },
  { date: "2026-07-15", event: "Найдено расхождение источников знаний: движок не читает kb_p44.db (EAR-1, RC-019)." },
  { date: "2026-09-02", event: "Покрытие доведено до 120 нозологий / 48 препаратов, но 119 записей заблокированы fail-closed гейтом." },
  { date: "2026-09-29", event: "Последний коммит. Review Workbench: очередь 9153 задач, 0 одобренных врачом объектов. P6 заблокирован." },
];

export const architectureComponents = [
  {
    name: "Pipeline (Python 3.12)",
    detail: "Скачивание PDF с apicr.minzdrav.gov.ru → классификация A/B/C/D → LLM-извлечение схем (DeepSeek) → валидация → knowledge_base.json + SQLite.",
  },
  {
    name: "Medical Normalizer",
    detail: "13 модулей, приводит «сырые» схемы к структурированным объектам с confidence-оценкой. Изолирован, детерминирован, 99.9% покрытия тестами.",
  },
  {
    name: "Clinical Engine (FastAPI)",
    detail: "API v1/v2, читает normalized_regimens.sqlite. Работает только на loopback (127.0.0.1), режим 'personal physician'.",
  },
  {
    name: "antibiotic_calc.html",
    detail: "Итоговое offline PWA-приложение (715 КБ). База данных встраивается в HTML на этапе сборки (db/build_html.py), 3230 строк шаблона.",
  },
  {
    name: "Review Workbench (P5.6)",
    detail: "Локальный сервис ревью врачей: append-only очередь, immutable snapshots, two-review + адъюдикация. Пока полностью отключён от Clinical Engine.",
  },
];

export const architectureRisks = [
  {
    id: "EAR-1",
    severity: "critical",
    title: "Два несвязанных источника знаний",
    detail:
      "P4.4-пайплайн пишет kb_p44.db (с полной провенантностью — ссылками на страницу/таблицу PDF), но Clinical Engine читает совершенно другой файл — normalized_regimens.sqlite. Гарантии прослеживаемости рекомендаций 'до документа Минздрава' не доходят до реального пути обслуживания ответа пользователю.",
  },
  {
    id: "EAR-2",
    severity: "high",
    title: "Тройное дублирование справочника препаратов",
    detail:
      "Идентичность лекарства хранится в трёх независимых местах (DRUG_SYNONYMS в pipeline, БД normalizer, объекты Medication в kb_p44) без единой онтологии — риск рассинхронизации.",
  },
  {
    id: "EAR-3",
    severity: "medium",
    title: "Роутинг диагнозов опирается на черновой индекс",
    detail:
      "diagnosis_index помечен в коде как AUTO_GENERATED_DRAFT / PARTIALLY_CURATED. Ошибочный роутинг молча выбирает не ту клиническую рекомендацию.",
  },
  {
    id: "EAR-5",
    severity: "high",
    title: "Хранилище не готово к росту нагрузки",
    detail:
      "Поиск поkb делается через SQL LIKE '%...%' по сериализованному JSON — O(n) skan. Пути захардкожены (C:\\clinrec_downloader), нет модели конкурентного доступа — архитектура рассчитана на локальный батч-пайплайн, а не на сервис.",
  },
  {
    id: "EAR-6",
    severity: "medium",
    title: "Врачебное ревью — реальное узкое место, для него нет инструмента",
    detail:
      "Golden Dataset (500+ кейсов), двойное ревью и адъюдикация зависят от часов врачей, а workbench для этого появился только в P5.6 и остаётся не подключён к движку.",
  },
];

export const securityFindings = [
  {
    title: "Инцидент с утечкой API-ключей",
    severity: "high",
    status: "Устранено (по самоатттестации владельца)",
    detail:
      "Отчёты репозитория фиксируют факт исторической утечки provider-ключей (Anthropic, DeepSeek, OpenRouter, OpenAI, Gemini). Сканирование текущего дерева и всей git-истории (6 коммитов на момент проверки) ключей не находит, .env корректно в .gitignore. Но факт ротации на стороне провайдеров подтверждён только текстовым заявлением владельца ('ROTATED_CONFIRMED_BY_OWNER_ATTESTATION'), а не независимой проверкой — это не техническое доказательство.",
  },
  {
    title: "server.js: защита от path traversal и loopback-only",
    severity: "positive",
    status: "Хорошая практика",
    detail:
      "Запросы с '..' (в т.ч. percent-encoded) отклоняются, разрешён строгий allowlist расширений, сервер слушает 127.0.0.1 по умолчанию, проксируемые /v1 /v2 запросы никогда не кешируются и не подменяются HTML-оболочкой при недоступности движка (502 вместо ложного ответа).",
  },
  {
    title: "Content-Security-Policy задан явно",
    severity: "positive",
    status: "Хорошая практика",
    detail:
      "default-src 'self', ограниченный список внешних источников (Tailwind CDN, Google Fonts, cdnjs), object-src 'none', form-action 'self'. Минус — 'unsafe-inline' для script/style, т.к. вся логика калькулятора инлайновая.",
  },
  {
    title: "Секреты через переменные окружения, без хардкода",
    severity: "positive",
    status: "Хорошая практика",
    detail:
      "src/pipeline/config.py читает ключи из os.environ без дефолтных значений; при отсутствии обязательных ключей выбрасывается RuntimeError с именами переменных, но без значений. Есть .gitleaks.toml с кастомным правилом на провайдерские ключи.",
  },
  {
    title: "Отсутствует CI/CD",
    severity: "medium",
    status: "Не реализовано",
    detail:
      "Каталог .github/workflows отсутствует. Проверки тестов, gitleaks и линтеров выполняются вручную (агентом), не гарантированы на каждый push/PR — при работе с медицинскими данными это значимый пробел процесса.",
  },
  {
    title: "Лицензия UNLICENSED в публичном репозитории",
    severity: "low",
    status: "Требует внимания",
    detail:
      "package.json объявляет license: UNLICENSED, при этом репозиторий публичный на GitHub. Юридический статус использования кода третьими лицами не определён.",
  },
];

// Данные для донат-чарта верификации регименов (quality_report.md)
export const validationVerdicts = [
  { label: "REJECT", value: 1475, pct: 55.1, color: "#ef4444" },
  { label: "PASS", value: 880, pct: 32.9, color: "#22c55e" },
  { label: "REVIEW", value: 320, pct: 12.0, color: "#f59e0b" },
];

export const fieldCompleteness = [
  { field: "Drug (препарат)", pct: 100 },
  { field: "Dose (доза)", pct: 71.1 },
  { field: "Route (путь введения)", pct: 65.1 },
  { field: "Frequency (частота)", pct: 56.6 },
  { field: "Duration (длительность)", pct: 41.0 },
  { field: "Therapy line (линия терапии)", pct: 60.1 },
  { field: "ATC-код", pct: 0 },
  { field: "Renal adjustment", pct: 2.8 },
  { field: "Pregnancy", pct: 2.6 },
];

export const calculatorCoverage = {
  totalNosologies: 120,
  unblocked: 1,
  blocked: 119,
  drugs: 48,
  note: "Единственная полностью разблокированная (просчитываемая) нозология — острый средний отит у детей (aom_child, КР 314_3). Остальные 119 показываются как справочные, но расчёт дозы заблокирован fail-closed гейтом source_verification_status = SOURCE_SPEC_MISSING до подтверждения врачом.",
};

export const testingStats = [
  { label: "Medical Normalizer — тестов", value: "726–1155" },
  { label: "Medical Normalizer — покрытие", value: "≈99.9%" },
  { label: "Канонический pytest suite", value: "1373 собрано" },
  { label: "Результат последнего прогона", value: "1371 pass / 1 skip / 1 xfail" },
  { label: "Golden Dataset (клинические эталоны)", value: "0/7 PASS на момент аудита P5.6" },
  { label: "Тесты JS-логики калькулятора", value: "не обнаружены (только validate_db.js на схему)" },
];

export const docBloat = {
  mdFiles: 360,
  mdLines: 46561,
  pyLines: 75515,
  ratio: (46561 / 75515).toFixed(2),
  biggestFiles: [
    { name: "AI_LOG.md", size: "281 КБ" },
    { name: "DECISIONS.md", size: "143 КБ" },
    { name: "CORPUS_MANIFEST.json", size: "206 КБ" },
    { name: "ANTIBIO_ROADMAP_P5_P10.md", size: "50 КБ" },
    { name: "CLINICAL_VALIDATION_FRAMEWORK.md", size: "39 КБ" },
  ],
};

export const riskRegister = [
  {
    id: "RC-019 / EAR-1",
    area: "Архитектура",
    severity: "critical",
    title: "Провенантность рекомендаций не доходит до пользователя",
    impact: "Обещание «каждая рекомендация прослеживается до документа Минздрава» не выполняется в реально обслуживаемом пути.",
  },
  {
    id: "SEC-1",
    area: "Безопасность",
    severity: "high",
    title: "Ротация скомпрометированных ключей не подтверждена независимо",
    impact: "Организационный риск: единственное доказательство — текстовое заявление владельца.",
  },
  {
    id: "DATA-1",
    area: "Качество данных",
    severity: "critical",
    title: "55% извлечённых схем дозирования не проходят автоматическую валидацию",
    impact: "Прямой риск для конечного медицинского применения, если такие данные попадут в продакшен без ревью.",
  },
  {
    id: "DATA-2",
    area: "Качество данных",
    severity: "high",
    title: "Только 1 из 120 нозологий реально считает дозу",
    impact: "Продукт в текущем виде — преимущественно справочник, а не рабочий калькулятор, несмотря на маркетинговое описание.",
  },
  {
    id: "PROC-1",
    area: "Процесс",
    severity: "medium",
    title: "Документация в 0.62 раза больше объёма кода",
    impact: "360 markdown-файлов усложняют онбординг, увеличивают риск противоречий между документами и реальным кодом.",
  },
  {
    id: "PROC-2",
    area: "Процесс",
    severity: "medium",
    title: "Нет CI/CD",
    impact: "Тесты/секрет-сканер не блокируют мёржи автоматически, качество зависит от дисциплины одного разработчика/агента.",
  },
  {
    id: "EAR-5",
    area: "Архитектура",
    severity: "high",
    title: "SQLite + LIKE-сканирование не переживёт рост нагрузки",
    impact: "При переходе к сервисной модели (P7) потребуется полная замена слоя хранения.",
  },
  {
    id: "LEGAL-1",
    area: "Лицензирование",
    severity: "low",
    title: "UNLICENSED в публичном репозитории",
    impact: "Неопределённые условия использования кода third-party.",
  },
];

export const recommendations = [
  {
    title: "Свести источники знаний в один (закрыть RC-019)",
    detail:
      "Прежде чем добавлять новые нозологии, перевести Clinical Engine на kb_p44.db или наоборот — иначе провенантность и дальше будет фиктивной для пользователя.",
  },
  {
    title: "Внедрить CI/CD",
    detail:
      "GitHub Actions: pytest + coverage gate, gitleaks/secret-scan, eslint/ruff, сборка antibiotic_calc.html — на каждый PR, без ручного контроля.",
  },
  {
    title: "Независимая проверка ротации ключей",
    detail:
      "Заменить самоатттестацию владельца on-chain/логами провайдеров (audit log с датой revoke) либо привлечь стороннего security-ревьюера.",
  },
  {
    title: "Сократить документационный долг",
    detail:
      "Архивировать исторические отчёты (P5.x, RC-*, EAR-*) в отдельную ветку/wiki, оставить в корне только 5–7 «живых» файлов (README, ARCHITECTURE, SECURITY, CONTRIBUTING, CHANGELOG).",
  },
  {
    title: "Инвестировать в пропускную способность врачебного ревью",
    detail:
      "Именно она — реальное узкое место (EAR-6): 9153 задачи в очереди, 0 одобрено. Нужны UX для быстрой адъюдикации и привлечение нескольких рецензентов.",
  },
  {
    title: "Покрыть тестами JS-логику калькулятора",
    detail:
      "Сейчас вся арифметика доз находится в inline-скрипте HTML без автоматических unit-тестов на JS-стороне — только backend/Python тестируется полноценно.",
  },
  {
    title: "Явный медицинский дисклеймер и версия данных на каждом экране расчёта",
    detail:
      "Учитывая 55% REJECT-показатель в исходных данных и fail-closed блокировку 119/120 нозологий, пользователь-врач должен на интерфейсе видеть статус верификации конкретной схемы.",
  },
  {
    title: "Определить лицензию",
    detail:
      "Заменить UNLICENSED на явную лицензию (или явное 'All rights reserved' в README), особенно поскольку репозиторий публичный и содержит медицинский контент.",
  },
];

export const scorecard = [
  { category: "Архитектура", grade: "C+", comment: "Хорошее разделение слоёв внутри normalizer, но два несвязанных хранилища знаний — фундаментальный порок." },
  { category: "Безопасность", grade: "B-", comment: "Грамотный server.js и работа с секретами сейчас, но был реальный инцидент утечки ключей, подтверждённый только на словах." },
  { category: "Качество данных", grade: "D+", comment: "55% REJECT, 0% ATC-кодов, только 1/120 нозологий реально считает дозу." },
  { category: "Тестирование", grade: "B+", comment: "Отличное покрытие Python-модулей (≈99.9%), но нет тестов JS-калькулятора и нет CI, запускающего их автоматически." },
  { category: "Процесс / документация", grade: "C-", comment: "360 md-файлов и постоянные 'NOT COMPLETE' вердикты — процесс регулярно опережает реальный результат." },
  { category: "Готовность к продакшену", grade: "D", comment: "Собственные документы проекта (P5.6 Recovery Report) прямо называют его 'NOT COMPLETE', P6 заблокирован владельцем же." },
];

export const overallVerdict = {
  grade: "C-",
  label: "В активной разработке, не готов к клиническому использованию",
};
