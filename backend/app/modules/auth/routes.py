"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.common.schemas.base import SuccessResponse, ok
from app.modules.auth.dependencies import get_auth_service, get_current_active_user
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)
from app.modules.auth.services import AuthService
from app.modules.users.models import User
from app.modules.users.schemas import UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=SuccessResponse[LoginResponse])
async def login(
    data: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessResponse[LoginResponse]:
    result = await service.login(data.username, data.password)
    return ok(result)


@router.post("/refresh", response_model=SuccessResponse[TokenResponse])
async def refresh_tokens(
    data: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessResponse[TokenResponse]:
    tokens = await service.refresh(data.refresh_token)
    return ok(tokens)


@router.get("/me", response_model=SuccessResponse[UserResponse])
async def whoami(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[UserResponse]:
    return ok(UserResponse.model_validate(current_user))


@router.post("/logout", response_model=SuccessResponse[dict])
async def logout(
    request: Request,
    data: LogoutRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[dict]:
    """
    Blacklist the current access token in Redis so it cannot be reused.

    The Bearer token is extracted from the Authorization header.
    Logout is best-effort — it always returns 200 even if Redis is unavailable.
    """
    auth_header = request.headers.get("Authorization", "")
    access_token = ""
    if auth_header.startswith("Bearer "):
        access_token = auth_header[7:]

    await service.logout(access_token, data.refresh_token)
    return ok({"detail": "Logged out successfully"})


@router.post("/change-password", response_model=SuccessResponse[dict])
async def change_password(
    data: ChangePasswordRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SuccessResponse[dict]:
    """
    Change the current user's password.

    Requires the current (old) password for verification.
    New password must be at least 8 characters with one uppercase letter and one digit.
    """
    await service.change_password(
        user_id=current_user.id,
        current_password=data.current_password,
        new_password=data.new_password,
        actor=str(current_user.id),
    )
    return ok({"detail": "Password changed successfully"})
