from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.auth_dependencies import get_current_user
from app.api.code_repositories import (
    delete_code_repository,
    get_code_repository,
    list_code_repositories,
    reindex_code_repository,
    router,
)
from app.schemas.code import (
    CodeRepositoryDetail,
    CodeRepositorySummary,
    DeleteCodeRepositoryResponse,
    ReindexCodeRepositoryResponse,
)
from app.services.auth_service import AuthenticatedUser
from app.services.permission_service import (
    CodeRepositoryAccessDeniedError,
    PermissionPersistenceError,
)


class FakeCodeRepositoryManagementService:
    def __init__(self) -> None:
        self.repository_ids: list[int] | None = None
        self.deleted_repository_id: int | None = None
        self.reindexed_repository_id: int | None = None

    def list_repositories(self, repository_ids=None):
        self.repository_ids = repository_ids
        return []

    def get_repository(self, repository_id):
        timestamp = datetime.now(timezone.utc)
        summary = CodeRepositorySummary(
            id=repository_id,
            repo_name="repo",
            repo_url="file:///repo",
            branch="main",
            commit_sha="a" * 40,
            storage_path="repo/main/aaaaaaaa",
            status="INDEXED",
            created_at=timestamp,
            updated_at=timestamp,
            file_count=0,
            chunk_count=0,
        )
        return CodeRepositoryDetail(**summary.model_dump(), files=[], chunks=[])

    def delete_repository(self, repository_id):
        self.deleted_repository_id = repository_id
        return DeleteCodeRepositoryResponse(
            repository_id=repository_id,
            deleted_vectors=2,
            deleted_metadata=True,
            deleted_files=True,
            cleanup_warning=None,
        )

    def reindex_repository(self, repository_id):
        self.reindexed_repository_id = repository_id
        return ReindexCodeRepositoryResponse(
            repository_id=repository_id,
            status="INDEXED",
            files=1,
            chunks=2,
            stored_vectors=2,
            replaced_vectors=2,
            cleanup_warning=None,
        )


class FakePermissionService:
    def __init__(self, denied: bool = False) -> None:
        self.denied = denied

    def list_accessible_code_repository_ids(self, user_id: int) -> list[int]:
        return [20, 21]

    def ensure_user_can_access_code_repository(
        self,
        user_id: int,
        repository_id: int,
    ) -> None:
        if self.denied:
            raise CodeRepositoryAccessDeniedError(
                f"User {user_id} cannot access code repository {repository_id}."
            )


class FailingPermissionService(FakePermissionService):
    def list_accessible_code_repository_ids(self, user_id: int) -> list[int]:
        raise PermissionPersistenceError(
            "sqlalchemy.exc.OperationalError: SELECT * FROM code_repository_permissions"
        )


def _build_user() -> AuthenticatedUser:
    timestamp = datetime.now(timezone.utc)
    return AuthenticatedUser(
        id=7,
        email="developer@example.com",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_list_code_repositories_filters_by_accessible_repository_ids() -> None:
    repository_service = FakeCodeRepositoryManagementService()

    response = list_code_repositories(
        current_user=_build_user(),
        code_repository_management_service=repository_service,
        permission_service=FakePermissionService(),
    )

    assert response == []
    assert repository_service.repository_ids == [20, 21]


def test_list_code_repositories_hides_internal_permission_errors() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_code_repositories(
            current_user=_build_user(),
            code_repository_management_service=FakeCodeRepositoryManagementService(),
            permission_service=FailingPermissionService(),
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to verify repository access."
    assert "SELECT" not in exc_info.value.detail
    assert "code_repository_permissions" not in exc_info.value.detail


def test_get_code_repository_blocks_inaccessible_repository() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_code_repository(
            repository_id=20,
            current_user=_build_user(),
            code_repository_management_service=FakeCodeRepositoryManagementService(),
            permission_service=FakePermissionService(denied=True),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "You do not have access to this code repository."


def test_delete_code_repository_calls_management_service_after_acl_check() -> None:
    repository_service = FakeCodeRepositoryManagementService()

    response = delete_code_repository(
        repository_id=20,
        current_user=_build_user(),
        code_repository_management_service=repository_service,
        permission_service=FakePermissionService(),
    )

    assert response.deleted_vectors == 2
    assert repository_service.deleted_repository_id == 20


def test_reindex_code_repository_calls_management_service_after_acl_check() -> None:
    repository_service = FakeCodeRepositoryManagementService()

    response = reindex_code_repository(
        repository_id=20,
        current_user=_build_user(),
        code_repository_management_service=repository_service,
        permission_service=FakePermissionService(),
    )

    assert response.stored_vectors == 2
    assert repository_service.reindexed_repository_id == 20


def test_code_repository_management_routes_require_jwt_dependency() -> None:
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
