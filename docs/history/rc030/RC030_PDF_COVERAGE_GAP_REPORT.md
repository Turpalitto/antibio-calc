# RC-030 PDF Coverage Gap — Report (corrected)

## Corrected finding

The prior turn's "65% coverage" claim was based on searching **only** `C:\clinrec_downloader\downloads_active\`. Searching the full set of approved local storage locations under the same trust boundary (`downloads_active`, `downloads_all`, `downloads_antibiotics`, `downloads_other`, `archive_no_antibiotics`, `archive_review`, `quarantine` — all siblings under `C:\clinrec_downloader`, the same `source_root` recorded in `CORPUS_MANIFEST.json`) finds:

- **193/193 distinct referenced PDFs (100%) are available somewhere in approved storage.**
- **0 hash mismatches** against `CORPUS_MANIFEST.json`'s recorded SHA-256 for every file checked.
- Of the 68 not present in `downloads_active`: 66 found in `downloads_antibiotics` + `archive_review` (both locations), 1 in `archive_no_antibiotics` + `downloads_other`, 1 in `archive_review` + `downloads_other`.

**No PDF was downloaded automatically.** All searches were read-only lookups within directories that already existed locally.

## Classification (per record)

- `AVAILABLE_PRIMARY`: present in `downloads_active` (the location used by prior queue-building) — 125/193.
- `AVAILABLE_DUPLICATE`: not in `downloads_active` but present (hash-matched) elsewhere in approved storage — 68/193.
- `HASH_MISMATCH`: 0.
- `OWNER_REDOWNLOAD_REQUIRED`: 0.

Full per-file detail: `RC030_MISSING_PDF_MANIFEST.json` (despite the filename, it now records that nothing is actually missing — kept the filename for traceability with the mission's required deliverable name rather than renaming mid-task).

## Consequence for prior turns' work

The 60-record owner pilot queue, the 20-record max-dose queue, and the 12-page multi-engine recovery pilot were all built searching only `downloads_active`, so they under-used the available pool (e.g. the max-dose queue had 35/104 candidates to choose from when it could have had up to 104/104). **Their existing selections remain valid** — nothing in them is wrong — but a future queue-refresh could draw from the full corpus without any PDF-availability constraint at all, since coverage is effectively complete.

## Recommendation

Update any future page/record selection scripts to search the full `C:\clinrec_downloader\{downloads_active,downloads_all,downloads_antibiotics,downloads_other,archive_no_antibiotics,archive_review,quarantine}` set, not just `downloads_active`, to avoid re-deriving this same "missing" false alarm.
