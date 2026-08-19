from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import utcnow, uuid4


class FiscalRange(Base):
    __tablename__ = "fiscal_ranges"
    __table_args__ = (
        UniqueConstraint("tenant_id", "branch_id", "document_type", "cai", name="uq_fiscal_range_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    cai: Mapped[str] = mapped_column(String(80), nullable=False)
    prefix: Mapped[str] = mapped_column(String(40), nullable=False)
    range_start: Mapped[int] = mapped_column(Integer, nullable=False)
    range_end: Mapped[int] = mapped_column(Integer, nullable=False)
    current_number: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FiscalDocument(Base):
    __tablename__ = "fiscal_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_number", name="uq_fiscal_document_number"),
        UniqueConstraint("tenant_id", "source_type", "source_id", name="uq_fiscal_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    fiscal_range_id: Mapped[str] = mapped_column(ForeignKey("fiscal_ranges.id", ondelete="RESTRICT"), index=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    document_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    cai: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="issued", nullable=False, index=True)
    issued_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
