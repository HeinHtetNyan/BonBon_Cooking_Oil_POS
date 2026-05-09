"""
Finance module repositories.

Repository responsibilities:
- All DB access for finance domain models lives here.
- Services must NOT call session.execute() directly.
- JournalEntryRepository does NOT extend BaseRepository because JournalEntry
  is append-only: there is no update(), soft_delete(), or delete(). Providing
  those methods would violate the immutability invariant.
- Balance calculation is done by the repository via SQLAlchemy expressions to
  push the arithmetic to the database layer and avoid loading every entry into
  Python memory.

Balance algorithm
-----------------
For a given account (normal_balance known):
  DEBIT normal balance accounts (assets, expenses):
    balance = Σ(amount where debit_account_id = account_id)
            - Σ(amount where credit_account_id = account_id)
  CREDIT normal balance accounts (liabilities, equity, revenue):
    balance = Σ(amount where credit_account_id = account_id)
            - Σ(amount where debit_account_id = account_id)
  Only non-reversed entries (is_reversed = False) contribute.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.repositories.base import BaseRepository
from app.modules.finance.enums import AccountNormalBalance, DebtStatus
from app.modules.finance.models import (
    CustomerDebt,
    DebtPayment,
    FinancialAccount,
    JournalEntry,
    PaymentMethod,
)


class FinancialAccountRepository(BaseRepository[FinancialAccount]):
    model = FinancialAccount

    async def get_by_code(self, code: str) -> FinancialAccount | None:
        """Fetch an active (non-deleted) account by its unique code."""
        q = self._base_query().where(FinancialAccount.code == code)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_by_codes(self, codes: list[str]) -> list[FinancialAccount]:
        """
        Fetch multiple accounts by their codes in one query.
        Returns only non-deleted accounts. Order is DB-determined.
        """
        if not codes:
            return []
        q = self._base_query().where(FinancialAccount.code.in_(codes))
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def calculate_balance(
        self,
        account_id: UUID,
        as_of_date: str | None = None,
    ) -> Decimal:
        """
        Compute the running balance for an account.

        Only entries with is_reversed=False are included. When `as_of_date`
        is provided (YYYY-MM-DD), only entries whose transaction_date <=
        as_of_date are included — this supports balance-sheet snapshots.

        The method queries the account to determine its normal_balance, then
        applies the correct sign convention.

        Returns Decimal("0") when no entries exist.
        """
        # Fetch the account to know its normal balance (exclude soft-deleted)
        acct_result = await self._session.execute(
            select(FinancialAccount).where(
                FinancialAccount.id == account_id,
                FinancialAccount.deleted_at.is_(None),
            )
        )
        account = acct_result.scalar_one_or_none()
        if account is None:
            return Decimal("0")

        # Build sum of debits to this account
        debit_q = select(func.coalesce(func.sum(JournalEntry.amount), Decimal("0"))).where(
            and_(
                JournalEntry.debit_account_id == account_id,
                JournalEntry.is_reversed.is_(False),
                *(
                    [JournalEntry.transaction_date <= as_of_date]
                    if as_of_date is not None
                    else []
                ),
            )
        )

        # Build sum of credits to this account
        credit_q = select(func.coalesce(func.sum(JournalEntry.amount), Decimal("0"))).where(
            and_(
                JournalEntry.credit_account_id == account_id,
                JournalEntry.is_reversed.is_(False),
                *(
                    [JournalEntry.transaction_date <= as_of_date]
                    if as_of_date is not None
                    else []
                ),
            )
        )

        debit_result = await self._session.execute(debit_q)
        credit_result = await self._session.execute(credit_q)

        total_debits: Decimal = debit_result.scalar_one() or Decimal("0")
        total_credits: Decimal = credit_result.scalar_one() or Decimal("0")

        # Apply normal-balance sign convention
        if account.normal_balance == AccountNormalBalance.DEBIT:
            return total_debits - total_credits
        else:
            return total_credits - total_debits

    async def get_system_account(self, code: str) -> FinancialAccount:
        """
        Fetch a required system account by code.

        Raises NotFoundError if the account does not exist. Used by
        LedgerService to resolve account codes to IDs before writing entries.
        The "system" in the name refers to the calling pattern (required
        infrastructure account), not the is_system flag.
        """
        from app.core.exceptions import NotFoundError

        account = await self.get_by_code(code)
        if account is None:
            raise NotFoundError("FinancialAccount", code)
        return account


class JournalEntryRepository:
    """
    Append-only repository for JournalEntry.

    Does NOT extend BaseRepository deliberately — update(), soft_delete(), and
    delete() must not exist on this class to enforce the immutability contract
    at the repository boundary.

    The only mutation allowed via this class is setting `is_reversed = True`
    on an existing entry, which is done by `LedgerService.reverse_transaction`
    via direct attribute assignment + session.flush().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, entry: JournalEntry) -> JournalEntry:
        """Persist a new journal entry. Flushes to populate DB-generated defaults."""
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def create_many(self, entries: list[JournalEntry]) -> list[JournalEntry]:
        """Persist multiple journal entries in one flush."""
        self._session.add_all(entries)
        await self._session.flush()
        for entry in entries:
            await self._session.refresh(entry)
        return entries

    async def get_by_id(self, entry_id: UUID) -> JournalEntry | None:
        """Fetch a single entry by its UUID. Returns None if not found."""
        q = select(JournalEntry).where(JournalEntry.id == entry_id)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_by_reference(
        self,
        reference_type: str,
        reference_id: str,
    ) -> list[JournalEntry]:
        """
        Fetch all journal entries for a given (reference_type, reference_id) pair.
        Ordered by created_at ASC for chronological reversal.
        """
        q = (
            select(JournalEntry)
            .where(
                and_(
                    JournalEntry.reference_type == reference_type,
                    JournalEntry.reference_id == reference_id,
                )
            )
            .order_by(JournalEntry.created_at.asc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_by_account(
        self,
        account_id: UUID,
        page: int,
        per_page: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[list[JournalEntry], int]:
        """
        Paginated ledger query for entries affecting a given account.

        Matches entries where the account is on EITHER the debit or credit
        side. Supports optional date-range filtering on transaction_date.
        Returns (entries, total_count).
        """
        date_filters = []
        if start_date is not None:
            date_filters.append(JournalEntry.transaction_date >= start_date)
        if end_date is not None:
            date_filters.append(JournalEntry.transaction_date <= end_date)

        base_filter = and_(
            or_(
                JournalEntry.debit_account_id == account_id,
                JournalEntry.credit_account_id == account_id,
            ),
            *date_filters,
        )

        # Count
        count_q = select(func.count()).select_from(JournalEntry).where(base_filter)
        count_result = await self._session.execute(count_q)
        total: int = count_result.scalar_one()

        # Fetch page
        offset = (page - 1) * per_page
        data_q = (
            select(JournalEntry)
            .where(base_filter)
            .order_by(
                JournalEntry.transaction_date.desc(),
                JournalEntry.created_at.desc(),
            )
            .offset(offset)
            .limit(per_page)
        )
        data_result = await self._session.execute(data_q)
        entries = list(data_result.scalars().all())

        return entries, total


class PaymentMethodRepository(BaseRepository[PaymentMethod]):
    model = PaymentMethod

    async def get_by_code(self, code: str) -> PaymentMethod | None:
        """Fetch a payment method by its unique code."""
        q = self._base_query().where(PaymentMethod.code == code)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_active(self) -> list[PaymentMethod]:
        """Fetch all active, non-deleted payment methods ordered by sort_order."""
        q = (
            self._base_query()
            .where(PaymentMethod.is_active.is_(True))
            .order_by(PaymentMethod.sort_order.asc(), PaymentMethod.name.asc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())


class CustomerDebtRepository(BaseRepository[CustomerDebt]):
    model = CustomerDebt

    async def get_by_customer(
        self,
        customer_id: UUID,
        status: DebtStatus | None = None,
    ) -> list[CustomerDebt]:
        """
        Fetch debts for a customer, optionally filtered by status.
        Ordered by created_at DESC (most recent first).
        """
        filters = [CustomerDebt.customer_id == customer_id]
        if status is not None:
            filters.append(CustomerDebt.status == status)
        q = (
            self._base_query()
            .where(and_(*filters))
            .order_by(CustomerDebt.created_at.desc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_total_outstanding(self, customer_id: UUID) -> Decimal:
        """
        Sum of outstanding balances across all non-paid, non-written-off debts
        for a customer. Returns Decimal("0") when no outstanding debts exist.
        """
        q = select(
            func.coalesce(
                func.sum(CustomerDebt.original_amount - CustomerDebt.paid_amount),
                Decimal("0"),
            )
        ).where(
            and_(
                CustomerDebt.customer_id == customer_id,
                CustomerDebt.status.in_(
                    [DebtStatus.OUTSTANDING, DebtStatus.PARTIALLY_PAID]
                ),
                CustomerDebt.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(q)
        return result.scalar_one() or Decimal("0")

    async def get_by_voucher(self, voucher_id: UUID) -> CustomerDebt | None:
        """
        Fetch the debt record associated with a specific voucher.
        A voucher can have at most one debt record.
        """
        q = self._base_query().where(CustomerDebt.voucher_id == voucher_id)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()


class DebtPaymentRepository(BaseRepository[DebtPayment]):
    model = DebtPayment

    async def get_by_debt(self, debt_id: UUID) -> list[DebtPayment]:
        """
        Fetch all payments applied to a debt, ordered chronologically.
        Note: DebtPayment has no soft-delete; all rows are live records.
        """
        q = (
            select(DebtPayment)
            .where(DebtPayment.debt_id == debt_id)
            .order_by(DebtPayment.created_at.asc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())
