from dataclasses import dataclass
from typing import Final

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import uuid4


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    name: str
    category: str
    dependencies: tuple[str, ...] = ()
    core: bool = False


MODULES: Final[dict[str, ModuleDefinition]] = {
    "platform": ModuleDefinition("platform", "Plataforma y gobierno", "core", core=True),
    "identity": ModuleDefinition("identity", "Identidad y permisos", "core", ("platform",), True),
    "branches": ModuleDefinition("branches", "Sucursales y ubicaciones", "core", ("identity",), True),
    "audit": ModuleDefinition("audit", "Auditoría y seguridad", "core", ("identity",), True),
    "catalog": ModuleDefinition("catalog", "Catálogo y prendas", "commerce", ("identity",), True),
    "inventory": ModuleDefinition("inventory", "Inventario", "commerce", ("catalog", "branches"), True),
    "purchasing": ModuleDefinition("purchasing", "Compras y proveedores", "commerce", ("inventory",)),
    "pos": ModuleDefinition("pos", "POS y caja", "sales", ("inventory", "identity"), True),
    "orders": ModuleDefinition("orders", "Pedidos y checkout", "sales", ("inventory",)),
    "payments": ModuleDefinition("payments", "Pagos y conciliación", "finance", ("orders", "pos")),
    "delivery": ModuleDefinition("delivery", "Entregas y driver", "sales", ("orders",)),
    "returns": ModuleDefinition("returns", "Devoluciones y reembolsos", "sales", ("pos", "inventory")),
    "customers": ModuleDefinition("customers", "Clientes", "crm", ("identity",), True),
    "crm": ModuleDefinition("crm", "CRM", "crm", ("customers",)),
    "loyalty": ModuleDefinition("loyalty", "Lealtad", "crm", ("customers", "orders")),
    "notifications": ModuleDefinition("notifications", "Notificaciones", "crm", ("customers",)),
    "storefront": ModuleDefinition("storefront", "Tienda online", "ecommerce", ("catalog", "orders"), True),
    "cms": ModuleDefinition("cms", "CMS", "marketing", ("storefront",)),
    "marketing": ModuleDefinition("marketing", "Marketing y campañas", "marketing", ("crm", "cms")),
    "mily_ads": ModuleDefinition("mily_ads", "Mily Ads", "marketing", ("marketing",)),
    "accounting": ModuleDefinition("accounting", "Contabilidad", "finance", ("platform",)),
    "receivables": ModuleDefinition("receivables", "Cuentas por cobrar", "finance", ("accounting", "customers")),
    "payables": ModuleDefinition("payables", "Cuentas por pagar", "finance", ("accounting", "purchasing")),
    "banking": ModuleDefinition("banking", "Bancos y conciliación", "finance", ("accounting",)),
    "fiscal": ModuleDefinition("fiscal", "Fiscal Honduras", "finance", ("accounting", "pos", "orders")),
    "hr": ModuleDefinition("hr", "Recursos humanos", "people", ("identity",)),
    "attendance": ModuleDefinition("attendance", "Asistencia", "people", ("hr",)),
    "payroll": ModuleDefinition("payroll", "Nómina", "people", ("hr", "accounting")),
    "workflows": ModuleDefinition("workflows", "Workflows y SLA", "automation", ("audit",)),
    "integrations": ModuleDefinition("integrations", "Integraciones y webhooks", "automation", ("audit",)),
    "hardware": ModuleDefinition("hardware", "Hardware de tienda", "store", ("pos",), True),
    "music": ModuleDefinition("music", "Música y perifoneo", "store", ("branches",)),
    "visual": ModuleDefinition("visual", "Probador y kiosco", "experience", ("catalog", "customers")),
    "rag": ModuleDefinition("rag", "RAG y conocimiento", "ai", ("catalog",)),
    "ai": ModuleDefinition("ai", "Asistentes de IA", "ai", ("rag",)),
    "analytics": ModuleDefinition("analytics", "Analítica y forecast", "analytics", ("inventory", "orders")),
}


class TenantModule(Base):
    __tablename__ = "tenant_modules"
    __table_args__ = (UniqueConstraint("tenant_id", "module_key", name="uq_tenant_module"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    module_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
