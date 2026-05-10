"""Audit module API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.common.schemas.base import PaginatedResponse, paginated
from app.modules.audit.dependencies import get_audit_service
from app.modules.audit.schemas import AuditLogResponse
from app.modules.audit.services import AuditService
from app.modules.auth.dependencies import require_role
from app.modules.users.enums import UserRole

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get(
    "/logs",
    response_model=PaginatedResponse[AuditLogResponse],
    dependencies=[Depends(require_role(UserRole.SUPER_ADMIN))],
)
async def list_audit_logs(
    service: Annotated[AuditService, Depends(get_audit_service)],
    actor_id: Annotated[str | None, Query(description="Filter by actor user ID")] = None,
    action: Annotated[str | None, Query(description="Filter by action (substring match)")] = None,
    resource_type: Annotated[str | None, Query(description="Filter by resource type")] = None,
    resource_id: Annotated[str | None, Query(description="Filter by resource ID")] = None,
    start_date: Annotated[datetime | None, Query(description="Filter from this UTC datetime")] = None,
    end_date: Annotated[datetime | None, Query(description="Filter to this UTC datetime")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginatedResponse[AuditLogResponse]:
    logs, total = await service.list_logs(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        per_page=per_page,
    )
    items = [
        AuditLogResponse(
            id=log.id,
            action=log.action,
            actor_id=log.actor_id,
            actor_username=log.actor_username,
            actor_role=log.actor_role,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            before_data=log.before_data,
            after_data=log.after_data,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            request_id=log.request_id,
            status_code=log.status_code,
            duration_ms=log.duration_ms,
            tenant_id=log.tenant_id,
            created_at=log.created_at,
        )
        for log in logs
    ]
    return paginated(items, page=page, per_page=per_page, total=total)
