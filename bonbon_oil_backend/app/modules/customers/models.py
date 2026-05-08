"""Customer model."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import FullAuditMixin, OptimisticLockMixin, SyncMixin
from app.modules.customers.enums import CustomerStatus, CustomerType


class Customer(OptimisticLockMixin, SyncMixin, FullAuditMixin, Base):
    __tablename__ = "customers"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_type: Mapped[CustomerType] = mapped_column(
        String(16), nullable=False, default=CustomerType.RETAIL, index=True
    )
    status: Mapped[CustomerStatus] = mapped_column(
        String(16), nullable=False, default=CustomerStatus.ACTIVE, index=True
    )

    # Credit management
    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    credit_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def available_credit(self) -> Decimal:
        return self.credit_limit - self.credit_balance

    @property
    def is_active(self) -> bool:
        return self.status == CustomerStatus.ACTIVE
