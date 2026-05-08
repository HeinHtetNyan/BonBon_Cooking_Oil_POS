"""
Finance module services.

LedgerService
-------------
Core double-entry ledger engine. ALL financial effects in the system must pass
through this service — no other module may write JournalEntry rows directly.

DebtService
-----------
Manages the full lifecycle of CustomerDebt records. Coordinates between the
debt/payment repositories and LedgerService to keep the ledger and the debt
balances in sync.

Transaction safety
------------------
Both services call session.flush() for intermediate state (repository.create
already flushes). The HTTP request boundary (get_db_session dependency) commits
once on clean exit. Services must never call session.commit() directly.

If a step fails mid-service, SQLAlchemy will roll back the entire transaction
when the exception propagates to the route boundary.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.common.utils.decimal import round_money
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.modules.finance.enums import DebtStatus, TransactionType
from app.modules.finance.models import (
    CustomerDebt,
    DebtPayment,
    JournalEntry,
)
from app.modules.finance.repositories import (
    CustomerDebtRepository,
    DebtPaymentRepository,
    FinancialAccountRepository,
    JournalEntryRepository,
    PaymentMethodRepository,
)


class LedgerService(BaseService):
    """
    Core double-entry ledger engine.

    All financial effects pass through here. The service validates accounts,
    enforces positive amounts, and writes JournalEntry rows via the append-only
    repository. It also provides higher-level helpers (record_sale_payment,
    record_credit_sale, etc.) that encode the chart-of-accounts mapping so
    callers don't need to know account codes.

    Account code convention used by helpers:
      1000  — Cash on Hand
      1050  — KBZPay / WavePay digital wallet (linked via PaymentMethod)
      1100  — Accounts Receivable
      4000  — Sales Revenue
      (expense account codes are passed explicitly by the caller)

    Payment method routing
    ----------------------
    When a payment method code is passed to record_sale_payment /
    record_debt_collection, the service passes that code directly as the
    debit_account_code. This relies on the PaymentMethod.linked_account_code
    being equal to the FinancialAccount.code for cash/digital methods.
    Callers must ensure payment method codes match account codes; the service
    validates this by calling get_system_account, which raises NotFoundError
    on mismatch.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._account_repo = FinancialAccountRepository(session)
        self._journal_repo = JournalEntryRepository(session)

    async def record_transaction(
        self,
        *,
        debit_account_code: str,
        credit_account_code: str,
        amount: Decimal,
        transaction_type: TransactionType,
        description: str,
        transaction_date: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        actor: str,
        tenant_id: str = "default",
    ) -> JournalEntry:
        """
        Record one double-entry transaction.

        Validates both accounts exist. Amount must be strictly positive.
        Returns the persisted JournalEntry (flushed, id populated).
        """
        if amount <= Decimal("0"):
            raise BusinessRuleError("Journal entry amount must be positive")

        debit_acct = await self._account_repo.get_system_account(debit_account_code)
        credit_acct = await self._account_repo.get_system_account(credit_account_code)

        entry = JournalEntry(
            debit_account_id=debit_acct.id,
            credit_account_id=credit_acct.id,
            amount=round_money(amount),
            transaction_type=transaction_type,
            description=description,
            transaction_date=transaction_date,
            reference_type=reference_type,
            reference_id=reference_id,
            actor=actor,
            tenant_id=tenant_id,
        )
        return await self._journal_repo.create(entry)

    async def reverse_transaction(
        self,
        *,
        original_entry_id: UUID,
        reason: str,
        actor: str,
    ) -> JournalEntry:
        """
        Create a reversal entry that swaps debit and credit sides.

        The reversal has the same amount and date as the original. The original
        entry's `is_reversed` flag is set to True so it is excluded from future
        balance calculations.

        Raises:
          NotFoundError        — if the original entry does not exist.
          BusinessRuleError    — if the entry has already been reversed.
        """
        original = await self._journal_repo.get_by_id(original_entry_id)
        if original is None:
            raise NotFoundError("JournalEntry", original_entry_id)
        if original.is_reversed:
            raise BusinessRuleError(
                f"JournalEntry {original_entry_id} is already reversed"
            )

        reversal = JournalEntry(
            # Swap debit ↔ credit to cancel the original effect
            debit_account_id=original.credit_account_id,
            credit_account_id=original.debit_account_id,
            amount=original.amount,
            transaction_type=TransactionType.REVERSAL,
            description=f"REVERSAL: {reason}",
            transaction_date=original.transaction_date,
            reference_type=original.reference_type,
            reference_id=original.reference_id,
            reversal_of_id=original.id,
            actor=actor,
            tenant_id=original.tenant_id,
        )
        saved_reversal = await self._journal_repo.create(reversal)

        # Mark original as reversed. This is the ONLY mutation allowed on a
        # JournalEntry after creation. The assignment goes through SQLAlchemy's
        # unit-of-work; session.flush() propagates it within the transaction.
        original.is_reversed = True
        await self._session.flush()

        return saved_reversal

    async def reverse_all_for_reference(
        self,
        reference_type: str,
        reference_id: str,
        reason: str,
        actor: str,
    ) -> list[JournalEntry]:
        """
        Reverse all non-reversed entries for a (reference_type, reference_id) pair.

        Used when voiding a voucher or writing off a debt to cancel all
        associated ledger effects in one call. Returns the list of new reversal
        entries. Already-reversed entries are silently skipped.
        """
        entries = await self._journal_repo.get_by_reference(reference_type, reference_id)
        reversals: list[JournalEntry] = []
        for entry in entries:
            if not entry.is_reversed:
                reversal = await self.reverse_transaction(
                    original_entry_id=entry.id,
                    reason=reason,
                    actor=actor,
                )
                reversals.append(reversal)
        return reversals

    async def get_account_balance(
        self,
        account_code: str,
        as_of_date: str | None = None,
    ) -> Decimal:
        """Return the current balance for a chart-of-accounts entry."""
        acct = await self._account_repo.get_system_account(account_code)
        return await self._account_repo.calculate_balance(acct.id, as_of_date)

    # Higher-level transaction helpers
    # These encode the chart-of-accounts mapping so callers (e.g., VoucherService)
    # don't need to know account codes. Each helper documents its Dr/Cr sides.

    async def record_sale_payment(
        self,
        *,
        payment_method_code: str,
        amount: Decimal,
        transaction_date: str,
        reference_type: str,
        reference_id: str,
        description: str,
        actor: str,
        tenant_id: str = "default",
    ) -> JournalEntry:
        """
        Record a cash/digital payment received for a sale.

        Dr: Cash / Bank / KBZPay account (mapped via payment_method_code)
        Cr: Sales Revenue (4000)
        """
        return await self.record_transaction(
            debit_account_code=payment_method_code,
            credit_account_code="4000",
            amount=amount,
            transaction_type=TransactionType.SALE,
            description=description,
            transaction_date=transaction_date,
            reference_type=reference_type,
            reference_id=reference_id,
            actor=actor,
            tenant_id=tenant_id,
        )

    async def record_credit_sale(
        self,
        *,
        amount: Decimal,
        transaction_date: str,
        reference_type: str,
        reference_id: str,
        description: str,
        actor: str,
        tenant_id: str = "default",
    ) -> JournalEntry:
        """
        Record a credit sale where no cash is received immediately.

        Dr: Accounts Receivable (1100)
        Cr: Sales Revenue (4000)
        """
        return await self.record_transaction(
            debit_account_code="1100",
            credit_account_code="4000",
            amount=amount,
            transaction_type=TransactionType.SALE,
            description=description,
            transaction_date=transaction_date,
            reference_type=reference_type,
            reference_id=reference_id,
            actor=actor,
            tenant_id=tenant_id,
        )

    async def record_debt_collection(
        self,
        *,
        payment_method_code: str,
        amount: Decimal,
        transaction_date: str,
        reference_type: str,
        reference_id: str,
        description: str,
        actor: str,
        tenant_id: str = "default",
    ) -> JournalEntry:
        """
        Record a customer paying an outstanding debt.

        Dr: Cash / Bank / KBZPay account (mapped via payment_method_code)
        Cr: Accounts Receivable (1100)
        """
        return await self.record_transaction(
            debit_account_code=payment_method_code,
            credit_account_code="1100",
            amount=amount,
            transaction_type=TransactionType.DEBT_COLLECTION,
            description=description,
            transaction_date=transaction_date,
            reference_type=reference_type,
            reference_id=reference_id,
            actor=actor,
            tenant_id=tenant_id,
        )

    async def record_expense(
        self,
        *,
        expense_account_code: str,
        payment_method_code: str,
        amount: Decimal,
        transaction_date: str,
        reference_type: str,
        reference_id: str,
        description: str,
        actor: str,
        tenant_id: str = "default",
    ) -> JournalEntry:
        """
        Record an expense payment.

        Dr: Expense account (caller-supplied code)
        Cr: Cash / Bank / KBZPay account (mapped via payment_method_code)
        """
        return await self.record_transaction(
            debit_account_code=expense_account_code,
            credit_account_code=payment_method_code,
            amount=amount,
            transaction_type=TransactionType.EXPENSE_PAID,
            description=description,
            transaction_date=transaction_date,
            reference_type=reference_type,
            reference_id=reference_id,
            actor=actor,
            tenant_id=tenant_id,
        )


