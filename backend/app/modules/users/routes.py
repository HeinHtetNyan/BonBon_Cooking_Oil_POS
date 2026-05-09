"""User management endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.common.schemas.base import PaginatedResponse, SuccessResponse, ok, paginated
from app.common.utils.pagination import PaginationParams
from app.modules.auth.dependencies import get_current_active_user, require_role
from app.modules.users.dependencies import get_user_service
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserResponse, UserSummary, UserUpdate
from app.modules.users.services import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=SuccessResponse[UserResponse])
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[UserResponse]:
    return ok(UserResponse.model_validate(current_user))


@router.get(
    "",
    response_model=PaginatedResponse[UserSummary],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def list_users(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[UserService, Depends(get_user_service)],
) -> PaginatedResponse[UserSummary]:
    users, total = await service.list_users(pagination)
    return paginated(
        [UserSummary.model_validate(u) for u in users],
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
    )


@router.post(
    "",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def create_user(
    data: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[UserResponse]:
    user = await service.create_user(data, actor_id=str(current_user.id))
    return ok(UserResponse.model_validate(user))


@router.get("/{user_id}", response_model=SuccessResponse[UserResponse])
async def get_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[UserResponse]:
    user = await service.get_user(user_id)
    return ok(UserResponse.model_validate(user))


@router.patch(
    "/{user_id}",
    response_model=SuccessResponse[UserResponse],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[UserResponse]:
    user = await service.update_user(user_id, data, actor_id=str(current_user.id))
    return ok(UserResponse.model_validate(user))
