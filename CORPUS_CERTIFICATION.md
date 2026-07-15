# P5.6 Corpus Certification

Source: `CORPUS_MANIFEST.json`, SHA-256 каждого PDF.

- antibiotic-flagged/selected union: 250 unique PDF;
- INCLUDED: 192;
- REVIEW_REQUIRED: 58;
- silent/unclassified: 0;
- автоматические exclusions: 0.

192 — текущий curated P4.4 production corpus. 58 документов имеют metadata antibiotic signal, но отсутствуют в builder selection; для каждого создан `CorpusExclusionDecision`. До врачебного решения они не включаются и не исключаются автоматически.

Verdict: classification completeness PASS; clinical inclusion certification WARNING до 58 human decisions.
