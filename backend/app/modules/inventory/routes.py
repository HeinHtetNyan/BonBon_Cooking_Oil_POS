"""Inventory management endpoints."""

from __future__ import annotations

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.common.schemas.base import PaginatedResponse, SuccessResponse, ok, paginated
from app.common.utils.pagination import PaginationParams
from app.modules.auth.dependencies import get_current_active_user, require_role
from app.modules.inventory.dependencies import get_inventory_service
from app.modules.inventory.enums import InventoryItemType, MovementType, WeightUnit
from app.modules.inventory.schemas import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    InventorySnapshotCreate,
    InventorySnapshotResponse,
    MovementCreate,
    MovementResponse,
)
from app.modules.inventory.services import InventoryService
from app.modules.users.enums import UserRole
from app.modules.users.models import User

router = APIRouter(prefix="/inventory", tags=["Inventory"])

# Items


@router.get("/items", response_model=PaginatedResponse[InventoryItemResponse])
async def list_inventory_items(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[InventoryService, Depends(get_inventory_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    item_type: InventoryItemType | None = Query(default=None),
    low_stock: bool = Query(default=False, description="Filter to low-stock items only"),
) -> PaginatedResponse[InventoryItemResponse]:
    items, total = await service.list_items(
        pagination, item_type=item_type, low_stock=low_stock
    )
    return paginated(
        [InventoryItemResponse.model_validate(i) for i in items],
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
    )


@router.post(
    "/items",
    response_model=SuccessResponse[InventoryItemResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def create_inventory_item(
    data: InventoryItemCreate,
    service: Annotated[InventoryService, Depends(get_inventory_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[InventoryItemResponse]:
    _type_prefix = {"raw_material": "RM", "finished_oil": "FG", "packaging": "PKG"}
    raw = re.sub(r"[^A-Z0-9]", "", re.sub(r"\s+", "_", data.name.upper()))[:28]
    code = data.code or raw or _type_prefix.get(str(data.item_type), "ITEM")
    item = await service.create_item(
        code=code,
        name=data.name,
        item_type=data.item_type,
        unit=data.unit,
        description=data.description,
        purchase_date=data.purchase_date,
        reorder_level=data.reorder_level,
        reorder_quantity=data.reorder_quantity,
        actor=str(current_user.id),
    )
    if data.initial_quantity:
        await service.record_movement(
            item_id=item.id,
            movement_type=MovementType.OPENING_BALANCE,
            quantity=data.initial_quantity,
            unit=data.unit,
            unit_price=data.unit_cost,
            transaction_date=data.purchase_date,
            notes="Opening balance set on item creation",
            actor=str(current_user.id),
        )
        await service._session.refresh(item)
    return ok(InventoryItemResponse.model_validate(item))


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def delete_inventory_item(
    item_id: UUID,
    service: Annotated[InventoryService, Depends(get_inventory_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    await service.delete_item(item_id, actor=str(current_user.id))


@router.get("/items/{item_id}", response_model=SuccessResponse[InventoryItemResponse])
async def get_inventory_item(
    item_id: UUID,
    service: Annotated[InventoryService, Depends(get_inventory_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[InventoryItemResponse]:
    item = await service.get_item(item_id)
    return ok(InventoryItemResponse.model_validate(item))


@router.patch(
    "/items/{item_id}",
    response_model=SuccessResponse[InventoryItemResponse],
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def update_inventory_item(
    item_id: UUID,
    data: InventoryItemUpdate,
    service: Annotated[InventoryService, Depends(get_inventory_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[InventoryItemResponse]:
    item = await service.update_item(
        item_id,
        name=data.name,
        description=data.description,
        purchase_date=data.purchase_date,
        reorder_level=data.reorder_level,
        reorder_quantity=data.reorder_quantity,
        actor=str(current_user.id),
    )
    return ok(InventoryItemResponse.model_validate(item))


# Movements


@router.get(
    "/movements",
    response_model=PaginatedResponse[MovementResponse],
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def list_movements(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[InventoryService, Depends(get_inventory_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    item_id: UUID | None = Query(default=None),
    movement_type: MovementType | None = Query(default=None),
    start_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="YYYY-MM-DD"),
) -> PaginatedResponse[MovementResponse]:
    movements, total = await service.list_movements(
        pagination,
        item_id=item_id,
        movement_type=movement_type,
        start_date=start_date,
        end_date=end_date,
    )
    return paginated(
        [MovementResponse.model_validate(m) for m in movements],
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
    )


@router.post(
    "/movements",
    response_model=SuccessResponse[MovementResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def record_manual_movement(
    data: MovementCreate,
    service: Annotated[InventoryService, Depends(get_inventory_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[MovementResponse]:
    movement = await service.record_movement(
        item_id=data.item_id,
        movement_type=data.movement_type,
        quantity=data.quantity,
        unit=data.unit,
        unit_price=data.unit_price,
        transaction_date=data.transaction_date,
        reference_type=data.reference_type,
        reference_id=data.reference_id,
        notes=data.notes,
        actor=str(current_user.id),
    )
    return ok(MovementResponse.model_validate(movement))


@router.post(
    "/movements/{movement_id}/reverse",
    response_model=SuccessResponse[MovementResponse],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def reverse_movement(
    movement_id: UUID,
    service: Annotated[InventoryService, Depends(get_inventory_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    reason: str = Query(description="Reason for reversal"),
) -> SuccessResponse[MovementResponse]:
    reversal = await service.reverse_movement(
        movement_id,
        reason=reason,
        actor=str(current_user.id),
    )
    return ok(MovementResponse.model_validate(reversal))


# Snapshots


@router.post(
    "/snapshots",
    response_model=SuccessResponse[InventorySnapshotResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def create_snapshot(
    data: InventorySnapshotCreate,
    service: Annotated[InventoryService, Depends(get_inventory_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[InventorySnapshotResponse]:
    snapshot = await service.create_snapshot(
        item_id=data.item_id,
        snapshot_date=data.snapshot_date,
        actor=str(current_user.id),
        notes=data.notes,
    )
    return ok(InventorySnapshotResponse.model_validate(snapshot))
