# Mily Zebra Commerce OS

ERP modular de comercio y ecommerce para Tienda Roatán / Mily Zebra.

## Objetivo

Unificar POS, caja, inventario, compras, ventas, ecommerce, clientes, CRM, reparto, impresión, contabilidad, CxC/CxP, bancos, marketing, automatización, RR.HH., analítica e IA en una sola plataforma instalable en VPS. La aplicación Windows es la misma web/PWA dentro de Chromium/WebView2; el agente de hardware es el único ejecutable separado.

## Principios

- Backend y API propios. No exponer UI nativa de ERPNext/Frappe.
- PostgreSQL como fuente de verdad; Redis para colas y sesiones efímeras.
- Multiempresa, multisucursal y multibodega desde el modelo de dominio.
- Arquitectura modular con dependencias explícitas y activación por tenant.
- Permisos RBAC y auditoría para cada operación sensible.
- POS y frontend en español, responsive y PWA.
- `MilyZebra.exe` abre exactamente `/admin` con Edge WebView2/Chromium; no duplica lógica ni base de datos.
- Cajera, vendedor, bodega, gerencia, driver y demás roles usan el mismo ejecutable; el backend define permisos según la cuenta autenticada.
- El perfil Chromium es persistente para conservar cookies, Service Worker, localStorage/IndexedDB y la cola offline de la PWA.
- Las ventas offline se conservan con `Idempotency-Key` y se resincronizan contra la misma API cuando vuelve la conectividad.
- `MilyZebra-Hardware-Agent.exe` es separado porque accede a impresoras, cajón y etiquetadora local.
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
agent/         agente local para hardware
desktop/       shell Windows Chromium/WebView2 de la misma PWA
infra/         Caddy, proxy y soporte
scripts/       bootstrap, backup, restore y verificación
docs/          arquitectura, alcance, manuales y operación
.github/       CI y construcción de ejecutables
```

## Instalación VPS

```bash
git clone https://github.com/LORDMANUEL/POSVENTA1.git
cd POSVENTA1
sudo ./install.sh
```

Con dominio ya apuntando a la IP del VPS:

```bash
sudo ./install.sh --domain tienda.midominio.com
```

El instalador instala Docker cuando hace falta, crea secretos aleatorios y levanta PostgreSQL, Redis, API, worker, frontend, almacenamiento persistente y Caddy. Con dominio, Caddy gestiona HTTPS y renovación automática.

> Mientras el PR de desarrollo no esté certificado y fusionado, no utilice `main` como release productivo.

## Aplicación Windows

El build genera únicamente:

```text
MilyZebra.exe
MilyZebra-Hardware-Agent.exe
```

`MilyZebra.exe` usa Edge WebView2 (Chromium) y abre la misma web administrativa. El perfil persistente queda por defecto en `%LOCALAPPDATA%\MilyZebra\WebView2` y puede cambiarse con `MZ_CACHE_DIR`.

La URL del VPS se configura con:

```text
MZ_APP_URL=https://tienda.midominio.com/admin
```

El ejecutable no contiene reglas comerciales, inventario ni una base local separada. La PWA administra caché y cola offline; al recuperar Internet, la misma API vuelve a validar usuario, caja, stock y permisos antes de confirmar una operación.

## Desarrollo

```bash
cp .env.example .env
docker compose up --build
```

- Storefront/proxy: `http://localhost`
- Web interno: `http://localhost/admin`
- API local: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## Módulos ERP

El registro de módulos está en `backend/app/module_registry.py` e incluye plataforma, identidad, sucursales, auditoría, catálogo, inventario, compras, POS/caja, pedidos, pagos, entregas, devoluciones, clientes, CRM, lealtad, notificaciones, storefront, CMS, marketing, Mily Ads, contabilidad, CxC, CxP, bancos, fiscal, RR.HH., asistencia, nómina, workflows, integraciones, hardware, música, experiencias visuales, RAG, IA y analítica.

## Roles

`owner`, `admin`, `manager`, `cashier`, `sales`, `warehouse`, `driver`, `auditor`, `support`.

Todos usan el mismo navegador o `MilyZebra.exe`. La visibilidad y las acciones permitidas se resuelven por permisos, módulo, usuario y sucursal desde el servidor.

## Operación

```bash
sudo ./scripts/backup-full.sh
sudo MZ_RESTORE_CONFIRM=RESTORE_<nombre_bd> ./scripts/restore-full.sh <archivo.tar.gz>
docker compose ps
docker compose logs -f api
```

## Estado de integración

La rama de desarrollo es la línea activa. `main` permanecerá estable hasta que CI, builds, E2E y gates externos aplicables estén verdes.
