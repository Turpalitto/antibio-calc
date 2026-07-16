# REGIMEN 5574 VERIFICATION REPORT

**Auto-generated from a verified evidence packet. Do not hand-edit this file — regenerate it from the packet instead.**

Packet hash: `a559ab5eb54028ca44ad0a4de81fb739804fa46728eddf0481c956cb35f39fe0`
Generated at: 2026-07-15T20:12:02Z

## assembled_regimens:5574:1 — DATABASE_QUERY

[DATABASE QUERY — assembled_regimens.sqlite — verified 2026-07-15T20:12:02Z]
Source: `assembled_regimens.sqlite` (SHA-256 `9f505d08428cd284...`)
Retrieval: `SELECT * FROM assembled_regimens WHERE regimen_id='5574'`

```
{
  "age_group": "child",
  "antibiotic": "джозамицин",
  "approved_at": "",
  "approved_by": "",
  "assembly_ruleset_version": "p5.3-v1",
  "confidence": 0.8544,
  "contraindications": "[]",
  "created_at": "2026-07-15T00:00:00Z",
  "diagnosis": "Урогенитальные заболевания, вызванные M. genitalium, у детей с массой тела менее 45 кг",
  "dose": 50.0,
  "duration_recommended": 10.0,
  "evidence_level": "UNKNOWN",
  "field_provenance": "[[\"antibiotic\", {\"source_object_id\": \"5574\", \"source_document\": \"Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf\", \"source_location\": \"page 16\", \"source_store\": \"normalized_regimens\", \"scope\": \"regimen\"}], [\"dose\", {\"source_object_id\": \"5574\", \"source_document\": \"Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf\", \"source_location\": \"page 16\", \"source_store\": \"normalized_regimens\", \"scope\": \"regimen\"}], [\"route\", {\"source_object_id\": \"5574\", \"source_document\": \"Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf\", \"source_location\": \"page 16\", \"source_store\": \"normalized_regimens\", \"scope\": \"regimen\"}], [\"frequency\", {\"source_object_id\": \"5574\", \"source_document\": \"Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf\", \"source_location\": \"page 16\", \"source_store\": \"normalized_regimens\", \"scope\": \"regimen\"}], [\"duration_recommended\", {\"source_object_id\": \"5574\", \"source_document\": \"Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf\", \"source_location\": \"page 16\", \"source_store\": \"normalized_regimens\", \"scope\": \"regimen\"}]]",
  "frequency": 2.0,
  "guideline_id": "1126",
  "icd_mkb": "A63.8",
  "needs_review_reasons": "[\"no_kb_p44_enrichment_for_guideline_1126\"]",
  "pregnancy": null,
  "regimen_id": "5574",
  "renal_adjustment": 0,
  "review_status": "pending",
  "route": "oral",
  "snapshot_version": "kb_p44-final-20260714",
  "source_page": "16",
  "source_pdf": "Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf",
  "source_quote": "Рекомендовано  для лечения детей с массой тела менее 45 кг назначать перорально\nджозамицин** 50 мг на кг массы тела в сутки, разделённые на 2 приема, в течение 10\nдней",
  "status": "REVIEW_REQUIRED",
  "therapy_line": "first",
  "unit": "mg/kg",
  "validation_verdict": "REVIEW",
  "version": 1
}
```

## normalized_regimens:5574 — DATABASE_QUERY

[DATABASE QUERY — normalized_regimens.sqlite — verified 2026-07-15T20:12:02Z]
Source: `normalized_regimens.sqlite` (SHA-256 `c7b67354b0723ad5...`)
Retrieval: `SELECT * FROM normalized_regimens WHERE regimen_id='5574'`

```
{
  "adult": 0,
  "approved": 0,
  "atc_code": "",
  "child": 1,
  "created_at": "2026-07-10T07:37:40Z",
  "diagnosis": "Урогенитальные заболевания, вызванные M. genitalium, у детей с массой тела менее 45 кг",
  "dose": 50.0,
  "dose_unit": "mg/kg",
  "drug_components": "[]",
  "drug_normalized": "джозамицин",
  "drug_original": "джозамицин**",
  "duration_max": 10.0,
  "duration_min": 10.0,
  "duration_recommended": 10.0,
  "field_confidence": "{\"drug\": 0.6, \"dose\": 0.9, \"route\": 0.9, \"frequency\": 0.9, \"duration\": 0.85, \"population\": 0.9, \"therapy_line\": 0.99, \"atc_code\": 0.0, \"pregnancy\": 0.0, \"renal_adjustment\": 0.0}",
  "frequency": 2.0,
  "guideline_id": "1126",
  "manual_notes": "",
  "manual_override": "",
  "mkb": "A63.8",
  "normalizer_version": "1.0.0",
  "overall_confidence": 0.8544,
  "parser_confidence": null,
  "population": "child",
  "pregnancy": null,
  "regimen_id": "5574",
  "renal_adjustment": 0,
  "review_date": "",
  "review_status": "pending",
  "reviewed_by": "",
  "route": "oral",
  "schema_version": "1.0.0",
  "source_page": "16",
  "source_pdf": "Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf",
  "source_quote": "Рекомендовано  для лечения детей с массой тела менее 45 кг назначать перорально\nджозамицин** 50 мг на кг массы тела в сутки, разделённые на 2 приема, в течение 10\nдней",
  "therapy_line": "first",
  "updated_at": "2026-07-10T07:37:40Z",
  "validation_errors": 0,
  "validation_issues": "[{\"code\": \"DRUG_UNKNOWN\", \"severity\": \"review\", \"message\": \"Drug 'джозамицин' is not in the known drug dictionary.\", \"field\": \"drug\", \"suggested_fix\": null}]",
  "validation_reviews": 1,
  "validation_verdict": "REVIEW",
  "validation_warnings": 0
}
```

## Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf:page16 — SOURCE_PDF_EXTRACT

[PDF EXTRACT — Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf — verified 2026-07-15T20:12:02Z]
Source: `Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf` (SHA-256 `b8a525c56b01e636...`)
Retrieval: `fitz.open(path).load_page(15).get_text()`

```
Рекомендовано  для лечения детей с массой тела менее 45 кг назначать перорально
джозамицин** 50 мг на кг массы тела в сутки, разделённые на 2 приема, в течение 10
дней[66,67].
Уровень убедительности рекомендаций С(уровень достоверности доказательств 5)
Комментарии:  Лечение детей с массой тела более 45 кг проводится в соответствии со
схемами назначения у взрослых с учетом противопоказаний.  
3.2 Хирургическое лечение
Не применяется.
3.3 Иное лечение
Диетотерапия не применяется.
Обезболивание не применяется.

```

## assembled-vs-normalized-consistency — GENERATED_CALCULATION

[COMPUTED — evidence_model.py comparison]
Source: `evidence_model.py comparison` (SHA-256 `f9b670f9abda5be0...`)
Retrieval: `row['antibiotic']==nrow['drug_normalized']; row['dose']==nrow['dose'] and row['unit']==nrow['dose_unit']`

```
{
  "assembled_antibiotic": "джозамицин",
  "normalized_drug_normalized": "джозамицин",
  "drug_name_consistent": true,
  "assembled_dose": [
    50.0,
    "mg/kg"
  ],
  "normalized_dose": [
    50.0,
    "mg/kg"
  ],
  "dose_consistent": true
}
```
