"""
Production batch service.

Workflow:
  PLANNED → IN_PROGRESS → COMPLETED
                       ↘ CANCELLED  (also reachable from PLANNED)

All inventory effects are coordinated via InventoryService.
No direct session.execute() calls — delegate to repositories.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.common.utils.decimal import ZERO, round_money
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.modules.inventory.enums import MovementType, WeightUnit
from app.modules.inventory.repositories import InventoryItemRepository
from app.modules.inventory.services import InventoryService
from app.modules.production.enums import ProductionBatchStatus
from app.modules.production.models import (
    ProductionBatch,
    ProductionMaterialUsage,
    ProductionOutput,
)
from app.modules.production.repositories import (
    ProductionBatchRepository,
    ProductionMaterialUsageRepository,
    ProductionOutputRepository,
)
from app.modules.production.schemas import ProductionBatchCreate, ProductionBatchUpdate


class ProductionBatchService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._batch_repo = ProductionBatchRepository(session)
        self._usage_repo = ProductionMaterialUsageRepository(session)
        self._output_repo = ProductionOutputRepository(session)
        self._inv_service = InventoryService(session)
        self._inv_item_repo = InventoryItemRepository(session)

    async def create_batch(
        self,
        data: ProductionBatchCreate,
        *,
        actor: str,
        tenant_id: str = "default",
    ) -> ProductionBatch:
        """Create a PLANNED batch with material usage plan."""
        batch_number = await self._batch_repo.next_batch_number()

        batch = ProductionBatch(
            batch_number=batch_number,
            status=ProductionBatchStatus.PLANNED,
            output_item_id=data.output_item_id,
            expected_output=data.expected_output,
            output_unit=data.output_unit,
            start_date=data.start_date,
            notes=data.notes,
            created_by=actor,
            updated_by=actor,
            tenant_id=tenant_id,
        )
        await self._batch_repo.create(batch)

        for usage_data in data.material_usages:
            usage = ProductionMaterialUsage(
                batch_id=batch.id,
                material_item_id=usage_data.material_item_id,
                planned_quantity=usage_data.planned_quantity,
                unit=usage_data.unit,
                unit_cost=usage_data.unit_cost,
            )
            await self._usage_repo.create(usage)

        self._logger.info(
            "production.batch_created",
            batch_id=str(batch.id),
            batch_number=batch_number,
        )
        return batch

    async def get_batch(self, batch_id: UUID) -> ProductionBatch:
        """Get batch by ID, loading usages and outputs."""
        batch = await self._batch_repo.get_with_usages(batch_id)
        if batch is None:
            raise NotFoundError("ProductionBatch", batch_id)
        return batch

    async def update_batch(
        self,
        batch_id: UUID,
        data: ProductionBatchUpdate,
        *,
        actor: str,
    ) -> ProductionBatch:
        """Update notes and/or cost estimates on a non-completed batch."""
        batch = await self._batch_repo.get_by_id_or_raise(batch_id)
        if batch.status == ProductionBatchStatus.COMPLETED:
            raise BusinessRuleError("Cannot update a completed batch")
        if batch.status == ProductionBatchStatus.CANCELLED:
            raise BusinessRuleError("Cannot update a cancelled batch")

        fields: dict = {"updated_by": actor}
        if data.notes is not None:
            fields["notes"] = data.notes
        if data.total_labour_cost is not None:
            fields["total_labour_cost"] = round_money(data.total_labour_cost)
        if data.total_overhead_cost is not None:
            fields["total_overhead_cost"] = round_money(data.total_overhead_cost)

        return await self._batch_repo.update(batch, **fields)

    async def start_batch(self, batch_id: UUID, *, actor: str) -> ProductionBatch:
        """Transition PLANNED → IN_PROGRESS."""
        batch = await self._batch_repo.get_by_id_for_update_or_raise(batch_id)
        if batch.status != ProductionBatchStatus.PLANNED:
            raise BusinessRuleError(
                f"Cannot start batch in status '{batch.status}'. Must be PLANNED."
            )

        from app.common.utils.datetime import utcnow

        batch.bump_version()
        batch.bump_sync_version()
        return await self._batch_repo.update(
            batch,
            status=ProductionBatchStatus.IN_PROGRESS,
            start_date=utcnow().date().isoformat(),
            updated_by=actor,
            version_number=batch.version_number,
            sync_version=batch.sync_version,
        )

    async def complete_batch(
        self,
        batch_id: UUID,
        *,
        actual_material_usages: list[dict],
        outputs: list[dict],
        labour_cost: Decimal,
        overhead_cost: Decimal,
        actor: str,
        tenant_id: str = "default",
    ) -> ProductionBatch:
        """
        Complete a production batch:

        1. Record actual material consumption (PRODUCTION_CONSUMPTION movements).
        2. Record finished goods output (PRODUCTION_OUTPUT movements + ProductionOutput rows).
        3. Calculate total costs.
        4. Set status to COMPLETED.

        All effects are atomic — if anything fails, everything rolls back.
        """
        from app.common.utils.datetime import utcnow

        batch = await self._batch_repo.get_with_usages_for_update(batch_id)
        if batch is None:
            raise NotFoundError("ProductionBatch", batch_id)
        if batch.status != ProductionBatchStatus.IN_PROGRESS:
            raise BusinessRuleError(
                f"Cannot complete batch in status '{batch.status}'. Must be IN_PROGRESS."
            )

        total_material_cost = ZERO

        # 1. Consume materials
        for usage_update in actual_material_usages:
            usage_id = usage_update["usage_id"]
            actual_qty = usage_update["actual_quantity"]

            usage = next(
                (u for u in batch.material_usages if str(u.id) == str(usage_id)),
                None,
            )
            if usage is None:
                raise NotFoundError("ProductionMaterialUsage", usage_id)

            unit = WeightUnit(usage.unit)

            await self._inv_service.record_movement(
                item_id=usage.material_item_id,
                movement_type=MovementType.PRODUCTION_CONSUMPTION,
                quantity=actual_qty,
                unit=unit,
                unit_price=usage.unit_cost,
                reference_type="production_batch",
                reference_id=str(batch_id),
                notes=f"Material consumption for batch {batch.batch_number}",
                actor=actor,
                tenant_id=tenant_id,
            )

            await self._usage_repo.update(usage, actual_quantity=actual_qty)

            if usage.unit_cost is not None:
                total_material_cost += actual_qty * usage.unit_cost

        # 2. Record outputs
        total_actual_output = ZERO

        for output_data in outputs:
            output_item_id = output_data["output_item_id"]
            qty = output_data["quantity"]
            unit = WeightUnit(output_data["unit"])

            movement = await self._inv_service.record_movement(
                item_id=output_item_id,
                movement_type=MovementType.PRODUCTION_OUTPUT,
                quantity=qty,
                unit=unit,
                reference_type="production_batch",
                reference_id=str(batch_id),
                notes=f"Production output for batch {batch.batch_number}",
                actor=actor,
                tenant_id=tenant_id,
            )

            output = ProductionOutput(
                batch_id=batch_id,
                output_item_id=output_item_id,
                quantity=qty,
                unit=unit,
                inventory_movement_id=movement.id,
                actor=actor,
                tenant_id=tenant_id,
            )
            await self._output_repo.create(output)
            total_actual_output += qty

        # 3. Finalise batch
        batch.bump_version()
        batch.bump_sync_version()
        completed_batch = await self._batch_repo.update(
            batch,
            status=ProductionBatchStatus.COMPLETED,
            actual_output=total_actual_output,
            total_material_cost=round_money(total_material_cost),
            total_labour_cost=round_money(labour_cost),
            total_overhead_cost=round_money(overhead_cost),
            end_date=utcnow().date().isoformat(),
            completed_at=utcnow(),
            updated_by=actor,
            version_number=batch.version_number,
            sync_version=batch.sync_version,
        )

        self._logger.info(
            "production.batch_completed",
            batch_id=str(batch_id),
            batch_number=batch.batch_number,
            total_actual_output=str(total_actual_output),
            total_cost=str(completed_batch.total_cost),
        )
        return completed_batch

    async def cancel_batch(
        self,
        batch_id: UUID,
        *,
        reason: str,
        actor: str,
    ) -> ProductionBatch:
        """
        Cancel a batch.

        - PLANNED → CANCELLED (no inventory effects).
        - IN_PROGRESS → reverses all inventory movements, then CANCELLED.
        - COMPLETED or already CANCELLED → raises BusinessRuleError.
        """
        batch = await self._batch_repo.get_by_id_for_update_or_raise(batch_id)

        if batch.status == ProductionBatchStatus.COMPLETED:
            raise BusinessRuleError("Cannot cancel a completed batch")
        if batch.status == ProductionBatchStatus.CANCELLED:
            raise BusinessRuleError("Batch is already cancelled")

        if batch.status == ProductionBatchStatus.IN_PROGRESS:
            await self._inv_service.reverse_all_for_reference(
                reference_type="production_batch",
                reference_id=str(batch_id),
                reason=reason,
                actor=actor,
            )

        from app.common.utils.datetime import utcnow

        batch.bump_version()
        batch.bump_sync_version()
        cancelled_batch = await self._batch_repo.update(
            batch,
            status=ProductionBatchStatus.CANCELLED,
            cancelled_at=utcnow(),
            cancellation_reason=reason,
            updated_by=actor,
            version_number=batch.version_number,
            sync_version=batch.sync_version,
        )

        self._logger.info(
            "production.batch_cancelled",
            batch_id=str(batch_id),
            reason=reason,
        )
        return cancelled_batch

    async def list_batches(
        self,
        params,
        *,
        status_filter: ProductionBatchStatus | None = None,
    ) -> tuple[list[ProductionBatch], int]:
        """List batches with optional status filter and pagination."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.common.utils.pagination import paginate_query

        q = (
            select(ProductionBatch)
            .where(ProductionBatch.deleted_at.is_(None))
            .order_by(ProductionBatch.created_at.desc())
            .options(
                selectinload(ProductionBatch.material_usages),
                selectinload(ProductionBatch.outputs),
            )
        )
        if status_filter is not None:
            q = q.where(ProductionBatch.status == status_filter)

        return await paginate_query(self._session, q, params)
