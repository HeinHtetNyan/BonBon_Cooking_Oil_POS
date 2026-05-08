"""
Finance module HTTP routes.

Router structure
----------------
  /finance/accounts          — Chart of accounts CRUD + balance queries
  /finance/payment-methods   — Payment method catalog CRUD
  /finance/debts             — Customer debt lifecycle + payments
  /finance/journal-entries   — Ledger read-only queries

All mutating endpoints use the service layer exclusively. Repositories are
never imported here. All responses use the ok() / paginated() envelope helpers.

Role requirements
-----------------
  VIEWER / any authenticated: read-only payment methods
  CASHIER+:  record debt payments, read debts
  ACCOUNTANT+: read journal entries
  MANAGER+:  list accounts, write-off debts
  ADMIN+:    create accounts, create payment methods, patch payment methods

Pagination
----------
Endpoints that return lists accept `page` (default 1) and `per_page`
(default 25) query parameters via PaginationParams.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas.base import (
    PaginatedResponse,
    SuccessResponse,
    ok,
    paginated,
)
from app.common.utils.pagination import PaginationParams
from app.database.session import get_db_session
from app.modules.auth.dependencies import get_current_active_user, require_role
from app.modules.finance.dependencies import get_debt_service, get_ledger_service
from app.modules.finance.enums import AccountType, DebtStatus, get_normal_balance
from app.modules.finance.models import FinancialAccount, PaymentMethod
from app.modules.finance.repositories import (
    CustomerDebtRepository,
    FinancialAccountRepository,
    JournalEntryRepository,
    PaymentMethodRepository,
)
from app.modules.finance.schemas import (
    AccountBalanceResponse,
    CustomerDebtResponse,
    DebtPaymentCreate,
    DebtPaymentResponse,
    FinancialAccountCreate,
    FinancialAccountResponse,
    FinancialAccountUpdate,
    JournalEntryCreate,
    JournalEntryResponse,
    PaymentMethodCreate,
    PaymentMethodResponse,
    PaymentMethodUpdate,
)
from app.modules.finance.services import DebtService, LedgerService
from app.modules.users.enums import UserRole
from app.modules.users.models import User

router = APIRouter(prefix="/finance", tags=["Finance"])


# Accounts

accounts_router = APIRouter(prefix="/accounts", tags=["Finance – Accounts"])


@accounts_router.get(
    "",
    response_model=PaginatedResponse[FinancialAccountResponse],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
    summary="List all financial accounts",
)
async def list_accounts(
    pagination: Annotated[PaginationParams, Depends()],
    account_type: Annotated[AccountType | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
) -> PaginatedResponse[FinancialAccountResponse]:
    repo = FinancialAccountRepository(session)
    filters = []
    if account_type is not None:
        filters.append(FinancialAccount.account_type == account_type)
    if is_active is not None:
        filters.append(FinancialAccount.is_active.is_(is_active))

    items = await repo.list(
        filters=filters or None,
        order_by=FinancialAccount.sort_order.asc(),
        offset=pagination.offset,
        limit=pagination.limit,
    )
    total = await repo.count(filters=filters or None)

    responses = [
        FinancialAccountResponse.model_validate(item) for item in items
    ]
    return paginated(responses, page=pagination.page, per_page=pagination.per_page, total=total)


@accounts_router.post(
    "",
    response_model=SuccessResponse[FinancialAccountResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    summary="Create a new financial account",
)
async def create_account(
    data: FinancialAccountCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(get_current_active_user)] = None,  # type: ignore[assignment]
) -> SuccessResponse[FinancialAccountResponse]:
    from app.core.exceptions import ConflictError

    repo = FinancialAccountRepository(session)

    existing = await repo.get_by_code(data.code)
    if existing is not None:
        raise ConflictError(f"Financial account with code '{data.code}' already exists")

    account = FinancialAccount(
        code=data.code,
        name=data.name,
        account_type=data.account_type,
        normal_balance=get_normal_balance(data.account_type),
        description=data.description,
        parent_code=data.parent_code,
        sort_order=data.sort_order,
        is_system=False,
        is_active=True,
        created_by=str(current_user.id),
        updated_by=str(current_user.id),
    )
    created = await repo.create(account)
    return ok(FinancialAccountResponse.model_validate(created))


@accounts_router.get(
    "/{code}",
    response_model=SuccessResponse[FinancialAccountResponse],
    dependencies=[Depends(get_current_active_user)],
    summary="Get account detail with current balance",
)
async def get_account(
    code: str,
    ledger: Annotated[LedgerService, Depends(get_ledger_service)] = None,  # type: ignore[assignment]
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
) -> SuccessResponse[FinancialAccountResponse]:
    repo = FinancialAccountRepository(session)
    account = await repo.get_system_account(code)
    balance = await repo.calculate_balance(account.id)

    response = FinancialAccountResponse.model_validate(account)
    response.calculated_balance = balance
    return ok(response)


@accounts_router.get(
    "/{code}/balance",
    response_model=SuccessResponse[AccountBalanceResponse],
    dependencies=[Depends(get_current_active_user)],
    summary="Get account balance, optionally as of a historical date",
)
async def get_account_balance(
    code: str,
    as_of_date: Annotated[
        str | None,
        Query(
            description="Balance as of this date (YYYY-MM-DD). Omit for current balance.",
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ] = None,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
) -> SuccessResponse[AccountBalanceResponse]:
    repo = FinancialAccountRepository(session)
    account = await repo.get_system_account(code)
    balance = await repo.calculate_balance(account.id, as_of_date)

    return ok(
        AccountBalanceResponse(
            account_code=account.code,
            account_name=account.name,
            balance=balance,
            account_type=account.account_type,
            normal_balance=account.normal_balance,
            as_of_date=as_of_date,
        )
    )


@accounts_router.patch(
    "/{code}",
    response_model=SuccessResponse[FinancialAccountResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    summary="Update a financial account",
)
async def update_account(
    code: str,
    data: FinancialAccountUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(get_current_active_user)] = None,  # type: ignore[assignment]
) -> SuccessResponse[FinancialAccountResponse]:
    repo = FinancialAccountRepository(session)
    account = await repo.get_system_account(code)

    update_fields: dict = {"updated_by": str(current_user.id)}
    if data.name is not None:
        update_fields["name"] = data.name
    if data.description is not None:
        update_fields["description"] = data.description
    if data.parent_code is not None:
        update_fields["parent_code"] = data.parent_code
    if data.sort_order is not None:
        update_fields["sort_order"] = data.sort_order
    if data.is_active is not None:
        update_fields["is_active"] = data.is_active

    updated = await repo.update(account, **update_fields)
    return ok(FinancialAccountResponse.model_validate(updated))


# Payment Methods

pm_router = APIRouter(prefix="/payment-methods", tags=["Finance – Payment Methods"])


@pm_router.get(
    "",
    response_model=SuccessResponse[list[PaymentMethodResponse]],
    dependencies=[Depends(get_current_active_user)],
    summary="List active payment methods",
)
async def list_payment_methods(
    include_inactive: Annotated[bool, Query()] = False,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
) -> SuccessResponse[list[PaymentMethodResponse]]:
    repo = PaymentMethodRepository(session)
    if include_inactive:
        items = await repo.list(order_by=PaymentMethod.sort_order.asc())
    else:
        items = await repo.get_active()
    return ok([PaymentMethodResponse.model_validate(pm) for pm in items])


@pm_router.post(
    "",
    response_model=SuccessResponse[PaymentMethodResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    summary="Create a payment method",
)
async def create_payment_method(
    data: PaymentMethodCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(get_current_active_user)] = None,  # type: ignore[assignment]
) -> SuccessResponse[PaymentMethodResponse]:
    from app.core.exceptions import ConflictError

    repo = PaymentMethodRepository(session)
    existing = await repo.get_by_code(data.code)
    if existing is not None:
        raise ConflictError(f"Payment method with code '{data.code}' already exists")

    pm = PaymentMethod(
        code=data.code,
        name=data.name,
        method_type=data.method_type,
        linked_account_code=data.linked_account_code,
        sort_order=data.sort_order,
        is_active=True,
        created_by=str(current_user.id),
        updated_by=str(current_user.id),
    )
    created = await repo.create(pm)
    return ok(PaymentMethodResponse.model_validate(created))


@pm_router.patch(
    "/{pm_id}",
    response_model=SuccessResponse[PaymentMethodResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    summary="Update a payment method",
)
async def update_payment_method(
    pm_id: UUID,
    data: PaymentMethodUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(get_current_active_user)] = None,  # type: ignore[assignment]
) -> SuccessResponse[PaymentMethodResponse]:
    repo = PaymentMethodRepository(session)
    pm = await repo.get_by_id_or_raise(pm_id)

    update_fields: dict = {"updated_by": str(current_user.id)}
    if data.name is not None:
        update_fields["name"] = data.name
    if data.linked_account_code is not None:
        update_fields["linked_account_code"] = data.linked_account_code
    if data.is_active is not None:
        update_fields["is_active"] = data.is_active
    if data.sort_order is not None:
        update_fields["sort_order"] = data.sort_order

    updated = await repo.update(pm, **update_fields)
    return ok(PaymentMethodResponse.model_validate(updated))


# Debts

debts_router = APIRouter(prefix="/debts", tags=["Finance – Customer Debts"])


@debts_router.get(
    "",
    response_model=PaginatedResponse[CustomerDebtResponse],
    dependencies=[Depends(require_role(UserRole.CASHIER))],
    summary="List customer debts with optional filters",
)
async def list_debts(
    pagination: Annotated[PaginationParams, Depends()],
    customer_id: Annotated[UUID | None, Query()] = None,
    debt_status: Annotated[DebtStatus | None, Query(alias="status")] = None,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
) -> PaginatedResponse[CustomerDebtResponse]:
    from app.modules.finance.models import CustomerDebt

    repo = CustomerDebtRepository(session)
    filters = []
    if customer_id is not None:
        filters.append(CustomerDebt.customer_id == customer_id)
    if debt_status is not None:
        filters.append(CustomerDebt.status == debt_status)

    items = await repo.list(
        filters=filters or None,
        order_by=CustomerDebt.created_at.desc(),
        offset=pagination.offset,
        limit=pagination.limit,
    )
    total = await repo.count(filters=filters or None)

    return paginated(
        [CustomerDebtResponse.model_validate(d) for d in items],
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
    )


@debts_router.get(
    "/{debt_id}",
    response_model=SuccessResponse[CustomerDebtResponse],
    dependencies=[Depends(require_role(UserRole.CASHIER))],
    summary="Get a single debt record",
)
async def get_debt(
    debt_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
) -> SuccessResponse[CustomerDebtResponse]:
    repo = CustomerDebtRepository(session)
    debt = await repo.get_by_id_or_raise(debt_id)
    return ok(CustomerDebtResponse.model_validate(debt))


@debts_router.post(
    "/{debt_id}/payments",
    response_model=SuccessResponse[DebtPaymentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.CASHIER))],
    summary="Record a payment against an outstanding debt",
)
async def record_debt_payment(
    debt_id: UUID,
    data: DebtPaymentCreate,
    debt_svc: Annotated[DebtService, Depends(get_debt_service)] = None,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(get_current_active_user)] = None,  # type: ignore[assignment]
) -> SuccessResponse[DebtPaymentResponse]:
    payment, _debt = await debt_svc.record_payment(
        debt_id=debt_id,
        payment_method_code=data.payment_method_code,
        amount=data.amount,
        transaction_date=data.transaction_date,
        reference_number=data.reference_number,
        notes=data.notes,
        actor=str(current_user.id),
    )
    return ok(DebtPaymentResponse.model_validate(payment))


@debts_router.post(
    "/{debt_id}/cancel",
    response_model=SuccessResponse[CustomerDebtResponse],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
    summary="Write off (cancel) an outstanding debt",
)
async def cancel_debt(
    debt_id: UUID,
    reason: Annotated[str, Query(min_length=3, max_length=512)] = "Written off by manager",
    debt_svc: Annotated[DebtService, Depends(get_debt_service)] = None,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(get_current_active_user)] = None,  # type: ignore[assignment]
) -> SuccessResponse[CustomerDebtResponse]:
    debt = await debt_svc.cancel_debt(
        debt_id=debt_id,
        reason=reason,
        actor=str(current_user.id),
    )
    return ok(CustomerDebtResponse.model_validate(debt))


# Journal Entries

journal_router = APIRouter(prefix="/journal-entries", tags=["Finance – Journal Entries"])


@journal_router.get(
    "",
    response_model=PaginatedResponse[JournalEntryResponse],
    dependencies=[Depends(require_role(UserRole.ACCOUNTANT))],
    summary="Query journal entries with filters",
)
async def list_journal_entries(
    pagination: Annotated[PaginationParams, Depends()],
    account_code: Annotated[str | None, Query(max_length=16)] = None,
    start_date: Annotated[
        str | None,
        Query(description="Filter from this date (YYYY-MM-DD)", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    ] = None,
    end_date: Annotated[
        str | None,
        Query(description="Filter up to this date (YYYY-MM-DD)", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    ] = None,
    reference_type: Annotated[str | None, Query(max_length=64)] = None,
    reference_id: Annotated[str | None, Query(max_length=36)] = None,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,  # type: ignore[assignment]
) -> PaginatedResponse[JournalEntryResponse]:
    journal_repo = JournalEntryRepository(session)

    if account_code is not None:
        # Filter by account — resolve code to id first
        acct_repo = FinancialAccountRepository(session)
        account = await acct_repo.get_system_account(account_code)
        entries, total = await journal_repo.get_by_account(
            account_id=account.id,
            page=pagination.page,
            per_page=pagination.per_page,
            start_date=start_date,
            end_date=end_date,
        )
    elif reference_type is not None and reference_id is not None:
        # Filter by reference (e.g., all entries for a voucher)
        all_entries = await journal_repo.get_by_reference(reference_type, reference_id)
        # Apply manual date filters if needed
        if start_date is not None:
            all_entries = [e for e in all_entries if e.transaction_date >= start_date]
        if end_date is not None:
            all_entries = [e for e in all_entries if e.transaction_date <= end_date]
        total = len(all_entries)
        offset = pagination.offset
        entries = all_entries[offset : offset + pagination.per_page]
    else:
        # General paginated query
        from sqlalchemy import and_, select
        from app.modules.finance.models import JournalEntry

        filters = []
        if start_date is not None:
            filters.append(JournalEntry.transaction_date >= start_date)
        if end_date is not None:
            filters.append(JournalEntry.transaction_date <= end_date)
        if reference_type is not None:
            filters.append(JournalEntry.reference_type == reference_type)
        if reference_id is not None:
            filters.append(JournalEntry.reference_id == reference_id)

        from sqlalchemy import func

        count_q = select(func.count()).select_from(JournalEntry)
        if filters:
            count_q = count_q.where(and_(*filters))
        count_result = await session.execute(count_q)
        total = count_result.scalar_one()

        data_q = (
            select(JournalEntry)
            .order_by(
                JournalEntry.transaction_date.desc(),
                JournalEntry.created_at.desc(),
            )
            .offset(pagination.offset)
            .limit(pagination.per_page)
        )
        if filters:
            data_q = data_q.where(and_(*filters))
        data_result = await session.execute(data_q)
        entries = list(data_result.scalars().all())

    return paginated(
        [JournalEntryResponse.model_validate(e) for e in entries],
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
    )


@journal_router.post(
    "",
    response_model=SuccessResponse[JournalEntryResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ACCOUNTANT))],
    summary="Manually create a journal entry (adjustments, opening balances)",
)
async def create_journal_entry(
    data: JournalEntryCreate,
    ledger: Annotated[LedgerService, Depends(get_ledger_service)] = None,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(get_current_active_user)] = None,  # type: ignore[assignment]
) -> SuccessResponse[JournalEntryResponse]:
    entry = await ledger.record_transaction(
        debit_account_code=data.debit_account_code,
        credit_account_code=data.credit_account_code,
        amount=data.amount,
        transaction_type=data.transaction_type,
        description=data.description,
        transaction_date=data.transaction_date,
        reference_type=data.reference_type,
        reference_id=data.reference_id,
        actor=str(current_user.id),
    )
    return ok(JournalEntryResponse.model_validate(entry))


# Assemble main router

router.include_router(accounts_router)
router.include_router(pm_router)
router.include_router(debts_router)
router.include_router(journal_router)
