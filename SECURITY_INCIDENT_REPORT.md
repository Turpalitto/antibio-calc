# Security Incident Report — P5.6

Date: 2026-07-15  
Status: OPEN / OWNER ACTION REQUIRED / BLOCKING

## Confirmed exposure

Two provider API credentials existed as plaintext string literals in `src/pipeline/config.py`.

| Provider configuration | Former line | Fingerprint | Redacted prefix | Working-tree remediation |
|---|---:|---|---|---|
| anthropic-compatible endpoint | 84 | `36a82f27fc71` | `sk-2***` | replaced by environment variable |
| deepseek-compatible endpoint | 91 | `ba7b83283119` | `sk-p***` | replaced by environment variable |

Full credential values intentionally omitted.

## Rotation

Revocation/rotation cannot be executed safely without provider account authority.

**OWNER ACTION REQUIRED:** revoke both fingerprints, issue replacements if still needed, store replacements outside repository, confirm old credentials rejected. Until confirmation, security exit gate remains BLOCKING.

## Git history

Current production source is untracked at baseline commit, so these exact files are not present in reachable Git history from `main`. Full history scan remains required after source inventory is normalized. No history rewrite authorized or performed.

## Remediation applied

- Source literals removed.
- Environment variable contract added.
- Missing enabled-provider credentials fail fast.
- `.env.example`, policy and Gitleaks configuration added.
- `.env` and credential-bearing local files must remain ignored.

## Safe history-remediation plan if later evidence appears

1. Rotate first.
2. Freeze pushes and inventory all refs/tags.
3. Create protected mirror backup.
4. Use `git filter-repo` with exact secret replacement file held outside repository.
5. Force-push coordinated refs.
6. Invalidate old clones and CI caches.
7. Re-scan every ref.

History rewrite requires explicit owner approval.
