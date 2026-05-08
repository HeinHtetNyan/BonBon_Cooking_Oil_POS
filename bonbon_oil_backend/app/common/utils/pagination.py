"""
Pagination utilities for SQLAlchemy queries.

`PaginationParams` is a FastAPI dependency that reads page/per_page from
query string and enforces MAX_PAGE_SIZE so clients cannot request unbounded
result sets.
"""

from __future__ import annotations

from typing import TypeVar

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

T = TypeVar("T")


class PaginationParams:
    """
    Reusable FastAPI query dependency for pagination.

    Usage:
        @router.get("/items")
        async def list_items(pagination: PaginationParams = Depends()):
            ...
    """

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
        per_page: int = Query(
            default=settings.DEFAULT_PAGE_SIZE,
            ge=1,
            le=settings.MAX_PAGE_SIZE,
            alias="per_page",
            description="Items per page",
        ),
    ) -> None:
        self.page = page
        self.per_page = per_page

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page

    def apply(self, query: Select) -> Select:  # type: ignore[type-arg]
        """Apply OFFSET/LIMIT to a SQLAlchemy Select statement."""
        return query.offset(self.offset).limit(self.limit)


async def paginate_query(
    session: AsyncSession,
    query: Select,  # type: ignore[type-arg]
    params: PaginationParams,
) -> tuple[list, int]:
    """
    Execute a paginated query and return (items, total_count).

    The total count query strips ORDER BY and wraps in a subquery so
    PostgreSQL can use the index for counting without fetching all rows.
    """
    # Count total matching rows
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_result = await session.execute(count_query)
    total: int = total_result.scalar_one()

    # Fetch page
    paginated = await session.execute(params.apply(query))
    items = list(paginated.scalars().all())

    return items, total
