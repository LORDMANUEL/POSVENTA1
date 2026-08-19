# Manual de operación — Mily Zebra Commerce OS v0.12.1

## Objetivo

Guía operativa para propietarios, administración, gerencia, cajera, vendedor, bodega, driver, auditoría y soporte.

## Roles

- **owner:** control total del tenant y configuración crítica.
- **admin:** administración operativa, usuarios, módulos y dispositivos.
- **manager:** supervisión de tienda, inventario, ventas y operación autorizada.
- **cashier:** POS, devoluciones y caja propia.
- **sales:** venta, postventa permitida y atención comercial.
- **warehouse:** catálogo, inventario, recepción, conteos, transferencias y etiquetas.
- **driver:** entregas asignadas y prueba de entrega.
- **auditor:** consulta sin facultades operativas sensibles.
- **support:** soporte técnico limitado a las funciones autorizadas.

El backend es la autoridad de permisos. Ocultar un botón no sustituye RBAC.

## Primera instalación

Después de crear al propietario, el ERP interno validado queda operativo por defecto. No es necesario activar manualmente compras, CRM, contabilidad, RR.HH., workflows o analítica.

Permanecen apagados hasta certificación externa: pagos/adquirente, fiscal/CAI, música/audio físico y probador/kiosco visual.

## Inicio de jornada

1. Verifique conexión y, si se usa hardware, el agente local.
2. Inicie sesión con una cuenta individual.
3. Cajera: abra su caja e indique fondo inicial.
4. Bodega: revise recepciones, transferencias y reposición.
5. Gerencia: revise dashboard, diferencias y pedidos.

## POS, caja y modo offline

Una venta en efectivo online requiere caja abierta. El servidor registra venta, salida de inventario, movimiento de caja, recibo y apertura de cajón.

Si se pierde Internet, `MilyZebra.exe`/PWA puede reabrir el app-shell desde Service Worker y usar la última instantánea de usuario, catálogo e inventario como referencia. Esa instantánea es **solo lectura**.

Una venta offline:

1. recibe un `Idempotency-Key` único;
2. queda pendiente localmente;
3. no descuenta stock en el servidor mientras no exista confirmación;
4. se reintenta con la misma clave al volver Internet;
5. el servidor vuelve a validar usuario, caja, precios, stock y permisos;
6. si existe conflicto queda **Requiere atención** y no se borra silenciosamente.

No cierre el navegador borrando datos de sitio mientras existan ventas offline pendientes.

### Cierre de caja

1. Cuente físicamente el efectivo.
2. Registre el monto contado.
3. El sistema calcula el esperado desde el ledger.
4. Revise la diferencia.
5. No altere movimientos históricos para ocultar descuadres.
6. Documente y escale diferencias según política interna.

## Productos, fotografías e importación

Cada producto maneja SKU, código de barras, nombre, descripción, categoría, talla, color, costo y precio. La galería admite hasta cinco fotografías validadas y convertidas a WebP.

La importación masiva tiene preview y commit atómico. Para ZIP de fotografías utilice el manifiesto definido por el sistema; un error de archivo/SKU/seguridad impide dejar una importación parcial.

## Inventario

El stock se deriva del ledger. No modifique `stock_balances` directamente.

Operaciones principales:

- recepción de compra;
- transferencia entre sucursales;
- venta;
- devolución;
- conteo físico aprobado;
- ajustes autorizados.

### Conteo físico

1. Cree el conteo.
2. Registre cantidades físicas.
3. Revise diferencias.
4. Un segundo usuario autorizado aprueba.
5. El usuario que contó no puede aprobar su propio ajuste.
6. Solo la aprobación genera el movimiento de ledger.

### Reposición

Configure mínimo y objetivo por producto/sucursal. Las sugerencias no crean compras automáticamente.

## Compras y proveedores

1. Registre proveedor.
2. Cree orden con líneas, cantidades y costo.
3. Reciba en la sucursal correcta.
4. La recepción actualiza inventario por ledger.
5. Registre CxP cuando corresponda.

## Transferencias

Una transferencia conserva origen, destino, líneas, despacho y recepción. No use ajustes manuales para simular una transferencia.

## Ecommerce

La tienda pública y el ERP usan el mismo catálogo e inventario.

