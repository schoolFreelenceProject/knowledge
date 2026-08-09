#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-backups/postgres}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_PATH="${1:-${BACKUP_DIR}/company_rag_${TIMESTAMP}.dump}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required." >&2
  exit 1
fi

mkdir -p "$(dirname "${OUTPUT_PATH}")"
pg_dump "${DATABASE_URL}" --format=custom --no-owner --no-privileges --file="${OUTPUT_PATH}"

echo "PostgreSQL backup written to: ${OUTPUT_PATH}"
