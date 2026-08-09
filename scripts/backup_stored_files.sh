#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-data}"
BACKUP_DIR="${BACKUP_DIR:-backups/files}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_PATH="${1:-${BACKUP_DIR}/stored_files_${TIMESTAMP}.tar.gz}"

mkdir -p "$(dirname "${OUTPUT_PATH}")"

tar \
  --create \
  --gzip \
  --file="${OUTPUT_PATH}" \
  --directory="${DATA_DIR}" \
  documents \
  repositories

echo "Stored files backup written to: ${OUTPUT_PATH}"
