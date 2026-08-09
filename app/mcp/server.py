from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.context import Context
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.api.dependencies import get_knowledge_tool_service
from app.core.config import AppSettings, get_settings
from app.core.logging import configure_logging
from app.mcp.auth import (
    MCP_READ_SCOPE,
    MCPServiceAccountTokenVerifier,
    resolve_mcp_service_identity,
    validate_mcp_auth_settings,
)


REQUEST_ID_HEADER = "X-Request-ID"


def create_mcp_server(settings: AppSettings | None = None) -> MCPServer:
    settings = settings or get_settings()
    server = MCPServer(
        name="company-knowledge-base",
        title="Company Knowledge Base",
        description=(
            "Read-only MCP tools for searching and asking the Company Knowledge Base."
        ),
        version="0.1.0",
        token_verifier=MCPServiceAccountTokenVerifier(),
        auth=AuthSettings(
            issuer_url=settings.mcp_public_url,
            resource_server_url=settings.mcp_public_url,
            required_scopes=[MCP_READ_SCOPE],
        ),
        log_level=settings.log_level,
    )

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health_check(_request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    @server.tool(
        description=(
            "Search accessible Document RAG and Code RAG knowledge without "
            "generating a final answer."
        ),
        structured_output=True,
    )
    def search_knowledge(
        query: str,
        top_k: int = 5,
        content_type: Literal["all", "document", "code"] = "all",
        request_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        identity = resolve_mcp_service_identity()
        response = get_knowledge_tool_service().search_knowledge(
            user_id=identity.user_id,
            query=query,
            top_k=top_k,
            content_type=content_type,
            request_id=_resolve_request_id(ctx=ctx, request_id=request_id),
        )
        return response.model_dump(mode="json")

    @server.tool(
        description=(
            "Use the existing full RAG pipeline to answer a question with sources."
        ),
        structured_output=True,
    )
    def ask_knowledge(
        question: str,
        top_k: int = 5,
        request_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        identity = resolve_mcp_service_identity()
        response = get_knowledge_tool_service().ask_knowledge(
            user_id=identity.user_id,
            question=question,
            top_k=top_k,
            request_id=_resolve_request_id(ctx=ctx, request_id=request_id),
        )
        return response.model_dump(mode="json")

    @server.tool(
        description="Return metadata and details for an accessible document.",
        structured_output=True,
    )
    def get_document(
        document_id: int,
        request_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        identity = resolve_mcp_service_identity()
        response = get_knowledge_tool_service().get_document(
            user_id=identity.user_id,
            document_id=document_id,
            request_id=_resolve_request_id(ctx=ctx, request_id=request_id),
        )
        return response.model_dump(mode="json")

    @server.tool(
        description="Search only accessible Code RAG chunks.",
        structured_output=True,
    )
    def search_code(
        query: str,
        top_k: int = 5,
        language: str | None = None,
        request_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        identity = resolve_mcp_service_identity()
        response = get_knowledge_tool_service().search_code(
            user_id=identity.user_id,
            query=query,
            top_k=top_k,
            language=language,
            request_id=_resolve_request_id(ctx=ctx, request_id=request_id),
        )
        return response.model_dump(mode="json")

    return server


def main() -> None:
    settings = get_settings()
    validate_mcp_auth_settings(settings)
    configure_logging(settings.log_level)
    server = create_mcp_server(settings)
    server.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path=settings.mcp_path,
        max_request_body_size=settings.max_request_body_bytes,
    )


def _resolve_request_id(
    ctx: Context | None,
    request_id: str | None,
) -> str | None:
    if request_id is not None and request_id.strip():
        return request_id

    if ctx is None or ctx.headers is None:
        return request_id

    for key, value in ctx.headers.items():
        if key.lower() == REQUEST_ID_HEADER.lower() and value.strip():
            return value

    return request_id


mcp = create_mcp_server()


if __name__ == "__main__":
    main()
