from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.auth_dependencies import get_current_user
from app.services.auth_service import AuthenticatedUser, InvalidTokenError


class _FakeAuthService:
    def __init__(self, user: AuthenticatedUser | None = None) -> None:
        self.user = user

    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        if token != "valid-token" or self.user is None:
            raise InvalidTokenError("Invalid bearer token.")

        return self.user


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=1,
        email="admin@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_get_current_user_requires_bearer_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(
            credentials=None,
            auth_service=_FakeAuthService(),
        )

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_invalid_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="invalid-token",
            ),
            auth_service=_FakeAuthService(user=_build_user()),
        )

    assert exc_info.value.status_code == 401


def test_get_current_user_returns_authenticated_user() -> None:
    user = _build_user()

    current_user = get_current_user(
        credentials=HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token",
        ),
        auth_service=_FakeAuthService(user=user),
    )

    assert current_user is user
