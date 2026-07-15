# NEXT TASK

## Задача: Запуск LLM извлечения схем лечения (extract_raw)

**Статус:** Запланировано
**Приоритет:** Высокий

---

## Почему нужна

Классификация выполнена: 506 Level A+B PDF готовы к LLM-извлечению. Без этого шага knowledge_base.json не будет сгенерирован.

## Что сделать

1. Запустить `main.py extract_raw` — DeepSeek V4 Pro извлекает схемы из Level A+B PDF (506 шт.)
2. Дождаться завершения (~30-60 мин, 3 concurrent запроса)
3. Проверить extraction_raw.json

## Команды

```powershell
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$env:PYTHONPATH = "C:\ANTIBIO\src\pipeline"
Set-Location -LiteralPath "C:\clinrec_downloader"
& $py main.py extract_raw
```

## Критерии готовности

- [ ] extraction_raw.json создан
- [ ] Содержит извлечённые схемы с source-полями
- [ ] Все 47 тестов проходят
