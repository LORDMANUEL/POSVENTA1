# Política de versiones — Mily Zebra Commerce OS

## Líneas oficiales

- `main`: **estable**. Solo recibe promociones desde `beta` después de completar tres betas aprobadas.
- `beta`: **candidata a estable**. Recibe una promoción después de completar cinco alphas aprobadas.
- `alpha`: **desarrollo integrado**. Aquí se incorporan nuevas funciones, correcciones y experimentos antes de promoverlos.

`main` no se usa para desarrollo normal.

## Cadencia obligatoria

- **5 alphas aprobadas = 1 beta.**
- **3 betas aprobadas = 1 estable.**
- Una estable representa como mínimo **15 ciclos alpha** desde la estable anterior.

Tomando `v0.12.0` como estable inicial:

- `v0.13.0-alpha.1` … `v0.13.0-alpha.5` → `v0.13.0-beta.1`
- `v0.13.0-alpha.6` … `v0.13.0-alpha.10` → `v0.13.0-beta.2`
- `v0.13.0-alpha.11` … `v0.13.0-alpha.15` → `v0.13.0-beta.3`
- tres betas aprobadas → `v0.13.0` estable

Un alpha o beta rechazado no cuenta para promoción hasta corregirse y volver a pasar sus gates.

## Gates

Cada alpha debe pasar backend install, Ruff, pytest, migraciones PostgreSQL, pruebas de lógica frontend, build frontend, contrato y build Windows, Compose, smoke completo y backup→restore.

Cada beta añade E2E, regresión acumulada, instalación/actualización desde la estable anterior, revisión de migraciones, seguridad/permisos y artefactos Windows verificables.

Cada estable exige tres betas aprobadas, cero bloqueadores críticos/altos conocidos, backup/restore final, documentación actualizada e instalación limpia validada. Hardware, pagos y fiscal solo se marcan certificados con evidencia externa real.

## Flujo

```text
feature/* -> alpha -> beta -> main
```

Hotfixes salen de `main`, se validan y luego se sincronizan hacia `beta` y `alpha`.

El nombre de una versión nunca sustituye evidencia.