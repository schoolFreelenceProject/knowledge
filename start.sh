#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${KB_ENV_FILE:-.env}"
GENERATED_ENV="false"

random_alnum() {
  local length="${1:-48}"
  local value
  set +o pipefail
  value="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${length}")"
  set -o pipefail
  printf '%s' "${value}"
}

random_hex() {
  local bytes="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "${bytes}"
    return
  fi

  local value
  set +o pipefail
  value="$(LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c "$((bytes * 2))")"
  set -o pipefail
  printf '%s' "${value}"
}

sha256_hex() {
  local value="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "${value}" | sha256sum | awk '{print $1}'
    return
  fi

  if command -v shasum >/dev/null 2>&1; then
    printf '%s' "${value}" | shasum -a 256 | awk '{print $1}'
    return
  fi

  python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())' "${value}"
}

get_env_value() {
  local key="$1"
  if [[ ! -f "${ENV_FILE}" ]]; then
    return 0
  fi

  grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true
}

set_env_value() {
  local key="$1"
  local value="$2"
  touch "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"

  if grep -q -E "^${key}=" "${ENV_FILE}"; then
    local tmp
    tmp="$(mktemp)"
    awk -v key="${key}" -v line="${key}=${value}" '
      BEGIN { replaced = 0 }
      $0 ~ "^" key "=" {
        if (!replaced) {
          print line
          replaced = 1
        }
        next
      }
      { print }
      END {
        if (!replaced) {
          print line
        }
      }
    ' "${ENV_FILE}" > "${tmp}"
    mv "${tmp}" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    return
  fi

  printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
}

ensure_env_value() {
  local key="$1"
  local value="$2"
  if [[ -z "$(get_env_value "${key}")" ]]; then
    set_env_value "${key}" "${value}"
  fi
}

if [[ ! -f "${ENV_FILE}" ]]; then
  umask 077
  touch "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  GENERATED_ENV="true"
fi

ensure_env_value "APP_ENV" "development"
ensure_env_value "API_PORT" "8000"
ensure_env_value "FRONTEND_PORT" "5173"
ensure_env_value "POSTGRES_PORT" "5432"
ensure_env_value "QDRANT_HTTP_PORT" "6333"
ensure_env_value "QDRANT_GRPC_PORT" "6334"
ensure_env_value "POSTGRES_DB" "company_rag"
ensure_env_value "POSTGRES_USER" "rag"
ensure_env_value "POSTGRES_PASSWORD" "$(random_hex 24)"
ensure_env_value "DATABASE_AUTO_CREATE" "false"

POSTGRES_DB="$(get_env_value POSTGRES_DB)"
POSTGRES_USER="$(get_env_value POSTGRES_USER)"
POSTGRES_PASSWORD="$(get_env_value POSTGRES_PASSWORD)"
ensure_env_value \
  "DATABASE_URL" \
  "postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"

ensure_env_value "JWT_SECRET_KEY" "$(random_hex 32)"
ensure_env_value "JWT_ALGORITHM" "HS256"
ensure_env_value "JWT_ACCESS_TOKEN_EXPIRE_MINUTES" "60"

ensure_env_value "QDRANT_URL" "http://qdrant:6333"
ensure_env_value "QDRANT_COLLECTION_NAME" "company_documents"
ensure_env_value "EMBEDDING_MODEL_NAME" "sentence-transformers/all-MiniLM-L6-v2"
ensure_env_value "INTERNAL_GENERATION_ENABLED" "false"
ensure_env_value "OLLAMA_BASE_URL" "http://ollama:11434"
ensure_env_value "OLLAMA_MODEL" "llama3.1:8b"
ensure_env_value "INSTALL_OLLAMA_CLIENT" "false"

