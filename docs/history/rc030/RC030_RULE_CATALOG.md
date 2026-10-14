# RC030_RULE_CATALOG.md

Status: RC-030 Evidence Validation, Phase 2. Exhaustive catalog of every rule in
`dose_verification_sandbox/semantics_parser.py` (hash at time of writing:
`c516a86be05fdf10ce3904a0d92563efb117196b74affe0539bf058cec00b778`, see `RC030_VALIDATION_BASELINE.md`).
No semantic assignment in the code relies on a rule not listed here.

## Global mechanism (applies to every rule below)

1. The `dose` number is located as a literal substring inside `source_quote` (tries integer,
   `g`-format, 1/2-decimal-place, and comma-decimal variants).
2. A **text window** is taken: 30 characters before the matched token, 90 characters after
   (`WINDOW_CHARS = 90`, pre-window = `WINDOW_CHARS // 3 = 30`). This window, not the full quote, is
   what every rule below searches.
3. All rules run against the window; **proximity** (nearest match to the dose token's position) is
   the tie-breaker when more than one rule fires (Rule P — see below).

No rule ever searches outside this window. No rule ever considers a second `source_quote` from a
different row.

---

## R1 — FREQ_MULTIPLIER (per-dose signal)

```regex
(?:\d+(?:[.,]\d+)?|один|одна|два|две|три|четыре|пять|шесть|дважды|трижды)
  \s*раз(?:а|ов)?\s+в\s+(?:сутки|день)
|(?:once|twice|three times|four times)\s+(?:a|per)\s+day
|\d+\s*(?:x|×)\s*/?\s*day
```
- **Meaning if matched**: the dose number is a single-administration amount, repeated N times/day.
- **Positive examples** (real, from corpus): `"2 раза в сутки"`, `"каждые...4 раза в сутки"`,
  `"два раза в день"` (spelled-out), `"1 раз в сутки"`.
- **Negative examples**: `"1 раз в месяц"` (month, not day — does not match, by design — only
  `сутки`/`день` are accepted, not `месяц`/`неделю`). `"3 раза"` alone without `"в сутки/день"` does
  not match (incomplete phrase, correctly rejected).
- **Case sensitivity**: none (`re.IGNORECASE`).
- **Known gap**: does not match `"раз в неделю"` (weekly) or `"раз в месяц"` (monthly) — regimens
  dosed weekly/monthly with this phrasing fall through to no-signal, not misclassified as daily.

## R2 — EVERY_N_HOURS (per-dose signal)

```regex
каждые\s+\d+(?:\s*-\s*\d+)?\s*ч(?:ас\w*)?|every\s+\d+\s*hours?
```
- **Meaning if matched**: administration-interval phrasing ⇒ per-administration dose.
- **Positive examples**: `"каждые 8 часов"`, `"каждые 12 ч"`, `"каждые 8-12 ч"`.
- **Negative examples**: `"через 8 часов"` (different preposition — does not match; a real gap, not
  tested against corpus frequency, could under-recognize some phrasings — conservative failure mode,
  i.e. falls through to no-signal rather than misfiring).

## R3 — PER_DOSE_NOUN (per-dose signal)

```regex
на\s+введени\w*|за\s+одно\s+введени\w*|разов\w*\s+доз\w*
|per\s+dose|per\s+administration|single\s+dose
```
- **Meaning if matched**: explicit per-administration noun phrase.
- **Positive examples**: `"на введение"`, `"разовая доза"`, `"разовые дозы"`.
- **Negative examples**: `"суточная доза, разделенная на 3 введения"` — this string DOES match
  `разов\w*\s+доз\w*`? No: the pattern requires "разов" immediately followed (after whitespace) by
  "доз" — "разделенная на 3 введения" does not contain "разов...доз" adjacency, so it does **not**
  match R3. It correctly falls under R5 (`суточная доза`, per-day) instead. Verified by inspection,
  not by an automated adjacency test — flagged as a Phase 4 sampling priority.

## R4 — PLAIN_PER_DAY (per-day signal)

```regex
/\s*сут(?:ки)?\b|\bв\s+сутки\b|суточн\w*\s+доз\w*|/\s*day\b|per\s+day
```
- **Meaning if matched**: the dose number is the daily total.
- **Positive examples**: `"/сут"`, `"мг/кг/сут"`, `"в сутки"`, `"суточная доза"`.
- **Precedence exception (Rule X1)**: any match of R4 whose character span **overlaps** an R1/R2/R3
  match is discarded before R4 is compared against R1/R2/R3 — this exists specifically because "N
  раз **в сутки**" contains the R4 substring "в сутки" as a strict subset of its own R1 match, which
  would otherwise self-conflict on every single R1 hit. See Phase 3 for verification this exception
  does not also swallow genuine independent per-day mentions that happen to sit near an unrelated R1
  match for a different drug.

## Rule P — PROXIMITY TIE-BREAK

When both an R1/R2/R3 (per-dose) match and a surviving R4 (per-day) match exist in the same window
(after Rule X1's overlap exclusion), the match whose span is **closer** (fewer characters) to the
dose token's anchor position wins. If both are equidistant, the result is
`AMBIGUOUS_CONFLICTING_SIGNAL` (never a coin-flip default).
- **Distance metric**: `0` if the anchor position falls inside the match span; otherwise the gap in
  characters between the anchor and the nearer edge of the match.
- **Known limitation** (documented, not fixed): for combination-drug alternatives where the frequency
  clause follows *two* numeric components (e.g. `"500 мг + 125 мг 3 раза в сутки или по 875 мг + 125
  мг 2 раза в сутки"`), Rule P can attribute the wrong alternative's R1 match if the character
  distance to the "wrong" one happens to be shorter than to the "right" one (see
  `DOSE_SEMANTICS_PARSER_SPEC.md`). Confirmed case: regimen 7620.

## Rule F1 — RESOLVED_BY_FREQUENCY_ONE (algebraic shortcut, not a text rule)

If no R1–R4 signal fires (`time_denominator` still `None`) **and** the row's own `frequency` column
equals exactly `1.0`, `time_denominator` is set to `"day"` with `ambiguity_status =
RESOLVED_BY_FREQUENCY_ONE`. This is not a text-matching rule — it fires purely on the numeric
`frequency` value and is mathematically forced (per-dose and per-day are the same number when there
is one administration per day), not an inference about the source text's intent. **Precedence**: only
applies when R1–R4 all fail to fire; a genuine textual signal always wins over this shortcut.

## R5 — MAX_DOSE_SIGNAL (qualitative, informational only)

```regex
не\s+более|максимальн\w*\s+сут\w*\s+доз\w*|максимальн\w*\s+разов\w*\s+доз\w*
|не\s+превышать|max(?:imum)?\s+(?:daily|single)\s+dose
```
- Searched against the **full** `source_quote`, not the window — used only to record whether *some*
  max-dose language exists anywhere in the quote, stored in `provenance.max_dose_signal` for human
  review context. **Not used to set `max_daily_dose`/`max_single_dose`** — that's R6.

## R6 — MAX_DOSE_VALUE (quantitative, sets `max_daily_dose`/`max_single_dose`)

```regex
не\s+более\s+(\d+(?:[.,]\d+)?)\s*(мг|г|гр)\b
|max(?:imum)?\s+(?:daily|single)\s+dose\D{0,10}(\d+(?:[.,]\d+)?)\s*(mg|g)\b
```
- Searched **only within the same proximity window** as R1–R4 (not the full quote) — scopes the
  extraction to this row's own dose token, not an unrelated drug's cap mentioned elsewhere in a
  combined guideline sentence.
- **Unit restriction is deliberate**: only `мг`/`г`/`гр`/`mg`/`g` are accepted directly after the
  number, specifically so `"не более 24 часов"` (hours, a duration) or `"не более 60 минут"`
  (minutes) can never be captured as a dose value. Verified by `test_max_dose_never_captures_duration`.
- **Attribution**: the extracted value is assigned to `max_daily_dose` if this row's own
  `time_denominator` resolved to `"day"`, `max_single_dose` if `"dose"`; if `time_denominator` is
  still unresolved, the value is **discarded**, not guessed onto either field.
- **Positive examples**: `"не более 2 гр"` → 2000 mg, `"не более 120 мг"` → 120 mg, `"не более
  600 мг"` → 600 mg.
- **Negative example (verified)**: `"вводятся не более 24 часов после операции"` → no match (unit
  "часов" rejected).

## Unit-level gate (upstream, `parser.py`, reused unchanged)

Before any R1–R6 rule runs, `parser.parse_dose_expression()` must resolve the `unit` column to a
known numerator (`mg`/`IU`/`mL`, with `g`→mg conversion) and reject compound/duplicated unit strings
(containing `;`) or unrecognized tokens (`%`, `капли`, empty string) as `UNPARSED`. Rows failing this
gate never reach R1–R6 at all — `semantic_type = UNPARSED` is returned immediately.

## `dose is None` gate (upstream)

Rows with no `dose` value never reach R1–R6. Split into `MISSING` vs `NOT_APPLICABLE` by a coarse
heuristic (long free-text `antibiotic` field + no unit/frequency/duration at all ⇒
`NOT_APPLICABLE`) — not a text rule, a structural-field heuristic, documented as approximate in
`RC030_DOSE_SEMANTICS_AUDIT.md`.

## Explicitly absent rules (not implemented — by design or by gap)

| Behavior requested by RC-030-EVIDENCE spec | Status |
|---|---|
| Table-boundary behavior | **Not implemented** — `assembled_regimens.sqlite` carries no table row/column structure; no rule can reference it because it does not exist in the data |
| Sentence-boundary detection (marker cannot cross a `.`) | **Not implemented** — the 90-char window can and does cross sentence boundaries; this is the single highest-risk gap, addressed in Phase 3 |
| Alternative-boundary detection (marker cannot cross "или") | **Not implemented** as an explicit rule — Rule P's proximity tie-break provides partial, not complete, protection (see the 7620 counter-example) — addressed in Phase 3 |
| Age-group boundary (adult marker cannot classify pediatric dose) | **Not implemented** as an explicit rule — relies entirely on the window being narrow enough not to cross into a different age-group's sentence, which is not guaranteed — addressed in Phase 3 |
| Loading-dose vs maintenance-dose separation | **Not implemented** — no rule distinguishes them; both would be classified independently per their own row if they are separate `assembled_regimens` rows, but if flattened into one `source_quote` shared by both, proximity is the only protection |

These absences are exactly what Phase 3's independent false-positive audit is designed to quantify
and, where necessary, correct by demoting affected rows to `AMBIGUOUS`.
