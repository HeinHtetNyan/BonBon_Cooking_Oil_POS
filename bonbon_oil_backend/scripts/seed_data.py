#!/usr/bin/env python3
"""
Seed script: loads reference data required for initial operation.

Seeds:
- Default payment methods (Cash, Bank Transfer, Mobile Payment)
- Default financial accounts (chart of accounts)
- Sample inventory items for testing
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("APP_ENV", "development")


async def main() -> None:
    from app.core.config import settings
    from app.database.session import db_manager

    db_manager.init(settings.database_url)

    async with db_manager.session() as session:
        await _seed_financial_accounts(session)
        await _seed_payment_methods(session)
        await _seed_inventory_items(session)

    await db_manager.close()
    print("Seed data loaded successfully")


async def _seed_financial_accounts(session) -> None:
    from app.modules.finance.enums import AccountType, get_normal_balance
    from app.modules.finance.models import FinancialAccount
    from sqlalchemy import select

    accounts = [
        # Assets
        {"code": "1000", "name": "Cash on Hand",           "account_type": AccountType.ASSET,   "sort_order": 10, "is_system": True},
        {"code": "1050", "name": "Digital Wallet (KBZPay/WavePay)", "account_type": AccountType.ASSET, "sort_order": 11, "is_system": True},
        {"code": "1060", "name": "Bank Account",           "account_type": AccountType.ASSET,   "sort_order": 12, "is_system": True},
        {"code": "1100", "name": "Accounts Receivable",    "account_type": AccountType.ASSET,   "sort_order": 20, "is_system": True},
        {"code": "1200", "name": "Raw Material Inventory", "account_type": AccountType.ASSET,   "sort_order": 30, "is_system": True},
        {"code": "1300", "name": "Finished Goods Inventory","account_type": AccountType.ASSET,  "sort_order": 31, "is_system": True},
        # Liabilities
        {"code": "2000", "name": "Accounts Payable",       "account_type": AccountType.LIABILITY, "sort_order": 50, "is_system": True},
        # Equity
        {"code": "3000", "name": "Owner Equity",           "account_type": AccountType.EQUITY,  "sort_order": 70, "is_system": True},
        # Revenue
        {"code": "4000", "name": "Sales Revenue",          "account_type": AccountType.REVENUE, "sort_order": 100, "is_system": True},
        # Expenses
        {"code": "5000", "name": "Cost of Goods Sold",     "account_type": AccountType.EXPENSE, "sort_order": 120, "is_system": True},
        {"code": "5100", "name": "Labour Expense",         "account_type": AccountType.EXPENSE, "sort_order": 121, "is_system": True},
        {"code": "5200", "name": "Overhead Expense",       "account_type": AccountType.EXPENSE, "sort_order": 122, "is_system": True},
        {"code": "5300", "name": "Utilities Expense",      "account_type": AccountType.EXPENSE, "sort_order": 123, "is_system": False},
        {"code": "5400", "name": "Maintenance Expense",    "account_type": AccountType.EXPENSE, "sort_order": 124, "is_system": False},
        {"code": "5500", "name": "Packaging Expense",      "account_type": AccountType.EXPENSE, "sort_order": 125, "is_system": False},
        {"code": "5900", "name": "Miscellaneous Expense",  "account_type": AccountType.EXPENSE, "sort_order": 130, "is_system": False},
    ]

    seeded = 0
    for a in accounts:
        existing = await session.execute(
            select(FinancialAccount).where(FinancialAccount.code == a["code"])
        )
        if not existing.scalar_one_or_none():
            normal_balance = get_normal_balance(a["account_type"])
            session.add(FinancialAccount(
                **a,
                normal_balance=normal_balance,
                is_active=True,
            ))
            seeded += 1
    await session.flush()
    print(f"  Financial accounts: {seeded} seeded ({len(accounts)} total)")


async def _seed_payment_methods(session) -> None:
    from app.modules.finance.enums import PaymentMethodType
    from app.modules.finance.models import PaymentMethod
    from sqlalchemy import select

    methods = [
        {
            "code": "CASH",
            "name": "Cash",
            "method_type": PaymentMethodType.CASH,
            "linked_account_code": "1000",
            "sort_order": 1,
        },
        {
            "code": "KBZ_PAY",
            "name": "KBZ Pay",
            "method_type": PaymentMethodType.KBZPAY,
            "linked_account_code": "1050",
            "sort_order": 2,
        },
        {
            "code": "WAVE_PAY",
            "name": "Wave Pay",
            "method_type": PaymentMethodType.WAVEPAY,
            "linked_account_code": "1050",
            "sort_order": 3,
        },
        {
            "code": "BANK_TRANSFER",
            "name": "Bank Transfer",
            "method_type": PaymentMethodType.BANK_TRANSFER,
            "linked_account_code": "1060",
            "sort_order": 4,
        },
        {
            "code": "CREDIT",
            "name": "Credit (On Account)",
            "method_type": PaymentMethodType.CREDIT,
            "linked_account_code": None,
            "sort_order": 5,
        },
    ]

    seeded = 0
    for m in methods:
        existing = await session.execute(
            select(PaymentMethod).where(PaymentMethod.code == m["code"])
        )
        if not existing.scalar_one_or_none():
            session.add(PaymentMethod(**m))
            seeded += 1
    await session.flush()
    print(f"  Payment methods: {seeded} seeded ({len(methods)} total)")


async def _seed_inventory_items(session) -> None:
    from decimal import Decimal

    from app.modules.inventory.enums import InventoryItemType, WeightUnit
    from app.modules.inventory.models import InventoryItem
    from sqlalchemy import select

    items = [
        {
            "code": "RM-PEANUT-001",
            "name": "Raw Groundnuts (Peanut Seeds)",
            "item_type": InventoryItemType.RAW_MATERIAL,
            "unit": WeightUnit.VISS,
            "reorder_level": Decimal("100"),
            "reorder_quantity": Decimal("500"),
        },
        {
            "code": "FG-OIL-PEANUT-001",
            "name": "Refined Groundnut Oil (Bulk)",
            "item_type": InventoryItemType.FINISHED_OIL,
            "unit": WeightUnit.VISS,
            "reorder_level": Decimal("50"),
            "reorder_quantity": Decimal("200"),
        },
        {
            "code": "FG-OIL-PEANUT-1L",
            "name": "Groundnut Oil 1L Bottle",
            "item_type": InventoryItemType.FINISHED_OIL,
            "unit": WeightUnit.UNIT,
            "reorder_level": Decimal("50"),
            "reorder_quantity": Decimal("200"),
        },
        {
            "code": "PKG-BOTTLE-1L",
            "name": "1L PET Bottle",
            "item_type": InventoryItemType.PACKAGING,
            "unit": WeightUnit.UNIT,
            "reorder_level": Decimal("200"),
            "reorder_quantity": Decimal("1000"),
        },
        {
            "code": "RM-SESAME-001",
            "name": "Raw Sesame Seeds",
            "item_type": InventoryItemType.RAW_MATERIAL,
            "unit": WeightUnit.VISS,
            "reorder_level": Decimal("50"),
            "reorder_quantity": Decimal("200"),
        },
        {
            "code": "FG-OIL-SESAME-001",
            "name": "Refined Sesame Oil (Bulk)",
            "item_type": InventoryItemType.FINISHED_OIL,
            "unit": WeightUnit.VISS,
        },
    ]

    seeded = 0
    for i in items:
        existing = await session.execute(
            select(InventoryItem).where(InventoryItem.code == i["code"])
        )
        if not existing.scalar_one_or_none():
            session.add(InventoryItem(**i))
            seeded += 1
    await session.flush()
    print(f"  Inventory items: {seeded} seeded ({len(items)} total)")


if __name__ == "__main__":
    asyncio.run(main())
