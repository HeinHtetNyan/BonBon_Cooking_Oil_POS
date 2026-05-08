"""Expense tracking models — Expense and ExpensePayment."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import FullAuditMixin, OptimisticLockMixin, SyncMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.expenses.enums import ExpenseCategory, ExpenseStatus


class Expense(OptimisticLockMixin, SyncMixin, FullAuditMixin, Base):
    __tablename__ = "expenses"

    reference_number: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    category: Mapped[ExpenseCategory] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[ExpenseStatus] = mapped_column(
        String(16), nullable=False, default=ExpenseStatus.PENDING, index=True
    )
    expense_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD

    # Optional: link to production batch
    production_batch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("production_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Linked journal entry (set when expense is paid immediately on creation)
    linked_journal_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )

    receipt_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ExpensePayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Records an individual payment event against an Expense.

    An expense may have multiple payment rows (e.g., split payments).
    No SoftDeleteMixin — payments are immutable facts.
    """

    __tablename__ = "expense_payments"

    expense_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("expenses.id", ondelete="CASCADE"),
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
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
