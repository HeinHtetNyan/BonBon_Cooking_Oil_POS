from enum import StrEnum


class ExpenseCategory(StrEnum):
    LABOUR = "labour"
    UTILITIES = "utilities"
    TRANSPORT = "transport"
    MAINTENANCE = "maintenance"
    PACKAGING = "packaging"
    ADMINISTRATIVE = "administrative"
    MARKETING = "marketing"
    RENT = "rent"
    OTHER = "other"


class ExpenseStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    REJECTED = "rejected"
