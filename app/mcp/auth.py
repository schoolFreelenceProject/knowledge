import hashlib
import hmac
from dataclasses import dataclass

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from app.api.auth_dependencies import get_auth_service
from app.core.config import AppSettings, get_settings
from app.services.auth_service import AuthPersistenceError, InvalidTokenError


MCP_READ_SCOPE = "knowledge:read"
MCP_CLIENT_ID = "company-kb-mcp"


class MCPAuthenticationError(RuntimeError):
    """Raised when an MCP tool cannot resolve its service identity."""


@dataclass(frozen=True)
class MCPServiceIdentity:
    user_id: int
    email: str


class MCPServiceAccountTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        settings = get_settings()
        if not _token_matches(token=token, settings=settings):
            return None

        try:
            service_user = get_auth_service().get_active_user_by_email(
                settings.mcp_service_account_email
            )
        except (AuthPersistenceError, InvalidTokenError):
            return None

        return AccessToken(
            token=token,
            client_id=MCP_CLIENT_ID,
            scopes=[MCP_READ_SCOPE],
            subject=str(service_user.id),
            claims={
                "kb_user_id": service_user.id,
                "kb_user_email": service_user.email,
            },
        )


def resolve_mcp_service_identity() -> MCPServiceIdentity:
    access_token = get_access_token()
    if access_token is None:
        raise MCPAuthenticationError("MCP service account token is missing.")

    claims = access_token.claims or {}
    try:
        user_id = int(claims["kb_user_id"])
        email = str(claims["kb_user_email"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MCPAuthenticationError("MCP service account identity is invalid.") from exc

    return MCPServiceIdentity(user_id=user_id, email=email)


def validate_mcp_auth_settings(settings: AppSettings) -> None:
    if not settings.mcp_service_token_sha256:
        raise ValueError("MCP_SERVICE_TOKEN_SHA256 must be set to run the MCP server.")

    if not settings.mcp_service_account_email:
        raise ValueError("MCP_SERVICE_ACCOUNT_EMAIL must be set to run the MCP server.")


def _token_matches(token: str, settings: AppSettings) -> bool:
    if not settings.mcp_service_token_sha256 or not token:
        return False

    token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return hmac.compare_digest(token_digest, settings.mcp_service_token_sha256)
