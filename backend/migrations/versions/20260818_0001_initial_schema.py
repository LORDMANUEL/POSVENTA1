"""Initial Mily Zebra Commerce OS schema.

Revision ID: 20260818_0001
Revises:
Create Date: 2026-08-18
"""

from alembic import op

from app.db import Base
from app import admin_models, models, ops_models, post_sale_models  # noqa: F401

revision = "20260818_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline migration: create the complete schema represented by this revision.
    # Subsequent revisions must use explicit Alembic operations.
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Destructive by design; production restore policy requires backups before downgrade.
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
