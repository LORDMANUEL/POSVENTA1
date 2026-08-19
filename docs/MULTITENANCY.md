# Multiempresa y multitenancy — Mily Zebra Commerce OS

## Contrato

Mily Zebra utiliza una sola aplicación, API y despliegue para múltiples empresas, pero cada operación comercial conserva `tenant_id` como frontera obligatoria. El operador de plataforma puede crear empresas; los propietarios y usuarios normales administran únicamente los datos de su tenant.

El privilegio global no convierte al usuario en superusuario de datos comerciales. `PlatformOperator` habilita exclusivamente la superficie `/platform/*`. POS, inventario, caja, clientes, compras, finanzas, media y demás módulos continúan aplicando filtros de tenant y sucursal.

## Primera empresa

La primera instalación crea la primera empresa con `/bootstrap`, protegido por `MZ_BOOTSTRAP_TOKEN`. El primer owner activo actúa como operador de plataforma inicial. Cuando crea el segundo tenant, ese privilegio queda persistido en `platform_operators`.

## Crear una empresa desde la interfaz

1. Ingrese con el owner de plataforma.
2. Abra **Usuarios y dispositivos**.
3. En **Empresas / tenants**, indique:
   - nombre de la empresa;
   - slug único;
   - sucursal inicial y código;
   - correo y nombre del propietario;
   - contraseña inicial.
4. El servidor crea tenant, sucursal y owner en una sola transacción.
5. La interfaz devuelve la ruta de acceso, por ejemplo:

```text
/admin?tenant=mily-zebra-sps
```

La misma PWA y `MilyZebra.exe` sirven a todas las empresas; no se duplica lógica ni base de datos.

## Login

Cuando la URL incluye `?tenant=<slug>`, la PWA autentica como:

```text
<slug>:<correo>
```

Esto permite que un mismo correo exista en dos empresas sin elegir un usuario de otro tenant por accidente. Si un correo ambiguo se usa sin slug, el backend exige seleccionar la tienda en vez de resolver arbitrariamente una cuenta.

## API de plataforma

```text
GET  /platform/access
GET  /platform/tenants
POST /platform/tenants
```

`GET /platform/access` puede consultarlo cualquier usuario autenticado y responde únicamente si tiene privilegio de plataforma. Listar o crear tenants exige ser operador de plataforma.

## Aislamiento obligatorio

Una credencial de tenant B no puede usar identificadores conocidos de tenant A para:

- mover inventario;
- operar una caja;
- crear compras o transferencias;
- consultar finanzas;
- enrolar hardware;
- leer o modificar postventa;
- acceder a recursos de administración del otro tenant.

Los endpoints que aceptan `branch_id` validan que la sucursal pertenezca al tenant autenticado. Los JWT incluyen `tenant_id` y el backend comprueba que coincida con el usuario persistido.

## Actualización desde v0.12.0

La migración `20260819_0010` crea `platform_operators` cuando no existe. Si la base anterior ya contiene usuarios, promueve al usuario más antiguo de la instalación original como operador de plataforma. Stable Gate construye una base real con `main`, crea un owner, ejecuta la migración de la candidata y comprueba que ese owner conserva la administración de plataforma.

## Recuperación

`platform_operators` forma parte de PostgreSQL y por tanto del backup completo. No se mantiene una lista de administradores globales en el navegador ni en un archivo separado.

Si se pierde todo acceso de plataforma, la recuperación debe tratarse como una operación administrativa auditada sobre la base de datos; no debe habilitarse un endpoint público de emergencia que pueda saltarse la autenticación.
