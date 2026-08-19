"""Add CRM, people, content and automation modules.

Revision ID: 20260818_0007
Revises: 20260818_0006
Create Date: 2026-08-18
"""

from alembic import op

from app.automation_models import OutboxEvent, WorkflowDefinition, WorkflowRun
from app.content_models import AdPlacement, Campaign, CmsPage
from app.crm_models import Consent, CrmActivity, Lead, LoyaltyEntry, Notification, Opportunity
from app.people_models import AttendanceRecord, Employee, PayrollLine, PayrollRun

revision = "20260818_0007"
down_revision = "20260818_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Lead.__table__.create(bind=op.get_bind(), checkfirst=True)
    Opportunity.__table__.create(bind=op.get_bind(), checkfirst=True)
    CrmActivity.__table__.create(bind=op.get_bind(), checkfirst=True)
    Consent.__table__.create(bind=op.get_bind(), checkfirst=True)
    LoyaltyEntry.__table__.create(bind=op.get_bind(), checkfirst=True)
    Notification.__table__.create(bind=op.get_bind(), checkfirst=True)
    Employee.__table__.create(bind=op.get_bind(), checkfirst=True)
    AttendanceRecord.__table__.create(bind=op.get_bind(), checkfirst=True)
    PayrollRun.__table__.create(bind=op.get_bind(), checkfirst=True)
    PayrollLine.__table__.create(bind=op.get_bind(), checkfirst=True)
    CmsPage.__table__.create(bind=op.get_bind(), checkfirst=True)
    Campaign.__table__.create(bind=op.get_bind(), checkfirst=True)
    AdPlacement.__table__.create(bind=op.get_bind(), checkfirst=True)
    WorkflowDefinition.__table__.create(bind=op.get_bind(), checkfirst=True)
    WorkflowRun.__table__.create(bind=op.get_bind(), checkfirst=True)
    OutboxEvent.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    OutboxEvent.__table__.drop(bind=op.get_bind(), checkfirst=True)
    WorkflowRun.__table__.drop(bind=op.get_bind(), checkfirst=True)
    WorkflowDefinition.__table__.drop(bind=op.get_bind(), checkfirst=True)
    AdPlacement.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Campaign.__table__.drop(bind=op.get_bind(), checkfirst=True)
    CmsPage.__table__.drop(bind=op.get_bind(), checkfirst=True)
    PayrollLine.__table__.drop(bind=op.get_bind(), checkfirst=True)
    PayrollRun.__table__.drop(bind=op.get_bind(), checkfirst=True)
    AttendanceRecord.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Employee.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Notification.__table__.drop(bind=op.get_bind(), checkfirst=True)
    LoyaltyEntry.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Consent.__table__.drop(bind=op.get_bind(), checkfirst=True)
    CrmActivity.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Opportunity.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Lead.__table__.drop(bind=op.get_bind(), checkfirst=True)
