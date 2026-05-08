"""
Base service layer.

Services hold business logic and coordinate between repositories.
They must not import from FastAPI (no Request, no Depends) so they
remain testable without the HTTP layer.

Transactional safety:
- Services call `session.flush()` for intermediate state and let the
  FastAPI route boundary commit once. This keeps the entire request in
  one database transaction.
- Services that must commit mid-operation (e.g., post-payment inventory
  adjustment) must be explicit about why and document the invariant.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger


class BaseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._logger = get_logger(self.__class__.__module__)
