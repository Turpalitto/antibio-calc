"""Thin FastAPI binding over the framework-agnostic handlers (INT-5a).

FastAPI is an OPTIONAL dependency: the engine core never imports this module.
``create_app()`` wires routes to ``service`` handlers. Run with any ASGI server
(e.g. ``uvicorn clinical_engine.api.app:app``) — but the platform can also be
driven in-process via the handlers directly (CLI/desktop) without a server.
"""

from __future__ import annotations

from typing import Any

from clinical_engine.api import contract, service


def create_app(ctx: "service.ApiContext | None" = None):
    from fastapi import Body, FastAPI  # imported lazily; optional dependency
    from fastapi.responses import JSONResponse

    context = ctx or service.ApiContext.default()
    app = FastAPI(title="ANTIBIO Clinical Decision Platform API",
                  version=contract.API_VERSION)

    def _json(result: tuple[int, dict[str, Any]]) -> JSONResponse:
        status_code, body = result
        return JSONResponse(status_code=status_code, content=body)

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

    return app


# Module-level app for `uvicorn clinical_engine.api.app:app` (created lazily on import).
try:  # pragma: no cover - only when fastapi present and imported as ASGI target
    app = create_app()
except Exception:  # pragma: no cover
    app = None
