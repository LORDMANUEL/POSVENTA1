"""Add ecommerce orders, payments, and stock reservations.

Revision ID: 20260818_0002
Revises: 20260818_0001
Create Date: 2026-08-18
"""

from alembic import op

from app.commerce_models import Order, OrderLine, Payment, StockReservation

revision = "20260818_0002"
down_revision = "20260818_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Order.__table__.create(bind=bind, checkfirst=True)
    OrderLine.__table__.create(bind=bind, checkfirst=True)
    Payment.__table__.create(bind=bind, checkfirst=True)
    StockReservation.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    StockReservation.__table__.drop(bind=bind, checkfirst=True)
    Payment.__table__.drop(bind=bind, checkfirst=True)
    OrderLine.__table__.drop(bind=bind, checkfirst=True)
    Order.__table__.drop(bind=bind, checkfirst=True)
