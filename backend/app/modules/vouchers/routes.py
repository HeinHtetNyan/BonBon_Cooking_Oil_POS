"""Voucher REST endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query

from app.common.schemas.base import PaginatedResponse, SuccessResponse, ok, paginated
from app.modules.auth.dependencies import get_current_active_user, require_role
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.vouchers.dependencies import get_voucher_service
from app.modules.vouchers.enums import VoucherStatus, VoucherType
from app.modules.vouchers.schemas import (
    VoucherCreate,
    VoucherItemCreate,
    VoucherPaymentSimple,
    VoucherResponse,
    VoucherUpdate,
)
from app.modules.vouchers.services import VoucherService

router = APIRouter(prefix="/vouchers", tags=["Vouchers"])


def _to_response(voucher) -> VoucherResponse:
    return VoucherResponse.model_validate(voucher)


@router.get("", response_model=PaginatedResponse[VoucherResponse])
async def list_vouchers(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[VoucherService, Depends(get_voucher_service)],
    status: VoucherStatus | None = Query(default=None),
    customer_id: UUID | None = Query(default=None),
    voucher_type: VoucherType | None = Query(default=None),
    start_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[VoucherResponse]:
    items, total = await service.list_vouchers(
        status=status,
        customer_id=customer_id,
        voucher_type=voucher_type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        per_page=per_page,
    )
    return paginated(
        [_to_response(v) for v in items],
        page=page,
        per_page=per_page,
        total=total,
    )


@router.post(
    "",
    response_model=SuccessResponse[VoucherResponse],
    status_code=201,
    dependencies=[Depends(require_role(UserRole.CASHIER))],
)
async def create_voucher(
    data: VoucherCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[VoucherService, Depends(get_voucher_service)],
) -> SuccessResponse[VoucherResponse]:
    voucher = await service.create_voucher(data, actor=str(current_user.id))
    return ok(_to_response(voucher))


@router.get("/number/{voucher_number}", response_model=SuccessResponse[VoucherResponse])
async def get_voucher_by_number(
    voucher_number: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[VoucherService, Depends(get_voucher_service)],
) -> SuccessResponse[VoucherResponse]:
    voucher = await service.get_by_number(voucher_number)
    return ok(_to_response(voucher))


@router.get("/{voucher_id}", response_model=SuccessResponse[VoucherResponse])
async def get_voucher(
    voucher_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[VoucherService, Depends(get_voucher_service)],
) -> SuccessResponse[VoucherResponse]:
    voucher = await service.get_voucher(voucher_id)
    return ok(_to_response(voucher))


@router.patch(
    "/{voucher_id}",
    response_model=SuccessResponse[VoucherResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def update_voucher(
    voucher_id: UUID,
    data: VoucherUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[VoucherService, Depends(get_voucher_service)],
) -> SuccessResponse[VoucherResponse]:
    """Update voucher metadata (notes, customer, sale_date, extra_charges). Requires ADMIN+."""
    voucher = await service.update_voucher(voucher_id, data, actor=str(current_user.id))
    return ok(_to_response(voucher))


@router.put(
    "/{voucher_id}/items",
    response_model=SuccessResponse[VoucherResponse],
    dependencies=[Depends(require_role(UserRole.CASHIER))],
)
async def update_voucher_items(
    voucher_id: UUID,
    items: list[VoucherItemCreate],
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[VoucherService, Depends(get_voucher_service)],
) -> SuccessResponse[VoucherResponse]:
    """Replace all line items on a DRAFT voucher. Recalculates totals."""
    voucher = await service.update_items(voucher_id, items, actor=str(current_user.id))
    return ok(_to_response(voucher))


@router.post(
    "/{voucher_id}/payments",
    response_model=SuccessResponse[VoucherResponse],
    dependencies=[Depends(require_role(UserRole.CASHIER))],
)
async def record_voucher_payment(
    voucher_id: UUID,
    data: VoucherPaymentSimple,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[VoucherService, Depends(get_voucher_service)],
) -> SuccessResponse[VoucherResponse]:
    """Record a payment against a confirmed voucher."""
    voucher = await service.record_payment(voucher_id, data, actor=str(current_user.id))
    return ok(_to_response(voucher))


@router.post(
    "/{voucher_id}/confirm",
    response_model=SuccessResponse[VoucherResponse],
    dependencies=[Depends(require_role(UserRole.CASHIER))],
)
async def confirm_voucher(
    voucher_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[VoucherService, Depends(get_voucher_service)],
) -> SuccessResponse[VoucherResponse]:
    """Confirm a DRAFT voucher. Triggers inventory SALE_OUT and ledger entries."""
    voucher = await service.confirm_voucher(voucher_id, actor=str(current_user.id))
    return ok(_to_response(voucher))


@router.post(
    "/{voucher_id}/void",
    response_model=SuccessResponse[VoucherResponse],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def void_voucher(
    voucher_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[VoucherService, Depends(get_voucher_service)],
    reason: str = Body(embed=True, description="Reason for voiding this voucher"),
) -> SuccessResponse[VoucherResponse]:
    """
    Void a voucher and reverse all inventory and ledger effects.
    Requires MANAGER role or above.
    """
    voucher = await service.void_voucher(
        voucher_id, reason, actor=str(current_user.id)
    )
    return ok(_to_response(voucher))
