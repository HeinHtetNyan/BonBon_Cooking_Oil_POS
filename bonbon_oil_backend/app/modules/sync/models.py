"""
Change event model for offline-sync engine.

Every create/update/delete/void/reversal on a sync-enabled entity appends
a ChangeEvent row. The `sequence_number` is a monotonically increasing
integer (server-assigned via a PostgreSQL sequence) that clients use to
efficiently fetch only the events they haven't seen yet.

Client sync protocol (future):
  1. Client sends GET /sync/events?since=<last_sequence_number>
  2. Server returns all ChangeEvent rows where sequence_number > since
  3. Client applies deltas in sequence_number order
  4. Client stores the highest sequence_number it has processed

The `delta` JSONB field contains only the changed fields (not the full
object), keeping event payloads small.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class ChangeEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ordered event log entry for offline-sync change tracking."""

    __tablename__ = "change_events"

    # The entity this event affects
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # "create" | "update" | "delete" | "void" | "reversal" | "confirm" | "complete"
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Only the fields that changed (null for create/delete events where full
    # object is implicit from the entity record itself)
    delta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    actor: Mapped[str] = mapped_column(String(36), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Monotonic server-assigned sequence for ordered sync queries
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")

    __table_args__ = (
        Index("ix_change_events_entity", "entity_type", "entity_id"),
        Index("ix_change_events_sequence", "sequence_number"),
        Index("ix_change_events_tenant_sequence", "tenant_id", "sequence_number"),
        Index("ix_change_events_created_at", "created_at"),
    )
