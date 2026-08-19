from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .models import utcnow, uuid4


class PurchaseStatus(str, enum.Enum):
    DRAFT = "draft"
    ORDERED = "ordered"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class TransferStatus(str, enum.Enum):
    PENDING = "pending"
    SHIPPED = "shipped"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    FAILED = "failed"


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_customer_tenant_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    loyalty_points: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[PurchaseStatus] = mapped_column(Enum(PurchaseStatus), default=PurchaseStatus.DRAFT, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lines: Mapped[list[PurchaseOrderLine]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")

    __mapper_args__ = {"version_id_col": version}


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class StockTransfer(Base):
    __tablename__ = "stock_transfers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    from_branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    to_branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[TransferStatus] = mapped_column(Enum(TransferStatus), default=TransferStatus.PENDING, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lines: Mapped[list[StockTransferLine]] = relationship(back_populates="transfer", cascade="all, delete-orphan")

    __mapper_args__ = {"version_id_col": version}


class StockTransferLine(Base):
    __tablename__ = "stock_transfer_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    transfer_id: Mapped[str] = mapped_column(ForeignKey("stock_transfers.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    transfer: Mapped[StockTransfer] = relationship(back_populates="lines")


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    sale_id: Mapped[str | None] = mapped_column(ForeignKey("sales.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    driver_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus), default=DeliveryStatus.PENDING, nullable=False)
    address_text: Mapped[str] = mapped_column(Text, nullable=False)
    proof_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": version}
