# MCP Server

The MCP layer exposes the Company Knowledge Base directly to Codex, Claude Code,
and other Streamable HTTP MCP clients as read-only retrieval tools. The
Knowledge Base remains a standalone backend/service, and MCP remains a separate
read-only service.

This milestone does not change the existing RAG architecture. It does not add
agent orchestration or workflow graph layers.

## Architecture

```text
Codex / Claude Code / MCP Client
 -> MCP Streamable HTTP
 -> Company Knowledge Base MCP Server
 -> existing KB service layer
 -> PermissionService
 -> RetrievalService
 -> PostgreSQL
 -> Qdrant
```

The MCP server reuses the existing service layer. It does not duplicate RAG,
ACL, PostgreSQL, Qdrant, reranker, trace, feedback, evaluation, or
analytics logic.

`app.api.dependencies.get_knowledge_tool_service()` composes the MCP-facing
service from the same dependency builders used by FastAPI:

- `get_retrieval_service()`
- `get_permission_service()`
- `get_document_management_service()`
- `get_rag_trace_service()`

`KnowledgeToolService` is orchestration only. It resolves the MCP service
identity, asks `PermissionService` for accessible Qdrant point IDs, then calls
the existing retrieval/document services. `ask_knowledge` additionally calls
the optional chat/generation service only when an internal generation provider
is configured.

## Database Session Lifecycle

The MCP process is separate from the FastAPI process, but it uses the same
`get_session_factory()` and service constructors. Database sessions are not kept
open across MCP requests. Each service method opens a short-lived SQLAlchemy
session with `with self.session_factory() as session`, performs the lookup or
write, and closes the session at the end of the operation.

This keeps session ownership inside the existing services and prevents the MCP
server from exposing raw PostgreSQL access.

## Authentication And ACL

MCP v1 uses one concrete vendor-neutral authentication model: a dedicated MCP
service account.

Clients send:

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

MCP v1 is read-only. The server advertises read-only tool annotations and
retrieval-first server instructions.

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

Backward-compatible optional internal-generation tool. When
`INTERNAL_GENERATION_ENABLED=true` and an internal generation provider is
available, this uses the existing RAG pipeline and returns an answer with
sources. In the default retrieval-first stack, it returns a clear unavailable
response and callers should use `search_knowledge` or `search_code`.

Inputs:

- `question`
- `top_k`, default `5`, max `20`
- `request_id`, optional

This tool preserves the existing RAG trace format and saves a best-effort trace
row using the provided or generated request ID.

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

## Deployment

The MCP service is a default Docker Compose service in the retrieval-first
stack. Ollama is not required for MCP search tools.

```bash
docker compose up -d --build mcp
```

Required MCP environment:

- `MCP_SERVICE_ACCOUNT_EMAIL`
- `MCP_SERVICE_TOKEN_SHA256`
- `MCP_HOST`
- `MCP_PORT`
- `MCP_PATH`
- `MCP_PUBLIC_URL`

`./start.sh` generates a local MCP token and digest automatically. To generate a
digest manually:

```bash
python - <<'PY'
import hashlib
token = "replace-with-long-random-token"
print(hashlib.sha256(token.encode("utf-8")).hexdigest())
PY
```

Create or choose an existing KB user for `MCP_SERVICE_ACCOUNT_EMAIL`, then grant
that user normal document and repository ACL rows.

The Codex-facing MCP URL for this milestone is:

```text
http://<knowledge-base-host>:8001/mcp
```

## Codex Configuration

The official Codex MCP configuration format was inspected in the current Codex
manual. Streamable HTTP MCP servers are configured in `config.toml` under a
`[mcp_servers.<name>]` table with `url`, optional
`bearer_token_env_var`, tool controls, and timeouts.

Use this exact config entry in `~/.codex/config.toml` or in a trusted project
`.codex/config.toml`:

