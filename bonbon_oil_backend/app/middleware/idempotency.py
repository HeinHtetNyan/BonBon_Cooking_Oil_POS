"""
Idempotency middleware for state-changing endpoints.

Wraps specified HTTP paths so that:
  1. Requests without `Idempotency-Key` header pass through unchanged.
  2. Requests with a key that was seen before return the cached response.
  3. Requests with a new key execute normally; the response is cached.
  4. Requests with a reused key but a different body get 409.

This is a Starlette-compatible ASGI middleware. It is registered in
app/main.py AFTER the request-id middleware so that the idempotency
key is traceable via the request ID.

Covered methods / paths (configured below):
  POST /api/v1/vouchers/{id}/confirm
  POST /api/v1/vouchers/{id}/void
  POST /api/v1/expenses/
  POST /api/v1/finance/debts/{id}/payments
  POST /api/v1/production/batches/{id}/complete

The middleware reads the body ONCE and caches it in request.state so
downstream handlers (routes) can still read it normally.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Paths that require idempotency protection (regex patterns)
_IDEMPOTENT_PATHS: list[re.Pattern] = [
    re.compile(r"^/api/v1/vouchers/[^/]+/confirm$"),
    re.compile(r"^/api/v1/vouchers/[^/]+/void$"),
    re.compile(r"^/api/v1/expenses/$"),
    re.compile(r"^/api/v1/finance/debts/[^/]+/payments$"),
    re.compile(r"^/api/v1/production/batches/[^/]+/complete$"),
]

IDEMPOTENCY_HEADER = "Idempotency-Key"


def _is_idempotent_path(path: str, method: str) -> bool:
    if method.upper() != "POST":
        return False
    return any(p.match(path) for p in _IDEMPOTENT_PATHS)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that enforces idempotency for critical POST endpoints.

    The middleware needs a DB session to look up and store idempotency keys.
    It obtains the session via the same `get_db_session` dependency factory
    used by routes, but calls it directly inside the middleware context.

    Implementation note:
    --------------------
    BaseHTTPMiddleware bodies are consumed once. We buffer the body bytes
    into `request.state.body` so the downstream route can re-read them via
    `await request.body()` (FastAPI caches this on the Request object).
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only process idempotency-protected paths
        if not _is_idempotent_path(request.url.path, request.method):
            return await call_next(request)

        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
        if not idempotency_key:
            # No key supplied → pass through (key is optional for these endpoints)
            return await call_next(request)

        # Buffer request body so downstream can still read it
        body_bytes = await request.body()
        request.state.body = body_bytes

        # Compute request hash for divergent-retry detection
        from app.modules.idempotency.services import IdempotencyService

        request_hash = IdempotencyService.hash_body(body_bytes)

        # Check existing key using the app's DB session
        try:
            from app.database.session import db_manager

            async with db_manager.session() as session:
                svc = IdempotencyService(session)
                cached = await svc.check(idempotency_key, request_hash)

                if cached is not None:
                    # Return cached response without re-executing the operation
                    body = cached.response_body or {}
                    return JSONResponse(
                        content=body,
                        status_code=cached.response_status_code,
                        headers={"X-Idempotency-Replayed": "true"},
                    )

        except Exception as exc:
            from app.core.exceptions import IdempotencyConflictError

            if isinstance(exc, IdempotencyConflictError):
                return JSONResponse(
                    content={
                        "error_code": exc.error_code,
                        "message": exc.message,
                    },
                    status_code=exc.status_code,
                )
            # Other errors → let request proceed normally (fail open)

        # Execute the actual request
        response = await call_next(request)

        # Cache successful responses (2xx only — don't cache validation errors)
        if 200 <= response.status_code < 300:
            try:
                # Read response body to cache it
                response_body_bytes = b""
                async for chunk in response.body_iterator:
                    response_body_bytes += chunk

                try:
                    response_body_dict = json.loads(response_body_bytes)
                except (json.JSONDecodeError, ValueError):
                    response_body_dict = None

                # Determine actor from JWT (best-effort)
                actor = request.headers.get("X-Actor", "system")

                from app.database.session import db_manager

                async with db_manager.session() as session:
                    svc = IdempotencyService(session)
                    await svc.store(
                        key=idempotency_key,
                        request_hash=request_hash,
                        response_status_code=response.status_code,
                        response_body=response_body_dict,
                        actor=actor,
                    )

                # Re-wrap the consumed response body
                return Response(
                    content=response_body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
            except Exception:
                # Caching failure must not break the original response
                pass

        return response
