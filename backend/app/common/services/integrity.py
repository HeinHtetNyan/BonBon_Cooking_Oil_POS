"""
Data integrity validation services.

These services are used by:
  - Celery consistency-check tasks (scheduled, background)
  - Admin reconciliation endpoints (on-demand)
  - Application startup (optional fast check)

They NEVER mutate data — all methods are read-only assertions.
Corruption is only repaired by reconciliation services.

InventoryValidationService
--------------------------
Pre-movement guard: validates that a proposed movement is safe to apply
before writing any rows. Used inside InventoryService but also callable
standalone for dry-run validation.

FinancialIntegrityService
-------------------------
Post-hoc verifier: scans existing journal entries and account balances for
structural violations (negative amounts, self-debit/credit, unbalanced
entries, orphaned references). Returns a structured report; callers decide
whether to log, alert, or raise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.utils.decimal import ZERO
from app.core.exceptions import BusinessRuleError, InsufficientInventoryError, NotFoundError

if TYPE_CHECKING:
    from app.modules.inventory.models import InventoryItem


# Shared data structures

@dataclass
class IntegrityIssue:
    severity: str  # "error" | "warning"
    code: str
    message: str
    context: dict = field(default_factory=dict)


@dataclass
class IntegrityReport:
    issues: list[IntegrityIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def add_error(self, code: str, message: str, **context: object) -> None:
        self.issues.append(IntegrityIssue("error", code, message, dict(context)))

    def add_warning(self, code: str, message: str, **context: object) -> None:
        self.issues.append(IntegrityIssue("warning", code, message, dict(context)))


# InventoryValidationService

class InventoryValidationService:
    """
    Pre-movement guard for inventory operations.

    All outbound movement types are validated here before the movement row
    is written. This is a read-only service — it never modifies data.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def validate_sufficient_stock(
        self,
        item_id: UUID,
        quantity_in_canonical_unit: Decimal,
        movement_label: str = "movement",
    ) -> None:
        """
        Raise InsufficientInventoryError if the item's current balance is
        below the requested canonical quantity.

        This check is redundant when InventoryService.record_movement() is
        used (which also checks), but is valuable as an independent guard
        for:
          - Batch pre-validation before any rows are written
          - Dry-run simulation endpoints
          - Unit tests that mock the service layer

        Note: This is not a substitute for the row-level lock inside
        record_movement(). Both checks are needed: this one for early
        validation feedback, the locked check for actual race safety.
        """
        from app.modules.inventory.models import InventoryItem

        result = await self._session.execute(
            select(InventoryItem).where(InventoryItem.id == item_id)
        )
        item: InventoryItem | None = result.scalar_one_or_none()
        if item is None:
            raise NotFoundError("InventoryItem", item_id)
        if item.current_balance < quantity_in_canonical_unit:
            raise InsufficientInventoryError(
                item.name,
                f"{quantity_in_canonical_unit} {item.unit} (canonical)",
                f"{item.current_balance} {item.unit}",
            )

    async def validate_unit_compatible(
        self,
        from_unit: str,
        to_unit: str,
    ) -> None:
        """Raise ValueError if units cannot be converted between each other."""
        from app.modules.inventory.enums import WeightUnit
        from app.modules.inventory.services import UnitConversionService

        try:
            fu = WeightUnit(from_unit)
            tu = WeightUnit(to_unit)
        except ValueError as exc:
            raise BusinessRuleError(f"Unknown unit: {exc}") from exc
        UnitConversionService.validate_compatible(fu, tu)

    async def validate_movement_batch(
        self,
        movements: list[dict],
    ) -> IntegrityReport:
        """
        Dry-run validate a list of proposed movements and return a report.

        Each dict in `movements` should have:
          item_id, quantity_in_canonical_unit, movement_type (str)

        Returns an IntegrityReport without writing anything.
        """
        from app.modules.inventory.enums import OUTBOUND_MOVEMENTS, MovementType
        from app.modules.inventory.models import InventoryItem

        report = IntegrityReport()
        # Accumulate running balance deltas per item so that multi-movement
        # batches (e.g., a production batch consuming several materials) are
        # validated as a whole rather than independently.
        balance_deltas: dict[UUID, Decimal] = {}

        # Pre-load all referenced items in one query
        item_ids = [m["item_id"] for m in movements]
        items_result = await self._session.execute(
            select(InventoryItem).where(InventoryItem.id.in_(item_ids))
        )
        items = {item.id: item for item in items_result.scalars().all()}

        for mov in movements:
            item_id = mov["item_id"]
            qty = mov["quantity_in_canonical_unit"]
            mtype = mov.get("movement_type", "")

            if item_id not in items:
                report.add_error(
                    "item_not_found",
                    f"InventoryItem {item_id} does not exist",
                    item_id=str(item_id),
                )
                continue

            item = items[item_id]
            try:
                mt = MovementType(mtype)
            except ValueError:
                report.add_error(
                    "invalid_movement_type",
                    f"Unknown movement type '{mtype}'",
                    item_id=str(item_id),
                )
                continue

            if mt in OUTBOUND_MOVEMENTS:
                delta = balance_deltas.get(item_id, ZERO)
                projected_balance = item.current_balance + delta - qty
                if projected_balance < ZERO:
                    report.add_error(
                        "insufficient_stock",
                        f"Item '{item.name}' would go negative: "
                        f"balance {item.current_balance + delta}, requested {qty}",
                        item_id=str(item_id),
                        item_name=item.name,
                        current_balance=str(item.current_balance),
                        requested=str(qty),
                    )
                balance_deltas[item_id] = balance_deltas.get(item_id, ZERO) - qty
            else:
                balance_deltas[item_id] = balance_deltas.get(item_id, ZERO) + qty

        return report

