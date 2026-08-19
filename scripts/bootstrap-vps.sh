#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${MZ_REPO_URL:-https://github.com/LORDMANUEL/POSVENTA1.git}"
REF="${MZ_REF:-main}"
TARGET="${MZ_INSTALL_DIR:-/opt/mily-zebra}"
DOMAIN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      DOMAIN="${2:-}"
      shift 2
      ;;
    --ref)
      REF="${2:-main}"
      shift 2
      ;;
    *)
      echo "Argumento no reconocido: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecute como root." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git ca-certificates curl

if [[ -d "$TARGET/.git" ]]; then
  git -C "$TARGET" fetch --all --tags --prune
  git -C "$TARGET" checkout "$REF"
  git -C "$TARGET" pull --ff-only
else
  rm -rf "$TARGET"
  git clone --branch "$REF" --depth 1 "$REPO_URL" "$TARGET"
fi

chmod +x "$TARGET/install.sh"
if [[ -n "$DOMAIN" ]]; then
  exec "$TARGET/install.sh" --domain "$DOMAIN"
fi
exec "$TARGET/install.sh"
