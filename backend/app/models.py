from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid4() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    CASHIER = "cashier"
    SALES = "sales"
    WAREHOUSE = "warehouse"
    DRIVER = "driver"
    AUDITOR = "auditor"
    SUPPORT = "support"


class SaleStatus(str, enum.Enum):
    COMPLETED = "completed"
    VOIDED = "voided"


class PrintJobStatus(str, enum.Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_branch_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_product_tenant_sku"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="general", nullable=False)
    size: Mapped[str | None] = mapped_column(String(30), nullable=True)
    color: Mapped[str | None] = mapped_column(String(60), nullable=True)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class StockBalance(Base):
    __tablename__ = "stock_balances"
    __table_args__ = (UniqueConstraint("tenant_id", "branch_id", "product_id", name="uq_stock_scope"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_sale_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    cashier_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[SaleStatus] = mapped_column(Enum(SaleStatus), default=SaleStatus.COMPLETED, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    lines: Mapped[list[SaleLine]] = relationship(back_populates="sale", cascade="all, delete-orphan")


class SaleLine(Base):
    __tablename__ = "sale_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sale: Mapped[Sale] = relationship(back_populates="lines")


class CashSession(Base):
    __tablename__ = "cash_sessions"
    __table_args__ = (
        Index(
            "uq_cash_open_user",
            "tenant_id",
            "user_id",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
            sqlite_where=text("closed_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    opening_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    closing_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": version}


class PrintJob(Base):
    __tablename__ = "print_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PrintJobStatus] = mapped_column(Enum(PrintJobStatus), default=PrintJobStatus.QUEUED, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": version}


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
