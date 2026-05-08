"""Expense module request/response schemas."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID
from datetime import datetime

from pydantic import Field, field_validator

from app.common.schemas.base import AppBaseModel
from app.modules.expenses.enums import ExpenseCategory, ExpenseStatus


class ExpenseCreate(AppBaseModel):
    category: ExpenseCategory
    description: str = Field(min_length=1, max_length=512)
    amount: Decimal = Field(gt=0, decimal_places=4)
    expense_date: str = Field(
        description="Expense date in YYYY-MM-DD format",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    production_batch_id: UUID | None = None
    notes: str | None = None
    payment_method_code: str | None = None  # if paid immediately at creation
    payment_reference: str | None = None


class ExpenseUpdate(AppBaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=512)
    category: ExpenseCategory | None = None
    notes: str | None = None


class ExpenseApproveRequest(AppBaseModel):
    approved: bool
    notes: str | None = None


class ExpensePaymentCreate(AppBaseModel):
    payment_method_code: str = Field(min_length=1)
    amount: Decimal = Field(gt=0, decimal_places=4)
    reference_number: str | None = None
    notes: str | None = None


class ExpensePaymentResponse(AppBaseModel):
    id: UUID
    expense_id: UUID
    payment_method_id: UUID
    amount: Decimal
    reference_number: str | None
    notes: str | None
    created_at: datetime


class ExpenseResponse(AppBaseModel):
    id: UUID
    reference_number: str
    category: ExpenseCategory
    description: str
    amount: Decimal
    status: ExpenseStatus
    expense_date: str
    production_batch_id: UUID | None
    notes: str | None
    approved_by: str | None
    created_at: datetime
    updated_at: datetime
    payments: list[ExpensePaymentResponse] = Field(default_factory=list)
