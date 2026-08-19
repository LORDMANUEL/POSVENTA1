"""Add module registry and accounting ledger.

Revision ID: 20260818_0005
Revises: 20260818_0004
Create Date: 2026-08-18
"""

from alembic import op

from app.accounting_models import Account, JournalEntry, JournalLine
from app.module_registry import TenantModule

revision = "20260818_0005"
down_revision = "20260818_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    TenantModule.__table__.create(bind=op.get_bind(), checkfirst=True)
    Account.__table__.create(bind=op.get_bind(), checkfirst=True)
    JournalEntry.__table__.create(bind=op.get_bind(), checkfirst=True)
    JournalLine.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    JournalLine.__table__.drop(bind=op.get_bind(), checkfirst=True)
    JournalEntry.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Account.__table__.drop(bind=op.get_bind(), checkfirst=True)
    TenantModule.__table__.drop(bind=op.get_bind(), checkfirst=True)
