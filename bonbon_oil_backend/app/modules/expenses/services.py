"""
Expense module service layer.

Business logic for expense creation, approval, and payment recording.
All financial ledger effects are delegated to LedgerService via lazy import
to avoid circular module dependencies.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.common.utils.decimal import round_money
from app.core.exceptions import BusinessRuleError
from app.modules.expenses.enums import ExpenseCategory, ExpenseStatus
from app.modules.expenses.models import Expense, ExpensePayment
from app.modules.expenses.repositories import ExpensePaymentRepository, ExpenseRepository
from app.modules.expenses.schemas import ExpenseCreate, ExpensePaymentCreate, ExpenseUpdate


class ExpenseService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._expense_repo = ExpenseRepository(session)
        self._payment_repo = ExpensePaymentRepository(session)

    @property
    def _ledger(self):
        from app.modules.finance.services import LedgerService

        return LedgerService(self._session)

    # Creation

    async def create_expense(
        self,
        data: ExpenseCreate,
        *,
        actor: str,
        tenant_id: str = "default",
    ) -> Expense:
        """
        Create a new expense.

        If `payment_method_code` is supplied, the expense is created directly
        in PAID status and a ledger entry + payment record are written
        transactionally in the same flush.
        """
        ref = await self._expense_repo.next_reference_number()

        initial_status = (
            ExpenseStatus.PAID if data.payment_method_code else ExpenseStatus.PENDING
        )

        expense = Expense(
            reference_number=ref,
            category=data.category,
            description=data.description,
            amount=round_money(data.amount),
            status=initial_status,
            expense_date=data.expense_date,
            production_batch_id=data.production_batch_id,
            notes=data.notes,
            created_by=actor,
            updated_by=actor,
            tenant_id=tenant_id,
        )
        await self._expense_repo.create(expense)

        if data.payment_method_code:
            from app.modules.finance.repositories import PaymentMethodRepository

            pm_repo = PaymentMethodRepository(self._session)
            pm = await pm_repo.get_by_code(data.payment_method_code)
            if pm is None:
                from app.core.exceptions import NotFoundError
                raise NotFoundError("PaymentMethod", data.payment_method_code)

            expense_account_code = self._category_to_account(data.category)

            journal = await self._ledger.record_expense(
                expense_account_code=expense_account_code,
                payment_method_code=data.payment_method_code,
                amount=data.amount,
                transaction_date=data.expense_date,
                reference_type="expense",
                reference_id=str(expense.id),
                description=data.description,
                actor=actor,
                tenant_id=tenant_id,
            )

            payment = ExpensePayment(
                expense_id=expense.id,
                payment_method_id=pm.id,
                amount=round_money(data.amount),
                reference_number=data.payment_reference,
                journal_entry_id=journal.id,
                actor=actor,
                tenant_id=tenant_id,
            )
            await self._payment_repo.create(payment)

            await self._expense_repo.update(
                expense,
                linked_journal_entry_id=journal.id,
            )

        self._logger.info(
            "expense.created",
            expense_id=str(expense.id),
            reference=ref,
            status=initial_status,
            actor=actor,
        )
        return expense

    # Read

    async def get_expense_with_payments(self, expense_id: UUID) -> tuple[Expense, list[ExpensePayment]]:
        """Fetch an expense and its payment records."""
        expense = await self._expense_repo.get_by_id_or_raise(expense_id)
        payments = await self._payment_repo.get_by_expense(expense_id)
        return expense, payments

    async def list_expenses(
        self,
        *,
        category: ExpenseCategory | None = None,
        status: ExpenseStatus | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> tuple[list[Expense], int]:
        """
        Paginated list of non-deleted expenses with optional filters.

        Returns (items, total_count).
        """
        from sqlalchemy import and_, func, select

        filters = []
        if category is not None:
            filters.append(Expense.category == category)
        if status is not None:
            filters.append(Expense.status == status)
        if start_date is not None:
            filters.append(Expense.expense_date >= start_date)
        if end_date is not None:
            filters.append(Expense.expense_date <= end_date)

        base_q = self._expense_repo._base_query()
        if filters:
            base_q = base_q.where(and_(*filters))

        count_q = select(func.count()).select_from(base_q.subquery())
        total: int = (await self._session.execute(count_q)).scalar_one()

        data_q = (
            base_q.order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(data_q)
        return list(result.scalars().all()), total

    # Update

    async def update_expense(
        self,
        expense_id: UUID,
        data: ExpenseUpdate,
        *,
        actor: str,
    ) -> Expense:
        """Update mutable fields on a PENDING expense."""
        expense = await self._expense_repo.get_by_id_or_raise(expense_id)
        if expense.status not in (ExpenseStatus.PENDING,):
            raise BusinessRuleError(
                f"Cannot edit expense in status '{expense.status}'. Only PENDING expenses can be edited."
            )

        updates: dict = {"updated_by": actor}
        if data.description is not None:
            updates["description"] = data.description
        if data.category is not None:
            updates["category"] = data.category
        if data.notes is not None:
            updates["notes"] = data.notes

        return await self._expense_repo.update(expense, **updates)

    # Approval

    async def approve_expense(
        self,
        expense_id: UUID,
        *,
        approved: bool,
        notes: str | None,
        actor: str,
    ) -> Expense:
        """Approve or reject a PENDING expense."""
        expense = await self._expense_repo.get_by_id_or_raise(expense_id)
        if expense.status not in (ExpenseStatus.PENDING,):
            raise BusinessRuleError(
                f"Cannot approve/reject expense in status '{expense.status}'. "
                "Only PENDING expenses can be approved or rejected."
            )

        new_status = ExpenseStatus.APPROVED if approved else ExpenseStatus.REJECTED
        return await self._expense_repo.update(
            expense,
            status=new_status,
            approved_by=actor if approved else None,
            notes=notes if notes is not None else expense.notes,
            updated_by=actor,
        )

    # Payment

    async def record_payment(
        self,
        expense_id: UUID,
        data: ExpensePaymentCreate,
        *,
        actor: str,
        tenant_id: str = "default",
    ) -> ExpensePayment:
        """
        Record a payment for an approved (or pending) expense.

        Creates a double-entry ledger record and sets the expense to PAID.
        Raises BusinessRuleError if the expense is already paid or rejected.
        """
        expense = await self._expense_repo.get_by_id_or_raise(expense_id)

        if expense.status == ExpenseStatus.PAID:
            raise BusinessRuleError("Expense is already paid")
        if expense.status == ExpenseStatus.REJECTED:
            raise BusinessRuleError("Cannot pay a rejected expense")

        expense_account_code = self._category_to_account(expense.category)

        journal = await self._ledger.record_expense(
            expense_account_code=expense_account_code,
            payment_method_code=data.payment_method_code,
            amount=data.amount,
            transaction_date=expense.expense_date,
            reference_type="expense",
            reference_id=str(expense_id),
            description=expense.description,
            actor=actor,
            tenant_id=tenant_id,
        )

        from app.modules.finance.repositories import PaymentMethodRepository

        pm_repo = PaymentMethodRepository(self._session)
        pm = await pm_repo.get_by_code(data.payment_method_code)
        if pm is None:
            from app.core.exceptions import NotFoundError

            raise NotFoundError("PaymentMethod", data.payment_method_code)

        payment = ExpensePayment(
            expense_id=expense_id,
            payment_method_id=pm.id,
            amount=round_money(data.amount),
            reference_number=data.reference_number,
            notes=data.notes,
            journal_entry_id=journal.id,
            actor=actor,
            tenant_id=tenant_id,
        )
        saved = await self._payment_repo.create(payment)
        await self._expense_repo.update(expense, status=ExpenseStatus.PAID, updated_by=actor)

        self._logger.info(
            "expense.payment_recorded",
            expense_id=str(expense_id),
            amount=str(data.amount),
            actor=actor,
        )
        return saved

    # Account mapping

    @staticmethod
    def _category_to_account(category: ExpenseCategory) -> str:
        """Map an expense category to the corresponding chart-of-accounts code."""
        mapping: dict[ExpenseCategory, str] = {
            ExpenseCategory.LABOUR: "5100",
            ExpenseCategory.UTILITIES: "5200",
            ExpenseCategory.TRANSPORT: "5200",
            ExpenseCategory.MAINTENANCE: "5200",
            ExpenseCategory.PACKAGING: "5200",
            ExpenseCategory.ADMINISTRATIVE: "5200",
            ExpenseCategory.MARKETING: "5200",
            ExpenseCategory.RENT: "5200",
            ExpenseCategory.OTHER: "5200",
        }
        return mapping.get(category, "5200")