1. Cliente navega catálogo.
2. Agrega productos.
3. Checkout revalida precio/stock.
4. Crea pedido idempotente.
5. Reserva inventario.
6. Registra método de pago.
7. Cuando se confirma, prepara y entrega/recoge.
8. La reserva se consume o libera según resultado.

Nunca vuelva a cobrar automáticamente un resultado de pago desconocido.

## Devoluciones y reembolsos

La pantalla **Devoluciones** lista ventas recientes y muestra por línea:

- producto/SKU;
- cantidad vendida;
- cantidad previamente devuelta;
- cantidad máxima todavía retornable.

Flujo:

1. Seleccione la venta.
2. Indique cantidades a devolver.
3. Escriba el motivo.
4. Registre la devolución.
5. El sistema usa un `Idempotency-Key`; si el navegador reintenta la misma operación no duplica inventario ni reembolso.

Para una venta en efectivo:

- debe existir caja abierta del usuario en la sucursal de la venta;
- el stock vuelve mediante ledger;
- el reembolso genera un movimiento negativo de caja;
- se genera recibo de devolución y trabajo de apertura de cajón;
- si no hay caja abierta, la operación devuelve conflicto antes de modificar stock.

Para pagos externos, el reembolso permanece `pending_external` hasta que el proveedor confirme. No se simula como completado.

El sistema impide devolver más unidades de las originalmente vendidas menos las ya devueltas.

## Clientes, CRM y lealtad

Clientes y CRM son dominios distintos. CRM registra leads, oportunidades e interacciones. Lealtad usa su propio ledger de puntos. Marketing debe respetar consentimientos por canal/propósito.

## Entregas y driver

El driver ve únicamente entregas autorizadas/asignadas. Debe actualizar estados reales y registrar prueba/nota. No marque entregado un pedido no recibido.

## Impresión y hardware

- Recibos: ESC/POS.
- Cajón: pulso ESC/POS autorizado.
- Etiquetas: ZPL/TCP RAW.
- El agente se enrola por dispositivo y sucursal.
- Un token incorrecto no puede reclamar trabajos.
- La cola se procesa en orden y cada trabajo se confirma `completed` o `failed`.

La certificación física de impresora/cajón/etiquetadora se realiza con los modelos reales instalados.

## Contabilidad y finanzas

La contabilidad utiliza partida doble; un asiento desbalanceado no puede publicarse.

Incluye plan de cuentas, diario/libro mayor, balanza, Estado de Resultados, Balance General, CxC, CxP, bancos y conciliación.

No borre transacciones para corregir errores; utilice reversas o asientos correctivos según política.

## Fiscal

El motor fiscal administra configuración/rangos/correlativos, pero está desactivado por defecto hasta tener datos reales y homologación aplicable. Programado no significa fiscalmente certificado.

## RR.HH., asistencia y nómina

RR.HH. mantiene empleados; asistencia registra entradas/salidas e incidencias; nómina administra períodos, líneas y aprobación. La operación definitiva debe seguir las reglas laborales/configuraciones que adopte la empresa.

## CMS, marketing y Mily Ads

CMS administra contenido; marketing campañas; Mily Ads placements y métricas. Una publicación externa solo debe marcarse entregada si el conector correspondiente la confirmó.

## Workflows e integraciones

Outbox e idempotencia evitan duplicados. El worker aplica reintentos/backoff y no marca `delivered` sin confirmación del destino.

## Música, kiosco y probador

Estos módulos permanecen con gate externo por defecto. Las sesiones visuales exigen consentimiento y TTL; no deben conservar fotografías indefinidamente.

## RAG e IA

El asistente recupera evidencia antes de responder. Si no hay contexto suficiente debe indicarlo. La IA no puede mover dinero, inventario, fiscal ni permisos de forma autónoma.

## Backup y contingencia

El comando oficial respalda **base de datos y media**:

```bash
sudo ./scripts/backup.sh
```

Conserve una copia externa. Para incidentes:

1. Detenga operaciones que agraven una inconsistencia.
2. Capture logs.
3. Verifique salud DB/API/worker.
4. No borre auditoría.
5. Restaure únicamente desde un paquete verificado.
6. Documente causa y corrección.

## Cierre de jornada

- cerrar cajas;
- revisar diferencias;
- confirmar que no queden ventas offline pendientes;
- revisar pedidos/entregas pendientes;
- revisar trabajos de impresión fallidos;
- revisar reposición;
- confirmar backup completo;
- escalar incidentes de pagos, fiscal, hardware o seguridad.
