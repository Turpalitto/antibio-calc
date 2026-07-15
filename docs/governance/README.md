# ANTIBIO Governance Framework

Versioned governing documents for AI/engineering work on ANTIBIO. Model-agnostic (Claude, GPT,
Gemini, Grok, …). Changes go through RFC + PR like any production code.

**Read `AUTONOMOUS_ENGINEERING_KERNEL.md` first** — the master entry point. It points to the six
governing documents below, in reading order.

| # | Document | Defines |
|---|----------|---------|
| — | `AUTONOMOUS_ENGINEERING_KERNEL.md` | Master entry point + canonical operating model |
| 1 | `ANTIBIO_CONSTITUTION.md` | WHO you are — role, mission, frozen scope |
| 2 | `ENGINEERING_PLAYBOOK.md` | HOW you work — 14-step milestone lifecycle |
| 3 | `CURRENT_PROJECT_STATE.md` | WHAT the repo state is (+ live audit addendum) |
| 4 | `AI_OPERATING_SYSTEM.md` | Operating principles — autonomy, priority order |
| 5 | `CLINICAL_GOVERNANCE.md` | Medical AI Constitution — provenance, safety, AI limits |
| 6 | `REPOSITORY_INTELLIGENCE.md` | Reasoning/verification method + technical-debt discipline |

**Non-negotiables across all documents:**
- Repository is the source of truth: Repository → Code → Tests → Real execution → Documentation → Conversation.
- Frozen scope (Clinical Decision Engine, approved medical content, deterministic treatment logic, bundle schemas) changes only via RFC.
- Real execution only — no mocked runs, no invented metrics.
- Every milestone: Design → Implement → Test → Benchmark → Audit → Doc-sync → Close.

**To start work:** "Read `docs/governance/`, adopt them as governing documents, and continue with
the active milestone."

Related (repo root): `HANDOFF.md` (onboarding index), `TECH_DEBT_BACKLOG.md`, `ROADMAP.md`,
`PROJECT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`, `AI_LOG.md`, `AGENTS.md`.
