"""User management service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services.base import BaseService
from app.common.utils.pagination import PaginationParams, paginate_query
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password, needs_rehash, verify_password
from app.modules.users.enums import UserStatus
from app.modules.users.models import User
from app.modules.users.repositories import UserRepository
from app.modules.users.schemas import UserCreate, UserUpdate


class UserService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = UserRepository(session)

    async def create_user(self, data: UserCreate, *, actor_id: str | None = None) -> User:
        if await self._repo.username_exists(data.username):
            raise ConflictError(f"Username '{data.username}' is already taken")
        if await self._repo.email_exists(data.email):
            raise ConflictError(f"Email '{data.email}' is already registered")

        user = User(
            username=data.username,
            email=data.email,
            full_name=data.full_name,
            phone=data.phone,
            role=data.role,
            hashed_password=hash_password(data.password),
            status=UserStatus.ACTIVE,
            created_by=actor_id,
            updated_by=actor_id,
        )
        return await self._repo.create(user)

    async def get_user(self, user_id: UUID) -> User:
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User", user_id)
        return user

    async def update_user(
        self,
        user_id: UUID,
        data: UserUpdate,
        *,
        actor_id: str | None = None,
    ) -> User:
        user = await self.get_user(user_id)
        update_data = data.model_dump(exclude_none=True)
        if update_data:
            update_data["updated_by"] = actor_id
            await self._repo.update(user, **update_data)
        return user

    async def deactivate_user(self, user_id: UUID, *, actor_id: str | None = None) -> User:
        user = await self.get_user(user_id)
        return await self._repo.update(
            user,
            status=UserStatus.INACTIVE,
            updated_by=actor_id,
        )

    async def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
        *,
        actor_id: str | None = None,
    ) -> User:
        from app.core.exceptions import CredentialsInvalidError

        user = await self.get_user(user_id)
        if not verify_password(current_password, user.hashed_password):
            raise CredentialsInvalidError
        return await self._repo.update(
            user,
            hashed_password=hash_password(new_password),
            updated_by=actor_id,
        )

    async def set_password(
        self,
        user_id: UUID,
        new_password: str,
        *,
        actor_id: str | None = None,
    ) -> User:
        user = await self.get_user(user_id)
        return await self._repo.update(
            user,
            hashed_password=hash_password(new_password),
            updated_by=actor_id,
        )

    async def delete_user(self, user_id: UUID, *, actor_id: str | None = None) -> User:
        user = await self.get_user(user_id)
        await self._repo.soft_delete(user)
        return user

    async def list_users(
        self,
        params: PaginationParams,
    ) -> tuple[list[User], int]:
        from sqlalchemy import select

        from app.modules.users.models import User

        q = (
            select(User)
            .where(User.deleted_at.is_(None))
            .order_by(User.created_at.desc())
        )
        return await paginate_query(self._session, q, params)
