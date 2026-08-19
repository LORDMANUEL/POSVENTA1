from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Branch, CashSession, PrintJob, Product, StockBalance, Tenant, User, UserRole
from .security import create_access_token, get_current_user, hash_password, require_roles, verify_password
from .services import AuditService, InventoryService, SalesService

router = APIRouter()


class BootstrapIn(BaseModel):
    store_name: str = Field(min_length=2, max_length=160)
    branch_name: str = Field(default="Roatán", min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=10, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    barcode: str | None = None
    name: str = Field(min_length=1, max_length=180)
    description: str = ""
    category: str = "general"
    size: str | None = None
    color: str | None = None
    unit_cost: Decimal = Decimal("0")
    sale_price: Decimal = Field(gt=0)


class ProductOut(ProductIn):
    id: str
    active: bool
    model_config = ConfigDict(from_attributes=True)


class InventoryMoveIn(BaseModel):
    product_id: str
    branch_id: str | None = None
    quantity_delta: Decimal
    reason: str = Field(min_length=2, max_length=80)


class SaleLineIn(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)


class SaleIn(BaseModel):
    branch_id: str | None = None
    payment_method: str = Field(default="cash", max_length=40)
    lines: list[SaleLineIn]


class CashOpenIn(BaseModel):
    branch_id: str | None = None
    opening_amount: Decimal = Field(ge=0)


class CashCloseIn(BaseModel):
    closing_amount: Decimal = Field(ge=0)


class PrintJobIn(BaseModel):
    branch_id: str | None = None
    device_id: str | None = None
    job_type: str = Field(pattern="^(receipt|label|drawer)$")
    payload: str


@router.post("/bootstrap", response_model=TokenOut)
def bootstrap(payload: BootstrapIn, db: Session = Depends(get_db)) -> TokenOut:
    if db.scalar(select(func.count(User.id))) != 0:
        raise HTTPException(status_code=409, detail="El sistema ya fue inicializado")
    tenant = Tenant(name=payload.store_name, slug="mily-zebra")
    db.add(tenant)
    db.flush()
    branch = Branch(tenant_id=tenant.id, code="RTN-01", name=payload.branch_name)
    db.add(branch)
    db.flush()
    owner = User(
        tenant_id=tenant.id,
        branch_id=branch.id,
        email=payload.email.lower().strip(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=UserRole.OWNER,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return TokenOut(access_token=create_access_token(owner))


@router.post("/auth/login", response_model=TokenOut)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == form.username.lower().strip(), User.active.is_(True)))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    return TokenOut(access_token=create_access_token(user))


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "tenant_id": user.tenant_id,
        "branch_id": user.branch_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
    }


@router.get("/products", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.tenant_id == user.tenant_id).order_by(Product.name)))


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> Product:
    existing = db.scalar(select(Product).where(Product.tenant_id == user.tenant_id, Product.sku == payload.sku))
    if existing:
        raise HTTPException(status_code=409, detail="SKU ya registrado")
    product = Product(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(product)
    db.flush()
    AuditService.record(db, user, "product.created", "product", product.id, {"sku": product.sku})
    db.commit()
    db.refresh(product)
    return product


@router.get("/inventory")
def inventory(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    rows = db.execute(
        select(StockBalance, Product)
        .join(Product, Product.id == StockBalance.product_id)
        .where(StockBalance.tenant_id == user.tenant_id)
        .order_by(Product.name)
    ).all()
    return [
        {
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "branch_id": balance.branch_id,
            "quantity": str(balance.quantity),
        }
        for balance, product in rows
    ]


@router.post("/inventory/movements")
def move_inventory(
    payload: InventoryMoveIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE)),
) -> dict:
    branch_id = payload.branch_id or user.branch_id
    if not branch_id:
        raise HTTPException(status_code=422, detail="Debe indicar una sucursal")
    balance = InventoryService.move(
        db,
        user,
        branch_id,
        payload.product_id,
        payload.quantity_delta,
        payload.reason,
    )
    AuditService.record(
        db,
        user,
        "inventory.moved",
        "product",
        payload.product_id,
        {"delta": str(payload.quantity_delta), "reason": payload.reason},
    )
    db.commit()
    return {"product_id": payload.product_id, "branch_id": branch_id, "quantity": str(balance.quantity)}


@router.post("/sales", status_code=201)
def create_sale(
    payload: SaleIn,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER, UserRole.SALES)),
) -> dict:
    branch_id = payload.branch_id or user.branch_id
    if not branch_id:
        raise HTTPException(status_code=422, detail="Debe indicar una sucursal")
    sale = SalesService.create_sale(
        db,
        user,
        branch_id,
        idempotency_key,
        payload.payment_method,
        [line.model_dump() for line in payload.lines],
    )
    return {
        "id": sale.id,
        "status": sale.status.value,
        "subtotal": str(sale.subtotal),
        "total": str(sale.total),
        "payment_method": sale.payment_method,
    }


@router.post("/cash/open", status_code=201)
def open_cash(
    payload: CashOpenIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER)),
) -> dict:
    branch_id = payload.branch_id or user.branch_id
    if not branch_id:
        raise HTTPException(status_code=422, detail="Debe indicar una sucursal")
    active = db.scalar(select(CashSession).where(CashSession.user_id == user.id, CashSession.closed_at.is_(None)))
    if active:
        raise HTTPException(status_code=409, detail="Ya existe una caja abierta para este usuario")
    session = CashSession(
        tenant_id=user.tenant_id,
        branch_id=branch_id,
        user_id=user.id,
        opening_amount=payload.opening_amount,
    )
    db.add(session)
    db.flush()
    AuditService.record(db, user, "cash.opened", "cash_session", session.id, {"opening": str(payload.opening_amount)})
    db.commit()
    return {"id": session.id, "opening_amount": str(session.opening_amount), "opened_at": session.opened_at}


@router.post("/cash/{session_id}/close")
def close_cash(
    session_id: str,
    payload: CashCloseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER)),
) -> dict:
    session = db.scalar(
        select(CashSession).where(
            CashSession.id == session_id,
            CashSession.tenant_id == user.tenant_id,
            CashSession.closed_at.is_(None),
        )
    )
    if not session:
        raise HTTPException(status_code=404, detail="Caja abierta no encontrada")
    if user.role == UserRole.CASHIER and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="No puede cerrar la caja de otro usuario")
    session.closing_amount = payload.closing_amount
    session.closed_at = datetime.now(timezone.utc)
    AuditService.record(db, user, "cash.closed", "cash_session", session.id, {"closing": str(payload.closing_amount)})
    db.commit()
    return {"id": session.id, "closing_amount": str(session.closing_amount), "closed_at": session.closed_at}


@router.post("/print-jobs", status_code=201)
def create_print_job(
    payload: PrintJobIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER, UserRole.WAREHOUSE)),
) -> dict:
    branch_id = payload.branch_id or user.branch_id
    if not branch_id:
        raise HTTPException(status_code=422, detail="Debe indicar una sucursal")
    job = PrintJob(
        tenant_id=user.tenant_id,
        branch_id=branch_id,
        device_id=payload.device_id,
        job_type=payload.job_type,
        payload=payload.payload,
    )
    db.add(job)
    db.flush()
    AuditService.record(db, user, "print.queued", "print_job", job.id, {"type": job.job_type})
    db.commit()
    return {"id": job.id, "status": job.status.value}
