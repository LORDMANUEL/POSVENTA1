"""Add stock count and replenishment rules.

Revision ID: 20260818_0008
Revises: 20260818_0007
Create Date: 2026-08-18
"""

from alembic import op

from app.inventory_advanced_models import ReplenishmentRule, StockCount, StockCountLine

revision = "20260818_0008"
down_revision = "20260818_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    StockCount.__table__.create(bind=op.get_bind(), checkfirst=True)
    StockCountLine.__table__.create(bind=op.get_bind(), checkfirst=True)
    ReplenishmentRule.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    ReplenishmentRule.__table__.drop(bind=op.get_bind(), checkfirst=True)
    StockCountLine.__table__.drop(bind=op.get_bind(), checkfirst=True)
    StockCount.__table__.drop(bind=op.get_bind(), checkfirst=True)
