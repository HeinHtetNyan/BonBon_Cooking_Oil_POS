"""Audit module request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.common.schemas.base import AppBaseModel


class AuditLogResponse(AppBaseModel):
    id: UUID
    action: str
    actor_id: str | None
    actor_username: str | None
    actor_role: str | None
    resource_type: str | None
    resource_id: str | None
    before_data: dict | None
    after_data: dict | None
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    status_code: int | None
    duration_ms: float | None
    tenant_id: str
    created_at: datetime
