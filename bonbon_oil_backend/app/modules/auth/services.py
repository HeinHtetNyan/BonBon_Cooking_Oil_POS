"""
Authentication service.

Login flow:
1. Look up user by username
2. Verify password against bcrypt hash
3. Check account status / lockout
4. Issue access + refresh tokens
5. Update last_login_at

Account lockout: 5 failed attempts → 30-minute lockout.
This is a simple in-DB strategy. For production scale, use Redis counters.

Logout: access token is blacklisted in Redis with TTL = remaining token lifetime.
Password change: verifies current password, then updates hash.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.common.utils.datetime import utcnow
from app.core.exceptions import AccountInactiveError, CredentialsInvalidError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    needs_rehash,
    hash_password,
    verify_password,
)
from app.modules.auth.schemas import LoginResponse, TokenResponse
from app.modules.users.enums import UserStatus
from app.modules.users.models import User
from app.modules.users.repositories import UserRepository
from app.modules.users.schemas import UserResponse

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


class AuthService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._user_repo = UserRepository(session)

    async def login(self, username: str, password: str) -> LoginResponse:
        user = await self._user_repo.get_by_username(username)

        # Use constant-time comparison path to prevent timing oracle
        if user is None:
            verify_password(password, "$2b$12$placeholder_for_timing_safety_only")
            raise CredentialsInvalidError

        if user.is_deleted:
            raise CredentialsInvalidError

        if user.is_locked:
            raise AccountInactiveError("Account is temporarily locked. Try again later.")

        if not verify_password(password, user.hashed_password):
            await self._handle_failed_login(user)
            raise CredentialsInvalidError

        if user.status != UserStatus.ACTIVE:
            raise AccountInactiveError

        # Rehash on the fly if work factor needs updating
        if needs_rehash(user.hashed_password):
            await self._user_repo.update(user, hashed_password=hash_password(password))

        await self._user_repo.reset_failed_login(user)
        await self._user_repo.update(user, last_login_at=utcnow())

        tokens = self._issue_tokens(user)
        self._logger.info("auth.login", user_id=str(user.id), username=user.username)
        return LoginResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        from app.core.exceptions import TokenInvalidError

        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise TokenInvalidError

        user_id = payload["sub"]

        user = await self._user_repo.get_by_id(UUID(user_id))
        if user is None or user.status != UserStatus.ACTIVE:
            raise TokenInvalidError

        return self._issue_tokens(user)

    async def logout(
        self,
        access_token: str,
        refresh_token: str | None = None,
    ) -> None:
        """
        Blacklist the access token in Redis until it naturally expires.

        Uses SETEX with TTL = remaining token lifetime so the key expires
        automatically and no cleanup job is required.  Best-effort — if Redis
        is unavailable the logout still returns 200 to the client (the token
        will simply expire naturally).
        """
        from app.database.redis import redis_manager

        try:
            payload = decode_token(access_token)
            exp_ts = payload.get("exp")
            if exp_ts:
                ttl = int(exp_ts) - int(time.time())
                if ttl > 0:
                    await redis_manager.client.setex(
                        f"blacklisted_token:{access_token[:64]}",
                        ttl,
                        "1",
                    )
        except Exception:
            pass  # Best-effort logout

        self._logger.info("auth.logout")

    async def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
        *,
        actor: str,
    ) -> None:
        """Verify current password, then update the hash."""
        user = await self._user_repo.get_by_id_or_raise(user_id)
        if not verify_password(current_password, user.hashed_password):
            raise CredentialsInvalidError("Current password is incorrect")

        await self._user_repo.update(
            user,
            hashed_password=hash_password(new_password),
            updated_by=actor,
        )
        self._logger.info("auth.password_changed", user_id=str(user_id))

    async def is_token_blacklisted(self, token: str) -> bool:
        """Return True if the token has been explicitly revoked via logout."""
        from app.database.redis import redis_manager

        try:
            result = await redis_manager.client.get(f"blacklisted_token:{token[:64]}")
            return result is not None
        except Exception:
            return False

    def _issue_tokens(self, user: User) -> TokenResponse:
        from app.core.config import settings

        access_token = create_access_token(
            subject=user.id,
            roles=[user.role],
        )
        refresh_token = create_refresh_token(subject=user.id)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def _handle_failed_login(self, user: User) -> None:
        await self._user_repo.increment_failed_login(user)
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            await self._user_repo.update(user, locked_until=locked_until)
            self._logger.warning(
                "auth.account_locked",
                user_id=str(user.id),
                locked_until=locked_until.isoformat(),
            )
