#!/usr/bin/env bash
set -euo pipefail

BACKUP_PATH="${1:-}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required." >&2
  exit 1
fi

if [[ -z "${BACKUP_PATH}" || ! -f "${BACKUP_PATH}" ]]; then
  echo "Usage: DATABASE_URL=... scripts/restore_postgres.sh <backup.dump>" >&2
  exit 1
fi

pg_restore \
  --dbname="${DATABASE_URL}" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  "${BACKUP_PATH}"

echo "PostgreSQL restore completed from: ${BACKUP_PATH}"
