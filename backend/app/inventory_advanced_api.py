import json
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .inventory_advanced_models import ReplenishmentRule, StockCount, StockCountLine
from .models import Branch, PrintJob, Product, StockBalance, User, UserRole
from .module_api import require_enabled_module
from .security import require_roles
from .services import AuditService, InventoryService

inventory_advanced_router = APIRouter(prefix="/inventory-advanced", tags=["inventory-advanced"], dependencies=[Depends(require_enabled_module("inventory"))])


class CountLineIn(BaseModel):
    product_id: str
    counted_quantity: Decimal = Field(ge=0)


class CountIn(BaseModel):
    branch_id: str | None = None
    note: str = ""
    lines: list[CountLineIn] = Field(min_length=1)


class ReplenishmentRuleIn(BaseModel):
    branch_id: str | None = None
    product_id: str
    min_quantity: Decimal = Field(ge=0)
    target_quantity: Decimal = Field(ge=0)


class LabelRequestIn(BaseModel):
    product_id: str
    branch_id: str | None = None
    device_id: str | None = None
    copies: int = Field(default=1, ge=1, le=100)
    include_qr: bool = True


def _branch_id(payload_branch: str | None, user: User) -> str:
    branch_id = payload_branch or user.branch_id
    if not branch_id:
        raise HTTPException(status_code=422, detail="Debe indicar sucursal")
    return branch_id


@inventory_advanced_router.post("/counts", status_code=201)
def create_count(payload: CountIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE))) -> dict:
    branch_id = _branch_id(payload.branch_id, user)
    if not db.scalar(select(Branch.id).where(Branch.id == branch_id, Branch.tenant_id == user.tenant_id)):
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    count = StockCount(tenant_id=user.tenant_id, branch_id=branch_id, created_by_user_id=user.id, note=payload.note)
    db.add(count)
    db.flush()
    seen: set[str] = set()
    for item in payload.lines:
        if item.product_id in seen:
            raise HTTPException(status_code=422, detail="Producto duplicado en conteo")
        seen.add(item.product_id)
        product = db.scalar(select(Product).where(Product.id == item.product_id, Product.tenant_id == user.tenant_id))
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        balance = db.scalar(select(StockBalance).where(StockBalance.tenant_id == user.tenant_id, StockBalance.branch_id == branch_id, StockBalance.product_id == product.id))
        system_qty = Decimal(balance.quantity) if balance else Decimal("0")
        db.add(StockCountLine(stock_count_id=count.id, product_id=product.id, system_quantity=system_qty, counted_quantity=item.counted_quantity))
    AuditService.record(db, user, "stock_count.created", "stock_count", count.id, {"lines": len(payload.lines)})
    db.commit()
    return {"id": count.id, "status": count.status, "lines": len(payload.lines)}


@inventory_advanced_router.post("/counts/{count_id}/approve")
def approve_count(count_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    count = db.scalar(select(StockCount).where(StockCount.id == count_id, StockCount.tenant_id == user.tenant_id))
    if not count:
        raise HTTPException(status_code=404, detail="Conteo no encontrado")
    if count.status == "approved":
        return {"id": count.id, "status": count.status, "approved_at": count.approved_at}
    lines = db.scalars(select(StockCountLine).where(StockCountLine.stock_count_id == count.id)).all()
    adjustments = 0
    for line in lines:
        delta = Decimal(line.counted_quantity) - Decimal(line.system_quantity)
        if delta != 0:
            InventoryService.move(db, user, count.branch_id, line.product_id, delta, "stock_count_adjustment", "stock_count", count.id, prevent_negative=True)
            adjustments += 1
    count.status = "approved"
    count.approved_by_user_id = user.id
    count.approved_at = datetime.now(timezone.utc)
    AuditService.record(db, user, "stock_count.approved", "stock_count", count.id, {"adjustments": adjustments})
    db.commit()
    return {"id": count.id, "status": count.status, "adjustments": adjustments, "approved_at": count.approved_at}


@inventory_advanced_router.put("/replenishment-rules")
def upsert_replenishment_rule(payload: ReplenishmentRuleIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE))) -> dict:
    if payload.target_quantity < payload.min_quantity:
        raise HTTPException(status_code=422, detail="Objetivo no puede ser menor al mínimo")
    branch_id = _branch_id(payload.branch_id, user)
    row = db.scalar(select(ReplenishmentRule).where(ReplenishmentRule.tenant_id == user.tenant_id, ReplenishmentRule.branch_id == branch_id, ReplenishmentRule.product_id == payload.product_id))
    if row is None:
        row = ReplenishmentRule(tenant_id=user.tenant_id, branch_id=branch_id, product_id=payload.product_id, min_quantity=payload.min_quantity, target_quantity=payload.target_quantity)
        db.add(row)
    else:
        row.min_quantity = payload.min_quantity
        row.target_quantity = payload.target_quantity
    db.commit()
    return {"id": row.id, "branch_id": row.branch_id, "product_id": row.product_id, "min_quantity": str(row.min_quantity), "target_quantity": str(row.target_quantity)}


@inventory_advanced_router.get("/replenishment-suggestions")
def replenishment_suggestions(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE, UserRole.AUDITOR))) -> list[dict]:
    rules = db.scalars(select(ReplenishmentRule).where(ReplenishmentRule.tenant_id == user.tenant_id)).all()
    result = []
    for rule in rules:
        balance = db.scalar(select(StockBalance).where(StockBalance.tenant_id == user.tenant_id, StockBalance.branch_id == rule.branch_id, StockBalance.product_id == rule.product_id))
        qty = Decimal(balance.quantity) if balance else Decimal("0")
        if qty <= Decimal(rule.min_quantity):
            result.append({"branch_id": rule.branch_id, "product_id": rule.product_id, "quantity": str(qty), "suggested_quantity": str(max(Decimal("0"), Decimal(rule.target_quantity) - qty))})
    return result


def build_zpl(product: Product, copies: int, include_qr: bool) -> str:
    name = product.name.replace("^", " ")[:28]
    sku = product.sku.replace("^", " ")[:30]
    barcode = (product.barcode or product.sku).replace("^", " ")[:40]
    qr = f"^FO310,45^BQN,2,4^FDLA,{barcode}^FS" if include_qr else ""
    return f"^XA^PW600^LL300^CF0,28^FO25,25^FD{name}^FS^CF0,22^FO25,70^FDSKU: {sku}^FS^FO25,110^BY2^BCN,80,Y,N,N^FD{barcode}^FS{qr}^PQ{copies}^XZ"


@inventory_advanced_router.post("/labels", status_code=201)
def queue_label(payload: LabelRequestIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE))) -> dict:
    branch_id = _branch_id(payload.branch_id, user)
    product = db.scalar(select(Product).where(Product.id == payload.product_id, Product.tenant_id == user.tenant_id))
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    zpl = build_zpl(product, payload.copies, payload.include_qr)
    job = PrintJob(tenant_id=user.tenant_id, branch_id=branch_id, device_id=payload.device_id, job_type="label", payload=json.dumps({"protocol": "zpl", "raw": zpl}, ensure_ascii=False))
    db.add(job)
    db.flush()
    AuditService.record(db, user, "label.queued", "print_job", job.id, {"product_id": product.id, "copies": payload.copies})
    db.commit()
    return {"id": job.id, "status": job.status.value, "protocol": "zpl"}
