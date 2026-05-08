"""Production batch management endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.common.schemas.base import PaginatedResponse, SuccessResponse, ok, paginated
from app.common.utils.pagination import PaginationParams
from app.modules.auth.dependencies import get_current_active_user, require_role
from app.modules.production.dependencies import get_production_service
from app.modules.production.enums import ProductionBatchStatus
from app.modules.production.schemas import (
    CancelBatchRequest,
    CompleteBatchRequest,
    ProductionBatchCreate,
    ProductionBatchResponse,
    ProductionBatchUpdate,
    MaterialUsageResponse,
    ProductionOutputResponse,
)
from app.modules.production.services import ProductionBatchService
from app.modules.users.enums import UserRole
from app.modules.users.models import User

router = APIRouter(prefix="/production", tags=["Production"])


def _build_batch_response(batch) -> ProductionBatchResponse:
    """Build ProductionBatchResponse including nested usages and outputs."""
    usages = [MaterialUsageResponse.model_validate(u) for u in (batch.material_usages or [])]
    outputs = [ProductionOutputResponse.model_validate(o) for o in (batch.outputs or [])]
    data = ProductionBatchResponse.model_validate(batch)
    data.material_usages = usages
    data.outputs = outputs
    return data


@router.get(
    "/batches",
    response_model=PaginatedResponse[ProductionBatchResponse],
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def list_batches(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[ProductionBatchService, Depends(get_production_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    batch_status: ProductionBatchStatus | None = Query(default=None, alias="status"),
) -> PaginatedResponse[ProductionBatchResponse]:
    batches, total = await service.list_batches(pagination, status_filter=batch_status)
    return paginated(
        [_build_batch_response(b) for b in batches],
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
    )


@router.post(
    "/batches",
    response_model=SuccessResponse[ProductionBatchResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def create_batch(
    data: ProductionBatchCreate,
    service: Annotated[ProductionBatchService, Depends(get_production_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ProductionBatchResponse]:
    batch = await service.create_batch(data, actor=str(current_user.id))
    # Re-fetch with relationships
    batch = await service.get_batch(batch.id)
    return ok(_build_batch_response(batch))


@router.get("/batches/{batch_id}", response_model=SuccessResponse[ProductionBatchResponse])
async def get_batch(
    batch_id: UUID,
    service: Annotated[ProductionBatchService, Depends(get_production_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ProductionBatchResponse]:
    batch = await service.get_batch(batch_id)
    return ok(_build_batch_response(batch))


@router.patch(
    "/batches/{batch_id}",
    response_model=SuccessResponse[ProductionBatchResponse],
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def update_batch(
    batch_id: UUID,
    data: ProductionBatchUpdate,
    service: Annotated[ProductionBatchService, Depends(get_production_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ProductionBatchResponse]:
    await service.update_batch(batch_id, data, actor=str(current_user.id))
    batch = await service.get_batch(batch_id)
    return ok(_build_batch_response(batch))


@router.post(
    "/batches/{batch_id}/start",
    response_model=SuccessResponse[ProductionBatchResponse],
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def start_batch(
    batch_id: UUID,
    service: Annotated[ProductionBatchService, Depends(get_production_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ProductionBatchResponse]:
    await service.start_batch(batch_id, actor=str(current_user.id))
    batch = await service.get_batch(batch_id)
    return ok(_build_batch_response(batch))


@router.post(
    "/batches/{batch_id}/complete",
    response_model=SuccessResponse[ProductionBatchResponse],
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def complete_batch(
    batch_id: UUID,
    data: CompleteBatchRequest,
    service: Annotated[ProductionBatchService, Depends(get_production_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ProductionBatchResponse]:
    actual_usages = [
        {"usage_id": u.usage_id, "actual_quantity": u.actual_quantity}
        for u in data.actual_material_usages
    ]
    outputs = [
        {
            "output_item_id": o.output_item_id,
            "quantity": o.quantity,
            "unit": o.unit,
        }
        for o in data.outputs
    ]
    await service.complete_batch(
        batch_id,
        actual_material_usages=actual_usages,
        outputs=outputs,
        labour_cost=data.labour_cost,
        overhead_cost=data.overhead_cost,
        actor=str(current_user.id),
    )
    batch = await service.get_batch(batch_id)
    return ok(_build_batch_response(batch))


@router.post(
    "/batches/{batch_id}/cancel",
    response_model=SuccessResponse[ProductionBatchResponse],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def cancel_batch(
    batch_id: UUID,
    data: CancelBatchRequest,
    service: Annotated[ProductionBatchService, Depends(get_production_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ProductionBatchResponse]:
    await service.cancel_batch(
        batch_id,
        reason=data.reason,
        actor=str(current_user.id),
    )
    batch = await service.get_batch(batch_id)
    return ok(_build_batch_response(batch))
