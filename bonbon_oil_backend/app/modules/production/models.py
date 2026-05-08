"""
Production batch models.

A ProductionBatch records one manufacturing run:
- Input: raw materials consumed (ProductionMaterialUsage)
- Output: finished oil produced (ProductionOutput + PRODUCTION_OUTPUT inventory movement)
- Losses: tracked as a percentage (actual_yield / expected_yield)

When a batch is completed:
1. Each ProductionMaterialUsage triggers PRODUCTION_CONSUMPTION inventory movements
2. The finished output triggers PRODUCTION_OUTPUT movements and ProductionOutput records
3. Manufacturing cost is calculated and stored on the batch

Cancellation:
- PLANNED batches are cancelled without inventory effects.
- IN_PROGRESS batches reverse all inventory movements before cancellation.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import FullAuditMixin, OptimisticLockMixin, SyncMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.production.enums import ProductionBatchStatus, ProductionStage


class ProductionBatch(OptimisticLockMixin, SyncMixin, FullAuditMixin, Base):
    __tablename__ = "production_batches"

    batch_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    status: Mapped[ProductionBatchStatus] = mapped_column(
        String(16), nullable=False, default=ProductionBatchStatus.PLANNED, index=True
    )

    # Output item
    output_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expected_output: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    actual_output: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    output_unit: Mapped[str] = mapped_column(String(16), nullable=False)

    # Cost
    total_material_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    total_labour_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    total_overhead_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )

    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Completion / cancellation timestamps
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    material_usages: Mapped[list["ProductionMaterialUsage"]] = relationship(
        "ProductionMaterialUsage", back_populates="batch", lazy="noload"
    )
    outputs: Mapped[list["ProductionOutput"]] = relationship(
        "ProductionOutput", back_populates="batch", lazy="noload"
    )

    @property
    def total_cost(self) -> Decimal:
        return self.total_material_cost + self.total_labour_cost + self.total_overhead_cost

    @property
    def yield_percentage(self) -> Decimal | None:
        if self.actual_output is None or self.expected_output == Decimal("0"):
            return None
        return (self.actual_output / self.expected_output * Decimal("100")).quantize(
            Decimal("0.01")
        )


class ProductionMaterialUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Record of raw material consumed in a production batch."""

    __tablename__ = "production_material_usages"

    batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("production_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    actual_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    batch: Mapped["ProductionBatch"] = relationship(
        "ProductionBatch", back_populates="material_usages", lazy="noload"
    )


class ProductionOutput(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Records the finished goods produced in a batch."""

    __tablename__ = "production_outputs"

    batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("production_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    output_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)

    # Links to the inventory movement that was created for this output
    inventory_movement_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="RESTRICT"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")

    batch: Mapped["ProductionBatch"] = relationship(
        "ProductionBatch", back_populates="outputs", lazy="noload"
    )
