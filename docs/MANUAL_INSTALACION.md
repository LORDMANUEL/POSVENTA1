# Manual de instalación — Mily Zebra Commerce OS

## 1. Propósito

Este manual describe el camino soportado para instalar el ERP modular Mily Zebra en un VPS limpio. El objetivo del proyecto es que el operador no tenga que instalar manualmente Python, Node.js, PostgreSQL o Redis.

## 2. Requisitos del VPS

- Debian 13 o Ubuntu Server soportado por Docker.
- Acceso root o sudo.
- Arquitectura x86_64/amd64 recomendada.
- 2 GB RAM como mínimo operativo para el stack base; 4 GB o más recomendado para producción. Los servicios de IA local requieren memoria adicional y no forman parte del mínimo base.
- 20 GB de almacenamiento como mínimo; dimensionar más para fotografías, backups y logs.
- Puertos 80 y 443 disponibles si se utilizará dominio/HTTPS.
- DNS A/AAAA del dominio apuntando al VPS antes de solicitar TLS.

## 3. Instalación desde Git

Mientras el proyecto permanezca en desarrollo use la rama certificada indicada por el release. Cuando `main` sea promovida a producción, el procedimiento será:

```bash
git clone https://github.com/LORDMANUEL/POSVENTA1.git
cd POSVENTA1
sudo ./install.sh --domain tienda.midominio.com
```

Sin dominio, para red local/evaluación:

```bash
sudo ./install.sh
```

El instalador:

1. Comprueba privilegios.
2. Instala Docker/Compose cuando corresponde.
3. Crea `.env` desde la plantilla si no existe.
4. Genera secretos aleatorios para base de datos y JWT.
5. Crea almacenamiento persistente para PostgreSQL, Redis, Caddy y media.
6. Construye API y frontend.
7. Ejecuta las migraciones Alembic antes de iniciar la API.
8. Levanta el proxy frontal.
9. Espera el health check del backend.
10. Falla con código distinto de cero si el servicio no queda saludable.

## 4. Primera configuración

Abra la URL del sistema y seleccione **Primera instalación**. Cree el propietario inicial. El bootstrap solo se permite cuando no existe ningún usuario.

Después configure, en este orden:

1. Datos de empresa/tenant.
2. Sucursales y bodegas.
3. Usuarios y roles.
4. Módulos opcionales necesarios.
5. Catálogo y fotografías.
6. Inventario inicial mediante movimiento/conteo autorizado.
7. Proveedores y compras.
8. Dispositivos de impresión.
9. Métodos de pago habilitados.
10. Fiscal únicamente después de cargar datos reales y completar la homologación aplicable.

## 5. Agente de hardware

El agente local se enrola desde administración. El token se muestra una sola vez y el servidor conserva únicamente su hash.

Variables principales de la estación:

```text
MZ_AGENT_API_URL=https://tienda.midominio.com/api
MZ_AGENT_DEVICE_ID=CAJA-01
MZ_AGENT_TOKEN=<secreto-de-enrollment>
MZ_PRINTER_HOST=<ip-impresora-recibo>
MZ_PRINTER_PORT=9100
MZ_LABEL_PRINTER_HOST=<ip-etiquetadora>
MZ_LABEL_PRINTER_PORT=9100
```

La impresora de recibos/cajón utiliza ESC/POS. La etiquetadora utiliza ZPL sobre TCP RAW. Deben certificarse los modelos físicos antes de declarar producción.

## 6. Verificación después de instalar

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/health
docker compose logs --tail=100 api
```

Con dominio verifique también HTTPS desde un equipo externo.

## 7. Backup

```bash
sudo ./scripts/backup.sh
```

Conserve los backups fuera del VPS además de la copia local. Un backup no se considera certificado hasta realizar una restauración de prueba.

## 8. Restauración

La restauración es destructiva y exige confirmación explícita:

```bash
sudo MZ_RESTORE_CONFIRM=<nombre_bd> ./scripts/restore.sh <archivo.sql.gz>
```

Después de restaurar ejecute health checks, valide migraciones y realice una venta controlada en un entorno de prueba.

## 9. Actualización

Antes de actualizar:

```bash
sudo ./scripts/backup.sh
git fetch --all --tags
git pull --ff-only
docker compose build --pull
docker compose up -d
```

La API ejecuta `alembic upgrade head` antes de arrancar. No edite tablas manualmente en producción.

## 10. Diagnóstico

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f web
docker compose logs -f caddy
docker compose logs -f db
```

Si el API no está saludable, no continúe operando ventas hasta resolver la causa.

## 11. Criterio de certificación

Una instalación se declara productiva solo cuando, como mínimo:

- CI del commit/release está verde.
- Migraciones PostgreSQL pasan desde base vacía.
- Build frontend pasa.
- Docker Compose pasa validación y smoke test.
- Backup y restore fueron probados.
- E2E de venta, compra, devolución, ecommerce y caja pasan.
- Hardware instalado fue probado físicamente.
- Pagos externos fueron certificados en sandbox/producción controlada.
- Fiscal fue revisado y homologado según corresponda.
- Los ejecutables Windows fueron construidos y, para distribución final, firmados.

No sustituya esta evidencia por una marca manual de “completo”.