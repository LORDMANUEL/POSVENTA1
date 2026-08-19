# Manual de operación — Mily Zebra Commerce OS

## Objetivo

Guía operativa para propietarios, administración, gerencia, cajera, vendedor, bodega, driver, auditoría y soporte.

## Roles

- **owner:** control total del tenant y configuración crítica.
- **admin:** administración operativa, usuarios, módulos y dispositivos.
- **manager:** supervisión de tienda, inventario, ventas y operación autorizada.
- **cashier:** POS y caja propia.
- **sales:** venta y atención comercial.
- **warehouse:** catálogo operativo, inventario, recepción, conteos, transferencias y etiquetas.
- **driver:** entregas asignadas y prueba de entrega.
- **auditor:** consulta de información y auditoría sin facultades operativas sensibles.
- **support:** soporte técnico limitado a las funciones permitidas.

El backend es la autoridad de permisos. Ocultar un botón no sustituye RBAC.

## Inicio de jornada

1. Verifique conexión del equipo y agente local.
2. Inicie sesión con cuenta individual; no comparta credenciales.
3. Cajera: abra su caja e indique fondo inicial.
4. Bodega: revise recepciones, transferencias y alertas de reposición.
5. Gerencia: revise dashboard, diferencias pendientes y pedidos ecommerce.

## POS y caja

Una venta en efectivo requiere caja abierta. El sistema registra la venta, salida de inventario, movimiento de caja, recibo y trabajo de apertura de cajón dentro del flujo correspondiente.

Al cierre:

1. Cuente físicamente el efectivo.
2. Registre el monto contado.
3. El sistema calcula el esperado desde el ledger.
4. Revise la diferencia.
5. No altere movimientos históricos para esconder un descuadre.
6. Documente y escale diferencias según política interna.

## Productos y catálogo

Cada producto maneja SKU, código de barras, nombre, descripción, categoría, talla, color, costo y precio. La galería admite hasta cinco fotografías validadas y convertidas a WebP.

Para mercadería real registre además las características operativas definidas por la tienda. La carga masiva debe pasar validación antes de importar y no debe saltarse controles de inventario.

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

1. Cree el conteo para la sucursal.
2. Registre cantidades contadas.
3. Revise diferencias contra sistema.
4. Un usuario autorizado aprueba.
5. Solo entonces se genera el ajuste en ledger.

### Reposición

Configure mínimo y objetivo por producto/sucursal. Las sugerencias se calculan desde existencia disponible y política configurada; son recomendaciones, no compras automáticas.

## Compras y proveedores

1. Registre proveedor.
2. Cree orden con productos, cantidades y costo.
3. Reciba la mercadería en la sucursal correcta.
4. La recepción incrementa inventario mediante ledger.
5. Registre CxP cuando aplique.

## Transferencias

Una transferencia conserva origen, destino, líneas, estado, despacho y recepción. No utilice ajustes manuales para simular transferencias.

## Ecommerce

La tienda pública usa el mismo catálogo y fuente de inventario que el ERP.

Flujo:

1. Cliente navega catálogo.
2. Agrega productos.
3. Checkout vuelve a validar precio/stock.
4. Se crea pedido idempotente.
5. Se reserva inventario.
6. Se registra el método de pago.
7. Al confirmarse se prepara y entrega/recoge.
8. La reserva se consume o libera según resultado.

Nunca vuelva a cobrar automáticamente un pago de resultado desconocido.

## Devoluciones y reembolsos

El sistema impide devolver más unidades de las vendidas. Una devolución válida registra el retorno al inventario y el reembolso. Un proveedor de pago externo debe confirmar su propio reembolso; hasta entonces el estado permanece pendiente.

## Clientes, CRM y lealtad

Clientes y CRM son dominios distintos. CRM registra leads/oportunidades/etapas e interacciones. Lealtad utiliza su propio ledger de puntos. No cambie saldos de puntos manualmente.

Marketing requiere consentimiento válido por canal/propósito cuando corresponda.

## Entregas y driver

El driver consulta únicamente entregas autorizadas/asignadas. Debe actualizar estados reales y registrar prueba/nota de entrega. No marque como entregado un pedido no recibido.

## Impresión

- Recibos: ESC/POS.
- Cajón: pulso ESC/POS autorizado.
- Etiquetas: ZPL mediante impresora configurada.
- Los trabajos se reclaman por un dispositivo enrolado y se confirman como completados o fallidos.

## Contabilidad y finanzas

La contabilidad utiliza partida doble. Un asiento no balanceado no debe publicarse.

Módulos relacionados:

- plan de cuentas;
- diario/libro mayor;
- CxC;
- CxP;
- bancos;
- conciliación;
- estados financieros.

No borre transacciones para corregir errores contables; utilice reversas/asientos correctivos según política.

## Fiscal

El módulo fiscal administra configuración, rangos y correlativos, pero **programado no significa homologado**. No emita documentos fiscales productivos hasta que los datos reales y reglas aplicables hayan sido revisados y certificados.

## RR.HH., asistencia y nómina

RR.HH. mantiene empleados. Asistencia registra entradas/salidas e incidencias. Nómina calcula períodos y requiere aprobación antes de considerarse definitiva. La contabilización debe apoyarse en el módulo contable.

## CMS, marketing y Mily Ads

CMS administra contenido del storefront. Marketing administra campañas. Mily Ads administra placements y métricas. La publicación en redes externas requiere conectores/credenciales y no debe simularse como publicada si el proveedor no confirmó.

## Workflows e integraciones

Las integraciones usan outbox/idempotencia para evitar duplicados. Los workers procesan trabajos pendientes y conservan errores/reintentos. No marque un evento como enviado antes de confirmación del destino.

## Música y perifoneo

Se configuran zonas, playlists y anuncios. Durante perifoneo se aplica ducking según configuración. Los derechos/licencias del contenido reproducido son responsabilidad de la operación de la tienda.

## Probador/kiosco

Las sesiones visuales requieren consentimiento y tienen TTL. No deben conservar fotografías indefinidamente. El kiosco debe reiniciarse tras inactividad y limpiar el contexto de la clienta anterior.

## RAG e IA

El asistente recupera evidencia antes de responder. Si no existe contexto suficiente debe indicarlo. La IA no puede mover dinero, cambiar inventario, emitir documentos fiscales ni modificar permisos por decisión autónoma.

## Backups y contingencia

Ejecute backup periódico y conserve copia externa. Para incidentes:

1. Detenga operaciones que puedan empeorar inconsistencia.
2. Capture logs.
3. Verifique salud de DB/API.
4. No borre evidencia/auditoría.
5. Restaure únicamente desde backup verificado cuando corresponda.
6. Documente la causa y corrección.

## Cierre de jornada

- cerrar cajas;
- revisar diferencias;
- verificar pedidos pendientes;
- verificar trabajos de impresión fallidos;
- revisar entregas no cerradas;
- revisar alertas de stock/reposición;
- confirmar backups según política;
- escalar incidentes de pagos, fiscal o seguridad.