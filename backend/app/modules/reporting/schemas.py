"""Reporting module schemas."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import Query

from app.common.schemas.base import AppBaseModel
from app.modules.inventory.enums import InventoryItemType, WeightUnit


class DateRangeParams:
    """FastAPI Depends class for date range query parameters."""

    def __init__(
        self,
        start_date: str | None = Query(None, description="Start date in YYYY-MM-DD format"),
        end_date: str | None = Query(None, description="End date in YYYY-MM-DD format"),
    ) -> None:
        self.start_date = start_date
        self.end_date = end_date


class InventoryBalanceReportRow(AppBaseModel):
    item_id: UUID
    item_code: str
    item_name: str
    item_type: InventoryItemType
    unit: WeightUnit
    current_balance: Decimal
    reorder_level: Decimal | None
    is_low_stock: bool


class SalesSummaryRow(AppBaseModel):
    sale_date: str
    voucher_count: int
    total_amount: Decimal
    total_paid: Decimal
    total_outstanding: Decimal


class ExpenseSummaryRow(AppBaseModel):
    category: str
    expense_count: int
    total_amount: Decimal


class CustomerDebtReportRow(AppBaseModel):
    customer_id: UUID
    customer_code: str
    customer_name: str
    total_debt: Decimal
    outstanding_debt: Decimal
    debt_count: int


class ProductionReportRow(AppBaseModel):
    batch_number: str
    status: str
    output_item_name: str
    expected_output: Decimal
    actual_output: Decimal | None
    yield_percentage: Decimal | None
    total_cost: Decimal
    start_date: str | None
    end_date: str | None


class DashboardSummary(AppBaseModel):
    today_sales_count: int
    today_sales_amount: Decimal
    today_expenses_amount: Decimal
    this_month_sales_amount: Decimal
    this_month_expenses_amount: Decimal
    all_time_sales_amount: Decimal
    all_time_expenses_amount: Decimal
    outstanding_debts_total: Decimal
    outstanding_debts_count: int
    low_stock_items_count: int
    active_production_batches: int
