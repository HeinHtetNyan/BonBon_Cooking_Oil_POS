"""
Audit log middleware.

Captures every state-mutating request (POST/PUT/PATCH/DELETE) and queues
an audit log entry. The actual write is deferred to a Celery task so it
never blocks the request path.

What is captured:
- actor (user ID from JWT, or "anonymous")
- HTTP method + path
- request body hash (not the body itself — avoid logging PII/secrets)
- response status
- duration
- IP address
- request_id (from RequestIDMiddleware, must run first)
"""

from __future__ import annotations

import hashlib
import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SKIP_PATHS = frozenset({"/health", "/metrics", "/favicon.ico"})


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method not in MUTATING_METHODS or request.url.path in SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()

        # Extract actor before calling next (token may be needed)
        actor = _extract_actor(request)

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Async audit write — fire and forget via Celery
        _enqueue_audit(
            actor=actor,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            ip_address=_get_ip(request),
        )

        return response


def _extract_actor(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.security import decode_token

            payload = decode_token(auth_header[7:])
            return str(payload.get("sub", "unknown"))
        except Exception:
            pass
    return "anonymous"


def _get_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _enqueue_audit(**kwargs: object) -> None:
    """Fire-and-forget: enqueue to Celery. Ignore failures — audit must never break requests."""
    try:
        from app.workers.tasks.audit_tasks import write_http_audit_log

        write_http_audit_log.delay(**kwargs)
    except Exception as exc:
        logger.warning("audit.enqueue_failed", error=str(exc))
