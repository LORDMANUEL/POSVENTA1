# Manual de instalación — Mily Zebra Commerce OS v0.12.1

## 1. Propósito

Este manual describe el camino soportado para instalar o actualizar Mily Zebra Commerce OS en un VPS. El operador no necesita instalar manualmente Python, Node.js, PostgreSQL ni Redis.

`v0.12.1` no se considera estable por nombre: la promoción exige que CI y Stable Gate terminen en verde sobre el mismo SHA.

## 2. Requisitos del VPS

- Debian 13 o Ubuntu Server compatible con Docker.
- Acceso root o sudo.
- Arquitectura x86_64/amd64 recomendada.
- 2 GB RAM como mínimo operativo para el stack base; 4 GB o más recomendado para producción.
- 20 GB de almacenamiento como mínimo; dimensionar más para fotografías, backups y logs.
- Puertos 80 y 443 disponibles para dominio/HTTPS.
- DNS A/AAAA apuntando al VPS antes de utilizar `--domain`.
- IA local/Ollama es opcional y requiere recursos adicionales.

## 3. Instalación desde Git

Mientras `v0.12.1` siga en estabilización use explícitamente la rama candidata:

```bash
git clone --branch stabilize/v0.12.1 --single-branch \
  https://github.com/LORDMANUEL/POSVENTA1.git
cd POSVENTA1
sudo ./install.sh --domain tienda.midominio.com
```

Sin dominio, para LAN o evaluación:

```bash
sudo ./install.sh
```

Después de que la candidata sea promovida y etiquetada como estable, el procedimiento normal vuelve a `main`.

El instalador soportado:

1. Comprueba privilegios y plataforma Debian/Ubuntu.
2. Instala Docker/Compose cuando hace falta.
3. Configura `vm.overcommit_memory=1` para Redis cuando el host lo permite.
4. Crea `.env` desde la plantilla si no existe.
5. Sustituye contraseña PostgreSQL y JWT de ejemplo por secretos criptográficamente aleatorios.
6. Genera `MZ_BOOTSTRAP_TOKEN` criptográficamente aleatorio para impedir que un tercero reclame la primera instalación.
7. Bloquea el arranque si queda cualquier secreto de ejemplo.
8. Configura dominio/CORS cuando se indica `--domain`.
9. Valida Docker Compose.
10. Descarga PostgreSQL, Redis y Caddy.
11. Construye API y frontend mediante dependencias fijadas; frontend usa `npm ci`.
12. Ejecuta Alembic antes de declarar saludable la API.
13. Worker y web esperan a que la API esté saludable.
14. Levanta Caddy/proxy y almacenamiento persistente.
15. Comprueba API, PostgreSQL, Redis, migración y frontend antes de reportar éxito.
16. Guarda el código de primera instalación en `.bootstrap-token` con permisos `600` y lo muestra una vez en consola.

Si cualquiera de esas verificaciones falla, la instalación termina con código distinto de cero.

## 4. Primera configuración segura

Al terminar `install.sh` verá:

```text
Código de primera instalación: <secreto>
```

El mismo valor queda disponible para root en:

```text
./.bootstrap-token
```

Abra `/admin`, seleccione **Primera instalación** e introduzca ese código cuando se solicite. `/bootstrap` exige el código y, una vez creado el primer propietario, queda cerrado por estado de base de datos aunque alguien conozca posteriormente el token.

No publique ni envíe `.env` o `.bootstrap-token`. Ambos están excluidos de Git.

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

### Usuarios presentes en más de una empresa

Si el mismo correo existe en más de un tenant, el backend no elige uno arbitrariamente. Devuelve conflicto y la aplicación solicita el identificador de tienda. La autenticación se resuelve como `tenant:correo` y el JWT firmado debe conservar el mismo `tenant_id` que el usuario persistido.

## 5. Aplicación Windows

`MilyZebra.exe` es la misma web/PWA ejecutada mediante Edge WebView2/Chromium. No contiene otra base de datos ni reglas comerciales duplicadas.

```powershell
setx MZ_APP_URL "https://tienda.midominio.com/admin"
```

Perfil persistente predeterminado:

```text
%LOCALAPPDATA%\MilyZebra\WebView2
```

El Service Worker conserva el app-shell; `/me`, `/products`, `/inventory` y la caja activa pueden utilizar snapshots locales de solo lectura tras una conexión válida. Las escrituras y `/api/` nunca se consideran confirmadas desde caché.

Las ventas offline se guardan en IndexedDB. El payload se cifra mediante AES-GCM cuando WebCrypto está disponible, cada operación conserva una `Idempotency-Key`, no existe truncado silencioso por cantidad y la sincronización se serializa para evitar que dos pestañas envíen la misma cola simultáneamente. Si el almacenamiento local no puede conservar una operación, el error se muestra: el POS no debe fingir que una venta quedó guardada.

