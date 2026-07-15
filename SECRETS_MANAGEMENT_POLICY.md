# ANTIBIO Secrets Management Policy

## Rules

- Secrets never live in source, documentation, fixtures, SQLite, logs or reports.
- Remote provider credentials use environment variables named `ANTIBIO_<PROVIDER>_API_KEY`.
- `.env` is local-only and ignored. `.env.example` contains placeholders only.
- Missing credential for an enabled remote provider fails during provider creation.
- Logs may show provider, file, line, redacted prefix and SHA-256 fingerprint only.
- Production uses OS/cloud secret storage. Shell environment is injection mechanism, not source of truth.
- Secret scan runs before commit and in CI using `.gitleaks.toml`.
- Suspected exposure triggers immediate rotation. Git history rewrite requires owner approval and coordinated clone invalidation.

## Provider variables

- `ANTIBIO_ANTHROPIC_API_KEY`
- `ANTIBIO_DEEPSEEK_API_KEY`
- `ANTIBIO_OPENROUTER_API_KEY`
- `ANTIBIO_OPENAI_API_KEY`
- `ANTIBIO_GEMINI_API_KEY`

## Incident response

1. Stop using exposed credential.
2. Record fingerprint, location, detection time.
3. Revoke and rotate at provider.
4. Remove literal from current tree.
5. Scan full working tree and Git history.
6. Decide history rewrite separately; never rewrite automatically.
7. Verify old credential rejected and new credential delivered through secret store.
