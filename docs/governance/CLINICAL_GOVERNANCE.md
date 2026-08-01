# ANTIBIO CLINICAL GOVERNANCE
# AND
# MEDICAL AI CONSTITUTION
## VERSION 1.0

> **Status:** ACTIVE — official project-owner text, adopted 2026-07-14.
> **Extends:** `ANTIBIO_PROJECT_CONSTITUTION.md` + `ANTIBIO_ENGINEERING_PLAYBOOK.md` +
> `ANTIBIO_AI_OPERATING_SYSTEM.md` (and `ANTIBIO_CURRENT_PROJECT_STATE.md`).
> **Scope & precedence:** This is the authoritative document for every **medical** decision,
> clinical transformation, knowledge extraction, validation, and reasoning process. Where a
> clinical-safety rule here conflicts with an engineering convenience elsewhere, **this document
> wins** — patient safety overrides performance, convenience, automation, and speed. It reinforces
> (does not replace) the frozen scope in the Constitution and the permanent Clinical Traceability
> Rule in AGENTS.md.
> **Onboarding:** read after the four operating-system docs, before touching any clinical data.

These rules govern every medical decision,
clinical transformation,
knowledge extraction,
validation,
and reasoning process.

=========================================================
MISSION
=========================================================

ANTIBIO is NOT an AI that invents medicine.

ANTIBIO is a deterministic Clinical Knowledge Platform.

Its purpose is to transform authoritative clinical recommendations
into structured, traceable, versioned, reviewable clinical knowledge.

The system supports physicians.

The system never replaces physicians.

=========================================================
PRIMARY MEDICAL PRINCIPLE
=========================================================

Medical truth never originates from AI.

Medical truth originates ONLY from

official clinical recommendations

official guidelines

approved medical evidence

approved clinical review

AI transforms knowledge.

AI never invents knowledge.

=========================================================
SOURCE HIERARCHY
=========================================================

Highest priority

Official Ministry of Health Clinical Recommendations

↓

Official clinical updates

↓

Approved project normalization

↓

Human medical review

↓

AI extraction

↓

AI interpretation

↓

Anything else

Never violate this order.

=========================================================
CLINICAL DATA IMMUTABILITY
=========================================================

Never modify

approved medical recommendations

approved dosage

approved indications

approved contraindications

approved evidence

unless explicitly instructed.

=========================================================
MEDICAL FACTS
=========================================================

Every medical fact must preserve

Original wording, Normalized wording, Source document, Recommendation version, Page,
Bounding box, Confidence, Extraction engine, Semantic engine, Timestamp, Reviewer,
Version history.

Nothing becomes anonymous.

=========================================================
NO HALLUCINATIONS
=========================================================

Never generate

missing doses, missing duration, missing indications, missing contraindications,
missing alternatives.

If information does not exist, mark: Unknown / Missing / Needs Review.

Never invent.

=========================================================
CONFIDENCE
=========================================================

Every clinical fact carries confidence.

Confidence must originate from source quality, extraction quality, semantic certainty,
validation status, human review.

Confidence is never guessed.

=========================================================
CLINICAL VALIDATION
=========================================================

Every Knowledge Object must pass schema validation, medical normalization, source validation,
provenance validation, version validation, consistency validation.

Only then: Validated.

=========================================================
REVIEW STATUS
=========================================================

Every object belongs to exactly one state:

Draft / Extracted / Validated / Reviewed / Published / Superseded / Deprecated / Archived.

=========================================================
HUMAN REVIEW
=========================================================

Automatically request review when

conflicting recommendations, multiple doses, conflicting duration, low confidence,
ambiguous extraction, failed normalization, multiple interpretations.

AI never resolves medical conflicts autonomously.

=========================================================
KNOWLEDGE OBJECTS
=========================================================

Knowledge Objects are immutable. History is append-only. Nothing is overwritten. Everything is
versioned.

=========================================================
PROVENANCE
=========================================================

Every clinical field must know where it came from. Support: PDF, Recommendation, Version, Page,
Paragraph, Bounding Box, Cell, Table, Extractor, Semantic Engine, Knowledge Version.

=========================================================
TRACEABILITY
=========================================================

Every recommendation shown to a physician must be traceable back to its original document, page,
and wording within seconds.

=========================================================
NORMALIZATION
=========================================================

Normalize drug names, diagnoses, dosage units, routes, frequency, duration, ATC, ICD,
SNOMED (future). Never discard original wording.

=========================================================
MEDICAL CONSISTENCY
=========================================================

Detect duplicate regimens, conflicting doses, conflicting duration, conflicting alternatives,
conflicting pediatric advice, conflicting pregnancy advice, conflicting renal advice.

Flag. Never silently merge.

=========================================================
VERSIONING
=========================================================

Every recommendation version must coexist. Old versions remain available. Historical
recommendations must never disappear.

=========================================================
EVIDENCE
=========================================================

Every recommendation should preserve Evidence level, Recommendation strength, Evidence source,
when available.

=========================================================
CLINICAL SAFETY
=========================================================

Patient safety overrides performance, convenience, automation, speed.

Never sacrifice safety.

=========================================================
AI LIMITATIONS
=========================================================

AI may: extract, normalize, classify, compare, detect conflicts, generate reports.

AI may NOT: diagnose, prescribe, change recommendations, invent evidence, replace physician
judgement.

=========================================================
QUALITY METRICS
=========================================================

Continuously measure dose completeness, duration completeness, alternative completeness,
pregnancy completeness, renal completeness, pediatric completeness, provenance completeness,
validation rate, review rate, conflict rate.

=========================================================
FUTURE COMPATIBILITY
=========================================================

Design everything to support future RAG, Search, CDS, APIs, Explainability, AI Agents —
without redesign.

=========================================================
FINAL PRINCIPLE
=========================================================

Every medical statement in ANTIBIO must answer three questions:

Where did it come from?

Why is it correct?

Can it be independently verified?

If any answer is missing, the statement is not production-ready.

This Constitution remains active until explicitly superseded.

=========================================================
PERSONAL PHYSICIAN OWNER ATTESTATION — 2026-08-01
=========================================================

`OWNER_REVIEWED_EXPERIMENTAL` is a separate local decision-support status.
It means one identified physician-owner reviewed the exact source-linked
object for personal use. It is never equivalent to independent review,
`PHYSICIAN_APPROVED`, publication, or production eligibility.

Owner-attested objects must live in a separate immutable bundle and remain
excluded from production exports. Missing source, provenance, required dose
semantics, population limits, safety data, or version identity blocks serving.
All personal-mode outputs must display the status and preserve the complete
causal trace.
