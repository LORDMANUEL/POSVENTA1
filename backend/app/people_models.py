from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import utcnow, uuid4


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_code", name="uq_employee_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)
    employee_code: Mapped[str] = mapped_column(String(40), nullable=False)
    full_name: Mapped[str] = mapped_column(String(180), nullable=False)
    identity_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    position: Mapped[str] = mapped_column(String(120), nullable=False)
    department: Mapped[str] = mapped_column(String(120), default="General", nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "period_key", name="uq_payroll_tenant_period"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    period_key: Mapped[str] = mapped_column(String(30), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PayrollLine(Base):
    __tablename__ = "payroll_lines"
    __table_args__ = (UniqueConstraint("payroll_run_id", "employee_id", name="uq_payroll_run_employee"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    payroll_run_id: Mapped[str] = mapped_column(ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    gross: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    deductions: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    bonuses: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    net: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
