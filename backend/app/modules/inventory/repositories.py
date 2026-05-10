"""Inventory repositories."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.common.repositories.base import BaseRepository
from app.modules.inventory.enums import MovementType
from app.modules.inventory.models import InventoryItem, InventoryMovement


class InventoryItemRepository(BaseRepository[InventoryItem]):
    model = InventoryItem

    async def get_by_code(self, code: str) -> InventoryItem | None:
        q = self._base_query(include_deleted=True).where(InventoryItem.code == code)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_by_id_locked(self, item_id: UUID) -> InventoryItem | None:
        """
        Fetch inventory item with SELECT ... FOR UPDATE.

        All outbound movements must call this before checking stock to
        prevent concurrent writes from racing past the balance check.
        """
        q = (
            self._base_query()
            .where(InventoryItem.id == item_id)
            .with_for_update()
        )
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def update_balance(self, item: InventoryItem, delta: Decimal) -> InventoryItem:
        """Atomically adjust the denormalized balance.

        Caller MUST have locked the item row via get_by_id_locked() first.
        """
        item.current_balance += delta
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def recalculate_balance(self, item_id: UUID) -> Decimal:
        """
        Recompute balance from the movement ledger.

        Use this for reconciliation jobs, not for every transaction.
        """
        from app.modules.inventory.enums import INBOUND_MOVEMENTS, OUTBOUND_MOVEMENTS

        inbound = await self._session.execute(
            select(func.coalesce(func.sum(InventoryMovement.quantity_in_canonical_unit), 0))
            .where(InventoryMovement.item_id == item_id)
            .where(InventoryMovement.movement_type.in_(list(INBOUND_MOVEMENTS)))
        )
        outbound = await self._session.execute(
            select(func.coalesce(func.sum(InventoryMovement.quantity_in_canonical_unit), 0))
            .where(InventoryMovement.item_id == item_id)
            .where(InventoryMovement.movement_type.in_(list(OUTBOUND_MOVEMENTS)))
        )
        return Decimal(str(inbound.scalar_one())) - Decimal(str(outbound.scalar_one()))


class InventoryMovementRepository(BaseRepository[InventoryMovement]):
    model = InventoryMovement

    # Movements are append-only — no update/delete overrides needed

    async def get_by_reference(
        self,
        reference_type: str,
        reference_id: str,
    ) -> list[InventoryMovement]:
        q = (
            select(InventoryMovement)
            .where(InventoryMovement.reference_type == reference_type)
            .where(InventoryMovement.reference_id == reference_id)
            .order_by(InventoryMovement.created_at)
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())
