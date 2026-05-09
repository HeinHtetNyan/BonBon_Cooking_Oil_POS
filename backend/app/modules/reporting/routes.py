"""Reporting module API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.common.schemas.base import SuccessResponse, ok
from app.modules.auth.dependencies import get_current_active_user, require_role
from app.modules.inventory.enums import InventoryItemType
from app.modules.reporting.dependencies import get_reporting_service
from app.modules.reporting.schemas import (
    CustomerDebtReportRow,
    DashboardSummary,
    ExpenseSummaryRow,
    InventoryBalanceReportRow,
    ProductionReportRow,
    SalesSummaryRow,
)
from app.modules.reporting.services import ReportingService
from app.modules.users.enums import UserRole
from app.modules.users.models import User

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get(
    "/dashboard",
    response_model=SuccessResponse[DashboardSummary],
    dependencies=[Depends(get_current_active_user)],
)
async def get_dashboard(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[DashboardSummary]:
    """Key metrics for the dashboard home screen. Accessible to all authenticated users."""
    summary = await service.get_dashboard_summary(
        tenant_id=getattr(current_user, "tenant_id", "default")
    )
    return ok(summary)


@router.get(
    "/inventory/balance",
    response_model=SuccessResponse[list[InventoryBalanceReportRow]],
    dependencies=[Depends(require_role(UserRole.WAREHOUSE))],
)
async def get_inventory_balance(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    item_type: Annotated[InventoryItemType | None, Query()] = None,
    low_stock_only: Annotated[bool, Query(description="Only return items below reorder level")] = False,
) -> SuccessResponse[list[InventoryBalanceReportRow]]:
    """Current inventory balances. Requires WAREHOUSE role or higher."""
    rows = await service.get_inventory_balance_report(
        item_type=item_type,
        low_stock_only=low_stock_only,
    )
    return ok(rows)


@router.get(
    "/sales/summary",
    response_model=SuccessResponse[list[SalesSummaryRow]],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def get_sales_summary(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    start_date: Annotated[str, Query(description="Start date YYYY-MM-DD")],
    end_date: Annotated[str, Query(description="End date YYYY-MM-DD")],
) -> SuccessResponse[list[SalesSummaryRow]]:
    """Daily sales summary between two dates. Requires ACCOUNTANT role or higher."""
    rows = await service.get_sales_summary(start_date=start_date, end_date=end_date)
    return ok(rows)


@router.get(
    "/expenses/summary",
    response_model=SuccessResponse[list[ExpenseSummaryRow]],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def get_expense_summary(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    start_date: Annotated[str, Query(description="Start date YYYY-MM-DD")],
    end_date: Annotated[str, Query(description="End date YYYY-MM-DD")],
) -> SuccessResponse[list[ExpenseSummaryRow]]:
    """Expense totals grouped by category between two dates. Requires ACCOUNTANT role or higher."""
    rows = await service.get_expense_summary(start_date=start_date, end_date=end_date)
    return ok(rows)


@router.get(
    "/customers/debts",
    response_model=SuccessResponse[list[CustomerDebtReportRow]],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def get_customer_debt_report(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
) -> SuccessResponse[list[CustomerDebtReportRow]]:
    """All customers with outstanding or partially-paid debts. Requires ACCOUNTANT role or higher."""
    rows = await service.get_customer_debt_report()
    return ok(rows)


@router.get(
    "/production",
    response_model=SuccessResponse[list[ProductionReportRow]],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def get_production_report(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    start_date: Annotated[str | None, Query(description="Filter start date YYYY-MM-DD")] = None,
    end_date: Annotated[str | None, Query(description="Filter end date YYYY-MM-DD")] = None,
) -> SuccessResponse[list[ProductionReportRow]]:
    """Production batch report with yield and cost data. Requires MANAGER role or higher."""
    rows = await service.get_production_report(start_date=start_date, end_date=end_date)
    return ok(rows)
