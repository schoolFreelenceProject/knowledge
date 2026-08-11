from dataclasses import dataclass
from datetime import datetime, timezone

from app.api.auth_dependencies import get_current_user
from app.api.permissions import (
    grant_code_repository_user_permission,
    grant_user_document_permission,
    list_code_repository_user_permissions,
    list_user_code_repository_permissions,
    list_user_document_permissions,
    revoke_code_repository_user_permission,
    revoke_user_document_permission,
    router,
)
from app.schemas.permissions import (
    GrantCodeRepositoryPermissionRequest,
    GrantDocumentToUserRequest,
)
from app.services.auth_service import AuthenticatedUser


@dataclass(frozen=True)
class FakeDocumentPermission:
    id: int
    document_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class FakeCodeRepositoryPermission:
    id: int
    repository_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class FakePermissionService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def list_document_permissions_for_user(self, user_id: int):
        timestamp = datetime.now(timezone.utc)
        return [
            FakeDocumentPermission(
                id=1,
                document_id=10,
                user_id=user_id,
                created_at=timestamp,
                updated_at=timestamp,
            )
        ]

    def grant_document_access(self, document_id: int, user_id: int):
        timestamp = datetime.now(timezone.utc)
        self.calls.append(("grant_document", document_id, user_id))
        return FakeDocumentPermission(
            id=1,
            document_id=document_id,
            user_id=user_id,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def revoke_document_access(self, document_id: int, user_id: int):
        self.calls.append(("revoke_document", document_id, user_id))
        return True

    def list_code_repository_permissions_for_user(self, user_id: int):
        timestamp = datetime.now(timezone.utc)
        return [
            FakeCodeRepositoryPermission(
                id=2,
                repository_id=20,
                user_id=user_id,
                created_at=timestamp,
                updated_at=timestamp,
            )
        ]

    def list_code_repository_permissions(self, repository_id: int):
        timestamp = datetime.now(timezone.utc)
        return [
            FakeCodeRepositoryPermission(
                id=2,
                repository_id=repository_id,
                user_id=7,
                created_at=timestamp,
                updated_at=timestamp,
            )
        ]

    def grant_code_repository_access(self, repository_id: int, user_id: int):
        timestamp = datetime.now(timezone.utc)
        self.calls.append(("grant_repository", repository_id, user_id))
        return FakeCodeRepositoryPermission(
            id=2,
            repository_id=repository_id,
            user_id=user_id,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def revoke_code_repository_access(self, repository_id: int, user_id: int):
        self.calls.append(("revoke_repository", repository_id, user_id))
        return True


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=1,
        email="admin@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_user_document_permissions_can_be_listed_granted_and_revoked() -> None:
    permission_service = FakePermissionService()

    listed = list_user_document_permissions(
        user_id=7,
        current_user=_build_user(),
        permission_service=permission_service,
    )
    granted = grant_user_document_permission(
        user_id=7,
        request=GrantDocumentToUserRequest(document_id=10),
        current_user=_build_user(),
        permission_service=permission_service,
    )
    revoked = revoke_user_document_permission(
        user_id=7,
        document_id=10,
        current_user=_build_user(),
        permission_service=permission_service,
    )

    assert listed[0].document_id == 10
    assert granted.user_id == 7
    assert revoked.revoked is True
    assert permission_service.calls == [
        ("grant_document", 10, 7),
        ("revoke_document", 10, 7),
    ]


def test_code_repository_permissions_can_be_listed_granted_and_revoked() -> None:
    permission_service = FakePermissionService()

    user_listed = list_user_code_repository_permissions(
        user_id=7,
        current_user=_build_user(),
        permission_service=permission_service,
    )
    repository_listed = list_code_repository_user_permissions(
        repository_id=20,
        current_user=_build_user(),
        permission_service=permission_service,
    )
    granted = grant_code_repository_user_permission(
        repository_id=20,
        request=GrantCodeRepositoryPermissionRequest(user_id=7),
        current_user=_build_user(),
        permission_service=permission_service,
    )
    revoked = revoke_code_repository_user_permission(
        repository_id=20,
        user_id=7,
        current_user=_build_user(),
        permission_service=permission_service,
    )

    assert user_listed[0].repository_id == 20
    assert repository_listed[0].user_id == 7
    assert granted.repository_id == 20
    assert revoked.revoked is True
    assert permission_service.calls == [
        ("grant_repository", 20, 7),
        ("revoke_repository", 20, 7),
    ]


def test_permission_management_routes_require_jwt_dependency() -> None:
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
