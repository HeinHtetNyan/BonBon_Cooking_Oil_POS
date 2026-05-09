"""Enhanced AuditService for domain-level audit trail creation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.modules.audit.models import AuditLog
from app.modules.audit.repositories import AuditLogRepository

if TYPE_CHECKING:
    from app.modules.users.models import User


class AuditService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = AuditLogRepository(session)

    async def log(
        self,
        *,
        action: str,
        actor_id: str | None = None,
        actor_username: str | None = None,
        actor_role: str | None = None,
        resource_type: str | None = None,
        resource_id: str | UUID | None = None,
        before_data: dict | None = None,
        after_data: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        tenant_id: str = "default",
    ) -> AuditLog:
        """Create an audit log entry within the current transaction."""
        entry = AuditLog(
            actor_id=actor_id,
            actor_username=actor_username,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            before_data=before_data,
            after_data=after_data,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            tenant_id=tenant_id,
        )
        return await self._repo.create(entry)

    async def log_from_user(
        self,
        *,
        user: "User",
        action: str,
        resource_type: str | None = None,
        resource_id: str | UUID | None = None,
        before_data: dict | None = None,
        after_data: dict | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Convenience method when we have a User object as the actor."""
        return await self.log(
            action=action,
            actor_id=str(user.id),
            actor_username=user.username,
            actor_role=user.role,
            resource_type=resource_type,
            resource_id=resource_id,
            before_data=before_data,
            after_data=after_data,
            request_id=request_id,
            ip_address=ip_address,
            tenant_id=getattr(user, "tenant_id", "default"),
        )

    async def list_logs(
        self,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        start_date=None,
        end_date=None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """Paginated audit log search with optional filters."""
        return await self._repo.list_logs(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=per_page,
        )
