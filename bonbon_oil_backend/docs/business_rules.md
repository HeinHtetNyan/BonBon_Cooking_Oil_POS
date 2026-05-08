# Bon Bon Oil ERP — Business Rules

This document is the authoritative reference for domain rules enforced by the
application layer. Rules here are **not** enforced solely by the database
schema — they live in service classes and must be preserved across refactors.

---

## Table of Contents

1. [Voucher Lifecycle](#1-voucher-lifecycle)
2. [Voucher Reversal (Void)](#2-voucher-reversal-void)
3. [Inventory Rules](#3-inventory-rules)
4. [Customer Debt Rules](#4-customer-debt-rules)
5. [Financial Posting Logic](#5-financial-posting-logic)
6. [Reconciliation Logic](#6-reconciliation-logic)
7. [Production Workflow](#7-production-workflow)
8. [Audit and Change Events](#8-audit-and-change-events)
9. [Concurrency and Locking](#9-concurrency-and-locking)
10. [Idempotency](#10-idempotency)

---

## 1. Voucher Lifecycle

A voucher represents a sales transaction. It moves through a strict linear
state machine; backward transitions are not permitted except through an
explicit void.

### 1.1 Status State Machine

```
DRAFT ──confirm──► CONFIRMED | PARTIALLY_PAID | PAID
                         │
                    void │
                         ▼
                     CANCELLED
```

| Status | Description |
|---|---|
| `draft` | Being composed; all fields editable |
| `confirmed` | Confirmed with zero payment (credit sale) |
| `partially_paid` | Some payment received, outstanding balance remains |
| `paid` | Fully paid; no outstanding balance |
| `cancelled` | Voided; no further transitions allowed |

### 1.2 Confirm Rules

`VoucherService.confirm_voucher()` applies the following checks **in order**
after acquiring a `SELECT … FOR UPDATE` row lock on the voucher:

1. **Status check** — voucher must be `DRAFT`. Any other status raises
   `VoucherLockedError`.
2. **Optimistic lock check** — if `expected_version` is supplied, it must
   match `voucher.version_number`. Mismatch raises `OptimisticLockError`.
3. **Inventory deduction** — one `SALE_OUT` movement is created per
   `VoucherItem` line; `InventoryItem.current_balance` decreases.
   `InsufficientInventoryError` is raised if balance would go negative.
4. **Ledger posting** — journal entries are written (see §5).
5. **Customer debt creation** — if `outstanding_amount > 0` and a
   `customer_id` is set, a `CustomerDebt` record is created with status
   `OUTSTANDING`.
6. **Payment status derivation**:
   - `outstanding_amount == 0` → `PAID`
   - `0 < outstanding_amount < total_amount` → `PARTIALLY_PAID`
   - `outstanding_amount == total_amount` → `CONFIRMED`
7. **Version bump** — `version_number` and `sync_version` are incremented.

### 1.3 Editable Fields

Fields can only be mutated while `status == DRAFT`. Once confirmed, the
voucher header and all line items are immutable. Attempting to edit a
non-`DRAFT` voucher raises `VoucherLockedError`.

### 1.4 Voucher Types

| Type | Description |
|---|---|
| `sale` | Standard outbound sale |
| `return` | Customer return (inbound movement) |

---

## 2. Voucher Reversal (Void)

`VoucherService.void_voucher()` reverses all effects of a confirmed voucher.

### 2.1 Void Rules

1. A voucher already in `CANCELLED` status raises `VoucherAlreadyCancelledError`.
2. If `expected_version` is supplied, mismatch raises `OptimisticLockError`.
3. For `DRAFT` vouchers: status is set to `CANCELLED` with no side effects
   (no inventory or ledger to reverse).
4. For confirmed vouchers (`CONFIRMED | PARTIALLY_PAID | PAID`):
   - Every `InventoryMovement` created by the original confirm is reversed via
     a new `VOID_REVERSAL` movement, restoring `current_balance`.
   - Every `JournalEntry` linked to the voucher `reference_id` is reversed via
     a new entry with swapped debit/credit accounts. The original entries are
     marked `is_reversed = True`.
   - If a `CustomerDebt` exists for this voucher, it is cancelled
     (`WRITTEN_OFF`) provided it is not already fully `PAID` (a paid debt
     cannot be cancelled — the cash has already been collected).
5. `version_number` and `sync_version` are incremented on the voided voucher.

### 2.2 Append-Only Ledger

Neither `JournalEntry` nor `InventoryMovement` rows are ever deleted or
updated after creation. Reversals always produce **new rows**. This preserves
the full audit trail.

---

## 3. Inventory Rules

### 3.1 Balance Invariant

`InventoryItem.current_balance` is a denormalised running total. Its value
must always equal:

```
SUM(quantity) for all inbound movements
  − SUM(quantity) for all outbound movements
```

Reconciliation tasks verify this nightly (see §6).

### 3.2 Negative Balance Prevention

All outbound movements check the current balance **after acquiring a row lock**
(`SELECT … FOR UPDATE`). If `quantity > current_balance` the operation raises
`InsufficientInventoryError` and the transaction is rolled back.

> **Why the lock matters**: without it, two concurrent sessions can both pass
> the balance check independently and together overdraw the item (TOCTOU race).
> The lock serialises the read-check-write sequence.

### 3.3 Movement Types

**Inbound** (increase balance): `purchase_in`, `production_output`,
`adjustment_in`, `return_in`, `transfer_in`, `opening_balance`.

**Outbound** (decrease balance): `sale_out`, `production_consumption`,
`adjustment_out`, `wastage`, `transfer_out`, `sample_out`.

`void_reversal` and `correction` are special types that can be either
direction depending on context.

### 3.4 Unit Conversion

All balances are stored in the item's canonical unit (set at item creation).
Movements in a different unit are converted by `UnitConversionService` before
the balance is updated. The `movement.quantity` is stored in the **original**
unit; `balance_after` reflects the canonical unit.

Supported conversions:

| From | To | Factor |
|---|---|---|
| `viss` | `tical` | × 100 |
| `tical` | `viss` | ÷ 100 |
| `liter` | `kg` | × 0.92 |
| `kg` | `liter` | ÷ 0.92 |
| any | same | × 1 |

Unsupported pairs (e.g., `unit` → `kg`) raise `ValueError`.

### 3.5 Inventory Snapshots

A nightly Celery task (`create_daily_inventory_snapshot`) computes and stores
`InventorySnapshot` rows at 00:05. Monthly snapshots run on the first of each
month. Snapshots are used as reconciliation baselines.

---

## 4. Customer Debt Rules

`CustomerDebt` tracks credit extended to wholesale customers.

### 4.1 Debt Lifecycle

```
OUTSTANDING ──partial payment──► PARTIALLY_PAID
     │                                 │
     └──full payment───────────────────┘
                                       │
                                  ▼ PAID
              (cancel)
OUTSTANDING / PARTIALLY_PAID ──────► WRITTEN_OFF
```

### 4.2 Create Debt

A debt is created by `DebtService.create_debt()` when
`confirm_voucher` detects `outstanding_amount > 0` with a `customer_id` set.

- `original_amount` = voucher `outstanding_amount` at confirm time.
- `paid_amount` = 0.
- `status` = `OUTSTANDING`.
- `Customer.credit_balance` is increased by `original_amount`.

### 4.3 Record Payment

`DebtService.record_payment()` applies the following rules after acquiring a
`SELECT … FOR UPDATE` lock on the debt row:

1. Debt must not be `PAID` (raises `BusinessRuleError: already fully paid`).
2. Debt must not be `WRITTEN_OFF` (raises `BusinessRuleError: written-off`).
3. Payment `amount` must be positive (raises `BusinessRuleError: must be positive`).
4. `amount` must not exceed `outstanding_amount`
   (raises `BusinessRuleError: exceeds outstanding`).
5. `paid_amount += amount`; `outstanding_amount -= amount`.
6. Status transitions:
   - `outstanding_amount == 0` → `PAID`
   - `outstanding_amount > 0` → `PARTIALLY_PAID`
7. A `DebtPayment` row is created.
8. A journal entry is written: debit cash account, credit accounts-receivable.
9. `Customer.credit_balance` is decreased by `amount`.

### 4.4 Cancel Debt

`DebtService.cancel_debt()` (write-off) rules:

- A `PAID` debt cannot be cancelled (cash already received).
- An already `WRITTEN_OFF` debt raises `BusinessRuleError: already written off`.
- On cancel: status → `WRITTEN_OFF`; ledger entry is reversed;
  `Customer.credit_balance` is reduced by remaining `outstanding_amount`.

---

## 5. Financial Posting Logic

The system uses **double-entry bookkeeping**: every transaction produces a
single `JournalEntry` row with a debit account, a credit account, and a
positive amount.

### 5.1 Chart of Accounts (System Accounts)

| Code | Name | Type | Normal Balance |
|---|---|---|---|
| 1000 | Cash | Asset | Debit |
| 1100 | Accounts Receivable | Asset | Debit |
| 4000 | Sales Revenue | Revenue | Credit |

System accounts (`is_system=True`) are resolved by code; they must exist or
`record_transaction` raises `NotFoundError`.

### 5.2 Posting Rules by Transaction Type

| Event | Debit | Credit |
|---|---|---|
| Cash sale (`record_sale_payment`) | Payment method account (e.g. 1000) | 4000 Sales Revenue |
| Credit sale (`record_credit_sale`) | 1100 Accounts Receivable | 4000 Sales Revenue |
| Debt collection (`record_debt_collection`) | 1000 Cash | 1100 Accounts Receivable |
| Void / reversal | Swap debit ↔ credit of original entry | — |

### 5.3 Amount Validation

`LedgerService.record_transaction()` raises `BusinessRuleError: must be positive`
for zero or negative amounts. All `JournalEntry.amount` values are strictly
positive; sign is encoded by which account is debited/credited.

### 5.4 Reversal

`LedgerService.reverse_transaction()` creates a new entry with debit and
credit accounts swapped and marks the original `is_reversed = True`. Attempting
to reverse an already-reversed entry raises `BusinessRuleError: already reversed`.

`reverse_all_for_reference(ref_type, ref_id)` reverses all non-reversed entries
linked to a reference (used during voucher void). Already-reversed entries are
silently skipped.

### 5.5 Financial Snapshots

`FinancialSnapshot` rows capture per-account balances daily (Celery task at
01:00) and monthly (task runs on last day of month at 00:30). If a snapshot
already exists for a given `(account_id, snapshot_date, snapshot_type)`, the
`UniqueConstraint` violation is caught and the existing snapshot is preserved.

---

## 6. Reconciliation Logic

Reconciliation tasks are **read-only**: they detect discrepancies and log
warnings but never automatically repair production data. Repairs require
an explicit admin action passing `repair=True`.

### 6.1 Inventory Reconciliation

`InventoryReconciliationService.reconcile_all()` (Celery: daily at 02:00):

1. Fetches all active `InventoryItem` rows.
2. For each item, recomputes the expected balance by summing `InventoryMovement`
   quantities (inbound positive, outbound negative).
3. If `expected_balance != item.current_balance`, a `ReconciliationDiscrepancy`
   is emitted with severity `WARNING`.
4. If `repair=True` (admin only), `current_balance` is set to the computed
   value and the correction is logged.

### 6.2 Financial Reconciliation

`FinancialReconciliationService.detect_ledger_imbalances()` (Celery: daily
at 02:15) checks that total debits equal total credits across all journal
entries. An imbalance is an `IntegrityCheckError`.

`FinancialIntegrityService.run_full_check()` (Celery: daily at 02:30) verifies:

- No `JournalEntry` has a zero or negative `amount`.
- No entry debits and credits the same account (self-loop).
- Asset account balances are non-negative (overdraft detection).
- `CustomerDebt.outstanding_amount` equals `original_amount − paid_amount`
  for every debt.

### 6.3 Snapshot-based Drift Detection

Monthly financial snapshots serve as a baseline. If an account's recomputed
balance differs from its snapshot, a drift is logged. Large drifts (>5% or
configurable threshold) trigger a `WARNING` severity discrepancy.

---

## 7. Production Workflow

`ProductionBatch` tracks oil pressing runs from raw material to finished product.

### 7.1 Batch Lifecycle

```
PLANNED ──start──► IN_PROGRESS ──complete──► COMPLETED
    │                   │
    └──cancel───────────┘
                        ▼
                   CANCELLED
```

### 7.2 Batch Completion Rules

When `complete_batch()` is called:

1. Batch must be `IN_PROGRESS`; other statuses raise `BusinessRuleError`.
2. Raw materials listed in `BatchInput` lines are consumed via
   `PRODUCTION_CONSUMPTION` movements (reduce raw material balance).
3. Finished oil output is added via `PRODUCTION_OUTPUT` movements
   (increase finished oil balance).
4. A `PRODUCTION_COST` ledger entry is written for the batch cost.
5. `version_number` and `sync_version` are incremented.

### 7.3 Input/Output Validation

- `actual_output` must be positive.
- `actual_output` must not exceed `expected_output` by more than 10% (waste
  detection; configurable). Exceeding raises `BusinessRuleError`.
- Sufficient raw material balance is required before consumption movements are
  recorded (`InsufficientInventoryError` if not).

---

## 8. Audit and Change Events

### 8.1 Audit Logs

Every write operation on key entities is recorded in the `audit_logs` table
via `AuditService`. Entries include: `entity_type`, `entity_id`, `action`
(`create | update | delete`), `actor`, `old_values` (JSONB), `new_values`
(JSONB), `ip_address`, `tenant_id`.

Audit logs are **immutable** — no service may update or delete them.

### 8.2 Change Events

`ChangeEvent` rows are written by `ChangeEventService.record()` for entities
that participate in the offline-sync protocol. Each event has a monotonically
increasing `sequence_number` sourced from a PostgreSQL sequence
(`change_events_sequence_number_seq`), guaranteeing total order within a
tenant.

Clients poll `GET /api/v1/sync/events?since=<sequence>` to receive changes
they missed while offline.

### 8.3 Retention

Expired idempotency keys are deleted daily at 03:00 (default TTL: 24 hours).
Change events older than 90 days are pruned weekly (Sunday at 03:30).

---

## 9. Concurrency and Locking

### 9.1 Row-Level Locking

The following operations acquire `SELECT … FOR UPDATE` before any read-check-write:

| Operation | Locked Row |
|---|---|
| `VoucherService.confirm_voucher` | `vouchers` row |
| `VoucherService.void_voucher` | `vouchers` row |
| `InventoryService.record_movement` | `inventory_items` row |
| `InventoryService.reverse_movement` | `inventory_items` row |
| `DebtService.record_payment` | `customer_debts` row |

Locks are released when the enclosing transaction commits or rolls back. The
application never holds locks across HTTP request boundaries.

### 9.2 Optimistic Concurrency Control

`Voucher`, `Customer`, `InventoryItem`, `ProductionBatch`, and `Expense` carry
a `version_number` column (default: 1). It increments on every state-changing
operation.

API clients may pass `expected_version` to `confirm_voucher` and `void_voucher`.
If the stored `version_number` does not match, `OptimisticLockError` (HTTP 409)
is raised before any side effects occur.

### 9.3 Deadlock Handling

If PostgreSQL raises a deadlock error (SQLSTATE 40P01), the application wraps
it in `DeadlockError`. Callers should retry the operation once after a short
delay. Celery tasks use `autoretry_for=(DeadlockError,)` with exponential
backoff.

---

## 10. Idempotency

### 10.1 Idempotent Endpoints

The following endpoints are protected by `IdempotencyMiddleware`:

| Method | Path |
|---|---|
| POST | `/api/v1/vouchers/{id}/confirm` |
| POST | `/api/v1/vouchers/{id}/void` |
| POST | `/api/v1/expenses/` |
| POST | `/api/v1/finance/debts/{id}/payments` |
| POST | `/api/v1/production/batches/{id}/complete` |

### 10.2 Protocol

1. Client sends `Idempotency-Key: <uuid>` header.
2. Middleware hashes the request body (SHA-256).
3. If a record exists for that key with the **same** hash, the stored response
   is returned immediately (no re-execution).
4. If a record exists with a **different** hash (different body), HTTP 409
   is returned (`IdempotencyConflictError`).
5. After a successful (2xx) response, the key + hash + response are persisted.
6. Keys expire after 24 hours.

### 10.3 Safe Retries

A network timeout after the server commits but before the client receives the
response is the classic scenario where idempotency keys help. The client
re-sends with the same key and body and receives the original committed response
without duplicating inventory movements, ledger entries, or debt records.
