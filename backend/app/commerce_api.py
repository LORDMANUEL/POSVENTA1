import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .commerce_models import (
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    PaymentStatus,
    ReservationStatus,
    StockReservation,
)
from .config import get_settings
from .db import get_db
from .media_models import ProductMedia
from .models import Branch, Product, StockBalance, Tenant, User, UserRole
from .ops_models import Customer
from .security import get_current_user, require_roles
from .services import AuditService, InventoryService, money

store_router = APIRouter(prefix="/store", tags=["storefront"])
commerce_router = APIRouter(prefix="/commerce", tags=["commerce"])
settings = get_settings()


class CheckoutLineIn(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)


class CheckoutIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=180)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    payment_method: str = Field(pattern="^(manual_transfer|cash_on_delivery)$")
    fulfillment_method: str = Field(default="pickup", pattern="^(pickup|delivery)$")
    delivery_address: str | None = Field(default=None, max_length=1500)
    lines: list[CheckoutLineIn] = Field(min_length=1)


class MarkPaidIn(BaseModel):
    external_reference: str | None = Field(default=None, max_length=180)


def _utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _tenant_by_slug(db: Session, slug: str) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == slug, Tenant.active.is_(True)))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    return tenant


def _tracking_token(order_id: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"track:{order_id}".encode(), hashlib.sha256).hexdigest()


def _tracking_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _serialize_order(order: Order, include_token: bool = False) -> dict:
    body = {
        "id": order.id,
        "status": order.status.value,
        "subtotal": str(order.subtotal),
        "total": str(order.total),
        "fulfillment_method": order.fulfillment_method,
        "created_at": order.created_at,
        "lines": [
            {
                "product_id": line.product_id,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "line_total": str(line.line_total),
            }
            for line in order.lines
        ],
        "payments": [
            {"id": p.id, "method": p.method, "status": p.status.value, "amount": str(p.amount)}
            for p in order.payments
        ],
    }
    if include_token:
        body["tracking_token"] = _tracking_token(order.id)
    return body


@store_router.get("/{slug}/catalog")
def public_catalog(slug: str, db: Session = Depends(get_db)) -> dict:
    tenant = _tenant_by_slug(db, slug)
    products = db.scalars(
        select(Product)
        .where(Product.tenant_id == tenant.id, Product.active.is_(True))
        .order_by(Product.category, Product.name)
    ).all()
    product_ids = [product.id for product in products]
    primary_media: dict[str, str] = {}
    if product_ids:
        media_rows = db.scalars(
            select(ProductMedia)
            .where(
                ProductMedia.tenant_id == tenant.id,
                ProductMedia.product_id.in_(product_ids),
                ProductMedia.primary.is_(True),
            )
            .order_by(ProductMedia.product_id, ProductMedia.position)
        ).all()
        for media in media_rows:
            primary_media.setdefault(media.product_id, media.public_url)
    return {
        "store": {"name": tenant.name, "slug": tenant.slug},
        "products": [
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "description": p.description,
                "category": p.category,
                "size": p.size,
                "color": p.color,
                "sale_price": str(p.sale_price),
                "primary_image_url": primary_media.get(p.id),
            }
            for p in products
        ],
    }


