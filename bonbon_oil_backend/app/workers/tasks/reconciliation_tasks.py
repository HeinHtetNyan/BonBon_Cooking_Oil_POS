"""
Celery tasks for data integrity checks and reconciliation.

These tasks run on a scheduled basis to detect and report inconsistencies
before they cause visible bugs in the application.

They NEVER mutate data automatically — any repairs require a separate
admin-triggered reconcile call with repair=True. This ensures that
automatic repairs are never applied silently to production data.

Alert strategy:
  - Tasks log at WARNING level when discrepancies are found.
  - In production, route Celery WARNING logs to your alerting system
    (e.g., Sentry, Datadog, Slack webhook).
"""

from __future__ import annotations

import asyncio

from celery import shared_task

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Inventory consistency check
# ---------------------------------------------------------------------------

@shared_task(
    name="reconciliation.check_inventory_consistency",
    queue="reports",
    max_retries=2,
    default_retry_delay=300,
    bind=True,
)
def check_inventory_consistency(self) -> dict:
    """
    Verify that every InventoryItem.current_balance matches its movement ledger.

    Returns a summary dict. Logs a WARNING for each discrepancy found.
    Does NOT repair — only detects and reports.
    """
    try:
        return asyncio.run(_check_inventory_consistency())
    except Exception as exc:
        logger.error("reconciliation.inventory.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _check_inventory_consistency() -> dict:
    from app.core.config import settings
    from app.database.session import db_manager
    from app.common.services.reconciliation import InventoryReconciliationService

    db_manager.init(settings.database_url)
    try:
        async with db_manager.session() as session:
            svc = InventoryReconciliationService(session)
            report = await svc.reconcile_all(repair=False)
    finally:
        await db_manager.close()

    if report.has_discrepancies:
        for d in report.discrepancies:
            logger.warning(
                "reconciliation.inventory.discrepancy",
                item_id=d.entity_id,
                item_label=d.entity_label,
                stored=str(d.stored_value),
                computed=str(d.computed_value),
                diff=str(d.diff),
            )

    result = {
        "checked": report.checked,
        "discrepancies": len(report.discrepancies),
    }
    logger.info("reconciliation.inventory.complete", **result)
    return result


# ---------------------------------------------------------------------------
# Financial integrity check
# ---------------------------------------------------------------------------

@shared_task(
    name="reconciliation.check_financial_integrity",
    queue="reports",
    max_retries=2,
    default_retry_delay=300,
    bind=True,
)
def check_financial_integrity(self) -> dict:
    """
    Run all FinancialIntegrityService checks.

    Checks:
      - Journal entry amounts > 0
      - No self-referencing journal entries
      - No negative asset account balances
      - customer.credit_balance matches outstanding debt totals
    """
    try:
        return asyncio.run(_check_financial_integrity())
    except Exception as exc:
        logger.error("reconciliation.financial.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _check_financial_integrity() -> dict:
    from app.core.config import settings
    from app.database.session import db_manager
    from app.common.services.integrity import FinancialIntegrityService

    db_manager.init(settings.database_url)
    try:
        async with db_manager.session() as session:
            svc = FinancialIntegrityService(session)
            report = await svc.run_full_check()
    finally:
        await db_manager.close()

    for issue in report.issues:
        level = logger.warning if issue.severity == "warning" else logger.error
        level(
            f"reconciliation.financial.{issue.code}",
            message=issue.message,
            **issue.context,
        )

    result = {
        "errors": report.error_count,
        "warnings": report.warning_count,
    }
    logger.info("reconciliation.financial.complete", **result)
    return result


# ---------------------------------------------------------------------------
# Orphaned record check
# ---------------------------------------------------------------------------

@shared_task(
    name="reconciliation.check_orphaned_records",
    queue="reports",
    max_retries=2,
    default_retry_delay=300,
    bind=True,
)
def check_orphaned_records(self) -> dict:
    """
    Detect journal entries that reference non-existent vouchers/debts/expenses.
    Also checks for orphaned reversal references.
    """
    try:
        return asyncio.run(_check_orphaned_records())
    except Exception as exc:
        logger.error("reconciliation.orphaned.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _check_orphaned_records() -> dict:
    from app.core.config import settings
    from app.database.session import db_manager
    from app.common.services.reconciliation import FinancialReconciliationService

    db_manager.init(settings.database_url)
    try:
        async with db_manager.session() as session:
            svc = FinancialReconciliationService(session)
            issues = await svc.detect_ledger_imbalances()
    finally:
        await db_manager.close()

    for issue in issues:
        logger.warning("reconciliation.orphaned_record", **issue)

    result = {"orphaned_references": len(issues)}
    logger.info("reconciliation.orphaned.complete", **result)
    return result


# ---------------------------------------------------------------------------
# Failed audit log retry
# ---------------------------------------------------------------------------

@shared_task(
    name="reconciliation.retry_failed_audit_logs",
    queue="default",
    max_retries=3,
    default_retry_delay=60,
    bind=True,
)
def retry_failed_audit_logs(self) -> dict:
    """
    Placeholder for retrying audit log writes that failed in the Celery worker.

    In the current implementation, audit_tasks.write_http_audit_log already
    has retry logic (max_retries=3). This task is a hook for any additional
    recovery logic needed after all retries are exhausted (e.g., write to a
    dead-letter queue or send an alert).
    """
    logger.info("reconciliation.audit_retry.noop")
    return {"status": "noop", "message": "Audit retry handled by task-level retries"}
