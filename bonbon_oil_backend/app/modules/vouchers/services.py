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
from app.modules.vouchers.schemas import VoucherCreate, VoucherItemCreate, VoucherPaymentCreate


class VoucherService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._voucher_repo = VoucherRepository(session)
        self._item_repo = VoucherItemRepository(session)
        self._payment_repo = VoucherPaymentRepository(session)

    # Public API

    async def create_voucher(self, data: VoucherCreate, *, actor: str) -> Voucher:
        """Create a DRAFT voucher with items and optional upfront payments."""
        voucher_number = await self._voucher_repo.next_voucher_number()

        voucher = Voucher(
            voucher_number=voucher_number,
            voucher_type=data.voucher_type,
            customer_id=data.customer_id,
            sale_date=str(data.sale_date),
            notes=data.notes,
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

        if data.payments:
            await self._add_payments(voucher, data.payments, actor=actor)

        return voucher

    async def confirm_voucher(self, voucher_id: UUID, *, actor: str) -> Voucher:
        """
        Confirm a DRAFT voucher: trigger inventory and ledger effects atomically.

        Steps:
          1. Validate status == DRAFT
          2. SALE_OUT inventory movements for each line item
          3. Double-entry journal entries for each payment received
          4. CustomerDebt if outstanding amount > 0
          5. Status transition: DRAFT → PAID / PARTIALLY_PAID / CONFIRMED
        """
        voucher = await self._voucher_repo.get_with_items_and_payments(voucher_id)
        if voucher is None:
            raise NotFoundError("Voucher", voucher_id)
        if voucher.status != VoucherStatus.DRAFT:
            raise VoucherLockedError

        await self._process_inventory_movements(voucher, actor=actor)
        await self._process_ledger_entries(voucher, actor=actor)

        new_status = self._determine_payment_status(voucher)
        await self._voucher_repo.update(voucher, status=new_status, updated_by=actor)

        if voucher.outstanding_amount > ZERO:
            await self._create_customer_debt_if_needed(voucher, actor=actor)

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
    ) -> Voucher:
        """
        Void (cancel) a voucher and reverse all its effects.

        - DRAFT voucher: simply marks CANCELLED; no ledger/inventory effects exist yet.
        - CONFIRMED/PARTIALLY_PAID/PAID: reverses all inventory movements and journal
          entries, then cancels any associated CustomerDebt (unless already PAID).
        """
        voucher = await self._voucher_repo.get_with_items_and_payments(voucher_id)
        if voucher is None:
            raise NotFoundError("Voucher", voucher_id)
        if voucher.status == VoucherStatus.CANCELLED:
            raise VoucherAlreadyCancelledError

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

        updated = await self._voucher_repo.update(
            voucher, status=VoucherStatus.CANCELLED, updated_by=actor
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
        subtotal = sum((item.line_total for item in items), ZERO)
        voucher.subtotal = round_money(subtotal)
        voucher.total_amount = round_money(
            subtotal - voucher.discount_amount + voucher.tax_amount
        )
        await self._session.flush()

    async def _add_payments(
        self,
        voucher: Voucher,
        payment_data: list[VoucherPaymentCreate],
        *,
        actor: str,
    ) -> None:
        total_paid = ZERO
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
            total_paid += pd.amount

        voucher.paid_amount = round_money(total_paid)
        await self._session.flush()

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
            if pm is None or pm.linked_account_code is None:
                # Skip unlinked payment methods (e.g., CREDIT type)
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
            raise BusinessRuleError("Credit sales require a customer to be set")

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
