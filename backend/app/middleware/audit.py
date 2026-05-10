"""
Audit log middleware.

Captures every state-mutating request (POST/PUT/PATCH/DELETE) and writes
an audit log entry as a fire-and-forget asyncio task — never blocks the
request path.
"""

from __future__ import annotations

import asyncio
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
        actor_id, actor_username, actor_role = _extract_actor(request)

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        asyncio.create_task(
            _write_audit(
                actor_id=actor_id,
                actor_username=actor_username,
                actor_role=actor_role,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                ip_address=_get_ip(request),
            )
        )

        return response


def _extract_actor(request: Request) -> tuple[str, str | None, str | None]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.security import decode_token

            payload = decode_token(auth_header[7:])
            actor_id = str(payload.get("sub", "unknown"))
            actor_username = payload.get("username")
            roles = payload.get("roles", [])
            actor_role = roles[0] if roles else None
            return actor_id, actor_username, actor_role
        except Exception:
            pass
    return "anonymous", None, None


def _get_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def _write_audit(
    *,
    actor_id: str,
    actor_username: str | None,
    actor_role: str | None,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    ip_address: str,
) -> None:
    try:
        from app.database.session import db_manager
        from app.modules.audit.models import AuditLog
        from app.modules.audit.repositories import AuditLogRepository

        async with db_manager.session() as session:
            repo = AuditLogRepository(session)
            await repo.create(
                AuditLog(
                    actor_id=actor_id,
                    actor_username=actor_username,
                    actor_role=actor_role,
                    action=f"{method} {path}",
                    resource_type="http_request",
                    status_code=status_code,
                    duration_ms=duration_ms,
                    ip_address=ip_address,
                )
            )
    except Exception as exc:
        logger.warning("audit.write_failed", error=str(exc))
