"""Reporting module FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
from app.modules.reporting.services import ReportingService


def get_reporting_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReportingService:
    return ReportingService(session)
