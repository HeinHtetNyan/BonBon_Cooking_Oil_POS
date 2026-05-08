"""Expense module repositories."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.repositories.base import BaseRepository
from app.modules.expenses.enums import ExpenseCategory
from app.modules.expenses.models import Expense, ExpensePayment


class ExpenseRepository(BaseRepository[Expense]):
    model = Expense

    async def get_by_reference(self, ref: str) -> Expense | None:
        """Fetch a non-deleted expense by its unique reference number."""
        q = self._base_query().where(Expense.reference_number == ref)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def next_reference_number(self) -> str:
        """
        Generate the next sequential expense reference number.

        Format: EXP + YYYYMMDD + zero-padded 4-digit sequence.
        The sequence resets each day (per-day uniqueness is guaranteed by the
        reference_number unique constraint on the model).
        """
        from app.common.utils.datetime import utcnow

        today_str = utcnow().strftime("%Y%m%d")
        prefix = f"EXP{today_str}"

        # Count existing references with today's prefix to determine sequence
        count_q = select(func.count()).select_from(Expense).where(
            Expense.reference_number.like(f"{prefix}%")
        )
        result = await self._session.execute(count_q)
        count: int = result.scalar_one()
        seq = count + 1
        return f"{prefix}{seq:04d}"

    async def list_by_category(
        self,
        category: ExpenseCategory,
        page: int,
        per_page: int,
    ) -> tuple[list[Expense], int]:
        """
        Return a paginated list of non-deleted expenses for a category.

        Returns (items, total_count).
        """
        base_q = self._base_query().where(Expense.category == category)
        count_q = select(func.count()).select_from(base_q.subquery())
        total: int = (await self._session.execute(count_q)).scalar_one()

        data_q = (
            base_q.order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(data_q)
        return list(result.scalars().all()), total


class ExpensePaymentRepository(BaseRepository[ExpensePayment]):
    model = ExpensePayment

    async def get_by_expense(self, expense_id: UUID) -> list[ExpensePayment]:
        """Return all payment records for a given expense, ordered chronologically."""
        q = (
            select(ExpensePayment)
            .where(ExpensePayment.expense_id == expense_id)
            .order_by(ExpensePayment.created_at.asc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_total_paid(self, expense_id: UUID) -> Decimal:
        """Return the total amount paid across all payment records for an expense."""
        q = select(
            func.coalesce(func.sum(ExpensePayment.amount), Decimal("0"))
        ).where(ExpensePayment.expense_id == expense_id)
        result = await self._session.execute(q)
        return result.scalar_one() or Decimal("0")
