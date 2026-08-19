from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .commerce_models import Order, OrderStatus
from .db import get_db
from .models import Product, Sale, SaleLine, SaleStatus, StockBalance, User, UserRole
from .module_api import require_enabled_module
from .security import require_roles

analytics_router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_enabled_module("analytics"))])


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


@analytics_router.get("/dashboard")
def dashboard(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)),
) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    sales = db.scalars(select(Sale).where(Sale.tenant_id == user.tenant_id, Sale.status == SaleStatus.COMPLETED, Sale.created_at >= since)).all()
    orders = db.scalars(select(Order).where(Order.tenant_id == user.tenant_id, Order.created_at >= since)).all()
    stock = db.execute(select(StockBalance, Product).join(Product, Product.id == StockBalance.product_id).where(StockBalance.tenant_id == user.tenant_id)).all()

    sale_total = sum((Decimal(row.total) for row in sales), Decimal("0"))
    order_total = sum((Decimal(row.total) for row in orders if row.status != OrderStatus.CANCELLED), Decimal("0"))
    stock_units = sum((Decimal(balance.quantity) for balance, _ in stock), Decimal("0"))
    stock_cost_value = sum((Decimal(balance.quantity) * Decimal(product.unit_cost) for balance, product in stock), Decimal("0"))
    stock_retail_value = sum((Decimal(balance.quantity) * Decimal(product.sale_price) for balance, product in stock), Decimal("0"))

    return {
        "period_days": days,
        "pos_sales_count": len(sales),
        "pos_sales_total": _money(sale_total),
        "online_orders_count": len(orders),
        "online_orders_total": _money(order_total),
        "inventory_units": str(stock_units),
        "inventory_cost_value": _money(stock_cost_value),
        "inventory_retail_value": _money(stock_retail_value),
    }


@analytics_router.get("/top-products")
def top_products(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)),
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(SaleLine, Product, Sale)
        .join(Sale, Sale.id == SaleLine.sale_id)
        .join(Product, Product.id == SaleLine.product_id)
        .where(Sale.tenant_id == user.tenant_id, Sale.status == SaleStatus.COMPLETED, Sale.created_at >= since)
    ).all()
    totals: dict[str, dict] = {}
    for line, product, _sale in rows:
        item = totals.setdefault(product.id, {"product_id": product.id, "sku": product.sku, "name": product.name, "quantity": Decimal("0"), "revenue": Decimal("0")})
        item["quantity"] += Decimal(line.quantity)
        item["revenue"] += Decimal(line.line_total)
    ranked = sorted(totals.values(), key=lambda item: (item["revenue"], item["quantity"]), reverse=True)[:limit]
    return [{**item, "quantity": str(item["quantity"]), "revenue": _money(item["revenue"])} for item in ranked]


@analytics_router.get("/sales-forecast")
def sales_forecast(
    lookback_days: int = Query(default=28, ge=7, le=180),
    forecast_days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.AUDITOR)),
) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=lookback_days)
    sales = db.scalars(select(Sale).where(Sale.tenant_id == user.tenant_id, Sale.status == SaleStatus.COMPLETED, Sale.created_at >= since)).all()
    daily: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for sale in sales:
        daily[sale.created_at.date().isoformat()] += Decimal(sale.total)
    series = []
    for offset in range(lookback_days):
        day = (since.date() + timedelta(days=offset)).isoformat()
        series.append(daily[day])
    average = sum(series, Decimal("0")) / Decimal(lookback_days)
    projection = average * Decimal(forecast_days)
    return {
        "method": "simple_daily_average",
        "lookback_days": lookback_days,
        "forecast_days": forecast_days,
        "average_daily_sales": _money(average),
        "projected_sales": _money(projection),
        "history": [{"date": (since.date() + timedelta(days=i)).isoformat(), "sales": _money(value)} for i, value in enumerate(series)],
    }
