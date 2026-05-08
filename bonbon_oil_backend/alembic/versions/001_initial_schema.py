"""Initial schema — all domain tables.

Revision ID: 001
Revises:
Create Date: 2026-05-08

Creates all application tables in dependency order so foreign-key constraints
are satisfied at creation time. Reverse is a complete DROP of all tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Shared helper columns (mirrors database.mixins)
# ---------------------------------------------------------------------------

_UUID = postgresql.UUID(as_uuid=True)
_NOW = sa.text("now()")
_UUID_GEN = sa.text("gen_random_uuid()")


def _pk() -> sa.Column:
    return sa.Column("id", _UUID, primary_key=True, server_default=_UUID_GEN)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    ]


def _full_audit() -> list[sa.Column]:
    return [
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("updated_by", sa.String(36), nullable=True),
    ]


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")

    # 1. users
    op.create_table(
        "users",
        _pk(),
        *_full_audit(),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("role", sa.String(32), nullable=False, server_default="cashier"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_status", "users", ["status"])
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # 2. customers
    op.create_table(
        "customers",
        _pk(),
        *_full_audit(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("customer_type", sa.String(16), nullable=False, server_default="retail"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("credit_limit", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("credit_balance", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_customers_code", "customers", ["code"], unique=True)
    op.create_index("ix_customers_name", "customers", ["name"])
    op.create_index("ix_customers_phone", "customers", ["phone"])
    op.create_index("ix_customers_customer_type", "customers", ["customer_type"])
    op.create_index("ix_customers_status", "customers", ["status"])
    op.create_index("ix_customers_deleted_at", "customers", ["deleted_at"])
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])

    # 3. financial_accounts
    op.create_table(
        "financial_accounts",
        _pk(),
        *_full_audit(),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("account_type", sa.String(16), nullable=False),
        sa.Column("normal_balance", sa.String(8), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("parent_code", sa.String(16), nullable=True),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_financial_accounts_code", "financial_accounts", ["code"], unique=True)
    op.create_index("ix_financial_accounts_account_type", "financial_accounts", ["account_type"])
    op.create_index("ix_financial_accounts_deleted_at", "financial_accounts", ["deleted_at"])
    op.create_index("ix_financial_accounts_tenant_id", "financial_accounts", ["tenant_id"])

    # 4. payment_methods
    op.create_table(
        "payment_methods",
        _pk(),
        *_full_audit(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("method_type", sa.String(32), nullable=False),
        sa.Column("linked_account_code", sa.String(16), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_payment_methods_code", "payment_methods", ["code"], unique=True)
    op.create_index("ix_payment_methods_deleted_at", "payment_methods", ["deleted_at"])
    op.create_index("ix_payment_methods_tenant_id", "payment_methods", ["tenant_id"])

    # 5. inventory_items
    op.create_table(
        "inventory_items",
        _pk(),
        *_full_audit(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("current_balance", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("reorder_level", sa.Numeric(18, 6), nullable=True),
        sa.Column("reorder_quantity", sa.Numeric(18, 6), nullable=True),
    )
    # 6. journal_entries (self-referencing FK reversal_of_id)
    op.create_index("ix_inventory_items_code", "inventory_items", ["code"], unique=True)
    op.create_index("ix_inventory_items_item_type", "inventory_items", ["item_type"])
    op.create_index("ix_inventory_items_deleted_at", "inventory_items", ["deleted_at"])
    op.create_index("ix_inventory_items_tenant_id", "inventory_items", ["tenant_id"])

    op.create_table(
        "journal_entries",
        _pk(),
        *_timestamps(),
        sa.Column(
            "debit_account_id",
            _UUID,
            sa.ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "credit_account_id",
            _UUID,
            sa.ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("transaction_type", sa.String(32), nullable=False),
        sa.Column("reference_type", sa.String(64), nullable=True),
        sa.Column("reference_id", sa.String(36), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("transaction_date", sa.String(10), nullable=False),
        sa.Column("is_reversed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "reversal_of_id",
            _UUID,
            sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
    )
    op.create_index("ix_journal_entries_transaction_type", "journal_entries", ["transaction_type"])
    op.create_index("ix_journal_entries_reference_type", "journal_entries", ["reference_type"])
    op.create_index("ix_journal_entries_reference_id", "journal_entries", ["reference_id"])
    op.create_index("ix_journal_entries_tenant_id", "journal_entries", ["tenant_id"])
    op.create_index(
        "ix_journal_entries_debit_date",
        "journal_entries",
        ["debit_account_id", "transaction_date"],
    )
    op.create_index(
        "ix_journal_entries_credit_date",
        "journal_entries",
        ["credit_account_id", "transaction_date"],
    )
    op.create_index(
        "ix_journal_entries_reference",
        "journal_entries",
        ["reference_type", "reference_id"],
    )

    # 7. inventory_movements
    op.create_table(
        "inventory_movements",
        _pk(),
        *_timestamps(),
        sa.Column(
            "item_id",
            _UUID,
            sa.ForeignKey("inventory_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("movement_type", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("quantity_in_canonical_unit", sa.Numeric(18, 6), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("reference_type", sa.String(64), nullable=True),
        sa.Column("reference_id", sa.String(36), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="confirmed"),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
    )
    op.create_index("ix_inventory_movements_item_id", "inventory_movements", ["item_id"])
    op.create_index("ix_inventory_movements_movement_type", "inventory_movements", ["movement_type"])
    op.create_index(
        "ix_inventory_movements_item_created",
        "inventory_movements",
        ["item_id", "created_at"],
    )
    op.create_index(
        "ix_inventory_movements_reference",
        "inventory_movements",
        ["reference_type", "reference_id"],
    )

    # 8. inventory_snapshots
    op.create_table(
        "inventory_snapshots",
        _pk(),
        *_timestamps(),
        sa.Column(
            "item_id",
            _UUID,
            sa.ForeignKey("inventory_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.String(10), nullable=False),
        sa.Column("balance", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.UniqueConstraint("item_id", "snapshot_date", name="uq_inventory_snapshot_item_date"),
    )
    op.create_index("ix_inventory_snapshots_item_id", "inventory_snapshots", ["item_id"])
    op.create_index("ix_inventory_snapshots_snapshot_date", "inventory_snapshots", ["snapshot_date"])

    # 9. vouchers
    op.create_table(
        "vouchers",
        _pk(),
        *_full_audit(),
        sa.Column("voucher_number", sa.String(32), nullable=False),
        sa.Column("voucher_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column(
            "customer_id",
            _UUID,
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("subtotal", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("sale_date", sa.String(10), nullable=False),
    )
    op.create_index("ix_vouchers_voucher_number", "vouchers", ["voucher_number"], unique=True)
    op.create_index("ix_vouchers_voucher_type", "vouchers", ["voucher_type"])
    op.create_index("ix_vouchers_status", "vouchers", ["status"])
    op.create_index("ix_vouchers_customer_id", "vouchers", ["customer_id"])
    op.create_index("ix_vouchers_deleted_at", "vouchers", ["deleted_at"])
    op.create_index("ix_vouchers_tenant_id", "vouchers", ["tenant_id"])

    # 10. voucher_items
    op.create_table(
        "voucher_items",
        _pk(),
        *_timestamps(),
        sa.Column(
            "voucher_id",
            _UUID,
            sa.ForeignKey("vouchers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "inventory_item_id",
            _UUID,
            sa.ForeignKey("inventory_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_voucher_items_voucher_id", "voucher_items", ["voucher_id"])

    # 11. voucher_payments
    op.create_table(
        "voucher_payments",
        _pk(),
        *_timestamps(),
        sa.Column(
            "voucher_id",
            _UUID,
            sa.ForeignKey("vouchers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payment_method_id",
            _UUID,
            sa.ForeignKey("payment_methods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("reference_number", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("actor", sa.String(36), nullable=False),
    )
    op.create_index("ix_voucher_payments_voucher_id", "voucher_payments", ["voucher_id"])

    # 12. customer_debts
    op.create_table(
        "customer_debts",
        _pk(),
        *_full_audit(),
        sa.Column(
            "customer_id",
            _UUID,
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "voucher_id",
            _UUID,
            sa.ForeignKey("vouchers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("original_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("paid_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="outstanding"),
        sa.Column("due_date", sa.String(10), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_customer_debts_customer_id", "customer_debts", ["customer_id"])
    op.create_index("ix_customer_debts_voucher_id", "customer_debts", ["voucher_id"])
    op.create_index("ix_customer_debts_status", "customer_debts", ["status"])
    op.create_index("ix_customer_debts_deleted_at", "customer_debts", ["deleted_at"])
    op.create_index("ix_customer_debts_tenant_id", "customer_debts", ["tenant_id"])
    op.create_index(
        "ix_customer_debts_customer_status",
        "customer_debts",
        ["customer_id", "status"],
    )

    # 13. debt_payments
    op.create_table(
        "debt_payments",
        _pk(),
        *_timestamps(),
        sa.Column(
            "debt_id",
            _UUID,
            sa.ForeignKey("customer_debts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "payment_method_id",
            _UUID,
            sa.ForeignKey("payment_methods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("reference_number", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column(
            "journal_entry_id",
            _UUID,
            sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
    )
    op.create_index("ix_debt_payments_debt_id", "debt_payments", ["debt_id"])

    # 14. production_batches
    op.create_table(
        "production_batches",
        _pk(),
        *_full_audit(),
        sa.Column("batch_number", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
        sa.Column(
            "output_item_id",
            _UUID,
            sa.ForeignKey("inventory_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("expected_output", sa.Numeric(18, 6), nullable=False),
        sa.Column("actual_output", sa.Numeric(18, 6), nullable=True),
        sa.Column("output_unit", sa.String(16), nullable=False),
        sa.Column("total_material_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_labour_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_overhead_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("start_date", sa.String(10), nullable=True),
        sa.Column("end_date", sa.String(10), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text, nullable=True),
    )
    op.create_index("ix_production_batches_batch_number", "production_batches", ["batch_number"], unique=True)
    op.create_index("ix_production_batches_status", "production_batches", ["status"])
    op.create_index("ix_production_batches_deleted_at", "production_batches", ["deleted_at"])
    op.create_index("ix_production_batches_tenant_id", "production_batches", ["tenant_id"])

    # 15. production_material_usages
    op.create_table(
        "production_material_usages",
        _pk(),
        *_timestamps(),
        sa.Column(
            "batch_id",
            _UUID,
            sa.ForeignKey("production_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_item_id",
            _UUID,
            sa.ForeignKey("inventory_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("planned_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("actual_quantity", sa.Numeric(18, 6), nullable=True),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=True),
    )
    op.create_index("ix_production_material_usages_batch_id", "production_material_usages", ["batch_id"])

    # 16. production_outputs
    op.create_table(
        "production_outputs",
        _pk(),
        *_timestamps(),
        sa.Column(
            "batch_id",
            _UUID,
            sa.ForeignKey("production_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "output_item_id",
            _UUID,
            sa.ForeignKey("inventory_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column(
            "inventory_movement_id",
            _UUID,
            sa.ForeignKey("inventory_movements.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
    )
    op.create_index("ix_production_outputs_batch_id", "production_outputs", ["batch_id"])

    # 17. expenses
    op.create_table(
        "expenses",
        _pk(),
        *_full_audit(),
        sa.Column("reference_number", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("expense_date", sa.String(10), nullable=False),
        sa.Column(
            "production_batch_id",
            _UUID,
            sa.ForeignKey("production_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "linked_journal_entry_id",
            _UUID,
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("receipt_url", sa.String(512), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("approved_by", sa.String(36), nullable=True),
    )
    op.create_index("ix_expenses_reference_number", "expenses", ["reference_number"], unique=True)
    op.create_index("ix_expenses_category", "expenses", ["category"])
    op.create_index("ix_expenses_status", "expenses", ["status"])
    op.create_index("ix_expenses_production_batch_id", "expenses", ["production_batch_id"])
    op.create_index("ix_expenses_deleted_at", "expenses", ["deleted_at"])
    op.create_index("ix_expenses_tenant_id", "expenses", ["tenant_id"])

    # 18. expense_payments
    op.create_table(
        "expense_payments",
        _pk(),
        *_timestamps(),
        sa.Column(
            "expense_id",
            _UUID,
            sa.ForeignKey("expenses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payment_method_id",
            _UUID,
            sa.ForeignKey("payment_methods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("reference_number", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "journal_entry_id",
            _UUID,
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
    )
    op.create_index("ix_expense_payments_expense_id", "expense_payments", ["expense_id"])

    # 19. audit_logs
    op.create_table(
        "audit_logs",
        _pk(),
        *_timestamps(),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("actor_username", sa.String(64), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column("before_data", postgresql.JSONB(), nullable=True),
        sa.Column("after_data", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("duration_ms", sa.Float, nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_actor_created", "audit_logs", ["actor_id", "created_at"])
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])
    op.create_index("ix_audit_logs_tenant_created", "audit_logs", ["tenant_id", "created_at"])


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("audit_logs")
    op.drop_table("expense_payments")
    op.drop_table("expenses")
    op.drop_table("production_outputs")
    op.drop_table("production_material_usages")
    op.drop_table("production_batches")
    op.drop_table("debt_payments")
    op.drop_table("customer_debts")
    op.drop_table("voucher_payments")
    op.drop_table("voucher_items")
    op.drop_table("vouchers")
    op.drop_table("inventory_snapshots")
    op.drop_table("inventory_movements")
    op.drop_table("journal_entries")
    op.drop_table("inventory_items")
    op.drop_table("payment_methods")
    op.drop_table("financial_accounts")
    op.drop_table("customers")
    op.drop_table("users")

    op.execute("DROP EXTENSION IF EXISTS btree_gin")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
