"""
Generic base repository implementing common CRUD operations.

Design:
- Repositories own ALL database access for a domain. Services must not
  call session.execute() directly.
- Soft-deleted records are excluded from all read operations by default.
  Pass `include_deleted=True` to override.
- Repositories receive a session via constructor injection (not DI decorators)
  so they can be composed in services without FastAPI's DI machinery.
- Type variable `ModelT` is bound to Base, ensuring full type safety.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base
from app.database.mixins import SoftDeleteMixin

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # Internal helpers

    def _base_query(self, include_deleted: bool = False) -> Select:  # type: ignore[type-arg]
        """Build base SELECT with optional soft-delete filter."""
        q = select(self.model)
        if not include_deleted and issubclass(self.model, SoftDeleteMixin):
            q = q.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return q

    # Read operations

    async def get_by_id(
        self,
        record_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> ModelT | None:
        q = self._base_query(include_deleted).where(self.model.id == record_id)  # type: ignore[attr-defined]
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(
        self,
        record_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> ModelT:
        from app.core.exceptions import NotFoundError

        record = await self.get_by_id(record_id, include_deleted=include_deleted)
        if record is None:
            raise NotFoundError(self.model.__name__, record_id)
        return record

    async def list(
        self,
        *,
        filters: list[Any] | None = None,
        order_by: Any | None = None,
        limit: int | None = None,
        offset: int | None = None,
        include_deleted: bool = False,
    ) -> list[ModelT]:
        q = self._base_query(include_deleted)
        if filters:
            q = q.where(and_(*filters))
        if order_by is not None:
            q = q.order_by(order_by)
        if offset is not None:
            q = q.offset(offset)
        if limit is not None:
            q = q.limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        filters: list[Any] | None = None,
        include_deleted: bool = False,
    ) -> int:
        q = select(func.count()).select_from(self.model)
        if not include_deleted and issubclass(self.model, SoftDeleteMixin):
            q = q.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        if filters:
            q = q.where(and_(*filters))
        result = await self._session.execute(q)
        return result.scalar_one()

    async def exists(self, *filters: Any, include_deleted: bool = False) -> bool:
        q = select(func.count()).select_from(self.model).where(and_(*filters))
        if not include_deleted and issubclass(self.model, SoftDeleteMixin):
            q = q.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        result = await self._session.execute(q)
        return result.scalar_one() > 0

    # Write operations

    async def create(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()  # populate server-generated defaults
        await self._session.refresh(instance)
        return instance

    async def create_many(self, instances: list[ModelT]) -> list[ModelT]:
        self._session.add_all(instances)
        await self._session.flush()
        for instance in instances:
            await self._session.refresh(instance)
        return instances

    async def update(self, instance: ModelT, **fields: Any) -> ModelT:
        for key, value in fields.items():
            setattr(instance, key, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def soft_delete(self, instance: ModelT) -> ModelT:
        if not isinstance(instance, SoftDeleteMixin):
            raise TypeError(f"{self.model.__name__} does not support soft delete")
        instance.soft_delete()  # type: ignore[union-attr]
        await self._session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        """Hard delete — only call from scheduled cleanup tasks, never from application code."""
        await self._session.delete(instance)
        await self._session.flush()
