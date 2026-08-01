# Personal Physician Owner Registration and Attestation Policy

Version 1.0 — 2026-08-01
Authority: accepted `PERSONAL_PHYSICIAN_MODE_RFC.md`

## Purpose

Define the only allowed path from draft calculator content to
`OWNER_REVIEWED_EXPERIMENTAL` eligibility in local personal mode. This policy
does not create production or independent physician approval.

## Owner registration

The physician-owner registers locally with:

- stable `owner_id`;
- display name;
- professional role;
- organisation or `independent practice`;
- registration timestamp;
- active flag;
- local session-token hash.

Credential documents, patient identifiers, passwords, and raw session tokens
must not be stored in the repository or bundle. The raw token is shown once to
the local owner and only its SHA-256 hash is persisted in gitignored local
state.

## Exact attestation

Attestation is per exact regimen version, never per disease category or entire
database. The owner must inspect the source and submit:

- guideline/rubricator identity and version;
- source URL;
- PDF SHA-256;
- page number;
- exact source wording;
- structured regimen and calculator binding;
- confirmation that dose basis, frequency, route, duration, maximum dose,
  population, contraindications, and available safety modifiers match;
- rationale and attestation timestamp.

The service validates completeness and creates an append-only event. It may
build a new immutable personal bundle version from valid terminal events. It
must not infer missing values, import all calculator entries, or convert C7
source-fidelity events automatically.

## Eligibility

An attested regimen is recommendation-eligible only when:

- owner registration is active and token validation succeeds;
- payload, source identity, and calculator binding hashes match;
- required clinical and provenance fields are complete;
- guideline recency status is known and acceptable;
- the bundle validates as `OWNER_REVIEWED_EXPERIMENTAL`;
- request context contains all inputs required by that regimen;
- personal guard accepts loopback Host and Origin.

Any failure returns `REVIEW_REQUIRED` or `BLOCKED` with zero recommendations.

## Corrections and revocation

Records are never overwritten. A correction creates a superseding event.
Deactivation or revocation creates a new event and excludes the regimen from
the next bundle version. Historical hashes and reasons remain auditable.

## Separation from production

Personal owner records, ledgers, bundles, and audits:

- are gitignored local artifacts;
- are excluded from production bundle exporters;
- do not write Review Workbench production state;
- do not create `PHYSICIAN_APPROVED` or `PUBLISHED` states;
- cannot be consumed by `Profiles.production()`.
