"""
Unit-based pricing service for Bon Bon Oil ERP.

Oil is priced exclusively by price_per_viss. Users never enter a per-tical
price directly. This module derives the effective unit price from
price_per_viss + unit and computes line totals with optional discount.

Conversion:  1 viss = 100 ticals
  VISS:  unit_price = price_per_viss
  TICAL: unit_price = price_per_viss / 100

All arithmetic uses Decimal. Float is never used.
"""

from __future__ import annotations

from decimal import Decimal

from app.common.utils.decimal import ZERO, round_money

TICALS_PER_VISS = Decimal("100")

SUPPORTED_PRICING_UNITS: frozenset[str] = frozenset({"viss", "tical"})


def calculate_unit_price(unit: str, price_per_viss: Decimal) -> Decimal:
    """
    Derive the effective per-unit price from price_per_viss.

    Args:
        unit: "viss" or "tical" (case-insensitive)
        price_per_viss: price per full viss (>= 0)

    Returns:
        Effective per-unit price as Decimal (4 dp).

    Raises:
        ValueError: if unit is not supported or price_per_viss < 0.
    """
    if price_per_viss < ZERO:
        raise ValueError("price_per_viss must be >= 0")

    norm = unit.lower()
    if norm not in SUPPORTED_PRICING_UNITS:
        raise ValueError(
            f"Unsupported pricing unit '{unit}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_PRICING_UNITS))}"
        )

    if norm == "viss":
        return price_per_viss
    # tical
    return price_per_viss / TICALS_PER_VISS


def calculate_item_total(
    quantity: Decimal,
    unit: str,
    price_per_viss: Decimal,
    discount_percent: Decimal = ZERO,
) -> Decimal:
    """
    Calculate the monetary line total for one voucher item.

    Formula:
        unit_price   = calculate_unit_price(unit, price_per_viss)
        gross        = quantity * unit_price
        total        = round_money(gross - gross * discount_percent / 100)

    Args:
        quantity: item quantity — must be > 0
        unit: "viss" or "tical" (case-insensitive)
        price_per_viss: price per full viss — must be >= 0
        discount_percent: percentage discount 0–100 (default 0)

    Returns:
        Rounded monetary total (Decimal, 4 dp).

    Raises:
        ValueError: on invalid inputs.
    """
    if quantity <= ZERO:
        raise ValueError("quantity must be > 0")
    if price_per_viss < ZERO:
        raise ValueError("price_per_viss must be >= 0")

    unit_price = calculate_unit_price(unit, price_per_viss)
    gross = quantity * unit_price
    discount = gross * (discount_percent / Decimal("100"))
    return round_money(gross - discount)
