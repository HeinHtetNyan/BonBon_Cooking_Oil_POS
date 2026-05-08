"""Expense module API routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.common.schemas.base import PaginatedResponse, SuccessResponse, ok, paginated
from app.modules.auth.dependencies import get_current_active_user, require_role
from app.modules.expenses.dependencies import get_expense_service
from app.modules.expenses.enums import ExpenseCategory, ExpenseStatus
from app.modules.expenses.schemas import (
    ExpenseApproveRequest,
    ExpenseCreate,
    ExpensePaymentCreate,
    ExpensePaymentResponse,
    ExpenseResponse,
    ExpenseUpdate,
)
from app.modules.expenses.services import ExpenseService
from app.modules.users.enums import UserRole
from app.modules.users.models import User

router = APIRouter(prefix="/expenses", tags=["Expenses"])


def _to_response(expense, payments) -> ExpenseResponse:
    return ExpenseResponse(
        id=expense.id,
        reference_number=expense.reference_number,
        category=expense.category,
        description=expense.description,
        amount=expense.amount,
        status=expense.status,
        expense_date=expense.expense_date,
        production_batch_id=expense.production_batch_id,
        notes=expense.notes,
        approved_by=expense.approved_by,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
        payments=[
            ExpensePaymentResponse(
                id=p.id,
                expense_id=p.expense_id,
                payment_method_id=p.payment_method_id,
                amount=p.amount,
                reference_number=p.reference_number,
                notes=p.notes,
                created_at=p.created_at,
            )
            for p in payments
        ],
    )


@router.get(
    "/",
    response_model=PaginatedResponse[ExpenseResponse],
    dependencies=[Depends(require_role(UserRole.ACCOUNTANT))],
)
async def list_expenses(
    service: Annotated[ExpenseService, Depends(get_expense_service)],
    category: Annotated[ExpenseCategory | None, Query()] = None,
    status: Annotated[ExpenseStatus | None, Query()] = None,
    start_date: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
    end_date: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PaginatedResponse[ExpenseResponse]:
    expenses, total = await service.list_expenses(
        category=category,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        per_page=per_page,
    )
    items = []
    for expense in expenses:
        payments = await service._payment_repo.get_by_expense(expense.id)
        items.append(_to_response(expense, payments))
    return paginated(items, page=page, per_page=per_page, total=total)


@router.post(
    "/",
    response_model=SuccessResponse[ExpenseResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.CASHIER))],
)
async def create_expense(
    data: ExpenseCreate,
    service: Annotated[ExpenseService, Depends(get_expense_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ExpenseResponse]:
    expense = await service.create_expense(
        data,
        actor=str(current_user.id),
        tenant_id=getattr(current_user, "tenant_id", "default"),
    )
    payments = await service._payment_repo.get_by_expense(expense.id)
    return ok(_to_response(expense, payments))


@router.get(
    "/{expense_id}",
    response_model=SuccessResponse[ExpenseResponse],
    dependencies=[Depends(require_role(UserRole.CASHIER))],
)
async def get_expense(
    expense_id: UUID,
    service: Annotated[ExpenseService, Depends(get_expense_service)],
) -> SuccessResponse[ExpenseResponse]:
    expense, payments = await service.get_expense_with_payments(expense_id)
    return ok(_to_response(expense, payments))


@router.patch(
    "/{expense_id}",
    response_model=SuccessResponse[ExpenseResponse],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def update_expense(
    expense_id: UUID,
    data: ExpenseUpdate,
    service: Annotated[ExpenseService, Depends(get_expense_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ExpenseResponse]:
    expense = await service.update_expense(expense_id, data, actor=str(current_user.id))
    payments = await service._payment_repo.get_by_expense(expense.id)
    return ok(_to_response(expense, payments))


@router.post(
    "/{expense_id}/approve",
    response_model=SuccessResponse[ExpenseResponse],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def approve_expense(
    expense_id: UUID,
    data: ExpenseApproveRequest,
    service: Annotated[ExpenseService, Depends(get_expense_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ExpenseResponse]:
    expense = await service.approve_expense(
        expense_id,
        approved=data.approved,
        notes=data.notes,
        actor=str(current_user.id),
    )
    payments = await service._payment_repo.get_by_expense(expense.id)
    return ok(_to_response(expense, payments))


@router.post(
    "/{expense_id}/payments",
    response_model=SuccessResponse[ExpensePaymentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.CASHIER))],
)
async def record_payment(
    expense_id: UUID,
    data: ExpensePaymentCreate,
    service: Annotated[ExpenseService, Depends(get_expense_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[ExpensePaymentResponse]:
    payment = await service.record_payment(
        expense_id,
        data,
        actor=str(current_user.id),
        tenant_id=getattr(current_user, "tenant_id", "default"),
    )
    return ok(
        ExpensePaymentResponse(
            id=payment.id,
            expense_id=payment.expense_id,
            payment_method_id=payment.payment_method_id,
            amount=payment.amount,
            reference_number=payment.reference_number,
            notes=payment.notes,
            created_at=payment.created_at,
        )
    )
