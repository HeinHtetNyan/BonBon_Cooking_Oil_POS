"""
Finance module enumerations.

All enums use StrEnum so values are JSON-serialisable strings and compare
equal to their string literals without an explicit .value dereference.

`get_normal_balance` encodes the accounting identity that determines which
side of a T-account increases the balance — this drives balance calculation
logic in FinancialAccountRepository.
"""

from __future__ import annotations

from enum import StrEnum


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class AccountNormalBalance(StrEnum):
    DEBIT = "debit"    # Assets, Expenses increase with debits
    CREDIT = "credit"  # Liabilities, Equity, Revenue increase with credits


class TransactionType(StrEnum):
    SALE = "sale"
    PAYMENT_RECEIVED = "payment_received"
    EXPENSE_PAID = "expense_paid"
    DEBT_COLLECTION = "debt_collection"
    PRODUCTION_COST = "production_cost"
    ADJUSTMENT = "adjustment"
    REVERSAL = "reversal"
    OPENING_BALANCE = "opening_balance"


class PaymentMethodType(StrEnum):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    KBZPAY = "kbzpay"
    WAVEPAY = "wavepay"
    CREDIT = "credit"


class DebtStatus(StrEnum):
    OUTSTANDING = "outstanding"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    WRITTEN_OFF = "written_off"


def get_normal_balance(account_type: AccountType) -> AccountNormalBalance:
    """
    Return the normal balance side for the given account type.

    Accounting identity:
      - Assets and Expenses: normal balance is DEBIT (increases on debit side)
      - Liabilities, Equity, Revenue: normal balance is CREDIT (increases on credit side)

    This function is the single source of truth for normal-balance derivation.
    It is called when creating a FinancialAccount so the stored normal_balance
    column stays consistent with account_type without relying on application
    code to remember the rule.
    """
    if account_type in (AccountType.ASSET, AccountType.EXPENSE):
        return AccountNormalBalance.DEBIT
    return AccountNormalBalance.CREDIT
