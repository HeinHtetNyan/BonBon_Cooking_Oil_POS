from enum import StrEnum


class UserRole(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MANAGER = "manager"
    CASHIER = "cashier"
    WAREHOUSE = "warehouse"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


# Role hierarchy: higher index = more permissions
ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.VIEWER: 0,
    UserRole.CASHIER: 1,
    UserRole.WAREHOUSE: 1,
    UserRole.ACCOUNTANT: 2,
    UserRole.MANAGER: 3,
    UserRole.ADMIN: 4,
    UserRole.SUPER_ADMIN: 5,
}


def has_permission(user_role: UserRole, required_role: UserRole) -> bool:
    """True if user_role has at least as many permissions as required_role."""
    return ROLE_HIERARCHY.get(user_role, -1) >= ROLE_HIERARCHY.get(required_role, 999)
