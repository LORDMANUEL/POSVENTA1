from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .models import utcnow, uuid4


class RefundStatus(str, enum.Enum):
    COMPLETED = "completed"
    PENDING_EXTERNAL = "pending_external"
    FAILED = "failed"


class ReturnRecord(Base):
    __tablename__ = "return_records"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_return_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    lines: Mapped[list[ReturnLine]] = relationship(back_populates="return_record", cascade="all, delete-orphan")
    refunds: Mapped[list[Refund]] = relationship(back_populates="return_record", cascade="all, delete-orphan")


class ReturnLine(Base):
    __tablename__ = "return_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    return_id: Mapped[str] = mapped_column(ForeignKey("return_records.id", ondelete="CASCADE"), index=True)
    sale_line_id: Mapped[str] = mapped_column(ForeignKey("sale_lines.id", ondelete="RESTRICT"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    return_record: Mapped[ReturnRecord] = relationship(back_populates="lines")


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    return_id: Mapped[str] = mapped_column(ForeignKey("return_records.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(Enum(RefundStatus), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    return_record: Mapped[ReturnRecord] = relationship(back_populates="refunds")
