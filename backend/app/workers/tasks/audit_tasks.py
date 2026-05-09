"""
Celery tasks for audit log persistence.

Audit writes are offloaded here so the HTTP request path never waits for
a database write to complete. The audit log is append-only and eventually
consistent — a small delay is acceptable.
"""

from __future__ import annotations

import asyncio

from celery import shared_task

from app.core.logging import get_logger

logger = get_logger(__name__)


@shared_task(
    name="audit.write_http_audit_log",
    queue="default",
    max_retries=3,
    default_retry_delay=5,
    bind=True,
)
def write_http_audit_log(
    self,  # type: ignore[no-untyped-def]
    *,
    actor: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    ip_address: str,
) -> None:
    """Persist an HTTP audit record to the database."""
    try:
        asyncio.run(
            _write_audit(
                actor=actor,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                ip_address=ip_address,
            )
        )
    except Exception as exc:
        logger.error("audit.task_failed", error=str(exc), task_id=self.request.id)
        raise self.retry(exc=exc)


async def _write_audit(
    *,
    actor: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    ip_address: str,
) -> None:
    from app.core.config import settings
    from app.database.session import db_manager

    # Celery workers run in a separate process — the FastAPI lifespan never fires,
    # so db_manager is not initialized. asyncio.run() also creates a fresh event
    # loop on every call, making any previously-created engine unusable. Always
    # init and dispose within this coroutine.
    db_manager.init(settings.database_url)
    try:
        async with db_manager.session() as session:
            from app.modules.audit.models import AuditLog
            from app.modules.audit.repositories import AuditLogRepository

            repo = AuditLogRepository(session)
            log = AuditLog(
                actor_id=actor,
                action=f"{method} {path}",
                resource_type="http_request",
                status_code=status_code,
                duration_ms=duration_ms,
                ip_address=ip_address,
            )
            await repo.create(log)
    finally:
        await db_manager.close()
