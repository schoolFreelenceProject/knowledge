# Production Deployment

This deployment keeps the Knowledge Base retrieval architecture unchanged:

```text
Browser
 -> FastAPI
 -> Auth / ACL / Retrieval services
 -> PostgreSQL metadata
 -> Qdrant vectors

Codex / Claude Code / MCP Client
 -> MCP service
 -> existing Auth / ACL / Retrieval services
 -> PostgreSQL metadata
 -> Qdrant vectors
```

The default Docker stack starts `postgres`, `qdrant`, `api`, `mcp`, and
`frontend`. Ollama is optional internal answer generation, not a required
production dependency.

## Environment

For a first local release deployment, prefer:

```bash
./start.sh
```

It generates local secrets, starts the default Compose stack, waits for
readiness, and bootstraps the admin and MCP service users.

For a production environment file, start from the template:

```bash
cp .env.production.example .env.production
```

Update all secrets before starting production:

- `JWT_SECRET_KEY`: at least 32 random characters.
- `POSTGRES_PASSWORD`: long random password.
- `DATABASE_URL`: must match the Postgres credentials.
- `CODE_REPOSITORY_ALLOWED_HOSTS`: explicit comma-separated Git hosts.
- `MCP_SERVICE_ACCOUNT_EMAIL`: existing active KB user for MCP access.
- `MCP_SERVICE_TOKEN_SHA256`: SHA-256 digest of the MCP bearer token.
- `MCP_PUBLIC_URL`: externally reachable MCP URL, for example
  `https://kb.example.com/mcp`.

Production startup validates:

- `APP_ENV=production`
- `DATABASE_AUTO_CREATE=false`
- non-default JWT secret
- explicit code repository host allowlist

## Alembic Migrations

Production uses Alembic as the source of truth for schema changes.

Start production after secrets are set:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --build
```

The production API command runs:

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The MCP service is a separate default process:

```bash
python -m app.mcp.server
```

It starts with the default Compose stack. To enable optional Ollama generation,
set `INTERNAL_GENERATION_ENABLED=true`, build with
`INSTALL_OLLAMA_CLIENT=true`, and start the `ollama` profile.

For an existing database that was created with `create_all()`:

```bash
DATABASE_URL=postgresql+psycopg://... alembic stamp head
```

Only do this after verifying the existing schema matches the baseline migration.

Rollback one migration:

```bash
DATABASE_URL=postgresql+psycopg://... alembic downgrade -1
```

Always take PostgreSQL, Qdrant, and stored file backups before downgrade.

## Health Checks

Endpoints:

- `/health`: shallow liveness for compatibility.
- `/health/live`: liveness.
- `/health/ready`: dependency readiness for PostgreSQL and Qdrant by default.
  Ollama is checked only when `INTERNAL_GENERATION_ENABLED=true`.

Docker Compose includes health checks and restart policies for all default core
services, including the frontend and MCP service.

## Security

The production app adds:

- request size limit
- upload size validation
- security headers
- process-local rate limiting
- JWT secret validation
- password policy on registration
- code repository host allowlist
- audit logs for auth, ingestion, document management, and ACL changes

Put the API behind a reverse proxy such as nginx or a managed load balancer.
Terminate HTTPS at the proxy and forward `X-Forwarded-For` so rate limiting can
use the original client IP.

## Scaling Notes

- Run API replicas only after moving rate limiting to a shared store such as Redis.
- Keep Qdrant collection vector size tied to the embedding model.
- Run benchmark scripts before enabling reranker in production, because reranking
adds model latency and memory pressure.
- Use persistent volumes or managed services for PostgreSQL, Qdrant, and `data/`.
  Add Ollama model storage only when optional internal generation is enabled.

See [release.md](release.md) for one-command startup, first-login bootstrap,
MCP client setup, backup/restore, update, shutdown, and release verification.
