"""
Sales voucher and line-item models.

A Voucher is the core sales document. It contains:
- Header: customer, date, status, totals
- Lines (VoucherItem): one per product, with quantity/unit/price
- Payments (VoucherPayment): one per payment transaction (split payment)

Totals are denormalized on the header for fast queries but must be
recalculated whenever items or discounts change. The service layer
enforces this invariant via `_recalculate_totals()`.

Financial and inventory effects are triggered when a voucher is confirmed:
- Each VoucherItem generates an inventory SALE_OUT movement
- Each VoucherPayment generates ledger entries
- If paid on credit, a CustomerDebt record is created
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import FullAuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.vouchers.enums import VoucherStatus, VoucherType


class Voucher(FullAuditMixin, Base):
    __tablename__ = "vouchers"

    voucher_number: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    voucher_type: Mapped[VoucherType] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[VoucherStatus] = mapped_column(
        String(16), nullable=False, default=VoucherStatus.DRAFT, index=True
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Totals (denormalized, recalculated by service on every change)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sale_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD

    # Relationships
    items: Mapped[list["VoucherItem"]] = relationship(
        "VoucherItem", back_populates="voucher", lazy="noload", cascade="all, delete-orphan"
    )
    payments: Mapped[list["VoucherPayment"]] = relationship(
        "VoucherPayment", back_populates="voucher", lazy="noload", cascade="all, delete-orphan"
    )

    @property
    def outstanding_amount(self) -> Decimal:
        return self.total_amount - self.paid_amount

    @property
    def is_editable(self) -> bool:
        from app.modules.vouchers.enums import EDITABLE_STATUSES

        return self.status in EDITABLE_STATUSES


class VoucherItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Line item for a voucher."""

    __tablename__ = "voucher_items"

    voucher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vouchers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inventory_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )

    # Denormalized line total (recalculated on save)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    voucher: Mapped["Voucher"] = relationship("Voucher", back_populates="items", lazy="noload")

    def recalculate(self) -> None:
        """Recalculate line_total from quantity, unit_price, discount."""
        gross = self.quantity * self.unit_price
        discount = gross * (self.discount_percent / Decimal("100"))
        self.line_total = gross - discount


class VoucherPayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One payment transaction against a voucher.

    Multiple VoucherPayment rows per voucher = split payment.
    """

    __tablename__ = "voucher_payments"

    voucher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vouchers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_method_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payment_methods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(36), nullable=False)

    voucher: Mapped["Voucher"] = relationship("Voucher", back_populates="payments", lazy="noload")
