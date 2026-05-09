"""Customer repository."""

from __future__ import annotations

from sqlalchemy import select

from app.common.repositories.base import BaseRepository
from app.modules.customers.models import Customer


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    async def get_by_code(self, code: str) -> Customer | None:
        q = self._base_query().where(Customer.code == code)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Customer | None:
        q = self._base_query().where(Customer.phone == phone)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def code_exists(self, code: str) -> bool:
        return await self.exists(Customer.code == code, include_deleted=True)

    async def search_by_name(self, query: str, limit: int = 20) -> list[Customer]:
        from sqlalchemy import or_

        q = (
            self._base_query()
            .where(
                or_(
                    Customer.name.ilike(f"%{query}%"),
                    Customer.phone.ilike(f"%{query}%"),
                    Customer.code.ilike(f"%{query}%"),
                )
            )
            .limit(limit)
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())
