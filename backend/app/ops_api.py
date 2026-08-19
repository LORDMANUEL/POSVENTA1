from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Branch, Product, User, UserRole
from .ops_models import (
    Customer,
    Delivery,
    DeliveryStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseStatus,
    StockTransfer,
    StockTransferLine,
    Supplier,
    TransferStatus,
)
from .security import get_current_user, hash_password, require_roles
from .services import AuditService, InventoryService

ops_router = APIRouter(prefix="/ops", tags=["operations"])


class UserCreateIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=10, max_length=128)
    role: UserRole
    branch_id: str | None = None


class CustomerIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=180)
    email: str | None = None
    phone: str | None = None
    notes: str = ""


class CustomerOut(CustomerIn):
    id: str
    loyalty_points: Decimal
    model_config = ConfigDict(from_attributes=True)


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    tax_id: str | None = None
    notes: str = ""


class SupplierOut(SupplierIn):
    id: str
    model_config = ConfigDict(from_attributes=True)


class PurchaseLineIn(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


class PurchaseIn(BaseModel):
    supplier_id: str
    branch_id: str | None = None
    notes: str = ""
    lines: list[PurchaseLineIn] = Field(min_length=1)


class TransferLineIn(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)


class TransferIn(BaseModel):
    from_branch_id: str
    to_branch_id: str
    notes: str = ""
    lines: list[TransferLineIn] = Field(min_length=1)


class DeliveryIn(BaseModel):
    branch_id: str | None = None
    sale_id: str | None = None
    customer_id: str | None = None
    driver_user_id: str | None = None
    address_text: str = Field(min_length=4, max_length=1000)


class DeliveryStatusIn(BaseModel):
    status: DeliveryStatus
    proof_note: str | None = Field(default=None, max_length=2000)


def _ensure_branch(db: Session, tenant_id: str, branch_id: str) -> None:
    exists = db.scalar(select(Branch.id).where(Branch.id == branch_id, Branch.tenant_id == tenant_id))
    if not exists:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")


def _ensure_product(db: Session, tenant_id: str, product_id: str) -> None:
    exists = db.scalar(select(Product.id).where(Product.id == product_id, Product.tenant_id == tenant_id))
    if not exists:
        raise HTTPException(status_code=404, detail="Producto no encontrado")


@ops_router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)),
) -> list[dict]:
    users = db.scalars(select(User).where(User.tenant_id == user.tenant_id).order_by(User.full_name)).all()
    return [
        {
            "id": item.id,
            "email": item.email,
            "full_name": item.full_name,
            "role": item.role.value,
            "branch_id": item.branch_id,
            "active": item.active,
        }
        for item in users
    ]


@ops_router.post("/users", status_code=201)
def create_user(
    payload: UserCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    email = payload.email.lower().strip()
    if db.scalar(select(User.id).where(User.tenant_id == user.tenant_id, User.email == email)):
        raise HTTPException(status_code=409, detail="Correo ya registrado")
    branch_id = payload.branch_id or user.branch_id
    if branch_id:
        _ensure_branch(db, user.tenant_id, branch_id)
    new_user = User(
        tenant_id=user.tenant_id,
        branch_id=branch_id,
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(new_user)
    db.flush()
    AuditService.record(db, user, "user.created", "user", new_user.id, {"role": payload.role.value})
    db.commit()
    return {"id": new_user.id, "email": new_user.email, "role": new_user.role.value}


@ops_router.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Customer]:
    return list(db.scalars(select(Customer).where(Customer.tenant_id == user.tenant_id).order_by(Customer.full_name)))


@ops_router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(
    payload: CustomerIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER, UserRole.SALES)),
) -> Customer:
    customer = Customer(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(customer)
    db.flush()
    AuditService.record(db, user, "customer.created", "customer", customer.id)
    db.commit()
    db.refresh(customer)
    return customer


@ops_router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE, UserRole.AUDITOR)),
) -> list[Supplier]:
    return list(db.scalars(select(Supplier).where(Supplier.tenant_id == user.tenant_id).order_by(Supplier.name)))


