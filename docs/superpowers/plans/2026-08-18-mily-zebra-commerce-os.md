# Mily Zebra Commerce OS Implementation Plan

> **For agentic workers:** ejecutar por entregables verificables; cada fase debe cerrar pruebas y documentación antes de avanzar.

**Goal:** construir el sistema integral de Tienda Roatán / Mily Zebra, instalable en VPS, con clientes web/PWA y ejecutables Windows por rol, más hardware local seguro.

**Architecture:** monorepo con FastAPI como API de dominio, PostgreSQL como fuente de verdad, Redis para trabajos efímeros, React como interfaz y un agente local separado para hardware. Los clientes Windows reutilizan la misma aplicación web y fijan el modo de trabajo; el backend conserva la autoridad de permisos.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, PostgreSQL 17, Redis 8, React 19, Vite 8, Nginx, Docker Compose, PyInstaller/pywebview.

**Spec:** `docs/ARCHITECTURE.md` y `docs/ROADMAP.md`.

## Global Constraints

- UI de usuario final completamente propia; no exponer ERPNext/Frappe.
- multiempresa, multisucursal y multibodega.
- español como idioma operativo inicial.
- RBAC y auditoría server-side.
- inventario mediante ledger; ventas/pagos idempotentes.
- secretos fuera del repositorio.
- ningún módulo se declara completo sin backend, persistencia, permisos, pruebas y flujo usable.
- hardware, pagos y fiscalidad requieren certificación externa.

---

### Task 1: Plataforma base

**Files:** `docker-compose.yml`, `.env.example`, `backend/app/config.py`, `backend/app/db.py`, `scripts/install.sh`.

- [x] Definir servicios PostgreSQL, Redis, API y web.
- [x] Separar secretos mediante entorno.
- [x] Crear health endpoint.
- [x] Crear instalación VPS reproducible.
- [ ] Incorporar migraciones Alembic y desactivar auto-create en producción.
- [ ] Añadir proxy TLS productivo y política de headers.

### Task 2: Identidad, tenant y sucursal

**Files:** `backend/app/models.py`, `backend/app/security.py`, `backend/app/api.py`.

- [x] Crear Tenant, Branch y User.
- [x] Crear bootstrap de propietario one-shot.
- [x] Hash Argon2 de contraseñas.
- [x] JWT con tenant/branch/role.
- [x] RBAC inicial.
- [ ] Administración de usuarios, sesiones, revocación y MFA opcional.

### Task 3: Catálogo e inventario

- [x] Producto con SKU/barcode/talla/color/costo/precio.
- [x] StockBalance + InventoryMovement.
- [x] Movimiento manual auditado.
- [x] Prevención de stock negativo en venta.
- [ ] Variantes normalizadas, medios 2–5 fotos, categorías y colecciones.
- [ ] Transferencias, conteos y reservas.
- [ ] etiquetas EAN/QR/ZPL/PDF.

### Task 4: POS y caja

- [x] Carrito POS funcional contra API.
- [x] Venta idempotente.
- [x] Descuento de stock transaccional.
- [x] Apertura/cierre básico de caja.
- [ ] métodos mixtos de pago, descuentos autorizados, impuestos configurables.
- [ ] movimientos de caja, retiros/aprobaciones, conciliación y recibo completo.
- [ ] devoluciones, anulaciones y reembolsos con reversa de ledger.

### Task 5: Hardware local y ejecutables

- [x] Cola de impresión server-side básica.
- [x] Agente local con backend TCP ESC/POS y apertura de cajón.
- [x] Fuente de launchers Windows por modo.
- [ ] enrollment de dispositivos con token rotatorio y heartbeat.
- [ ] spooler Windows/USB, ZPL, retries y dead-letter queue.
- [ ] certificación física por modelo de impresora/cajón/etiquetadora.
- [ ] pipeline firmado para EXE/MSI.

### Task 6: Operación de bodega y reparto

- [ ] proveedores, compras y recepciones.
- [ ] picking/packing por pedido.
- [ ] asignación a driver.
- [ ] evidencia de entrega, georreferencia opcional con consentimiento y estados.

### Task 7: Ecommerce y cliente

- [ ] integrar identidad visual/landing Mily Zebra previamente definida.
- [ ] storefront, carrito, checkout y reservas temporales.
- [ ] adaptadores de pago y webhooks firmados.
- [ ] portal cliente, tracking, devoluciones y lealtad.

### Task 8: Administración y analítica

- [ ] dashboard gerencial, reportes, exportaciones y KPIs.
- [ ] CRM, marketing, campañas y Mily Ads.
- [ ] contabilidad/CxC/CxP/bancos/fiscal mediante módulos separados.
- [ ] RAG, asistente y forecast con permisos.

### Task 9: Gate productivo

- [ ] tests unitarios y de servicio verdes.
- [ ] build frontend reproducible con lockfile.
- [ ] E2E del POS, caja, inventario, pedido y devolución.
- [ ] prueba de backup/restore.
- [ ] hardening, rate limits, CSP, secret scan y dependency scan.
- [ ] certificaciones externas registradas.
- [ ] PR de release a `main` solamente después de cerrar el gate.
