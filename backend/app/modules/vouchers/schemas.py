"""Voucher Pydantic schemas."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, computed_field, field_validator

from app.common.schemas.base import AppBaseModel
from app.modules.vouchers.enums import VoucherStatus, VoucherType


class VoucherExtraCharge(AppBaseModel):
    description: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0, decimal_places=4)


class VoucherItemCreate(AppBaseModel):
    inventory_item_id: UUID
    quantity: Decimal = Field(gt=0, decimal_places=6)
    unit: str = Field(min_length=1, max_length=16)
    # price_per_viss is the only pricing input; per-unit price is derived from it.
    price_per_viss: Decimal = Field(ge=0, decimal_places=4)
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=2)
    notes: str | None = None

    @field_validator("unit")
    @classmethod
    def _validate_unit(cls, v: str) -> str:
        norm = v.lower()
        if norm not in ("viss", "tical"):
            raise ValueError(
                f"unit must be 'viss' or 'tical' for oil pricing, got '{v}'"
            )
        return norm


class VoucherItemResponse(AppBaseModel):
    id: UUID
    inventory_item_id: UUID
    quantity: Decimal
    unit: str
    # price_per_viss: the user-facing input price (oil always priced per viss)
    price_per_viss: Decimal = Decimal("0")
    # unit_price: effective per-unit price computed from price_per_viss + unit
    unit_price: Decimal
    discount_percent: Decimal
    line_total: Decimal
    notes: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def calculated_unit_price(self) -> Decimal:
        """Effective per-unit price derived from price_per_viss and unit."""
        return self.unit_price

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_price(self) -> Decimal:
        """Alias for line_total; included per API response spec."""
        return self.line_total


class VoucherPaymentCreate(AppBaseModel):
    payment_method_id: UUID
    amount: Decimal = Field(gt=0, decimal_places=4)
    reference_number: str | None = None
    notes: str | None = None


class VoucherPaymentSimple(AppBaseModel):
    payment_method_code: str = Field(min_length=1, max_length=32, description="PaymentMethod.code (e.g. 'CASH', 'KBZPAY')")
    amount: Decimal = Field(gt=0, decimal_places=4)
    reference_number: str | None = None
    notes: str | None = None


class VoucherPaymentResponse(AppBaseModel):
    id: UUID
    payment_method_id: UUID | None = None
    amount: Decimal
    reference_number: str | None = None
    created_at: datetime


class VoucherCreate(AppBaseModel):
    customer_id: UUID | None = None
    voucher_type: VoucherType = VoucherType.SALE
    sale_date: date
    items: list[VoucherItemCreate] = Field(min_length=1)
    payments: list[VoucherPaymentCreate] = Field(default_factory=list)
    extra_charges: list[VoucherExtraCharge] = Field(default_factory=list)
    notes: str | None = None
    auto_confirm: bool = False

    @field_validator("sale_date", mode="before")
    @classmethod
    def _parse_date(cls, v: object) -> date:
        if isinstance(v, date):
            return v
        from datetime import datetime

        return datetime.strptime(str(v), "%Y-%m-%d").date()


class VoucherUpdate(AppBaseModel):
    notes: str | None = None
    customer_id: UUID | None = None
    sale_date: date | None = None
    extra_charges: list[VoucherExtraCharge] | None = None

    @field_validator("sale_date", mode="before")
    @classmethod
    def _parse_date(cls, v: object) -> date | None:
        if v is None:
            return v
        if isinstance(v, date):
            return v
        from datetime import datetime
        return datetime.strptime(str(v), "%Y-%m-%d").date()


class VoucherResponse(AppBaseModel):
    id: UUID
    voucher_number: str
    voucher_type: VoucherType
    status: VoucherStatus
    customer_id: UUID | None
    sale_date: str
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    extra_charges: list[VoucherExtraCharge] = Field(default_factory=list)
    total_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    notes: str | None
    version_number: int = 1
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[VoucherItemResponse] = Field(default_factory=list)
    payments: list[VoucherPaymentResponse] = Field(default_factory=list)

    @field_validator("outstanding_amount", mode="before")
    @classmethod
    def _clamp_outstanding(cls, v: object) -> object:
        from decimal import Decimal
        try:
            return max(Decimal("0"), Decimal(str(v)))
        except Exception:
            return Decimal("0")

    @field_validator("extra_charges", mode="before")
    @classmethod
    def _parse_extra_charges(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return v or []