@ops_router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(
    payload: SupplierIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> Supplier:
    supplier = Supplier(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(supplier)
    db.flush()
    AuditService.record(db, user, "supplier.created", "supplier", supplier.id)
    db.commit()
    db.refresh(supplier)
    return supplier


@ops_router.post("/purchases", status_code=201)
def create_purchase(
    payload: PurchaseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> dict:
    branch_id = payload.branch_id or user.branch_id
    if not branch_id:
        raise HTTPException(status_code=422, detail="Debe indicar una sucursal")
    _ensure_branch(db, user.tenant_id, branch_id)
    supplier = db.scalar(select(Supplier).where(Supplier.id == payload.supplier_id, Supplier.tenant_id == user.tenant_id))
    if not supplier:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    purchase = PurchaseOrder(
        tenant_id=user.tenant_id,
        branch_id=branch_id,
        supplier_id=supplier.id,
        created_by_user_id=user.id,
        status=PurchaseStatus.ORDERED,
        notes=payload.notes,
    )
    db.add(purchase)
    db.flush()
    for line in payload.lines:
        _ensure_product(db, user.tenant_id, line.product_id)
        db.add(PurchaseOrderLine(purchase_order_id=purchase.id, **line.model_dump()))
    AuditService.record(db, user, "purchase.created", "purchase_order", purchase.id, {"supplier_id": supplier.id})
    db.commit()
    return {"id": purchase.id, "status": purchase.status.value}


@ops_router.post("/purchases/{purchase_id}/receive")
def receive_purchase(
    purchase_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> dict:
    purchase = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == purchase_id, PurchaseOrder.tenant_id == user.tenant_id))
    if not purchase:
        raise HTTPException(status_code=404, detail="Orden de compra no encontrada")
    if purchase.status == PurchaseStatus.RECEIVED:
        return {"id": purchase.id, "status": purchase.status.value}
    if purchase.status != PurchaseStatus.ORDERED:
        raise HTTPException(status_code=409, detail="La orden no está en estado recibible")
    for line in purchase.lines:
        InventoryService.move(
            db,
            user,
            purchase.branch_id,
            line.product_id,
            line.quantity,
            "purchase_receipt",
            "purchase_order",
            purchase.id,
        )
    purchase.status = PurchaseStatus.RECEIVED
    purchase.received_at = datetime.now(timezone.utc)
    AuditService.record(db, user, "purchase.received", "purchase_order", purchase.id)
    db.commit()
    return {"id": purchase.id, "status": purchase.status.value}


@ops_router.post("/transfers", status_code=201)
def create_transfer(
    payload: TransferIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> dict:
    if payload.from_branch_id == payload.to_branch_id:
        raise HTTPException(status_code=422, detail="Origen y destino deben ser diferentes")
    _ensure_branch(db, user.tenant_id, payload.from_branch_id)
    _ensure_branch(db, user.tenant_id, payload.to_branch_id)
    transfer = StockTransfer(
        tenant_id=user.tenant_id,
        from_branch_id=payload.from_branch_id,
        to_branch_id=payload.to_branch_id,
        created_by_user_id=user.id,
        notes=payload.notes,
    )
    db.add(transfer)
    db.flush()
    for line in payload.lines:
        _ensure_product(db, user.tenant_id, line.product_id)
        db.add(StockTransferLine(transfer_id=transfer.id, **line.model_dump()))
    AuditService.record(db, user, "transfer.created", "stock_transfer", transfer.id)
    db.commit()
    return {"id": transfer.id, "status": transfer.status.value}


@ops_router.post("/transfers/{transfer_id}/ship")
def ship_transfer(
    transfer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> dict:
    transfer = db.scalar(select(StockTransfer).where(StockTransfer.id == transfer_id, StockTransfer.tenant_id == user.tenant_id))
    if not transfer:
        raise HTTPException(status_code=404, detail="Transferencia no encontrada")
    if transfer.status != TransferStatus.PENDING:
        raise HTTPException(status_code=409, detail="La transferencia no está pendiente")
    for line in transfer.lines:
        InventoryService.move(
            db,
            user,
            transfer.from_branch_id,
            line.product_id,
            -line.quantity,
            "transfer_out",
            "stock_transfer",
            transfer.id,
            prevent_negative=True,
        )
    transfer.status = TransferStatus.SHIPPED
    transfer.shipped_at = datetime.now(timezone.utc)
    AuditService.record(db, user, "transfer.shipped", "stock_transfer", transfer.id)
    db.commit()
    return {"id": transfer.id, "status": transfer.status.value}


@ops_router.post("/transfers/{transfer_id}/receive")
def receive_transfer(
    transfer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> dict:
    transfer = db.scalar(select(StockTransfer).where(StockTransfer.id == transfer_id, StockTransfer.tenant_id == user.tenant_id))
    if not transfer:
        raise HTTPException(status_code=404, detail="Transferencia no encontrada")
    if transfer.status == TransferStatus.RECEIVED:
        return {"id": transfer.id, "status": transfer.status.value}
    if transfer.status != TransferStatus.SHIPPED:
        raise HTTPException(status_code=409, detail="La transferencia aún no fue despachada")
    for line in transfer.lines:
        InventoryService.move(
            db,
            user,
            transfer.to_branch_id,
            line.product_id,
            line.quantity,
            "transfer_in",
            "stock_transfer",
            transfer.id,
        )
    transfer.status = TransferStatus.RECEIVED
    transfer.received_at = datetime.now(timezone.utc)
    AuditService.record(db, user, "transfer.received", "stock_transfer", transfer.id)
    db.commit()
    return {"id": transfer.id, "status": transfer.status.value}


@ops_router.get("/deliveries")
def list_deliveries(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    query = select(Delivery).where(Delivery.tenant_id == user.tenant_id)
    if user.role == UserRole.DRIVER:
        query = query.where(Delivery.driver_user_id == user.id)
    deliveries = db.scalars(query.order_by(Delivery.created_at.desc())).all()
    return [
        {
            "id": item.id,
            "sale_id": item.sale_id,
            "customer_id": item.customer_id,
            "driver_user_id": item.driver_user_id,
            "status": item.status.value,
            "address_text": item.address_text,
            "proof_note": item.proof_note,
        }
        for item in deliveries
    ]


@ops_router.post("/deliveries", status_code=201)
def create_delivery(
    payload: DeliveryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES, UserRole.WAREHOUSE)),
) -> dict:
    branch_id = payload.branch_id or user.branch_id
    if not branch_id:
        raise HTTPException(status_code=422, detail="Debe indicar una sucursal")
    _ensure_branch(db, user.tenant_id, branch_id)
    if payload.driver_user_id:
        driver = db.scalar(select(User).where(User.id == payload.driver_user_id, User.tenant_id == user.tenant_id, User.role == UserRole.DRIVER))
        if not driver:
            raise HTTPException(status_code=404, detail="Driver no encontrado")
    delivery = Delivery(
        tenant_id=user.tenant_id,
        branch_id=branch_id,
        sale_id=payload.sale_id,
        customer_id=payload.customer_id,
        driver_user_id=payload.driver_user_id,
        status=DeliveryStatus.ASSIGNED if payload.driver_user_id else DeliveryStatus.PENDING,
        address_text=payload.address_text,
    )
    db.add(delivery)
    db.flush()
    AuditService.record(db, user, "delivery.created", "delivery", delivery.id)
    db.commit()
    return {"id": delivery.id, "status": delivery.status.value}


@ops_router.post("/deliveries/{delivery_id}/status")
def update_delivery_status(
    delivery_id: str,
    payload: DeliveryStatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    delivery = db.scalar(select(Delivery).where(Delivery.id == delivery_id, Delivery.tenant_id == user.tenant_id))
    if not delivery:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    if user.role == UserRole.DRIVER and delivery.driver_user_id != user.id:
        raise HTTPException(status_code=403, detail="Esta entrega no está asignada a usted")
    if user.role not in {UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.DRIVER}:
        raise HTTPException(status_code=403, detail="No tiene permiso para cambiar la entrega")
    delivery.status = payload.status
    delivery.proof_note = payload.proof_note
    if payload.status == DeliveryStatus.DELIVERED:
        delivery.delivered_at = datetime.now(timezone.utc)
        if not payload.proof_note:
            raise HTTPException(status_code=422, detail="La prueba de entrega requiere una nota")
    AuditService.record(db, user, "delivery.status_changed", "delivery", delivery.id, {"status": payload.status.value})
    db.commit()
    return {"id": delivery.id, "status": delivery.status.value, "proof_note": delivery.proof_note}
