# API Key Rotation Verification — Phase 2

Generated: 2026-07-15. Repository-side scan only. Provider-side revocation cannot be proven by this scan.

## Scope of scan

- All 19 tracked files (`git ls-files`)
- All 500 untracked, non-ignored files (`git status --untracked-files=all`)
- Full Git history on all local refs (6 commits total): `git log --all --diff-filter=A --name-only` for filenames, and `git log --all -p` content grep for key-literal patterns
- `.gitignore`-excluded paths were spot-checked where safe (e.g. confirming `.env` itself is absent, not merely ignored)

## Patterns searched

- Provider key literal shapes: `sk-…`, `sk-ant-…`, `AKIA[0-9A-Z]{16}`, `AIza…` (Google), `ghp_…` (GitHub), `xox[baprs]-…` (Slack), PEM private key headers
- Generic assignment patterns: `(api_key|secret|token|password) = "<20+ char literal>"`
- Filenames: any `.env` (non-`.example`), `credentials*.json`, `secrets*.json`

## Findings

| Check | Result |
|---|---|
| Old secret literals in current working tree | **None found** — zero matches across tracked + untracked + history-content grep |
| `.env` (real, non-example) present anywhere in repo tree | **Not present** — only `.env.example` exists |
| `.env` or credential filename ever committed in history | **Never** — `git log --all --diff-filter=A --name-only \| grep -i env/secret/credential` returns nothing across all 6 commits |
| Key-literal content ever committed in history | **None found** — full-history content grep for provider key shapes returns nothing |
| Code loads credentials from environment | **Confirmed** — [src/pipeline/config.py](src/pipeline/config.py:85) reads `ANTIBIO_ANTHROPIC_API_KEY`, `ANTIBIO_DEEPSEEK_API_KEY`, `ANTIBIO_OPENROUTER_API_KEY`, `ANTIBIO_OPENAI_API_KEY`, `ANTIBIO_GEMINI_API_KEY` via `os.environ.get(..., "")`; no hardcoded fallback values |
| Missing credentials fail safely | **Confirmed** — [src/llm/llm_provider.py:255-256](src/llm/llm_provider.py:255) raises `RuntimeError("Missing required LLM credentials: ...")` naming only the env-var names, never a value |
| `.env` is gitignored | **Confirmed** — `.gitignore` lines 17-19: `.env` / `.env.*` / `!.env.example` negation, verified with `git check-ignore` |
| `.env.example` contains placeholders only | **Confirmed** — values are `<set-in-local-secret-store>` / `<optional>`, no live-looking strings |
| Test fixtures contain no live credentials | **Confirmed** — pattern scan of `*/tests/*` and fixture-like files returned no matches |
| Documentation contains no live credentials | **Confirmed** — pattern scan across all `*.md` returned no matches |
| Generated logs/reports contain no live credentials | **Confirmed** — no `.log` files present in working tree; JSON/CSV reports scanned, no matches |
| Currently staged content | **N/A** — `git diff --cached` is empty; nothing is staged |
| `.gitleaks.toml` present and scoped | **Confirmed** — [.gitleaks.toml](.gitleaks.toml) extends default gitleaks ruleset plus a custom `antibio-provider-key` rule; no `gitleaks` binary available in this environment to run it directly, so the manual regex scan above is a substitute, not a replacement |

## Owner attestation received (2026-07-15)

The owner has explicitly confirmed:

> "I confirm that the previously exposed API keys have been revoked at the providers and replaced outside the repository."

Per the owner's explicit instruction, no new secret values were requested, printed, stored, or validated in response to this attestation, and repository scanning is **not** treated as independent proof of provider-side revocation — the attestation itself is the basis for closing this item, on top of (not instead of) the repository-side findings above.

## Required status

**`ROTATED_CONFIRMED_BY_OWNER_ATTESTATION`**

This supersedes the earlier `OWNER_ATTESTATION_REQUIRED` status recorded in this document during the initial audit pass. The repository-side findings (no literals in tree/history, safe-fail credential loading, correct `.gitignore`) stand unchanged and remain the evidence on the repo side; the status change reflects the owner's attestation of the provider-side action that this repository cannot itself observe.

For the record, the status this item held before attestation: **`OWNER_ATTESTATION_REQUIRED`** — **blocking = true**

Rationale: repository scanning can confirm that no key literal is currently present in the working tree, in any untracked file, or anywhere in local Git history, and that the code fails safely without credentials. It **cannot** prove that a previously-exposed key was revoked or rotated on the provider side (Anthropic, DeepSeek, OpenRouter, OpenAI, or Gemini consoles). That fact only exists outside this repository.

Per the governing instructions for this program, this status is not inferred as `ROTATED_CONFIRMED` merely because literals were removed from the codebase. The owner must confirm one of:

- Provider-side rotation completed (new key issued, old key revoked in each provider's dashboard), or
- Provider-side evidence (e.g., an email/audit-log entry from the provider showing revocation timestamp)

## Other statuses, for completeness

- `ROTATED_CONFIRMED` — not applicable until owner attestation is given.
- `ROTATION_NOT_CONFIRMED` — not applicable; no evidence rotation has *not* happened, this is simply outside repo-scan authority.
- `HISTORY_EXPOSURE_REMAINS` — **not** the case: full local Git history (all 6 commits, all refs) was scanned and contains no key literal or `.env` file at any point. If the original incident involved a key being pasted somewhere outside this Git history (e.g. a chat log, an external gist, a screenshot), that is also outside this repository's scan authority and must be attested by the owner separately.

## Historical owner-action section (superseded)

The checklist below was the requirement before the owner attestation recorded
above. It is retained only as historical audit context and is no longer an
active blocker.

State explicitly, for each provider key in `.env.example` (Anthropic, DeepSeek, OpenRouter, OpenAI, Gemini):
1. Was a key for this provider ever exposed?
2. If yes, has it been revoked/rotated in that provider's console?
3. Date of rotation (for the record).

This attestation was received on 2026-07-15. Current status remains
**`ROTATED_CONFIRMED_BY_OWNER_ATTESTATION`**; the credential gate is met.
