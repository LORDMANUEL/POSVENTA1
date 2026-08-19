#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo ".env no existe" >&2
  exit 1
fi

set -a
source .env
set +a

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
PACKAGE="$BACKUP_DIR/milyzebra-full-${STAMP}.tar.gz"
WORK="$(mktemp -d)"

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

echo "Respaldando PostgreSQL..."
docker compose exec -T db pg_dump \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --no-owner \
  --no-privileges \
  --format=custom > "$WORK/database.dump"

echo "Respaldando media persistente..."
docker compose exec -T api sh -c 'tar -C /data/media -czf - .' > "$WORK/media.tar.gz"
ALEMBIC_HEAD="$(docker compose exec -T api alembic current 2>/dev/null | awk 'NF {print $1}' | tail -n 1 | tr -d '\r')"

cat > "$WORK/manifest.env" <<EOF
MZ_BACKUP_FORMAT=2
CREATED_AT=$STAMP
POSTGRES_DB=$POSTGRES_DB
ALEMBIC_HEAD=$ALEMBIC_HEAD
EOF

(
  cd "$WORK"
  sha256sum database.dump media.tar.gz manifest.env > SHA256SUMS
  tar -czf "$PACKAGE" database.dump media.tar.gz manifest.env SHA256SUMS
)
sha256sum "$PACKAGE" > "$PACKAGE.sha256"
chmod 600 "$PACKAGE" "$PACKAGE.sha256"
echo "$PACKAGE"