## 6. Integridad de inventario

PostgreSQL es la autoridad de stock. Las salidas que pueden reducir inventario bloquean el saldo correspondiente y respetan las reservas ecommerce activas.

```text
on_hand - reservas activas = disponible real
```

POS, transferencias y otras salidas no pueden consumir unidades reservadas por el ecommerce. El fulfillment del pedido sí puede consumir su propia reserva.

La suite de integridad prueba concurrentemente el último artículo: dos cajas no deben poder vender la misma unidad.

## 7. Agente de hardware

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

Los trabajos de impresión se reclaman atómicamente con bloqueo PostgreSQL para evitar que dos agentes tomen el mismo ticket. Recibos/cajón usan ESC/POS y las etiquetas ZPL/TCP RAW. La certificación física sigue dependiendo de los modelos instalados.

## 8. Verificación después de instalar

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/health
docker compose exec -T api alembic current
docker compose logs --tail=100 api worker
```

El health debe reportar `0.12.1` y el head de esquema debe ser:

```text
20260819_0010
```

Con dominio, verifique también HTTPS desde un equipo externo.

## 9. Backup completo

El comando oficial incluye **PostgreSQL y fotografías/media**:

```bash
sudo ./scripts/backup.sh
```

También puede invocar explícitamente:

```bash
sudo ./scripts/backup-full.sh
```

El resultado es un paquete `milyzebra-full-*.tar.gz` con dump de PostgreSQL, media, manifiesto, checksums internos y SHA-256 del paquete. Mantenga una copia fuera del VPS.

## 10. Restauración completa

La restauración es destructiva y exige una frase ligada al nombre real de la base:

```bash
set -a
source .env
set +a
sudo -E MZ_RESTORE_CONFIRM="RESTORE_${POSTGRES_DB}" \
  ./scripts/restore-full.sh backups/milyzebra-full-YYYYMMDDTHHMMSSZ.tar.gz
```

El script valida checksum, formato, nombre de base, recrea PostgreSQL, restaura media, verifica el head Alembic del backup y espera nuevamente el health check.

## 11. Actualización desde la base anterior

Antes de actualizar:

```bash
sudo ./scripts/backup.sh
git fetch --all --tags
git checkout stabilize/v0.12.1
git pull --ff-only
sudo ./install.sh --domain tienda.midominio.com
```

No modifique tablas manualmente. Alembic es la autoridad de esquema.

El Stable Gate reproduce una actualización real: crea primero la base usando `main` en `20260818_0009`, instala después el código candidato y exige converger a `20260819_0010`. Verifica fingerprints de idempotencia, columnas de control de versión e índices de unicidad de caja/conciliación.

## 12. Diagnóstico

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f web
docker compose logs -f proxy
docker compose logs -f db
```

Si API o PostgreSQL dejan de estar saludables, detenga operaciones transaccionales hasta resolver la causa.

Un HTTP `409` en una operación sensible significa que otra transacción ganó una carrera o que el estado cambió; la UI debe recargar y mostrar el estado actual, no repetir ciegamente la escritura.

## 13. Gates de la versión estable

La versión estable de software exige como mínimo:

- Pytest y Ruff verdes.
- Migración limpia hasta `20260819_0010`.
- Actualización real `main/20260818_0009 → candidata/20260819_0010`.
- PostgreSQL concurrency suite: stock, caja, devoluciones, CxC y cola de impresión.
- Aislamiento tenant/sucursal y validación del tenant firmado en JWT.
- Bootstrap protegido contra toma de control inicial.
- Semántica de `Idempotency-Key`: misma clave + operación diferente = `409`.
- POS respetando reservas ecommerce.
- `npm ci`, pruebas lógicas y build React verdes.
- Cola offline durable sin truncado silencioso y Chromium E2E.
- Docker Compose y smoke verde.
- Instalación real mediante `install.sh` en entorno limpio.
- E2E de POS/caja/idempotencia.
- E2E de compras, transferencias, driver y hardware queue.
- E2E ecommerce, reserva/sobreventa/fulfillment.
- E2E CxC/CxP/bancos.
- E2E postventa con devolución idempotente y ledger de caja.
- Backup → destrucción → restore de BD + media.
- Build real de `MilyZebra.exe` y `MilyZebra-Hardware-Agent.exe`.
- `VERSION`, backend, frontend y OpenAPI/API reportando la misma versión.

El Stable Gate no cancela una candidata a mitad de ejecución. El SHA queda congelado hasta obtener resultado.

Las integraciones que dependen de terceros se habilitan únicamente después de su aceptación externa: hardware físico, adquirente/pagos, fiscal/CAI, SMTP/WhatsApp/redes y firma digital del ejecutable. La ausencia de una certificación externa no debe hacer que el software simule una operación exitosa.
