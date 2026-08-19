# Mily Zebra Commerce OS v0.12.1

ERP modular de comercio y ecommerce para Tienda Roatán / Mily Zebra.

## Estado de la versión

`v0.12.1` es la línea estable de software. `main` solo recibe promociones después de CI, instalación limpia, recorridos E2E, Chromium/PWA, backup→restore y builds Windows verdes.

Los módulos que dependen de terceros permanecen **fail-closed** hasta aportar evidencia real de integración: adquirente/pagos, fiscal/CAI, audio/kiosco físico y demás conectores externos. El sistema no simula certificaciones que no existen.

## Objetivo

Unificar POS, caja, inventario, compras, ventas, ecommerce, clientes, CRM, reparto, impresión, contabilidad, CxC/CxP, bancos, marketing, automatización, RR.HH., analítica e IA en una sola plataforma instalable en VPS. La aplicación Windows es la misma web/PWA dentro de Chromium/WebView2; el agente de hardware es el único ejecutable separado.

## Instalación VPS

Debian 13 / Ubuntu Server:

```bash
git clone https://github.com/LORDMANUEL/POSVENTA1.git
cd POSVENTA1
sudo ./install.sh
```

Con dominio ya apuntando al VPS:

```bash
sudo ./install.sh --domain tienda.midominio.com
```

El instalador configura Docker/Compose cuando corresponde, secretos aleatorios, `vm.overcommit_memory` para Redis, PostgreSQL, Redis, migraciones Alembic, API, worker, frontend, media persistente y Caddy. Antes de declarar éxito comprueba API, PostgreSQL, Redis, frontend y el head de migración.

Después abra:

```text
http(s)://servidor/admin
```

y use **Primera instalación** para crear el propietario.

Una tienda nueva tiene habilitado por defecto el perfil ERP interno validado: compras, entregas, devoluciones, CRM, lealtad, notificaciones, CMS, marketing, Mily Ads, contabilidad, CxC, CxP, bancos, RR.HH., asistencia, nómina, workflows, integraciones internas, RAG, IA y analítica, además del núcleo. Los módulos con gate externo permanecen desactivados.

## Aplicación Windows

El build genera:

```text
MilyZebra.exe
MilyZebra-Hardware-Agent.exe
```

`MilyZebra.exe` usa Edge WebView2/Chromium y abre exactamente la misma `/admin`. Cajera, vendedor, bodega, gerencia y driver utilizan el mismo ejecutable; login + RBAC determinan la experiencia.

Configure el VPS en Windows:

```powershell
setx MZ_APP_URL "https://tienda.midominio.com/admin"
```

Perfil persistente:

```text
%LOCALAPPDATA%\MilyZebra\WebView2
```

La PWA incluye Service Worker. El app-shell puede reabrirse sin conexión y conserva snapshots de solo lectura de usuario, catálogo e inventario. Las ventas offline quedan pendientes con el mismo `Idempotency-Key`; ninguna escritura se considera confirmada hasta que la API vuelva a validar usuario, caja, stock y permisos.

`MilyZebra-Hardware-Agent.exe` queda separado porque accede a impresora ESC/POS, cajón y etiquetadora ZPL.

## Operación cubierta

- Multiempresa / multisucursal / RBAC / auditoría.
- Catálogo, fotografías WebP e importación CSV/ZIP.
- Inventario por ledger, conteos con segunda aprobación, reposición y transferencias.
- Proveedores, compras y recepción.
- POS, caja, idempotencia, recibos y cajón.
- Venta offline y resincronización.
- Devoluciones parciales idempotentes, inventario y reembolso de caja.
- Ecommerce, catálogo público, reserva, prevención de sobreventa, tracking y fulfillment.
- Clientes, CRM, lealtad y consentimientos.
- Entregas y driver.
- Contabilidad, balanza, resultados, balance, CxC, CxP, bancos y conciliación.
- RR.HH., asistencia y nómina base.
- CMS, marketing, Mily Ads, workflows/outbox y worker.
- RAG/IA opcional y analítica/forecast.

## Módulos externos bloqueados por defecto

- `payments`: requiere adquirente/proveedor real y pruebas de webhook/reembolso.
- `fiscal`: requiere RTN/CAI/rangos reales y validación/homologación aplicable.
- `music`: requiere reproductor/audio físico y aceptación de zonas.
- `visual`: requiere cámara/kiosco y motor visual aceptado.

El código de soporte puede existir, pero esos módulos no se consideran certificados por software únicamente.

## Backup y restore

El comando simple ya es el backup completo de **BD + fotografías/media**:

```bash
sudo ./scripts/backup.sh
```

Restauración:

```bash
set -a
source .env
set +a
sudo -E MZ_RESTORE_CONFIRM="RESTORE_${POSTGRES_DB}" \
  ./scripts/restore-full.sh backups/milyzebra-full-YYYYMMDDTHHMMSSZ.tar.gz
```

Los gates de CI destruyen datos de prueba y media, restauran el paquete y verifican ambos.

## Desarrollo reproducible

El frontend incluye `package-lock.json` y tanto CI como la imagen Docker usan `npm ci`.

```bash
cp .env.example .env
docker compose up --build
```

- Storefront/proxy: `http://localhost`
- Web interno: `http://localhost/admin`
- API local: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## Versionado de base de datos

Alembic es la autoridad. Head de `v0.12.1`:

```text
20260819_0010
```

No modifique tablas manualmente en producción.

## Documentación

- `docs/MANUAL_INSTALACION.md` — instalación, actualización, backup, restore, diagnóstico y gates.
- `docs/MANUAL_OPERACION.md` — operación diaria por rol.
- `docs/ARCHITECTURE.md` — arquitectura técnica.
- `docs/ROADMAP.md` — evolución posterior.
- `docs/RELEASE_POLICY.md` — política alpha/beta/stable.

## Política de versiones

`main` representa estable. El desarrollo futuro comenzará solamente después del cierre de esta estable:

```text
5 alpha aprobadas = 1 beta
3 beta aprobadas  = 1 stable
```

No se inicia la siguiente alpha mientras la estable vigente tenga un gate interno rojo.
