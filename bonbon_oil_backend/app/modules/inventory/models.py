"""
Inventory models: items, movement ledger, and snapshots.

Architecture: Ledger-based inventory.
- `InventoryItem` is the catalog of all stockable goods.
- `InventoryMovement` is the append-only ledger — each row records one
  physical movement (in or out) with a signed quantity.
- `current_balance` on `InventoryItem` is a denormalized running total
  updated transactionally with each movement. It exists for fast reads.
  The source of truth is the movement ledger; the balance can be recalculated
  from it at any time.
- `InventorySnapshot` records point-in-time balance snapshots for reporting.

Why ledger architecture:
- Full audit trail of every stock movement
- Supports backdated corrections (correction movement type)
- Enables point-in-time balance queries
- Required for manufacturing loss tracking (production_consumption)
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import FullAuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.inventory.enums import (
    InventoryItemType,
    InventoryMovementStatus,
    MovementType,
    WeightUnit,
)


class InventoryItem(FullAuditMixin, Base):
    """
    Catalog entry for a stockable item.

    `unit` is the canonical unit used for all balance calculations.
    When a movement uses a different unit, the service layer converts
    to the canonical unit before writing the ledger entry.
    """

    __tablename__ = "inventory_items"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_type: Mapped[InventoryItemType] = mapped_column(String(32), nullable=False, index=True)
    unit: Mapped[WeightUnit] = mapped_column(String(16), nullable=False)

    # Denormalized running balance (canonical unit)
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )

    # Reorder settings
    reorder_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    reorder_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Relationships
    movements: Mapped[list["InventoryMovement"]] = relationship(
        "InventoryMovement", back_populates="item", lazy="noload"
    )

    @property
    def is_low_stock(self) -> bool:
        if self.reorder_level is None:
            return False
        return self.current_balance <= self.reorder_level


class InventoryMovement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Append-only ledger entry for one inventory movement.

    `quantity` is always positive. Direction is determined by `movement_type`
    (checked against INBOUND/OUTBOUND sets in the service).
    `balance_after` snapshots the item balance after this movement was applied —
    allows point-in-time queries without a full ledger replay.
    """

    __tablename__ = "inventory_movements"

    item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    movement_type: Mapped[MovementType] = mapped_column(String(32), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[WeightUnit] = mapped_column(String(16), nullable=False)
    quantity_in_canonical_unit: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # Unit price at time of movement (for COGS calculation)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # Source reference (polymorphic)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[InventoryMovementStatus] = mapped_column(
        String(16), nullable=False, default=InventoryMovementStatus.CONFIRMED
    )

    # Actor
    actor: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")

    # Relationships
    item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="movements", lazy="noload")

    __table_args__ = (
        Index("ix_inventory_movements_item_created", "item_id", "created_at"),
        Index("ix_inventory_movements_reference", "reference_type", "reference_id"),
    )


class InventorySnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Daily/period-end snapshot of inventory balance for reporting.

    Snapshots allow fast point-in-time balance queries without replaying
    the entire movement ledger. One snapshot per item per date is enforced
    by a unique constraint.
    """

    __tablename__ = "inventory_snapshots"

    item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")

    __table_args__ = (
        UniqueConstraint("item_id", "snapshot_date", name="uq_inventory_snapshot_item_date"),
    )
