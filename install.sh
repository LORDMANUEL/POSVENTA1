#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

DOMAIN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      DOMAIN="${2:-}"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Uso:
  sudo ./install.sh
  sudo ./install.sh --domain tienda.ejemplo.com

Sin dominio: publica Mily Zebra por HTTP en el puerto 80.
Con dominio apuntando al VPS: Caddy solicita y renueva TLS automáticamente.
EOF
      exit 0
      ;;
    *)
      echo "Argumento no reconocido: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecute como root: sudo ./install.sh [--domain dominio]" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "El instalador soporta Debian/Ubuntu. Para otras distribuciones use Docker Compose manualmente." >&2
  exit 1
fi

if [[ -n "$DOMAIN" && ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "Dominio inválido: $DOMAIN" >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl openssl git

if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y docker.io docker-compose-v2
  systemctl enable --now docker
fi
if ! docker compose version >/dev/null 2>&1; then
  apt-get install -y docker-compose-v2
fi

# Redis recomienda memory overcommit para evitar fallos de persistencia bajo presión.
printf 'vm.overcommit_memory=1\n' > /etc/sysctl.d/99-mily-zebra.conf
sysctl -w vm.overcommit_memory=1 >/dev/null || true

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

# Nunca permita arrancar producción con secretos de ejemplo. Si siguen presentes,
# se reemplazan sin alterar secretos ya configurados por el operador.
if grep -q 'POSTGRES_PASSWORD=change-this-in-production' .env; then
  DB_PASSWORD="$(openssl rand -hex 24)"
  sed -i "s|^POSTGRES_PASSWORD=change-this-in-production|POSTGRES_PASSWORD=${DB_PASSWORD}|" .env
  sed -i "s|change-this-in-production|${DB_PASSWORD}|g" .env
fi
if grep -q 'JWT_SECRET=change-this-to-a-long-random-secret' .env; then
  JWT_SECRET_VALUE="$(openssl rand -hex 48)"
  sed -i "s|^JWT_SECRET=change-this-to-a-long-random-secret|JWT_SECRET=${JWT_SECRET_VALUE}|" .env
fi

if grep -Eq 'change-this-in-production|change-this-to-a-long-random-secret' .env; then
  echo "Quedaron secretos de ejemplo dentro de .env; instalación bloqueada." >&2
  exit 3
fi

if [[ -n "$DOMAIN" ]]; then
  if grep -q '^MZ_SITE_ADDRESS=' .env; then
    sed -i "s|^MZ_SITE_ADDRESS=.*|MZ_SITE_ADDRESS=${DOMAIN}|" .env
  else
    echo "MZ_SITE_ADDRESS=${DOMAIN}" >> .env
  fi
  if grep -q '^CORS_ORIGINS=' .env; then
    sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=https://${DOMAIN}|" .env
  fi
else
  if grep -q '^MZ_SITE_ADDRESS=' .env; then
    sed -i 's|^MZ_SITE_ADDRESS=.*|MZ_SITE_ADDRESS=:80|' .env
  fi
fi

mkdir -p backups
chmod 700 backups
chmod 600 .env

docker compose config >/dev/null
docker compose pull db redis proxy
docker compose build --pull
docker compose up -d

echo "Verificando servicios..."
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS http://127.0.0.1:8000/health >/dev/null || {
  docker compose ps
  docker compose logs --tail=200 api db redis worker
  echo "La API no pasó el health check." >&2
  exit 1
}

docker compose exec -T db pg_isready -U "$(grep '^POSTGRES_USER=' .env | cut -d= -f2-)" -d "$(grep '^POSTGRES_DB=' .env | cut -d= -f2-)" >/dev/null
docker compose exec -T redis redis-cli ping | grep -q PONG
docker compose exec -T api alembic current | grep -q 20260819_0010
curl -fsS http://127.0.0.1:8080/ >/dev/null

if [[ -n "$DOMAIN" ]]; then
  echo "Mily Zebra instalado: https://${DOMAIN}"
else
  IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "Mily Zebra instalado: http://${IP:-IP-DEL-VPS}"
fi

echo "Abra /admin y use 'Primera instalación' para crear el propietario inicial."
echo "Backup completo (BD + fotos): sudo ./scripts/backup.sh"
echo "Restore completo: consulte docs/MANUAL_INSTALACION.md"
echo "Estado: docker compose ps"
