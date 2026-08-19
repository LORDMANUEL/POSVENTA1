# Mily Zebra Commerce OS

Sistema integral para Tienda Roatán / Mily Zebra.

## Objetivo

Unificar POS, caja, inventario, ventas, ecommerce, clientes, bodega, reparto, impresión, auditoría y administración en una sola plataforma instalable en VPS, con clientes Windows/PWA para cajera, vendedor y bodeguero, más un agente local de hardware para impresoras, cajón y etiquetas.

## Principios

- Backend y API propios. No exponer UI nativa de ERPNext/Frappe.
- PostgreSQL como fuente de verdad; Redis para colas y sesiones efímeras.
- Multiempresa, multisucursal y multibodega desde el modelo de dominio.
- Permisos RBAC y auditoría para cada operación sensible.
- POS y frontend en español, responsive y PWA.
- Agente local de hardware con mínimo privilegio.
- Docker Compose para VPS y CI obligatorio antes de integrar a `main`.
- No marcar un módulo como terminado solo por tener pantalla o tablas: debe incluir backend, persistencia, permisos, pruebas y flujo usable.

## Estructura

```text
backend/       API FastAPI + dominio + persistencia
frontend/      React/Vite PWA
agent/         agente local Windows/Linux para hardware
infra/         proxy, despliegue y soporte
scripts/       instalación, backup y verificación
docs/          arquitectura, alcance, fases y operación
.github/       CI y construcción de ejecutables
```

## Inicio rápido de desarrollo

```bash
cp .env.example .env
docker compose up --build
```

- Web: `http://localhost:8080`
- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Instalación en VPS

```bash
sudo ./scripts/install.sh
```

El instalador valida Docker, crea `.env` si no existe, levanta PostgreSQL, Redis, API y frontend, y muestra los comandos de verificación.

## Roles iniciales

`owner`, `admin`, `manager`, `cashier`, `sales`, `warehouse`, `driver`, `auditor`, `support`.

Los ejecutables por rol no contienen una base de datos separada: consumen la misma API y la visibilidad se resuelve por permisos y sucursal.

## Estado

La rama de desarrollo es la línea activa. `main` permanecerá estable hasta que los gates de integración estén en verde. Consulte `docs/ARCHITECTURE.md` y `docs/ROADMAP.md`.
