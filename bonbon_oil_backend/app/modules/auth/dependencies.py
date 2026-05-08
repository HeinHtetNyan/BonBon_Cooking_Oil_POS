"""
FastAPI auth dependencies.

`get_current_active_user` is the primary dependency — use it on any
endpoint that requires authentication.

`require_role(role)` returns a dependency that additionally checks the
user's role level. It can be used directly in `dependencies=[...]` on
the router or applied to individual endpoints.

Token blacklist check is performed inline in `get_current_user` via a
direct Redis lookup to avoid circular import with AuthService.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AccountInactiveError, TokenInvalidError
from app.core.security import decode_token
from app.database.session import get_db_session
from app.modules.auth.services import AuthService
from app.modules.users.enums import UserRole, has_permission
from app.modules.users.models import User
from app.modules.users.repositories import UserRepository

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    if credentials is None:
        raise TokenInvalidError

    token = credentials.credentials
    payload = decode_token(token)

    # Token blacklist check
    # Performed directly (no AuthService instantiation) to keep this dependency
    # free of circular imports. Best-effort: if Redis is unavailable we allow
    # the request through rather than taking the whole API down.
    try:
        from app.database.redis import redis_manager

        blacklisted = await redis_manager.client.get(f"blacklisted_token:{token[:64]}")
        if blacklisted:
            raise TokenInvalidError("Token has been revoked")
    except TokenInvalidError:
        raise
    except Exception:
        pass  # Redis unavailable — allow request

    user_id_str: str = payload.get("sub", "")
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise TokenInvalidError

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise TokenInvalidError
    return user


async def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_active:
        raise AccountInactiveError
    if user.is_locked:
        raise AccountInactiveError("Account is temporarily locked")
    return user


def require_role(minimum_role: UserRole):
    """
    Dependency factory that enforces a minimum role requirement.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role(UserRole.ADMIN))])
    """

    async def _check_role(
        user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        from app.core.exceptions import RoleRequiredError

        if not has_permission(user.role, minimum_role):
            raise RoleRequiredError([minimum_role])
        return user

    return _check_role


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthService:
    return AuthService(session)
