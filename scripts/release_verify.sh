#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "== Shell scripts =="
bash -n start.sh reset.sh scripts/release_verify.sh

echo "== Python scripts =="
python -m py_compile scripts/bootstrap_release.py scripts/audit_vector_consistency.py

echo "== Docker Compose config =="
docker compose config >/dev/null
docker compose config --services

echo "== Tracked runtime/secrets audit =="
tracked_runtime="$(
  git ls-files \
    | grep -E '(^|/)(\.env($|\.)|backups/|frontend/node_modules/|frontend/dist/|__pycache__/|qdrant_storage/|postgres_data/|ollama_storage/|.*\.pyc$|.*\.snapshot$|data/evaluation/|data/repositories/|data/uploads/|data/documents/.+)' \
    | grep -v '^\.env\.production\.example$' \
    | grep -v '^data/documents/\.gitkeep$' \
    || true
)"
if [[ -n "${tracked_runtime}" ]]; then
  echo "Tracked runtime or secret-like files found:" >&2
  echo "${tracked_runtime}" >&2
  exit 1
fi

echo "== Backend tests =="
python -m pytest tests

echo "== Frontend build =="
(
  cd frontend
  npm run build
)

if docker compose ps --services --filter status=running | grep -q '^api$'; then
  echo "== Live Alembic/current and vector consistency =="
  docker compose exec -T api alembic current
  docker compose exec -T api python - --fail-on-inconsistency < scripts/audit_vector_consistency.py
else
  echo "== Live checks skipped: api service is not running =="
fi

echo "== Git whitespace check =="
git diff --check

echo "Release verification completed."
