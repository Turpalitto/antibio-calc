"""Public HTTP API for the ANTIBIO Clinical Decision Platform (INT-5).

INT-5a: skeleton, versioning, request/response contract, health endpoint.
Framework-agnostic handlers live in ``service``; the optional FastAPI binding is
in ``app`` (the engine core never imports a web framework).
"""

from clinical_engine.api import contract, service

__all__ = ["contract", "service"]
