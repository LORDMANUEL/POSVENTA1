#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecute como root: sudo ./scripts/install.sh" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "Docker no está instalado y este instalador automático solo soporta Debian/Ubuntu." >&2
    exit 1
  fi
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 openssl ca-certificates
  systemctl enable --now docker
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Se requiere Docker Compose v2 (comando: docker compose)." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  DB_PASSWORD="$(openssl rand -hex 24)"
  JWT_SECRET="$(openssl rand -hex 48)"
  sed -i "s/change-this-in-production/${DB_PASSWORD}/g" .env
  sed -i "s/change-this-to-a-long-random-secret/${JWT_SECRET}/g" .env
  echo "Se creó .env con secretos aleatorios. Guárdelo en el backup seguro del servidor."
fi

mkdir -p backups
chmod 700 backups

docker compose pull db redis || true
docker compose build --pull
docker compose up -d

echo "Esperando API..."
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "API saludable."
    break
  fi
  sleep 2
done

curl -fsS http://127.0.0.1:8000/health || {
  docker compose ps
  docker compose logs --tail=100 api
  echo "La API no pasó el health check." >&2
  exit 1
}

docker compose ps
cat <<'EOF'

Mily Zebra quedó levantado.
Web local: http://IP-DEL-VPS:8080
API local: http://127.0.0.1:8000

Siguiente paso: configurar dominio/TLS en el proxy frontal antes de exponer producción a Internet.
En el primer acceso seleccione "Primera instalación" para crear el propietario.
EOF
