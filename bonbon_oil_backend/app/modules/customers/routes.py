"""Customer management endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.common.schemas.base import PaginatedResponse, SuccessResponse, ok, paginated
from app.common.utils.pagination import PaginationParams
from app.modules.auth.dependencies import get_current_active_user, require_role
from app.modules.customers.dependencies import get_customer_service
from app.modules.customers.enums import CustomerStatus, CustomerType
from app.modules.customers.models import Customer
from app.modules.customers.schemas import (
    CustomerCreate,
    CustomerResponse,
    CustomerSummary,
    CustomerUpdate,
)
from app.modules.customers.services import CustomerService
from app.modules.users.enums import UserRole
from app.modules.users.models import User

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("", response_model=PaginatedResponse[CustomerResponse])
async def list_customers(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[CustomerService, Depends(get_customer_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    q: str | None = Query(default=None, description="Search by name, phone, or code"),
    customer_type: CustomerType | None = Query(default=None),
    customer_status: CustomerStatus | None = Query(default=None, alias="status"),
) -> PaginatedResponse[CustomerResponse]:
    customers, total = await service.list_customers(
        pagination,
        q=q,
        customer_type=customer_type,
        status=customer_status,
    )
    return paginated(
        [CustomerResponse.model_validate(c) for c in customers],
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
    )


@router.post(
    "",
    response_model=SuccessResponse[CustomerResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.CASHIER))],
)
async def create_customer(
    data: CustomerCreate,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[CustomerResponse]:
    customer = await service.create_customer(data, actor=str(current_user.id))
    return ok(CustomerResponse.model_validate(customer))


@router.get("/search", response_model=SuccessResponse[list[CustomerSummary]])
async def search_customers(
    service: Annotated[CustomerService, Depends(get_customer_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    q: str = Query(description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
) -> SuccessResponse[list[CustomerSummary]]:
    customers = await service.search_customers(q, limit=limit)
    return ok([CustomerSummary.model_validate(c) for c in customers])


@router.get("/{customer_id}", response_model=SuccessResponse[CustomerResponse])
async def get_customer(
    customer_id: UUID,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[CustomerResponse]:
    customer = await service.get_customer(customer_id)
    debt_summary = await service.get_debt_summary(customer_id)

    response = CustomerResponse.model_validate(customer)
    response.total_debt = debt_summary["outstanding_debt"]
    return ok(response)


@router.patch(
    "/{customer_id}",
    response_model=SuccessResponse[CustomerResponse],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def update_customer(
    customer_id: UUID,
    data: CustomerUpdate,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[CustomerResponse]:
    customer = await service.update_customer(
        customer_id, data, actor=str(current_user.id)
    )
    return ok(CustomerResponse.model_validate(customer))


@router.delete(
    "/{customer_id}",
    response_model=SuccessResponse[CustomerResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def deactivate_customer(
    customer_id: UUID,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[CustomerResponse]:
    customer = await service.deactivate_customer(
        customer_id, actor=str(current_user.id)
    )
    return ok(CustomerResponse.model_validate(customer))


@router.get(
    "/{customer_id}/debts",
    response_model=SuccessResponse[dict],
    dependencies=[Depends(require_role(UserRole.CASHIER))],
)
async def get_customer_debts(
    customer_id: UUID,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[dict]:
    summary = await service.get_debt_summary(customer_id)
    return ok(summary)
