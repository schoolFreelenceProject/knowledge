import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.auth_dependencies import get_auth_service
from app.services.auth_service import (
    DuplicateUserError,
    InvalidTokenError,
)


DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_MCP_EMAIL = "mcp-service@example.com"


def main() -> int:
    admin_email = os.getenv("KB_BOOTSTRAP_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip()
    admin_password = os.getenv("KB_BOOTSTRAP_ADMIN_PASSWORD", "").strip()
    mcp_email = os.getenv("MCP_SERVICE_ACCOUNT_EMAIL", DEFAULT_MCP_EMAIL).strip()
    mcp_password = os.getenv("MCP_SERVICE_ACCOUNT_PASSWORD", "").strip()

    if not admin_email or not admin_password:
        print(
            "KB_BOOTSTRAP_ADMIN_EMAIL and KB_BOOTSTRAP_ADMIN_PASSWORD "
            "must be set.",
            file=sys.stderr,
        )
        return 1

    if not mcp_email or not mcp_password:
        print(
            "MCP_SERVICE_ACCOUNT_EMAIL and MCP_SERVICE_ACCOUNT_PASSWORD "
            "must be set.",
            file=sys.stderr,
        )
        return 1

    auth_service = get_auth_service()
    admin_status = _ensure_active_user(
        auth_service=auth_service,
        email=admin_email,
        password=admin_password,
    )
    mcp_status = _ensure_active_user(
        auth_service=auth_service,
        email=mcp_email,
        password=mcp_password,
    )

    print(f"admin_user={admin_email} status={admin_status}")
    print(f"mcp_service_user={mcp_email} status={mcp_status}")
    return 0


def _ensure_active_user(auth_service, email: str, password: str) -> str:
    try:
        auth_service.get_active_user_by_email(email)
        return "exists"
    except InvalidTokenError:
        pass

    try:
        auth_service.create_user(email=email, password=password, is_active=True)
        return "created"
    except DuplicateUserError:
        for user in auth_service.list_users():
            if user.email == email.casefold():
                auth_service.update_user_activation(user_id=user.id, is_active=True)
                return "reactivated"
        raise


if __name__ == "__main__":
    raise SystemExit(main())
