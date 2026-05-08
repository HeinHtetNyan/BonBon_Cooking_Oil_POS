"""
Inventory service — movement ledger logic and unit conversion.

Every inventory change goes through `InventoryService.record_movement()`.
All unit conversions go through `UnitConversionService`. No conversion
logic is scattered across other services.

Decimal precision: all calculations use Decimal. The service receives
Decimal from schemas (Pydantic v2 Decimal type) and passes Decimal to models.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.common.utils.decimal import ZERO, round_quantity
from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    InsufficientInventoryError,
    NotFoundError,
)
from app.modules.inventory.enums import (
    INBOUND_MOVEMENTS,
    OUTBOUND_MOVEMENTS,
    InventoryItemType,
    InventoryMovementStatus,
    MovementType,
    WeightUnit,
)
from app.modules.inventory.models import InventoryItem, InventoryMovement, InventorySnapshot
from app.modules.inventory.repositories import InventoryItemRepository, InventoryMovementRepository


class UnitConversionService:
    """
    Centralized unit conversion. NEVER do conversions inline in other services.

    Conversion constants (exact Decimal values — no floats):
        1 viss  = 100 ticals
        1 viss  = 1.6329 kg
        1 tical = 0.016329 kg
        1 liter (cooking oil) ≈ 0.92 kg
    """

    CONVERSION_TABLE: dict[tuple[WeightUnit, WeightUnit], Decimal] = {
        # viss ↔ tical
        (WeightUnit.VISS, WeightUnit.TICAL): Decimal("100"),
        (WeightUnit.TICAL, WeightUnit.VISS): Decimal("0.01"),
        # viss ↔ kg
        (WeightUnit.VISS, WeightUnit.KG): Decimal("1.6329"),
        (WeightUnit.KG, WeightUnit.VISS): Decimal("0.612400975"),
        # tical ↔ kg
        (WeightUnit.TICAL, WeightUnit.KG): Decimal("0.016329"),
        (WeightUnit.KG, WeightUnit.TICAL): Decimal("61.2400975"),
        # liter ↔ kg  (cooking oil approximation: 1 liter ≈ 0.92 kg)
        (WeightUnit.LITER, WeightUnit.KG): Decimal("0.92"),
        (WeightUnit.KG, WeightUnit.LITER): Decimal("1.086956521739"),
        # liter ↔ viss
        (WeightUnit.LITER, WeightUnit.VISS): Decimal("0.563418"),
        (WeightUnit.VISS, WeightUnit.LITER): Decimal("1.775"),
        # liter ↔ tical
        (WeightUnit.LITER, WeightUnit.TICAL): Decimal("56.3418"),
        (WeightUnit.TICAL, WeightUnit.LITER): Decimal("0.01775"),
    }

    @classmethod
    def convert(
        cls,
        quantity: Decimal,
        from_unit: WeightUnit,
        to_unit: WeightUnit,
    ) -> Decimal:
        """Convert quantity from one unit to another. Returns rounded to 6 dp."""
        if from_unit == to_unit:
            return round_quantity(quantity)
        factor = cls.CONVERSION_TABLE.get((from_unit, to_unit))
        if factor is None:
            raise ValueError(
                f"No conversion defined from '{from_unit}' to '{to_unit}'"
            )
        return round_quantity(quantity * factor)

    @classmethod
    def to_canonical(
        cls,
        quantity: Decimal,
        from_unit: WeightUnit,
        canonical_unit: WeightUnit,
    ) -> Decimal:
        """Convert to the item's canonical (storage) unit."""
        if from_unit == canonical_unit:
            return round_quantity(quantity)
        return cls.convert(quantity, from_unit, canonical_unit)

    @classmethod
    def validate_compatible(cls, from_unit: WeightUnit, to_unit: WeightUnit) -> None:
        """Raise ValueError if units are not convertible."""
        if from_unit == to_unit:
            return
        if (from_unit, to_unit) not in cls.CONVERSION_TABLE:
            raise ValueError(
                f"Units '{from_unit}' and '{to_unit}' are not convertible"
            )


