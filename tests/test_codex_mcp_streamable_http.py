import asyncio
import hashlib
import socket
from contextlib import closing
from datetime import datetime, timezone

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import httpx2, streamable_http_client

import app.mcp.auth as mcp_auth
import app.mcp.server as mcp_server
from app.core.config import AppSettings
from app.mcp.server import create_mcp_server
from app.schemas.mcp import (
    MCPAskKnowledgeResponse,
    MCPDocumentDetail,
    MCPSearchCodeResponse,
    MCPSearchKnowledgeResponse,
)
from app.services.auth_service import AuthenticatedUser


EXPECTED_TOOL_NAMES = {
    "search_knowledge",
    "ask_knowledge",
    "get_document",
    "search_code",
}
VALID_TOKEN = "valid-codex-mcp-token"


class FakeAuthService:
    def get_active_user_by_email(self, email: str) -> AuthenticatedUser:
        timestamp = datetime.now(timezone.utc)
        return AuthenticatedUser(
            id=55,
            email=email,
            is_active=True,
            created_at=timestamp,
            updated_at=timestamp,
        )


class FakeKnowledgeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def search_knowledge(self, **kwargs) -> MCPSearchKnowledgeResponse:
        self.calls.append(("search_knowledge", kwargs))
        return MCPSearchKnowledgeResponse(
            request_id=kwargs["request_id"],
            results=[],
        )

    def ask_knowledge(self, **kwargs) -> MCPAskKnowledgeResponse:
        self.calls.append(("ask_knowledge", kwargs))
        return MCPAskKnowledgeResponse(
            request_id=kwargs["request_id"],
            answer="No matching context found.",
            sources=[],
        )

    def get_document(self, **kwargs) -> MCPDocumentDetail:
        self.calls.append(("get_document", kwargs))
        timestamp = datetime.now(timezone.utc)
        return MCPDocumentDetail(
            request_id=kwargs["request_id"],
            id=kwargs["document_id"],
            filename="policy.md",
            file_type="markdown",
            storage_path="policy.md",
            file_hash="a" * 64,
            status="INDEXED",
            created_at=timestamp,
            updated_at=timestamp,
            chunk_count=0,
            chunks=[],
        )

    def search_code(self, **kwargs) -> MCPSearchCodeResponse:
        self.calls.append(("search_code", kwargs))
        return MCPSearchCodeResponse(
            request_id=kwargs["request_id"],
            results=[],
        )


def test_codex_streamable_http_discovers_and_calls_all_tools(monkeypatch) -> None:
    result = asyncio.run(_exercise_codex_streamable_http(monkeypatch))

    assert result["server_name"] == "company-knowledge-base"
    assert result["instructions"].startswith("Use these tools only for read-only")
    assert set(result["tool_names"]) == EXPECTED_TOOL_NAMES
    assert result["read_only_tools"] == EXPECTED_TOOL_NAMES
    assert result["invalid_token_status_code"] == 401
    assert result["invalid_token_error"] == "invalid_token"

    assert result["tool_outputs"]["search_knowledge"] == {
        "request_id": "req-search",
        "results": [],
    }
    assert result["tool_outputs"]["ask_knowledge"] == {
        "request_id": "req-ask",
        "answer": "No matching context found.",
        "sources": [],
    }
    assert result["tool_outputs"]["get_document"]["request_id"] == "req-document"
    assert result["tool_outputs"]["get_document"]["id"] == 1
    assert result["tool_outputs"]["search_code"] == {
        "request_id": "req-code",
        "results": [],
    }

    assert result["service_calls"] == [
        (
            "search_knowledge",
            {
                "user_id": 55,
                "query": "no matching policy",
                "top_k": 5,
                "content_type": "all",
                "request_id": "req-search",
            },
        ),
        (
            "ask_knowledge",
            {
                "user_id": 55,
                "question": "no matching policy",
                "top_k": 5,
                "request_id": "req-ask",
            },
        ),
        (
            "get_document",
            {
                "user_id": 55,
                "document_id": 1,
                "request_id": "req-document",
            },
        ),
        (
            "search_code",
            {
                "user_id": 55,
                "query": "no matching symbol",
                "top_k": 5,
                "language": None,
                "request_id": "req-code",
            },
        ),
    ]


