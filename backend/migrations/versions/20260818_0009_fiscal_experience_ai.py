"""Add fiscal, store experience and knowledge modules.

Revision ID: 20260818_0009
Revises: 20260818_0008
Create Date: 2026-08-18
"""

from alembic import op

from app.experience_models import Announcement, AudioZone, KioskHeartbeat, Playlist, VisualSession
from app.fiscal_models import FiscalDocument, FiscalRange
from app.knowledge_models import KnowledgeChunk, KnowledgeDocument

revision = "20260818_0009"
down_revision = "20260818_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    FiscalRange.__table__.create(bind=op.get_bind(), checkfirst=True)
    FiscalDocument.__table__.create(bind=op.get_bind(), checkfirst=True)
    AudioZone.__table__.create(bind=op.get_bind(), checkfirst=True)
    Playlist.__table__.create(bind=op.get_bind(), checkfirst=True)
    Announcement.__table__.create(bind=op.get_bind(), checkfirst=True)
    VisualSession.__table__.create(bind=op.get_bind(), checkfirst=True)
    KioskHeartbeat.__table__.create(bind=op.get_bind(), checkfirst=True)
    KnowledgeDocument.__table__.create(bind=op.get_bind(), checkfirst=True)
    KnowledgeChunk.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    KnowledgeChunk.__table__.drop(bind=op.get_bind(), checkfirst=True)
    KnowledgeDocument.__table__.drop(bind=op.get_bind(), checkfirst=True)
    KioskHeartbeat.__table__.drop(bind=op.get_bind(), checkfirst=True)
    VisualSession.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Announcement.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Playlist.__table__.drop(bind=op.get_bind(), checkfirst=True)
    AudioZone.__table__.drop(bind=op.get_bind(), checkfirst=True)
    FiscalDocument.__table__.drop(bind=op.get_bind(), checkfirst=True)
    FiscalRange.__table__.drop(bind=op.get_bind(), checkfirst=True)
