# Manual de instalación — Mily Zebra Commerce OS v0.12.1

## 1. Propósito

Este manual describe el camino soportado para instalar Mily Zebra Commerce OS en un VPS limpio. El operador no necesita instalar manualmente Python, Node.js, PostgreSQL ni Redis.

## 2. Requisitos del VPS

- Debian 13 o Ubuntu Server compatible con Docker.
- Acceso root o sudo.
- Arquitectura x86_64/amd64 recomendada.
- 2 GB RAM como mínimo operativo para el stack base; 4 GB o más recomendado para producción.
- 20 GB de almacenamiento como mínimo; dimensionar más para fotografías, backups y logs.
- Puertos 80 y 443 disponibles para dominio/HTTPS.
- DNS A/AAAA apuntando al VPS antes de utilizar `--domain`.
- IA local/Ollama es opcional y requiere recursos adicionales.

## 3. Instalación estable desde Git

```bash
git clone https://github.com/LORDMANUEL/POSVENTA1.git
cd POSVENTA1
sudo ./install.sh --domain tienda.midominio.com
```

Sin dominio, para LAN o evaluación:

```bash
sudo ./install.sh
```

El instalador soportado:

1. Comprueba privilegios y plataforma Debian/Ubuntu.
2. Instala Docker/Compose cuando hace falta.
3. Configura `vm.overcommit_memory=1` para Redis cuando el host lo permite.
4. Crea `.env` desde la plantilla si no existe.
5. Sustituye secretos de ejemplo por secretos criptográficamente aleatorios.
6. Bloquea el arranque si queda un secreto de ejemplo.
7. Configura dominio/CORS cuando se indica `--domain`.
8. Valida Docker Compose.
9. Descarga PostgreSQL, Redis y Caddy.
10. Construye API y frontend mediante dependencias fijadas; frontend usa `npm ci`.
11. Levanta PostgreSQL y Redis.
12. Ejecuta Alembic antes de declarar saludable la API.
13. Worker y web esperan a que la API esté saludable.
14. Levanta Caddy/proxy y almacenamiento persistente.
15. Comprueba API, PostgreSQL, Redis, migración y frontend antes de reportar éxito.

Si cualquiera de esas verificaciones falla, la instalación termina con código distinto de cero.

## 4. Primera configuración

Abra `/admin` y seleccione **Primera instalación**. El bootstrap solo funciona si aún no existe ningún usuario.

Configure en este orden:

1. Empresa/tenant.
2. Sucursales.
3. Usuarios y roles.
4. Módulos opcionales necesarios.
5. Catálogo, variantes y fotografías.
6. Inventario inicial mediante movimientos o conteos autorizados.
7. Proveedores y compras.
8. Dispositivos/agente de hardware.
9. Métodos de pago operativos.
10. Fiscal solamente después de cargar datos reales y completar la revisión/homologación aplicable.

## 5. Aplicación Windows

`MilyZebra.exe` es la misma web/PWA ejecutada mediante Edge WebView2/Chromium. No contiene otra base de datos ni reglas comerciales duplicadas.

```powershell
setx MZ_APP_URL "https://tienda.midominio.com/admin"
```

Perfil persistente predeterminado:

```text
%LOCALAPPDATA%\MilyZebra\WebView2
```

El Service Worker conserva el app-shell; `/me`, `/products` e `/inventory` pueden utilizar snapshots locales de solo lectura tras una conexión válida. Las escrituras y `/api/` nunca se consideran confirmadas desde caché. Las ventas offline permanecen pendientes con su `Idempotency-Key` hasta que el servidor las valide.

## 6. Agente de hardware

El agente local se enrola desde administración. El secreto se muestra una sola vez y el servidor almacena solamente su hash.

```text
MZ_AGENT_API_URL=https://tienda.midominio.com/api
MZ_AGENT_DEVICE_ID=CAJA-01
MZ_AGENT_TOKEN=<secreto-de-enrollment>
MZ_PRINTER_HOST=<ip-impresora-recibo>
MZ_PRINTER_PORT=9100
MZ_LABEL_PRINTER_HOST=<ip-etiquetadora>
MZ_LABEL_PRINTER_PORT=9100
```

Recibos/cajón usan ESC/POS y las etiquetas ZPL/TCP RAW. La certificación física depende de los modelos instalados.

## 7. Verificación después de instalar

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/health
docker compose exec -T api alembic current
docker compose logs --tail=100 api worker
```

El head de esquema de v0.12.1 es:

```text
20260819_0010
```

Con dominio, verifique también HTTPS desde un equipo externo.

## 8. Backup completo

El comando oficial incluye **PostgreSQL y fotografías/media**:

```bash
sudo ./scripts/backup.sh
```

También puede invocar explícitamente:

```bash
sudo ./scripts/backup-full.sh
```

El resultado es un paquete `milyzebra-full-*.tar.gz` con dump de PostgreSQL, media, manifiesto, checksums internos y SHA-256 del paquete. Mantenga una copia fuera del VPS.

## 9. Restauración completa

La restauración es destructiva y exige una frase ligada al nombre real de la base:

```bash
set -a
source .env
set +a
sudo -E MZ_RESTORE_CONFIRM="RESTORE_${POSTGRES_DB}" \
  ./scripts/restore-full.sh backups/milyzebra-full-YYYYMMDDTHHMMSSZ.tar.gz
```

El script valida checksum, formato, nombre de base, recrea PostgreSQL, restaura media, verifica el head Alembic del backup y espera nuevamente el health check.

## 10. Actualización de una estable

```bash
sudo ./scripts/backup.sh
git fetch --all --tags
git checkout main
git pull --ff-only
sudo ./install.sh --domain tienda.midominio.com
```

No modifique tablas manualmente. Alembic es la autoridad de esquema.

## 11. Diagnóstico

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f web
docker compose logs -f proxy
docker compose logs -f db
```

Si API o PostgreSQL dejan de estar saludables, detenga operaciones transaccionales hasta resolver la causa.

## 12. Gates de la versión estable

La versión estable de software exige como mínimo:

- Pytest y Ruff verdes.
- Migración desde PostgreSQL vacío hasta `20260819_0010`.
- `npm ci`, pruebas lógicas y build React verdes.
- Docker Compose y smoke verde.
- Instalación real mediante `install.sh` en entorno limpio.
- E2E de POS/caja/idempotencia.
- E2E de compras, transferencias, driver y hardware queue.
- E2E ecommerce, reserva/sobreventa/fulfillment.
- E2E CxC/CxP/bancos.
- E2E postventa con devolución idempotente y ledger de caja.
- Chromium: login, PWA, recarga offline y resincronización.
- Backup → destrucción → restore de BD + media.
- Build real de `MilyZebra.exe` y `MilyZebra-Hardware-Agent.exe`.

Las integraciones que dependen de terceros se habilitan únicamente después de su aceptación externa: hardware físico, adquirente/pagos, fiscal/CAI, SMTP/WhatsApp/redes y firma digital del ejecutable. La ausencia de una certificación externa no debe hacer que el software simule una operación exitosa.