def test_claude_code_uses_same_streamable_http_bearer_token_flow(
    monkeypatch,
) -> None:
    result = asyncio.run(_exercise_codex_streamable_http(monkeypatch))

    assert result["server_name"] == "company-knowledge-base"
    assert set(result["tool_names"]) == EXPECTED_TOOL_NAMES
    assert result["invalid_token_status_code"] == 401
    assert result["invalid_token_error"] == "invalid_token"
    assert result["tool_outputs"]["search_knowledge"] == {
        "request_id": "req-search",
        "results": [],
    }
    assert result["tool_outputs"]["search_code"] == {
        "request_id": "req-code",
        "results": [],
    }


def test_codex_mcp_unavailable_connection_fails_closed() -> None:
    port = _free_tcp_port()

    with pytest.raises(httpx2.TransportError):
        asyncio.run(_post_to_unavailable_mcp(port))


async def _exercise_codex_streamable_http(monkeypatch) -> dict:
    fake_service = FakeKnowledgeService()
    port = _free_tcp_port()
    settings = AppSettings(
        mcp_public_url=f"http://127.0.0.1:{port}/mcp",
        mcp_path="/mcp",
        mcp_service_token_sha256=hashlib.sha256(
            VALID_TOKEN.encode("utf-8")
        ).hexdigest(),
        mcp_service_account_email="mcp-service@example.com",
        log_level="WARNING",
    )
    monkeypatch.setattr(mcp_auth, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_auth, "get_auth_service", lambda: FakeAuthService())
    monkeypatch.setattr(
        mcp_server,
        "get_knowledge_tool_service",
        lambda: fake_service,
    )

    server = create_mcp_server(settings)
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        host="127.0.0.1",
    )
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    server_task = asyncio.create_task(uvicorn_server.serve())
    await _wait_for_server_start(uvicorn_server, server_task)

    try:
        url = f"http://127.0.0.1:{port}/mcp"
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {VALID_TOKEN}"}
        ) as http_client:
            async with streamable_http_client(
                url,
                http_client=http_client,
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    initialize_result = await session.initialize()
                    tool_list = await session.list_tools()
                    tools = tool_list.tools
                    tool_outputs = {}
                    for tool_name, arguments in {
                        "search_knowledge": {
                            "query": "no matching policy",
                            "request_id": "req-search",
                        },
                        "ask_knowledge": {
                            "question": "no matching policy",
                            "request_id": "req-ask",
                        },
                        "get_document": {
                            "document_id": 1,
                            "request_id": "req-document",
                        },
                        "search_code": {
                            "query": "no matching symbol",
                            "request_id": "req-code",
                        },
                    }.items():
                        call_result = await session.call_tool(tool_name, arguments)
                        tool_outputs[tool_name] = call_result.structured_content

        async with httpx2.AsyncClient(
            headers={"Authorization": "Bearer invalid-token"}
        ) as invalid_client:
            invalid_response = await invalid_client.post(
                url,
                headers={"accept": "application/json, text/event-stream"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
            )

        return {
            "server_name": initialize_result.server_info.name,
            "instructions": initialize_result.instructions,
            "tool_names": [tool.name for tool in tools],
            "read_only_tools": {
                tool.name
                for tool in tools
                if tool.annotations
                and tool.annotations.read_only_hint is True
                and tool.annotations.destructive_hint is False
            },
            "tool_outputs": tool_outputs,
            "service_calls": fake_service.calls,
            "invalid_token_status_code": invalid_response.status_code,
            "invalid_token_error": invalid_response.json()["error"],
        }
    finally:
        uvicorn_server.should_exit = True
        await server_task


async def _post_to_unavailable_mcp(port: int) -> None:
    async with httpx2.AsyncClient(timeout=0.2) as http_client:
        await http_client.post(
            f"http://127.0.0.1:{port}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            },
        )


async def _wait_for_server_start(
    server: uvicorn.Server,
    server_task: asyncio.Task,
) -> None:
    for _ in range(100):
        if server.started:
            return
        if server_task.done():
            server_task.result()
        await asyncio.sleep(0.05)

    raise RuntimeError("Timed out waiting for MCP test server to start.")


def _free_tcp_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
