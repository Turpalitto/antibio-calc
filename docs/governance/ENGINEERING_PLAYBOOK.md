# ANTIBIO ENGINEERING PLAYBOOK
## VERSION 1.0

> **Status:** ACTIVE — official project-owner text, adopted 2026-07-14.
> **Relationship:** Extends `ANTIBIO_PROJECT_CONSTITUTION.md`. The Constitution defines WHO you
> are (role, mission, frozen scope). This Playbook defines HOW you work (the milestone lifecycle,
> quality/testing/benchmark/audit standards). Read both, in that order, when onboarding.
> **Precedence:** On process, this Playbook is authoritative and refines the Constitution's
> Definition of Done into the 14-step lifecycle below. Frozen technical scope (Constitution §
> "PERMANENTLY FROZEN") is unchanged.

This document extends the Project Constitution.

The Constitution defines WHO you are.

This Playbook defines HOW you work.

These rules remain active until explicitly superseded.

=========================================================
MISSION
=========================================================

Develop ANTIBIO as a long-term production platform.

Optimize for maintainability,
traceability,
reproducibility,
clinical safety,
and production quality.

Never optimize only for today's task.

=========================================================
PRIMARY DEVELOPMENT PROCESS
=========================================================

Every milestone must follow exactly this lifecycle.

1.

Repository Review

↓

2.

Architecture Review

↓

3.

RFC Review (if applicable)

↓

4.

Design

↓

5.

Implementation

↓

6.

Migration (if required)

↓

7.

Unit Tests

↓

8.

Integration Tests

↓

9.

Regression Tests

↓

10.

Real Corpus Validation

↓

11.

Benchmark

↓

12.

Production Audit

↓

13.

Documentation Synchronization

↓

14.

Milestone Closure

Skipping any step is prohibited.

=========================================================
WHEN TO IMPLEMENT
=========================================================

If a milestone explicitly requires a subsystem
that does not yet exist

DO NOT stop.

Design

Implement

Test

Benchmark

Document

=========================================================
WHEN TO STOP
=========================================================

Stop ONLY if

Repository mismatch

Medical ambiguity

Conflicting user instructions

Potential data corruption

Otherwise continue autonomously.

=========================================================
REPOSITORY RULES
=========================================================

Always verify repository state.

Never trust previous reports.

Never trust memory.

Repository is the source of truth.

=========================================================
CODE QUALITY
=========================================================

Every implementation must be

production-ready

typed where appropriate

modular

documented

tested

maintainable

No temporary code.

No throwaway scripts unless explicitly requested.

Reusable tooling is preferred.

=========================================================
DOCUMENTATION
=========================================================

Documentation is production code.

Every completed milestone must synchronize

ROADMAP

PROJECT_STATE

NEXT_TASK

DECISIONS

AI_LOG

AGENTS

Architecture docs

README

if affected.

=========================================================
TESTING
=========================================================

Every implementation requires

unit tests

integration tests

regression tests

real execution

production validation

=========================================================
BENCHMARKS
=========================================================

No estimated improvements.

Only measured improvements.

Benchmark before

↓

Benchmark after

↓

Explain delta

=========================================================
AUTONOMOUS DECISION MAKING
=========================================================

You may independently

refactor

create modules

improve infrastructure

improve tooling

optimize performance

provided that

Clinical Decision Engine

medical logic

approved medical data

remain unchanged.

=========================================================
ARCHITECTURAL PRINCIPLES
=========================================================

Preferred architecture

Extraction

↓

Layout

↓

Semantic

↓

Knowledge

↓

Clinical Engine

↓

Application

Never bypass layers.

=========================================================
PRODUCTION AUDIT
=========================================================

Every milestone ends with

Engineering Audit

Production Validation

Documentation Sync

Milestone Closure

=========================================================
SUCCESS
=========================================================

Only after all checks pass

may the next milestone begin.
