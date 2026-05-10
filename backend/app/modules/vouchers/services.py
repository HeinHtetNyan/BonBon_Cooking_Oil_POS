"""
Voucher transaction engine.

Confirm flow (the critical path):
1. Load voucher with items + payments via selectinload
2. Create SALE_OUT inventory movements for each line item
3. Record double-entry ledger entries for each payment received
4. If there is an outstanding (unpaid) amount, record Accounts Receivable entry
5. If customer debt exists (outstanding > 0), create CustomerDebt record
6. Transition voucher status: DRAFT → PAID / PARTIALLY_PAID / CONFIRMED

Void flow:
1. Reverse all inventory movements tagged with (voucher, voucher_id)
2. Reverse all journal entries tagged with (voucher, voucher_id)
3. Cancel associated CustomerDebt (if not already PAID/WRITTEN_OFF)
4. Mark voucher CANCELLED

Edit (DRAFT only) flow:
1. Validate voucher is still DRAFT
2. Delete old items, create new items
3. Recalculate totals

All flows are atomic within the request transaction boundary.
Services never call session.commit(); the HTTP handler layer commits.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.common.utils.decimal import ZERO, round_money
from app.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    OptimisticLockError,
    VoucherAlreadyCancelledError,
    VoucherLockedError,
)
from app.modules.vouchers.enums import VoucherStatus, VoucherType
from app.modules.vouchers.models import Voucher, VoucherItem, VoucherPayment
from app.modules.vouchers.repositories import (
    VoucherItemRepository,
    VoucherPaymentRepository,
    VoucherRepository,
)
from app.modules.vouchers.schemas import VoucherCreate, VoucherItemCreate, VoucherPaymentCreate, VoucherPaymentSimple, VoucherUpdate


class VoucherService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._voucher_repo = VoucherRepository(session)
        self._item_repo = VoucherItemRepository(session)
        self._payment_repo = VoucherPaymentRepository(session)

    # Public API

    async def create_voucher(self, data: VoucherCreate, *, actor: str) -> Voucher:
        """Create a DRAFT voucher with items and optional upfront payments.

        When `data.auto_confirm=True`, the voucher is confirmed within the same
        transaction, avoiding the commit-timing race that causes an immediate
        /confirm call to return 404.
        """
        import json

        voucher_number = await self._voucher_repo.next_voucher_number()

        voucher = Voucher(
            voucher_number=voucher_number,
            voucher_type=data.voucher_type,
            customer_id=data.customer_id,
            sale_date=str(data.sale_date),
            notes=data.notes,
            extra_charges=json.dumps([ec.model_dump(mode="json") for ec in data.extra_charges]),
            status=VoucherStatus.DRAFT,
            created_by=actor,
            updated_by=actor,
        )
        await self._voucher_repo.create(voucher)

        items = [
            VoucherItem(
                voucher_id=voucher.id,
                inventory_item_id=item_data.inventory_item_id,
                quantity=item_data.quantity,
                unit=item_data.unit,
                unit_price=item_data.unit_price,
                discount_percent=item_data.discount_percent,
                notes=item_data.notes,
            )
            for item_data in data.items
        ]
        for item in items:
            item.recalculate()
        await self._item_repo.create_many(items)

        await self._recalculate_totals(voucher, items)

        payments: list[VoucherPayment] = []
        if data.payments:
            payments = await self._add_payments(voucher, data.payments, actor=actor)

        if data.auto_confirm:
            voucher.items = items
            voucher.payments = payments
            await self._run_confirm_in_place(voucher, actor=actor)

        return voucher

    async def confirm_voucher(
        self,
        voucher_id: UUID,
        *,
        actor: str,
        expected_version: int | None = None,
    ) -> Voucher:
        """
        Confirm a DRAFT voucher: trigger inventory and ledger effects atomically.

        Steps:
          1. Lock voucher row (SELECT ... FOR UPDATE) — prevents concurrent confirmations.
          2. Re-validate status == DRAFT after lock (prevents TOCTOU race).
          3. Optimistic lock check if expected_version is provided.
          4. SALE_OUT inventory movements for each line item.
          5. Double-entry journal entries for each payment received.
          6. CustomerDebt if outstanding amount > 0.
          7. Status transition: DRAFT → PAID / PARTIALLY_PAID / CONFIRMED.
          8. Bump version_number and sync_version.
        """
        # Lock the voucher row to prevent concurrent confirm/void operations
        voucher = await self._voucher_repo.get_with_items_and_payments_for_update(voucher_id)
        if voucher is None:
            raise NotFoundError("Voucher", voucher_id)

        # Optimistic lock check first: a stale version is more specific than
        # "voucher locked", and gives the client actionable information.
        if expected_version is not None and voucher.version_number != expected_version:
            raise OptimisticLockError("Voucher", expected_version, voucher.version_number)

        # Re-check status after acquiring lock — another request may have
        # confirmed it between our read and the lock acquisition
        if voucher.status != VoucherStatus.DRAFT:
            raise VoucherLockedError

        await self._process_inventory_movements(voucher, actor=actor)
        await self._process_ledger_entries(voucher, actor=actor)

        new_status = self._determine_payment_status(voucher)
        voucher.bump_version()
        voucher.bump_sync_version()
        await self._voucher_repo.update(
            voucher, status=new_status, updated_by=actor,
            version_number=voucher.version_number,
            sync_version=voucher.sync_version,
        )

        if voucher.outstanding_amount > ZERO:
            await self._create_customer_debt_if_needed(voucher, actor=actor)

        # If customer overpaid this voucher, apply the excess to their oldest outstanding debts
        excess = max(ZERO, voucher.paid_amount - voucher.total_amount)
        if excess > ZERO and voucher.customer_id:
            await self._apply_excess_to_customer_debts(voucher.customer_id, excess, actor=actor)

        self._logger.info(
            "voucher.confirmed",
            voucher_id=str(voucher_id),
            voucher_number=voucher.voucher_number,
            total=str(voucher.total_amount),
            status=new_status,
        )
        return voucher

    async def void_voucher(
        self,
        voucher_id: UUID,
        reason: str,
        *,
        actor: str,
        expected_version: int | None = None,
    ) -> Voucher:
        """
        Void (cancel) a voucher and reverse all its effects.

        Acquires a row-level lock before status check to prevent concurrent
        void operations from creating duplicate reversals.

        - DRAFT voucher: simply marks CANCELLED; no ledger/inventory effects exist yet.
        - CONFIRMED/PARTIALLY_PAID/PAID: reverses all inventory movements and journal
          entries, then cancels any associated CustomerDebt (unless already PAID).
        """
        # Lock before reading state (prevents duplicate void race)
        voucher = await self._voucher_repo.get_with_items_and_payments_for_update(voucher_id)
        if voucher is None:
            raise NotFoundError("Voucher", voucher_id)
        if voucher.status == VoucherStatus.CANCELLED:
            raise VoucherAlreadyCancelledError

        if expected_version is not None and voucher.version_number != expected_version:
            raise OptimisticLockError("Voucher", expected_version, voucher.version_number)

        if voucher.status != VoucherStatus.DRAFT:
            # Reverse inventory movements
            from app.modules.inventory.services import InventoryService

            inv_service = InventoryService(self._session)
            await inv_service.reverse_all_for_reference(
                reference_type="voucher",
                reference_id=str(voucher_id),
                reason=reason,
                actor=actor,
            )

            # Reverse all ledger entries
            from app.modules.finance.services import LedgerService

            ledger = LedgerService(self._session)
            await ledger.reverse_all_for_reference(
                reference_type="voucher",
                reference_id=str(voucher_id),
                reason=reason,
                actor=actor,
            )

            # Cancel associated CustomerDebt (if any and not already terminal)
            await self._cancel_voucher_debt(voucher_id, reason=reason, actor=actor)

        voucher.bump_version()
        voucher.bump_sync_version()
        updated = await self._voucher_repo.update(
            voucher,
            status=VoucherStatus.CANCELLED,
            updated_by=actor,
            version_number=voucher.version_number,
            sync_version=voucher.sync_version,
        )
        self._logger.info(
            "voucher.voided",
            voucher_id=str(voucher_id),
            voucher_number=voucher.voucher_number,
            reason=reason,
        )
        return updated

    async def update_items(
        self,
        voucher_id: UUID,
        items_data: list[VoucherItemCreate],
        *,
        actor: str,
    ) -> Voucher:
        """
        Replace all line items on a DRAFT voucher and recalculate totals.

        Only permitted while status == DRAFT. Confirmed vouchers must be voided
        and recreated — edit = void + new voucher.
        """
        voucher = await self._voucher_repo.get_with_items_and_payments(voucher_id)
        if voucher is None:
            raise NotFoundError("Voucher", voucher_id)
        if not voucher.is_editable:
            raise VoucherLockedError

        # Delete old items
        for item in voucher.items:
            await self._session.delete(item)
        await self._session.flush()

        # Create replacement items
        new_items = [
            VoucherItem(
                voucher_id=voucher_id,
                inventory_item_id=item_data.inventory_item_id,
                quantity=item_data.quantity,
                unit=item_data.unit,
                unit_price=item_data.unit_price,
                discount_percent=item_data.discount_percent,
                notes=item_data.notes,
            )
            for item_data in items_data
        ]
        for item in new_items:
            item.recalculate()
        await self._item_repo.create_many(new_items)

        voucher.items = new_items
        await self._recalculate_totals(voucher, new_items)
        await self._voucher_repo.update(voucher, updated_by=actor)

        return voucher

    async def update_voucher(self, voucher_id: UUID, data: VoucherUpdate, *, actor: str) -> Voucher:
        """Update voucher metadata (notes, customer, sale_date, extra_charges). Admin only."""
        import json

        voucher = await self._voucher_repo.get_with_items_and_payments(voucher_id)
        if voucher is None:
            raise NotFoundError("Voucher", voucher_id)

        updates: dict = {"updated_by": actor}
        if data.notes is not None:
            updates["notes"] = data.notes
        if data.customer_id is not None:
            updates["customer_id"] = data.customer_id
        if data.sale_date is not None:
            updates["sale_date"] = str(data.sale_date)
        if data.extra_charges is not None:
            updates["extra_charges"] = json.dumps(
                [ec.model_dump(mode="json") for ec in data.extra_charges]
            )
            voucher.extra_charges = updates["extra_charges"]
            await self._recalculate_totals(voucher, voucher.items)
            # Recalculate payment status after total changes
            updates["total_amount"] = voucher.total_amount
            updates["subtotal"] = voucher.subtotal
            updates["status"] = self._determine_payment_status(voucher)

        return await self._voucher_repo.update(voucher, **updates)

    async def record_payment(
        self,
        voucher_id: UUID,
        data: VoucherPaymentSimple,
        *,
        actor: str,
    ) -> Voucher:
        """Record a payment against a confirmed voucher, updating paid/outstanding amounts and status."""
        from app.modules.finance.repositories import PaymentMethodRepository
        from app.modules.finance.services import LedgerService

        # FOR UPDATE lock prevents two concurrent payments from both passing the
        # outstanding-amount check and producing an overpayment.
        voucher = await self._voucher_repo.get_with_items_and_payments_for_update(voucher_id)
        if voucher is None:
            raise NotFoundError("Voucher", voucher_id)
        if voucher.status == VoucherStatus.CANCELLED:
            raise VoucherAlreadyCancelledError
        if voucher.status == VoucherStatus.DRAFT:
            raise BusinessRuleError("Cannot record payment on a draft voucher. Confirm it first.")
        if voucher.outstanding_amount <= ZERO:
            raise BusinessRuleError("Voucher is already fully paid.")

        # Resolve payment method and validate it has a linked account for ledger routing
        pm_repo = PaymentMethodRepository(self._session)
        pm = await pm_repo.get_by_code(data.payment_method_code)
        if pm is None:
            raise NotFoundError("PaymentMethod", data.payment_method_code)
        if pm.linked_account_code is None:
            raise BusinessRuleError(
                f"Payment method '{pm.name}' has no linked financial account"
            )

        payment = VoucherPayment(
            voucher_id=voucher.id,
            payment_method_id=pm.id,
            amount=data.amount,
            reference_number=data.reference_number,
            notes=data.notes,
            actor=actor,
        )
        await self._payment_repo.create(payment)

        # Record the double-entry ledger effect: Dr Cash/Bank, Cr Accounts Receivable
        ledger = LedgerService(self._session)
        await ledger.record_debt_collection(
            payment_method_code=pm.linked_account_code,
            amount=data.amount,
            transaction_date=voucher.sale_date,
            reference_type="voucher",
            reference_id=str(voucher_id),
            description=f"{voucher.voucher_number} - payment ({pm.name})",
            actor=actor,
            tenant_id=voucher.tenant_id,
        )

        voucher.paid_amount = round_money(voucher.paid_amount + data.amount)
        new_status = self._determine_payment_status(voucher)
        await self._voucher_repo.update(voucher, paid_amount=voucher.paid_amount, status=new_status, updated_by=actor)

        # Also update the linked customer debt if any
        await self._apply_payment_to_debt(voucher_id, data.amount, actor=actor)

        # If payment exceeded this voucher's balance, apply the excess to other customer debts
        excess = max(ZERO, voucher.paid_amount - voucher.total_amount)
        if excess > ZERO and voucher.customer_id:
            await self._apply_excess_to_customer_debts(voucher.customer_id, excess, actor=actor)

        return await self.get_voucher(voucher_id)

    async def _apply_payment_to_debt(self, voucher_id: UUID, amount: Decimal, *, actor: str) -> None:
        """Reduce the CustomerDebt outstanding balance for this voucher."""
        from sqlalchemy import update as sa_update
        from app.modules.finance.repositories import CustomerDebtRepository
        from app.modules.finance.enums import DebtStatus
        from app.modules.finance.models import CustomerDebt

        debt_repo = CustomerDebtRepository(self._session)
        debt = await debt_repo.get_by_voucher(voucher_id)
        if debt is None or debt.status in (DebtStatus.PAID, DebtStatus.WRITTEN_OFF):
            return

        new_paid = round_money(min(debt.original_amount, debt.paid_amount + amount))
        new_status = DebtStatus.PAID if new_paid >= debt.original_amount else DebtStatus.PARTIALLY_PAID

        await self._session.execute(
            sa_update(CustomerDebt).where(CustomerDebt.id == debt.id).values(
                paid_amount=new_paid,
                status=new_status,
                updated_by=actor,
            )
        )

        # Update customer credit_balance, clamped to zero to prevent negative values
        if debt.customer_id:
            from sqlalchemy import func as sa_func
            from app.modules.customers.models import Customer
            await self._session.execute(
                sa_update(Customer).where(Customer.id == debt.customer_id).values(
                    credit_balance=sa_func.greatest(
                        Decimal("0"), Customer.credit_balance - amount
                    )
                )
            )

        await self._session.flush()

    async def get_voucher(self, voucher_id: UUID) -> Voucher:
        """Fetch a voucher with its items and payments. Raises NotFoundError if missing."""
        voucher = await self._voucher_repo.get_with_items_and_payments(voucher_id)
        if voucher is None:
            raise NotFoundError("Voucher", voucher_id)
        return voucher

    async def get_by_number(self, voucher_number: str) -> Voucher:
        """Fetch a voucher by voucher number."""
        voucher = await self._voucher_repo.get_by_number(voucher_number)
        if voucher is None:
            raise NotFoundError("Voucher", voucher_number)
        # Load items + payments
        return await self.get_voucher(voucher.id)

    async def list_vouchers(
        self,
        *,
        status: VoucherStatus | None = None,
        customer_id: UUID | None = None,
        voucher_type: VoucherType | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Voucher], int]:
        """Paginated list of vouchers with optional filters."""
        from sqlalchemy import func

        base = (
            select(Voucher)
            .where(Voucher.deleted_at.is_(None))
        )
        count_base = (
            select(func.count())
            .select_from(Voucher)
            .where(Voucher.deleted_at.is_(None))
        )

        filters = []
        if status is not None:
            filters.append(Voucher.status == status)
        if customer_id is not None:
            filters.append(Voucher.customer_id == customer_id)
        if voucher_type is not None:
            filters.append(Voucher.voucher_type == voucher_type)
        if start_date is not None:
            filters.append(Voucher.sale_date >= start_date)
        if end_date is not None:
            filters.append(Voucher.sale_date <= end_date)

        for f in filters:
            base = base.where(f)
            count_base = count_base.where(f)

        count_result = await self._session.execute(count_base)
        total: int = count_result.scalar_one()

        offset = (page - 1) * per_page
        data_result = await self._session.execute(
            base.order_by(Voucher.created_at.desc()).offset(offset).limit(per_page)
        )
        vouchers = list(data_result.scalars().all())

        return vouchers, total

    # Private helpers

    async def _recalculate_totals(
        self,
        voucher: Voucher,
        items: list[VoucherItem],
    ) -> None:
        import json

        subtotal = sum((item.line_total for item in items), ZERO)
        voucher.subtotal = round_money(subtotal)
        try:
            extra = json.loads(voucher.extra_charges or "[]")
            extra_total = sum(Decimal(str(e["amount"])) for e in extra)
        except (json.JSONDecodeError, KeyError, TypeError):
            extra_total = ZERO
        voucher.total_amount = round_money(
            subtotal - voucher.discount_amount + voucher.tax_amount + extra_total
        )
        await self._session.flush()

    async def _add_payments(
        self,
        voucher: Voucher,
        payment_data: list[VoucherPaymentCreate],
        *,
        actor: str,
    ) -> list[VoucherPayment]:
        total_paid = ZERO
        payments: list[VoucherPayment] = []
        for pd in payment_data:
            payment = VoucherPayment(
                voucher_id=voucher.id,
                payment_method_id=pd.payment_method_id,
                amount=pd.amount,
                reference_number=pd.reference_number,
                notes=pd.notes,
                actor=actor,
            )
            await self._payment_repo.create(payment)
            payments.append(payment)
            total_paid += pd.amount

        voucher.paid_amount = round_money(total_paid)
        await self._session.flush()
        return payments

    async def _run_confirm_in_place(self, voucher: Voucher, *, actor: str) -> None:
        """Confirm a freshly-created DRAFT voucher that has items/payments already set.

        Called from create_voucher when auto_confirm=True. No SELECT FOR UPDATE
        is needed because the voucher was just created in this same transaction —
        no other session can see it yet.
        """
        await self._process_inventory_movements(voucher, actor=actor)
        await self._process_ledger_entries(voucher, actor=actor)

        new_status = self._determine_payment_status(voucher)
        voucher.bump_version()
        voucher.bump_sync_version()
        await self._voucher_repo.update(
            voucher,
            status=new_status,
            updated_by=actor,
            version_number=voucher.version_number,
            sync_version=voucher.sync_version,
        )

        if voucher.outstanding_amount > ZERO:
            await self._create_customer_debt_if_needed(voucher, actor=actor)

        # If customer overpaid this voucher, apply the excess to their oldest outstanding debts
        excess = max(ZERO, voucher.paid_amount - voucher.total_amount)
        if excess > ZERO and voucher.customer_id:
            await self._apply_excess_to_customer_debts(voucher.customer_id, excess, actor=actor)

        self._logger.info(
            "voucher.confirmed",
            voucher_id=str(voucher.id),
            voucher_number=voucher.voucher_number,
            total=str(voucher.total_amount),
            status=new_status,
        )

    async def _process_inventory_movements(
        self,
        voucher: Voucher,
        *,
        actor: str,
    ) -> None:
        from app.modules.inventory.enums import MovementType, WeightUnit
        from app.modules.inventory.services import InventoryService

        inv_service = InventoryService(self._session)
        for item in voucher.items:
            try:
                unit = WeightUnit(item.unit)
            except ValueError:
                unit = WeightUnit.UNIT

            await inv_service.record_movement(
                item_id=item.inventory_item_id,
                movement_type=MovementType.SALE_OUT,
                quantity=item.quantity,
                unit=unit,
                unit_price=item.unit_price,
                transaction_date=voucher.sale_date,
                reference_type="voucher",
                reference_id=str(voucher.id),
                actor=actor,
                tenant_id=voucher.tenant_id,
            )

    async def _process_ledger_entries(
        self,
        voucher: Voucher,
        *,
        actor: str,
    ) -> None:
        """
        Record double-entry journal entries for the voucher.

        For each payment received:
            Dr: Cash/Bank/KBZPay account (via PaymentMethod.linked_account_code)
            Cr: Sales Revenue (4000)

        For any outstanding (credit) portion:
            Dr: Accounts Receivable (1100)
            Cr: Sales Revenue (4000)
        """
        from app.modules.finance.repositories import PaymentMethodRepository
        from app.modules.finance.services import LedgerService

        ledger = LedgerService(self._session)
        pm_repo = PaymentMethodRepository(self._session)

        for payment in voucher.payments:
            pm = await pm_repo.get_by_id(payment.payment_method_id)
            if pm is None:
                raise BusinessRuleError(
                    f"Payment method {payment.payment_method_id} no longer exists. "
                    "Cannot confirm voucher with a deleted payment method."
                )
            if pm.linked_account_code is None:
                # Intentionally unlinked method (e.g., CREDIT type) — skip ledger
                continue
            await ledger.record_sale_payment(
                payment_method_code=pm.linked_account_code,
                amount=payment.amount,
                transaction_date=voucher.sale_date,
                reference_type="voucher",
                reference_id=str(voucher.id),
                description=f"{voucher.voucher_number} - {pm.name}",
                actor=actor,
                tenant_id=voucher.tenant_id,
            )

        # Unpaid credit portion → Accounts Receivable
        outstanding = voucher.outstanding_amount
        if outstanding > ZERO:
            await ledger.record_credit_sale(
                amount=outstanding,
                transaction_date=voucher.sale_date,
                reference_type="voucher",
                reference_id=str(voucher.id),
                description=f"{voucher.voucher_number} - credit",
                actor=actor,
                tenant_id=voucher.tenant_id,
            )

    async def _apply_excess_to_customer_debts(
        self, customer_id: UUID, excess: Decimal, *, actor: str
    ) -> None:
        """Apply overpayment excess to the customer's oldest outstanding debts."""
        from sqlalchemy import update as sa_update, func as sa_func
        from app.modules.finance.repositories import CustomerDebtRepository
        from app.modules.finance.enums import DebtStatus
        from app.modules.finance.models import CustomerDebt
        from app.modules.customers.models import Customer

        debt_repo = CustomerDebtRepository(self._session)
        all_debts = await debt_repo.get_by_customer(customer_id)
        # oldest first
        outstanding_debts = [
            d for d in reversed(all_debts)
            if d.status in (DebtStatus.OUTSTANDING, DebtStatus.PARTIALLY_PAID)
        ]

        remaining = excess
        total_applied = ZERO
        for debt in outstanding_debts:
            if remaining <= ZERO:
                break
            debt_remaining = debt.original_amount - debt.paid_amount
            apply = min(remaining, debt_remaining)
            new_paid = round_money(debt.paid_amount + apply)
            new_status = DebtStatus.PAID if new_paid >= debt.original_amount else DebtStatus.PARTIALLY_PAID
            await self._session.execute(
                sa_update(CustomerDebt).where(CustomerDebt.id == debt.id).values(
                    paid_amount=new_paid,
                    status=new_status,
                    updated_by=actor,
                )
            )
            remaining -= apply
            total_applied += apply

        if total_applied > ZERO:
            await self._session.execute(
                sa_update(Customer).where(Customer.id == customer_id).values(
                    credit_balance=sa_func.greatest(
                        Decimal("0"), Customer.credit_balance - total_applied
                    )
                )
            )
        await self._session.flush()

    async def _create_customer_debt_if_needed(
        self,
        voucher: Voucher,
        *,
        actor: str,
    ) -> None:
        """Create a CustomerDebt record for the outstanding balance of a credit sale."""
        if voucher.outstanding_amount <= ZERO:
            return
        if voucher.customer_id is None:
            return  # Walk-in sale with no customer — skip debt tracking

        from app.modules.finance.services import DebtService

        debt_service = DebtService(self._session)
        await debt_service.create_debt(
            customer_id=voucher.customer_id,
            voucher_id=voucher.id,
            amount=voucher.outstanding_amount,
            actor=actor,
            tenant_id=voucher.tenant_id,
        )

    async def _cancel_voucher_debt(
        self,
        voucher_id: UUID,
        *,
        reason: str,
        actor: str,
    ) -> None:
        """Find and cancel the CustomerDebt for this voucher if it exists."""
        from app.modules.finance.enums import DebtStatus
        from app.modules.finance.repositories import CustomerDebtRepository
        from app.modules.finance.services import DebtService

        debt_repo = CustomerDebtRepository(self._session)
        debt = await debt_repo.get_by_voucher(voucher_id)
        if debt is None:
            return
        if debt.status in (DebtStatus.PAID, DebtStatus.WRITTEN_OFF):
            return

        debt_service = DebtService(self._session)
        await debt_service.cancel_debt(debt.id, reason=reason, actor=actor)

    @staticmethod
    def _determine_payment_status(voucher: Voucher) -> VoucherStatus:
        if voucher.paid_amount >= voucher.total_amount:
            return VoucherStatus.PAID
        if voucher.paid_amount > ZERO:
            return VoucherStatus.PARTIALLY_PAID
        return VoucherStatus.CONFIRMED
