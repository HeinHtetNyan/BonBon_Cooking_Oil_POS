"""Celery tasks for financial report generation."""

from __future__ import annotations

from celery import shared_task

from app.core.logging import get_logger

logger = get_logger(__name__)


@shared_task(
    name="reports.generate_daily_summary",
    queue="reports",
    max_retries=2,
    default_retry_delay=300,
)
def generate_daily_summary() -> None:
    """Generate daily financial summary and cache for dashboard."""
    logger.info("reports.daily_summary.started")
    # Implementation in Phase 2 — finance module
    logger.info("reports.daily_summary.completed")
