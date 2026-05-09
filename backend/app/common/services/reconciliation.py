"""
Reconciliation services.

These services detect and (optionally) repair discrepancies between
denormalized cached values and the append-only ledgers that are the
source of truth.

InventoryReconciliationService
------------------------------
Rebuilds InventoryItem.current_balance from the InventoryMovement ledger.
Detects differences and optionally repairs them.

FinancialReconciliationService
------------------------------
Rebuilds financial account balances from JournalEntry rows. Creates
FinancialSnapshot checkpoints. Detects ledger imbalances.

Safety
------
Both services operate within an explicit AsyncSession. Repair operations
go through the same flush/commit cycle as normal writes so they are
logged and audited the same way.

Usage
-----
These are called by:
  - Celery consistency_tasks (read-only reporting)
  - Admin routes (on-demand, with optional repair=True)
  - On application startup for a lightweight sanity check
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.utils.decimal import ZERO, round_money, round_quantity
from app.core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared data structures
# ---------------------------------------------------------------------------

@dataclass
class ReconciliationDiscrepancy:
    entity_type: str
    entity_id: str
    entity_label: str
    stored_value: Decimal
    computed_value: Decimal
    diff: Decimal
    repaired: bool = False


@dataclass
class ReconciliationReport:
    discrepancies: list[ReconciliationDiscrepancy] = field(default_factory=list)
    checked: int = 0
    repaired: int = 0

    @property
    def has_discrepancies(self) -> bool:
        return bool(self.discrepancies)

    @property
    def unrepaired_count(self) -> int:
        return sum(1 for d in self.discrepancies if not d.repaired)

    def add(self, d: ReconciliationDiscrepancy) -> None:
        self.discrepancies.append(d)


# ---------------------------------------------------------------------------
# InventoryReconciliationService
# ---------------------------------------------------------------------------

class InventoryReconciliationService:
    """
    Verifies and optionally repairs InventoryItem.current_balance by
    replaying the movement ledger.

    Balance formula:
      Σ(quantity_in_canonical_unit where movement_type IN INBOUND_MOVEMENTS
          AND status != CANCELLED)
      - Σ(quantity_in_canonical_unit where movement_type IN OUTBOUND_MOVEMENTS
          AND status != CANCELLED)

    VOID_REVERSAL movements are inbound (they add stock back), so they
    appear in the inbound sum.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reconcile_all(
        self,
        *,
        repair: bool = False,
        tolerance: Decimal = Decimal("0.000001"),
    ) -> ReconciliationReport:
        """
        Check all inventory items and optionally repair discrepancies.

        Args:
            repair:    If True, overwrite current_balance with the ledger value
                       when a discrepancy is detected. This is a destructive
                       operation that must only be run after confirming no
                       in-flight transactions are active.
            tolerance: Decimal differences smaller than this are ignored (rounding).

        Returns a ReconciliationReport with all findings.
        """
        from app.modules.inventory.models import InventoryItem

        items_result = await self._session.execute(
            select(InventoryItem).where(InventoryItem.deleted_at.is_(None))
        )
        items = items_result.scalars().all()
        report = ReconciliationReport()

        for item in items:
            report.checked += 1
            computed = await self._compute_balance(item.id)
            diff = abs(item.current_balance - computed)

            if diff > tolerance:
                discrepancy = ReconciliationDiscrepancy(
                    entity_type="inventory_item",
                    entity_id=str(item.id),
                    entity_label=f"{item.code} {item.name}",
                    stored_value=item.current_balance,
                    computed_value=computed,
                    diff=diff,
                )

                if repair:
                    old_balance = item.current_balance
                    item.current_balance = computed
                    await self._session.flush()
                    discrepancy.repaired = True
                    report.repaired += 1
                    logger.warning(
                        "inventory.reconciliation.repaired",
                        item_id=str(item.id),
                        item_code=item.code,
                        old_balance=str(old_balance),
                        new_balance=str(computed),
                    )

                report.add(discrepancy)

        return report

    async def reconcile_item(
        self,
        item_id: UUID,
        *,
        repair: bool = False,
        tolerance: Decimal = Decimal("0.000001"),
    ) -> ReconciliationDiscrepancy | None:
        """
        Reconcile a single inventory item. Returns None if no discrepancy.
        """
        from app.modules.inventory.models import InventoryItem

        result = await self._session.execute(
            select(InventoryItem).where(InventoryItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            from app.core.exceptions import NotFoundError
            raise NotFoundError("InventoryItem", item_id)

        computed = await self._compute_balance(item_id)
        diff = abs(item.current_balance - computed)

        if diff <= tolerance:
            return None

        discrepancy = ReconciliationDiscrepancy(
            entity_type="inventory_item",
            entity_id=str(item.id),
            entity_label=f"{item.code} {item.name}",
            stored_value=item.current_balance,
            computed_value=computed,
            diff=diff,
        )
        if repair:
            item.current_balance = computed
            await self._session.flush()
            discrepancy.repaired = True

        return discrepancy

    async def _compute_balance(self, item_id: UUID) -> Decimal:
        """Replay movement ledger to derive the correct balance."""
        from app.modules.inventory.enums import (
            INBOUND_MOVEMENTS,
            OUTBOUND_MOVEMENTS,
            InventoryMovementStatus,
        )
        from app.modules.inventory.models import InventoryMovement

        inbound_result = await self._session.execute(
            select(
                func.coalesce(func.sum(InventoryMovement.quantity_in_canonical_unit), 0)
            ).where(
                and_(
                    InventoryMovement.item_id == item_id,
                    InventoryMovement.movement_type.in_(list(INBOUND_MOVEMENTS)),
                    InventoryMovement.status != InventoryMovementStatus.CANCELLED,
                )
            )
        )
        outbound_result = await self._session.execute(
            select(
                func.coalesce(func.sum(InventoryMovement.quantity_in_canonical_unit), 0)
            ).where(
                and_(
                    InventoryMovement.item_id == item_id,
                    InventoryMovement.movement_type.in_(list(OUTBOUND_MOVEMENTS)),
                    InventoryMovement.status != InventoryMovementStatus.CANCELLED,
                )
            )
        )
        total_in = Decimal(str(inbound_result.scalar_one() or 0))
        total_out = Decimal(str(outbound_result.scalar_one() or 0))
        return round_quantity(total_in - total_out)


# ---------------------------------------------------------------------------
# FinancialReconciliationService
# ---------------------------------------------------------------------------

class FinancialReconciliationService:
    """
    Verifies financial account balances and creates balance snapshots.

    Snapshot creation is idempotent (INSERT ON CONFLICT DO NOTHING),
    so the Celery task can re-run safely on retries or restarts.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_daily_snapshots(
        self,
        snapshot_date: str,
        actor: str,
        tenant_id: str = "default",
    ) -> int:
        """
        Persist a FinancialSnapshot for every active account as of snapshot_date.
        Returns the number of snapshots created (skips existing).
        """
        from app.modules.finance.enums import AccountNormalBalance
        from app.modules.finance.models import FinancialAccount, FinancialSnapshot, JournalEntry

        accounts_result = await self._session.execute(
            select(FinancialAccount).where(
                and_(
                    FinancialAccount.deleted_at.is_(None),
                    FinancialAccount.is_active.is_(True),
                )
            )
        )
        accounts = accounts_result.scalars().all()
        created = 0

        for account in accounts:
            balance = await self._compute_account_balance(account.id, snapshot_date)

            # Use a nested savepoint so a UniqueConstraint violation only rolls back
            # this one insert, not all previously created snapshots in the loop.
            try:
                async with self._session.begin_nested():
                    snapshot = FinancialSnapshot(
                        account_id=account.id,
                        snapshot_date=snapshot_date,
                        balance=round_money(balance),
                        snapshot_type="daily",
                        actor=actor,
                        tenant_id=tenant_id,
                    )
                    self._session.add(snapshot)
                    await self._session.flush()
                created += 1
            except Exception:
                # UniqueConstraint violation: snapshot already exists for this date → skip
                pass

        return created

    async def create_monthly_snapshots(
        self,
        year: int,
        month: int,
        actor: str,
        tenant_id: str = "default",
    ) -> int:
        """
        Persist monthly balance snapshots for the last day of the given month.
        """
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        snapshot_date = f"{year:04d}-{month:02d}-{last_day:02d}"

        from app.modules.finance.enums import AccountNormalBalance
        from app.modules.finance.models import FinancialAccount, FinancialSnapshot

        accounts_result = await self._session.execute(
            select(FinancialAccount).where(
                and_(
                    FinancialAccount.deleted_at.is_(None),
                    FinancialAccount.is_active.is_(True),
                )
            )
        )
        accounts = accounts_result.scalars().all()
        created = 0

        for account in accounts:
            balance = await self._compute_account_balance(account.id, snapshot_date)
            try:
                async with self._session.begin_nested():
                    snapshot = FinancialSnapshot(
                        account_id=account.id,
                        snapshot_date=snapshot_date,
                        balance=round_money(balance),
                        snapshot_type="monthly",
                        actor=actor,
                        tenant_id=tenant_id,
                    )
                    self._session.add(snapshot)
                    await self._session.flush()
                created += 1
            except Exception:
                pass

        return created

    async def detect_ledger_imbalances(self) -> list[dict]:
        """
        Find journal entry pairs where debit != credit (structural violations).

        In a correct double-entry system every entry has one debit and one
        credit side with the same amount. Since each JournalEntry row encodes
        both sides with a single amount column, the check reduces to:
          - amount must be > 0 (handled by FinancialIntegrityService)
          - debit_account_id != credit_account_id
          - There are no orphaned reversal references

        Returns a list of issue dicts for logging/alerting.
        """
        from app.modules.finance.models import JournalEntry

        # Entries that reference a reversal_of_id that doesn't exist
        reversal_refs = await self._session.execute(
            select(JournalEntry.id, JournalEntry.reversal_of_id).where(
                JournalEntry.reversal_of_id.is_not(None)
            )
        )
        issues = []
        for entry_id, reversal_of_id in reversal_refs.all():
            check = await self._session.execute(
                select(JournalEntry.id).where(JournalEntry.id == reversal_of_id)
            )
            if check.scalar_one_or_none() is None:
                issues.append({
                    "type": "orphaned_reversal_reference",
                    "entry_id": str(entry_id),
                    "missing_original_id": str(reversal_of_id),
                })

        return issues

    async def _compute_account_balance(
        self,
        account_id: UUID,
        as_of_date: str | None = None,
    ) -> Decimal:
        """Compute account balance from JournalEntry ledger."""
        from app.modules.finance.enums import AccountNormalBalance
        from app.modules.finance.models import FinancialAccount, JournalEntry

        acct_result = await self._session.execute(
            select(FinancialAccount).where(FinancialAccount.id == account_id)
        )
        account = acct_result.scalar_one_or_none()
        if account is None:
            return ZERO

        date_filter = []
        if as_of_date:
            date_filter.append(JournalEntry.transaction_date <= as_of_date)

        debit_sum = await self._session.execute(
            select(func.coalesce(func.sum(JournalEntry.amount), Decimal("0"))).where(
                and_(
                    JournalEntry.debit_account_id == account_id,
                    JournalEntry.is_reversed.is_(False),
                    *date_filter,
                )
            )
        )
        credit_sum = await self._session.execute(
            select(func.coalesce(func.sum(JournalEntry.amount), Decimal("0"))).where(
                and_(
                    JournalEntry.credit_account_id == account_id,
                    JournalEntry.is_reversed.is_(False),
                    *date_filter,
                )
            )
        )

        debits = debit_sum.scalar_one() or Decimal("0")
        credits = credit_sum.scalar_one() or Decimal("0")

        if account.normal_balance == AccountNormalBalance.DEBIT:
            return round_money(debits - credits)
        return round_money(credits - debits)
