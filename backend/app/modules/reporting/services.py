"""
Reporting service.

Provides cross-module aggregation queries for dashboards and management reports.
All queries go through the session directly (no service chaining) to keep report
queries efficient and avoid loading unnecessary ORM state.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.modules.reporting.schemas import (
    CustomerDebtReportRow,
    DashboardSummary,
    ExpenseSummaryRow,
    InventoryBalanceReportRow,
    ProductionReportRow,
    SalesSummaryRow,
)


class ReportingService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_inventory_balance_report(
        self,
        *,
        item_type=None,
        low_stock_only: bool = False,
    ) -> list[InventoryBalanceReportRow]:
        """
        Return current inventory balances for all non-deleted items.

        Optionally filtered by item_type or restricted to low-stock items only.
        """
        from sqlalchemy import select

        from app.modules.inventory.models import InventoryItem

        q = select(InventoryItem).where(InventoryItem.deleted_at.is_(None))
        if item_type is not None:
            q = q.where(InventoryItem.item_type == item_type)
        if low_stock_only:
            q = q.where(
                InventoryItem.reorder_level.is_not(None),
                InventoryItem.current_balance <= InventoryItem.reorder_level,
            )
        q = q.order_by(InventoryItem.code)

        result = await self._session.execute(q)
        items = result.scalars().all()

        return [
            InventoryBalanceReportRow(
                item_id=item.id,
                item_code=item.code,
                item_name=item.name,
                item_type=item.item_type,
                unit=item.unit,
                current_balance=item.current_balance,
                reorder_level=item.reorder_level,
                is_low_stock=item.is_low_stock,
            )
            for item in items
        ]

    async def get_sales_summary(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> list[SalesSummaryRow]:
        """
        Aggregate daily sales totals between start_date and end_date (inclusive).

        Returns one row per day that had at least one sale voucher.
        """
        from sqlalchemy import func, select

        from app.modules.vouchers.enums import VoucherStatus, VoucherType
        from app.modules.vouchers.models import Voucher

        q = (
            select(
                Voucher.sale_date,
                func.count(Voucher.id).label("voucher_count"),
                func.sum(Voucher.total_amount).label("total_amount"),
                func.sum(Voucher.paid_amount).label("total_paid"),
                func.sum(Voucher.total_amount - Voucher.paid_amount).label("total_outstanding"),
            )
            .where(Voucher.deleted_at.is_(None))
            .where(Voucher.voucher_type == VoucherType.SALE)
            .where(Voucher.status != VoucherStatus.CANCELLED)
            .where(Voucher.sale_date >= start_date)
            .where(Voucher.sale_date <= end_date)
            .group_by(Voucher.sale_date)
            .order_by(Voucher.sale_date)
        )
        result = await self._session.execute(q)
        rows = result.all()

        return [
            SalesSummaryRow(
                sale_date=row.sale_date,
                voucher_count=row.voucher_count,
                total_amount=Decimal(str(row.total_amount or "0")),
                total_paid=Decimal(str(row.total_paid or "0")),
                total_outstanding=Decimal(str(row.total_outstanding or "0")),
            )
            for row in rows
        ]

    async def get_expense_summary(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> list[ExpenseSummaryRow]:
        """
        Aggregate expense totals grouped by category between start_date and end_date.
        """
        from sqlalchemy import func, select

        from app.modules.expenses.models import Expense

        q = (
            select(
                Expense.category,
                func.count(Expense.id).label("expense_count"),
                func.sum(Expense.amount).label("total_amount"),
            )
            .where(Expense.deleted_at.is_(None))
            .where(Expense.expense_date >= start_date)
            .where(Expense.expense_date <= end_date)
            .group_by(Expense.category)
            .order_by(Expense.category)
        )
        result = await self._session.execute(q)

        return [
            ExpenseSummaryRow(
                category=row.category,
                expense_count=row.expense_count,
                total_amount=Decimal(str(row.total_amount or "0")),
            )
            for row in result.all()
        ]

    async def get_customer_debt_report(self) -> list[CustomerDebtReportRow]:
        """
        Return all customers with outstanding or partially-paid debts.

        Ordered by outstanding debt descending (highest debtors first).
        """
        from sqlalchemy import func, select

        from app.modules.customers.models import Customer
        from app.modules.finance.enums import DebtStatus
        from app.modules.finance.models import CustomerDebt

        q = (
            select(
                Customer.id,
                Customer.code,
                Customer.name,
                func.count(CustomerDebt.id).label("debt_count"),
                func.sum(CustomerDebt.original_amount).label("total_debt"),
                func.sum(
                    CustomerDebt.original_amount - CustomerDebt.paid_amount
                ).label("outstanding_debt"),
            )
            .join(CustomerDebt, CustomerDebt.customer_id == Customer.id)
            .where(Customer.deleted_at.is_(None))
            .where(CustomerDebt.deleted_at.is_(None))
            .where(
                CustomerDebt.status.in_(
                    [DebtStatus.OUTSTANDING, DebtStatus.PARTIALLY_PAID]
                )
            )
            .group_by(Customer.id, Customer.code, Customer.name)
            .order_by(
                func.sum(
                    CustomerDebt.original_amount - CustomerDebt.paid_amount
                ).desc()
            )
        )
        result = await self._session.execute(q)

        return [
            CustomerDebtReportRow(
                customer_id=row.id,
                customer_code=row.code,
                customer_name=row.name,
                total_debt=Decimal(str(row.total_debt or "0")),
                outstanding_debt=Decimal(str(row.outstanding_debt or "0")),
                debt_count=row.debt_count,
            )
            for row in result.all()
        ]

    async def get_production_report(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[ProductionReportRow]:
        """
        Return production batch summary optionally filtered by start_date range.

        Ordered by created_at descending (most recent first).
        """
        from sqlalchemy import select

        from app.modules.inventory.models import InventoryItem
        from app.modules.production.models import ProductionBatch

        q = (
            select(ProductionBatch, InventoryItem.name.label("output_name"))
            .join(InventoryItem, InventoryItem.id == ProductionBatch.output_item_id)
            .where(ProductionBatch.deleted_at.is_(None))
        )
        if start_date is not None:
            q = q.where(ProductionBatch.start_date >= start_date)
        if end_date is not None:
            q = q.where(ProductionBatch.end_date <= end_date)
        q = q.order_by(ProductionBatch.created_at.desc())

        result = await self._session.execute(q)

        return [
            ProductionReportRow(
                batch_number=row.ProductionBatch.batch_number,
                status=row.ProductionBatch.status,
                output_item_name=row.output_name,
                expected_output=row.ProductionBatch.expected_output,
                actual_output=row.ProductionBatch.actual_output,
                yield_percentage=row.ProductionBatch.yield_percentage,
                total_cost=row.ProductionBatch.total_cost,
                start_date=row.ProductionBatch.start_date,
                end_date=row.ProductionBatch.end_date,
            )
            for row in result.all()
        ]

    async def get_dashboard_summary(
        self, tenant_id: str = "default"
    ) -> DashboardSummary:
        """
        Return key metrics for the dashboard home screen.

        Covers: today's sales, today's expenses, outstanding debts,
        low-stock item count, and active production batches.
        """
        from sqlalchemy import func, select

        from app.common.utils.datetime import utcnow
        from app.modules.expenses.models import Expense
        from app.modules.finance.enums import DebtStatus
        from app.modules.finance.models import CustomerDebt
        from app.modules.inventory.models import InventoryItem
        from app.modules.production.enums import ProductionBatchStatus
        from app.modules.production.models import ProductionBatch
        from app.modules.vouchers.enums import VoucherStatus, VoucherType
        from app.modules.vouchers.models import Voucher

        today = utcnow().date().isoformat()
        month_start = utcnow().date().replace(day=1).isoformat()

        # Today's sales count and total amount (exclude cancelled vouchers)
        sales_q = select(
            func.count(Voucher.id),
            func.coalesce(func.sum(Voucher.total_amount), 0),
        ).where(
            Voucher.deleted_at.is_(None),
            Voucher.voucher_type == VoucherType.SALE,
            Voucher.status != VoucherStatus.CANCELLED,
            Voucher.sale_date == today,
        )
        sales_result = (await self._session.execute(sales_q)).one()

        # Today's total expenses
        exp_q = select(
            func.coalesce(func.sum(Expense.amount), 0)
        ).where(
            Expense.deleted_at.is_(None),
            Expense.expense_date == today,
        )
        today_expenses = (await self._session.execute(exp_q)).scalar_one()

        # This month's sales total (exclude cancelled vouchers)
        month_sales_q = select(
            func.coalesce(func.sum(Voucher.total_amount), 0),
        ).where(
            Voucher.deleted_at.is_(None),
            Voucher.voucher_type == VoucherType.SALE,
            Voucher.status != VoucherStatus.CANCELLED,
            Voucher.sale_date >= month_start,
        )
        this_month_sales = (await self._session.execute(month_sales_q)).scalar_one()

        # This month's total expenses
        month_exp_q = select(
            func.coalesce(func.sum(Expense.amount), 0)
        ).where(
            Expense.deleted_at.is_(None),
            Expense.expense_date >= month_start,
        )
        this_month_expenses = (await self._session.execute(month_exp_q)).scalar_one()

        # All-time total sales (exclude cancelled vouchers)
        all_time_sales_q = select(
            func.coalesce(func.sum(Voucher.total_amount), 0),
        ).where(
            Voucher.deleted_at.is_(None),
            Voucher.voucher_type == VoucherType.SALE,
            Voucher.status != VoucherStatus.CANCELLED,
        )
        all_time_sales = (await self._session.execute(all_time_sales_q)).scalar_one()

        # All-time total expenses
        all_time_exp_q = select(
            func.coalesce(func.sum(Expense.amount), 0)
        ).where(
            Expense.deleted_at.is_(None),
        )
        all_time_expenses = (await self._session.execute(all_time_exp_q)).scalar_one()

        # Outstanding debts count and total
        debt_q = select(
            func.count(CustomerDebt.id),
            func.coalesce(
                func.sum(CustomerDebt.original_amount - CustomerDebt.paid_amount), 0
            ),
        ).where(
            CustomerDebt.deleted_at.is_(None),
            CustomerDebt.status.in_(
                [DebtStatus.OUTSTANDING, DebtStatus.PARTIALLY_PAID]
            ),
        )
        debt_result = (await self._session.execute(debt_q)).one()

        # Low stock items
        low_q = select(func.count(InventoryItem.id)).where(
            InventoryItem.deleted_at.is_(None),
            InventoryItem.reorder_level.is_not(None),
            InventoryItem.current_balance <= InventoryItem.reorder_level,
        )
        low_stock: int = (await self._session.execute(low_q)).scalar_one()

        # Active (planned or in-progress) production batches
        prod_q = select(func.count(ProductionBatch.id)).where(
            ProductionBatch.deleted_at.is_(None),
            ProductionBatch.status.in_(
                [ProductionBatchStatus.PLANNED, ProductionBatchStatus.IN_PROGRESS]
            ),
        )
        active_prod: int = (await self._session.execute(prod_q)).scalar_one()

        return DashboardSummary(
            today_sales_count=sales_result[0],
            today_sales_amount=Decimal(str(sales_result[1])),
            today_expenses_amount=Decimal(str(today_expenses)),
            this_month_sales_amount=Decimal(str(this_month_sales)),
            this_month_expenses_amount=Decimal(str(this_month_expenses)),
            all_time_sales_amount=Decimal(str(all_time_sales)),
            all_time_expenses_amount=Decimal(str(all_time_expenses)),
            outstanding_debts_total=Decimal(str(debt_result[1])),
            outstanding_debts_count=debt_result[0],
            low_stock_items_count=low_stock,
            active_production_batches=active_prod,
        )
