# Release Guide

Company Knowledge Base is a retrieval/context service. It owns ingestion,
retrieval, ACL, metadata, source inspection, REST APIs, and vendor-neutral MCP.
Codex, Claude Code, and other MCP clients remain external reasoning/generation
agents.

## Architecture

```text
Codex --------\
               \
                Standard Streamable HTTP MCP
               /
Claude Code --/
        |
        v
Company Knowledge Base
  - ingestion
  - retrieval
  - ACL
  - metadata
  - source inspection
  - REST API
  - MCP
        |
        v
PostgreSQL + Qdrant
```

Default services:

- `postgres`
- `qdrant`
- `api`
- `mcp`
- `frontend`

Ollama is optional and is not started by the default stack.

## Prerequisites

- Docker Engine with Docker Compose v2
- Internet access for first image build and first embedding model download
- Git, only if using Git repository ingestion
- Supported CPU targets: `linux/amd64` and `linux/arm64`

The backend Docker image uses Python 3.11 because the current PyTorch CPU and
tree-sitter parser wheel set resolves cleanly for both supported CPU targets.

## One-Command Startup

Recommended first run:

```bash
./start.sh
```

`start.sh` creates `.env` with mode `600` if missing, generates local secrets,
starts Docker Compose, waits for API readiness, and creates:

- bootstrap admin user
- MCP service account user
- MCP bearer token hash

The equivalent steady-state command after `.env` exists is:

```bash
docker compose up -d --build
```

## First Login

After `./start.sh` finishes, it prints:

- frontend URL
- API URL
- MCP URL
- admin email and generated password
- raw MCP bearer token

Do not commit `.env` or copied secrets.

## Ingestion

Documents:

- Single upload supports Markdown, PDF, DOCX, XLSX, and PPTX.
- Folder upload supports recursive Markdown/PDF/Office files and preserves relative
  paths such as `HR/leave.md`.
- Mixed folders can include Markdown, PDF, DOCX, XLSX, and PPTX together; one
  malformed document must not stop the rest of the folder.
- Unsupported, hidden/system, generated/cache, binary, and oversized files are
  skipped with per-file reasons where applicable.

Code:

- Git repository ingestion clones a repository URL and stores source metadata as
  `GIT_REPOSITORY`.
- Code folder upload stores source metadata as `LOCAL_FOLDER`.
- Relative paths such as `src/app.py` and `include/common.hpp` are preserved.
- Supported languages are the current Code RAG parser extensions:
  `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.java`, `.go`, `.rs`, `.c`, `.h`,
  `.cpp`, `.hpp`, `.php`.
- Unsupported, binary, generated/cache, vendor, and oversized files are skipped
  without failing the whole folder when possible.

All successful documents and code sources receive the existing uploader ACL.

## Knowledge Explorer

The frontend includes a Knowledge Explorer page with:

- search modes: All, Documents, Code
- top-k filter
- document/code filters
- language filter for code
- relevance scores
- matched text/code previews
- source inspection with surrounding context

Search and preview results always use existing ACL filtering.

## MCP Configuration

The MCP endpoint is Streamable HTTP:

```text
http://<host>:8001/mcp
```

Authentication is vendor-neutral bearer token auth:

```text
Authorization: Bearer <raw-mcp-service-token>
```

Tools:

- `search_knowledge`
- `search_code`
- `get_document`
- `ask_knowledge`

`ask_knowledge` is backward-compatible. In the default no-Ollama stack it
returns a clear message that internal generation is not configured.

Grant the MCP service account normal document/repository ACL rows before
expecting search hits.

## Codex Setup

```bash
export COMPANY_KB_MCP_TOKEN="<raw-mcp-service-token>"
codex mcp add company_knowledge_base \
  --url http://<host>:8001/mcp \
  --bearer-token-env-var COMPANY_KB_MCP_TOKEN
codex mcp list
```

Codex can use the same Streamable HTTP endpoint without any server-side
Codex-specific behavior.

## Claude Code Setup

Configure Claude Code with the same Streamable HTTP URL and bearer token. The
server does not branch on client identity.

Use:

- URL: `http://<host>:8001/mcp`
- auth header: `Authorization: Bearer <raw-mcp-service-token>`
- tools: `search_knowledge`, `search_code`, `get_document`

If the local `claude`/`claude-code` CLI is unavailable, validate compatibility
with a standard Streamable HTTP MCP client and then configure Claude Code on a
machine where the CLI is installed and authenticated.

## Backup And Restore

Back up all three state layers at the same logical point in time:

- PostgreSQL volume/database dump
- Qdrant snapshot
- `kb_data` stored uploads/repository clones

PostgreSQL dump example:

```bash
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backups/postgres.dump
```

Qdrant snapshots can be created through Qdrant's snapshot API or with the
consistency/audit runbook used for production cleanup.

Before restore, stop API/MCP/frontend so no writes occur:

```bash
docker compose stop api mcp frontend
```

Restore PostgreSQL, Qdrant, and `kb_data` together, then run:

```bash
docker compose up -d
docker compose exec -T api python scripts/audit_vector_consistency.py --fail-on-inconsistency
```

## Updates

Recommended update flow:

```bash
git pull
docker compose up -d --build
docker compose exec -T api alembic current
docker compose exec -T api python scripts/audit_vector_consistency.py --fail-on-inconsistency
```

The API container runs `alembic upgrade head` before serving.

## Shutdown And Reset

Clean shutdown, preserving data:

```bash
docker compose down
```

Restart:

```bash
docker compose up -d
```

Explicit destructive reset:

```bash
./reset.sh --yes-delete-all-data
```

The reset script removes containers and named volumes for the current Compose
project. It will not run without the exact confirmation flag.

## Optional Ollama

Ollama is optional internal answer generation only. It is not required for:

- ingestion
- embeddings
- Qdrant retrieval
- hybrid/BM25 retrieval
- reranker
- ACL
- Knowledge Explorer
- MCP retrieval tools

Enable only when needed:

```bash
INSTALL_OLLAMA_CLIENT=true INTERNAL_GENERATION_ENABLED=true \
  docker compose --profile ollama up -d --build
docker compose exec ollama ollama pull llama3.1:8b
```

## Troubleshooting

- API unhealthy: inspect `docker compose logs api`; Alembic or dependency
  readiness failures are logged server-side.
- Frontend unreachable: check `docker compose ps frontend` and verify port
  `FRONTEND_PORT`.
- Empty search results: verify the ingesting user or MCP service account has
  ACL permissions.
- MCP 401: verify the raw bearer token matches `MCP_SERVICE_TOKEN_SHA256`.
- Duplicate Git revision: if already indexed successfully, use the existing
  repository record; failed/incomplete records should be reindexed/recovered.
- Consistency drift: run the vector audit command below before cleanup.

## Consistency Audit

Read-only audit:

```bash
docker compose exec -T api python scripts/audit_vector_consistency.py --fail-on-inconsistency
```

Delete only confirmed orphan Qdrant points:

```bash
docker compose exec -T api python scripts/audit_vector_consistency.py --delete-orphans --fail-on-inconsistency
```

PostgreSQL metadata is the source of truth. The cleanup command never deletes
document or repository metadata.

## Release Verification

Run the release checklist before tagging a release:

```bash
scripts/release_verify.sh
```

The checklist covers Docker Compose validation, Alembic visibility, backend
tests, frontend build, consistency audit when the stack is running, and common
secret/runtime-data checks.
