"""
User model.

Passwords are stored as bcrypt hashes — never plaintext.
Roles are stored as a PostgreSQL ARRAY of strings for future multi-role support.
The `last_login_at` and `failed_login_count` columns support account lockout logic.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, Boolean, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import FullAuditMixin
from app.modules.users.enums import UserRole, UserStatus


class User(FullAuditMixin, Base):
    __tablename__ = "users"

    # Identity
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Auth
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        String(32),
        nullable=False,
        default=UserStatus.ACTIVE,
        index=True,
    )

    # Role — primary role (additional granular permissions in future ACL table)
    role: Mapped[UserRole] = mapped_column(
        String(32),
        nullable=False,
        default=UserRole.CASHIER,
        index=True,
    )

    # Security tracking
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)

    # Profile
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        from app.common.utils.datetime import utcnow

        return utcnow() < self.locked_until
