# RC-030 C7 Quick Review Interface

Date: 2026-07-29

## Result

The owner-review interface now supports a deliberate one-click path for the
three common source-fidelity outcomes:

1. `Диапазон за одно введение`;
2. `Суточный диапазон`;
3. `По источнику неоднозначно`.

After a click, the interface:

- maps the action to the existing canonical verdict taxonomy;
- writes a standardized note containing the PDF filename and page;
- appends a new local event without overwriting prior events;
- automatically opens the next unreviewed record.

Keyboard shortcuts `1`, `2`, and `3` perform the same actions. Arrow keys
still navigate, and `Ctrl+Enter` still submits the detailed form.

## Safety properties retained

- No verdict is preselected.
- Parser and AI proposals remain hidden until after submission.
- A quick result exists only after an explicit owner click/key press.
- Table-context tasks use the dedicated
  `TABLE_HEADER_CONFIRMS_PER_DOSE/PER_DAY` UI actions.
- Wrong anchor, wrong frequency, wrong alternative, corrupted source, and
  other unusual cases remain in the detailed form and require a custom note.
- Events remain local and append-only.
- Nothing changes `calculation_eligibility`, clinical approval, a source
  database, or the Clinical Engine.

## Build and live verification

- Rebuilt all 11 C7 batch interfaces and the synthetic control interface.
- Live browser test on `c7_controls.html`:
  - clicked the quick daily-total button once;
  - progress changed from `0/4` to `1/4`;
  - interface automatically moved from record 1 to record 2;
  - event contained `SOURCE_CONFIRMS_RANGE_DAILY` /
    `CORRECT_RANGE_DAILY`;
  - standardized source/page note was present;
  - `test_event=true` remained enforced in control mode.
- The real batch was only inspected, not submitted; no real owner verdict was
  created by the assistant.

## Files

- `generated/rc030_recovery/owner_review_template.html`
- `tests/rc030_owner_interface/test_c5_owner_interface.py`
- local-only generated interfaces under `generated/rc030_c7_owner_review/`

## Tests

`python -m pytest tests/rc030_owner_interface tests/dose_verification_sandbox -q`
-> 382 passed.
