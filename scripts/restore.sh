#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: sudo ./scripts/restore.sh backups/milyzebra-YYYYMMDDTHHMMSSZ.sql.gz" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
BACKUP="$1"

if [[ ! -f "$BACKUP" ]]; then
  echo "Backup no encontrado: $BACKUP" >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo ".env no existe" >&2
  exit 1
fi
if [[ -f "$BACKUP.sha256" ]]; then
  sha256sum -c "$BACKUP.sha256"
fi

set -a
source .env
set +a

if [[ "${MZ_RESTORE_CONFIRM:-}" != "RESTORE_${POSTGRES_DB}" ]]; then
  echo "Restauración bloqueada para evitar borrado accidental." >&2
  echo "Ejecute: MZ_RESTORE_CONFIRM=RESTORE_${POSTGRES_DB} sudo -E ./scripts/restore.sh '$BACKUP'" >&2
  exit 3
fi

echo "Deteniendo API/web durante la restauración..."
docker compose stop api web

echo "Recreando base de datos $POSTGRES_DB..."
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${POSTGRES_DB}";
CREATE DATABASE "${POSTGRES_DB}" OWNER "${POSTGRES_USER}";
SQL

gzip -dc "$BACKUP" | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1

docker compose up -d api web

echo "Restauración completada. Ejecute ./scripts/verify.sh"
