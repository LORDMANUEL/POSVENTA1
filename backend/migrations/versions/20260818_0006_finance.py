"""Add receivables payables and banking.

Revision ID: 20260818_0006
Revises: 20260818_0005
Create Date: 2026-08-18
"""

from alembic import op

from app.finance_models import (
    BankAccount,
    BankTransaction,
    Payable,
    PayablePayment,
    Receivable,
    ReceivablePayment,
)

revision = "20260818_0006"
down_revision = "20260818_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Receivable.__table__.create(bind=op.get_bind(), checkfirst=True)
    ReceivablePayment.__table__.create(bind=op.get_bind(), checkfirst=True)
    Payable.__table__.create(bind=op.get_bind(), checkfirst=True)
    PayablePayment.__table__.create(bind=op.get_bind(), checkfirst=True)
    BankAccount.__table__.create(bind=op.get_bind(), checkfirst=True)
    BankTransaction.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    BankTransaction.__table__.drop(bind=op.get_bind(), checkfirst=True)
    BankAccount.__table__.drop(bind=op.get_bind(), checkfirst=True)
    PayablePayment.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Payable.__table__.drop(bind=op.get_bind(), checkfirst=True)
    ReceivablePayment.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Receivable.__table__.drop(bind=op.get_bind(), checkfirst=True)
