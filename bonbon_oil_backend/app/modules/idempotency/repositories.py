"""Idempotency key repository."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.modules.idempotency.models import IdempotencyKey
from sqlalchemy.ext.asyncio import AsyncSession


class IdempotencyKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_key(self, key: str) -> IdempotencyKey | None:
        q = select(IdempotencyKey).where(IdempotencyKey.key == key)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_by_key_for_update(self, key: str) -> IdempotencyKey | None:
        """Lock row to prevent duplicate concurrent inserts."""
        q = (
            select(IdempotencyKey)
            .where(IdempotencyKey.key == key)
            .with_for_update()
        )
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def create(self, record: IdempotencyKey) -> IdempotencyKey:
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def delete_expired(self) -> int:
        """Remove all expired keys. Returns count of deleted rows."""
        result = await self._session.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.expires_at < datetime.now(UTC)
            )
        )
        return result.rowcount or 0
