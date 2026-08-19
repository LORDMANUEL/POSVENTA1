# Política de versiones — Mily Zebra Commerce OS

## Estado de las líneas

- `main`: línea protegida de producción. Solo se etiqueta como estable cuando el commit promovido tiene todos los gates requeridos en verde.
- `stabilize/*`: correcciones de una candidata antes de promoverla a `main`; no admite funciones nuevas mientras exista un bloqueador de estabilidad.
- `beta`: candidata a la siguiente estable después de ciclos alpha aprobados.
- `alpha`: desarrollo integrado de funciones nuevas, correcciones y experimentos.

El nombre de una rama no sustituye evidencia. Un commit en `main` sin tag estable y sin gates completos sigue siendo únicamente la base publicada del repositorio.

## Baseline histórica

`0.12.0-rc1` fue la base piloto que llegó a `main`. La primera versión que puede denominarse **estable real** en esta política es `v0.12.1`, únicamente después de aprobar el hardening transaccional, la actualización desde `main`, CI, Stable Gate, PWA/offline, backup→restore y los builds Windows sobre el mismo SHA.

Esto elimina la contradicción anterior que describía `v0.12.0` como estable mientras `VERSION` todavía decía `0.12.0-rc1`.

## Cadencia después de v0.12.1

Una vez publicada `v0.12.1`:

- **5 alphas aprobadas = 1 beta.**
- **3 betas aprobadas = 1 estable.**
- Una estable normal representa como mínimo **15 ciclos alpha** desde la estable anterior.

Ejemplo:

- `v0.13.0-alpha.1` … `v0.13.0-alpha.5` → `v0.13.0-beta.1`
- `v0.13.0-alpha.6` … `v0.13.0-alpha.10` → `v0.13.0-beta.2`
- `v0.13.0-alpha.11` … `v0.13.0-alpha.15` → `v0.13.0-beta.3`
- tres betas aprobadas → `v0.13.0`

Un alpha o beta rechazado no cuenta para promoción hasta corregirse y volver a pasar sus gates.

## Gates por nivel

### Alpha

Debe pasar backend install, Ruff, Pytest, migraciones PostgreSQL, pruebas frontend, build React, contrato/build Windows, Compose, smoke y backup→restore.

### Beta

Añade E2E, regresión acumulada, actualización desde la estable anterior, revisión de migraciones, seguridad/permisos, pruebas PostgreSQL de integridad y artefactos Windows verificables.

### Stable

Exige:

- tres betas aprobadas en el ciclo normal, salvo un hotfix/estabilización explícita como `v0.12.1`;
- cero bloqueadores críticos/altos conocidos del núcleo habilitado;
- CI y Stable Gate completos sobre el mismo SHA;
- instalación limpia;
- actualización real desde la versión/base anterior;
- pruebas PostgreSQL de concurrencia e invariantes;
- aislamiento multi-tenant;
- bootstrap seguro;
- PWA/offline durable e idempotente;
- backup → destrucción → restore final;
- documentación/versionado coherentes;
- artefactos Windows verificables.

Hardware, pagos, fiscal, audio/kiosco y otros componentes externos solo se marcan certificados cuando existe evidencia externa real. El código de soporte puede estar presente y permanecer `fail-closed`.

## Concurrencia de CI

El CI rápido puede usar `cancel-in-progress: true` para no desperdiciar runners en commits obsoletos.

El **Stable Gate usa `cancel-in-progress: false`**: una candidata de release debe terminar su certificación y producir una evidencia completa. Durante ese run la rama se congela; solo se crea otro commit para corregir un fallo reproducible.

## Flujo

```text
feature/* -> alpha -> beta -> main
                     ↑
stabilize/* ----------┘  (solo hardening/hotfix aprobado)
```

Hotfixes salen de `main`, se validan y después se sincronizan hacia las ramas futuras.

## Regla de oro

**El nombre de una versión nunca sustituye evidencia.**
