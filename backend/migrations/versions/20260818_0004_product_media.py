"""Add product media gallery.

Revision ID: 20260818_0004
Revises: 20260818_0003
Create Date: 2026-08-18
"""

from alembic import op

from app.media_models import ProductMedia

revision = "20260818_0004"
down_revision = "20260818_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ProductMedia.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    ProductMedia.__table__.drop(bind=op.get_bind(), checkfirst=True)
