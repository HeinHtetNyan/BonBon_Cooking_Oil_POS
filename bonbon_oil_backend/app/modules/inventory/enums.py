from enum import StrEnum


class InventoryItemType(StrEnum):
    RAW_MATERIAL = "raw_material"
    FINISHED_OIL = "finished_oil"
    PACKAGING = "packaging"
    CONSUMABLE = "consumable"


class MovementType(StrEnum):
    # Inbound
    PURCHASE_IN = "purchase_in"
    PRODUCTION_OUTPUT = "production_output"
    ADJUSTMENT_IN = "adjustment_in"
    RETURN_IN = "return_in"
    TRANSFER_IN = "transfer_in"
    OPENING_BALANCE = "opening_balance"

    # Outbound
    SALE_OUT = "sale_out"
    PRODUCTION_CONSUMPTION = "production_consumption"
    ADJUSTMENT_OUT = "adjustment_out"
    WASTAGE = "wastage"
    TRANSFER_OUT = "transfer_out"
    SAMPLE_OUT = "sample_out"

    # Corrections
    CORRECTION = "correction"

    # Reversal (used to undo a previous movement, e.g., void a voucher)
    VOID_REVERSAL = "void_reversal"


INBOUND_MOVEMENTS = frozenset({
    MovementType.PURCHASE_IN,
    MovementType.PRODUCTION_OUTPUT,
    MovementType.ADJUSTMENT_IN,
    MovementType.RETURN_IN,
    MovementType.TRANSFER_IN,
    MovementType.OPENING_BALANCE,
})

OUTBOUND_MOVEMENTS = frozenset({
    MovementType.SALE_OUT,
    MovementType.PRODUCTION_CONSUMPTION,
    MovementType.ADJUSTMENT_OUT,
    MovementType.WASTAGE,
    MovementType.TRANSFER_OUT,
    MovementType.SAMPLE_OUT,
})


class WeightUnit(StrEnum):
    """
    Myanmar traditional weight units used in the oil trade.

    1 viss (peittha) = 100 ticals (kyattha)
    1 tical ≈ 16.33 grams
    1 viss ≈ 1.633 kg
    """
    VISS = "viss"
    TICAL = "tical"
    KG = "kg"
    LITER = "liter"
    UNIT = "unit"  # for packaging/consumables


class InventoryMovementStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
