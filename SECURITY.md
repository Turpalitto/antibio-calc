# Security policy

ANTIBIO is an offline-first clinical dose calculator plus a loopback-only
clinical engine. It handles no accounts and stores no patient data on a server,
but a physician may type patient context (weight, age, pregnancy, GFR, a name
in the MIS text) into the shell, so defects in the shell, the static server or
the engine proxy are treated as security issues.

## Reporting a vulnerability

* Preferred: GitHub **private vulnerability reporting** on this repository
  (Security → "Report a vulnerability"), if the owner has enabled it.
* Otherwise open an issue titled `security:` **without** exploit details and
  ask for a private channel.
* Please do not include real patient data in any report.

Clinical content (doses, regimens, source references) is **not** a security
issue — it goes through the owner-physician review queue (`NEXT_TASK.md` §1).

## Scope

| Component | Security-relevant behaviour |
|---|---|
| `antibiotic_calc.html` (shell) | no network calls for dosing; patient history kept in `sessionStorage` with a 24 h TTL; no third-party origins (Tailwind / Font Awesome / fonts self-hosted under `vendor/`) |
| `server.js` | loopback bind by default; allowlisted static paths only; `nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, CSP on HTML (`default-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`); `/v1/*`, `/v2/*` proxied only for loopback peers unless `ENGINE_PROXY_ALLOW_LAN=1`; 1 MiB body cap |
| `clinical_engine/api` | loopback peer gate on physician-mode endpoints; 413 on oversized bodies; the same security headers / CSP as `server.js` on the shell it serves; the engine is **not** connected to the calculator |
| `sw.js` | never caches `/v1/*`, `/v2/*` or non-GET requests; only same-origin assets |

## Guarantees enforced by CI

* `gitleaks` on every push and PR (`.gitleaks.toml`, plus a custom rule for the
  provider keys this project used to store in plaintext — see `DECISIONS.md`).
* `pip-audit` over the locked core dependencies — blocking; ML extras and the
  build-time npm trees — report-only with annotations.
* CodeQL (Python, JavaScript, Actions) on pushes, PRs and weekly.
* Policy tests: `src/tests/test_static_server_policy.py`,
  `clinical_engine/tests/test_api_peer_policy.py`,
  `clinical_engine/tests/test_api_static_assets.py` (forbidden paths, header
  parity with `server.js`), `clinical_engine/tests/test_service_worker.py`
  (the worker never caches engine routes), `test_calculator_clinical_safety.py`
  (DB strings are rendered as text, never as markup; CodeQL-found
  `js/xss-through-dom` on the rubricator link fixed 2026-10-14).

## Out of scope

* The archival dashboard `audit-site/` (not served by the calculator; `npm
  audit` there is report-only).
* Historical documents under `docs/history/`.
