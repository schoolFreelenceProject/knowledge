from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.auth_dependencies import get_current_user
from app.api.users import (
    create_user,
    list_users,
    router,
    update_user_activation,
)
from app.schemas.users import CreateUserRequest, UpdateUserActivationRequest
from app.services.auth_service import (
    AuthenticatedUser,
    DuplicateUserError,
    UserNotFoundError,
)


class FakeUserManagementAuthService:
    def __init__(
        self,
        duplicate: bool = False,
        missing: bool = False,
    ) -> None:
        self.duplicate = duplicate
        self.missing = missing
        self.create_call: dict | None = None
        self.activation_call: dict | None = None

    def list_users(self):
        return [
            _build_user(
                user_id=2,
                email="analyst@example.com",
                is_active=True,
            )
        ]

    def create_user(self, email: str, password: str, is_active: bool = True):
        if self.duplicate:
            raise DuplicateUserError("Email is already registered.")

        self.create_call = {
            "email": email,
            "password": password,
            "is_active": is_active,
        }
        return _build_user(user_id=2, email=email, is_active=is_active)

    def update_user_activation(self, user_id: int, is_active: bool):
        if self.missing:
            raise UserNotFoundError(f"User {user_id} was not found.")

        self.activation_call = {
            "user_id": user_id,
            "is_active": is_active,
        }
        return _build_user(
            user_id=user_id,
            email="analyst@example.com",
            is_active=is_active,
        )


def _build_user(
    user_id: int = 1,
    email: str = "admin@example.com",
    is_active: bool = True,
) -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=user_id,
        email=email,
        is_active=is_active,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_list_users_returns_users_from_auth_service() -> None:
    response = list_users(
        current_user=_build_user(),
        auth_service=FakeUserManagementAuthService(),
    )

    assert len(response) == 1
    assert response[0].email == "analyst@example.com"
    assert response[0].is_active is True


def test_create_user_passes_active_flag_to_auth_service() -> None:
    auth_service = FakeUserManagementAuthService()

    response = create_user(
        request=CreateUserRequest(
            email="Analyst@Example.com",
            password="correct-password",
            is_active=False,
        ),
        current_user=_build_user(),
        auth_service=auth_service,
    )

    assert response.email == "analyst@example.com"
    assert response.is_active is False
    assert auth_service.create_call == {
        "email": "analyst@example.com",
        "password": "correct-password",
        "is_active": False,
    }


def test_create_user_maps_duplicate_email_to_409() -> None:
    with pytest.raises(HTTPException) as exc_info:
        create_user(
            request=CreateUserRequest(
                email="analyst@example.com",
                password="correct-password",
            ),
            current_user=_build_user(),
            auth_service=FakeUserManagementAuthService(duplicate=True),
        )

    assert exc_info.value.status_code == 409


def test_update_user_activation_passes_toggle_to_auth_service() -> None:
    auth_service = FakeUserManagementAuthService()

    response = update_user_activation(
        user_id=2,
        request=UpdateUserActivationRequest(is_active=False),
        current_user=_build_user(),
        auth_service=auth_service,
    )

    assert response.id == 2
    assert response.is_active is False
    assert auth_service.activation_call == {
        "user_id": 2,
        "is_active": False,
    }


def test_update_user_activation_maps_missing_user_to_404() -> None:
    with pytest.raises(HTTPException) as exc_info:
        update_user_activation(
            user_id=999,
            request=UpdateUserActivationRequest(is_active=True),
            current_user=_build_user(),
            auth_service=FakeUserManagementAuthService(missing=True),
        )

    assert exc_info.value.status_code == 404


def test_user_management_routes_require_jwt_dependency() -> None:
    protected_routes = [
        route for route in router.routes
        if getattr(route, "dependant", None) is not None
    ]

    assert protected_routes
    for route in protected_routes:
        dependency_calls = {
            dependency.call
            for dependency in route.dependant.dependencies
        }
        assert get_current_user in dependency_calls
