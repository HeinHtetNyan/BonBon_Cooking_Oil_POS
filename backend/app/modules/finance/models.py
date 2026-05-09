"""
Finance module ORM models.

Design principles:
- JournalEntry is APPEND-ONLY: it has no SoftDeleteMixin, no updated_at onupdate,
  and must never be mutated after creation. Reversals create new entries.
- FinancialAccount, PaymentMethod, and CustomerDebt use FullAuditMixin for full
  soft-delete + tenant + audit trail support.
- DebtPayment uses UUIDPrimaryKeyMixin + TimestampMixin only (no soft-delete —
  payments are facts; if a payment must be undone, a counter-payment is made).
- All monetary columns are NUMERIC(18, 4). Python code uses Decimal throughout.
- Composite indexes are declared in __table_args__ for query performance.
- Relationships use lazy="noload" to prevent accidental N+1 loads in async context.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import FullAuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.finance.enums import (
    AccountNormalBalance,
    AccountType,
    DebtStatus,
    PaymentMethodType,
    TransactionType,
)


class FinancialAccount(FullAuditMixin, Base):
    """
    Chart of accounts entry.

    Each account belongs to one of five account types. The `normal_balance`
    column is derived from `account_type` at creation time and stored for
    fast balance-query filtering (avoids a CASE expression in every balance
    computation).

    `is_system` flags accounts that ship with the product seed data and
    that application logic depends on by code (e.g., "1100" Accounts
    Receivable). System accounts cannot be soft-deleted.

    Hierarchy is supported via `parent_code` for reporting purposes only —
    balance roll-ups are computed in the service layer, not via DB joins.
    """

    __tablename__ = "financial_accounts"

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(String(16), nullable=False, index=True)
    normal_balance: Mapped[AccountNormalBalance] = mapped_column(
        String(8), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    debit_entries: Mapped[list["JournalEntry"]] = relationship(
        "JournalEntry",
        foreign_keys="JournalEntry.debit_account_id",
        back_populates="debit_account",
        lazy="noload",
    )
    credit_entries: Mapped[list["JournalEntry"]] = relationship(
        "JournalEntry",
        foreign_keys="JournalEntry.credit_account_id",
        back_populates="credit_account",
        lazy="noload",
    )


class JournalEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Append-only double-entry journal record.

    IMMUTABILITY CONTRACT
    ---------------------
    - Once created, a JournalEntry is NEVER updated or deleted.
    - The only mutation allowed is setting `is_reversed = True` after a
      reversal entry is created.
    - There is intentionally NO SoftDeleteMixin — the ledger is a permanent
      historical record. Reversal entries (TransactionType.REVERSAL) are used
      to undo effects.
    - `reversal_of_id` links a reversal back to the original entry for audit.

    BALANCE SEMANTICS
    -----------------
    - `debit_account_id` is the account that is DEBITED by this transaction.
    - `credit_account_id` is the account that is CREDITED by this transaction.
    - `amount` is always positive. Direction is encoded by which side of the
      entry the account appears on, combined with the account's normal_balance.
    - Balance for an account = Σ amounts where account appears on its normal
      balance side - Σ amounts where account appears on the opposite side.

    INDEXES
    -------
    Composite indexes on (debit_account_id, transaction_date) and
    (credit_account_id, transaction_date) allow efficient balance-as-of-date
    queries. The (reference_type, reference_id) index supports ledger lookups
    for a specific voucher or debt.
    """

    __tablename__ = "journal_entries"

    debit_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    credit_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(
        String(32), nullable=False, index=True
    )
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # YYYY-MM-DD string — stored as String(10) to avoid timezone ambiguity for
    # accounting periods. The business operates in a single timezone (MMT).
    transaction_date: Mapped[str] = mapped_column(String(10), nullable=False)

    is_reversed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reversal_of_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )

    actor: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default", index=True
    )

    # Relationships — noload enforced: never trigger lazy loads in async context
    debit_account: Mapped["FinancialAccount"] = relationship(
        "FinancialAccount",
        foreign_keys=[debit_account_id],
        back_populates="debit_entries",
        lazy="noload",
    )
    credit_account: Mapped["FinancialAccount"] = relationship(
        "FinancialAccount",
        foreign_keys=[credit_account_id],
        back_populates="credit_entries",
        lazy="noload",
    )
    reversal_of: Mapped["JournalEntry | None"] = relationship(
        "JournalEntry",
        foreign_keys=[reversal_of_id],
        remote_side="JournalEntry.id",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_journal_entries_debit_date", "debit_account_id", "transaction_date"),
        Index("ix_journal_entries_credit_date", "credit_account_id", "transaction_date"),
        Index("ix_journal_entries_reference", "reference_type", "reference_id"),
    )


