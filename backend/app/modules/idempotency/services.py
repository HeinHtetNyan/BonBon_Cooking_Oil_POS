"""
Idempotency service.

Provides a request-level idempotency guarantee for state-changing API
endpoints. Clients supply an `Idempotency-Key` HTTP header; subsequent
retries with the same key return the original cached response.

Divergent retry detection
-------------------------
When a key is reused with a DIFFERENT request body (detected via SHA-256
hash comparison), the service raises IdempotencyConflictError (409).
This protects against accidentally using the same key for two different
operations.

Expiry
------
Keys expire after 24 hours (configurable). Expired keys are cleaned up
by a Celery task.

Thread safety
-------------
For concurrent requests with the same new key, the PostgreSQL unique
constraint on `key` ensures only one wins. The loser gets a
IntegrityError that the middleware converts to a retry instruction.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IdempotencyConflictError
from app.core.logging import get_logger
from app.modules.idempotency.models import IdempotencyKey
from app.modules.idempotency.repositories import IdempotencyKeyRepository

logger = get_logger(__name__)


class IdempotencyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = IdempotencyKeyRepository(session)

    @staticmethod
    def hash_body(body: bytes | dict | str | None) -> str:
        """Produce a stable SHA-256 hex digest for a request body."""
        if body is None:
            raw = b""
        elif isinstance(body, bytes):
            raw = body
        elif isinstance(body, dict):
            # Sort keys for stable serialization regardless of dict insertion order
            raw = json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
        else:
            raw = str(body).encode()
        return hashlib.sha256(raw).hexdigest()

    async def check(
        self,
        key: str,
        request_hash: str,
    ) -> IdempotencyKey | None:
        """
        Look up an idempotency key.

        Returns the stored IdempotencyKey if this key was seen before with
        the SAME request hash (safe to return cached response).

        Raises IdempotencyConflictError if the key was seen with a different
        request hash (divergent retry — caller used same key for different op).

        Returns None if the key has never been seen (proceed normally).
        """
        existing = await self._repo.get_by_key(key)
        if existing is None:
            return None

        if existing.is_expired:
            # Treat expired keys as if they never existed — allow re-use
            return None

        if existing.request_hash != request_hash:
            raise IdempotencyConflictError()

        logger.info(
            "idempotency.cache_hit",
            key=key,
            status_code=existing.response_status_code,
        )
        return existing

    async def store(
        self,
        key: str,
        request_hash: str,
        response_status_code: int,
        response_body: dict | None,
        actor: str,
        tenant_id: str = "default",
    ) -> IdempotencyKey:
        """
        Persist the result of a successful operation.

        Called after the operation completes successfully so the next
        identical retry can return the cached result.
        """
        record = IdempotencyKey(
            key=key,
            request_hash=request_hash,
            response_status_code=response_status_code,
            response_body=response_body,
            expires_at=IdempotencyKey.make_expiry(hours=24),
            actor=actor,
            tenant_id=tenant_id,
        )
        return await self._repo.create(record)

    async def cleanup_expired(self) -> int:
        """Delete expired keys. Called by Celery cleanup task."""
        count = await self._repo.delete_expired()
        if count:
            logger.info("idempotency.cleanup", deleted=count)
        return count
