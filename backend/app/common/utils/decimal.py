"""
Decimal precision utilities for financial and inventory calculations.

Floating point is never used for money. All monetary values are stored as
NUMERIC(18, 4) in the database and represented as Python Decimal objects.

Inventory units (viss/tical) use 6 decimal places to support sub-tical precision.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


MONEY_PRECISION = Decimal("0.0001")     # 4 decimal places for MMK
QUANTITY_PRECISION = Decimal("0.000001")  # 6 decimal places for viss/tical
RATE_PRECISION = Decimal("0.000001")    # 6 decimal places for rates/ratios

ZERO = Decimal("0")
ONE = Decimal("1")


def round_money(value: Decimal) -> Decimal:
    """Round to 4 decimal places using ROUND_HALF_UP (banker-safe for MMK)."""
    return value.quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP)


def round_quantity(value: Decimal) -> Decimal:
    """Round inventory quantities to 6 decimal places."""
    return value.quantize(QUANTITY_PRECISION, rounding=ROUND_HALF_UP)


def round_rate(value: Decimal) -> Decimal:
    """Round rates/unit prices to 6 decimal places."""
    return value.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)


def to_decimal(value: str | int | float | Decimal) -> Decimal:
    """
    Safe conversion to Decimal.

    Float inputs are converted via string to avoid IEEE-754 precision drift.
    This is the ONLY acceptable path for float → Decimal.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(value)  # type: ignore[arg-type]
    except InvalidOperation as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc


def safe_divide(numerator: Decimal, denominator: Decimal, default: Decimal = ZERO) -> Decimal:
    """Division that returns `default` instead of raising on zero denominator."""
    if denominator == ZERO:
        return default
    return numerator / denominator
