"""Production module repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.common.repositories.base import BaseRepository
from app.modules.production.models import (
    ProductionBatch,
    ProductionMaterialUsage,
    ProductionOutput,
)


class ProductionBatchRepository(BaseRepository[ProductionBatch]):
    model = ProductionBatch

    async def get_by_number(self, batch_number: str) -> ProductionBatch | None:
        q = self._base_query().where(ProductionBatch.batch_number == batch_number)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_with_usages(self, batch_id: UUID) -> ProductionBatch | None:
        """Load batch with material_usages and outputs eagerly."""
        q = (
            select(ProductionBatch)
            .where(ProductionBatch.id == batch_id)
            .where(ProductionBatch.deleted_at.is_(None))
            .options(
                selectinload(ProductionBatch.material_usages),
                selectinload(ProductionBatch.outputs),
            )
        )
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_with_usages_for_update(self, batch_id: UUID) -> ProductionBatch | None:
        """
        Lock the batch row and eagerly load material_usages and outputs.

        Combining with_for_update() and selectinload() in one query ensures
        selectinload overrides the mapper-level lazy="noload" on initial load.
        A two-phase approach (lock first, then selectinload) fails because the
        first query already marks the relationships as "loaded" (empty), and
        the second selectinload sees them as already loaded and skips them.
        """
        q = (
            select(ProductionBatch)
            .where(ProductionBatch.id == batch_id)
            .where(ProductionBatch.deleted_at.is_(None))
            .with_for_update()
            .options(
                selectinload(ProductionBatch.material_usages),
                selectinload(ProductionBatch.outputs),
            )
        )
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def next_batch_number(self) -> str:
        """
        Generate the next batch number in format BATCHYYYYMMDD<seq>.

        Sequence is the count of batches created today (1-indexed, zero-padded to 4).
        Example: BATCH202506010001
        """
        today_str = datetime.now(UTC).strftime("%Y%m%d")
        prefix = f"BATCH{today_str}"

        # Count batches whose number starts with today's prefix
        from sqlalchemy import func

        q = (
            select(func.count())
            .select_from(ProductionBatch)
            .where(ProductionBatch.batch_number.like(f"{prefix}%"))
        )
        result = await self._session.execute(q)
        count: int = result.scalar_one()
        return f"{prefix}{(count + 1):04d}"


class ProductionMaterialUsageRepository(BaseRepository[ProductionMaterialUsage]):
    model = ProductionMaterialUsage

    async def get_by_batch(self, batch_id: UUID) -> list[ProductionMaterialUsage]:
        q = (
            select(ProductionMaterialUsage)
            .where(ProductionMaterialUsage.batch_id == batch_id)
            .order_by(ProductionMaterialUsage.created_at)
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())


class ProductionOutputRepository(BaseRepository[ProductionOutput]):
    model = ProductionOutput

    async def get_by_batch(self, batch_id: UUID) -> list[ProductionOutput]:
        q = (
            select(ProductionOutput)
            .where(ProductionOutput.batch_id == batch_id)
            .order_by(ProductionOutput.created_at)
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())
