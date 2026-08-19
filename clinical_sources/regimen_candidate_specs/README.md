# Regimen candidate source specs

Each JSON file binds one current rubricator revision to an exact official PDF
SHA-256 and declares only extraction coordinates/diagnosis metadata. Clinical
dose values are not copied into the spec; they must be extracted from the PDF.
The spec also pins the canonical candidate-payload SHA-256, so a local JSON
edit or extraction-code drift fails closed before physician attestation.

Build a local review artifact and queued Versioned-KB objects:

```powershell
.venv\Scripts\python.exe -m src.pipeline.extraction.regimen_candidates `
  --spec clinical_sources\regimen_candidate_specs\314_3.json `
  --pdf tmp\pdfs\aom\official_314.pdf `
  --output .local\personal_physician\extracted_candidates\314_3.json `
  --kb .local\personal_physician\extracted_candidates\kb.sqlite
```

Hash mismatch, missing pages, ambiguous semantics or unsupported calculator
forms must fail closed. Adding a spec never attests or approves a regimen.
