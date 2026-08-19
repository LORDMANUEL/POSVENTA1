# Arquitectura de Mily Zebra Commerce OS

## 1. Alcance del sistema

La plataforma cubre la operación completa de una tienda de variedades/moda femenina: catálogo, productos y variantes, inventario, compras, POS, caja, ecommerce, pedidos, pagos, devoluciones, clientes, CRM, lealtad, reparto, impresión, etiquetas, administración, auditoría, reportes, marketing, contenido y automatización.

## 2. Arquitectura

```text
Internet / LAN
      |
      v
Reverse proxy / TLS
      |
      +--> React PWA / clientes Windows
      |
      +--> FastAPI Domain API
              |
              +--> PostgreSQL
              +--> Redis
              +--> Worker / scheduler
              +--> integrations adapters
              +--> hardware print queue
                           |
                           v
                    Local Store Agent
                     |     |      |
                  receipt drawer labels
```

### Servidor central

- FastAPI: API HTTP y WebSocket/SSE.
- PostgreSQL: fuente de verdad transaccional.
- Redis: colas, locks, rate limiting y caché corta.
- Worker: trabajos de impresión, notificaciones, reservas, conciliaciones y tareas asíncronas.
- React/Vite: aplicación administrativa, POS y tienda pública.

### Agente local

El agente local se instala en las PCs de tienda y registra un `device_id`. Solo ejecuta trabajos de hardware autorizados para su sucursal. No acepta comandos arbitrarios ni expone shell remoto.

Backends previstos:

- ESC/POS USB/red para recibos.
- TCP 9100/CUPS/Windows spooler para impresoras.
- ZPL para etiquetas.
- Pulso de cajón a través de impresora compatible.

## 3. Dominio mínimo

Entidades nucleares:

- Tenant, Branch, Warehouse, Register, Device.
- User, Role, Permission, Session.
- Product, Variant, Category, PriceList, MediaAsset.
- InventoryMovement, StockBalance, Reservation, Transfer, StockCount.
- Supplier, PurchaseOrder, GoodsReceipt.
- Customer, Address, Consent, LoyaltyAccount.
- Cart, Order, Sale, SaleLine, Payment, Refund, Return.
- CashSession, CashMovement, Reconciliation.
- Delivery, DriverAssignment, ProofOfDelivery.
- PrintJob, DeviceHeartbeat.
- AuditEvent, SecurityEvent.

## 4. Reglas de consistencia

- Inventario se modifica únicamente mediante movimientos de ledger.
- Ventas y pagos utilizan claves de idempotencia.
- Cierre de caja nunca sobrescribe movimientos históricos.
- Operaciones sensibles generan `AuditEvent`.
- Cada fila operativa incluye `tenant_id`; las transacciones de tienda además incluyen `branch_id` cuando aplica.
- El backend aplica permisos; el frontend solo mejora UX.
- El agente local no puede crear ventas, pagos ni ajustes de inventario.

## 5. Roles

- `owner`: gobierno del tenant.
- `admin`: configuración global y usuarios.
- `manager`: operación y aprobaciones de sucursal.
- `cashier`: POS, caja y recibos.
- `sales`: clientes, catálogo y pedidos.
- `warehouse`: recepciones, conteos, transferencias y picking.
- `driver`: entregas asignadas y prueba de entrega.
- `auditor`: lectura ampliada, conciliaciones y auditoría.
- `support`: diagnóstico técnico limitado.

## 6. Clientes Windows

Los `.exe` se construirán desde el mismo frontend/PWA para evitar cuatro productos divergentes. Cada instalador puede fijar `APP_MODE` (`cashier`, `sales`, `warehouse`, `driver`) y la API determina permisos reales según el usuario autenticado.

El agente de hardware se distribuye como ejecutable separado y servicio opcional de Windows.

## 7. ERPNext/Frappe

ERPNext/Frappe puede utilizarse más adelante como motor lógico complementario cuando convenga, mediante adaptadores explícitos. La interfaz, API de dominio, flujos, permisos y experiencia de Mily Zebra son propios. Ningún usuario final depende de la UI nativa de ERPNext.

## 8. Producción

Un módulo solo es `COMPLETE` cuando cumple simultáneamente:

1. API/dominio funcional.
2. Migración persistente.
3. permisos y auditoría.
4. pruebas unitarias/servicio.
5. UI operativa.
6. prueba integral.
7. documentación.
8. certificación externa cuando dependa de hardware, pagos o fiscalidad.
