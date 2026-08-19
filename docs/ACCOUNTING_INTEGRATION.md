# Integración contable automática — v0.12.1

Mily Zebra mantiene el principio de partida doble: una operación comercial solo genera contabilidad automática cuando la contrapartida es inequívoca y el módulo `accounting` está habilitado.

## Cuentas de sistema

El runtime crea de forma idempotente, por tenant, las cuentas reservadas que necesita. Si un código reservado ya existe con un tipo incompatible o está inactivo, la operación se bloquea con `409` en lugar de contabilizar en una cuenta incorrecta.

| Código | Cuenta | Tipo |
|---|---|---|
| 1100 | Caja | Activo |
| 1110 | Pagos por acreditar | Activo |
| 1200 | Cuentas por cobrar | Activo |
| 1300 | Inventario | Activo |
| 2000 | Cuentas por pagar | Pasivo |
| 4000 | Ventas | Ingreso |
| 4010 | Devoluciones sobre ventas | Ingreso/contraingreso |
| 5000 | Costo de ventas | Gasto |

## Venta POS

Venta en efectivo:

```text
Dr 1100 Caja                 precio de venta
    Cr 4000 Ventas           precio de venta
Dr 5000 Costo de ventas      costo registrado del producto
    Cr 1300 Inventario       costo registrado del producto
```

Para medios no efectivos, `1110 Pagos por acreditar` sustituye a Caja hasta que exista una integración bancaria/adquirente que permita identificar la cuenta definitiva.

El asiento usa referencia determinística `SALE:<sale_id>`. Un reintento idempotente de la venta no duplica el asiento.

## Recepción de compra

```text
Dr 1300 Inventario           cantidad × costo de la orden
    Cr 2000 Cuentas por pagar
```

Referencia contable: `PURCHASE:<purchase_id>`.

Cuando `payables` está habilitado se crea además, en la misma transacción, una cuenta por pagar con referencia `PO:<purchase_id>`. Una segunda recepción del mismo documento no duplica inventario, asiento ni CxP.

## Devolución de cliente

Para una venta originalmente cobrada en efectivo:

```text
Dr 4010 Devoluciones sobre ventas   importe devuelto
    Cr 1100 Caja                    importe devuelto
Dr 1300 Inventario                  costo reingresado
    Cr 5000 Costo de ventas         reversa del costo
```

En reembolsos externos se utiliza `1110 Pagos por acreditar` mientras el proveedor externo permanezca pendiente/no certificado.

Referencia contable: `RETURN:<return_id>`.

La devolución, el reingreso de inventario, el reembolso/ledger de caja y el asiento forman parte de la misma transacción lógica.

## Ecommerce

Al confirmar un pago:

```text
Dr 1110 Pagos por acreditar   total confirmado
    Cr 4000 Ventas            total confirmado
```

Para `cash_on_delivery` confirmado como cobrado se usa Caja. Referencia: `ORDER-REVENUE:<order_id>`.

Al cumplir el pedido y consumir la reserva:

```text
Dr 5000 Costo de ventas       costo de productos
    Cr 1300 Inventario        costo de productos
```

Referencia: `ORDER-COGS:<order_id>`.

Separar ambos hechos evita reconocer costo antes de que el inventario realmente salga y evita reconocer ingreso de una transferencia manual antes de que un operador confirme el pago.

## Operaciones manuales que NO se auto-contabilizan

Crear manualmente una CxC o CxP no produce por sí solo un asiento automático. Esa API recibe monto, parte y referencia, pero no especifica la cuenta origen de ingreso, gasto, activo o pasivo. Elegirla automáticamente sería inventar criterio contable.

Para esos casos el operador utiliza el módulo de asientos o un flujo futuro que provea explícitamente la cuenta de contrapartida.

## Garantías

- Asientos balanceados antes de persistir.
- Referencias determinísticas por operación.
- Unicidad por tenant + referencia.
- Cuentas reservadas validadas por tipo.
- Auditoría `journal.auto_posted`.
- Contabilidad en la misma transacción que el hecho comercial.
- Si contabilidad falla, no se confirma silenciosamente la operación comercial.
- Los módulos externos/fiscales permanecen fail-closed hasta certificación real.
