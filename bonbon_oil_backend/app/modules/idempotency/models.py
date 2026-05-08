"""
Idempotency key model.

Stores a per-request idempotency key so that retried API calls return the
same cached response instead of executing the operation again.

Lifecycle:
  1. Client sends `Idempotency-Key: <uuid>` header with a state-changing request.
  2. Middleware looks up the key in this table.
  3. If found (same request hash) → return cached response immediately.
  4. If found (different request hash) → 409 IdempotencyConflictError.
  5. If not found → process normally, persist (key, hash, response) here.

Expiry:
  Keys expire after 24 hours. A Celery cleanup task removes expired rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class IdempotencyKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Cached response storage for idempotent API operations."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # SHA-256 hex digest of the canonical request body — detects divergent retries
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    response_status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  index=True)
    actor: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")

    @classmethod
    def make_expiry(cls, hours: int = 24) -> datetime:
        return datetime.now(UTC) + timedelta(hours=hours)

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at
