# MCP Server

The MCP layer exposes the Company Knowledge Base to Hermes as read-only tools.
The Knowledge Base remains a standalone backend and service; Hermes remains the
agent layer.

## Architecture

```text
Hermes Agent
 -> MCP streamable HTTP
 -> Company Knowledge Base MCP Server
 -> existing KB service layer
 -> PermissionService
 -> RetrievalService
 -> RAGChatService / RAGGenerationService
 -> PostgreSQL
 -> Qdrant
 -> Ollama
```

The MCP server reuses the existing service layer. It does not duplicate RAG,
ACL, PostgreSQL, Qdrant, reranker, generation, trace, feedback, evaluation, or
analytics logic.

`app.api.dependencies.get_knowledge_tool_service()` composes the MCP-facing
service from the same dependency builders used by FastAPI:

- `get_chat_service()`
- `get_permission_service()`
- `get_document_management_service()`
- `get_rag_trace_service()`

`KnowledgeToolService` is orchestration only. It resolves the MCP service
identity, asks `PermissionService` for accessible Qdrant point IDs, then calls
the existing retrieval/chat/document services.

## Database Session Lifecycle

The MCP process is separate from the FastAPI process, but it uses the same
`get_session_factory()` and service constructors. Database sessions are not kept
open across MCP requests. Each service method opens a short-lived SQLAlchemy
session with `with self.session_factory() as session`, performs the lookup or
write, and closes the session at the end of the operation.

This keeps session ownership inside the existing services and prevents the MCP
server from exposing raw PostgreSQL access.

## Authentication

MCP v1 uses one concrete authentication model: a dedicated MCP service account.

Hermes sends:

```text
Authorization: Bearer <mcp-service-token>
```

The MCP server stores only the SHA-256 digest of that token in
`MCP_SERVICE_TOKEN_SHA256`. On each request, the MCP SDK bearer-token middleware
calls `MCPServiceAccountTokenVerifier`, which:

1. hashes the bearer token and compares it to `MCP_SERVICE_TOKEN_SHA256`;
2. loads the existing KB user configured by `MCP_SERVICE_ACCOUNT_EMAIL`;
3. rejects the request if the token is wrong or the KB user is missing/inactive;
4. maps the request to that KB user ID for ACL checks.

All MCP tool calls therefore run under normal existing KB ACL rows for the
service account. No credentials are hard-coded.

Future per-user delegated identity can be added by replacing the verifier and
identity resolver while keeping the same `KnowledgeToolService` boundary.

## Tools

MCP v1 is read-only.

### `search_knowledge`

Search accessible Document RAG and Code RAG chunks without generating a final
LLM answer.

Inputs:

- `query`
- `top_k`, default `5`, max `20`
- `content_type`: `all`, `document`, or `code`
- `request_id`, optional

Returns matched context, source type, filename/source path, scores, document
metadata, and code metadata when applicable.

### `ask_knowledge`

Use the existing full RAG pipeline and return an answer with sources.

Inputs:

- `question`
- `top_k`, default `5`, max `20`
- `request_id`, optional

This tool reuses `RAGChatService`, which reuses `RetrievalService` and
`RAGGenerationService`. It preserves the existing RAG trace format and saves a
best-effort trace row using the provided or generated request ID.

### `get_document`

Return metadata and chunk details for an accessible document.

Inputs:

- `document_id`
- `request_id`, optional

The tool calls `PermissionService.ensure_user_can_access_document()` before
reading document metadata.

### `search_code`

Search only accessible Code RAG chunks.

Inputs:

- `query`
- `top_k`, default `5`, max `20`
- `language`, optional
- `request_id`, optional

Returns code-specific metadata including repo, file path, language, symbol,
line range, score, and code context.

## Explicitly Out Of Scope

MCP v1 does not include:

- document upload
- document delete
- document reindex
- code repository ingest
- permission management
- database SQL tools
- raw PostgreSQL or Qdrant access
- agent logic
- multi-tenant or RBAC redesign

## Request IDs And Logs

Tools accept `request_id`. If missing, the MCP server reads `X-Request-ID` from
HTTP headers when available. If neither exists, it generates a UUID.

MCP tool calls write structured-style application logs with tool name,
request ID, KB user ID, and result count. `ask_knowledge` uses the existing
RAG trace fields and does not change trace or analytics schema.

## Deployment

The MCP service is a separate Docker Compose service behind the `mcp` profile:

```bash
docker compose --profile mcp up -d --build mcp
```

Required MCP environment:

- `MCP_SERVICE_ACCOUNT_EMAIL`
- `MCP_SERVICE_TOKEN_SHA256`
- `MCP_HOST`
- `MCP_PORT`
- `MCP_PATH`
- `MCP_PUBLIC_URL`

Generate a token digest:

```bash
python - <<'PY'
import hashlib
token = "replace-with-long-random-token"
print(hashlib.sha256(token.encode("utf-8")).hexdigest())
PY
```

Create or choose an existing KB user for `MCP_SERVICE_ACCOUNT_EMAIL`, then grant
that user normal document and repository ACL rows.

Hermes should connect to the MCP URL, for example:

```text
http://<kb-host>:8001/mcp
```

and send the raw MCP service token as a bearer token. In the inspected local
environment, Hermes-specific configuration is expected inside
`/sandbox/.hermes/config.yaml`, but no active Hermes sandbox configuration was
available on the host.

## Test Plan

- Unit-test service-account token verification and invalid-token rejection.
- Unit-test `search_knowledge` passes ACL-derived point IDs and content type
  filters into `RetrievalService`.
- Unit-test `search_code` uses code-only and optional language filters.
- Unit-test `get_document` calls `PermissionService` before document metadata.
- Unit-test `ask_knowledge` reuses `RAGChatService`, passes ACL point IDs, and
  saves a trace with the request ID.
- Existing RAG, ACL, vector filter, trace, analytics, and production-hardening
  tests must continue to pass.
