"""User repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.common.repositories.base import BaseRepository
from app.modules.users.models import User


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_username(self, username: str) -> User | None:
        q = self._base_query().where(User.username == username)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        q = self._base_query().where(User.email == email)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def username_exists(self, username: str, exclude_id: UUID | None = None) -> bool:
        q = select(User).where(User.username == username)
        if exclude_id:
            q = q.where(User.id != exclude_id)
        result = await self._session.execute(q)
        return result.scalar_one_or_none() is not None

    async def email_exists(self, email: str, exclude_id: UUID | None = None) -> bool:
        q = select(User).where(User.email == email)
        if exclude_id:
            q = q.where(User.id != exclude_id)
        result = await self._session.execute(q)
        return result.scalar_one_or_none() is not None

    async def increment_failed_login(self, user: User) -> User:
        user.failed_login_count += 1
        await self._session.flush()
        return user

    async def reset_failed_login(self, user: User) -> User:
        user.failed_login_count = 0
        user.locked_until = None
        await self._session.flush()
        return user