@store_router.post("/{slug}/checkout", status_code=201)
def checkout(
    slug: str,
    payload: CheckoutIn,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)],
    db: Session = Depends(get_db),
) -> dict:
    tenant = _tenant_by_slug(db, slug)
    existing = db.scalar(select(Order).where(Order.tenant_id == tenant.id, Order.idempotency_key == idempotency_key))
    if existing:
        return _serialize_order(existing, include_token=True)
    if payload.fulfillment_method == "delivery" and not payload.delivery_address:
        raise HTTPException(status_code=422, detail="La entrega a domicilio requiere dirección")
    branch = db.scalar(select(Branch).where(Branch.tenant_id == tenant.id, Branch.active.is_(True)).order_by(Branch.code))
    if not branch:
        raise HTTPException(status_code=409, detail="La tienda no tiene sucursal activa")
    customer = None
    normalized_email = payload.email.lower().strip() if payload.email else None
    if normalized_email:
        customer = db.scalar(select(Customer).where(Customer.tenant_id == tenant.id, Customer.email == normalized_email))
    if customer is None:
        customer = Customer(tenant_id=tenant.id, full_name=payload.full_name, email=normalized_email, phone=payload.phone)
        db.add(customer)
        db.flush()
    else:
        customer.full_name = payload.full_name
        if payload.phone:
            customer.phone = payload.phone
    order = Order(
        tenant_id=tenant.id,
        branch_id=branch.id,
        customer_id=customer.id,
        idempotency_key=idempotency_key,
        tracking_token_hash="pending",
        status=OrderStatus.CONFIRMED if payload.payment_method == "cash_on_delivery" else OrderStatus.PENDING_PAYMENT,
        subtotal=Decimal("0"),
        total=Decimal("0"),
        fulfillment_method=payload.fulfillment_method,
        delivery_address=payload.delivery_address,
    )
    db.add(order)
    db.flush()
    order.tracking_token_hash = _tracking_hash(_tracking_token(order.id))
    subtotal = Decimal("0")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    seen_products: set[str] = set()
    for requested in payload.lines:
        if requested.product_id in seen_products:
            raise HTTPException(status_code=422, detail="Un producto no debe repetirse en el checkout")
        seen_products.add(requested.product_id)
        product = db.scalar(select(Product).where(Product.id == requested.product_id, Product.tenant_id == tenant.id, Product.active.is_(True)))
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        balance = db.scalar(
            select(StockBalance)
            .where(StockBalance.tenant_id == tenant.id, StockBalance.branch_id == branch.id, StockBalance.product_id == product.id)
            .with_for_update()
        )
        on_hand = Decimal(balance.quantity) if balance else Decimal("0")
        reserved = db.scalar(
            select(func.coalesce(func.sum(StockReservation.quantity), 0)).where(
                StockReservation.tenant_id == tenant.id,
                StockReservation.branch_id == branch.id,
                StockReservation.product_id == product.id,
                StockReservation.status == ReservationStatus.ACTIVE,
                StockReservation.expires_at > datetime.now(timezone.utc),
            )
        )
        available = on_hand - Decimal(reserved or 0)
        quantity = Decimal(requested.quantity)
        if quantity > available:
            raise HTTPException(status_code=409, detail=f"Stock insuficiente para {product.name}; disponible: {available}")
        line_total = money(Decimal(product.sale_price) * quantity)
        subtotal += line_total
        db.add(OrderLine(order_id=order.id, product_id=product.id, quantity=quantity, unit_price=product.sale_price, line_total=line_total))
        db.add(StockReservation(tenant_id=tenant.id, branch_id=branch.id, order_id=order.id, product_id=product.id, quantity=quantity, status=ReservationStatus.ACTIVE, expires_at=expires_at))
    order.subtotal = money(subtotal)
    order.total = money(subtotal)
    db.add(Payment(tenant_id=tenant.id, order_id=order.id, method=payload.payment_method, amount=order.total, status=PaymentStatus.PENDING))
    db.commit()
    db.refresh(order)
    return _serialize_order(order, include_token=True)


@store_router.get("/{slug}/orders/{order_id}/track")
def track_order(slug: str, order_id: str, token: str, db: Session = Depends(get_db)) -> dict:
    tenant = _tenant_by_slug(db, slug)
    order = db.scalar(select(Order).where(Order.id == order_id, Order.tenant_id == tenant.id))
    if not order or not hmac.compare_digest(order.tracking_token_hash, _tracking_hash(token)):
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return _serialize_order(order)


@commerce_router.get("/orders")
def list_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    orders = db.scalars(select(Order).where(Order.tenant_id == user.tenant_id).order_by(Order.created_at.desc())).all()
    return [_serialize_order(order) for order in orders]


@commerce_router.post("/orders/{order_id}/mark-paid")
def mark_order_paid(order_id: str, payload: MarkPaidIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.CASHIER))) -> dict:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.tenant_id == user.tenant_id))
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id).order_by(Payment.created_at.desc()))
    if not payment:
        raise HTTPException(status_code=409, detail="Pedido sin registro de pago")
    payment.status = PaymentStatus.PAID
    payment.external_reference = payload.external_reference
    if order.status == OrderStatus.PENDING_PAYMENT:
        order.status = OrderStatus.CONFIRMED
    AuditService.record(db, user, "order.payment_confirmed", "order", order.id, {"method": payment.method})
    db.commit()
    return _serialize_order(order)


@commerce_router.post("/orders/{order_id}/fulfill")
def fulfill_order(order_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE))) -> dict:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.tenant_id == user.tenant_id))
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if order.status == OrderStatus.FULFILLED:
        return _serialize_order(order)
    if order.status not in {OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY}:
        raise HTTPException(status_code=409, detail="El pedido no está listo para consumir inventario")
    reservations = db.scalars(select(StockReservation).where(StockReservation.order_id == order.id, StockReservation.status == ReservationStatus.ACTIVE)).all()
    if len(reservations) != len(order.lines):
        raise HTTPException(status_code=409, detail="Las reservas del pedido no están completas")
    now = datetime.now(timezone.utc)
    for reservation in reservations:
        if _utc_aware(reservation.expires_at) <= now:
            reservation.status = ReservationStatus.EXPIRED
            db.commit()
            raise HTTPException(status_code=409, detail="La reserva del pedido venció")
        InventoryService.move(db, user, order.branch_id, reservation.product_id, -Decimal(reservation.quantity), "online_order", "order", order.id, prevent_negative=True)
        reservation.status = ReservationStatus.CONSUMED
    order.status = OrderStatus.FULFILLED
    AuditService.record(db, user, "order.fulfilled", "order", order.id, {"total": str(order.total)})
    db.commit()
    return _serialize_order(order)
