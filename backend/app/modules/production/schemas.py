"""Production module Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.common.schemas.base import AppBaseModel
from app.modules.inventory.enums import WeightUnit
from app.modules.production.enums import ProductionBatchStatus


class MaterialUsageCreate(AppBaseModel):
    material_item_id: UUID
    planned_quantity: Decimal = Field(gt=0)
    unit: WeightUnit
    unit_cost: Decimal | None = Field(default=None, ge=0)


class MaterialUsageResponse(AppBaseModel):
    id: UUID
    batch_id: UUID
    material_item_id: UUID
    planned_quantity: Decimal
    actual_quantity: Decimal | None
    unit: str
    unit_cost: Decimal | None


class ProductionOutputCreate(AppBaseModel):
    output_item_id: UUID
    quantity: Decimal = Field(gt=0)
    unit: WeightUnit
    notes: str | None = None


class ProductionOutputResponse(AppBaseModel):
    id: UUID
    batch_id: UUID
    output_item_id: UUID
    quantity: Decimal
    unit: str
    notes: str | None


class ProductionBatchCreate(AppBaseModel):
    output_item_id: UUID
    expected_output: Decimal = Field(gt=0)
    output_unit: WeightUnit
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    material_usages: list[MaterialUsageCreate] = Field(min_length=1)
    notes: str | None = None


class ProductionBatchUpdate(AppBaseModel):
    notes: str | None = None
    total_labour_cost: Decimal | None = Field(default=None, ge=0)
    total_overhead_cost: Decimal | None = Field(default=None, ge=0)


class ProductionBatchResponse(AppBaseModel):
    id: UUID
    batch_number: str
    status: ProductionBatchStatus
    output_item_id: UUID
    expected_output: Decimal
    actual_output: Decimal | None
    output_unit: str
    total_material_cost: Decimal
    total_labour_cost: Decimal
    total_overhead_cost: Decimal
    total_cost: Decimal
    yield_percentage: Decimal | None
    start_date: str | None
    end_date: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    material_usages: list[MaterialUsageResponse] = Field(default_factory=list)
    outputs: list[ProductionOutputResponse] = Field(default_factory=list)


class ActualMaterialUsage(AppBaseModel):
    usage_id: UUID
    actual_quantity: Decimal = Field(gt=0)


class OutputEntry(AppBaseModel):
    output_item_id: UUID
    quantity: Decimal = Field(gt=0)
    unit: WeightUnit


class CompleteBatchRequest(AppBaseModel):
    """Request body for completing a production batch."""

    actual_material_usages: list[ActualMaterialUsage]
    outputs: list[OutputEntry]
    labour_cost: Decimal = Field(default=Decimal("0"), ge=0)
    overhead_cost: Decimal = Field(default=Decimal("0"), ge=0)


class CancelBatchRequest(AppBaseModel):
    reason: str = Field(min_length=1, max_length=500)
