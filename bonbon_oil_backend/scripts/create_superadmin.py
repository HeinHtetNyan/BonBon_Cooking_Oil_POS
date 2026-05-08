#!/usr/bin/env python3
"""
One-time script: create initial super admin user.

Usage:
    python scripts/create_superadmin.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("APP_ENV", "development")


async def main() -> None:
    import getpass

    username = input("Username [admin]: ").strip() or "admin"
    email = input("Email: ").strip()
    full_name = input("Full name [Super Admin]: ").strip() or "Super Admin"
    password = getpass.getpass("Password (min 8 chars, 1 uppercase, 1 digit): ").strip()

    if not email:
        print("Email is required")
        sys.exit(1)

    from app.core.config import settings
    from app.database.session import db_manager
    from app.modules.users.enums import UserRole, UserStatus
    from app.modules.users.models import User
    from app.core.security import hash_password

    db_manager.init(settings.database_url)

    async with db_manager.session() as session:
        from sqlalchemy import select

        existing = await session.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            print(f"User '{username}' already exists")
            return

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role=UserRole.SUPER_ADMIN,
            status=UserStatus.ACTIVE,
            hashed_password=hash_password(password),
        )
        session.add(user)

    print(f"Super admin '{username}' created successfully")
    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
