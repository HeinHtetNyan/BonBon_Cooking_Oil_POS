"""Inventory Pydantic v2 schemas."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from app.common.schemas.base import AppBaseModel
from app.modules.inventory.enums import (
    InventoryItemType,
    InventoryMovementStatus,
    MovementType,
    WeightUnit,
)

_ITEM_CODE_RE = re.compile(r"^[A-Z0-9_\-]+$")


class InventoryItemCreate(AppBaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    item_type: InventoryItemType
    unit: WeightUnit
    description: str | None = None
    purchase_date: str | None = Field(default=None, description="YYYY-MM-DD")
    reorder_level: Decimal | None = Field(default=None, ge=0)
    reorder_quantity: Decimal | None = Field(default=None, ge=0)
    initial_quantity: Decimal | None = Field(default=None, gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)

    @field_validator("code")
    @classmethod
    def code_must_be_uppercase(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.upper()
        if not _ITEM_CODE_RE.match(v):
            raise ValueError(
                "Item code must contain only uppercase letters, digits, underscores, or hyphens"
            )
        return v


class InventoryItemUpdate(AppBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    purchase_date: str | None = Field(default=None, description="YYYY-MM-DD")
    reorder_level: Decimal | None = Field(default=None, ge=0)
    reorder_quantity: Decimal | None = Field(default=None, ge=0)


class InventoryItemResponse(AppBaseModel):
    id: UUID
    code: str
    name: str
    item_type: InventoryItemType
    unit: WeightUnit
    current_balance: Decimal
    purchase_date: str | None
    reorder_level: Decimal | None
    reorder_quantity: Decimal | None
    is_low_stock: bool
    created_at: datetime
    updated_at: datetime


class MovementCreate(AppBaseModel):
    item_id: UUID
    movement_type: MovementType
    quantity: Decimal = Field(gt=0)
    unit: WeightUnit
    unit_price: Decimal | None = Field(default=None, ge=0)
    transaction_date: str | None = Field(default=None, description="YYYY-MM-DD")
    reference_type: str | None = None
    reference_id: str | None = None
    notes: str | None = None


class MovementResponse(AppBaseModel):
    id: UUID
    item_id: UUID
    movement_type: MovementType
    quantity: Decimal
    unit: WeightUnit
    quantity_in_canonical_unit: Decimal
    balance_after: Decimal
    unit_price: Decimal | None
    transaction_date: str | None
    reference_type: str | None
    reference_id: str | None
    notes: str | None
    status: InventoryMovementStatus
    actor: str
    created_at: datetime


class InventorySnapshotCreate(AppBaseModel):
    item_id: UUID
    snapshot_date: str = Field(description="YYYY-MM-DD")
    notes: str | None = None


class InventorySnapshotResponse(AppBaseModel):
    id: UUID
    item_id: UUID
    snapshot_date: str
    balance: Decimal
    unit: str
    created_at: datetime
