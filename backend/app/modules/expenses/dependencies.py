"""Expense module FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
from app.modules.expenses.services import ExpenseService


def get_expense_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExpenseService:
    return ExpenseService(session)
