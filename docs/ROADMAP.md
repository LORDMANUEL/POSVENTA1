# Roadmap de construcción

## Fase 0 — Gobierno y arquitectura

- Monorepo, CI, Docker, configuración y documentación.
- Modelo multiempresa/multisucursal.
- Identidad, roles, permisos y auditoría.
- Gate de integración a `main`.

## Fase 1 — Núcleo vendible

- Catálogo, variantes, precios e imágenes.
- Inventario ledger, existencias y reservas.
- POS, ventas, pagos básicos y recibos.
- Apertura/cierre de caja y movimientos.
- Clientes.
- PWA usable en escritorio/tablet/móvil.
- Agente local y cola de impresión.

## Fase 2 — Operación de tienda

- Compras, proveedores, recepciones.
- Transferencias, conteos y reposición.
- Devoluciones/reembolsos.
- Etiquetas QR/EAN/ZPL/PDF.
- Bodeguero, picking y packing.
- Driver, asignaciones y prueba de entrega.
- Clientes Windows por modo de trabajo.

## Fase 3 — Ecommerce y experiencia

- Landing/storefront Mily Zebra.
- Carrito, checkout y reserva de inventario.
- Pagos online por adaptador.
- Portal cliente y tracking.
- Lealtad, consentimientos y notificaciones.
- CMS y analítica consentida.

## Fase 4 — Gestión empresarial

- CRM y pipeline.
- Marketing/redes/Mily Ads.
- Contabilidad, bancos, CxC/CxP.
- Fiscal Honduras mediante módulo configurable y homologable.
- RR.HH., asistencia y nómina si se mantienen dentro del producto.

## Fase 5 — IA y automatización

- RAG de políticas/productos.
- Asistente público y copiloto interno.
- Generación/edición asistida de contenido.
- Forecast de ventas/reposición.
- Workflows y SLA.

## Fase 6 — Certificación productiva

- E2E completos.
- restore test de backup.
- hardening.
- pruebas de carga.
- certificación de impresoras/cajón/etiquetadoras.
- sandbox y certificación de pagos.
- revisión fiscal/contable aplicable.
- instaladores Windows firmados.

## Regla de main

`main` solo recibe cambios mediante PR cuando CI, pruebas, build y gate correspondiente están verdes. Una función parcial debe permanecer claramente marcada como parcial y nunca presentarse como terminada.
