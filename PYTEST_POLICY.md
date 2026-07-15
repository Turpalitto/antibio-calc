# ANTIBIO Pytest Policy

Каноническая команда: `python -m pytest` из Git root.

Законы:

- broad skip/ignore запрещён;
- xfail обязан иметь конкретную причину и не может скрывать safety regression;
- unit tests могут изолировать external provider boundary, но benchmarks/corpus/production validation используют только real artifacts;
- markers: unit, integration, corpus, ml, slow, clinical, golden, security;
- tests не требуют live credentials по умолчанию;
- credential-required tests должны иметь отдельный marker и явный fail/skip contract;
- canonical collection обязана завершаться без import errors.
