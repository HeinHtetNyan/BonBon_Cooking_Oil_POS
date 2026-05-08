"""
Finance module Pydantic v2 schemas.

Naming convention:
  *Create   — inbound payload for POST endpoints (no id, no server-set fields)
  *Update   — inbound payload for PATCH endpoints (all fields optional)
  *Response — outbound representation of a model (includes id, timestamps)
  *Summary  — lightweight embedding schema (used inside other responses)

All monetary fields are typed as Decimal for Pydantic validation. FastAPI will
serialise them to strings in JSON (via the custom serialiser in AppBaseModel)
to preserve precision — never use float for money.

`model_config = ConfigDict(from_attributes=True)` is inherited from AppBaseModel,
which allows `MySchema.model_validate(orm_instance)` to work directly.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.common.schemas.base import AppBaseModel
from app.modules.finance.enums import (
    AccountNormalBalance,
    AccountType,
    DebtStatus,
    PaymentMethodType,
    TransactionType,
)


# Financial Account

class FinancialAccountCreate(AppBaseModel):
    """Payload for creating a new chart-of-accounts entry."""

    code: str = Field(
        min_length=1,
        max_length=16,
        description="Unique account code (e.g. '1000', '4000')",
    )
    name: str = Field(min_length=1, max_length=128)
    account_type: AccountType
    description: str | None = Field(default=None, max_length=2048)
    parent_code: str | None = Field(default=None, max_length=16)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("code")
    @classmethod
    def _strip_code(cls, v: str) -> str:
        return v.strip()


class FinancialAccountUpdate(AppBaseModel):
    """Payload for partially updating an account. All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2048)
    parent_code: str | None = Field(default=None, max_length=16)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class FinancialAccountSummary(AppBaseModel):
    """Lightweight account representation embedded inside JournalEntryResponse."""

    id: UUID
    code: str
    name: str
    account_type: AccountType
    normal_balance: AccountNormalBalance


class FinancialAccountResponse(AppBaseModel):
    """
    Full account representation.

    `calculated_balance` is populated by the route handler after calling
    LedgerService.get_account_balance. It is not stored on the model — the
    schema accepts it as an optional field with a default of Decimal("0")
    so the response is valid even when the caller omits it.
    """

    id: UUID
    code: str
    name: str
    account_type: AccountType
    normal_balance: AccountNormalBalance
    description: str | None
    parent_code: str | None
    is_system: bool
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Injected by the route handler; not stored in the DB
    calculated_balance: Decimal = Field(default=Decimal("0"))


# Journal Entry

class JournalEntryCreate(AppBaseModel):
    """
    Payload for manually creating a journal entry (e.g., opening balance,
    manual adjustment). Most entries are created automatically by services.
    """

    debit_account_code: str = Field(min_length=1, max_length=16)
    credit_account_code: str = Field(min_length=1, max_length=16)
    amount: Decimal = Field(gt=Decimal("0"), decimal_places=4)
    transaction_type: TransactionType
    description: str = Field(min_length=1, max_length=2048)
    transaction_date: str = Field(
        description="Accounting date in YYYY-MM-DD format",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    reference_type: str | None = Field(default=None, max_length=64)
    reference_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode="after")
    def _different_accounts(self) -> "JournalEntryCreate":
        if self.debit_account_code == self.credit_account_code:
            raise ValueError("debit_account_code and credit_account_code must differ")
        return self


class JournalEntryResponse(AppBaseModel):
    """Full journal entry representation including related account summaries."""

    id: UUID
    debit_account_id: UUID
    credit_account_id: UUID
    amount: Decimal
    transaction_type: TransactionType
    reference_type: str | None
    reference_id: str | None
    description: str | None
    transaction_date: str
    is_reversed: bool
    reversal_of_id: UUID | None
    actor: str
    tenant_id: str
    created_at: datetime
    # Populated when the route handler eager-loads accounts
    debit_account: FinancialAccountSummary | None = None
    credit_account: FinancialAccountSummary | None = None


# Payment Method

class PaymentMethodCreate(AppBaseModel):
    """Payload for creating a payment method catalog entry."""

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    method_type: PaymentMethodType
    linked_account_code: str | None = Field(default=None, max_length=16)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("code")
    @classmethod
    def _upper_code(cls, v: str) -> str:
        """Normalise payment method codes to uppercase for consistency."""
        return v.strip().upper()


class PaymentMethodUpdate(AppBaseModel):
    """Payload for partially updating a payment method."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    linked_account_code: str | None = Field(default=None, max_length=16)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)


class PaymentMethodResponse(AppBaseModel):
    """Full payment method representation."""

    id: UUID
    code: str
    name: str
    method_type: PaymentMethodType
    linked_account_code: str | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


# Customer Debt

class CustomerDebtResponse(AppBaseModel):
    """
    Full debt representation.

    `outstanding_amount` is computed from the model property —
    `from_attributes=True` (inherited) allows Pydantic to read it directly
    from the ORM object.
    """

    id: UUID
    customer_id: UUID
    voucher_id: UUID | None
    original_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    status: DebtStatus
    due_date: str | None
    notes: str | None
    is_overdue: bool
    created_at: datetime
    updated_at: datetime


# Debt Payment

class DebtPaymentCreate(AppBaseModel):
    """Payload for recording a payment against an outstanding debt."""

    payment_method_code: str = Field(min_length=1, max_length=32)
    amount: Decimal = Field(gt=Decimal("0"), decimal_places=4)
    transaction_date: str = Field(
        description="Payment date in YYYY-MM-DD format",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    reference_number: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=2048)


class DebtPaymentResponse(AppBaseModel):
    """Full debt payment record."""

    id: UUID
    debt_id: UUID
    payment_method_id: UUID
    amount: Decimal
    reference_number: str | None
    notes: str | None
    actor: str
    journal_entry_id: UUID | None
    tenant_id: str
    created_at: datetime


# Account Balance

class AccountBalanceResponse(AppBaseModel):
    """
    Lightweight balance snapshot for a single account.

    Returned by GET /finance/accounts/{code}/balance.
    The `as_of_date` field echoes back the query parameter when provided.
    """

    account_code: str
    account_name: str
    balance: Decimal
    account_type: AccountType
    normal_balance: AccountNormalBalance
    as_of_date: str | None = Field(
        default=None,
        description="Date the balance was calculated as of (YYYY-MM-DD), or None for current",
    )
