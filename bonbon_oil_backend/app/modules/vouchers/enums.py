from enum import StrEnum


class VoucherType(StrEnum):
    SALE = "sale"
    RETURN = "return"


class VoucherStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    CANCELLED = "cancelled"


# Statuses that allow modification
EDITABLE_STATUSES = frozenset({VoucherStatus.DRAFT})

# Statuses that block any modification
LOCKED_STATUSES = frozenset({
    VoucherStatus.CONFIRMED,
    VoucherStatus.PARTIALLY_PAID,
    VoucherStatus.PAID,
    VoucherStatus.CANCELLED,
})
