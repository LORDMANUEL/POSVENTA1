"""Add auditable cash movement ledger.

Revision ID: 20260818_0003
Revises: 20260818_0002
Create Date: 2026-08-18
"""

from alembic import op

from app.cash_models import CashMovement

revision = "20260818_0003"
down_revision = "20260818_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    CashMovement.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    CashMovement.__table__.drop(bind=op.get_bind(), checkfirst=True)
