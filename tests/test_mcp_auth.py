import asyncio
import hashlib
from datetime import datetime, timezone

from app.core.config import AppSettings
from app.mcp.auth import MCP_READ_SCOPE, MCPServiceAccountTokenVerifier
from app.services.auth_service import AuthenticatedUser


class FakeAuthService:
    def __init__(self, user: AuthenticatedUser | None = None) -> None:
        self.user = user
        self.email: str | None = None

    def get_active_user_by_email(self, email: str) -> AuthenticatedUser:
        self.email = email
        if self.user is None:
            raise RuntimeError("missing user")

        return self.user


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=42,
        email="mcp-service@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _build_settings(token: str) -> AppSettings:
    return AppSettings(
        mcp_service_token_sha256=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        mcp_service_account_email="mcp-service@example.com",
    )


def test_mcp_service_account_token_verifier_maps_to_existing_kb_user(monkeypatch):
    token = "long-random-mcp-token"
    fake_auth_service = FakeAuthService(user=_build_user())
    monkeypatch.setattr("app.mcp.auth.get_settings", lambda: _build_settings(token))
    monkeypatch.setattr("app.mcp.auth.get_auth_service", lambda: fake_auth_service)

    access_token = asyncio.run(
        MCPServiceAccountTokenVerifier().verify_token(token)
    )

    assert access_token is not None
    assert access_token.scopes == [MCP_READ_SCOPE]
    assert access_token.subject == "42"
    assert access_token.claims["kb_user_id"] == 42
    assert access_token.claims["kb_user_email"] == "mcp-service@example.com"
    assert fake_auth_service.email == "mcp-service@example.com"


def test_mcp_service_account_token_verifier_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr("app.mcp.auth.get_settings", lambda: _build_settings("right"))
    monkeypatch.setattr("app.mcp.auth.get_auth_service", lambda: FakeAuthService())

    access_token = asyncio.run(
        MCPServiceAccountTokenVerifier().verify_token("wrong")
    )

    assert access_token is None
