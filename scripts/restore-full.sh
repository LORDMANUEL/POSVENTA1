#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: MZ_RESTORE_CONFIRM=RESTORE_<DB> sudo -E ./scripts/restore-full.sh backups/milyzebra-full-*.tar.gz" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PACKAGE="$1"

[[ -f "$PACKAGE" ]] || { echo "Backup no encontrado: $PACKAGE" >&2; exit 1; }
[[ -f .env ]] || { echo ".env no existe" >&2; exit 1; }
if [[ -f "$PACKAGE.sha256" ]]; then
  sha256sum -c "$PACKAGE.sha256"
fi

set -a
source .env
set +a

if [[ "${MZ_RESTORE_CONFIRM:-}" != "RESTORE_${POSTGRES_DB}" ]]; then
  echo "Restauración bloqueada para evitar borrado accidental." >&2
  echo "Use MZ_RESTORE_CONFIRM=RESTORE_${POSTGRES_DB}" >&2
  exit 3
fi

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

tar -xzf "$PACKAGE" -C "$WORK"
for required in database.dump media.tar.gz manifest.env SHA256SUMS; do
  [[ -f "$WORK/$required" ]] || { echo "Backup incompleto: falta $required" >&2; exit 4; }
done
(
  cd "$WORK"
  sha256sum -c SHA256SUMS
)
# shellcheck disable=SC1090
source "$WORK/manifest.env"
if [[ "${MZ_BACKUP_FORMAT:-}" != "2" ]]; then
  echo "Formato de backup no soportado" >&2
  exit 4
fi
if [[ "${POSTGRES_DB:-}" != "$(grep '^POSTGRES_DB=' .env | cut -d= -f2-)" ]]; then
  echo "El backup corresponde a otra base de datos" >&2
  exit 4
fi

echo "Deteniendo servicios que escriben datos..."
docker compose stop worker api web

echo "Recreando PostgreSQL..."
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${POSTGRES_DB}";
CREATE DATABASE "${POSTGRES_DB}" OWNER "${POSTGRES_USER}";
SQL

docker compose exec -T db pg_restore \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --no-owner \
  --no-privileges \
  --exit-on-error < "$WORK/database.dump"

echo "Restaurando media persistente..."
cat "$WORK/media.tar.gz" | docker compose run --rm --no-deps -T --entrypoint sh api -c 'rm -rf /data/media/* /data/media/.[!.]* /data/media/..?* 2>/dev/null || true; mkdir -p /data/media; tar -xzf - -C /data/media'

docker compose up -d api worker web

echo "Verificando migración y salud..."
docker compose exec -T api alembic current
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "Restauración completa verificada."
    exit 0
  fi
  sleep 2
done

echo "La restauración terminó pero la API no respondió al healthcheck" >&2
exit 5