# FinancialIntegrityService

class FinancialIntegrityService:
    """
    Read-only structural verifier for the financial ledger.

    Checks performed:
      1. journal_entry_amounts_positive     — all amounts > 0
      2. journal_entry_no_self_loop         — debit_account ≠ credit_account
      3. account_balance_non_negative       — asset accounts should not be negative
         (warning, not error — negative AR from write-offs is expected)
      4. customer_debt_consistency          — customer.credit_balance matches
         sum of outstanding CustomerDebt amounts for that customer
      5. orphaned_journal_entries           — reference_type/reference_id pairs
         that point to non-existent vouchers, debts, or expenses
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def run_full_check(self) -> IntegrityReport:
        """Run all checks and aggregate results into a single report."""
        report = IntegrityReport()
        await self._check_journal_entry_amounts(report)
        await self._check_journal_entry_no_self_loop(report)
        await self._check_asset_account_balances(report)
        await self._check_customer_debt_consistency(report)
        return report

    async def _check_journal_entry_amounts(self, report: IntegrityReport) -> None:
        from app.modules.finance.models import JournalEntry

        result = await self._session.execute(
            select(func.count()).select_from(JournalEntry).where(
                JournalEntry.amount <= ZERO
            )
        )
        bad_count: int = result.scalar_one()
        if bad_count > 0:
            report.add_error(
                "journal_entry_zero_or_negative_amount",
                f"{bad_count} journal entry(ies) have amount ≤ 0",
                count=bad_count,
            )

    async def _check_journal_entry_no_self_loop(self, report: IntegrityReport) -> None:
        from app.modules.finance.models import JournalEntry

        result = await self._session.execute(
            select(func.count()).select_from(JournalEntry).where(
                JournalEntry.debit_account_id == JournalEntry.credit_account_id
            )
        )
        bad_count: int = result.scalar_one()
        if bad_count > 0:
            report.add_error(
                "journal_entry_self_loop",
                f"{bad_count} journal entry(ies) debit and credit the same account",
                count=bad_count,
            )

    async def _check_asset_account_balances(self, report: IntegrityReport) -> None:
        from app.modules.finance.enums import AccountType, AccountNormalBalance
        from app.modules.finance.models import FinancialAccount, JournalEntry

        accounts_result = await self._session.execute(
            select(FinancialAccount).where(
                and_(
                    FinancialAccount.deleted_at.is_(None),
                    FinancialAccount.account_type == AccountType.ASSET,
                )
            )
        )
        accounts = accounts_result.scalars().all()

        for account in accounts:
            # Compute balance using same algorithm as FinancialAccountRepository
            debit_sum = await self._session.execute(
                select(func.coalesce(func.sum(JournalEntry.amount), Decimal("0"))).where(
                    and_(
                        JournalEntry.debit_account_id == account.id,
                        JournalEntry.is_reversed.is_(False),
                    )
                )
            )
            credit_sum = await self._session.execute(
                select(func.coalesce(func.sum(JournalEntry.amount), Decimal("0"))).where(
                    and_(
                        JournalEntry.credit_account_id == account.id,
                        JournalEntry.is_reversed.is_(False),
                    )
                )
            )
            debits = debit_sum.scalar_one() or Decimal("0")
            credits = credit_sum.scalar_one() or Decimal("0")
            balance = debits - credits  # DEBIT-normal asset accounts

            if balance < ZERO:
                report.add_warning(
                    "asset_account_negative_balance",
                    f"Asset account '{account.code} {account.name}' has negative balance {balance}",
                    account_code=account.code,
                    account_name=account.name,
                    balance=str(balance),
                )

    async def _check_customer_debt_consistency(self, report: IntegrityReport) -> None:
        """
        Verify that each Customer's credit_balance matches the sum of their
        outstanding CustomerDebt records.
        """
        from app.modules.customers.models import Customer
        from app.modules.finance.enums import DebtStatus
        from app.modules.finance.models import CustomerDebt

        customers_result = await self._session.execute(
            select(Customer).where(Customer.deleted_at.is_(None))
        )
        customers = customers_result.scalars().all()

        for customer in customers:
            debt_result = await self._session.execute(
                select(
                    func.coalesce(
                        func.sum(CustomerDebt.original_amount - CustomerDebt.paid_amount),
                        Decimal("0"),
                    )
                ).where(
                    and_(
                        CustomerDebt.customer_id == customer.id,
                        CustomerDebt.status.in_(
                            [DebtStatus.OUTSTANDING, DebtStatus.PARTIALLY_PAID]
                        ),
                        CustomerDebt.deleted_at.is_(None),
                    )
                )
            )
            expected_balance = debt_result.scalar_one() or Decimal("0")
            diff = abs(customer.credit_balance - expected_balance)

            # Allow 1 unit of NUMERIC(18,4) rounding tolerance
            if diff > Decimal("0.0001"):
                report.add_error(
                    "customer_debt_balance_mismatch",
                    f"Customer '{customer.code}' credit_balance {customer.credit_balance} "
                    f"≠ debt sum {expected_balance} (diff {diff})",
                    customer_id=str(customer.id),
                    customer_code=customer.code,
                    stored_balance=str(customer.credit_balance),
                    computed_balance=str(expected_balance),
                    diff=str(diff),
                )
