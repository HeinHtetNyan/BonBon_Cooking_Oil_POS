"""
SQLAlchemy 2.0 declarative base and session management.

Architecture decisions:
- DeclarativeBase is subclassed once; all models inherit from it.
- `mapped_column` + `Mapped` annotations are used exclusively (no legacy Column).
- UUIDs are generated at the application layer (not DB-default) so we can
  reference them in code before the INSERT round-trip.
- All datetimes are stored as TIMESTAMP WITH TIME ZONE (timezone=True),
  ensuring UTC is preserved across application restarts and DB connections.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedColumn, mapped_column

# Naming convention
# Enforcing a naming convention allows Alembic to generate predictable
# constraint names for renaming operations in migrations.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """
    Declarative base for all ORM models.

    Provides:
    - Unified metadata with naming conventions
    - `__repr__` for debugging
    - Type annotation map for custom types
    """

    metadata = metadata

    type_annotation_map: dict[Any, Any] = {
        UUID: PGUUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }

    def __repr__(self) -> str:
        cols = ", ".join(
            f"{col.key}={getattr(self, col.key)!r}"
            for col in self.__table__.columns
            if col.key in ("id", "name", "code", "status")
        )
        return f"<{self.__class__.__name__}({cols})>"