```toml
[mcp_servers.company_knowledge_base]
url = "http://<knowledge-base-host>:8001/mcp"
bearer_token_env_var = "COMPANY_KB_MCP_TOKEN"
enabled = true
required = true
enabled_tools = [
  "search_knowledge",
  "get_document",
  "search_code",
]
default_tools_approval_mode = "writes"
startup_timeout_sec = 10
tool_timeout_sec = 60
```

`required = true` makes Codex fail startup/resume instead of silently continuing
without the Knowledge Base MCP server. `default_tools_approval_mode = "writes"`
keeps future non-read-only tools behind approval; the current four tools are
advertised as read-only.

### Codex CLI

Set the raw MCP service token in the Codex process environment:

```bash
export COMPANY_KB_MCP_TOKEN="<raw-mcp-service-token>"
```

Add the Streamable HTTP MCP server:

```bash
codex mcp add company_knowledge_base \
  --url http://<knowledge-base-host>:8001/mcp \
  --bearer-token-env-var COMPANY_KB_MCP_TOKEN
```

Inspect the saved config:

```bash
codex mcp list
codex mcp get company_knowledge_base --json
```

Start Codex and inspect connected MCP servers:

```bash
codex
```

Then type:

```text
/mcp
```

### Codex App

The Codex App and Codex CLI share the same Codex host configuration.

1. Set `COMPANY_KB_MCP_TOKEN` in the environment used to launch the app.
2. Open **Settings > Configuration > Open config.toml**.
3. Add the `[mcp_servers.company_knowledge_base]` config block above.
4. Restart the app.
5. Open **Settings > MCP servers** and confirm `company_knowledge_base` is enabled.
6. In a Codex chat, type `/mcp` and confirm the retrieval tools are listed.

Claude Code can use the same Streamable HTTP URL and bearer token. The MCP
server does not branch on client identity.

On macOS, a persistent app environment variable can be set with:

```bash
launchctl setenv COMPANY_KB_MCP_TOKEN "<raw-mcp-service-token>"
```

On Linux, launch the app from a shell that exports the variable. On Windows,
set the user environment variable before starting the app:

```powershell
setx COMPANY_KB_MCP_TOKEN "<raw-mcp-service-token>"
```

## Verification

Run the focused automated MCP checks:

```bash
python -m pytest \
  tests/test_codex_mcp_streamable_http.py \
  tests/test_knowledge_tool_service.py \
  tests/test_mcp_auth.py
```

These tests verify:

- valid service-account authentication over Streamable HTTP
- invalid bearer token rejection
- Codex-compatible MCP initialization
- discovery of `search_knowledge`, `ask_knowledge`, `get_document`, and `search_code`
- calls to all four tools over Streamable HTTP
- allowed ACL point filtering
- denied document ACL access
- empty retrieval responses
- unavailable MCP connection failure
- `ask_knowledge` explicit unavailable response when generation is disabled
  and RAG trace creation when it is called

Run the full local regression suite:

```bash
python -m compileall app tests
python -m pytest tests
docker compose config
```

Manual production smoke checks:

```bash
curl -fsS http://<knowledge-base-host>:8001/health
```

Invalid token check:

```bash
curl -i \
  -X POST http://<knowledge-base-host>:8001/mcp \
  -H 'Authorization: Bearer invalid-token' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Expected result: HTTP `401` with `invalid_token`.

After an `ask_knowledge` call with `request_id="mcp-smoke-ask"` in a deployment
where internal generation is enabled, verify that RAG tracing still persists:

```bash
docker compose exec postgres psql -U rag -d company_rag -c "
SELECT request_id, user_id, status, retrieval_mode, retrieved_count
FROM rag_traces
WHERE request_id = 'mcp-smoke-ask'
ORDER BY created_at DESC
LIMIT 1;
"
```

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
- workflow graph orchestration

## Request IDs And Logs

Tools accept `request_id`. If missing, the MCP server reads `X-Request-ID` from
HTTP headers when available. If neither exists, it generates a UUID.

MCP tool calls write structured-style application logs with tool name,
request ID, KB user ID, and result count. Retrieval tools do not require any
generation provider. `ask_knowledge` uses the existing RAG trace fields and does
not change trace or analytics schema.
