"""Thin FastAPI binding over the framework-agnostic handlers (INT-5a).

FastAPI is an OPTIONAL dependency: the engine core never imports this module.
``create_app()`` wires routes to ``service`` handlers. Run with any ASGI server
(``uvicorn clinical_engine.api.app:app --port 8000``; port 8000 is also
``server.js``'s ``ENGINE_PORT`` default) — but the platform can also be driven
in-process via the handlers directly (CLI/desktop) without a server.

Two serving shapes are supported, and both need this app to answer the PWA
asset requests the shell makes relative to its own origin:

* ``npm start`` — ``server.js`` (default ``http://127.0.0.1:8080``) serves the
  shell and proxies ``/v1/``, ``/v2/`` to this app. The assets never reach
  this process.
* this app alone — the physician opens ``http://127.0.0.1:8000/personal``, so
  ``/sw.js``, ``/manifest.webmanifest``, ``/antibiotic_calc.html``,
  ``/icons/*`` and ``/vendor/*`` must be served here or the service worker
  silently fails to register and the app is not installable/offline-capable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from clinical_engine.api import contract, service

# Repository root: ``clinical_engine/api/app.py`` -> parents[2].
APP_ROOT = Path(__file__).resolve().parents[2]
ICON_DIR = APP_ROOT / "icons"
VENDOR_DIR = APP_ROOT / "vendor"

# The only static files the PWA shell may fetch, mapped to the content type the
# browser insists on (a service worker with the wrong MIME type is rejected at
# registration time). Deliberately an ALLOW-LIST of names rather than a
# ``StaticFiles`` mount of the repository root: the root also holds ``.git/``,
# ``.env`` and the gitignored ``.local/personal_physician/`` owner-token store,
# and Starlette's StaticFiles applies no dot-path filtering.
PWA_ASSETS: dict[str, str] = {
    "sw.js": "text/javascript; charset=utf-8",
    "manifest.webmanifest": "application/manifest+json; charset=utf-8",
    "antibiotic_calc.html": "text/html; charset=utf-8",
}


def _asset(name: str) -> Any:
    """Resolve an allow-listed PWA asset, or None when it is not there.

    ``name`` must be a key of :data:`PWA_ASSETS`. The containment check is on
    the *resolved* path and requires the file to sit directly in the app root,
    so neither a ``..`` name nor a symlink pointing out of the root can be
    served. ``Cache-Control: no-cache`` keeps the browser (and the service
    worker) revalidating a rebuilt shell instead of pinning a stale artifact.
    """
    if name not in PWA_ASSETS:
        return None
    from fastapi.responses import FileResponse  # optional dependency, imported lazily

    path = (APP_ROOT / name).resolve()
    if path.parent != APP_ROOT or not path.is_file():
        return None
    return FileResponse(path, media_type=PWA_ASSETS[name], headers={"Cache-Control": "no-cache"})


def create_app(ctx: "service.ApiContext | None" = None):
    from fastapi import Body, FastAPI, Request  # imported lazily; optional dependency
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles

    # ``from __future__ import annotations`` stores route annotations as strings.
    # FastAPI resolves them in module globals, so expose the lazily imported
    # optional Request type only when the FastAPI adapter is actually created.
    globals()["Request"] = Request

    context = ctx or service.ApiContext.default()
    app = FastAPI(title="ANTIBIO Clinical Decision Platform API",
                  version=contract.API_VERSION)

    def _json(result: tuple[int, dict[str, Any]]) -> JSONResponse:
        status_code, body = result
        return JSONResponse(status_code=status_code, content=body)

    def _loopback(request: Request) -> bool:
        peer = (request.client.host if request.client else "").lower()
        if peer not in {"127.0.0.1", "::1", "testclient"}:
            return False
        if (request.url.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
            return False
        origin = request.headers.get("origin")
        if not origin:
            return True  # local CLI/native clients do not send Origin
        return (urlsplit(origin).hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}

    def _personal_action(request: Request, method: str, payload: dict[str, Any]) -> Any:
        if not _loopback(request):
            return _json((403, service.v2_contract.blocked(
                "NON_LOOPBACK_REQUEST", "personal owner workflow is loopback-only"
            )))
        personal = context.personal_service
        if personal is None or not hasattr(personal, method):
            return _json((503, service.v2_contract.blocked(
                "PERSONAL_RUNTIME_UNAVAILABLE", "personal runtime is unavailable"
            )))
        try:
            result = getattr(personal, method)(payload)
        except Exception as exc:
            return _json((409, service.v2_contract.blocked(
                str(getattr(exc, "code", "OWNER_WORKFLOW_FAILED")),
                str(getattr(exc, "detail", "owner workflow failed")),
            )))
        return _json((200, result))

    @app.get("/v1/health")
    def health() -> Any:
        return _json(service.handle_health(context))

    @app.get("/v1/version")
    def version() -> Any:
        return _json(service.handle_version(context))

    @app.post("/v1/recommend")
    def recommend(payload: dict[str, Any] | None = Body(default=None)) -> Any:
        if payload is None:
            return _json((400, contract.error_response("INVALID_REQUEST", "missing JSON body")))
        return _json(service.handle_recommend(context, payload))

    @app.post("/v2/recommend")
    def recommend_v2(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> Any:
        if not _loopback(request):
            return _json((403, service.v2_contract.blocked(
                "NON_LOOPBACK_REQUEST", "personal mode is loopback-only"
            )))
        if payload is None:
            return _json((400, service.v2_contract.blocked(
                "INVALID_REQUEST", "missing JSON body", status=service.v2_contract.Status.ERROR
            )))
        host = request.url.hostname or ""
        origin = request.headers.get("origin", "")
        return _json(service.handle_recommend_v2(
            context, payload, host=host, origin=origin
        ))

    @app.get("/v2/personal/health")
    def personal_health(request: Request) -> Any:
        host = request.url.hostname or ""
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return _json((403, service.v2_contract.blocked(
                "NON_LOOPBACK_HOST", "personal mode is loopback-only"
            )))
        personal = context.personal_service
        details = personal.health() if personal is not None and hasattr(personal, "health") else {}
        return {
            "api_version": "2",
            "operating_mode": "PERSONAL_PHYSICIAN",
            "configured": personal is not None,
            "recommendation_eligible": bool(details.get("recommendation_eligible", False)),
            "bundle_version": details.get("bundle_version"),
            "governance_status": "OWNER_REVIEWED_EXPERIMENTAL",
            "production_mode_changed": False,
        }

    @app.post("/v2/personal/register-owner")
    def register_personal_owner(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> Any:
        return _personal_action(request, "register_owner", payload or {})

    @app.post("/v2/personal/recover-owner")
    def recover_personal_owner(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> Any:
        return _personal_action(request, "recover_owner", payload or {})

    @app.post("/v2/personal/attest")
    def attest_personal_regimen(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> Any:
        return _personal_action(request, "attest", payload or {})

    @app.get("/v2/personal/extracted-candidates/{guideline_id}")
    def list_extracted_candidates(request: Request, guideline_id: str) -> Any:
        if not _loopback(request):
            return _json((403, service.v2_contract.blocked(
                "NON_LOOPBACK_REQUEST", "personal owner workflow is loopback-only"
            )))
        personal = context.personal_service
        if personal is None or not hasattr(personal, "list_extracted_candidates"):
            return _json((503, service.v2_contract.blocked(
                "PERSONAL_RUNTIME_UNAVAILABLE", "personal runtime is unavailable"
            )))
        try:
            return personal.list_extracted_candidates(guideline_id)
        except Exception as exc:
            code = getattr(exc, "code", "EXTRACTED_CANDIDATES_INVALID")
            detail = getattr(exc, "detail", "extracted candidate store is unavailable")
            return _json((409, service.v2_contract.blocked(code, detail)))

    @app.post("/v2/personal/attest-candidate")
    def attest_extracted_candidate(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> Any:
        return _personal_action(request, "attest_extracted_candidate", payload or {})

    @app.post("/v2/personal/build-bundle")
    def build_personal_bundle(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> Any:
        return _personal_action(request, "build_bundle", payload or {})

    @app.get("/v2/personal/attestations")
    def list_personal_attestations(request: Request) -> Any:
        if not _loopback(request):
            return _json((403, service.v2_contract.blocked(
                "NON_LOOPBACK_REQUEST", "personal owner workflow is loopback-only"
            )))
        personal = context.personal_service
        if personal is None or not hasattr(personal, "list_attestations"):
            return _json((503, service.v2_contract.blocked(
                "PERSONAL_RUNTIME_UNAVAILABLE", "personal runtime is unavailable"
            )))
        try:
            return personal.list_attestations()
        except Exception:
            return _json((409, service.v2_contract.blocked(
                "ATTESTATION_LEDGER_INVALID", "local attestation ledger is unavailable"
            )))

    def _calculator(request: Request) -> Any:
        """Serve the built shell, loopback-only like every owner route.

        The static shell embeds the clinical DB but no owner state; it is still
        withheld off-loopback so that widening ``--host`` cannot expose the
        calculator without also exposing the token-gated workflows.
        """
        host = request.url.hostname or ""
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return _json((403, service.v2_contract.blocked(
                "NON_LOOPBACK_HOST", "personal mode is loopback-only"
            )))
        shell = _asset("antibiotic_calc.html")
        if shell is None:
            return _json((503, service.v2_contract.blocked(
                "CALCULATOR_BUILD_MISSING",
                "run `npm run build` (db/build_html.py) first"
            )))
        return shell

    @app.get("/personal")
    def personal_calculator(request: Request) -> Any:
        return _calculator(request)

    # The manifest declares start_url/scope "./", i.e. the origin root, so the
    # root must serve the shell too: without it an installed app launched from
    # this origin would 404. Same loopback policy as /personal.
    @app.get("/")
    def calculator_root(request: Request) -> Any:
        return _calculator(request)

    @app.get("/antibiotic_calc.html")
    def calculator_document(request: Request) -> Any:
        return _calculator(request)

    def _pwa_asset(name: str) -> Any:
        asset = _asset(name)
        if asset is None:
            return _json((404, service.v2_contract.blocked(
                "ASSET_NOT_FOUND", f"{name} is not available; run `npm run build`"
            )))
        return asset

    @app.get("/sw.js")
    def service_worker() -> Any:
        return _pwa_asset("sw.js")

    @app.get("/manifest.webmanifest")
    def web_manifest() -> Any:
        return _pwa_asset("manifest.webmanifest")

    # Only icons/ and vendor/ are mounted, and only after every /v1, /v2 and
    # /personal route is registered, so no engine path can be shadowed by a
    # static file. vendor/ is the self-hosted asset set (audit S-3: Tailwind,
    # Font Awesome, Google Fonts) precached by sw.js — the precache-list test
    # requires it to be served here too.
    # Mounted conditionally: StaticFiles raises at request time (HTTP 500) for a
    # directory that does not exist, even with check_dir=False, and a checkout
    # without icons/ or vendor/ must degrade to a plain 404 instead.
    if ICON_DIR.is_dir():
        app.mount("/icons", StaticFiles(directory=str(ICON_DIR)), name="icons")
    if VENDOR_DIR.is_dir():
        app.mount("/vendor", StaticFiles(directory=str(VENDOR_DIR)), name="vendor")

    return app


# Module-level app for `uvicorn clinical_engine.api.app:app` (created lazily on import).
try:  # pragma: no cover - only when fastapi present and imported as ASGI target
    app = create_app()
except Exception:  # pragma: no cover
    app = None
