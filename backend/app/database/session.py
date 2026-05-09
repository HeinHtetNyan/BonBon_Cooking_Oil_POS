"""
Async SQLAlchemy session manager.

DatabaseSessionManager is the single source of truth for engine and session
factory lifecycle. It is initialized once at startup and torn down at shutdown.

Design:
- One engine for the entire application (connection pool is shared).
- Sessions are created per-request and injected via FastAPI dependency.
- `session_context` is an async context manager for use in Celery workers
  where the FastAPI DI system is not available.
- `nullpool` is used in testing to avoid connection reuse across test
  function boundaries.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DatabaseSessionManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init(self, database_url: str, **engine_kwargs: Any) -> None:
        """
        Create engine and session factory.

        Called once from app lifespan. Accepts `**engine_kwargs` so tests
        can pass `poolclass=NullPool` without subclassing.
        """
        self._engine = create_async_engine(
            database_url,
            echo=settings.POSTGRES_ECHO,
            pool_size=settings.POSTGRES_POOL_SIZE,
            max_overflow=settings.POSTGRES_MAX_OVERFLOW,
            pool_timeout=settings.POSTGRES_POOL_TIMEOUT,
            pool_pre_ping=True,  # detect stale connections
            **engine_kwargs,
        )
        self._sessionmaker = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,  # prevent lazy-load errors after commit
            autobegin=True,
            autoflush=False,
        )
        logger.info("database.engine_created", url=self._redacted_url(database_url))

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None
            logger.info("database.engine_disposed")

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        """Raw connection context — use for DDL or migrations outside sessions."""
        if not self._engine:
            raise RuntimeError("DatabaseSessionManager is not initialized")
        async with self._engine.begin() as conn:
            yield conn

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """
        Session context manager for use outside of FastAPI DI (e.g., Celery workers).

        Commits on success, rolls back and re-raises on any exception.
        """
        if not self._sessionmaker:
            raise RuntimeError("DatabaseSessionManager is not initialized")
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @property
    def engine(self) -> AsyncEngine:
        if not self._engine:
            raise RuntimeError("DatabaseSessionManager is not initialized")
        return self._engine

    @staticmethod
    def _redacted_url(url: str) -> str:
        """Mask password in URL for safe logging."""
        try:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url)
            if parsed.password:
                netloc = f"{parsed.username}:***@{parsed.hostname}:{parsed.port}"
                return urlunparse(parsed._replace(netloc=netloc))
        except Exception:
            pass
        return url


# Application-level singleton
db_manager = DatabaseSessionManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a request-scoped async session.

    The session is committed on a clean exit. The caller is responsible
    for not committing mid-request — services call session.flush() instead
    of commit() for intermediate state; the request boundary commits once.
    """
    if not db_manager._sessionmaker:
        raise RuntimeError("DatabaseSessionManager is not initialized")
    async with db_manager._sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
