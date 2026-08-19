"""Harden v0.12.1 transactional integrity safely.

Revision ID: 20260819_0010
Revises: 20260818_0009
Create Date: 2026-08-19

The historical baseline migration used ``Base.metadata.create_all()``. A fresh
install therefore sees the current model and may already contain columns and
indexes introduced by this unreleased candidate, while a real v0.12.0 database
at revision 0009 does not. This migration deliberately introspects every change
so clean installs and upgrades converge on the same schema.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0010"
down_revision = "20260818_0009"
branch_labels = None
depends_on = None


VERSIONED_TABLES = (
    "cash_sessions",
    "print_jobs",
    "purchase_orders",
    "stock_transfers",
    "deliveries",
    "orders",
    "payments",
    "receivables",
    "payables",
    "bank_transactions",
)


def _column_names(bind, table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(bind).get_columns(table)}


def _unique_constraint_names(bind, table: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(bind).get_unique_constraints(table)
        if item.get("name")
    }


def _index_names(bind, table: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(bind).get_indexes(table)
        if item.get("name")
    }


def _add_nullable_string(bind, table: str, column: str, length: int) -> None:
    if column not in _column_names(bind, table):
        op.add_column(table, sa.Column(column, sa.String(length=length), nullable=True))


def _add_version(bind, table: str) -> None:
    if "version" in _column_names(bind, table):
        return
    op.add_column(
        table,
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.alter_column(table, "version", server_default=None)


def _assert_no_duplicate_open_cash(bind) -> None:
    duplicate = bind.execute(
        sa.text(
            """
            SELECT tenant_id, user_id, COUNT(*)
            FROM cash_sessions
            WHERE closed_at IS NULL
            GROUP BY tenant_id, user_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "No se puede crear uq_cash_open_user: existen múltiples cajas abiertas "
            f"para tenant={duplicate[0]} user={duplicate[1]}"
        )


def _assert_no_duplicate_bank_matches(bind) -> None:
    duplicate = bind.execute(
        sa.text(
            """
            SELECT tenant_id, matched_type, matched_id, COUNT(*)
            FROM bank_transactions
            WHERE reconciliation_status = 'matched' AND matched_id IS NOT NULL
            GROUP BY tenant_id, matched_type, matched_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "No se puede crear uq_bank_match_target: una operación interna ya está "
            f"conciliada más de una vez ({duplicate[0]}, {duplicate[1]}, {duplicate[2]})"
        )


def upgrade() -> None:
    bind = op.get_bind()

    # Payload fingerprints make idempotency semantic: the same key may replay
    # the same request, but may never silently represent different contents.
    _add_nullable_string(bind, "sales", "request_hash", 64)
    _add_nullable_string(bind, "orders", "request_hash", 64)
    _add_nullable_string(bind, "return_records", "idempotency_key", 100)
    _add_nullable_string(bind, "return_records", "request_hash", 64)

    if "uq_return_idempotency" not in _unique_constraint_names(bind, "return_records"):
        op.create_unique_constraint(
            "uq_return_idempotency",
            "return_records",
            ["tenant_id", "idempotency_key"],
        )

    for table in VERSIONED_TABLES:
        _add_version(bind, table)

    # Durable retry safety for CxC/CxP payments.
    for table, constraint in (
        ("receivable_payments", "uq_receivable_payment_idempotency"),
        ("payable_payments", "uq_payable_payment_idempotency"),
    ):
        _add_nullable_string(bind, table, "idempotency_key", 100)
        _add_nullable_string(bind, table, "request_hash", 64)
        if constraint not in _unique_constraint_names(bind, table):
            op.create_unique_constraint(
                constraint,
                table,
                ["tenant_id", "idempotency_key"],
            )

    if "uq_cash_open_user" not in _index_names(bind, "cash_sessions"):
        _assert_no_duplicate_open_cash(bind)
        op.create_index(
            "uq_cash_open_user",
            "cash_sessions",
            ["tenant_id", "user_id"],
            unique=True,
            postgresql_where=sa.text("closed_at IS NULL"),
        )

    if "uq_bank_match_target" not in _index_names(bind, "bank_transactions"):
        _assert_no_duplicate_bank_matches(bind)
        op.create_index(
            "uq_bank_match_target",
            "bank_transactions",
            ["tenant_id", "matched_type", "matched_id"],
            unique=True,
            postgresql_where=sa.text(
                "reconciliation_status = 'matched' AND matched_id IS NOT NULL"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()

    if "uq_bank_match_target" in _index_names(bind, "bank_transactions"):
        op.drop_index("uq_bank_match_target", table_name="bank_transactions")
    if "uq_cash_open_user" in _index_names(bind, "cash_sessions"):
        op.drop_index("uq_cash_open_user", table_name="cash_sessions")

    for table, constraint in (
        ("payable_payments", "uq_payable_payment_idempotency"),
        ("receivable_payments", "uq_receivable_payment_idempotency"),
    ):
        if constraint in _unique_constraint_names(bind, table):
            op.drop_constraint(constraint, table, type_="unique")
        for column in ("request_hash", "idempotency_key"):
            if column in _column_names(bind, table):
                op.drop_column(table, column)

    for table in reversed(VERSIONED_TABLES):
        if "version" in _column_names(bind, table):
            op.drop_column(table, "version")

    if "uq_return_idempotency" in _unique_constraint_names(bind, "return_records"):
        op.drop_constraint("uq_return_idempotency", "return_records", type_="unique")
    for table, column in (
        ("return_records", "request_hash"),
        ("return_records", "idempotency_key"),
        ("orders", "request_hash"),
        ("sales", "request_hash"),
    ):
        if column in _column_names(bind, table):
            op.drop_column(table, column)
