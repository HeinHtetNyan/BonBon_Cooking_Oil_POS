"""
SQLAlchemy model mixins for cross-cutting concerns.

Mixin approach keeps each model focused on its own columns while sharing
identical infrastructure columns (timestamps, soft-delete, tenant, audit).

Ordering: UUIDPrimaryKeyMixin → TimestampMixin → SoftDeleteMixin → TenantMixin
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column


class UUIDPrimaryKeyMixin:
    """
    UUID v4 primary key generated at the application layer.

    Application-layer generation (not gen_random_uuid()) allows us to
    know the ID before the INSERT, enabling parent-child batch inserts
    and offline sync scenarios without a DB round-trip.
    """

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """
    UTC-aware created_at / updated_at.

    `server_default` is used as a fallback for rows inserted via raw SQL
    (e.g., data migrations). Application code relies on `default` and
    `onupdate` to ensure timezone-aware Python datetime objects are stored.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )


class SoftDeleteMixin:
    """
    Soft-delete support via `deleted_at` timestamp.

    Repositories must filter `deleted_at IS NULL` in all queries.
    Hard deletes are prohibited — a deleted record provides an audit trail
    and allows recovery. Physical deletion happens only via scheduled cleanup
    after a retention period (handled by a Celery task).
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = datetime.now(UTC)


class TenantMixin:
    """
    Multi-tenant discriminator column.

    Even though the initial deployment is single-tenant, embedding tenant_id
    now avoids a painful migration when multi-tenancy is added later.
    The default 'default' keeps all existing queries working.
    """

    tenant_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="default",
        index=True,
    )


class AuditFieldsMixin:
    """
    Who created/modified a record (user UUID as string for flexibility).

    Using string rather than FK to users.id avoids a cascade dependency
    when a user is deleted. The audit_logs table holds the full trace.
    """

    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class FullAuditMixin(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    TenantMixin,
    AuditFieldsMixin,
):
    """
    Convenience mixin that combines all infrastructure columns.

    Use on any table that is a first-class domain entity (vouchers, customers, etc.).
    """
