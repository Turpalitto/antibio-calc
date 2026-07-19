# RC-030 / C7 Part III — Review Task Model and Evidence Completeness Gate

## Task record schema (Phase 4)

Every field the spec requires is present: `review_task_schema_version`, `review_batch_id` (assigned in Part IV), `queue_category`, `priority`, `unit_id` (= `evidence_hash`), `validation_unit_schema_version`, `regimen_id`, `regimen_version`, `source_packet_hash`, `PDF_hash`, `source_pdf_relative_path`, `page`, `exact_quote`, `sentence_context`, `paragraph_context`, `table_context`, `antibiotic`, `diagnosis`, `route`, `frequency`, `duration`, `structured_scalar`, `structured_unit`, `source_range_text`, `source_dose_min`, `source_dose_max`, `source_unit_signature`, `structured_unit_signature`, `risk_flags`, `deterministic_candidate`, `deterministic_classification`, `comparison_metadata`, `owner_verdict` (absent/`null`), `owner_note` (absent/`null`).

`sentence_context`/`paragraph_context` extracted live from the real PDF page text (via the already-tested `pdf_evidence.expand_context`, 80-char and 350-char windows respectively) — not reused from any prior artifact.

`deterministic_candidate`, `deterministic_classification`, and `comparison_metadata` are present in this build artifact (`generated/rc030_c7/review_tasks_ready.json`) for governance/audit purposes only — Part V Phase 9 strips them before anything reaches the owner-facing HTML. **This build artifact itself is never shown to the owner.**

## Evidence completeness gate (Phase 5)

Every one of the 113 unique tasks checked against: PDF exists, PDF hash matches `CORPUS_MANIFEST.json`, page exists, quote found on page (via the C6.8-hardened `find_quote_in_page_text`, including the hyphen-linewrap fix), antibiotic evidence exists, range evidence exists where applicable, no personal absolute paths (all paths are repository-relative filenames, no `C:\Users\...`), no missing validation identity, no duplicate task identity (0 duplicates, re-verified independently at this stage), no preloaded owner verdict.

## Result

**113/113 `READY_FOR_OWNER_REVIEW`. 0 blocked.**

This is a real, direct consequence of the C6.7/C6.8 audits already having removed every record with a source-evidence problem from the candidate pool before it ever reached a C6.8 queue (the 2 source-quote defects were fixed in C6.8-B; the PDF hash re-verification was completed in C6.7; every queued record already passed the same underlying checks this gate re-runs). No blocked-evidence report was needed — `generated/rc030_c7/review_tasks_blocked.json` exists and is empty by construction, not omitted.

`owner_verdict`/`owner_note` confirmed `null` (absent) on all 113 tasks; all 113 `unit_id` values confirmed unique.
