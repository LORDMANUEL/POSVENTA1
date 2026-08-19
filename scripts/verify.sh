#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "FAIL: .env no existe" >&2
  exit 1
fi

cp /dev/null /tmp/mz-verify-errors

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '[OK] %s\n' "$name"
  else
    printf '[FAIL] %s\n' "$name" | tee -a /tmp/mz-verify-errors
  fi
}

check "Docker Compose válido" docker compose config
check "PostgreSQL saludable" docker compose exec -T db pg_isready
check "Redis saludable" docker compose exec -T redis redis-cli ping
check "API health" curl -fsS http://127.0.0.1:8000/health
check "Web responde" curl -fsS http://127.0.0.1:8080/

if [[ -s /tmp/mz-verify-errors ]]; then
  echo "Verificación fallida."
  exit 1
fi

echo "Verificación base aprobada. Esto no sustituye E2E, restore test ni certificación de hardware."
