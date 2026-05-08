"""
Celery application factory.

Queue strategy:
- `default`        : general background tasks
- `high_priority`  : time-sensitive tasks (payment confirmations, alerts)
- `reports`        : long-running report generation (doesn't starve real-time work)

All tasks use the shared_task decorator so they can be imported without a
Celery app instance (important for testing with CELERY_TASK_ALWAYS_EAGER=True).
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

from app.core.config import settings

celery_app = Celery(
    "bonbon_oil",
    broker=settings.redis_celery_url,
    backend=settings.redis_celery_url,
    include=[
        "app.workers.tasks.audit_tasks",
        "app.workers.tasks.report_tasks",
        "app.workers.tasks.inventory_tasks",
    ],
)

# Configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # prevent worker starvation on long tasks
    # Limits
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    # Results
    result_expires=3600,
    # Testing
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
)

# Queues
default_exchange = Exchange("default", type="direct")
priority_exchange = Exchange("high_priority", type="direct")
reports_exchange = Exchange("reports", type="direct")

celery_app.conf.task_queues = (
    Queue("default", default_exchange, routing_key="default"),
    Queue("high_priority", priority_exchange, routing_key="high_priority"),
    Queue("reports", reports_exchange, routing_key="reports"),
)
celery_app.conf.task_default_queue = "default"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "default"

# Scheduled Tasks
celery_app.conf.beat_schedule = {
    "daily-inventory-snapshot": {
        "task": "app.workers.tasks.inventory_tasks.create_daily_snapshot",
        "schedule": crontab(hour=0, minute=5),
        "options": {"queue": "reports"},
    },
    "daily-financial-summary": {
        "task": "app.workers.tasks.report_tasks.generate_daily_summary",
        "schedule": crontab(hour=0, minute=10),
        "options": {"queue": "reports"},
    },
}
