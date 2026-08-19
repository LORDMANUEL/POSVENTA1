"""Add idempotency key to customer returns safely.

Revision ID: 20260819_0010
Revises: 20260818_0009
Create Date: 2026-08-19

The historical baseline migration used ``Base.metadata.create_all()``. On a fresh
install that baseline therefore sees the current model and may already create
this column/constraint, while a real v0.12.0 database at revision 0009 does not
have them. This migration intentionally detects both states so clean installs
and upgrades from the previous stable line converge on the same schema.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0010"
down_revision = "20260818_0009"
branch_labels = None
depends_on = None

TABLE = "return_records"
COLUMN = "idempotency_key"
CONSTRAINT = "uq_return_idempotency"


def _column_names(bind) -> set[str]:
    return {item["name"] for item in sa.inspect(bind).get_columns(TABLE)}


def _unique_constraint_names(bind) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(bind).get_unique_constraints(TABLE)
        if item.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    if COLUMN not in _column_names(bind):
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=100), nullable=True))
    if CONSTRAINT not in _unique_constraint_names(bind):
        op.create_unique_constraint(CONSTRAINT, TABLE, ["tenant_id", COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    if CONSTRAINT in _unique_constraint_names(bind):
        op.drop_constraint(CONSTRAINT, TABLE, type_="unique")
    if COLUMN in _column_names(bind):
        op.drop_column(TABLE, COLUMN)
