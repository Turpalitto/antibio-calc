"""Thin FastAPI binding over the framework-agnostic handlers (INT-5a).

FastAPI is an OPTIONAL dependency: the engine core never imports this module.
``create_app()`` wires routes to ``service`` handlers. Run with any ASGI server
(e.g. ``uvicorn clinical_engine.api.app:app``) — but the platform can also be
driven in-process via the handlers directly (CLI/desktop) without a server.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from clinical_engine.api import contract, service


def create_app(ctx: "service.ApiContext | None" = None):
    from fastapi import Body, FastAPI, Request  # imported lazily; optional dependency
    from fastapi.responses import FileResponse, JSONResponse

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

    @app.get("/personal", response_class=FileResponse)
    def personal_calculator(request: Request) -> Any:
        host = request.url.hostname or ""
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return _json((403, service.v2_contract.blocked(
                "NON_LOOPBACK_HOST", "personal mode is loopback-only"
            )))
        calculator = Path(__file__).resolve().parents[2] / "antibiotic_calc.html"
        if not calculator.is_file():
            return _json((503, service.v2_contract.blocked(
                "CALCULATOR_BUILD_MISSING", "run build_html.ps1 first"
            )))
        return FileResponse(calculator, media_type="text/html")

    return app


# Module-level app for `uvicorn clinical_engine.api.app:app` (created lazily on import).
try:  # pragma: no cover - only when fastapi present and imported as ASGI target
    app = create_app()
except Exception:  # pragma: no cover
    app = None
