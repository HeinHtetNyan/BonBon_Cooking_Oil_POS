"""
Pydantic v2 base schemas and response envelope.

All API responses are wrapped in a standard envelope so clients always know
where to find data, pagination metadata, and errors — regardless of endpoint.

{
  "success": true,
  "data": {...} | [...],
  "meta": {"page": 1, "per_page": 25, ...},
  "error": null
}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

T = TypeVar("T")


class AppBaseModel(BaseModel):
    """
    Base for all application Pydantic models.

    - `from_attributes=True` allows construction from ORM objects.
    - `populate_by_name=True` allows both alias and field name on input.
    - Datetime fields are always serialized as ISO-8601 UTC strings.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=False,
    )

    @field_serializer("*", when_used="json", check_fields=False)  # type: ignore[misc]
    def _serialize_datetime(self, value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.isoformat()
        return value


class PaginationMeta(AppBaseModel):
    page: int = Field(ge=1)
    per_page: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_next: bool
    has_prev: bool

    @classmethod
    def build(cls, *, page: int, per_page: int, total: int) -> "PaginationMeta":
        total_pages = max(1, -(-total // per_page))  # ceiling division
        return cls(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


class ErrorDetail(AppBaseModel):
    code: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class SuccessResponse(AppBaseModel, Generic[T]):
    success: bool = True
    data: T
    meta: dict[str, Any] | None = None
    error: None = None


class PaginatedResponse(AppBaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    meta: PaginationMeta
    error: None = None


class ErrorResponse(AppBaseModel):
    success: bool = False
    data: None = None
    meta: None = None
    error: ErrorDetail


# Helpers

def ok(data: T, meta: dict[str, Any] | None = None) -> SuccessResponse[T]:
    return SuccessResponse(data=data, meta=meta)


def paginated(
    items: list[T],
    *,
    page: int,
    per_page: int,
    total: int,
) -> PaginatedResponse[T]:
    return PaginatedResponse(
        data=items,
        meta=PaginationMeta.build(page=page, per_page=per_page, total=total),
    )
