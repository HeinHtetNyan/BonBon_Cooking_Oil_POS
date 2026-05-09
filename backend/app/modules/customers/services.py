"""Customer service — business logic for customer management."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.common.utils.decimal import ZERO
from app.common.utils.pagination import PaginationParams, paginate_query
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.customers.enums import CustomerStatus, CustomerType
from app.modules.customers.models import Customer
from app.modules.customers.repositories import CustomerRepository
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate


class CustomerService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = CustomerRepository(session)

    async def create_customer(self, data: CustomerCreate, *, actor: str) -> Customer:
        """Create a new customer with auto-generated code."""
        if data.phone is not None:
            existing = await self._repo.get_by_phone(data.phone)
            if existing is not None:
                raise ConflictError(
                    f"A customer with phone '{data.phone}' already exists"
                )

        # Auto-generate code: CUST + zero-padded count (e.g. CUST000001)
        count = await self._repo.count()
        code = f"CUST{(count + 1):06d}"

        # Ensure code uniqueness (handles race conditions / deletions)
        while await self._repo.code_exists(code):
            count += 1
            code = f"CUST{(count + 1):06d}"

        customer = Customer(
            code=code,
            name=data.name,
            phone=data.phone,
            address=data.address,
            customer_type=data.customer_type,
            credit_balance=ZERO,
            status=CustomerStatus.ACTIVE,
            notes=data.notes,
            created_by=actor,
            updated_by=actor,
        )
        return await self._repo.create(customer)

    async def get_customer(self, customer_id: UUID) -> Customer:
        """Get a customer by ID, raising NotFoundError if missing."""
        customer = await self._repo.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer", customer_id)
        return customer

    async def update_customer(
        self,
        customer_id: UUID,
        data: CustomerUpdate,
        *,
        actor: str,
    ) -> Customer:
        """Update customer fields. Only set fields are updated."""
        customer = await self.get_customer(customer_id)

        update_fields = data.model_dump(exclude_none=True)

        # Validate phone uniqueness if changing phone
        new_phone = update_fields.get("phone")
        if new_phone is not None and new_phone != customer.phone:
            existing = await self._repo.get_by_phone(new_phone)
            if existing is not None and existing.id != customer_id:
                raise ConflictError(
                    f"A customer with phone '{new_phone}' already exists"
                )

        if update_fields:
            update_fields["updated_by"] = actor
            await self._repo.update(customer, **update_fields)

        return customer

    async def deactivate_customer(self, customer_id: UUID, *, actor: str) -> Customer:
        """Set customer status to INACTIVE (soft-delete equivalent)."""
        customer = await self._repo.get_by_id_for_update_or_raise(customer_id)
        customer.bump_version()
        customer.bump_sync_version()
        return await self._repo.update(
            customer,
            status=CustomerStatus.INACTIVE,
            updated_by=actor,
            version_number=customer.version_number,
            sync_version=customer.sync_version,
        )

    async def list_customers(
        self,
        params: PaginationParams,
        *,
        q: str | None = None,
        customer_type: CustomerType | None = None,
        status: CustomerStatus | None = None,
    ) -> tuple[list[Customer], int]:
        """List customers with optional filters and pagination."""
        query = (
            select(Customer)
            .where(Customer.deleted_at.is_(None))
            .order_by(Customer.name)
        )

        if q is not None and q.strip():
            search_term = f"%{q.strip()}%"
            query = query.where(
                or_(
                    Customer.name.ilike(search_term),
                    Customer.phone.ilike(search_term),
                    Customer.code.ilike(search_term),
                )
            )

        if customer_type is not None:
            query = query.where(Customer.customer_type == customer_type)

        if status is not None:
            query = query.where(Customer.status == status)

        return await paginate_query(self._session, query, params)

    async def get_debt_summary(self, customer_id: UUID) -> dict:
        """Return debt summary for a customer."""
        await self.get_customer(customer_id)  # ensure customer exists

        from app.modules.finance.models import CustomerDebt
        from app.modules.finance.enums import DebtStatus

        # Total original debt
        total_result = await self._session.execute(
            select(func.coalesce(func.sum(CustomerDebt.original_amount), Decimal("0")))
            .where(CustomerDebt.customer_id == customer_id)
            .where(CustomerDebt.deleted_at.is_(None))
        )
        total_debt: Decimal = Decimal(str(total_result.scalar_one()))

        # Outstanding debt (not fully paid or written off)
        outstanding_result = await self._session.execute(
            select(
                func.coalesce(
                    func.sum(CustomerDebt.original_amount - CustomerDebt.paid_amount),
                    Decimal("0"),
                )
            )
            .where(CustomerDebt.customer_id == customer_id)
            .where(CustomerDebt.deleted_at.is_(None))
            .where(CustomerDebt.status.in_([DebtStatus.OUTSTANDING, DebtStatus.PARTIALLY_PAID]))
        )
        outstanding_debt: Decimal = Decimal(str(outstanding_result.scalar_one()))

        # Paid debt
        paid_result = await self._session.execute(
            select(func.coalesce(func.sum(CustomerDebt.paid_amount), Decimal("0")))
            .where(CustomerDebt.customer_id == customer_id)
            .where(CustomerDebt.deleted_at.is_(None))
        )
        paid_debt: Decimal = Decimal(str(paid_result.scalar_one()))

        # Debt count
        count_result = await self._session.execute(
            select(func.count())
            .select_from(CustomerDebt)
            .where(CustomerDebt.customer_id == customer_id)
            .where(CustomerDebt.deleted_at.is_(None))
        )
        debt_count: int = count_result.scalar_one()

        return {
            "total_debt": total_debt,
            "outstanding_debt": outstanding_debt,
            "paid_debt": paid_debt,
            "debt_count": debt_count,
        }

    async def search_customers(self, query: str, limit: int = 20) -> list[Customer]:
        """Quick search across name, phone, and code."""
        return await self._repo.search_by_name(query, limit=limit)
