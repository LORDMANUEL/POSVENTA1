# Mily Zebra Commerce OS

ERP modular de comercio y ecommerce para Tienda Roatán / Mily Zebra.

## Objetivo

Unificar POS, caja, inventario, compras, ventas, ecommerce, clientes, CRM, reparto, impresión, contabilidad, CxC/CxP, bancos, marketing, automatización, RR.HH., analítica e IA en una sola plataforma instalable en VPS, con clientes Windows/PWA para cajera, vendedor, bodeguero y driver, más un agente local de hardware.

## Principios

- Backend y API propios. No exponer UI nativa de ERPNext/Frappe.
- PostgreSQL como fuente de verdad; Redis para colas y sesiones efímeras.
- Multiempresa, multisucursal y multibodega desde el modelo de dominio.
- Arquitectura modular con dependencias explícitas y activación por tenant.
- Permisos RBAC y auditoría para cada operación sensible.
- POS y frontend en español, responsive y PWA.
- Agente local de hardware con identidad de dispositivo y mínimo privilegio.
- Alembic como autoridad de migraciones en producción.
- Docker Compose + Caddy para instalación VPS y TLS automático con dominio.
- CI obligatorio antes de integrar a `main`.
- Ningún módulo se marca terminado solo por tener tablas o pantalla: requiere backend, migración, permisos, auditoría, pruebas y flujo usable.

## Documentación

- `docs/MANUAL_INSTALACION.md` — instalación, actualización, backup, restore, diagnóstico y criterios de certificación.
- `docs/MANUAL_OPERACION.md` — operación por rol y flujo de cada dominio ERP.
- `docs/ARCHITECTURE.md` — arquitectura técnica.
- `docs/ROADMAP.md` — fases y gates pendientes.

## Estructura

```text
backend/       API FastAPI + módulos ERP + persistencia
frontend/      storefront + administración React/Vite PWA
agent/         agente local Windows/Linux para hardware
desktop/       launchers Windows por rol
infra/         Caddy, proxy y soporte
scripts/       bootstrap, backup, restore y verificación
docs/          arquitectura, alcance, manuales y operación
.github/       CI y construcción de ejecutables
```

## Instalación VPS

En Debian/Ubuntu:

```bash
git clone https://github.com/LORDMANUEL/POSVENTA1.git
cd POSVENTA1
sudo ./install.sh
```

Con dominio ya apuntando a la IP del VPS:

```bash
sudo ./install.sh --domain tienda.midominio.com
```

El instalador instala Docker cuando hace falta, crea secretos aleatorios, levanta PostgreSQL, Redis, API, frontend, almacenamiento persistente y Caddy. Con dominio, Caddy gestiona HTTPS y renovación automática.

También existe `scripts/bootstrap-vps.sh` para automatizar clonación/actualización + instalación desde un servidor limpio.

> Mientras el PR de desarrollo no esté certificado y fusionado, no utilice `main` como release productivo. Producción se promoverá únicamente con evidencia verde.

## Desarrollo

```bash
cp .env.example .env
docker compose up --build
```

- Storefront/proxy: `http://localhost`
- Web interno directo: `http://localhost:8080/admin`
- API local: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## Módulos ERP

El registro de módulos está en `backend/app/module_registry.py`. Incluye plataforma, identidad, sucursales, auditoría, catálogo, inventario, compras, POS/caja, pedidos, pagos, entregas, devoluciones, clientes, CRM, lealtad, notificaciones, storefront, CMS, marketing, Mily Ads, contabilidad, CxC, CxP, bancos, fiscal, RR.HH., asistencia, nómina, workflows, integraciones, hardware, música, experiencias visuales, RAG, IA y analítica.

Los módulos núcleo se habilitan siempre. Los módulos opcionales respetan dependencias y el backend bloquea sus rutas cuando están desactivados.

## Roles

`owner`, `admin`, `manager`, `cashier`, `sales`, `warehouse`, `driver`, `auditor`, `support`.

Los ejecutables por rol no contienen una base de datos separada: consumen la misma API y la visibilidad se resuelve por permisos, módulo y sucursal.

## Operación

```bash
sudo ./scripts/backup.sh
sudo MZ_RESTORE_CONFIRM=<nombre_bd> ./scripts/restore.sh <archivo.sql.gz>
docker compose ps
docker compose logs -f api
```

## Estado de integración

La rama de desarrollo es la línea activa. `main` permanecerá estable hasta que CI, builds, E2E y gates externos aplicables estén verdes. Consulte los manuales y el roadmap antes de instalar en producción.
