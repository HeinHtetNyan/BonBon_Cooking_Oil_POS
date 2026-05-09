"""Voucher repositories."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.common.repositories.base import BaseRepository
from app.modules.vouchers.models import Voucher, VoucherItem, VoucherPayment


class VoucherRepository(BaseRepository[Voucher]):
    model = Voucher

    async def get_by_number(self, voucher_number: str) -> Voucher | None:
        q = self._base_query().where(Voucher.voucher_number == voucher_number)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_with_items_and_payments(self, voucher_id: UUID) -> Voucher | None:
        from sqlalchemy.orm import selectinload

        q = (
            select(Voucher)
            .where(Voucher.id == voucher_id)
            .where(Voucher.deleted_at.is_(None))
            .options(
                selectinload(Voucher.items),
                selectinload(Voucher.payments),
            )
        )
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_with_items_and_payments_for_update(self, voucher_id: UUID) -> Voucher | None:
        """
        Lock the voucher row and eagerly load items + payments.

        Two-phase approach:
        1. Lock the header row with SELECT ... FOR UPDATE (prevents concurrent
           confirm/void operations on the same voucher).
        2. Explicit SELECT queries for items and payments (session.refresh()
           does not bypass the noload strategy on these relationships).
        """
        # Phase 1: lock header row
        lock_q = (
            select(Voucher)
            .where(Voucher.id == voucher_id)
            .where(Voucher.deleted_at.is_(None))
            .with_for_update()
        )
        result = await self._session.execute(lock_q)
        voucher = result.scalar_one_or_none()
        if voucher is None:
            return None

        # Phase 2: load relationships with explicit queries
        items_result = await self._session.execute(
            select(VoucherItem).where(VoucherItem.voucher_id == voucher_id)
        )
        voucher.items = list(items_result.scalars().all())

        payments_result = await self._session.execute(
            select(VoucherPayment).where(VoucherPayment.voucher_id == voucher_id)
        )
        voucher.payments = list(payments_result.scalars().all())

        return voucher

    async def next_voucher_number(self, prefix: str = "INV") -> str:
        """Generate next sequential voucher number."""
        from sqlalchemy import func

        q = select(func.count()).select_from(Voucher).where(
            Voucher.voucher_number.like(f"{prefix}%")
        )
        result = await self._session.execute(q)
        count = result.scalar_one()
        return f"{prefix}{str(count + 1).zfill(6)}"


class VoucherItemRepository(BaseRepository[VoucherItem]):
    model = VoucherItem

    async def get_by_voucher(self, voucher_id: UUID) -> list[VoucherItem]:
        q = select(VoucherItem).where(VoucherItem.voucher_id == voucher_id)
        result = await self._session.execute(q)
        return list(result.scalars().all())


class VoucherPaymentRepository(BaseRepository[VoucherPayment]):
    model = VoucherPayment

    async def get_by_voucher(self, voucher_id: UUID) -> list[VoucherPayment]:
        q = select(VoucherPayment).where(VoucherPayment.voucher_id == voucher_id)
        result = await self._session.execute(q)
        return list(result.scalars().all())
