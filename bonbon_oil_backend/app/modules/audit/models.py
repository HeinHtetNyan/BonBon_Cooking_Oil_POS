"""
Enhanced Audit log model.

Audit logs are immutable append-only records. They are never updated
or soft-deleted — the `deleted_at` column does NOT appear here.

`resource_type` + `resource_id` form a polymorphic FK pattern without
an actual foreign key (so deleting a voucher does not cascade to audit logs).
`before_data` / `after_data` store JSON snapshots of the relevant fields.

The enhanced model adds:
- actor_id + actor_username for richer actor context
- request_id for cross-request correlation
- user_agent for client tracing
"""

from __future__ import annotations

from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    # Actor
    actor_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Action
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Resource (polymorphic)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # State snapshots
    before_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Request context
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Response metadata
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Tenant
    tenant_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default", index=True
    )

    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
    )
