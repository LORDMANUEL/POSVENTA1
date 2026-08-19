# Mily Zebra Commerce OS v0.12.0-rc1

## Propósito

Primera versión candidata instalable del ERP/ecommerce Mily Zebra construida sobre `POSVENTA1`.

## Instalación VPS

```bash
git clone --branch release/v0.12.0-rc1 --single-branch https://github.com/LORDMANUEL/POSVENTA1.git
cd POSVENTA1
sudo ./install.sh --domain tienda.midominio.com
```

Para laboratorio o red local sin dominio:

```bash
git clone --branch release/v0.12.0-rc1 --single-branch https://github.com/LORDMANUEL/POSVENTA1.git
cd POSVENTA1
sudo ./install.sh
```

El instalador levanta PostgreSQL, Redis, API, worker, frontend, almacenamiento persistente y Caddy. Con dominio correctamente apuntado al VPS, Caddy administra HTTPS.

## Windows

El paquete Windows contiene únicamente:

- `MilyZebra.exe`: shell WebView2/Chromium que abre la misma aplicación web `/admin` con almacenamiento persistente para cookies, localStorage, IndexedDB y Service Worker.
- `MilyZebra-Hardware-Agent.exe`: agente separado para impresora ESC/POS, cajón y etiquetadora ZPL.

Cajera, vendedor, bodega, gerencia y driver usan el mismo `MilyZebra.exe`; la experiencia y permisos se derivan del usuario autenticado y del RBAC del servidor.

Configure la URL del VPS con:

```powershell
setx MZ_APP_URL "https://tienda.midominio.com/admin"
```

El perfil WebView2 se conserva por defecto en `%LOCALAPPDATA%\MilyZebra\WebView2`.

## Capacidades incluidas

- Multiempresa/multisucursal, usuarios, roles y auditoría.
- Catálogo, imágenes, importación CSV y ZIP de fotografías.
- Inventario ledger, conteos con segunda aprobación, transferencias y reposición.
- POS, caja, ventas idempotentes, recibos y cola offline/resincronización.
- Compras, proveedores y recepción.
- Ecommerce, carrito, checkout, reservas de stock, tracking y métodos manuales.
- Entregas y driver.
- Devoluciones y reembolsos.
- CRM, lealtad y consentimientos.
- Contabilidad, CxC, CxP, bancos, conciliación, balance general y estado de resultados.
- RR.HH., asistencia y nómina base.
- CMS, campañas, Mily Ads y workflows/outbox.
- Música/perifoneo, kiosco/experiencias visuales, RAG, Ollama opcional y analítica.
- Instalación Docker Compose, Caddy, backup completo DB+media y restore destructivo verificado.

## Gates de esta versión

La candidatura solo se fija en la rama `release/v0.12.0-rc1` después de que el commit correspondiente tenga verdes:

- backend install + Ruff + pytest;
- frontend logic + build;
- contrato del shell Windows;
- compilación real de `MilyZebra.exe` y Hardware Agent en `windows-latest`;
- migraciones PostgreSQL 17;
- validación Docker Compose;
- smoke del stack completo;
- backup → destrucción → restore de DB y media;
- compilación Python.

## Límites de certificación externa

Esta RC es instalable y funcional para evaluación/piloto controlado. No declara como certificados todavía los componentes que requieren evidencia externa: homologación fiscal Honduras/CAI real, proveedor de pagos online, impresoras/cajón/etiquetadora físicos, conectores WhatsApp/redes y firma digital de ejecutables.
