"""Audit log repository — append-only, no updates or deletes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


class AuditLogRepository:
    """
    Audit logs are append-only — this repository only supports write and read.

    No BaseRepository inheritance is intentional: update(), soft_delete(), and
    delete() must NOT exist here to enforce the immutability invariant at the
    repository boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, log: AuditLog) -> AuditLog:
        self._session.add(log)
        await self._session.flush()
        return log

    async def create_many(self, logs: list[AuditLog]) -> list[AuditLog]:
        self._session.add_all(logs)
        await self._session.flush()
        return logs

    async def list_logs(
        self,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """
        Paginated search over audit logs with optional filters.

        `action` supports substring matching (ILIKE). All other filters are
        exact matches. Returns (items, total_count).
        """
        filters = []

        if actor_id is not None:
            filters.append(AuditLog.actor_id == actor_id)
        if action is not None:
            filters.append(AuditLog.action.ilike(f"%{action}%"))
        if resource_type is not None:
            filters.append(AuditLog.resource_type == resource_type)
        if resource_id is not None:
            filters.append(AuditLog.resource_id == resource_id)
        if start_date is not None:
            filters.append(AuditLog.created_at >= start_date)
        if end_date is not None:
            filters.append(AuditLog.created_at <= end_date)

        q = select(AuditLog).order_by(AuditLog.created_at.desc())
        if filters:
            q = q.where(and_(*filters))

        count_q = select(func.count()).select_from(q.subquery())
        total: int = (await self._session.execute(count_q)).scalar_one()

        paginated_q = q.offset((page - 1) * per_page).limit(per_page)
        result = await self._session.execute(paginated_q)
        return list(result.scalars().all()), total