class InventoryService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._item_repo = InventoryItemRepository(session)
        self._movement_repo = InventoryMovementRepository(session)

    async def record_movement(
        self,
        *,
        item_id: UUID,
        movement_type: MovementType,
        quantity: Decimal,
        unit: WeightUnit,
        unit_price: Decimal | None = None,
        reference_type: str | None = None,
        reference_id: str | None = None,
        notes: str | None = None,
        actor: str,
        tenant_id: str = "default",
    ) -> InventoryMovement:
        """
        Core movement recording. All inventory changes MUST go through here.

        - Validates sufficient stock for outbound movements.
        - Converts to canonical unit using UnitConversionService.
        - Updates denormalized balance atomically.
        - Stores balance_after snapshot.
        - Raises InsufficientInventoryError if outbound > balance.
        """
        item = await self._item_repo.get_by_id(item_id)
        if item is None:
            raise NotFoundError("InventoryItem", item_id)

        canonical_qty = UnitConversionService.to_canonical(quantity, unit, item.unit)

        if movement_type in OUTBOUND_MOVEMENTS:
            if item.current_balance < canonical_qty:
                raise InsufficientInventoryError(
                    item.name,
                    f"{quantity} {unit}",
                    f"{item.current_balance} {item.unit}",
                )

        delta = canonical_qty if movement_type in INBOUND_MOVEMENTS else -canonical_qty
        updated_item = await self._item_repo.update_balance(item, delta)
        balance_after = updated_item.current_balance

        movement = InventoryMovement(
            item_id=item_id,
            movement_type=movement_type,
            quantity=quantity,
            unit=unit,
            quantity_in_canonical_unit=canonical_qty,
            balance_after=balance_after,
            unit_price=unit_price,
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes,
            status=InventoryMovementStatus.CONFIRMED,
            actor=actor,
            tenant_id=tenant_id,
        )
        return await self._movement_repo.create(movement)

    async def reverse_movement(
        self,
        movement_id: UUID,
        *,
        reason: str,
        actor: str,
    ) -> InventoryMovement:
        """
        Create a reversal movement (opposite direction, same quantity).
        Used when voiding vouchers or cancelling production batches.
        Updates balance and marks original as CANCELLED.
        """
        original = await self._movement_repo.get_by_id_or_raise(movement_id)
        if original.status == InventoryMovementStatus.CANCELLED:
            raise BusinessRuleError("Movement is already cancelled")

        # For a VOID_REVERSAL we always use VOID_REVERSAL type.
        # The direction is determined: inbound original → outbound reversal,
        # outbound original → inbound reversal.
        # We handle this by computing balance delta correctly in record_movement.
        # Since VOID_REVERSAL is not in INBOUND or OUTBOUND sets, we handle
        # direction explicitly here by calling the item repo directly.

        item = await self._item_repo.get_by_id_or_raise(original.item_id)

        # Original inbound movements added to balance → reversal removes from balance.
        # Original outbound movements removed from balance → reversal adds to balance.
        if original.movement_type in INBOUND_MOVEMENTS:
            # Reversal is outbound — deduct from balance
            if item.current_balance < original.quantity_in_canonical_unit:
                raise InsufficientInventoryError(
                    item.name,
                    f"{original.quantity_in_canonical_unit} {item.unit}",
                    f"{item.current_balance} {item.unit}",
                )
            delta = -original.quantity_in_canonical_unit
        else:
            # Reversal is inbound — add back to balance
            delta = original.quantity_in_canonical_unit

        updated_item = await self._item_repo.update_balance(item, delta)

        reversal = InventoryMovement(
            item_id=original.item_id,
            movement_type=MovementType.VOID_REVERSAL,
            quantity=original.quantity,
            unit=original.unit,
            quantity_in_canonical_unit=original.quantity_in_canonical_unit,
            balance_after=updated_item.current_balance,
            unit_price=original.unit_price,
            reference_type=original.reference_type,
            reference_id=original.reference_id,
            notes=f"REVERSAL: {reason}",
            status=InventoryMovementStatus.CONFIRMED,
            actor=actor,
            tenant_id=original.tenant_id,
        )
        await self._movement_repo.create(reversal)

        # Mark original as cancelled
        original.status = InventoryMovementStatus.CANCELLED
        await self._session.flush()

        return reversal

    async def reverse_all_for_reference(
        self,
        reference_type: str,
        reference_id: str,
        reason: str,
        actor: str,
    ) -> list[InventoryMovement]:
        """Reverse all active movements for a reference. Used on voucher void."""
        movements = await self._movement_repo.get_by_reference(reference_type, reference_id)
        reversals = []
        for mov in movements:
            if mov.status != InventoryMovementStatus.CANCELLED:
                r = await self.reverse_movement(mov.id, reason=reason, actor=actor)
                reversals.append(r)
        return reversals

    async def create_snapshot(
        self,
        item_id: UUID,
        snapshot_date: str,
        actor: str,
        tenant_id: str = "default",
        notes: str | None = None,
    ) -> InventorySnapshot:
        """Create a point-in-time balance snapshot."""
        item = await self._item_repo.get_by_id_or_raise(item_id)
        snapshot = InventorySnapshot(
            item_id=item_id,
            snapshot_date=snapshot_date,
            balance=item.current_balance,
            unit=item.unit,
            notes=notes,
            actor=actor,
            tenant_id=tenant_id,
        )
        self._session.add(snapshot)
        await self._session.flush()
        await self._session.refresh(snapshot)
        return snapshot

    async def recalculate_balance(self, item_id: UUID) -> Decimal:
        """Recompute balance from ledger. Use for reconciliation only."""
        return await self._item_repo.recalculate_balance(item_id)

    async def create_item(
        self,
        *,
        code: str,
        name: str,
        item_type: InventoryItemType,
        unit: WeightUnit,
        description: str | None = None,
        reorder_level: Decimal | None = None,
        reorder_quantity: Decimal | None = None,
        actor: str,
        tenant_id: str = "default",
    ) -> InventoryItem:
        existing = await self._item_repo.get_by_code(code)
        if existing:
            raise ConflictError(f"Item code '{code}' already exists")
        item = InventoryItem(
            code=code,
            name=name,
            item_type=item_type,
            unit=unit,
            description=description,
            reorder_level=reorder_level,
            reorder_quantity=reorder_quantity,
            current_balance=ZERO,
            created_by=actor,
            updated_by=actor,
            tenant_id=tenant_id,
        )
        return await self._item_repo.create(item)

    async def update_item(
        self,
        item_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        reorder_level: Decimal | None = None,
        reorder_quantity: Decimal | None = None,
        actor: str,
    ) -> InventoryItem:
        item = await self._item_repo.get_by_id_or_raise(item_id)
        fields: dict = {"updated_by": actor}
        if name is not None:
            fields["name"] = name
        if description is not None:
            fields["description"] = description
        if reorder_level is not None:
            fields["reorder_level"] = reorder_level
        if reorder_quantity is not None:
            fields["reorder_quantity"] = reorder_quantity
        return await self._item_repo.update(item, **fields)
