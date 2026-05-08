"""
Finance module FastAPI dependencies.

These thin factory functions wire AsyncSession → Service so route handlers
receive a fully initialised service via Depends(). Keeping them here (rather
than inline in routes.py) allows tests to override them easily via
app.dependency_overrides.

Usage in a route:
    @router.post("/")
    async def my_endpoint(
        svc: Annotated[LedgerService, Depends(get_ledger_service)],
    ) -> ...:
        ...
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
from app.modules.finance.services import DebtService, LedgerService


def get_ledger_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LedgerService:
    """Dependency that provides a LedgerService bound to the request session."""
    return LedgerService(session)


def get_debt_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DebtService:
    """Dependency that provides a DebtService bound to the request session."""
    return DebtService(session)