class DebtService(BaseService):
    """
    Customer debt lifecycle manager.

    Coordinates CustomerDebt + DebtPayment repositories with LedgerService to
    keep the ledger and debt balances consistently in sync. Every state change
    that has a financial effect (create debt, record payment, cancel debt)
    produces a corresponding JournalEntry.

    Customer credit_balance updates
    --------------------------------
    `_update_customer_credit_balance` increments/decrements the in-memory
    `credit_balance` on the Customer model and flushes. It uses a direct
    session.execute(select(Customer)) rather than a CustomerRepository
    to avoid a circular module dependency. This is the only place where the
    finance module touches the customers table directly.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._debt_repo = CustomerDebtRepository(session)
        self._debt_payment_repo = DebtPaymentRepository(session)
        self._ledger = LedgerService(session)
        self._pm_repo = PaymentMethodRepository(session)

    async def create_debt(
        self,
        *,
        customer_id: UUID,
        voucher_id: UUID | None,
        amount: Decimal,
        due_date: str | None = None,
        notes: str | None = None,
        actor: str,
        tenant_id: str = "default",
    ) -> CustomerDebt:
        """
        Create an outstanding CustomerDebt record after a credit sale.

        Assumes the caller (e.g., VoucherService) has already recorded the
        credit sale JournalEntry via LedgerService.record_credit_sale. This
        method only manages the CustomerDebt row and the customer's balance.
        """
        debt = CustomerDebt(
            customer_id=customer_id,
            voucher_id=voucher_id,
            original_amount=round_money(amount),
            paid_amount=Decimal("0"),
            status=DebtStatus.OUTSTANDING,
            due_date=due_date,
            notes=notes,
            created_by=actor,
            updated_by=actor,
            tenant_id=tenant_id,
        )
        created = await self._debt_repo.create(debt)

        # Increase the customer's credit_balance by the new debt amount
        await self._update_customer_credit_balance(customer_id, amount)

        return created

    async def record_payment(
        self,
        *,
        debt_id: UUID,
        payment_method_code: str,
        amount: Decimal,
        transaction_date: str,
        reference_number: str | None = None,
        notes: str | None = None,
        actor: str,
        tenant_id: str = "default",
    ) -> tuple[DebtPayment, CustomerDebt]:
        """
        Apply a payment against an outstanding debt.

        Steps:
          1. Validate debt state (not already PAID or WRITTEN_OFF).
          2. Validate amount does not exceed outstanding balance.
          3. Resolve payment method to get its DB id.
          4. Record ledger entry (Dr: Cash/Bank, Cr: Accounts Receivable).
          5. Create DebtPayment row linked to the ledger entry.
          6. Update debt paid_amount and status.
          7. Reduce customer credit_balance.

        Returns (DebtPayment, updated CustomerDebt).
        """
        # Row-level lock: prevents concurrent payments from both passing the
        # "amount <= outstanding" check and together exceeding the debt balance.
        debt = await self._debt_repo.get_by_id_for_update_or_raise(debt_id)

        if debt.status == DebtStatus.PAID:
            raise BusinessRuleError("This debt is already fully paid")
        if debt.status == DebtStatus.WRITTEN_OFF:
            raise BusinessRuleError("Cannot apply payment to a written-off debt")

        outstanding = debt.outstanding_amount
        if amount <= Decimal("0"):
            raise BusinessRuleError("Payment amount must be positive")
        if amount > outstanding:
            raise BusinessRuleError(
                f"Payment amount {amount} exceeds outstanding balance {outstanding}"
            )

        # Resolve the payment method for its DB id
        pm = await self._pm_repo.get_by_code(payment_method_code)
        if pm is None:
            raise NotFoundError("PaymentMethod", payment_method_code)

        # Record the double-entry ledger effect
        journal_entry = await self._ledger.record_debt_collection(
            payment_method_code=payment_method_code,
            amount=amount,
            transaction_date=transaction_date,
            reference_type="debt",
            reference_id=str(debt_id),
            description=f"Debt payment for debt {debt_id}",
            actor=actor,
            tenant_id=tenant_id,
        )

        # Persist the payment record
        payment = DebtPayment(
            debt_id=debt_id,
            payment_method_id=pm.id,
            amount=round_money(amount),
            reference_number=reference_number,
            notes=notes,
            actor=actor,
            journal_entry_id=journal_entry.id,
            tenant_id=tenant_id,
        )
        saved_payment = await self._debt_payment_repo.create(payment)

        # Update debt balance and status
        new_paid = debt.paid_amount + amount
        if new_paid >= debt.original_amount:
            new_status = DebtStatus.PAID
            new_paid = debt.original_amount  # cap at original to avoid float drift
        else:
            new_status = DebtStatus.PARTIALLY_PAID

        updated_debt = await self._debt_repo.update(
            debt,
            paid_amount=round_money(new_paid),
            status=new_status,
            updated_by=actor,
        )

        # Reduce customer's outstanding credit balance
        await self._update_customer_credit_balance(debt.customer_id, -amount)

        return saved_payment, updated_debt

    async def cancel_debt(
        self,
        debt_id: UUID,
        reason: str,
        actor: str,
    ) -> CustomerDebt:
        """
        Write off a debt (mark as WRITTEN_OFF and reverse all ledger entries).

        Steps:
          1. Validate debt can be cancelled (not already PAID).
          2. Reverse all journal entries tagged with reference (debt, debt_id).
          3. Reduce customer credit_balance by the remaining outstanding amount.
          4. Set debt status to WRITTEN_OFF.

        A PAID debt cannot be written off — the money has already been received.
        An OUTSTANDING or PARTIALLY_PAID debt can be written off at any time.
        """
        debt = await self._debt_repo.get_by_id_for_update_or_raise(debt_id)

        if debt.status == DebtStatus.PAID:
            raise BusinessRuleError("Cannot cancel a fully paid debt")
        if debt.status == DebtStatus.WRITTEN_OFF:
            raise BusinessRuleError("Debt is already written off")

        # Reverse all ledger effects associated with this debt
        await self._ledger.reverse_all_for_reference(
            reference_type="debt",
            reference_id=str(debt_id),
            reason=reason,
            actor=actor,
        )

        # Reduce customer credit balance by the remaining outstanding amount
        outstanding = debt.outstanding_amount
        if outstanding > Decimal("0"):
            await self._update_customer_credit_balance(debt.customer_id, -outstanding)

        return await self._debt_repo.update(
            debt,
            status=DebtStatus.WRITTEN_OFF,
            updated_by=actor,
        )

    async def get_customer_debts(
        self,
        customer_id: UUID,
        status: DebtStatus | None = None,
    ) -> list[CustomerDebt]:
        """Fetch all debts for a customer, optionally filtered by status."""
        return await self._debt_repo.get_by_customer(customer_id, status)

    async def get_total_outstanding(self, customer_id: UUID) -> Decimal:
        """Return the total outstanding balance across all open debts for a customer."""
        return await self._debt_repo.get_total_outstanding(customer_id)

    # Private helpers

    async def _update_customer_credit_balance(
        self,
        customer_id: UUID,
        delta: Decimal,
    ) -> None:
        """
        Adjust Customer.credit_balance by `delta` (positive = increase debt,
        negative = reduce debt). Clamps to zero to prevent negative balances
        caused by rounding or data fixes.

        Uses a direct session query to avoid a circular import between the
        finance and customers modules.
        """
        from sqlalchemy import select

        from app.modules.customers.models import Customer

        result = await self._session.execute(
            select(Customer).where(Customer.id == customer_id).with_for_update()
        )
        customer = result.scalar_one_or_none()
        if customer is not None:
            new_balance = customer.credit_balance + delta
            # Never let credit_balance go below zero
            customer.credit_balance = round_money(
                Decimal("0") if new_balance < Decimal("0") else new_balance
            )
            await self._session.flush()
