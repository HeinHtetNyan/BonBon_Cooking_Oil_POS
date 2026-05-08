"""
Celery tasks for daily and monthly financial/inventory snapshots.

These tasks run after midnight (configured in celery_app.py beat schedule)
to capture end-of-day and end-of-month balances for:
  - InventoryItem.current_balance  → InventorySnapshot
  - FinancialAccount balances       → FinancialSnapshot

Both tasks are idempotent — re-running them on the same date has no effect
(duplicate prevention via UniqueConstraint on (item_id/account_id, snapshot_date)).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from celery import shared_task

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Inventory snapshots
# ---------------------------------------------------------------------------

@shared_task(
    name="snapshots.create_daily_inventory_snapshot",
    queue="reports",
    max_retries=3,
    default_retry_delay=60,
    bind=True,
)
def create_daily_inventory_snapshot(self, *, snapshot_date: str | None = None) -> dict:
    """
    Create an InventorySnapshot for every active inventory item.

    If `snapshot_date` is not provided, defaults to yesterday's date (the
    task runs after midnight, so yesterday is the closed day).
    """
    try:
        return asyncio.run(_create_daily_inventory_snapshot(snapshot_date=snapshot_date))
    except Exception as exc:
        logger.error("snapshot.inventory_daily.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _create_daily_inventory_snapshot(snapshot_date: str | None) -> dict:
    from app.core.config import settings
    from app.database.session import db_manager
    from app.modules.inventory.models import InventoryItem
    from app.modules.inventory.services import InventoryService
    from sqlalchemy import select

    if snapshot_date is None:
        yesterday = datetime.now(UTC) - timedelta(days=1)
        snapshot_date = yesterday.strftime("%Y-%m-%d")

    db_manager.init(settings.database_url)
    created = 0
    skipped = 0

    try:
        async with db_manager.session() as session:
            items_result = await session.execute(
                select(InventoryItem).where(InventoryItem.deleted_at.is_(None))
            )
            items = items_result.scalars().all()
            inv_service = InventoryService(session)

            for item in items:
                try:
                    await inv_service.create_snapshot(
                        item_id=item.id,
                        snapshot_date=snapshot_date,
                        actor="system",
                        notes="daily_celery_snapshot",
                    )
                    created += 1
                except Exception:
                    # UniqueConstraint → snapshot already exists for this date
                    skipped += 1
    finally:
        await db_manager.close()

    logger.info(
        "snapshot.inventory_daily.complete",
        snapshot_date=snapshot_date,
        created=created,
        skipped=skipped,
    )
    return {"snapshot_date": snapshot_date, "created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# Financial snapshots
# ---------------------------------------------------------------------------

@shared_task(
    name="snapshots.create_daily_financial_snapshot",
    queue="reports",
    max_retries=3,
    default_retry_delay=60,
    bind=True,
)
def create_daily_financial_snapshot(self, *, snapshot_date: str | None = None) -> dict:
    """
    Create a FinancialSnapshot for every active chart-of-accounts entry.
    """
    try:
        return asyncio.run(_create_daily_financial_snapshot(snapshot_date=snapshot_date))
    except Exception as exc:
        logger.error("snapshot.financial_daily.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _create_daily_financial_snapshot(snapshot_date: str | None) -> dict:
    from app.core.config import settings
    from app.database.session import db_manager
    from app.common.services.reconciliation import FinancialReconciliationService

    if snapshot_date is None:
        yesterday = datetime.now(UTC) - timedelta(days=1)
        snapshot_date = yesterday.strftime("%Y-%m-%d")

    db_manager.init(settings.database_url)
    try:
        async with db_manager.session() as session:
            svc = FinancialReconciliationService(session)
            created = await svc.create_daily_snapshots(
                snapshot_date=snapshot_date,
                actor="system",
            )
    finally:
        await db_manager.close()

    logger.info(
        "snapshot.financial_daily.complete",
        snapshot_date=snapshot_date,
        created=created,
    )
    return {"snapshot_date": snapshot_date, "created": created}


@shared_task(
    name="snapshots.create_monthly_financial_snapshot",
    queue="reports",
    max_retries=3,
    default_retry_delay=120,
    bind=True,
)
def create_monthly_financial_snapshot(
    self,
    *,
    year: int | None = None,
    month: int | None = None,
) -> dict:
    """
    Create monthly FinancialSnapshots for the last day of the given month.
    Defaults to the previous calendar month.
    """
    try:
        return asyncio.run(
            _create_monthly_financial_snapshot(year=year, month=month)
        )
    except Exception as exc:
        logger.error("snapshot.financial_monthly.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _create_monthly_financial_snapshot(
    year: int | None,
    month: int | None,
) -> dict:
    from app.core.config import settings
    from app.database.session import db_manager
    from app.common.services.reconciliation import FinancialReconciliationService

    if year is None or month is None:
        now = datetime.now(UTC)
        # Previous month
        first_of_this_month = now.replace(day=1)
        last_month = first_of_this_month - timedelta(days=1)
        year = last_month.year
        month = last_month.month

    db_manager.init(settings.database_url)
    try:
        async with db_manager.session() as session:
            svc = FinancialReconciliationService(session)
            created = await svc.create_monthly_snapshots(
                year=year, month=month, actor="system"
            )
    finally:
        await db_manager.close()

    logger.info(
        "snapshot.financial_monthly.complete",
        year=year,
        month=month,
        created=created,
    )
    return {"year": year, "month": month, "created": created}
