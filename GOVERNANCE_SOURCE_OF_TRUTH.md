# ANTIBIO Governance Source of Truth

Дата: 2026-07-30.

Приоритет: repository/code/tests/real execution → current governance docs →
historical docs → chat.

Статусы milestone: ANALYSIS, RFC, IMPLEMENTATION, ACCEPTANCE, FREEZE, CLOSED,
BLOCKED.

Текущая истина:

- P4.4, P4.5, P5.3, P5.4, P5.5: CLOSED по существующим certification reports;
- P5.6: ACCEPTANCE, NOT COMPLETE;
- credential-rotation gate: CLOSED по owner attestation от 2026-07-15 и
  repository-side scan; это больше не активный blocker;
- исторический fresh-clone gate на commit `6e26aeb`: PASS;
- текущий P5.6 blocker: состояние после C7 ещё не зафиксировано одним
  воспроизводимым Git boundary, а `main` опережает `origin/main`;
- C7 source-fidelity review: CLOSED — 182 append-only events, 113/113
  regimens, 0 validation issues, 105 exact matches, 8 governed
  per-administration label equivalents, 0 substantive mismatches;
- proposed-boundary canonical test run: 1499 passed, 11 skipped, 1 xfailed,
  0 failed (1511 collected; 2026-07-30);
- P6: BLOCKED;
- Clinical Decision Engine integration: запрещена до P6 entry gates;
- physician-approved ClinicalRegimen/TherapeuticOption: 0;
- Review Workbench: реализован, local-only, disconnected.

Frozen: Clinical Decision Engine logic, deterministic medical logic, approved
medical content, bundle schemas, validated medical data. Production DB/PDF
нельзя включать в Git или изменять в рамках P5.6 acceptance audit.
