#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--yes-delete-all-data" ]]; then
  cat >&2 <<'EOF'
This command deletes Docker containers and named volumes for the local
Knowledge Base stack.

Usage:
  ./reset.sh --yes-delete-all-data

The normal restart path is:
  docker compose down
  docker compose up -d
EOF
  exit 2
fi

docker compose down -v --remove-orphans
echo "Deleted local Docker containers and named volumes."