class PaymentMethod(FullAuditMixin, Base):
    """
    Catalog of accepted payment methods.

    `linked_account_code` maps this payment method to a FinancialAccount code
    (e.g., CASH → "1000", KBZPay → "1050"). The LedgerService uses this to
    debit the correct asset account when a payment is received.
    """

    __tablename__ = "payment_methods"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    method_type: Mapped[PaymentMethodType] = mapped_column(String(32), nullable=False)
    linked_account_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)


class CustomerDebt(FullAuditMixin, Base):
    """
    Outstanding debt for a credit sale.

    Lifecycle:
      OUTSTANDING → PARTIALLY_PAID (first partial payment)
                 → PAID            (full payment received)
                 → WRITTEN_OFF     (debt cancelled, ledger reversed)

    `outstanding_amount` is a computed property; it is NOT stored as a column
    to avoid double-write bugs. Always read `original_amount - paid_amount`.

    `is_overdue` compares `due_date` (YYYY-MM-DD) against today's date. It
    returns False when `due_date` is None (open-ended credit).
    """

    __tablename__ = "customer_debts"

    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    voucher_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vouchers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    original_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    status: Mapped[DebtStatus] = mapped_column(
        String(16), nullable=False, default=DebtStatus.OUTSTANDING, index=True
    )
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def outstanding_amount(self) -> Decimal:
        """Remaining unpaid balance. Always >= 0."""
        return self.original_amount - self.paid_amount

    @property
    def is_overdue(self) -> bool:
        """True if due_date is set and is strictly before today."""
        if self.due_date is None:
            return False
        today_str = date.today().strftime("%Y-%m-%d")
        return self.due_date < today_str

    __table_args__ = (
        Index("ix_customer_debts_customer_status", "customer_id", "status"),
    )


class FinancialSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Daily or monthly snapshot of a financial account's balance.

    Snapshots serve two purposes:
    1. Performance — fast point-in-time balance queries for reporting without
       replaying the full JournalEntry ledger.
    2. Reconciliation — checkpoints that the FinancialReconciliationService
       uses to quickly detect drifts.

    A unique constraint on (account_id, snapshot_date, snapshot_type) prevents
    duplicate snapshots. The Celery snapshot task uses INSERT ... ON CONFLICT
    DO NOTHING to remain idempotent.
    """

    __tablename__ = "financial_snapshots"

    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # "daily" | "monthly"
    snapshot_type: Mapped[str] = mapped_column(String(16), nullable=False, default="daily")

    actor: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")

    __table_args__ = (
        UniqueConstraint(
            "account_id", "snapshot_date", "snapshot_type",
            name="uq_financial_snapshot_account_date_type",
        ),
    )


class DebtPayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Individual payment applied against a CustomerDebt.

    Each row records one payment event. Multiple DebtPayments may exist for
    a single CustomerDebt when the customer pays in instalments.

    `journal_entry_id` links the payment to its corresponding double-entry
    record for reconciliation and audit purposes.

    No SoftDeleteMixin: payments are immutable facts. An incorrect payment is
    corrected by creating a reversal JournalEntry and adjusting the debt
    manually — a process that requires manager authorisation.
    """

    __tablename__ = "debt_payments"

    debt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_debts.id", ondelete="RESTRICT"),
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
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default"
    )
