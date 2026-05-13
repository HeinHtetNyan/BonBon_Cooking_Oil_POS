"""User Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.common.schemas.base import AppBaseModel
from app.modules.users.enums import UserRole, UserStatus


class UserBase(AppBaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    role: UserRole = UserRole.CASHIER


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdate(AppBaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    avatar_url: str | None = Field(default=None, max_length=512)
    role: UserRole | None = None
    status: UserStatus | None = None


class UserChangePassword(AppBaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(UserBase):
    id: UUID
    status: UserStatus
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False


class UserSetPassword(AppBaseModel):
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserSummary(AppBaseModel):
    """Lightweight user representation for embedding in other responses."""

    id: UUID
    username: str
    email: str
    full_name: str
    phone: str | None
    role: UserRole
    status: UserStatus
    last_login_at: datetime | None
