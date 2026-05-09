"""
Change event service for offline-sync tracking.

Every create/update/delete/void/reversal on a sync-enabled entity should
append a ChangeEvent so that mobile/PWA clients can efficiently pull only
the changes they missed since their last sync.

Usage
-----
Call `ChangeEventService.record()` at the end of any service method that
modifies a sync-enabled entity. The call is fire-and-forget from the
service's perspective — if event recording fails, the underlying operation
should still succeed (the event system is eventually-consistent).

Sync protocol (future)
----------------------
  GET /api/v1/sync/events?since=<sequence_number>&tenant_id=<tenant>
  → returns ChangeEvent rows where sequence_number > since, ordered ASC

The client applies events in order and stores the highest sequence_number
it has seen.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sync.models import ChangeEvent


class ChangeEventService:
    """Records change events for offline-sync."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        entity_type: str,
        entity_id: UUID | str,
        event_type: str,
        actor: str,
        delta: dict[str, Any] | None = None,
        device_id: str | None = None,
        tenant_id: str = "default",
    ) -> ChangeEvent:
        """
        Append a ChangeEvent to the log.

        The sequence_number is assigned by the PostgreSQL sequence
        `change_events_sequence_number_seq` which guarantees strictly
        monotonic, gap-free ordering within a single PostgreSQL node.

        Args:
            entity_type : "voucher" | "customer" | "inventory_item" | etc.
            entity_id   : UUID of the affected record.
            event_type  : "create" | "update" | "delete" | "confirm" |
                          "void" | "complete" | "cancel" | "reversal"
            actor       : User ID or "system".
            delta       : Dict of changed field names → new values.
                          Null for create/delete (full object is in entity).
            device_id   : Client device identifier if originating from mobile.
            tenant_id   : Tenant context.
        """
        # Get next sequence number from PostgreSQL sequence
        seq_result = await self._session.execute(
            text("SELECT nextval('change_events_sequence_number_seq')")
        )
        seq_number: int = seq_result.scalar_one()

        event = ChangeEvent(
            entity_type=entity_type,
            entity_id=str(entity_id),
            event_type=event_type,
            delta=delta,
            actor=actor,
            device_id=device_id,
            sequence_number=seq_number,
            tenant_id=tenant_id,
        )
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)
        return event

    async def get_events_since(
        self,
        since_sequence: int,
        tenant_id: str = "default",
        limit: int = 500,
    ) -> list[ChangeEvent]:
        """
        Return up to `limit` events with sequence_number > since_sequence.
        Ordered ASC so clients can apply in correct order.
        """
        q = (
            select(ChangeEvent)
            .where(ChangeEvent.sequence_number > since_sequence)
            .where(ChangeEvent.tenant_id == tenant_id)
            .order_by(ChangeEvent.sequence_number.asc())
            .limit(limit)
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_entity_history(
        self,
        entity_type: str,
        entity_id: UUID | str,
    ) -> list[ChangeEvent]:
        """Return all events for a specific entity, oldest first."""
        q = (
            select(ChangeEvent)
            .where(ChangeEvent.entity_type == entity_type)
            .where(ChangeEvent.entity_id == str(entity_id))
            .order_by(ChangeEvent.sequence_number.asc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())
