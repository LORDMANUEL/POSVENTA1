#!/usr/bin/env bash
set -euo pipefail

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

if [[ ! -f .env ]]; then
  cp .env.example .env
  DB_PASSWORD="$(openssl rand -hex 24)"
  JWT_SECRET="$(openssl rand -hex 48)"
  sed -i "s/change-this-in-production/${DB_PASSWORD}/g" .env
  sed -i "s/change-this-to-a-long-random-secret/${JWT_SECRET}/g" .env
fi

if [[ -n "$DOMAIN" ]]; then
  if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then
    echo "Dominio inválido: $DOMAIN" >&2
    exit 2
  fi
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
  docker compose logs --tail=150 api
  echo "La API no pasó el health check." >&2
  exit 1
}

if [[ -n "$DOMAIN" ]]; then
  echo "Mily Zebra instalado: https://${DOMAIN}"
else
  IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "Mily Zebra instalado: http://${IP:-IP-DEL-VPS}"
fi

echo "Abra /admin y use 'Primera instalación' para crear el propietario inicial."
echo "Backup: sudo ./scripts/backup.sh"
echo "Estado: docker compose ps"
