"""Customer Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.common.schemas.base import AppBaseModel
from app.modules.customers.enums import CustomerStatus, CustomerType


class CustomerCreate(AppBaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = None
    customer_type: CustomerType
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=4)
    notes: str | None = None


class CustomerUpdate(AppBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = None
    customer_type: CustomerType | None = None
    credit_limit: Decimal | None = Field(default=None, ge=0)
    status: CustomerStatus | None = None
    notes: str | None = None


class CustomerResponse(AppBaseModel):
    id: UUID
    code: str
    name: str
    phone: str | None
    address: str | None
    customer_type: CustomerType
    status: CustomerStatus
    credit_limit: Decimal
    credit_balance: Decimal
    available_credit: Decimal
    total_debt: Decimal = Decimal("0")
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CustomerSummary(AppBaseModel):
    id: UUID
    code: str
    name: str
    phone: str | None
    customer_type: CustomerType
    status: CustomerStatus
    credit_balance: Decimal


class CustomerSearchParams(AppBaseModel):
    q: str | None = Field(default=None, description="Search by name, phone, or code")
    customer_type: CustomerType | None = None
    status: CustomerStatus | None = None
