"""
Celery cleanup tasks for time-limited data.

Tasks:
  - cleanup_expired_idempotency_keys : Remove expired IdempotencyKey rows.
  - cleanup_old_change_events        : Prune change events older than N days
                                       (configurable; default 90 days).

Both tasks are safe to re-run and are idempotent.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from celery import shared_task

from app.core.logging import get_logger

logger = get_logger(__name__)


@shared_task(
    name="cleanup.expired_idempotency_keys",
    queue="default",
    max_retries=3,
    default_retry_delay=60,
    bind=True,
)
def cleanup_expired_idempotency_keys(self) -> dict:
    """Delete all IdempotencyKey rows past their expires_at timestamp."""
    try:
        return asyncio.run(_cleanup_expired_idempotency_keys())
    except Exception as exc:
        logger.error("cleanup.idempotency.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _cleanup_expired_idempotency_keys() -> dict:
    from app.core.config import settings
    from app.database.session import db_manager
    from app.modules.idempotency.services import IdempotencyService

    db_manager.init(settings.database_url)
    try:
        async with db_manager.session() as session:
            svc = IdempotencyService(session)
            deleted = await svc.cleanup_expired()
    finally:
        await db_manager.close()

    logger.info("cleanup.idempotency.complete", deleted=deleted)
    return {"deleted": deleted}


@shared_task(
    name="cleanup.old_change_events",
    queue="default",
    max_retries=3,
    default_retry_delay=300,
    bind=True,
)
def cleanup_old_change_events(self, *, retain_days: int = 90) -> dict:
    """
    Prune ChangeEvent rows older than `retain_days` days.

    The default 90-day window is generous enough for any offline device
    to sync before its change stream is purged. Adjust `retain_days`
    if your mobile devices may be offline for longer periods.
    """
    try:
        return asyncio.run(_cleanup_old_change_events(retain_days=retain_days))
    except Exception as exc:
        logger.error("cleanup.change_events.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _cleanup_old_change_events(retain_days: int) -> dict:
    from sqlalchemy import delete

    from app.core.config import settings
    from app.database.session import db_manager
    from app.modules.sync.models import ChangeEvent

    cutoff = datetime.now(UTC) - timedelta(days=retain_days)

    db_manager.init(settings.database_url)
    try:
        async with db_manager.session() as session:
            result = await session.execute(
                delete(ChangeEvent).where(ChangeEvent.created_at < cutoff)
            )
            deleted = result.rowcount or 0
    finally:
        await db_manager.close()

    logger.info(
        "cleanup.change_events.complete",
        deleted=deleted,
        retain_days=retain_days,
        cutoff=cutoff.isoformat(),
    )
    return {"deleted": deleted, "retain_days": retain_days}
