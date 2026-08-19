from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Branch, User, UserRole
from .module_api import require_enabled_module
from .people_models import AttendanceRecord, Employee, PayrollLine, PayrollRun
from .security import require_roles
from .services import AuditService

hr_router = APIRouter(prefix="/hr", tags=["hr"], dependencies=[Depends(require_enabled_module("hr"))])
attendance_router = APIRouter(prefix="/attendance", tags=["attendance"], dependencies=[Depends(require_enabled_module("attendance"))])
payroll_router = APIRouter(prefix="/payroll", tags=["payroll"], dependencies=[Depends(require_enabled_module("payroll"))])


class EmployeeIn(BaseModel):
    user_id: str | None = None
    branch_id: str | None = None
    employee_code: str = Field(min_length=1, max_length=40)
    full_name: str = Field(min_length=2, max_length=180)
    identity_number: str | None = Field(default=None, max_length=40)
    position: str = Field(min_length=2, max_length=120)
    department: str = Field(default="General", max_length=120)
    hire_date: date
    base_salary: Decimal = Field(default=Decimal("0"), ge=0)


class AttendanceIn(BaseModel):
    employee_id: str
    branch_id: str | None = None
    event_type: str = Field(pattern="^(check_in|check_out|break_start|break_end)$")
    source: str = Field(default="manual", max_length=40)
    note: str = ""


class PayrollRunIn(BaseModel):
    period_key: str = Field(min_length=2, max_length=30)
    period_start: date
    period_end: date


class PayrollLineIn(BaseModel):
    employee_id: str
    gross: Decimal = Field(ge=0)
    deductions: Decimal = Field(default=Decimal("0"), ge=0)
    bonuses: Decimal = Field(default=Decimal("0"), ge=0)
    note: str = ""


@hr_router.get("/employees")
def list_employees(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR))) -> list[dict]:
    rows = db.scalars(select(Employee).where(Employee.tenant_id == user.tenant_id).order_by(Employee.full_name)).all()
    return [{"id": row.id, "employee_code": row.employee_code, "full_name": row.full_name, "position": row.position, "department": row.department, "branch_id": row.branch_id, "base_salary": str(row.base_salary), "active": row.active} for row in rows]


@hr_router.post("/employees", status_code=201)
def create_employee(payload: EmployeeIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    if db.scalar(select(Employee.id).where(Employee.tenant_id == user.tenant_id, Employee.employee_code == payload.employee_code)):
        raise HTTPException(status_code=409, detail="Código de empleado ya registrado")
    if payload.user_id and not db.scalar(select(User.id).where(User.id == payload.user_id, User.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if payload.branch_id and not db.scalar(select(Branch.id).where(Branch.id == payload.branch_id, Branch.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    row = Employee(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(row)
    db.flush()
    AuditService.record(db, user, "employee.created", "employee", row.id, {"employee_code": row.employee_code})
    db.commit()
    return {"id": row.id, "employee_code": row.employee_code, "active": row.active}


@hr_router.post("/employees/{employee_id}/terminate")
def terminate_employee(employee_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    row = db.scalar(select(Employee).where(Employee.id == employee_id, Employee.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    row.active = False
    row.terminated_at = datetime.now(timezone.utc)
    AuditService.record(db, user, "employee.terminated", "employee", row.id)
    db.commit()
    return {"id": row.id, "active": row.active, "terminated_at": row.terminated_at}


@attendance_router.post("/events", status_code=201)
def record_attendance(payload: AttendanceIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPPORT))) -> dict:
    employee = db.scalar(select(Employee).where(Employee.id == payload.employee_id, Employee.tenant_id == user.tenant_id, Employee.active.is_(True)))
    if not employee:
        raise HTTPException(status_code=404, detail="Empleado activo no encontrado")
    row = AttendanceRecord(tenant_id=user.tenant_id, employee_id=employee.id, branch_id=payload.branch_id or employee.branch_id, event_type=payload.event_type, source=payload.source, note=payload.note)
    db.add(row)
    db.flush()
    AuditService.record(db, user, "attendance.recorded", "attendance", row.id, {"event_type": row.event_type})
    db.commit()
    return {"id": row.id, "employee_id": row.employee_id, "event_type": row.event_type, "occurred_at": row.occurred_at}


@payroll_router.post("/runs", status_code=201)
def create_payroll_run(payload: PayrollRunIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=422, detail="El fin del período no puede ser anterior al inicio")
    if db.scalar(select(PayrollRun.id).where(PayrollRun.tenant_id == user.tenant_id, PayrollRun.period_key == payload.period_key)):
        raise HTTPException(status_code=409, detail="Período de nómina ya registrado")
    row = PayrollRun(tenant_id=user.tenant_id, created_by_user_id=user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    AuditService.record(db, user, "payroll.run.created", "payroll_run", row.id, {"period": row.period_key})
    db.commit()
    return {"id": row.id, "period_key": row.period_key, "status": row.status}


@payroll_router.post("/runs/{run_id}/lines", status_code=201)
def add_payroll_line(run_id: str, payload: PayrollLineIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    run = db.scalar(select(PayrollRun).where(PayrollRun.id == run_id, PayrollRun.tenant_id == user.tenant_id, PayrollRun.status == "draft"))
    if not run:
        raise HTTPException(status_code=404, detail="Nómina borrador no encontrada")
    employee = db.scalar(select(Employee).where(Employee.id == payload.employee_id, Employee.tenant_id == user.tenant_id, Employee.active.is_(True)))
    if not employee:
        raise HTTPException(status_code=404, detail="Empleado activo no encontrado")
    if db.scalar(select(PayrollLine.id).where(PayrollLine.payroll_run_id == run.id, PayrollLine.employee_id == employee.id)):
        raise HTTPException(status_code=409, detail="Empleado ya incluido en la nómina")
    net = (payload.gross + payload.bonuses - payload.deductions).quantize(Decimal("0.01"))
    if net < 0:
        raise HTTPException(status_code=422, detail="El neto de nómina no puede ser negativo")
    line = PayrollLine(payroll_run_id=run.id, employee_id=employee.id, gross=payload.gross, deductions=payload.deductions, bonuses=payload.bonuses, net=net, note=payload.note)
    db.add(line)
    db.commit()
    return {"id": line.id, "employee_id": employee.id, "net": str(line.net)}


@payroll_router.post("/runs/{run_id}/approve")
def approve_payroll(run_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))) -> dict:
    run = db.scalar(select(PayrollRun).where(PayrollRun.id == run_id, PayrollRun.tenant_id == user.tenant_id))
    if not run:
        raise HTTPException(status_code=404, detail="Nómina no encontrada")
    if run.status == "approved":
        return {"id": run.id, "status": run.status, "approved_at": run.approved_at}
    count = len(db.scalars(select(PayrollLine).where(PayrollLine.payroll_run_id == run.id)).all())
    if count == 0:
        raise HTTPException(status_code=409, detail="No se puede aprobar una nómina sin líneas")
    run.status = "approved"
    run.approved_at = datetime.now(timezone.utc)
    AuditService.record(db, user, "payroll.run.approved", "payroll_run", run.id, {"lines": count})
    db.commit()
    return {"id": run.id, "status": run.status, "approved_at": run.approved_at}
