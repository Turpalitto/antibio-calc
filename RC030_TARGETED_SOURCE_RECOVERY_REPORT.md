# RC030_TARGETED_SOURCE_RECOVERY_REPORT.md

Status: RC-030 Evidence Validation, Phase 7. **Corrected 2026-07-16 — see the "Correction" section
below. The original version of this report contained a fabricated data comparison and a false
conclusion (filed as RC-031). RC-031 has been retracted; see `ROOT_CAUSE_REGISTER.md`.**

## Tool availability check (unchanged, still accurate)

```
fitz (PyMuPDF)      AVAILABLE
mineru               AVAILABLE
docling               AVAILABLE
doclayout_yolo        AVAILABLE
table_transformer     AVAILABLE
rapidtable            NOT AVAILABLE (module not installed in this environment)
```

Source PDF corpus is accessible at `C:/clinrec_downloader/downloads_active/` and
`downloads_antibiotics/` (confirmed present, read-only inspection only).

## What was actually done (the PyMuPDF part — real, and correct)

`assembled_regimens.source_pdf` for regimen 5574 does not match any file on disk under either corpus
directory by exact name — a genuine filename-tracking inconsistency, unrelated to drug attribution
(see below). Two candidate documents were checked with PyMuPDF (read-only text extraction) to find the
real source:

1. `Хламидийная инфекция.pdf`, page 16 — ruled out: entirely about lab diagnostics for *Chlamydia
   trachomatis*, no dose information.
2. `Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf`, page 16 — confirmed as the real
   source, page 16 reads: `"Рекомендовано для лечения детей с массой тела менее 45 кг назначать
   перорально джозамицин** 50 мг на кг массы тела в сутки, разделённые на 2 приема, в течение 10
   дней[66,67]."`

This part of the investigation was genuine and the PDF text quoted above is real.

## Correction: the reported "finding" was fabricated, not measured

The original version of this report then presented a comparison against
`assembled_regimens.source_quote for regimen 5574`, showing it beginning `"Азитромицин** 50 мг на кг
массы тела..."`. **That string was not copied from the database — it was written by hand and does not
match the real row.** A direct, live, hash-verified query of `assembled_regimens.sqlite` for regimen
5574 returns:

```
antibiotic: джозамицин
source_pdf: Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf   (page 16)
source_quote: "Рекомендовано  для лечения детей с массой тела менее 45 кг назначать перорально
               джозамицин** 50 мг на кг массы тела в сутки, разделённые на 2 приема, в течение 10
               дней"
```

This **matches the real PDF text exactly** (module-for-module, modulo whitespace). There is no
mismatch. `normalized_regimens.sqlite` (the upstream store, `backups/p5_6_baseline_20260715/`) was
independently checked too and also correctly says `drug_original="джозамицин**"`,
`drug_normalized="джозамицин"` for `regimen_id=5574`. Every layer of the pipeline — extraction,
normalization, assembly, and the final table — agrees. **Regimen 5574 has no drug-attribution
defect.**

## Root cause of the false finding

Earlier in this work (the original P5.6 sandbox build), a browser-based demo session queried the
snapshot for a diagnosis/antibiotic pair and found a *different* regimen — a genuine Азитромицин
10 mg/kg case — and used it as a "worked example" without recording its actual `regimen_id`. When
later writing follow-up reports (`DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md`'s "worked example",
`RC030_12CASE_REVALIDATION.md`'s "regimen 5574" section, this report), the label "regimen 5574" was
applied to that Азитромицин example by mistake, and a "verbatim" quote was constructed by hand to
match rather than copied from the live database. The likely real identity of the original Азитромицин
10 mg/kg example is `regimen_id=6138` (matching diagnosis code `A02.0, A02.1, A02.2, A02.8, A02.9`
recorded at the time) — not confirmed with full certainty, since the original session didn't log the
ID explicitly, but the diagnosis code match is a strong signal. This is a **citation/transcription
error in my own reporting**, not a data-pipeline defect.

## Disposition

**RC-031 is retracted** — see `ROOT_CAUSE_REGISTER.md`. No drug-name misattribution exists in
regimen 5574. This report is preserved (corrected, not deleted) as a record of both the genuine PDF
cross-verification work and the reporting error that followed it, per the same fail-closed,
show-your-work standard this validation exercise is supposed to uphold for the data itself.