ensure_env_value "RETRIEVAL_MODE" "vector"
ensure_env_value "HYBRID_FUSION_STRATEGY" "rrf"
ensure_env_value "HYBRID_VECTOR_WEIGHT" "0.6"
ensure_env_value "HYBRID_BM25_WEIGHT" "0.4"
ensure_env_value "HYBRID_CANDIDATE_MULTIPLIER" "4"
ensure_env_value "BM25_K1" "1.5"
ensure_env_value "BM25_B" "0.75"
ensure_env_value "RERANKER_ENABLED" "false"
ensure_env_value "RERANKER_MODEL_NAME" "cross-encoder/ms-marco-MiniLM-L-6-v2"
ensure_env_value "RERANKER_CANDIDATE_SIZE" "20"
ensure_env_value "RERANKER_BATCH_SIZE" "16"
ensure_env_value "DOCUMENT_CHUNK_SIZE" "1000"
ensure_env_value "DOCUMENT_CHUNK_OVERLAP" "150"
ensure_env_value "MAX_REQUEST_BODY_BYTES" "26214400"
ensure_env_value "MAX_UPLOAD_BYTES" "26214400"
ensure_env_value "SECURITY_HEADERS_ENABLED" "true"
ensure_env_value "RATE_LIMIT_ENABLED" "true"
ensure_env_value "RATE_LIMIT_REQUESTS" "120"
ensure_env_value "RATE_LIMIT_WINDOW_SECONDS" "60"
ensure_env_value "CODE_REPOSITORY_ALLOWED_HOSTS" "*"
ensure_env_value "AUDIT_LOG_ENABLED" "true"
ensure_env_value "LOG_LEVEL" "INFO"

ensure_env_value "MCP_HOST" "0.0.0.0"
ensure_env_value "MCP_PORT" "8001"
ensure_env_value "MCP_HOST_PORT" "8001"
ensure_env_value "MCP_PATH" "/mcp"
ensure_env_value "MCP_PUBLIC_URL" "http://localhost:$(get_env_value MCP_HOST_PORT)/mcp"
ensure_env_value "MCP_SERVICE_ACCOUNT_EMAIL" "mcp-service@example.com"
ensure_env_value "MCP_SERVICE_ACCOUNT_PASSWORD" "Mcp-$(random_alnum 28)-9"

if [[ -z "$(get_env_value MCP_SERVICE_TOKEN)" ]]; then
  set_env_value "MCP_SERVICE_TOKEN" "mcp_$(random_alnum 48)"
fi
set_env_value \
  "MCP_SERVICE_TOKEN_SHA256" \
  "$(sha256_hex "$(get_env_value MCP_SERVICE_TOKEN)")"

ensure_env_value "KB_BOOTSTRAP_ADMIN_EMAIL" "admin@example.com"
ensure_env_value "KB_BOOTSTRAP_ADMIN_PASSWORD" "Admin-$(random_alnum 28)-9"
mkdir -p backups/qdrant

docker compose up -d --build

echo "Waiting for API readiness..."
API_READY="false"
for _ in $(seq 1 90); do
  if docker compose exec -T api python - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("http://localhost:8000/health/ready", timeout=3).read()
PY
  then
    API_READY="true"
    break
  fi
  sleep 2
done

if [[ "${API_READY}" != "true" ]]; then
  echo "API did not become ready in time. Inspect with: docker compose logs api" >&2
  exit 1
fi

docker compose exec -T api python scripts/bootstrap_release.py

cat <<EOF

Company Knowledge Base is running.

Frontend: http://localhost:$(get_env_value FRONTEND_PORT)
API:      http://localhost:$(get_env_value API_PORT)
MCP:      http://localhost:$(get_env_value MCP_HOST_PORT)$(get_env_value MCP_PATH)

First login:
  email:    $(get_env_value KB_BOOTSTRAP_ADMIN_EMAIL)
  password: $(get_env_value KB_BOOTSTRAP_ADMIN_PASSWORD)

MCP bearer token:
  $(get_env_value MCP_SERVICE_TOKEN)

Local secrets are stored in ${ENV_FILE} with mode 600 and should not be committed.
EOF

if [[ "${GENERATED_ENV}" == "true" ]]; then
  echo "Created ${ENV_FILE} with generated local secrets."
fi
