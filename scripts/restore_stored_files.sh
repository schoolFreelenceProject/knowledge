#!/usr/bin/env bash
set -euo pipefail

BACKUP_PATH="${1:-}"
DATA_DIR="${DATA_DIR:-data}"

if [[ -z "${BACKUP_PATH}" || ! -f "${BACKUP_PATH}" ]]; then
  echo "Usage: DATA_DIR=data scripts/restore_stored_files.sh <stored_files.tar.gz>" >&2
  exit 1
fi

mkdir -p "${DATA_DIR}"
tar --extract --gzip --file="${BACKUP_PATH}" --directory="${DATA_DIR}"

echo "Stored files restore completed into: ${DATA_DIR}"
