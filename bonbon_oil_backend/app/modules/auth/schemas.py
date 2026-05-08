"""Auth request/response schemas."""

from __future__ import annotations

from pydantic import Field, field_validator

from app.common.schemas.base import AppBaseModel
from app.modules.users.schemas import UserResponse


class LoginRequest(AppBaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(AppBaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(AppBaseModel):
    refresh_token: str


class LoginResponse(AppBaseModel):
    user: UserResponse
    tokens: TokenResponse


class LogoutRequest(AppBaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(AppBaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v
