"""Add idempotency key to customer returns.

Revision ID: 20260819_0010
Revises: 20260818_0009
Create Date: 2026-08-19
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0010"
down_revision = "20260818_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("return_records", sa.Column("idempotency_key", sa.String(length=100), nullable=True))
    op.create_unique_constraint("uq_return_idempotency", "return_records", ["tenant_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_return_idempotency", "return_records", type_="unique")
    op.drop_column("return_records", "idempotency_key")
